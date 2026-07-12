from __future__ import annotations
from typing import List
from loguru import logger
from ..browser import browser_manager, safe_goto, find_all
from ..config import settings
from ..models import NewsItem
from urllib.parse import urljoin

async def get_news(league: str, limit: int = 10) -> List[NewsItem]:
    logger.info("get_news league={} limit={}", league, limit)
    if not league.startswith("http"):
        league = f"{settings.base_url.rstrip('/')}/{league.lstrip('/')}"
    url = league.rstrip("/") + "/news/" if "news" not in league else league
    items: List[NewsItem] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)
        links = await find_all(page, ["a[href*='/news/']", "a[class*='news']", "article a"])
        for link in links[:limit*2]:
            try:
                href = await link.get_attribute("href") or ""
                title = (await link.inner_text()).strip()
                if title and href and len(title) > 10:
                    full = urljoin(settings.base_url, href)
                    items.append(NewsItem(title=title, link=full))
                    if len(items) >= limit:
                        break
            except Exception:
                continue
    return items
