"""League news tab. The article card markup is shared across sports."""
from __future__ import annotations

from typing import List

from loguru import logger

from ..models import NewsItem
from ..parsers.news import parse_news
from .fetch import fetch_html
from .results import _league_url


async def get_news(league: str, limit: int = 10) -> List[NewsItem]:
    url = _league_url(league, "current", "news")
    logger.info("get_news url={}", url)
    items = parse_news(await fetch_html(url))[:limit]
    logger.info("Returning {} news items", len(items))
    return items
