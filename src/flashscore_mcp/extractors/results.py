"""Results history with show-more handling and multi-selector adaptability."""

from __future__ import annotations
from typing import List, Optional
from loguru import logger
from ..browser import browser_manager, safe_goto, find_first_locator, get_all_matching
from ..config import settings
from ..models import MatchResult


async def get_results_history(
    league: str,
    season: str = "current",
    mode: str = "full",
    limit: Optional[int] = None,
) -> List[MatchResult]:
    logger.info("get_results_history league={} season={} mode={}", league, season, mode)

    if league.startswith("http"):
        url = league.rstrip("/") + "/results/"
    else:
        url = f"{settings.base_url}/{league.strip('/')}/results/"

    results: List[MatchResult] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)

        # Click show more a few times for full history
        for _ in range(5):
            more = await find_first_locator(page, settings.selectors["show_more"], timeout=2000)
            if more:
                try:
                    await more.click()
                    await page.wait_for_timeout(800)
                except Exception:
                    break
            else:
                break

        events = await get_all_matching(page, settings.selectors["results_rows"])
        for ev in events[: (limit or 100)]:
            try:
                text = await ev.inner_text()
                # Simple parse - improve with better cell selectors
                # Typical: date | home - away | score
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if len(lines) < 3:
                    continue
                # Placeholder robust parse - real would use sub-locators for home/away/score
                home = lines[1] if len(lines) > 1 else "Home"
                away = lines[2] if len(lines) > 2 else "Away"
                # Score often "1-0" or separate
                home_pf, away_pf = 0, 0
                for l in lines:
                    if "-" in l and l.replace("-", "").replace(" ", "").isdigit():
                        parts = l.split("-")
                        if len(parts) == 2:
                            home_pf = int(parts[0].strip() or 0)
                            away_pf = int(parts[1].strip() or 0)
                            break
                results.append(MatchResult(
                    date=lines[0] if lines else None,
                    home_team=home,
                    away_team=away,
                    home_pf=home_pf,
                    away_pf=away_pf,
                ))
            except Exception:
                continue

    if mode == "minimal":
        # Already minimal
        pass

    logger.info("Extracted {} results", len(results))
    return results
