"""Standings extractor with multi-fallback selectors for adaptability."""

from __future__ import annotations
from typing import List
from loguru import logger
from ..browser import browser_manager, safe_goto, find_first_locator, get_all_matching
from ..config import settings
from ..models import StandingRow
from urllib.parse import urljoin


async def get_standings(league: str, season: str = "current") -> List[StandingRow]:
    """Get standings. league can be full URL or slug path. Uses resilient table selectors."""
    logger.info("get_standings league={} season={}", league, season)

    # Resolve URL
    if league.startswith("http"):
        url = league.rstrip("/") + "/standings/"
    else:
        url = f"{settings.base_url}/{league.strip('/')}/standings/"

    if season != "current":
        # Archive often uses /standings/#/season or similar; keep simple for now
        url = url  # TODO: append season param when pattern known

    rows: List[StandingRow] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)

        table = await find_first_locator(page, settings.selectors["standings_table"])
        if not table:
            logger.warning("No standings table found")
            return rows

        # Try to parse rows (flexible)
        trs = table.locator("tr")
        count = await trs.count()
        for i in range(1, min(count, 50)):  # skip header
            try:
                cells = trs.nth(i).locator("td, th")
                ccount = await cells.count()
                if ccount < 5:
                    continue
                pos_text = (await cells.nth(0).inner_text()).strip()
                team = (await cells.nth(1).inner_text()).strip()
                # Heuristic column mapping (common: Pos Team MP W D L GF GA Pts Form)
                played = int((await cells.nth(2).inner_text()).strip() or 0)
                # Flexible for W/D/L/PF/PA
                wins = int((await cells.nth(3).inner_text()).strip() or 0) if ccount > 3 else 0
                # etc. - real sites vary; improve with header detection later
                pf = 0
                pa = 0
                form = None
                if ccount > 7:
                    try:
                        pf = int((await cells.nth(6).inner_text()).strip() or 0)
                        pa = int((await cells.nth(7).inner_text()).strip() or 0)
                    except Exception:
                        pass
                if ccount > 9:
                    form = (await cells.nth(ccount - 1).inner_text()).strip()

                if team and pos_text.isdigit():
                    rows.append(StandingRow(
                        position=int(pos_text),
                        team=team,
                        played=played,
                        wins=wins,
                        losses=0,  # placeholder - parse properly in next iteration
                        draws=None,
                        pf=pf,
                        pa=pa,
                        form=form,
                    ))
            except Exception as e:
                logger.debug("Row parse skip: {}", e)
                continue

    logger.info("Parsed {} standing rows", len(rows))
    return rows
