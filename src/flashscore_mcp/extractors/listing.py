"""Results and fixtures lists: read rows from the page's own feeds, then filter and page.

A league or team results/fixtures tab embeds its first rows as a feed
(cjs.initialFeeds) and loads each further batch from x/feed/... when "Show
more matches" is clicked. The feed rows carry the round, competition and
kick-off timestamp of every game, so they are the source of truth here; the
rendered rows only add period scores, notes and the full match URL.

Loading stops as soon as the caller has enough: the requested page plus one
row (to know there is more), or rows past the requested date range. One
overall time budget bounds the whole read; whatever loaded before it ran out
is returned as a partial page.

Every page is kept under a byte budget (FLASHSCORE_PAGE_BYTES), because the
connector gateway cuts responses at about 20 KB and drops whatever does not
fit. The response says how many rows match (total), whether there are more
(has_more) and where the next page starts (next_offset).
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional, Sequence

from loguru import logger

from ..browser import _match_count, _visible_show_more, browser_manager, safe_goto
from ..config import settings
from ..errors import BusyError, LoadFailed
from ..models import CompactMatch, MatchCollection, MatchResult
from ..parsers.feed import initial_feeds, merge_listing, parse_list_feed
from ..parsers.matches import parse_matches
from ..parsers.stage import apply_stage, knockout_slug, round_number
from ..timeutil import game_day, localize, parse_day, zone_name

# Show-more batches come from x/feed/<prefix>_...; the day feed (f_<sport>_<day>)
# and the menu counters (mc_, cmc_) are not list rows.
_LIST_FEED = re.compile(r"/x/feed/(?!f_|mc_|cmc_)[a-z]{1,4}_")
DEFAULT_COMPACT_LIMIT = 100
MAX_LIMIT = 500


@dataclass
class Listing:
    """What one list page read produced."""

    items: list[MatchResult] = field(default_factory=list)
    html: str = ""
    all_count: Optional[int] = None  # allEventsCount: every row of the tab
    complete: bool = False  # Show more is gone: nothing further exists
    timed_out: bool = False
    # Flashscore stopped handing out rows before allEventsCount was reached
    # (the Show more control vanished or added nothing).
    stalled: bool = False
    from_feed: bool = False
    clicks: int = 0


@dataclass
class _Cached:
    at: float
    html: str
    batches: dict
    template: Optional[str]
    sign: Optional[str]
    complete: bool


# Recently read lists, so paging through a season does not reload the page
# for every page: later batches come straight from the feed by number.
_cache: dict[str, _Cached] = {}
_ARCHIVE_SLUG = re.compile(r"-\d{4}(?:-\d{4})?/(?:results|fixtures)/?$")


_CACHE_MAX = 24


def _remember(url: str, entry: "_Cached") -> None:
    _cache[url] = entry
    while len(_cache) > _CACHE_MAX:
        oldest = min(_cache, key=lambda k: _cache[k].at)
        _cache.pop(oldest, None)


def _ttl(url: str) -> float:
    """Archived seasons do not change; current lists (live scores) only briefly cached."""
    return settings.list_cache_archive_s if _ARCHIVE_SLUG.search(url or "") else settings.list_cache_s


def tab_key(url: str) -> str:
    return "fixtures" if "/fixtures" in (url or "").lower() else "results"


def rows_from(html: str, extra_feeds: Sequence[str], key: str) -> tuple[list[MatchResult], Optional[int], bool]:
    """(rows, allEventsCount, from_feed) for a list page and its captured batches."""
    feeds = initial_feeds(html)
    first, count = feeds.get(key, ("", None))
    feed_rows = parse_list_feed(first)
    for text in extra_feeds:
        feed_rows.extend(parse_list_feed(text))
    rendered = parse_matches(html)
    if not feed_rows:
        return [apply_stage(game) for game in rendered], count, False
    return [apply_stage(game) for game in merge_listing(feed_rows, rendered)], count, True


async def fetch_listing(
    url: str,
    enough: Optional[Callable[[list[MatchResult]], bool]] = None,
    budget_s: Optional[float] = None,
    timezone_id: str = "UTC",
) -> Listing:
    """Open a results/fixtures tab and load batches until enough(rows) or the end.

    Raises LoadFailed when the page does not load; BusyError when no browser
    slot frees up in time. Runs out of budget -> Listing.timed_out with the
    rows loaded so far.
    """
    budget = settings.list_budget_s if budget_s is None else budget_s
    deadline = time.monotonic() + budget
    key = tab_key(url)
    cached = _cache.get(url)
    if cached is not None and time.monotonic() - cached.at > _ttl(url):
        _cache.pop(url, None)
        cached = None
    if cached is not None:
        hit = await _from_cache(url, cached, key, enough, deadline)
        if hit is not None:
            return hit
    # Show-more batches by page number (parsed from the feed URL).
    batches: dict[int, str] = dict(cached.batches) if cached is not None else {}
    requested: list[str] = []
    pending: list[asyncio.Future] = []
    out = Listing()

    async def grab(response) -> None:
        if not _LIST_FEED.search(response.url):
            return
        try:
            body = await response.text() if response.ok else ""
        except Exception as exc:  # pragma: no cover - network edge
            logger.debug("list feed body unavailable: {}", exc)
            return
        number = batch_number(response.url)
        if "AA÷" in body and number is not None:
            batches.setdefault(number, body)

    def on_request(request) -> None:
        if _LIST_FEED.search(request.url) and batch_number(request.url) is not None:
            requested.append(request.url)

    async def settle() -> None:
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
            pending.clear()

    def current(html: str) -> list[MatchResult]:
        rows, count, from_feed = rows_from(html, [batches[n] for n in sorted(batches)], key)
        out.all_count, out.from_feed = count, from_feed
        return rows

    def finished(rows: list[MatchResult]) -> bool:
        if enough is not None and enough(rows):
            return True
        if out.all_count is not None and len(rows) >= out.all_count:
            out.complete = True
            return True
        return False

    try:
        queue_wait = max(0.0, min(settings.queue_wait_s, deadline - time.monotonic()))
        async with browser_manager.new_page(queue_wait_s=queue_wait, timezone_id=timezone_id) as page:
            page.on("response", lambda r: pending.append(asyncio.ensure_future(grab(r))))
            page.on("request", on_request)
            await asyncio.wait_for(safe_goto(page, url), timeout=max(1.0, deadline - time.monotonic()))
            html = await page.content()
            sign = _feed_sign(html)
            stale = 0
            while True:
                await settle()
                rows = current(await page.content())
                if finished(rows):
                    break
                if time.monotonic() >= deadline - 3:
                    out.timed_out = True
                    break
                if requested and sign:
                    # The first click showed the batch URL: read the next
                    # batches straight from the feed (with retries), which is
                    # faster than clicking and survives a failed batch.
                    await _direct_batches(page, requested[0], sign, batches, deadline, out, current, finished)
                    break
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception:
                    pass
                more = await _visible_show_more(page)
                if more is None:
                    if out.all_count is not None and len(rows) < out.all_count:
                        if not await _wait_for_more(page, len(rows), deadline):
                            out.stalled = True
                            break
                        continue
                    out.complete = True
                    break
                before_rows = await _match_count(page)
                before_batches = len(batches)
                try:
                    try:
                        await more.click(timeout=2000)
                    except Exception:
                        await more.click(timeout=2000, force=True)
                except Exception as exc:
                    logger.info("Show more click failed on {}: {}", url, exc)
                    break
                out.clicks += 1
                wait_ms = int(max(500, min(10000, (deadline - time.monotonic() - 2) * 1000)))
                try:
                    await page.wait_for_function(
                        """(before) => document.querySelectorAll(".event__match, [id^='g_']").length > before""",
                        arg=before_rows,
                        timeout=wait_ms,
                    )
                except Exception:
                    pass
                await settle()
                if await _match_count(page) <= before_rows and len(batches) == before_batches and not requested:
                    stale += 1
                    if stale >= 2:
                        logger.warning("Show more added no rows twice on {}", url)
                        out.stalled = True
                        break
                else:
                    stale = 0
            await settle()
            out.html = await page.content()
            out.items = current(out.html)
            if out.items:
                _remember(url, _Cached(
                    time.monotonic(), out.html, dict(batches), requested[0] if requested else None, sign, out.complete
                ))
    except BusyError:
        raise
    except LoadFailed:
        raise
    except asyncio.TimeoutError:
        out.timed_out = True
        if not out.items and not out.html:
            raise LoadFailed(f"Timed out loading {url} within {budget:.0f}s.", reason="timeout")
    except Exception as exc:
        raise LoadFailed(f"Failed to load {url}: {exc}", reason="source-refused") from exc
    logger.info(
        "fetch_listing url={} rows={} all={} clicks={} complete={} timed_out={} feed={}",
        url, len(out.items), out.all_count, out.clicks, out.complete, out.timed_out, out.from_feed,
    )
    return out


_FEED_SIGN = re.compile(r'"feed_sign"\s*:\s*"([^"]+)"')


def _feed_sign(html: str) -> Optional[str]:
    found = _FEED_SIGN.search(html or "")
    return found.group(1) if found else None


def batch_number(feed_url: str) -> Optional[int]:
    """Page number of a show-more feed URL: tr_5_200_<tournament>_<season>_<N>_0_en_1 or pr_5_200_<team>_<N>_0_en_1."""
    name = feed_url.rstrip("/").rsplit("/", 1)[-1]
    parts = name.split("_")
    if len(parts) < 6:
        return None
    value = parts[-4]
    return int(value) if value.isdigit() else None


def batch_url(template: str, number: int) -> str:
    head, name = template.rstrip("/").rsplit("/", 1)
    parts = name.split("_")
    parts[-4] = str(number)
    return f"{head}/{'_'.join(parts)}"


_FETCH_JS = """async ([u, sign]) => {
  try {
    const r = await fetch(u, {headers: {'x-fsign': sign}, credentials: 'omit'});
    return [r.status, r.ok ? await r.text() : ''];
  } catch (e) { return [0, String(e)]; }
}"""


async def _fetch_batch(page, template: str, sign: str, number: int, deadline: float) -> Optional[str]:
    """One feed batch by number, retried while the budget allows (Flashscore answers 503 at times)."""
    from .http_util import get_feed

    url = batch_url(template, number)
    for attempt in range(6):
        if page is not None:
            status, text = await page.evaluate(_FETCH_JS, [url, sign])
        else:
            status, text = await get_feed(url, sign, timeout=max(2.0, min(10.0, deadline - time.monotonic() - 1)))
        if status == 200:
            return text
        logger.info("feed batch {} status {} (try {})", number, status, attempt + 1)
        if time.monotonic() >= deadline - 4:
            break
        await asyncio.sleep(min(4.0, 1.0 + attempt))
    return None


async def _from_cache(url: str, cached: "_Cached", key: str, enough, deadline: float) -> Optional[Listing]:
    """Serve a list from the cache, reading further batches from the feed when needed."""
    out = Listing(html=cached.html, clicks=0)
    batches = dict(cached.batches)

    def current(_html: str = "") -> list[MatchResult]:
        rows, count, from_feed = rows_from(cached.html, [batches[n] for n in sorted(batches)], key)
        out.all_count, out.from_feed = count, from_feed
        return rows

    def finished(rows: list[MatchResult]) -> bool:
        if out.all_count is not None and len(rows) >= out.all_count:
            out.complete = True
            return True
        if cached.complete:
            out.complete = True
            return True
        return enough is not None and enough(rows)

    rows = current()
    if not finished(rows):
        if not (cached.template and cached.sign):
            return None  # needs the browser to find the batch URL
        await _direct_batches(None, cached.template, cached.sign, batches, deadline, out, current, finished)
        rows = current()
    out.items = rows
    _remember(url, _Cached(cached.at, cached.html, batches, cached.template, cached.sign, out.complete))
    logger.info("fetch_listing (cached) url={} rows={} all={} batches={} complete={}", url, len(rows), out.all_count, len(batches), out.complete)
    return out


async def _direct_batches(page, template, sign, batches, deadline, out, current, finished) -> None:
    """Read show-more batches by page number until enough rows, the end, or the budget."""
    number = batch_number(template) or 1
    while True:
        if time.monotonic() >= deadline - 2:
            out.timed_out = True
            return
        if number not in batches:
            body = await _fetch_batch(page, template, sign, number, deadline)
            if body is None:
                out.stalled = True
                return
            if "AA÷" not in body:
                out.complete = True  # an empty batch: the list has ended
                return
            batches[number] = body
            out.clicks += 1
        rows = current(await page.content()) if page is not None else current()
        if finished(rows):
            return
        number += 1


async def _wait_for_more(page, have: int, deadline: float) -> bool:
    """After a click the control hides until its batch lands; wait for rows or the control."""
    wait_ms = int(max(500, min(8000, (deadline - time.monotonic() - 2) * 1000)))
    try:
        await page.wait_for_function(
            """(have) => document.querySelectorAll(".event__match, [id^='g_']").length > have
                || [...document.querySelectorAll('a.event__more, button')].some(
                     el => /show more/i.test(el.textContent || '') && el.offsetParent !== null)""",
            arg=have,
            timeout=wait_ms,
        )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

_STAGES = {"regular_season", "playoffs", "all_star", "preseason", "qualification", "relegation"}
_STAGE_ALIASES = {
    "regular": "regular_season", "regular season": "regular_season", "season": "regular_season",
    "playoff": "playoffs", "play offs": "playoffs", "play-offs": "playoffs", "postseason": "playoffs",
    "allstar": "all_star", "all stars": "all_star", "all-star": "all_star", "pro bowl": "all_star",
    "pre-season": "preseason", "pre season": "preseason",
}


@dataclass
class Filters:
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    round: Optional[str] = None
    stage: Optional[str] = None
    timezone: Optional[str] = None

    @property
    def active(self) -> bool:
        return any(v is not None for v in (self.date_from, self.date_to, self.round, self.stage))


def build_filters(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    round: Optional[str | int] = None,
    stage: Optional[str] = None,
    timezone: Optional[str] = None,
    since: Optional[str] = None,
) -> Filters:
    zone_name(timezone)  # ValueError for an unknown zone, before any page load
    start = parse_day(date_from) if date_from else None
    if since and start is None:
        start = _since_day(since)
    end = parse_day(date_to) if date_to else None
    if start and end and start > end:
        raise ValueError("date_from must be on or before date_to.")
    wanted_stage = None
    if stage:
        key = stage.strip().lower().replace("_", " ")
        wanted_stage = _STAGE_ALIASES.get(key, key.replace(" ", "_"))
        if wanted_stage not in _STAGES:
            raise ValueError(f"stage must be one of: {', '.join(sorted(_STAGES))}.")
    rnd = str(round).strip() if round is not None and str(round).strip() else None
    return Filters(start, end, rnd, wanted_stage, timezone)


def _since_day(since: str) -> Optional[date]:
    try:
        return parse_day(since)
    except ValueError:
        # Legacy 'DD.MM.' without a year is handled by the caller's take_until.
        return None


def round_matches(game: MatchResult, wanted: str) -> bool:
    text = wanted.strip().lower()
    if text.isdigit():
        return game.round_number == int(text)
    num = round_number(wanted)
    if num is not None:
        return game.round_number == num
    slug = knockout_slug(wanted) or text.replace(" ", "_").replace("-", "_")
    if game.playoff_round and game.playoff_round == slug:
        return True
    def norm(value: str | None) -> str:
        return " ".join((value or "").lower().replace("_", " ").replace("-", " ").split())

    return norm(text) in {norm(game.round), norm(game.playoff_round_name)}


def keep(game: MatchResult, filters: Filters) -> bool:
    if filters.stage and game.stage != filters.stage:
        return False
    if filters.round and not round_matches(game, filters.round):
        return False
    if filters.date_from or filters.date_to:
        day = game_day(game, filters.timezone)
        if day is None:
            return False
        if filters.date_from and day < filters.date_from:
            return False
        if filters.date_to and day > filters.date_to:
            return False
    return True


def past_range(rows: list[MatchResult], filters: Filters, newest_first: bool) -> bool:
    """True once the loaded rows run past the date range in load order."""
    edge = filters.date_from if newest_first else filters.date_to
    if edge is None:
        return False
    for game in reversed(rows):
        day = game_day(game, filters.timezone)
        if day is None:
            continue
        return day < edge if newest_first else day > edge
    return False


def stop_rule(
    filters: Filters,
    offset: int,
    limit: Optional[int],
    newest_first: bool,
    extra: Optional[Callable[[MatchResult], bool]] = None,
):
    """enough(rows) for fetch_listing: the page plus one row, or past the date range."""
    want = None if limit is None else offset + limit + 1

    def wanted(game: MatchResult) -> bool:
        return keep(game, filters) and (extra is None or extra(game))

    def enough(rows: list[MatchResult]) -> bool:
        if filters.round or filters.stage:
            # A round or stage can be spread out (postponed games): read on
            # until the date range (if any) is passed.
            return past_range(rows, filters, newest_first)
        if past_range(rows, filters, newest_first):
            return True
        if want is None:
            return False
        if filters.active or extra is not None:
            return sum(1 for g in rows if wanted(g)) >= want
        return len(rows) >= want

    return enough


# ---------------------------------------------------------------------------
# Paging
# ---------------------------------------------------------------------------


def compact_row(game: MatchResult) -> CompactMatch:
    score = None
    if game.home_score is not None and game.away_score is not None:
        score = f"{game.home_score}-{game.away_score}"
    return CompactMatch(
        id=game.match_id,
        kickoff_utc=game.kickoff_utc,
        date=game.date,
        round=game.round,
        round_number=game.round_number,
        stage=game.stage,
        playoff_round=game.playoff_round,
        home=game.home_team,
        away=game.away_team,
        score=score,
        status=game.status,
    )


def _size(item) -> int:
    return len(json.dumps(item.model_dump(), separators=(",", ":"), ensure_ascii=False).encode()) + 1


def check_paging(offset: Optional[int], limit: Optional[int]) -> tuple[int, Optional[int]]:
    off = 0 if offset is None else int(offset)
    if off < 0:
        raise ValueError("offset must be zero or more.")
    if limit is not None:
        limit = int(limit)
        if limit < 1:
            raise ValueError("limit must be at least 1.")
        limit = min(limit, MAX_LIMIT)
    return off, limit


def page_collection(
    rows: list[MatchResult],
    filters: Filters,
    offset: int,
    limit: Optional[int],
    compact: bool,
    *,
    complete: bool,
    all_count: Optional[int] = None,
    timed_out: bool = False,
    stalled: bool = False,
    notes: Optional[list[str]] = None,
    newest_first: bool = True,
) -> MatchCollection:
    """One page of filtered rows under the byte budget, with paging fields."""
    matching = [game for game in rows if keep(game, filters)]
    matching = localize(matching, filters.timezone)
    budget = max(1000, settings.page_bytes)
    page_items: list = []
    used = 200  # envelope
    cut_by_bytes = False
    for game in matching[offset:]:
        if limit is not None and len(page_items) >= limit:
            break
        item = compact_row(game) if compact else game
        size = _size(item)
        if page_items and used + size > budget:
            cut_by_bytes = True
            break
        page_items.append(item)
        used += size
    end = offset + len(page_items)
    if complete:
        total: Optional[int] = len(matching)
    elif not filters.active and all_count is not None and not timed_out:
        total = all_count
    elif filters.active and range_closed(rows, filters, newest_first):
        total = len(matching)
    else:
        total = None
    has_more = end < total if total is not None else True
    out_notes = list(notes or [])
    tz_label = zone_name(filters.timezone)
    out_notes.append(
        f"Rows {offset}-{max(offset, end - 1)} ({len(page_items)} returned), {"newest first" if newest_first else "oldest first"}; dates and times in {tz_label}"
        + (", kickoff_utc is ISO 8601 UTC." if not compact else ".")
    )
    if cut_by_bytes:
        out_notes.append(
            f"Page cut at about {budget // 1000} KB to fit the connector's response limit; "
            f"pass offset={end} for the next page"
            + ("." if compact else ", or compact=true for more rows per page.")
        )
    status, reason, errors = "ok", None, []
    if timed_out:
        status, reason = "partial", "timeout"
        errors.append(
            f"timeout: the list read stopped after {settings.list_budget_s:.0f}s; rows past the loaded ones "
            "may be missing. Narrow it with date_from/date_to or retry."
        )
    elif stalled:
        status, reason = "partial", "source-incomplete"
        loaded = len(rows)
        errors.append(
            f"Flashscore stopped loading more rows after {loaded}"
            + (f" of {all_count}" if all_count else "")
            + "; later pages may be missing. Retry in a moment."
        )
    if not page_items:
        if status == "ok":
            status = "empty"
            reason = "no-matches" if not filters.active else "no-matching-rows"
        if complete and offset and matching and offset >= len(matching):
            out_notes.append(f"offset {offset} is past the last matching row ({len(matching)}).")
    return MatchCollection(
        status=status,
        reason=reason,
        items=page_items,
        errors=errors,
        notes=out_notes,
        total=total,
        offset=offset,
        returned=len(page_items),
        has_more=bool(has_more),
        next_offset=end if has_more else None,
        timezone=tz_label,
    )


def range_closed(rows: list[MatchResult], filters: Filters, newest_first: bool) -> bool:
    """A date-bounded read is complete once a row past the far end of the range has loaded.

    The list starts at its newest row (results) or its oldest (fixtures), so
    only the far side needs proof.
    """
    if not (filters.date_from or filters.date_to):
        return False
    return past_range(rows, filters, newest_first)
