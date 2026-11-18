"""Recent team form from a Flashscore team page, by URL or by team name."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, urlparse

from loguru import logger

from ..config import settings
from ..models import MatchCollection
from ..parsers.adapter import count_match_hints
from ..parsers.matches import parse_matches
from .fetch import fetch_html
from .http_util import get_json
from .page_status import LoadFailed, page_outcome
from .resolve import parse_name_and_country

_TEAM_PATH = re.compile(r"/team/[^/?#]+/[A-Za-z0-9]+/?", re.I)
_TEAM_PARTS = re.compile(r"/team/([^/?#]+)/([A-Za-z0-9]{6,12})/?", re.I)

# Flashscore's own search box calls this public endpoint.
SEARCH_URL = (
    "https://s.livesport.services/api/v2/search/"
    "?q={q}&lang-id=1&type-ids=1,2,3,4&project-id=2&project-type-id=1"
)
_TEAM_TYPE_ID = 2


@dataclass
class TeamRef:
    slug: str
    id: str
    name: Optional[str] = None
    match: Optional[str] = None  # search match quality: exact, prefix, words, fuzzy

    @property
    def path(self) -> str:
        return f"/team/{self.slug}/{self.id}/"

    @property
    def url(self) -> str:
        return settings.base_url.rstrip("/") + self.path


def team_ref_from_url(team: str) -> TeamRef | None:
    raw = (team or "").strip()
    if not raw:
        return None
    path = urlparse(raw).path if raw.startswith("http") else raw
    found = _TEAM_PARTS.search(path if path.startswith("/") else f"/{path}")
    if not found:
        return None
    return TeamRef(slug=found.group(1), id=found.group(2))


def _team_results_url(team: str) -> str | None:
    ref = team_ref_from_url(team)
    return f"{ref.url}results/" if ref else None


def parse_search_team_paths(html: str) -> list[str]:
    return list(dict.fromkeys(_TEAM_PATH.findall(html)))


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _words_match(query: str, label: str) -> bool:
    """Every query word starts a label word or abbreviates a run of them ('la' ~ 'los angeles')."""
    words = label.split()
    runs = {"".join(w[0] for w in words[i:j]) for i in range(len(words)) for j in range(i + 2, len(words) + 1)}
    q_words = query.split()
    return bool(q_words) and all(any(w.startswith(q) for w in words) or q in runs for q in q_words)


def pick_search_team(
    results, name: str, country: Optional[str] = None, sport: Optional[str] = None
) -> TeamRef | None:
    """Best team hit of the sport: exact name, then name prefix, then fuzzy; men's sides first.

    With a sport, hits from other sports are dropped, so 'LA Galaxy' cannot
    land on a cricket team.
    """
    if not isinstance(results, list):
        return None
    want_sport = None
    if sport:
        from .league_teams import sport_id

        want_sport = sport_id(sport)
    wanted = _norm(name)
    want_country = _norm(country) if country else None
    scored = []
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            continue
        if (item.get("type") or {}).get("id") != _TEAM_TYPE_ID:
            continue
        if want_sport is not None and (item.get("sport") or {}).get("id") != want_sport:
            continue
        slug, ident = item.get("url"), item.get("id")
        if not slug or not ident:
            continue
        label = _norm(item.get("name") or "")
        item_country = _norm((item.get("defaultCountry") or {}).get("name") or "")
        if want_country and item_country and want_country not in item_country and item_country not in want_country:
            continue
        gender = ((item.get("gender") or {}).get("name") or "").lower()
        words_match = _words_match(wanted, label)
        score = (
            0 if label == wanted
            else 1 if label.startswith(wanted) or wanted.startswith(label)
            else 2 if words_match
            else 3,
            0 if gender in ("", "men") else 1,
            index,
        )
        quality = ("exact", "prefix", "words", "fuzzy")[score[0]]
        scored.append((score, TeamRef(slug=slug, id=ident, name=item.get("name"), match=quality)))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0])
    return scored[0][1]


async def search_team(team: str, sport: Optional[str] = "football") -> TeamRef | None:
    name, country = parse_name_and_country(team)
    data = await get_json(SEARCH_URL.format(q=quote(name)))
    ref = pick_search_team(data, name, country, sport)
    if ref:
        logger.info("Resolved team {!r} -> {}", team, ref.path)
    return ref


def team_note(team: str, ref: TeamRef, how: str) -> str:
    shown = ref.name or ref.slug.replace("-", " ").title()
    note = f"Team {team!r} resolved to {shown} ({ref.url}) {how}."
    if ref.match == "fuzzy":
        note += " The name did not match closely; check it, or pass league or a team URL."
    return note


async def resolve_team_noted(team: str, sport: Optional[str] = "football", league=None) -> tuple[TeamRef, str]:
    """The team, plus a note saying which team was picked and how.

    With a league (a LeagueContext), the league's own teams are tried first;
    global search (restricted to the sport) is the fallback.
    """
    direct = team_ref_from_url(team)
    if direct:
        return direct, team_note(team, direct, "from the URL")
    if not (team or "").strip():
        raise ValueError("team is required: a team name such as 'Arsenal' or a URL like /team/arsenal/hA1Zm19f/.")
    if league is not None:
        from .league_teams import match_league_team

        found, close = match_league_team(parse_name_and_country(team)[0], league.teams)
        if found:
            ref = TeamRef(slug=found.slug, id=found.id, name=found.display)
            note = team_note(team, ref, f"from {league.name} teams")
            return ref, f"{note} {close}" if close else note
    ref = await resolve_team(team, sport=sport)
    how = f"by Flashscore search ({sport or 'any sport'})"
    if league is not None:
        how += f", not found among {league.name} teams"
    return ref, team_note(team, ref, how)


async def resolve_team(team: str, sport: Optional[str] = "football") -> TeamRef:
    direct = team_ref_from_url(team)
    if direct:
        return direct
    if not (team or "").strip():
        raise ValueError("team is required: a team name such as 'Arsenal' or a URL like /team/arsenal/hA1Zm19f/.")
    ref = await search_team(team, sport)
    if ref is None:
        raise LoadFailed(
            f"Could not find a Flashscore team page for {team!r}. "
            "Pass a team URL such as /team/arsenal/hA1Zm19f/ or a clearer team name, "
            "optionally with its country, such as 'Arsenal (England)'.",
            reason="no-data",
        )
    return ref


async def _resolve_team_url(team: str) -> str:
    ref = await resolve_team(team)
    return f"{ref.url}results/"


async def get_team_form(
    team: str,
    last_n: int = 10,
    league: Optional[str] = None,
    sport: str = "football",
    league_only: bool = False,
) -> MatchCollection:
    if last_n < 1:
        raise ValueError("last_n must be at least 1")
    notes: list[str] = []
    context = None
    if league:
        from .league_teams import load_league

        context = await load_league(league, sport)
        notes.append(f"League: {context.name} ({context.url}), resolved by {context.source}.")
    elif league_only:
        raise ValueError("league_only needs a league.")
    ref, note = await resolve_team_noted(team, sport, context)
    notes.append(note)
    url = f"{ref.url}results/"
    logger.info("get_team_form url={} last_n={}", url, last_n)
    # Filtering to one competition may drop rows, so read further down the list.
    html = await fetch_html(url, full=True, until_count=last_n * (3 if league_only else 1))
    parsed = raw = parse_matches(html)
    if context is not None and league_only:
        from .league_teams import competition_matches

        if context.competition:
            parsed = [g for g in parsed if competition_matches(g.competition, context)]
            notes.append(f"Only {context.competition} games (league_only).")
        else:
            notes.append("league_only ignored: the league's competition label could not be read; all competitions shown.")
    elif context is not None:
        notes.append("All competitions shown; pass league_only=true for league games only.")
    items = parsed[:last_n]
    if raw and not parsed:
        return MatchCollection(
            status="empty",
            reason="no-league-games",
            items=[],
            errors=[f"None of the {len(raw)} recent games read were in {context.competition}."],
            notes=notes,
        )
    if not parsed:
        status, reason = page_outcome(
            html, tab="team", parsed_count=0, raw_hints=count_match_hints(html)
        )
        if status == "failed":
            raise LoadFailed(
                f"Failed to load team form from {url}.",
                reason=reason or "parse-failed",
            )
        return MatchCollection(status="empty", reason=reason or "no-matches-scheduled", items=[], notes=notes)
    return MatchCollection(status="ok", items=items, notes=notes)
