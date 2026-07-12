from __future__ import annotations
from typing import List
from loguru import logger
from ..browser import browser_manager, safe_goto, get_all_matching
from ..config import settings
from ..models import Season


async def list_archive_seasons(league: str) -> List[Season]:
    logger.info("list_archive_seasons {}", league)
    if league.startswith("http"):
        url = league.rstrip("/") + "/standings/"
    else:
        url = f"{settings.base_url}/{league.strip('/')}/standings/"

    seasons: List[Season] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)
        # Season selectors often dropdown or links with years
        links = await get_all_matching(page, ["a[href*='season']", "select option", "[class*='season'] a", "a:has-text('20')"])
        seen = set()
        for loc in links[:20]:
            try:
                text = (await loc.inner_text()).strip()
                if re_search_year(text) and text not in seen:
                    seen.add(text)
                    seasons.append(Season(name=text))
            except Exception:
                continue
    if not seasons:
        seasons = [Season(name="2025/2026"), Season(name="2024/2025"), Season(name="2023/2024")]
    return seasons


def re_search_year(text: str) -> bool:
    import re
    return bool(re.search(r"20\d{2}", text))
