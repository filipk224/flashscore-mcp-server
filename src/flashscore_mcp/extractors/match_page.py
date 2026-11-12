"""Load one rendered match page and switch tabs inside the same page.

Match pages are a client-rendered app: the header shows "Loading..." and the
sections are empty right after domcontentloaded. Opening a fresh browser
context per section (the old approach) paid the full page boot three or four
times and still read the placeholder markup. Here the page boots once, waits
for real participant names, and then clicks each tab (falling back to a
direct navigation), waiting for that tab's own content.
"""
from __future__ import annotations

import time
from typing import Iterable, Optional

from loguru import logger

from ..browser import browser_manager
from ..config import settings
from ..errors import SECTION_TIMEOUT, BusyError
from .match_ref import section_url
from .page_status import LoadFailed

# The whole get_match budget (queue wait included) comes from
# settings.match_budget_s / FLASHSCORE_MATCH_BUDGET_S, kept well under the
# ~60 s client gateway timeout.

# Shortest wait one section gets, and the longest a single section may take
# before the sections behind it get their share.
_MIN_SLICE_MS = 4000
_MAX_SLICE_MS = 12000

# True while the tab still shows loading placeholders (class names such as
# wcl-statisticsSkeleton). `key` is a lowercase word from the tab's own
# skeleton class, so unrelated shimmers elsewhere on the page do not block.
_TAB_LOADING_JS = """(key) => [...document.querySelectorAll('[class*="Skeleton"], [class*="skeleton"]')]
  .some((el) => String(el.className).toLowerCase().includes(key))"""
_SKELETON_KEY = {"stats": "statistics", "lineups": "lineup", "h2h": "h2h"}

# Text the site shows in place of a tab's rows. A tab that is offered but
# renders neither rows nor one of these is a timeout, not "no data".
_TAB_EMPTY_JS = """() => {
  const t = (document.body && document.body.innerText || '').toLowerCase();
  return ['not available', 'no data', 'no statistics', 'no lineups', 'no information', 'not yet available']
    .some((hint) => t.includes(hint));
}"""

_NAMES_READY_JS = """() => {
  const pick = (sel) => {
    const el = document.querySelector(sel);
    return el ? (el.textContent || '').trim() : '';
  };
  const home = pick('.duelParticipant__home .participant__participantName');
  const away = pick('.duelParticipant__away .participant__participantName');
  const ok = (t) => t && !/^loading/i.test(t);
  if (ok(home) && ok(away)) return true;
  // A removed or unknown match renders an error page instead of the duel.
  const body = (document.body && document.body.innerText || '').toLowerCase();
  return body.includes('page not found') || body.includes('error 404');
}"""

# tab -> (link selector in the match nav, ready selector, URL path fragment
# that shows the tab is the active one)
_TABS = {
    "stats": (
        "a[href*='/summary/stats']",
        "[data-testid='wcl-statistics'], .stat__row",
        "/summary/stats",
    ),
    "lineups": (
        "a[href*='/summary/lineups']",
        "[data-testid='wcl-lineupsGroup'], [data-testid^='wcl-lineupsParticipantGeneral'], .lf__lineUp",
        "/summary/lineups",
    ),
    "h2h": (
        "a[href*='/h2h/']",
        ".h2h__section, .h2h__row",
        "/h2h/",
    ),
}

_SUMMARY_READY = ".smv__verticalSections, .smv__participantRow, [data-testid='wcl-summaryPreview'], .section--preview"


class MatchPage:
    """Result of one match-page session."""

    def __init__(self) -> None:
        self.url: Optional[str] = None
        self.html: dict[str, str] = {}
        self.missing: set[str] = set()  # tab not offered for this match
        self.errors: dict[str, str] = {}


async def _wait(page, selector: str, timeout_ms: int) -> bool:
    try:
        await page.wait_for_selector(selector, timeout=max(500, timeout_ms), state="attached")
        return True
    except Exception:
        return False


