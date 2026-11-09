"""League news tab. The article card markup is shared across sports."""
from __future__ import annotations

import asyncio
from typing import List

from loguru import logger

from ..models import NewsItem
from ..parsers.news import parse_article_page, parse_news
from .fetch import fetch_html
from .http_util import get_text
from .page_status import empty_or_raise
from .resolve import resolve_league_ref
from .results import _league_url

# The list cards only carry a title and a relative time. Each article page
# has the summary (meta description) and the exact publish timestamp; they
# are plain server-rendered HTML, so a bounded parallel GET is enough.
_ARTICLE_BUDGET_S = 12.0
_ARTICLE_TIMEOUT_S = 6.0


async def _enrich(item: NewsItem) -> NewsItem:
    html = await get_text(item.link, timeout=_ARTICLE_TIMEOUT_S, browser_fallback=False)
    if not html:
        return item
    found = parse_article_page(html, item.link)
    return item.model_copy(update={k: v for k, v in found.items() if v})


async def get_news(league: str, limit: int = 10) -> List[NewsItem]:
    league = await resolve_league_ref(league)
    url = _league_url(league, "current", "news")
    logger.info("get_news url={}", url)
    html = await fetch_html(url)
    items = parse_news(html)[:limit]
    if not items:
        empty_or_raise(html, "news", items)
        return items
    tasks = [asyncio.ensure_future(_enrich(item)) for item in items]
    done, pending = await asyncio.wait(tasks, timeout=_ARTICLE_BUDGET_S)
    for task in pending:
        task.cancel()
    enriched = []
    for item, task in zip(items, tasks):
        if task in done and not task.cancelled() and task.exception() is None:
            enriched.append(task.result())
        else:
            enriched.append(item)
    logger.info(
        "Returning {} news items ({} with summary)",
        len(enriched),
        sum(1 for item in enriched if item.summary),
    )
    return enriched
