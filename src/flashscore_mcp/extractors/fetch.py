"""Playwright fetch. The sport parsers never open a browser."""
from __future__ import annotations

from typing import Optional

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
        return await page.content()