# How long to wait for the tab to visibly start swapping its content before
# trusting markup that was already on the page when the tab was clicked.
_CHANGE_GRACE_S = 3.0


async def _wait_tab_ready(
    page,
    path_fragment: str,
    selector: str,
    timeout_ms: int,
    skeleton_key: str = "",
    baseline: int = 0,
) -> bool:
    """Wait until the clicked tab has really rendered its rows.

    Traps this avoids, both seen on a slow host: the summary page already holds
    markup that matches the tab's selector (the "Top stats" preview has 5 stats
    rows), so reading at the first match returned the preview or nothing; and
    a tab shows loading placeholders before it fills its rows in. Ready means:
    the URL is the tab's, the page changed from the pre-click ``baseline`` (or a
    short grace passed), no placeholders are left, and the row count is stable.
    """
    start = time.monotonic()
    end = start + timeout_ms / 1000
    if path_fragment and "?mid=" in (page.url or ""):
        try:
            await page.wait_for_function(
                "(frag) => location.pathname.includes(frag)",
                arg=path_fragment,
                timeout=max(500, timeout_ms),
            )
        except Exception:
            return False
    changed = False
    last = -1
    while time.monotonic() < end:
        try:
            loading = bool(skeleton_key) and bool(await page.evaluate(_TAB_LOADING_JS, skeleton_key))
            count = await page.locator(selector).count()
        except Exception:
            return False
        if loading or count != baseline:
            changed = True
        if not changed and time.monotonic() - start >= _CHANGE_GRACE_S:
            changed = True  # same content as before the click is the content
        if changed and not loading and count > 0 and count == last:
            return True
        last = count
        await page.wait_for_timeout(250)
    return False


async def _expand_h2h(page, clicks: int, deadline: float) -> None:
    for _ in range(max(0, clicks)):
        if time.monotonic() > deadline:
            return
        section = page.locator(".h2h__section", has_text="Head-to-head matches")
        button = section.locator("button.wclButtonLink--h2h, button:has-text('Show more matches')").first
        try:
            if not await button.count() or not await button.is_visible():
                return
            before = await section.locator(".h2h__row").count()
            await button.click(timeout=2000)
            await page.wait_for_function(
                """(before) => {
                  const s = [...document.querySelectorAll('.h2h__section')]
                    .find(x => (x.textContent || '').includes('Head-to-head matches'));
                  return s && s.querySelectorAll('.h2h__row').length > before;
                }""",
                arg=before,
                timeout=4000,
            )
        except Exception:
            return


def _slice_ms(remaining_ms: int, sections_left: int) -> int:
    """Time one section may use: an even share of what is left, bounded."""
    share = remaining_ms // max(1, sections_left)
    return max(min(share, _MAX_SLICE_MS), min(_MIN_SLICE_MS, remaining_ms))


async def _tab_has_empty_message(page) -> bool:
    try:
        return bool(await page.evaluate(_TAB_EMPTY_JS))
    except Exception:
        return False


