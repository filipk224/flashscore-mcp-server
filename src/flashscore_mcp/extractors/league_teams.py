"""An explicit league for team lookups: its path, its teams, its season format.

get_h2h and get_team_form take an optional ``league``. When it is given:

* The league is resolved within the requested sport: a URL or path, a
  well-known name ('Premier League', 'MLS'), 'England: Premier League' or
  'Premier League (England)', else Flashscore's own search restricted to
  tournaments of that sport.
* One load of the league's results page gives both the season label and
  archive (calendar vs split year) and the league's teams: every result row
  links to a match URL that carries both teams' slug and id.
* Team names are matched against those teams first (exact, acronym such as
  LAFC, short forms such as LA Galaxy or Man Utd), before any global search.
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Iterable, Optional
from urllib.parse import quote, urlparse

from loguru import logger

from ..config import settings
from ..parsers.league import parse_league_page
from ..parsers.matches import parse_matches
from ..seasons import LeagueSeasons
from .http_util import get_json
from .resolve import WELL_KNOWN, country_slug, normalize_key, slugify

# Flashscore search sport ids (the "sport" object on each search hit).
SPORT_IDS = {
    "football": 1,
    "soccer": 1,
    "tennis": 2,
    "basketball": 3,
    "hockey": 4,
    "ice-hockey": 4,
    "american-football": 5,
    "baseball": 6,
    "handball": 7,
    "rugby": 8,
    "rugby-union": 8,
    "floorball": 9,
    "futsal": 11,
    "volleyball": 12,
    "cricket": 13,
    "darts": 14,
    "snooker": 15,
    "aussie-rules": 18,
    "rugby-league": 19,
}

LEAGUE_SEARCH_URL = (
    "https://s.livesport.services/api/v2/search/"
    "?q={q}&lang-id=1&type-ids=1&project-id=2&project-type-id=1"
)
_TOURNAMENT_TYPE_ID = 1
_LEAGUE_TTL_S = 6 * 3600

# Two-team match URLs: /match/<sport>/<slug>-<id>/<slug>-<id>/
_MATCH_TEAMS = re.compile(r"/match/[^/]+/([a-z0-9-]+)-([A-Za-z0-9]{8})/([a-z0-9-]+)-([A-Za-z0-9]{8})/")

# Nicknames that no string rule can derive.
NICKNAMES = {
    "spurs": "tottenham",
    "wolves": "wolverhampton",
    "man u": "manchester united",
    "man utd": "manchester united",
    "man united": "manchester united",
    "man city": "manchester city",
    "gunners": "arsenal",
    "barca": "barcelona",
    "psg": "paris saint germain",
    "inter": "inter",
    "ny red bulls": "new york red bulls",
}
_SUFFIXES = {"fc", "sc", "cf", "afc", "fk", "sk", "ac", "cd", "club", "the"}


def sport_id(sport: Optional[str]) -> int:
    key = (sport or "football").strip().lower().replace(" ", "-").replace("_", "-")
    if key not in SPORT_IDS:
        raise ValueError(f"Unknown sport {sport!r}. Use a Flashscore sport slug such as football, basketball or hockey.")
    return SPORT_IDS[key]


def sport_slug(sport: Optional[str]) -> str:
    key = (sport or "football").strip().lower().replace(" ", "-").replace("_", "-")
    return {"soccer": "football", "ice-hockey": "hockey", "rugby-union": "rugby"}.get(key, key)


@dataclass
class LeagueTeam:
    slug: str
    id: str
    names: set[str] = field(default_factory=set)

    @property
    def display(self) -> str:
        shown = sorted(self.names, key=lambda n: (-len(n), n))
        return shown[0] if shown else self.slug.replace("-", " ").title()

    @property
    def path(self) -> str:
        return f"/team/{self.slug}/{self.id}/"


@dataclass
class LeagueContext:
    path: str  # sport/country/slug
    name: str
    competition: Optional[str]  # 'USA: MLS', as team pages label their rows
    seasons: Optional[LeagueSeasons]
    teams: list[LeagueTeam]
    source: str  # how the league was resolved

    @property
    def url(self) -> str:
        return f"{settings.base_url.rstrip('/')}/{self.path}/"


# --- league path ------------------------------------------------------------

_COUNTRY_COLON = re.compile(r"^\s*(?P<country>[^:/]+?)\s*:\s*(?P<name>.+?)\s*$")
_NAME_PAREN = re.compile(r"^\s*(?P<name>.+?)\s*\((?P<country>[^)]+)\)\s*$")


def parse_league_text(text: str) -> tuple[str, Optional[str]]:
    """'England: Premier League' / 'Premier League (England)' -> (name, country)."""
    raw = (text or "").strip()
    found = _COUNTRY_COLON.match(raw)
    if found and not raw.lower().startswith("http"):
        return found.group("name"), found.group("country")
    found = _NAME_PAREN.match(raw)
    if found:
        return found.group("name"), found.group("country")
    return raw, None


def path_from_url(text: str) -> Optional[str]:
    raw = (text or "").strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        raw = urlparse(raw).path
    parts = [p for p in raw.strip("/").split("/") if p]
    if len(parts) >= 3 and " " not in raw and ":" not in raw and parts[0] not in ("team", "match", "player"):
        return "/".join(parts[:3])
    return None


def pick_league_hit(results, name: str, country: Optional[str], sport: str) -> Optional[str]:
    """Best tournament hit of the requested sport: exact name, then country, then search order."""
    if not isinstance(results, list):
        return None
    want_sport = sport_id(sport)
    wanted = normalize_key(name)
    want_country = country_slug(country) if country else None
    scored = []
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            continue
        if (item.get("type") or {}).get("id") != _TOURNAMENT_TYPE_ID:
            continue
        if (item.get("sport") or {}).get("id") != want_sport:
            continue
        slug = item.get("url")
        item_country = (item.get("defaultCountry") or {}).get("name") or ""
        if not slug or not item_country:
            continue
        c_slug = country_slug(item_country)
        if want_country and c_slug != want_country:
            continue
        label = normalize_key(item.get("name") or "")
        gender = ((item.get("gender") or {}).get("name") or "").lower()
        score = (0 if label == wanted else 1 if label.startswith(wanted) else 2, 0 if gender in ("", "men") else 1, index)
        scored.append((score, f"{sport_slug(sport)}/{c_slug}/{slug}"))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0])
    return scored[0][1]


async def resolve_league_path(league: str, sport: str = "football") -> tuple[str, str]:
    """(sport/country/slug, how it was found) for a league of the given sport."""
    raw = (league or "").strip()
    if not raw:
        raise ValueError("league is empty. Pass a league name such as 'Premier League' or a path like /football/england/premier-league/.")
    direct = path_from_url(raw)
    if direct:
        return direct, "path"
    want = sport_slug(sport)
    name, country = parse_league_text(raw)
    known = WELL_KNOWN.get(normalize_key(name))
    if known and known.split("/")[0] == want and (not country or country_slug(country) == known.split("/")[1]):
        return known, "well-known name"
    data = await get_json(LEAGUE_SEARCH_URL.format(q=quote(name)))
    hit = pick_league_hit(data, name, country, want)
    if hit:
        return hit, "Flashscore search"
    if country:
        from .resolve import _discover_named_league

        found = await _discover_named_league(name, country)
        if found and found.split("/")[0] == want:
            return found, "country menu"
    raise ValueError(
        f"Could not find a {want} league called {raw!r}. Use a path like /{want}/england/premier-league/ "
        "or a name with its country, such as 'England: Premier League'."
    )


# --- league teams -----------------------------------------------------------

def _slug_words(slug: str) -> str:
    return slug.replace("-", " ")


def _similar(name: str, slug: str) -> int:
    a, b = set(normalize_key(name).split()), set(_slug_words(slug).split())
    shared = len(a & b)
    prefix = sum(1 for x in a for y in b if x != y and (x.startswith(y) or y.startswith(x)))
    return shared * 2 + prefix


def teams_from_results(html: str) -> list[LeagueTeam]:
    """Teams of a league from its results rows (names plus slug and id from the match URLs)."""
    teams: dict[str, LeagueTeam] = {}
    for game in parse_matches(html):
        found = _MATCH_TEAMS.search(game.match_url or "")
        if not found:
            continue
        s1, i1, s2, i2 = found.groups()
        home, away = game.home_team or "", game.away_team or ""
        # The URL lists the two teams alphabetically, not home then away.
        straight = _similar(home, s1) + _similar(away, s2)
        crossed = _similar(home, s2) + _similar(away, s1)
        pairs = [(s1, i1, home), (s2, i2, away)] if straight >= crossed else [(s1, i1, away), (s2, i2, home)]
        for slug, ident, name in pairs:
            team = teams.setdefault(ident, LeagueTeam(slug=slug, id=ident))
            if name.strip():
                team.names.add(" ".join(name.split()))
    return list(teams.values())


def _strip_suffixes(words: list[str]) -> list[str]:
    kept = [w for w in words if w not in _SUFFIXES]
    return kept or words


def _initials(words: list[str]) -> str:
    return "".join(w[0] for w in words if w)


def team_aliases(team: LeagueTeam) -> set[str]:
    """Normalized names a user may type for this team."""
    out: set[str] = set()
    for name in set(team.names) | {_slug_words(team.slug)}:
        words = normalize_key(name).split()
        if not words:
            continue
        out.add(" ".join(words))
        core = _strip_suffixes(words)
        out.add(" ".join(core))
        out.add(_initials(words))
        if len(words) >= 3:
            # Los Angeles Galaxy -> la galaxy, New York Red Bulls -> ny red bulls,
            # Los Angeles FC -> lafc
            short = [_initials(words[:2])] + words[2:]
            out.add(" ".join(short))
            out.add("".join(short))
        if len(core) >= 3:
            out.add(_initials(core))
            if core == words:
                # New York City -> nycfc, the club's own short form
                out.add(_initials(core) + "fc")
    return {a for a in out if len(a) >= 3}


def _token_prefix(query: list[str], words: list[str]) -> bool:
    """Each query word starts the matching name word, in order (man utd ~ manchester utd)."""
    if not query or len(query) > len(words):
        return False
    return all(w.startswith(q) for q, w in zip(query, words))


def match_score(query: str, team: LeagueTeam) -> Optional[int]:
    """0 exact/alias, 1 nickname, 2 word prefixes, 3 contained; None for no match."""
    q = normalize_key(query)
    if not q:
        return None
    aliases = team_aliases(team)
    if q in aliases:
        return 0
    nick = NICKNAMES.get(q)
    if nick and any(a == nick or a.startswith(nick) for a in aliases):
        return 1
    q_words = q.split()
    for name in set(team.names) | {_slug_words(team.slug)}:
        words = normalize_key(name).split()
        if _token_prefix(q_words, words) or _token_prefix(q_words, _strip_suffixes(words)):
            return 2
    if len(q) >= 4 and any(q in a for a in aliases):
        return 3
    return None


def match_league_team(query: str, teams: Iterable[LeagueTeam]) -> tuple[Optional[LeagueTeam], Optional[str]]:
    """Best team for a typed name, and a note when the choice was a close call."""
    scored = []
    for team in teams:
        score = match_score(query, team)
        if score is not None:
            scored.append((score, len(team.display), team))
    if not scored:
        return None, None
    scored.sort(key=lambda row: (row[0], row[1]))
    best = scored[0]
    # Any other team that matched as well as a word prefix is a real rival.
    rivals = [row[2].display for row in scored[1:] if row[0] <= max(best[0], 2)]
    note = None
    if rivals:
        note = f"{query!r} also matched {', '.join(rivals[:3])}; picked {best[2].display}. Pass a team URL to choose."
    return best[2], note


# --- league context (one page load, cached) ---------------------------------

_cache: dict[str, tuple[float, LeagueContext]] = {}


def _league_name(info_name: str, path: str) -> str:
    cleaned = re.sub(r"\s+\d{4}(?:\s*[/\-]\s*\d{2,4})?.*$", "", info_name or "").strip()
    return cleaned or path.split("/")[-1].replace("-", " ").title()


def context_from_html(html: str, path: str, source: str) -> LeagueContext:
    info = parse_league_page(html)
    name = _league_name(info.name, path)
    seasons = LeagueSeasons(name, info.season, tuple(item.name for item in info.archive_seasons))
    competition = None
    for game in parse_matches(html):
        if game.competition:
            competition = game.competition
            break
    return LeagueContext(
        path=path,
        name=name,
        competition=competition,
        seasons=seasons if seasons.format else None,
        teams=teams_from_results(html),
        source=source,
    )


async def load_league(league: str, sport: str = "football", deadline: Optional[float] = None) -> LeagueContext:
    path, source = await resolve_league_path(league, sport)
    cached = _cache.get(path)
    if cached and time.monotonic() - cached[0] < _LEAGUE_TTL_S:
        return cached[1]
    from ..browser import browser_manager
    from .h2h_season import _goto_list

    remaining = settings.queue_wait_s if deadline is None else max(0.0, min(settings.queue_wait_s, deadline - time.monotonic()))
    async with browser_manager.new_page(queue_wait_s=remaining) as page:
        await _goto_list(page, f"{settings.base_url.rstrip('/')}/{path}/results/")
        html = await page.content()
    context = context_from_html(html, path, source)
    if not context.teams:
        logger.warning("league {} results page listed no teams", path)
    else:
        _cache[path] = (time.monotonic(), context)
    logger.info("league {} -> {} teams, season format {}", path, len(context.teams), context.seasons and context.seasons.format)
    return context


def competition_matches(row_competition: Optional[str], context: LeagueContext) -> bool:
    """True when a team-page row belongs to the league (its header reads 'USA: MLS...')."""
    if not row_competition or not context.competition:
        return False
    row = normalize_key(row_competition)
    want = normalize_key(context.competition)
    if row == want:
        return True
    # 'USA: MLS - Play Offs' is the same league; 'USA: MLS Next Pro' is not.
    if not row.startswith(want + " "):
        return False
    return set(row[len(want):].split()) <= _STAGE_WORDS


_STAGE_WORDS = {
    "play", "off", "offs", "playoff", "playoffs", "relegation", "promotion", "championship",
    "group", "groups", "round", "final", "finals", "stage", "winners", "losers", "qualification",
}
