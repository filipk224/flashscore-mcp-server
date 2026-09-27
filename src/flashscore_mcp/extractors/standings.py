"""Standings. One header-driven parser for every sampled sport."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from loguru import logger

from ..config import settings
from ..models import StandingsPage
from ..parsers.archive import parse_archive, resolve_season
from ..parsers.standings import parse_standings
from .fetch import fetch_html
from .results import _league_url

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
    url = _league_url(league, "current", "standings")
    logger.info("get_standings url={} season={} view={}", url, season, view)
    html = await fetch_html(url)
    if season not in ("current", "", None):
        seasons = parse_archive(html)
        target, names = resolve_season(seasons, season)
        if not target:
            return StandingsPage(kind="unknown-season", available_seasons=names)
        url = urljoin(settings.base_url, target).rstrip("/") + "/standings/"
        html = await fetch_html(url)
    found = _view_url(html, view)
    if view != "overall" and found:
        html = await fetch_html(urljoin(settings.base_url, found))
    return parse_standings(html)
