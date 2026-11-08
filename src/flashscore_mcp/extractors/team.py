"""Recent team form from a Flashscore team page or search."""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from loguru import logger

from ..config import settings
from ..models import MatchCollection
from ..parsers.adapter import count_match_hints
from ..parsers.matches import parse_matches
from .fetch import fetch_html
from .page_status import LoadFailed, page_outcome

_TEAM_PATH = re.compile(r"/team/[^/?#]+/[A-Za-z0-9]+/?", re.I)


def _team_results_url(team: str) -> str | None:
    raw = (team or "").strip()
    if not raw:
        return None
    path = raw
    if raw.startswith("http"):
        path = urlparse(raw).path
    match = _TEAM_PATH.search(path if path.startswith("/") else f"/{path}")
    if match:
        base = match.group(0).rstrip("/")
        return f"{settings.base_url.rstrip('/')}{base}/results/"
    return None


def parse_search_team_paths(html: str) -> list[str]:
    return list(dict.fromkeys(_TEAM_PATH.findall(html)))


async def _resolve_team_url(team: str) -> str:
    direct = _team_results_url(team)
    if direct:
        return direct
    query = team.strip()
    search_url = f"{settings.base_url.rstrip('/')}/search/?q={query}"
    html = await fetch_html(search_url)
    paths = parse_search_team_paths(html)
    if not paths:
        raise LoadFailed(
            f"Could not find a Flashscore team page for {team!r}. "
            "Pass a team URL such as /team/arsenal/hA1Zm19f/ or a clearer team name.",
            reason="no-data",
        )
    path = paths[0].rstrip("/")
    return f"{settings.base_url.rstrip('/')}{path}/results/"


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
