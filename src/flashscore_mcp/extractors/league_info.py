"""League identity: sport, country, tabs, and archive seasons."""
from __future__ import annotations

from loguru import logger

from ..models import LeagueInfo
from ..parsers.league import parse_league_page
from .fetch import fetch_html
from .page_status import empty_or_raise
from .resolve import resolve_league_ref
from .results import _league_url


async def get_league(league: str) -> LeagueInfo:
    league = await resolve_league_ref(league)
    url = _league_url(league, "current", "standings")
    root = url[: -len("standings/")]
    logger.info("get_league url={}", root)
    html = await fetch_html(root)
    info = parse_league_page(html)
    if not info.name and not info.tabs:
        empty_or_raise(html, "league", [])
    return info
