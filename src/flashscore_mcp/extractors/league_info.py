"""League identity: sport, country, tabs, and archive seasons."""
from __future__ import annotations

from loguru import logger

from ..models import LeagueInfo
from ..parsers.league import parse_league_page
from .fetch import fetch_html
from .results import _league_url


async def get_league(league: str) -> LeagueInfo:
    url = _league_url(league, "current", "standings")
    root = url[: -len("standings/")]
    logger.info("get_league url={}", root)
    return parse_league_page(await fetch_html(root))
