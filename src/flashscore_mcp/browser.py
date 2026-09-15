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
    try:
        await page.wait_for_selector(
            ".event__match, .ui-table, [id^='g_'], a[href*='/news/'], [class*='archive']",
            timeout=4000,
        )
    except Exception:
        pass


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
    logger.warning("No matching selector found from list: {}", selector_list[:3])
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


async def click_show_more(page: Page, max_clicks: int = 12) -> int:
    clicks = 0
    for _ in range(max_clicks):
        more = await find_first_locator(page, settings.selectors["show_more"], timeout=800)
        if not more:
            break
        try:
            await more.click(timeout=800)
            clicks += 1
            await page.wait_for_timeout(200)
        except Exception:
            break
    return clicks
