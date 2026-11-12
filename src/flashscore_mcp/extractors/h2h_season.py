"""Season-scoped head-to-head search by team names.

Two teams meet only a handful of times in one season (league home and away,
plus maybe cups), so the search reads team A's own fixtures and results pages
and stops as soon as the page has gone past the season. That is at most a few
page loads for the whole call, instead of hunting through years of results.

The scan is bounded twice: by a load cap (page loads plus "Show more" clicks)
and by one overall time budget. Whatever was found before a bound hit is kept,
and the caller is told the list may be incomplete.
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from loguru import logger

from ..browser import _match_count, _visible_show_more, browser_manager, safe_goto
from ..config import settings
from ..models import MatchResult
from ..parsers.matches import parse_matches

_SEASON_RE = re.compile(r"^(\d{4})\s*[/\-–]\s*(\d{2}|\d{4})$")
_YEAR_RE = re.compile(r"^\d{4}$")


@dataclass(frozen=True)
class SeasonWindow:
    start: date
    end: date
    label: str


def current_season_start_year(today: Optional[date] = None) -> int:
    today = today or date.today()
    return today.year if today.month >= 7 else today.year - 1


def parse_season(season: Optional[str], today: Optional[date] = None) -> Optional[SeasonWindow]:
    """Season window for '2025/26', '2025-2026', '2025' (starts in 2025), or 'current'.

    The window runs 1 July to 30 June, which fits the football calendar.
    Returns None for 'all', which means no season scope.
    """
    raw = (season or "").strip().lower()
    if raw == "all":
        return None
    if raw in ("", "current"):
        year = current_season_start_year(today)
    elif _YEAR_RE.match(raw):
        year = int(raw)
    else:
        found = _SEASON_RE.match(raw)
        if not found:
            raise ValueError(
                "season must look like '2025/26', '2025-2026', '2025', 'current' or 'all'."
            )
        year = int(found.group(1))
        tail = found.group(2)
        end_year = int(tail) if len(tail) == 4 else (year // 100) * 100 + int(tail)
        if end_year != year + 1:
            raise ValueError(f"season {season!r} must span two consecutive years, such as 2025/26.")
    return SeasonWindow(date(year, 7, 1), date(year + 1, 6, 30), f"{year}/{str(year + 1)[2:]}")


@dataclass
class SeasonScan:
    items: dict[str, MatchResult] = field(default_factory=dict)
    loads: int = 0
    capped: bool = False
    timed_out: bool = False


_DAY_MONTH = re.compile(r"(\d{1,2})\.(\d{1,2})\.?(\d{2,4})?")


def assign_years(games: list[MatchResult], tab: str, today: Optional[date] = None) -> list[Optional[date]]:
    """Full dates for team-page rows, which show only day and month.

    A results list runs newest to oldest from today and a fixtures list
    oldest to newest from today, so the year changes whenever the month
    sequence wraps. A row that does carry a year is trusted as it is.
    """
    today = today or date.today()
    year = today.year
    prev: Optional[date] = None
    out: list[Optional[date]] = []
    for game in games:
        found = _DAY_MONTH.search(game.date or "")
        if not found:
            out.append(None)
            continue
        day, month = int(found.group(1)), int(found.group(2))
        explicit = found.group(3)
        try:
            if explicit:
                y = int(explicit)
                y = 2000 + y if y < 100 else y
                cand = date(y, month, day)
                year = y
            else:
                cand = date(year, month, day)
                if tab == "results":
                    if (prev is None and cand > today + timedelta(days=2)) or (
                        prev is not None and cand > prev + timedelta(days=7)
                    ):
                        year -= 1
                        cand = date(year, month, day)
                else:
                    if (prev is None and cand < today - timedelta(days=60)) or (
                        prev is not None and cand < prev - timedelta(days=7)
                    ):
                        year += 1
                        cand = date(year, month, day)
        except ValueError:
            out.append(None)  # e.g. 29 Feb in a non-leap year
            continue
        prev = cand
        out.append(cand)
    return out


def _past_boundary(days: list[Optional[date]], window: SeasonWindow, tab: str) -> bool:
    """Results list newest first, fixtures oldest first: has the page left the season?"""
    known = [d for d in days if d is not None]
    if not known:
        return False
    return min(known) < window.start if tab == "results" else max(known) > window.end


def _dated(game: MatchResult, day: date) -> MatchResult:
    """Copy of the row with its full date, so callers see the year."""
    return game.model_copy(update={"date": day.strftime("%d.%m.%Y")})


async def _show_more_once(page) -> bool:
    """One "Show more" click. True when it added rows."""
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(250)
    except Exception:
        pass
    more = await _visible_show_more(page)
    if not more:
        return False
    before = await _match_count(page)
    try:
        try:
            await more.click(timeout=2000)
        except Exception:
            await more.click(timeout=2000, force=True)
        await page.wait_for_function(
            """(before) => document.querySelectorAll(".event__match, [id^='g_']").length > before""",
            arg=before,
            timeout=6000,
        )
    except Exception:
        pass
    return await _match_count(page) > before


async def _scan_tab(
    url: str,
    tab: str,
    ref_b,
    window: SeasonWindow,
    state: SeasonScan,
    max_loads: int,
    deadline: float,
    today: date,
) -> None:
    from .match import _involves  # local import: match imports this module

    queue_wait = max(0.0, min(settings.queue_wait_s, deadline - time.monotonic()))
    async with browser_manager.new_page(queue_wait_s=queue_wait) as page:
        await safe_goto(page, url)
        state.loads += 1
        while True:
            games = parse_matches(await page.content())
            days = assign_years(games, tab, today)
            for game, day in zip(games, days):
                if (
                    day is not None
                    and window.start <= day <= window.end
                    and game.match_id
                    and _involves(game, ref_b)
                ):
                    state.items.setdefault(game.match_id, _dated(game, day))
            if _past_boundary(days, window, tab):
                return  # the whole season is on the page
            if state.loads >= max_loads:
                if await _visible_show_more(page):
                    state.capped = True
                return
            if not await _show_more_once(page):
                return  # the list is exhausted: nothing older/newer exists
            state.loads += 1


async def scan_season(
    ref_a,
    ref_b,
    window: SeasonWindow,
    state: SeasonScan,
    deadline: float,
    max_loads: Optional[int] = None,
    today: Optional[date] = None,
) -> None:
    """Fill ``state`` with the season's meetings; raises asyncio.TimeoutError at the deadline."""
    cap = max_loads if max_loads is not None else settings.h2h_max_loads
    today = today or date.today()
    tabs = []
    if window.end >= today:
        tabs.append("fixtures")
    if window.start <= today:
        tabs.append("results")
    for tab in tabs:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise asyncio.TimeoutError()
        logger.info("h2h season scan {} {} loads={}/{}", tab, window.label, state.loads, cap)
        await asyncio.wait_for(
            _scan_tab(f"{ref_a.url}{tab}/", tab, ref_b, window, state, cap, deadline, today),
            timeout=remaining,
        )
