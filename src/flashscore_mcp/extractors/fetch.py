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
        raise LoadFailed(f"Failed to load {url}: {exc}", reason="source-refused") from exc


# ---------------------------------------------------------------------------
# Sport day pages
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402
import re  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402

_DAY_FEED = re.compile(r"/x/feed/f_\d+_(-?\d+)_")
_DAY_LABEL = '[data-testid="wcl-dayPickerButton"]'
_ROWS_OR_EMPTY = ".event__match, .nmf__title, [class*='noMatches'], .leagues--static"


@dataclass
class DayPage:
    html: str = ""
    feed: str = ""
    label: Optional[str] = None
    offset: int = 0
    feeds: dict = field(default_factory=dict)


async def _day_label(page) -> Optional[str]:
    try:
        return await page.get_attribute(_DAY_LABEL, "aria-label", timeout=2000)
    except Exception:
        return None


async def fetch_day(url: str, offset: int = 0, live_tab: bool = False) -> DayPage:
    """Open a sport page, step the day picker to offset, and keep that day's feed.

    The ?d= query the old code used is ignored by Flashscore, so yesterday's
    request silently returned today's games. The day picker arrows are the
    supported control; each step loads f_<sport>_<offset>_... which this
    captures from the page's own network traffic.
    """
    result = DayPage(offset=offset)
    pending: list[asyncio.Future] = []

    async def grab(response) -> None:
        found = _DAY_FEED.search(response.url)
        if not found:
            return
        try:
            result.feeds[int(found.group(1))] = await response.text()
        except Exception as exc:  # pragma: no cover - network edge
            logger.debug("day feed body unavailable: {}", exc)

    try:
        async with browser_manager.new_page() as page:
            page.on("response", lambda r: pending.append(asyncio.ensure_future(grab(r))))
            await safe_goto(page, url)
            try:
                await page.wait_for_selector(_ROWS_OR_EMPTY, timeout=15000, state="attached")
            except Exception:
                logger.debug("Day rows not ready: {}", url)
            if offset:
                arrow = f'[data-day-picker-arrow="{"prev" if offset < 0 else "next"}"]'
                for _ in range(abs(offset)):
                    before = await _day_label(page)
                    await page.click(arrow, timeout=5000)
                    try:
                        await page.wait_for_function(
                            """([sel, before]) => {
                              const el = document.querySelector(sel);
                              return el && el.getAttribute('aria-label') !== before;
                            }""",
                            arg=[_DAY_LABEL, before],
                            timeout=10000,
                        )
                    except Exception:
                        logger.warning("Day picker did not move from {}", before)
                        break
            # Wait for the target day's feed and its rows to land.
            for _ in range(40):
                if offset in result.feeds:
                    break
                await page.wait_for_timeout(250)
            if live_tab:
                tab = page.locator(".filters__tab", has_text="LIVE").first
                try:
                    if await tab.count():
                        await tab.click(timeout=3000)
                        await page.wait_for_timeout(600)
                except Exception:
                    logger.debug("LIVE tab click failed")
            try:
                await page.wait_for_selector(_ROWS_OR_EMPTY, timeout=8000, state="attached")
            except Exception:
                pass
            await page.wait_for_timeout(400)
            result.label = await _day_label(page)
            result.html = await page.content()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            result.feed = result.feeds.get(offset, "")
            logger.info(
                "fetch_day url={} offset={} label={} feed_bytes={}",
                url, offset, result.label, len(result.feed),
            )
            return result
    except LoadFailed:
        raise
    except Exception as exc:
        raise LoadFailed(f"Failed to load {url}: {exc}", reason="source-refused") from exc
