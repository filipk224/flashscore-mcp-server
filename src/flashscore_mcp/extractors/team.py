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


def pick_search_team(results, name: str, country: Optional[str] = None) -> TeamRef | None:
    """Best team hit: exact name first, then men's senior sides, then search order."""
    if not isinstance(results, list):
        return None
    wanted = _norm(name)
    want_country = _norm(country) if country else None
    scored = []
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            continue
        if (item.get("type") or {}).get("id") != _TEAM_TYPE_ID:
            continue
        slug, ident = item.get("url"), item.get("id")
        if not slug or not ident:
            continue
        label = _norm(item.get("name") or "")
        item_country = _norm((item.get("defaultCountry") or {}).get("name") or "")
        if want_country and item_country and want_country not in item_country and item_country not in want_country:
            continue
        gender = ((item.get("gender") or {}).get("name") or "").lower()
        score = (
            0 if label == wanted else 1 if label.startswith(wanted) or wanted.startswith(label) else 2,
            0 if gender in ("", "men") else 1,
            index,
        )
        scored.append((score, TeamRef(slug=slug, id=ident, name=item.get("name"))))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0])
    return scored[0][1]


async def search_team(team: str) -> TeamRef | None:
    name, country = parse_name_and_country(team)
    data = await get_json(SEARCH_URL.format(q=quote(name)))
    ref = pick_search_team(data, name, country)
    if ref:
        logger.info("Resolved team {!r} -> {}", team, ref.path)
    return ref


async def resolve_team(team: str) -> TeamRef:
    direct = team_ref_from_url(team)
    if direct:
        return direct
    if not (team or "").strip():
        raise ValueError("team is required: a team name such as 'Arsenal' or a URL like /team/arsenal/hA1Zm19f/.")
    ref = await search_team(team)
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


async def get_team_form(team: str, last_n: int = 10) -> MatchCollection:
    if last_n < 1:
        raise ValueError("last_n must be at least 1")
    url = await _resolve_team_url(team)
    logger.info("get_team_form url={} last_n={}", url, last_n)
    html = await fetch_html(url, full=True, until_count=last_n)
    parsed = parse_matches(html)
    items = parsed[:last_n]
    if not parsed:
        status, reason = page_outcome(
            html, tab="team", parsed_count=0, raw_hints=count_match_hints(html)
        )
        if status == "failed":
            raise LoadFailed(
                f"Failed to load team form from {url}.",
                reason=reason or "parse-failed",
            )
        return MatchCollection(status="empty", reason=reason or "no-matches-scheduled", items=[])
    return MatchCollection(status="ok", items=items)
