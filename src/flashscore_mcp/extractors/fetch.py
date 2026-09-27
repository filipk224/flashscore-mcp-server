"""Playwright fetch. The sport parsers never open a browser."""
from __future__ import annotations

from ..browser import browser_manager, click_show_more, safe_goto


async def fetch_html(url: str, show_more: int = 0) -> str:
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)
        if show_more:
            await click_show_more(page, max_clicks=show_more)
        return await page.content()
