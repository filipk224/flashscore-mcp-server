from __future__ import annotations
from typing import List
from loguru import logger
from ..browser import browser_manager, safe_goto, get_all_matching
from ..config import settings
from ..models import Fixture


async def get_upcoming_fixtures(league: str, limit: int = 20) -> List[Fixture]:
    logger.info("get_upcoming_fixtures {}", league)
    if league.startswith("http"):
        url = league.rstrip("/") + "/fixtures/"
    else:
        url = f"{settings.base_url}/{league.strip('/')}/fixtures/"

    fixtures: List[Fixture] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)
        events = await get_all_matching(page, settings.selectors["results_rows"])
        for ev in events[:limit]:
            try:
                text = await ev.inner_text()
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if len(lines) >= 3:
                    fixtures.append(Fixture(
                        date=lines[0],
                        home_team=lines[1],
                        away_team=lines[2],
                    ))
            except Exception:
                continue
    return fixtures
