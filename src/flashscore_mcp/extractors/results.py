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
from .page_status import empty_or_raise
from .resolve import resolve_league_ref
from .window import take_until
from ..parsers.adapter import count_match_hints


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
    league = await resolve_league_ref(league)
    url = await _season_tab_url(league, season, "results")
    logger.info("get_results_history url={} mode={} limit={} since={}", url, mode, limit, since)
    if not url:
        raise ValueError(f"Unknown season {season!r} for league {league}")
    # A date bound can sit further down the list than a raw row count, so load
    # the whole tab and cut afterwards. A count alone stops once that many rows
    # are on the page.
    until_count = limit if limit is not None and not since else None
    html = await fetch_html(url, full=True, until_count=until_count)
    parsed = parse_matches(html)
    games = take_until(parsed, limit=limit, since=since)
    if not parsed:
        empty_or_raise(html, "results", parsed, raw_hints=count_match_hints(html))
    logger.info("Returning {} results", len(games))
    return games
