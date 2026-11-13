"""Section time budget (timeout vs no-data) and the browser queue-wait cap."""
from __future__ import annotations

import asyncio
import time
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

from flashscore_mcp import browser as browser_mod
from flashscore_mcp.config import settings
from flashscore_mcp.errors import SECTION_TIMEOUT, BusyError, LoadFailed
from flashscore_mcp.extractors import match as match_ext
from flashscore_mcp.extractors import match_page as mp
from flashscore_mcp.extractors.match_page import MatchPage, load_match_page

MATCH_URL = "https://www.flashscore.com/match/football/a-AAAA1111/b-BBBB2222/?mid=Me9aWSp3"
PAGE_HTML = "<html>flashscore " + "x" * 2000 + "</html>"


class FakeLocator:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector

    @property
    def first(self):
        return self

    async def count(self):
        if any(key in self.selector for key in self.page.links):
            return 1  # a nav link
        # Tab rows exist only once their tab was clicked and is set to render.
        rendered = self.page.clicked and any(tab in self.selector for tab in self.page.ready_tabs)
        return 5 if rendered else 0

    async def click(self, timeout=None):
        self.page.clicked.append(self.selector)


class FakePage:
    """Stands in for a Playwright page; ready_tabs decides which tabs render."""

    def __init__(self, links, ready_tabs, empty_message=False, url=MATCH_URL):
        self.links = links  # tab selectors the nav offers, e.g. "/summary/stats"
        self.ready_tabs = ready_tabs
        self.empty_message = empty_message
        self.url = url
        self.clicked: list[str] = []
        self.waited: list[tuple[str, int]] = []

    async def goto(self, url, **kwargs):
        return None

    async def wait_for_function(self, *args, **kwargs):
        return None

    def locator(self, selector):
        return FakeLocator(self, selector)

    async def wait_for_selector(self, selector, timeout=0, state="attached"):
        self.waited.append((selector, timeout))
        if any(tab in selector for tab in self.ready_tabs) or "smv" in selector:
            return None
        raise TimeoutError(selector)

    async def wait_for_timeout(self, ms):
        return None

    async def evaluate(self, script, arg=None):
        return self.empty_message

    async def content(self):
        return PAGE_HTML


def _patch_page(page):
    @asynccontextmanager
    async def new_page(queue_wait_s=None):
        yield page

    return patch.object(mp.browser_manager, "new_page", new_page)


# Selectors used by the tab readiness checks in match_page._TABS.
STATS_READY = "wcl-statistics"
LINEUPS_READY = "wcl-lineupsGroup"
H2H_READY = "h2h__section"
ALL_LINKS = ("/summary/stats", "/summary/lineups", "/h2h/")


