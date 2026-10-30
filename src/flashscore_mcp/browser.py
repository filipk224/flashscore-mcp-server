"""Browser manager — fast path, no human-delay sleeps."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, List, Optional

from loguru import logger
from playwright.async_api import async_playwright, Browser, Page, Locator
from tenacity import retry, stop_after_attempt, wait_fixed

from .config import settings


class BrowserManager:
    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_pages)

    async def start(self) -> None:
        if self._browser is not None:
            return
        async with self._lock:
            if self._browser is not None:
                return
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=settings.headless,
                args=settings.browser_args,
            )
            logger.info(
                "Browser started (headless={}, concurrent={})",
                settings.headless,
                settings.max_concurrent_pages,
            )

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Browser stopped")

    @asynccontextmanager
    async def new_page(self) -> AsyncIterator[Page]:
        await self.start()
        async with self._semaphore:
            context = await self._browser.new_context(
                user_agent=settings.user_agent,
                viewport={"width": 1280, "height": 800},
                locale="en-US",
                java_script_enabled=True,
            )
            page = await context.new_page()
            try:
                yield page
            finally:
                await context.close()


browser_manager = BrowserManager()


@retry(stop=stop_after_attempt(2), wait=wait_fixed(0.4))
async def safe_goto(page: Page, url: str, **kwargs) -> None:
    await page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=settings.nav_timeout_ms,
        **kwargs,
    )
    # Longer, more specific wait for data-bearing elements, especially standings
    selector = ".event__match, .ui-table, [id^='g_'], a[href*='/news/'], [class*='archive']"
    if "standings" in url or "form" in url:
        selector = ".ui-table, .ui-table__row"
    try:
        await page.wait_for_selector(selector, timeout=8000)
    except Exception:
        logger.debug("wait_for_selector timed out for {}", url)
        # Extra short pause for JS hydration
        await page.wait_for_timeout(1500)


async def find_first_locator(page: Page, selector_list: List[str], timeout: int = 1500) -> Optional[Locator]:
    for sel in selector_list:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                await loc.wait_for(state="attached", timeout=timeout)
                logger.debug("Used selector: {}", sel)
                return loc
        except Exception:
            continue
    return None


async def get_all_matching(page: Page, selector_list: List[str]) -> List[Locator]:
    for sel in selector_list:
        try:
            locs = page.locator(sel)
            count = await locs.count()
            if count > 0:
                logger.debug("Matched {} elements with {}", count, sel)
                return [locs.nth(i) for i in range(count)]
        except Exception:
            continue
    return []


async def _match_count(page: Page) -> int:
    try:
        return await page.locator(".event__match, [class*='event__match'], [id^='g_']").count()
    except Exception:
        return 0


async def click_show_more(
    page: Page,
    max_clicks: Optional[int] = None,
    until_count: Optional[int] = None,
) -> int:
    """Click Show more until the button is gone.

    until_count: stop early once that many matches are loaded (limited fetches only).
    max_clicks: hard safety only. None means keep going until the button disappears.
    Full season data is never cut short by a click cap.
    """
    clicks = 0
    stale = 0
    while True:
        if until_count is not None and await _match_count(page) >= until_count:
            logger.info("Show more stopped: {} matches reached", until_count)
            break
        if max_clicks is not None and clicks >= max_clicks:
            logger.warning("Show more safety cap {} reached", max_clicks)
            break
        # Scroll to bottom to reveal any lazy "Show more" controls
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(300)
        except Exception:
            pass
        more = await find_first_locator(page, settings.selectors["show_more"], timeout=600)
        if not more:
            break
        before = await _match_count(page)
        try:
            # Prefer a real click; fall back to force if the element is off-screen
            try:
                await more.click(timeout=800)
            except Exception:
                await more.click(timeout=800, force=True)
            clicks += 1
            await page.wait_for_timeout(400)
        except Exception:
            break
        if await _match_count(page) <= before:
            stale += 1
            if stale >= 2:
                break
        else:
            stale = 0
    logger.info("Show more clicks={}", clicks)
    return clicks
