"""Archive seasons from league_archive_data. The object is the same on every sport."""
from __future__ import annotations

from typing import List

from loguru import logger

from ..models import Season
from ..parsers.archive import parse_archive
from .fetch import fetch_html
from .results import _league_url


async def list_archive_seasons(league: str) -> List[Season]:
    url = _league_url(league, "current", "archive")
    logger.info("list_archive_seasons url={}", url)
    seasons = parse_archive(await fetch_html(url))
    logger.info("Found {} archive seasons", len(seasons))
    return seasons
