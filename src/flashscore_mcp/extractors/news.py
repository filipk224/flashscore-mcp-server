"""League news tab extractor — titles + links. No cache."""
from __future__ import annotations
from typing import List
from urllib.parse import urljoin
from loguru import logger
from ..browser import browser_manager, safe_goto
from ..config import settings
from ..models import NewsItem
from .results import _league_url

async def get_news(league: str, limit: int = 10) -> List[NewsItem]:
    url = _league_url(league, "current", "news")
    logger.info("get_news url={}", url)
    items: List[NewsItem] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)
        raw = await page.evaluate("""() => {
              const nodes = Array.from(document.querySelectorAll("a[href*='/news/'], article a, [class*='news'] a, [class*='article'] a"));
              return nodes.map(a => ({title: (a.innerText || a.getAttribute('title') || '').trim(), href: a.getAttribute('href') || ''}));
            }""")
    seen = set()
    for n in raw:
        title = (n.get("title") or "").strip()
        href = (n.get("href") or "").strip()
        if not href or not title or len(title) < 18:
            continue
        if title.lower() in ("news", "more news", "standings"):
            continue
        full = urljoin(settings.base_url, href)
        if full in seen:
            continue
        seen.add(full)
        items.append(NewsItem(title=title[:240], link=full))
        if len(items) >= limit:
            break
    logger.info("Returning {} news items", len(items))
    return items
