"""Playwright fetch. The sport parsers never open a browser."""
from __future__ import annotations

from typing import Optional

from loguru import logger

from ..browser import browser_manager, click_show_more, safe_goto


async def fetch_html(
    url: str,
    show_more: Optional[int] = 0,
    until_count: Optional[int] = None,
    full: bool = False,
) -> str:
    """show_more=None or full=True loads every page (button gone). Limited fetches pass until_count."""
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)
        if full or show_more is None or until_count is not None or (show_more or 0) > 0:
            await click_show_more(
                page,
                max_clicks=None if full or show_more is None else show_more,
                until_count=until_count,
            )
            # Extra adaptive attempts: scroll the match container and re-check
            try:
                await page.evaluate('''() => {
                    const c = document.querySelector('.leagues--static, .event--leagues, [class*="event--leagues"]');
                    if (c) c.scrollTop = c.scrollHeight;
                    window.scrollTo(0, document.body.scrollHeight);
                }''')
                await page.wait_for_timeout(800)
                await click_show_more(page, max_clicks=5, until_count=until_count)
            except Exception as e:
                logger.debug("Adaptive scroll attempt failed: {}", e)
        return await page.content()
