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
from .match_ref import section_url
from .page_status import LoadFailed

# Whole get_match call budget, well under the ~60 s client timeouts.
MATCH_BUDGET_S = 40.0

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

# tab -> (link selector in the match nav, ready selector, empty-state hint)
_TABS = {
    "stats": (
        "a[href*='/summary/stats']",
        "[data-testid='wcl-statistics'], .stat__row",
    ),
    "lineups": (
        "a[href*='/summary/lineups']",
        "[data-testid='wcl-lineupsGroup'], [data-testid^='wcl-lineupsParticipantGeneral'], .lf__lineUp",
    ),
    "h2h": (
        "a[href*='/h2h/']",
        ".h2h__section, .h2h__row",
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


async def load_match_page(
    match_url: str,
    sections: Iterable[str],
    h2h_more: int = 0,
    budget_s: float = MATCH_BUDGET_S,
) -> MatchPage:
    wanted = list(dict.fromkeys(sections))
    result = MatchPage()
    deadline = time.monotonic() + budget_s
    try:
        async with browser_manager.new_page() as page:
            started = time.monotonic()
            await page.goto(match_url, wait_until="domcontentloaded", timeout=settings.nav_timeout_ms)
            try:
                await page.wait_for_function(_NAMES_READY_JS, timeout=15000)
            except Exception:
                logger.warning("Match header did not hydrate: {}", page.url)
            result.url = page.url
            if "summary" in wanted:
                await _wait(page, _SUMMARY_READY, 3000)
                result.html["summary"] = await page.content()
            logger.info("match page ready in {:.1f}s url={}", time.monotonic() - started, page.url)

            for name in wanted:
                if name == "summary" or name not in _TABS:
                    continue
                remaining_ms = int((deadline - time.monotonic()) * 1000)
                if remaining_ms <= 1000:
                    result.errors[name] = "timeout"
                    continue
                link_sel, ready_sel = _TABS[name]
                link = page.locator(link_sel).first
                t0 = time.monotonic()
                try:
                    has_link = await link.count() > 0
                except Exception:
                    has_link = False
                if not has_link:
                    if "?mid=" not in (page.url or ""):
                        result.errors[name] = "source-refused"
                    else:
                        result.missing.add(name)
                    continue
                try:
                    await link.click(timeout=3000)
                except Exception:
                    try:
                        await page.goto(
                            section_url(page.url, name),
                            wait_until="domcontentloaded",
                            timeout=min(settings.nav_timeout_ms, remaining_ms),
                        )
                    except Exception as exc:
                        result.errors[name] = "source-refused"
                        logger.warning("match tab {} navigation failed: {}", name, exc)
                        continue
                ready = await _wait(page, ready_sel, min(9000, remaining_ms))
                if not ready:
                    # Tab exists but rendered no rows: keep the page so the
                    # caller can tell "no data" from a broken load.
                    logger.info("match tab {} rendered no rows", name)
                if name == "h2h" and ready and h2h_more:
                    await _expand_h2h(page, h2h_more, deadline)
                result.html[name] = await page.content()
                logger.info("match tab {} in {:.1f}s ready={}", name, time.monotonic() - t0, ready)
    except LoadFailed:
        raise
    except Exception as exc:
        if not result.html:
            raise LoadFailed(f"Failed to load {match_url}: {exc}", reason="source-refused") from exc
        logger.warning("match page session ended early: {}", exc)
    return result
