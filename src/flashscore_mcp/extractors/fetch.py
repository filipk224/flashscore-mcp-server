"""Playwright fetch. The sport parsers never open a browser."""
from __future__ import annotations

from typing import Optional

from loguru import logger

from ..browser import browser_manager, click_show_more, safe_goto
from .page_status import LoadFailed


async def fetch_html(
    url: str,
    show_more: Optional[int] = 0,
    until_count: Optional[int] = None,
    full: bool = False,
) -> str:
    """Expand match lists to until_count, or until Show more is gone.

    show_more is only a switch. A number is not a click ceiling.
    Standings and other non-match pages leave it at 0 and do not expand.
    """
    expand = full or show_more is None or until_count is not None or (show_more or 0) > 0
    try:
        async with browser_manager.new_page() as page:
            await safe_goto(page, url)
            if expand:
                await click_show_more(page, until_count=until_count)
                # The control can appear after the list container is scrolled.
                try:
                    await page.evaluate('''() => {
                        const c = document.querySelector('.leagues--static, .event--leagues, [class*="event--leagues"]');
                        if (c) c.scrollTop = c.scrollHeight;
                        window.scrollTo(0, document.body.scrollHeight);
                    }''')
                    await page.wait_for_timeout(800)
                    await click_show_more(page, until_count=until_count)
                except Exception as e:
                    logger.debug("Adaptive scroll attempt failed: {}", e)
            return await page.content()
    except LoadFailed:
        raise
    except Exception as exc:
        raise LoadFailed(f"Failed to load {url}: {exc}") from exc
