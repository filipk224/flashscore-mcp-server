from __future__ import annotations
from typing import List
from loguru import logger
from ..browser import browser_manager, safe_goto, find_first, find_all
from ..config import settings
from ..models import Fixture

async def get_upcoming_fixtures(league: str, limit: int = 20) -> List[Fixture]:
    logger.info("get_upcoming_fixtures league={} limit={}", league, limit)
    if not league.startswith("http"):
        league = f"{settings.base_url.rstrip('/')}/{league.lstrip('/')}"
    url = league.rstrip("/") + "/fixtures/" if "fixtures" not in league else league
    fixtures: List[Fixture] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)
        tab = await find_first(page, settings.selectors["tab_fixtures"])
        if tab:
            try:
                await tab.click()
                await page.wait_for_timeout(1000)
            except Exception:
                pass
        events = await find_all(page, settings.selectors["results_container"])
        for ev in events[:limit]:
            try:
                text = await ev.inner_text()
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if len(lines) >= 2:
                    fixtures.append(Fixture(
                        home_team=lines[0],
                        away_team=lines[-1],
                        date=lines[1] if len(lines) > 2 else None,
                    ))
            except Exception:
                continue
    return fixtures
