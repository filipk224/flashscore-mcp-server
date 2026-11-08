"""League news tab. The article card markup is shared across sports."""
from __future__ import annotations

from typing import List

from loguru import logger

from ..models import NewsItem
from ..parsers.news import parse_news
from .fetch import fetch_html
from .page_status import empty_or_raise
from .resolve import resolve_league_ref
from .results import _league_url


async def get_news(league: str, limit: int = 10) -> List[NewsItem]:
    league = await resolve_league_ref(league)
    url = _league_url(league, "current", "news")
    logger.info("get_news url={}", url)
    html = await fetch_html(url)
    items = parse_news(html)[:limit]
    if not items:
        empty_or_raise(html, "news", items)
    logger.info("Returning {} news items", len(items))
    return items
