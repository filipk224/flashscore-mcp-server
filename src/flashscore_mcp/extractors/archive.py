from __future__ import annotations
from typing import List
from loguru import logger
from ..browser import browser_manager, safe_goto, find_all
from ..config import settings
from ..models import Season

async def list_archive_seasons(league: str) -> List[Season]:
    logger.info("list_archive_seasons league={}", league)
    if not league.startswith("http"):
        league = f"{settings.base_url.rstrip('/')}/{league.lstrip('/')}"
    seasons: List[Season] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, league)
        links = await find_all(page, ["a[href*='20']", "select option", "[class*='season'] a"])
        seen = set()
        for link in links:
            try:
                text = (await link.inner_text()).strip()
                href = await link.get_attribute("href") or ""
                if any(y in text for y in ["202", "2023", "2024", "2025", "2026"]) and text not in seen:
                    seen.add(text)
                    seasons.append(Season(name=text, url=href if href.startswith("http") else None))
            except Exception:
                continue
        if not seasons:
            seasons = [Season(name="2025/2026"), Season(name="2024/2025"), Season(name="2023/2024")]
    return seasons
