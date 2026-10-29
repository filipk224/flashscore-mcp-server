"""Results history. The match-row parser is shared with fixtures and the summary tab."""
from __future__ import annotations

from typing import List, Optional
from urllib.parse import urljoin

from loguru import logger

from ..config import settings
from ..models import MatchResult
from ..parsers.archive import parse_archive, resolve_season
from ..parsers.matches import parse_matches
from .fetch import fetch_html


def _league_url(league: str, season: str, tab: str) -> str:
    if league.startswith("http"):
        base = league.rstrip("/")
        for suffix in ("/results", "/fixtures", "/standings", "/news", "/archive", "/odds"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
        return f"{base}/{tab}/" if tab else f"{base}/"
    key = league.strip("/")
    if season and season not in ("current",) and season.isdigit() and f"-{season}" not in key:
        parts = key.split("/")
        parts[-1] = f"{parts[-1]}-{season}"
        key = "/".join(parts)
    return f"{settings.base_url}/{key}/{tab}/" if tab else f"{settings.base_url}/{key}/"


async def _season_tab_url(league: str, season: str, tab: str) -> str | None:
    if season in ("current", "", None):
        return _league_url(league, "current", tab)
    html = await fetch_html(_league_url(league, "current", "standings"))
    target, _names = resolve_season(parse_archive(html), season)
    if not target:
        return None
    return urljoin(settings.base_url, target).rstrip("/") + f"/{tab}/"


async def get_results_history(
    league: str,
    season: str = "current",
    mode: str = "full",
    limit: Optional[int] = None,
    since: Optional[str] = None,
) -> List[MatchResult]:
    url = await _season_tab_url(league, season, "results")
    logger.info("get_results_history url={} mode={} limit={}", url, mode, limit)
    if not url:
        return []
    # Keep pressing Show more until the requested count is loaded, or the button is gone.
    html = await fetch_html(url, show_more=40, until_count=limit)
    games = parse_matches(html)
    if since:
        games = [game for game in games if not game.date or game.date > since]
    if limit:
        games = games[:limit]
    logger.info("Returning {} results", len(games))
    return games
