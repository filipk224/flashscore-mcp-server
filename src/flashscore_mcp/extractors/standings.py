"""Standings. One header-driven parser for every sampled sport."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from loguru import logger

from ..config import settings
from ..models import StandingsPage
from ..parsers.standings import parse_standings
from ..parsers.adapter import count_standings_hints
from .fetch import fetch_html
from .page_status import empty_or_raise
from .resolve import resolve_league_ref
from .results import _league_url, resolve_archive_season

_VIEW_TAIL = {
    "overall": "/standings/overall/",
    "home": "/standings/home/",
    "away": "/standings/away/",
    "form": "/form/",
}


def _view_url(html: str, view: str) -> str | None:
    tail = _VIEW_TAIL.get(view)
    if not tail:
        return None
    match = re.search(rf'href="([^"]*{re.escape(tail)})"', html)
    return match.group(1) if match else None


async def get_standings(league: str, season: str = "current", view: str = "overall") -> StandingsPage:
    league = await resolve_league_ref(league)
    url = _league_url(league, "current", "standings")
    if season not in ("current", "", None):
        target, names = await resolve_archive_season(league, season)
        if not target:
            return StandingsPage(kind="unknown-season", available_seasons=names)
        url = urljoin(settings.base_url, target).rstrip("/") + "/standings/"
    logger.info("get_standings url={} season={} view={}", url, season, view)
    html = await fetch_html(url)
    found = _view_url(html, view)
    if view != "overall" and found:
        html = await fetch_html(urljoin(settings.base_url, found))
    page = parse_standings(html)
    if not page.sections and page.kind != "draw":
        empty_or_raise(html, "standings", page.sections, raw_hints=count_standings_hints(html))
    return page
