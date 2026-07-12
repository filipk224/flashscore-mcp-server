from __future__ import annotations
from typing import List
from loguru import logger
from ..browser import browser_manager, safe_goto, get_all_matching
from ..config import settings
from ..models import NewsItem
from urllib.parse import urljoin


async def get_news(league: str, limit: int = 10) -> List[NewsItem]:
    logger.info("get_news {}", league)
    # News often at /news/ or league specific
    url = f"{settings.base_url}/news/" if not league.startswith("http") else league.rstrip("/") + "/news/"
    items: List[NewsItem] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)
        # Simple links
        links = await get_all_matching(page, ["a[href*='/news/']", "article a", "[class*='news'] a"])
        seen = set()
        for loc in links[:limit * 2]:
            try:
                href = await loc.get_attribute("href") or ""
                title = (await loc.inner_text()).strip()
                if href and title and href not in seen and len(title) > 10:
                    seen.add(href)
                    items.append(NewsItem(
                        title=title[:200],
                        link=urljoin(settings.base_url, href),
                    ))
                    if len(items) >= limit:
                        break
            except Exception:
                continue
    return items