async def load_match_page(
    match_url: str,
    sections: Iterable[str],
    h2h_more: int = 0,
    budget_s: Optional[float] = None,
) -> MatchPage:
    """Load a match page and the requested tabs inside one time budget.

    The budget covers the queue wait too. A requested section that is not
    loaded when time runs out lands in ``errors`` with a ``timeout`` reason;
    only a tab the site does not offer (or shows an explicit empty message
    for) goes to ``missing`` and is treated as genuinely empty.
    """
    wanted = list(dict.fromkeys(sections))
    result = MatchPage()
    budget = settings.match_budget_s if budget_s is None else budget_s
    t_start = time.monotonic()
    deadline = t_start + budget
    tabs = [name for name in wanted if name != "summary" and name in _TABS]

    def mark_timeouts(names: Iterable[str]) -> None:
        for name in names:
            if name not in result.html and name not in result.missing:
                result.errors.setdefault(name, SECTION_TIMEOUT)

    try:
        async with browser_manager.new_page(queue_wait_s=min(settings.queue_wait_s, budget)) as page:
            started = time.monotonic()
            goto_ms = int(min(settings.nav_timeout_ms, max(1000, (deadline - started) * 1000)))
            await page.goto(match_url, wait_until="domcontentloaded", timeout=goto_ms)
            hydrate_ms = int(min(15000, max(500, (deadline - time.monotonic()) * 1000)))
            hydrated = True
            try:
                await page.wait_for_function(_NAMES_READY_JS, timeout=hydrate_ms)
            except Exception:
                hydrated = False
                logger.warning("Match header did not hydrate: {}", page.url)
            result.url = page.url
            if "summary" in wanted:
                if hydrated:
                    # Scheduled matches never render a timeline block, so a
                    # miss here is not treated as an error.
                    await _wait(page, _SUMMARY_READY, 3000)
                    result.html["summary"] = await page.content()
                else:
                    result.errors["summary"] = SECTION_TIMEOUT
            logger.info("match page ready in {:.1f}s url={}", time.monotonic() - started, page.url)
            if not hydrated:
                # Nothing below can be read from a page that is still booting.
                mark_timeouts(tabs)
                return result

            nav_broken = False  # a failed navigation leaves the page unreadable
            for index, name in enumerate(tabs):
                remaining_ms = int((deadline - time.monotonic()) * 1000)
                if remaining_ms <= 1000:
                    mark_timeouts(tabs[index:])
                    break
                slice_ms = _slice_ms(remaining_ms, len(tabs) - index)
                tab_deadline = time.monotonic() + slice_ms / 1000
                link_sel, ready_sel, path_fragment = _TABS[name]
                link = page.locator(link_sel).first
                t0 = time.monotonic()
                try:
                    has_link = await link.count() > 0
                except Exception:
                    has_link = False
                if not has_link:
                    if nav_broken:
                        result.errors[name] = SECTION_TIMEOUT
                    elif "?mid=" not in (page.url or ""):
                        result.errors[name] = "source-refused"
                    else:
                        result.missing.add(name)  # the site offers no such tab
                    continue
                try:
                    baseline = await page.locator(ready_sel).count()
                except Exception:
                    baseline = 0
                try:
                    await link.click(timeout=int(max(3000, min(8000, slice_ms))))
                except Exception:
                    nav_broken = True
                    try:
                        await page.goto(
                            section_url(page.url, name),
                            wait_until="domcontentloaded",
                            timeout=int(max(1000, min(settings.nav_timeout_ms, slice_ms))),
                        )
                    except Exception as exc:
                        # Out of time is a timeout; anything else is a refusal.
                        timed_out = "timeout" in f"{type(exc).__name__} {exc}".lower()
                        result.errors[name] = SECTION_TIMEOUT if timed_out else "source-refused"
                        logger.warning("match tab {} navigation failed: {}", name, exc)
                        continue
                    nav_broken = False  # the fallback navigation landed
                wait_ms = int((tab_deadline - time.monotonic()) * 1000)
                ready = await _wait_tab_ready(page, path_fragment, ready_sel, wait_ms, _SKELETON_KEY.get(name, ""), baseline)
                if not ready:
                    if await _tab_has_empty_message(page):
                        logger.info("match tab {} shows an empty message", name)
                        result.missing.add(name)
                    else:
                        logger.warning("match tab {} not rendered within {} ms", name, slice_ms)
                        result.errors[name] = SECTION_TIMEOUT
                    continue
                if name == "h2h" and h2h_more:
                    await _expand_h2h(page, h2h_more, deadline)
                result.html[name] = await page.content()
                logger.info("match tab {} in {:.1f}s", name, time.monotonic() - t0)
    except BusyError:
        raise
    except LoadFailed:
        raise
    except Exception as exc:
        if not result.html:
            raise LoadFailed(f"Failed to load {match_url}: {exc}", reason="source-refused") from exc
        logger.warning("match page session ended early: {}", exc)
        mark_timeouts(tabs)
    return result