class SectionTimeouts(unittest.TestCase):
    def setUp(self):
        # Shrink the per-section slices so "never renders" cases run fast.
        for name, value in (("_MAX_SLICE_MS", 600), ("_MIN_SLICE_MS", 300), ("_CHANGE_GRACE_S", 0.0)):
            patcher = patch.object(mp, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _load(self, page, sections=("summary", "stats", "lineups", "h2h"), **kw):
        with _patch_page(page):
            return asyncio.run(load_match_page(MATCH_URL, list(sections), **kw))

    def test_all_sections_render(self):
        page = FakePage(ALL_LINKS, ready_tabs=(STATS_READY, LINEUPS_READY, H2H_READY))
        result = self._load(page)
        self.assertEqual(result.errors, {})
        self.assertEqual(set(result.html), {"summary", "stats", "lineups", "h2h"})

    def test_tab_that_never_renders_is_a_timeout_not_empty(self):
        page = FakePage(ALL_LINKS, ready_tabs=(STATS_READY, H2H_READY))
        result = self._load(page)
        self.assertEqual(result.errors, {"lineups": SECTION_TIMEOUT})
        self.assertNotIn("lineups", result.html)
        self.assertNotIn("lineups", result.missing)
        self.assertTrue(SECTION_TIMEOUT.startswith("timeout"))

    def test_tab_the_site_does_not_offer_is_genuinely_empty(self):
        page = FakePage(("/h2h/",), ready_tabs=(H2H_READY,))
        result = self._load(page)
        self.assertEqual(result.errors, {})
        self.assertEqual(result.missing, {"stats", "lineups"})

    def test_explicit_empty_message_is_no_data_not_timeout(self):
        page = FakePage(("/summary/stats",), ready_tabs=(), empty_message=True)
        result = self._load(page, sections=("stats",))
        self.assertEqual(result.errors, {})
        self.assertEqual(result.missing, {"stats"})

    def test_exhausted_budget_marks_unreached_sections_as_timeouts(self):
        page = FakePage(ALL_LINKS, ready_tabs=(STATS_READY, LINEUPS_READY, H2H_READY))
        result = self._load(page, budget_s=0.5)
        self.assertEqual(
            result.errors,
            {"stats": SECTION_TIMEOUT, "lineups": SECTION_TIMEOUT, "h2h": SECTION_TIMEOUT},
        )
        self.assertIn("summary", result.html)

    def test_budget_comes_from_settings_env(self):
        page = FakePage(ALL_LINKS, ready_tabs=(STATS_READY, LINEUPS_READY, H2H_READY))
        with patch.object(settings, "match_budget_s", 0.5):
            result = self._load(page)
        self.assertEqual(set(result.errors), {"stats", "lineups", "h2h"})



class SliceMath(unittest.TestCase):
    def test_slices_are_shared_so_one_slow_tab_cannot_starve_the_rest(self):
        # 30 s left and three tabs: the first may use at most 10 s.
        self.assertEqual(mp._slice_ms(30000, 3), 10000)
        self.assertEqual(mp._slice_ms(60000, 1), mp._MAX_SLICE_MS)
        self.assertEqual(mp._slice_ms(2500, 3), 2500)  # never more than remains
        self.assertEqual(mp._slice_ms(9000, 3), mp._MIN_SLICE_MS)


class TabReadiness(unittest.TestCase):
    """The summary page already holds a few matching rows; they are not the tab."""

    def test_pre_click_markup_alone_is_not_ready(self):
        class Page(FakePage):
            async def evaluate(self, script, arg=None):
                return False  # no placeholders

        class Loc(FakeLocator):
            async def count(self):
                return 5  # preview rows, never replaced

        page = Page((), ())
        page.locator = lambda selector: Loc(page, selector)
        with patch.object(mp, "_CHANGE_GRACE_S", 5.0):
            ready = asyncio.run(mp._wait_tab_ready(page, "", "x", 1000, "statistics", baseline=5))
        self.assertFalse(ready)  # nothing changed within the wait

    def test_ready_after_placeholders_clear_and_rows_grow(self):
        states = iter([(False, 5), (True, 0), (True, 0), (False, 45), (False, 45), (False, 45)])
        current = {"loading": False, "count": 5}

        class Page(FakePage):
            async def evaluate(self, script, arg=None):
                current["loading"], current["count"] = next(states, (False, 45))
                return current["loading"]

        class Loc(FakeLocator):
            async def count(self):
                return current["count"]

        page = Page((), ())
        page.locator = lambda selector: Loc(page, selector)
        self.assertTrue(asyncio.run(mp._wait_tab_ready(page, "", "x", 10000, "statistics", baseline=5)))
        self.assertEqual(current["count"], 45)

    def test_unchanged_content_counts_as_ready_after_the_grace(self):
        class Page(FakePage):
            async def evaluate(self, script, arg=None):
                return False

        class Loc(FakeLocator):
            async def count(self):
                return 5

        page = Page((), ())
        page.locator = lambda selector: Loc(page, selector)
        with patch.object(mp, "_CHANGE_GRACE_S", 0.3):
            self.assertTrue(asyncio.run(mp._wait_tab_ready(page, "", "x", 5000, "statistics", baseline=5)))


def _detail_page(html=None, errors=None, missing=None):
    page = MatchPage()
    page.url = MATCH_URL
    page.html = html or {}
    page.errors = errors or {}
    page.missing = set(missing or ())
    return page


class GetMatchReportsTimeouts(unittest.TestCase):
    def _run(self, page, sections):
        async def fake_load(*args, **kwargs):
            return page

        with patch("flashscore_mcp.extractors.match.load_match_page", side_effect=fake_load):
            return asyncio.run(match_ext.get_match("Me9aWSp3", sections=sections))

    def test_timed_out_sections_are_errors_and_stay_unset(self):
        summary = (
            '<html>flashscore <div class="duelParticipant__home"><a class="participant__participantName">A</a></div>'
            '<div class="duelParticipant__away"><a class="participant__participantName">B</a></div>' + "x" * 2000 + "</html>"
        )
        page = _detail_page(
            html={"summary": summary},
            errors={"stats": SECTION_TIMEOUT, "lineups": SECTION_TIMEOUT},
        )
        with patch.object(match_ext, "parse_summary", return_value={"home_team": "A", "away_team": "B"}):
            detail = self._run(page, ["summary", "stats", "lineups"])
        self.assertEqual(detail.errors["stats"], SECTION_TIMEOUT)
        self.assertEqual(detail.errors["lineups"], SECTION_TIMEOUT)
        self.assertIsNone(detail.stats)
        self.assertIsNone(detail.lineups)
        self.assertEqual(detail.status, "partial")
        self.assertEqual(detail.reason, "section-failed")

    def test_genuinely_missing_tab_is_empty_without_error(self):
        page = _detail_page(html={}, missing={"stats"})
        with patch.object(match_ext, "parse_summary", return_value={"home_team": "A", "away_team": "B"}):
            page.html = {"h2h": PAGE_HTML}
            detail = self._run(page, ["stats"])
        self.assertEqual(detail.stats, [])
        self.assertNotIn("stats", detail.errors)

    def test_nothing_loaded_before_the_budget_raises_a_timeout(self):
        page = _detail_page(errors={"summary": SECTION_TIMEOUT, "stats": SECTION_TIMEOUT})
        with self.assertRaises(LoadFailed) as ctx:
            self._run(page, ["summary", "stats"])
        self.assertTrue(ctx.exception.reason.startswith("timeout"))


class FakeBrowser:
    def __init__(self):
        self.contexts = 0

    async def new_context(self, **kwargs):
        self.contexts += 1
        return FakeContext()


class FakeContext:
    closed = False

    async def route(self, *args, **kwargs):
        return None

    async def new_page(self):
        return object()

    async def close(self):
        FakeContext.closed = True


def _manager(slots: int) -> browser_mod.BrowserManager:
    with patch.object(settings, "max_concurrent_pages", slots):
        manager = browser_mod.BrowserManager()
    manager._browser = FakeBrowser()
    return manager


class QueueWaitCap(unittest.TestCase):
    def test_full_pool_returns_busy_after_the_cap(self):
        async def scenario():
            manager = _manager(1)
            async with manager.new_page():
                started = time.monotonic()
                with self.assertRaises(BusyError) as ctx:
                    async with manager.new_page(queue_wait_s=0.2):
                        self.fail("should not get a slot")
                return time.monotonic() - started, ctx.exception

        waited, exc = asyncio.run(scenario())
        self.assertGreaterEqual(waited, 0.15)
        self.assertLess(waited, 2.0)
        self.assertEqual(exc.reason, "busy")
        self.assertIn("busy, retry", str(exc))
        self.assertIsInstance(exc, LoadFailed)

    def test_default_cap_comes_from_settings(self):
        async def scenario():
            manager = _manager(1)
            async with manager.new_page():
                with patch.object(settings, "queue_wait_s", 0.1):
                    with self.assertRaises(BusyError):
                        async with manager.new_page():
                            pass

        asyncio.run(scenario())

    def test_waiting_call_gets_the_slot_when_one_frees_in_time(self):
        async def scenario():
            manager = _manager(1)
            order = []

            async def holder():
                async with manager.new_page():
                    order.append("holder")
                    await asyncio.sleep(0.2)

            async def waiter():
                await asyncio.sleep(0.05)
                async with manager.new_page(queue_wait_s=2.0):
                    order.append("waiter")

            await asyncio.gather(holder(), waiter())
            return order

        self.assertEqual(asyncio.run(scenario()), ["holder", "waiter"])

    def test_slot_is_released_after_busy_and_after_errors(self):
        async def scenario():
            manager = _manager(1)
            async with manager.new_page():
                with self.assertRaises(BusyError):
                    async with manager.new_page(queue_wait_s=0.05):
                        pass
            with self.assertRaises(RuntimeError):
                async with manager.new_page(queue_wait_s=0.5):
                    raise RuntimeError("scrape blew up")
            async with manager.new_page(queue_wait_s=0.5):
                return True

        self.assertTrue(asyncio.run(scenario()))

    def test_busy_is_not_swallowed_by_the_h2h_meeting_search(self):
        async def busy(*args, **kwargs):
            raise BusyError("busy, retry: test")

        with patch.object(match_ext, "fetch_html", side_effect=busy):
            with self.assertRaises(BusyError):
                asyncio.run(match_ext._find_meeting(_ref("a"), _ref("b")))


def _ref(name):
    from flashscore_mcp.extractors.team import TeamRef

    return TeamRef(slug=name, id="id", name=name)


if __name__ == "__main__":
    unittest.main()
