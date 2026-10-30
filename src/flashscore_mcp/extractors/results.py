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
    # No limit = full season. Keep pressing Show more until the button is gone.
    # A limit stops once that many matches are loaded, or the button is gone.
    if limit is None:
        html = await fetch_html(url, full=True)
    else:
        html = await fetch_html(url, show_more=None, until_count=limit)
    games = parse_matches(html)
    if since:
        games = [game for game in games if not game.date or game.date > since]
    if limit:
        games = games[:limit]
    # Adaptive note: Flashscore results tabs currently embed only the most recent
    # rounds in the initial HTML/feed. A functional Show-more that expands the full
    # season is not exposed in headless mode. Callers should treat counts well
    # below a full season (e.g. < 200 for a 20-team league) as partial.
    if not limit and len(games) < 150:
        logger.warning(
            "Results appear truncated ({} matches). Full season from Round 1 is not available from the results tab in the current markup.",
            len(games),
        )
    logger.info("Returning {} results", len(games))
    return games
