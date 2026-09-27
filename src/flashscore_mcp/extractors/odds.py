"""Odds tab. Archived seasons omit the tab and return an empty list."""
from __future__ import annotations

from urllib.parse import urljoin

from loguru import logger

from ..config import settings
from ..models import OddsPrice
from ..parsers.archive import parse_archive, resolve_season
from ..parsers.odds import parse_odds
from .fetch import fetch_html
from .results import _league_url


async def get_odds(league: str, season: str = "current") -> list[OddsPrice]:
    url = _league_url(league, "current", "odds")
    if season not in ("current", "", None):
        html = await fetch_html(_league_url(league, "current", "standings"))
        target, _names = resolve_season(parse_archive(html), season)
        if not target:
            return []
        season_html = await fetch_html(urljoin(settings.base_url, target))
        if 'title="Odds"' not in season_html:
            logger.info("No odds tab for season {}", season)
            return []
        url = urljoin(settings.base_url, target).rstrip("/") + "/odds/"
    logger.info("get_odds url={}", url)
    return parse_odds(await fetch_html(url))
