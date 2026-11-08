"""Archive seasons from league_archive_data. The object is the same on every sport."""
from __future__ import annotations

from typing import List

from loguru import logger

from ..models import Season
from ..parsers.archive import parse_archive
from .fetch import fetch_html
from .page_status import empty_or_raise
from .resolve import resolve_league_ref
from .results import _league_url


async def list_archive_seasons(league: str) -> List[Season]:
    league = await resolve_league_ref(league)
    url = _league_url(league, "current", "archive")
    logger.info("list_archive_seasons url={}", url)
    html = await fetch_html(url)
    seasons = parse_archive(html)
    if not seasons:
        empty_or_raise(html, "archive", seasons)
    logger.info("Found {} archive seasons", len(seasons))
    return seasons
