from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator
from loguru import logger
from playwright.async_api import async_playwright, Browser, Page
from tenacity import retry, stop_after_attempt, wait_exponential
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
            self._browser = await self._playwright.chromium.launch(headless=settings.headless, args=settings.browser_args)
            logger.info("Browser started")

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    @asynccontextmanager
    async def new_page(self) -> AsyncIterator[Page]:
        await self.start()
        async with self._semaphore:
            context = await self._browser.new_context(user_agent=settings.user_agent, viewport={"width": 1280, "height": 800})
            page = await context.new_page()
            try:
                yield page
            finally:
                await context.close()

browser_manager = BrowserManager()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
async def safe_goto(page: Page, url: str, **kwargs) -> None:
    await page.goto(url, wait_until="domcontentloaded", timeout=settings.nav_timeout_ms, **kwargs)
    await asyncio.sleep(settings.min_delay_s)
