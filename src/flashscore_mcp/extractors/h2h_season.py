"""Season-scoped head-to-head search by team names.

The season follows the league's own format (calendar year such as MLS '2026',
or split year such as Premier League '2026/2027'), read from the league page
and its archive list; July to June is only the fallback.

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
from ..parsers.league import parse_league_page
from ..parsers.matches import parse_matches
from ..seasons import LeagueSeasons, SeasonPlan, needs_league, plan_season

@dataclass
class SeasonScan:
    items: dict[str, MatchResult] = field(default_factory=dict)
    loads: int = 0
    capped: bool = False
    timed_out: bool = False
    plan: Optional[SeasonPlan] = None
    cap: int = 0  # page-load cap actually applied


_DAY_MONTH = re.compile(r"(\d{1,2})\.(\d{1,2})\.?(\d{2,4})?")


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:  # e.g. 29 Feb in a non-leap year
        return None


def assign_years(games: list[MatchResult], tab: str, today: Optional[date] = None) -> list[Optional[date]]:
    """Full dates for team-page rows, which show only day and month.

    A results list runs newest to oldest from today and a fixtures list
    oldest to newest from today. Each row takes the year (the running year,
    or one step back for results and forward for fixtures) that puts it
    closest to the row before it. So the year changes at a real wrap, such
    as 02.01. followed by 28.12., while a row listed a few months out of
    order (Flashscore lists some cup games in a later block) keeps its year.
    A row that carries its own year is trusted as it is.
    """
    today = today or date.today()
    step = -1 if tab == "results" else 1
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
        if explicit:
            y = int(explicit)
            y = 2000 + y if y < 100 else y
            cand = _safe_date(y, month, day)
            if cand is None:
                out.append(None)
                continue
            year = y
        else:
            options = [d for d in (_safe_date(year, month, day), _safe_date(year + step, month, day)) if d]
            # Results are never after today, fixtures never long before it.
            if tab == "results":
                options = [d for d in options if d <= today + timedelta(days=2)] or options
            else:
                options = [d for d in options if d >= today - timedelta(days=60)] or options
            if not options:
                out.append(None)
                continue
            if prev is None:
                # First row: results cannot be after today, fixtures not long before it.
                if tab == "results":
                    cand = options[0] if options[0] <= today + timedelta(days=2) else options[-1]
                else:
                    cand = options[0] if options[0] >= today - timedelta(days=60) else options[-1]
            else:
                cand = min(options, key=lambda d: (abs((d - prev).days), 0 if d.year == year + step else 1))
            year = cand.year
        prev = cand
        out.append(cand)
    return out


def _past_boundary(days: list[Optional[date]], window: SeasonPlan, tab: str) -> bool:
    """Results list newest first, fixtures oldest first: has the page left the season?

    The last three dated rows must all be outside the season, so one stray
    out-of-order row cannot end the scan early.
    """
    known = [d for d in days if d is not None]
    if not known:
        return False
    tail = known[-3:]
    if tab == "results":
        return all(d < window.start for d in tail)
    return all(d > window.end for d in tail)


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


_ROWS_OR_EMPTY = ".event__match, .nmf__title, [class*='noMatches'], .leagues--static"


async def _goto_list(page, url: str) -> None:
    """Open a team's fixtures/results list without waiting out an empty one.

    safe_goto waits the full navigation timeout for rows, which is 25 s on a
    fixtures page with nothing scheduled (the season is over). Here an empty
    list marker ends the wait too, and a miss costs at most 8 s.
    """
    await page.goto(url, wait_until="domcontentloaded", timeout=settings.nav_timeout_ms)
    try:
        await page.wait_for_selector(_ROWS_OR_EMPTY, timeout=8000, state="attached")
    except Exception:
        logger.info("no rows or empty marker on {} within 8 s", url)


async def _scan_tab(
    url: str,
    tab: str,
    ref_b,
    window: SeasonPlan,
    state: SeasonScan,
    max_loads: int,
    deadline: float,
    today: date,
) -> None:
    from .match import _involves  # local import: match imports this module

    queue_wait = max(0.0, min(settings.queue_wait_s, deadline - time.monotonic()))
    async with browser_manager.new_page(queue_wait_s=queue_wait) as page:
        await _goto_list(page, url)
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


_LEAGUE_LINK = re.compile(r'<a[^>]*href="(/[a-z0-9\-]+/[a-z0-9\-]+/[a-z0-9\-]+/)"[^>]*class="headerLeague__title"')
_league_cache: dict[str, LeagueSeasons] = {}


def main_league_path(html: str) -> Optional[str]:
    """The league the team plays most in, from the league headers on its results page."""
    counts: dict[str, int] = {}
    for href in _LEAGUE_LINK.findall(html or ""):
        if "friendl" in href:
            continue
        counts[href] = counts.get(href, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda key: counts[key])


async def read_league_seasons(ref_a, deadline: float, state: SeasonScan) -> Optional[LeagueSeasons]:
    """Season labels of the team's main league: page label and archive list.

    Reads the team's results page to find its main league, then the league
    page. These two lookups are not counted against the page-load cap. Cached per team. Returns None when either step fails, so the caller
    can fall back (and say so).
    """
    if ref_a.id in _league_cache:
        return _league_cache[ref_a.id]
    queue_wait = max(0.0, min(settings.queue_wait_s, deadline - time.monotonic()))
    try:
        async with browser_manager.new_page(queue_wait_s=queue_wait) as page:
            await _goto_list(page, f"{ref_a.url}results/")
            path = main_league_path(await page.content())
            if not path:
                return None
            await safe_goto(page, f"{settings.base_url.rstrip('/')}{path}")
            info = parse_league_page(await page.content())
    except asyncio.TimeoutError:
        raise
    except Exception as exc:  # BusyError and navigation failures: fall back to July-June
        from ..errors import BusyError

        if isinstance(exc, BusyError):
            raise
        logger.warning("league season lookup failed for {}: {}", ref_a.path, exc)
        return None
    seasons = LeagueSeasons(info.name or path, info.season, tuple(item.name for item in info.archive_seasons))
    if seasons.format is None:
        return None
    # The h1 reads 'Premier League 2026/2027 scores, ...': keep just the league name.
    seasons = LeagueSeasons(
        re.sub(r"\s+\d{4}(?:\s*[/\-]\s*\d{2,4})?.*$", "", seasons.name) or seasons.name,
        seasons.page_label,
        seasons.archive_names,
    )
    _league_cache[ref_a.id] = seasons
    return seasons


def effective_cap(configured: int, plan: SeasonPlan) -> int:
    """Page-load cap for a season: grows with how far back it is, up to the configured ceiling."""
    return max(1, min(configured, max(6, 3 + 2 * plan.seasons_back)))


async def scan_season(
    ref_a,
    ref_b,
    season: Optional[str],
    state: SeasonScan,
    deadline: float,
    max_loads: Optional[int] = None,
    today: Optional[date] = None,
) -> None:
    """Fill ``state`` with the season's meetings; raises asyncio.TimeoutError at the deadline.

    ``state.plan`` is set once the season's dates are known.
    """
    today = today or date.today()
    configured = max_loads if max_loads is not None else settings.h2h_max_loads
    league = None
    if needs_league(season):
        try:
            league = await asyncio.wait_for(
                read_league_seasons(ref_a, deadline, state),
                timeout=max(0.1, deadline - time.monotonic()),
            )
        except asyncio.TimeoutError:
            raise
    plan = plan_season(season, league, today)
    state.plan = plan
    cap = state.cap = effective_cap(configured, plan)
    tabs = []
    if plan.end >= today:
        tabs.append("fixtures")
    if plan.start <= today:
        tabs.append("results")
    for tab in tabs:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise asyncio.TimeoutError()
        logger.info("h2h season scan {} {} loads={}/{}", tab, plan.label, state.loads, cap)
        await asyncio.wait_for(
            _scan_tab(f"{ref_a.url}{tab}/", tab, ref_b, plan, state, cap, deadline, today),
            timeout=remaining,
        )
