"""Browser manager — fast path, no human-delay sleeps."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, List, Optional
from urllib.parse import urlparse

from loguru import logger
from playwright.async_api import async_playwright, Browser, Page, Locator
from tenacity import retry, stop_after_attempt, wait_fixed

from .config import settings


# Heavy third-party and binary assets the parsers never read. Blocking them
# cuts page boot time sharply on small (Apify/VM) CPUs. Stylesheets stay so
# visibility checks such as "Show more" keep working.
_BLOCK_TYPES = {"image", "media", "font"}
_BLOCK_HOSTS = (
    "googletagmanager.com",
    "google-analytics.com",
    "googlesyndication.com",
    "doubleclick.net",
    "googleadservices.com",
    "adservice.google",
    "bannerflow.net",
    "bannerflow.com",
    "lsaudio.eu",
    "content.livesportmedia.eu",
    "scorecardresearch.com",
    "facebook.net",
    "hotjar.com",
    "criteo",
    "adnxs.com",
    "amazon-adsystem.com",
    "taboola.com",
    "outbrain.com",
)


async def _route_filter(route) -> None:
    request = route.request
    try:
        if request.resource_type in _BLOCK_TYPES:
            await route.abort()
            return
        host = urlparse(request.url).hostname or ""
        if any(blocked in host for blocked in _BLOCK_HOSTS):
            await route.abort()
            return
        await route.continue_()
    except Exception:
        # The page may already be closing; never let routing break a scrape.
        pass


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
            if settings.block_assets:
                await context.route("**/*", _route_filter)
            page = await context.new_page()
            try:
                yield page
            finally:
                await context.close()


browser_manager = BrowserManager()


# Tab content is hydrated after domcontentloaded. A header link such as News
# is already in the shell, so the wait has to be tab-specific or standings and
# results are read before the real rows exist.
# (url fragment, selector, timeout ms or None to use nav_timeout_ms).
# Odds cells are absent when the season is not current, so that wait is short.
_TAB_READY = (
    # Cups render a bracket instead of a table; without the draw selector a
    # knockout competition waited the whole navigation timeout.
    ("/standings", ".ui-table__row, .draw__bracket, [class*='draw__']", None),
    ("/form/", ".ui-table__row", None),
    ("/results", ".event__match, [id^='g_']", None),
    ("/fixtures", ".event__match, [id^='g_']", None),
    ("/news/", '[data-testid="wcl-newsArticlePreview"]', None),
    ("/odds", '[data-testid="wcl-oddsCell"]', 8000),
)


def _content_ready(url: str) -> tuple[str, int] | None:
    lowered = url.lower()
    for needle, selector, timeout in _TAB_READY:
        if needle in lowered:
            return selector, timeout or settings.nav_timeout_ms
    return None


@retry(stop=stop_after_attempt(2), wait=wait_fixed(0.4))
async def safe_goto(page: Page, url: str, **kwargs) -> None:
    await page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=settings.nav_timeout_ms,
        **kwargs,
    )
    landed = page.url or url
    if "/archive" in landed.lower():
        try:
            await page.wait_for_function(
                "() => document.documentElement.innerHTML.includes('league_archive_data')",
                timeout=settings.nav_timeout_ms,
            )
        except Exception:
            logger.debug("Archive payload not ready: {}", landed)
        return
    ready = _content_ready(landed)
    if not ready:
        # League summary URLs are /sport/country/league/ and the tab list
        # is filled in after domcontentloaded.
        parts = [part for part in urlparse(landed).path.strip("/").split("/") if part]
        if len(parts) == 3:
            try:
                await page.wait_for_selector('[role="tab"]', timeout=8000)
            except Exception:
                logger.debug("League tabs not ready: {}", landed)
        return
    selector, timeout = ready
    try:
        await page.wait_for_selector(selector, timeout=timeout)
    except Exception:
        logger.debug("Content not ready for {} ({})", landed, selector)


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


async def _visible_show_more(page: Page) -> Optional[Locator]:
    """The results shell also contains hidden 'Show more matches' links.

    Those links sit in display:none summary blocks. Clicking the first match
    in DOM order never loads older rounds, so only a visible control counts.
    """
    for sel in (
        "a.event__more:visible",
        "a:visible:has-text('Show more matches')",
        "button:visible:has-text('Show more matches')",
        "button:visible:has-text('Show more')",
    ):
        loc = page.locator(sel).first
        try:
            if await loc.count() > 0 and await loc.is_visible():
                logger.debug("Show more selector: {}", sel)
                return loc
        except Exception:
            continue
    return None


async def click_show_more(
    page: Page,
    until_count: Optional[int] = None,
) -> int:
    """Click Show more until the caller has enough rows, or the button is gone.

    until_count is the caller's own stop. There is no click ceiling.
    A control that stays visible but adds no rows is a dead page, not a cap.
    """
    clicks = 0
    stale = 0
    while True:
        if until_count is not None and await _match_count(page) >= until_count:
            logger.info("Show more stopped: {} matches reached", until_count)
            break
        # Scroll to bottom to reveal any lazy "Show more" controls
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(300)
        except Exception:
            pass
        more = await _visible_show_more(page)
        if not more:
            break
        before = await _match_count(page)
        try:
            try:
                await more.click(timeout=2000)
            except Exception:
                await more.click(timeout=2000, force=True)
            clicks += 1
            try:
                await page.wait_for_function(
                    """(before) => document.querySelectorAll(".event__match, [id^='g_']").length > before""",
                    arg=before,
                    timeout=8000,
                )
            except Exception:
                pass
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
