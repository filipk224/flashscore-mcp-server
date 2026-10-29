"""Playwright fetch. The sport parsers never open a browser."""
from __future__ import annotations

from typing import Optional

from ..browser import browser_manager, click_show_more, safe_goto


async def fetch_html(
    url: str,
    show_more: int = 0,
    until_count: Optional[int] = None,
) -> str:
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)
        if show_more or until_count is not None:
            await click_show_more(page, max_clicks=show_more or 40, until_count=until_count)
        return await page.content()
