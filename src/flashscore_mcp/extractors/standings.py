"""Standings extractor - multi-selector for auto-adapt, production ready."""

from __future__ import annotations
from typing import List
from loguru import logger
from ..browser import browser_manager, safe_goto, find_first, find_all
from ..config import settings
from ..models import StandingRow


async def get_standings(league: str, season: str = "current") -> List[StandingRow]:
    """Get standings. Accepts full URL or path. Tries /standings/ tab."""
    logger.info("get_standings league={} season={}", league, season)
    if not league.startswith("http"):
        league = f"{settings.base_url.rstrip('/')}/{league.lstrip('/')}"
    standings_url = league.rstrip("/") + "/standings/" if "standings" not in league else league

    rows: List[StandingRow] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, standings_url)
        tab = await find_first(page, settings.selectors["tab_standings"])
        if tab:
            try:
                await tab.click()
                await page.wait_for_timeout(1500)
            except Exception:
                pass

        table = await find_first(page, settings.selectors["standings_table"])
        if not table:
            logger.warning("No standings table found for {}", standings_url)
            return rows

        trs = await find_all(page, settings.selectors["standings_row"])
        pos = 1
        for tr in trs:
            try:
                text = await tr.inner_text()
                cells = [c.strip() for c in text.split("\n") if c.strip()]
                if len(cells) < 5:
                    continue
                team = cells[1] if len(cells) > 1 else "Unknown"
                nums = []
                for c in cells:
                    try:
                        nums.append(int(c))
                    except ValueError:
                        pass
                if len(nums) < 3:
                    continue
                played = nums[0] if nums else 0
                wins = nums[1] if len(nums) > 1 else 0
                draws = nums[2] if len(nums) > 2 else 0
                losses = nums[3] if len(nums) > 3 else 0
                pf = nums[4] if len(nums) > 4 else 0
                pa = nums[5] if len(nums) > 5 else 0
                points = nums[-1] if nums else 0
                form = cells[-1] if cells and any(x in cells[-1] for x in "WDL") else None

                rows.append(StandingRow(
                    position=pos,
                    team=team,
                    played=played,
                    wins=wins,
                    losses=losses,
                    draws=draws,
                    pf=pf,
                    pa=pa,
                    pd=pf - pa if isinstance(pf, int) else None,
                    points=points,
                    form=form,
                ))
                pos += 1
                if pos > 30:
                    break
            except Exception as e:
                logger.debug("Row parse skip: {}", e)
                continue

        logger.info("Parsed {} standing rows", len(rows))
        return rows
