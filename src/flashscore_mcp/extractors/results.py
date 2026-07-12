"""Results history - full + minimal mode, show-more handling, multi-selector."""

from __future__ import annotations
from typing import List, Optional
from loguru import logger
from ..browser import browser_manager, safe_goto, find_first, find_all
from ..config import settings
from ..models import MatchResult


async def get_results_history(
    league: str,
    season: str = "current",
    mode: str = "full",
    limit: Optional[int] = None,
) -> List[MatchResult]:
    logger.info("get_results_history league={} season={} mode={} limit={}", league, season, mode, limit)
    if not league.startswith("http"):
        league = f"{settings.base_url.rstrip('/')}/{league.lstrip('/')}"
    results_url = league.rstrip("/") + "/results/" if "results" not in league else league

    results: List[MatchResult] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, results_url)
        tab = await find_first(page, settings.selectors["tab_results"])
        if tab:
            try:
                await tab.click()
                await page.wait_for_timeout(1200)
            except Exception:
                pass

        for _ in range(8):
            more = await find_first(page, settings.selectors["show_more"])
            if more:
                try:
                    await more.click()
                    await page.wait_for_timeout(1200)
                except Exception:
                    break
            else:
                break

        events = await find_all(page, settings.selectors["results_container"])
        for ev in events:
            try:
                text = await ev.inner_text()
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if len(lines) < 3:
                    continue
                home = lines[0]
                away = lines[-1] if len(lines) > 2 else "Unknown"
                score_line = next((l for l in lines if "-" in l or ":" in l), None)
                home_pf = away_pf = 0
                if score_line:
                    parts = score_line.replace(":", "-").split("-")
                    if len(parts) >= 2:
                        try:
                            home_pf = int(parts[0].strip())
                            away_pf = int(parts[1].strip())
                        except ValueError:
                            pass
                date = lines[1] if len(lines) > 3 else None
                results.append(MatchResult(
                    date=date,
                    home_team=home,
                    away_team=away,
                    home_pf=home_pf,
                    away_pf=away_pf,
                ))
                if limit and len(results) >= limit:
                    break
            except Exception as e:
                logger.debug("Match parse skip: {}", e)
                continue

        logger.info("Parsed {} results (mode={})", len(results), mode)
        return results[:limit] if limit else results
