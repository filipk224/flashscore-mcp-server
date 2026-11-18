"""Results history. Rows come from the tab's own feed (see listing.py)."""
from __future__ import annotations

from typing import Optional
from urllib.parse import urljoin

from loguru import logger

from ..config import settings
from ..models import MatchCollection
from ..parsers.adapter import count_match_hints
from ..parsers.archive import parse_archive, resolve_season
from .fetch import fetch_html
from .listing import build_filters, check_paging, fetch_listing, page_collection, stop_rule
from .page_status import empty_or_raise
from .resolve import resolve_league_ref
from .window import take_until


def _league_url(league: str, season: str, tab: str) -> str:
    if league.startswith("http"):
        base = league.rstrip("/")
        for suffix in ("/results", "/fixtures", "/standings", "/news", "/archive", "/odds"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
        return f"{base}/{tab}/" if tab else f"{base}/"
    key = league.strip("/")
    if season and season not in ("current",) and season.isdigit() and f"-{season}" not in key:
        parts = key.split("/")
        parts[-1] = f"{parts[-1]}-{season}"
        key = "/".join(parts)
    return f"{settings.base_url}/{key}/{tab}/" if tab else f"{settings.base_url}/{key}/"


# Archive season lists change once a season; paging through one season reads
# it on every call, so keep it for a while.
_ARCHIVE_TTL_S = 3600.0
_archive_cache: dict[str, tuple[float, list]] = {}


async def resolve_archive_season(league: str, season: str) -> tuple[str | None, list[str]]:
    """Archive season URL from the league's /archive/ page.

    league_archive_data is server-rendered, so the archive page is ready at
    DOMContentLoaded. The old lookup loaded the current standings page and
    waited for its table to hydrate first, which was the slow half of every
    historical call.
    """
    return resolve_season(await archive_seasons(league), season)


async def archive_seasons(league: str) -> list:
    """The league's archive season list (cached for an hour)."""
    import time as _time

    archive_url = _league_url(league, "current", "archive")
    cached = _archive_cache.get(archive_url)
    if cached and _time.monotonic() - cached[0] < _ARCHIVE_TTL_S:
        return cached[1]
    html = await fetch_html(archive_url)
    seasons = parse_archive(html)
    if seasons:
        _archive_cache[archive_url] = (_time.monotonic(), seasons)
    return seasons


async def _season_tab_url(league: str, season: str, tab: str) -> str | None:
    if season in ("current", "", None):
        return _league_url(league, "current", tab)
    target, _names = await resolve_archive_season(league, season)
    if not target:
        return None
    return urljoin(settings.base_url, target).rstrip("/") + f"/{tab}/"


def _legacy_since(since: Optional[str]) -> Optional[str]:
    """A since without a year ('01.09.') keeps the old newest-first walk."""
    if not since:
        return None
    from ..timeutil import parse_day

    try:
        parse_day(since)
        return None
    except ValueError:
        return since


async def read_list(
    url: str,
    tab: str,
    *,
    offset: Optional[int] = None,
    limit: Optional[int] = None,
    since: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    round: Optional[str] = None,
    stage: Optional[str] = None,
    compact: bool = False,
    timezone: Optional[str] = None,
    newest_first: bool = True,
    keep_status: Optional[str] = None,
    notes: Optional[list[str]] = None,
    row_filter=None,
) -> MatchCollection:
    """Load a results/fixtures tab as far as the request needs, then page it."""
    off, lim = check_paging(offset, limit)
    filters = build_filters(date_from, date_to, round, stage, timezone, since=since)
    legacy = _legacy_since(since) if filters.date_from is None else None
    def extra(game) -> bool:
        if keep_status and game.status != keep_status:
            return False
        return row_filter is None or row_filter(game)

    use_extra = extra if (keep_status or row_filter) else None
    enough = None if legacy else stop_rule(
        filters, off, lim if lim is not None else _byte_rows(compact), newest_first, use_extra
    )
    listing = await fetch_listing(url, enough=enough)
    rows = listing.items
    if use_extra is not None:
        rows = [game for game in rows if use_extra(game)]
    if legacy:
        rows = take_until(rows, since=legacy)
    if not listing.items:
        empty_or_raise(listing.html, tab, [], raw_hints=count_match_hints(listing.html))
    all_count = listing.all_count if use_extra is None and not legacy else None
    page_notes = list(notes or [])
    if not listing.from_feed and listing.items:
        page_notes.append("Rows were read from the rendered list (no feed found); dates may lack a year.")
    result = page_collection(
        rows,
        filters,
        off,
        lim,
        compact,
        complete=listing.complete,
        all_count=all_count,
        timed_out=listing.timed_out,
        stalled=listing.stalled,
        notes=page_notes,
        newest_first=newest_first,
    )
    logger.info("read_list {} -> {} of {} (has_more={})", url, result.returned, result.total, result.has_more)
    return result


def _byte_rows(compact: bool) -> int:
    """Rows a default page can hold, to know how far to load."""
    per_row = 230 if compact else 700
    return max(5, settings.page_bytes // per_row + 1)


async def get_results_history(
    league: str,
    season: str = "current",
    mode: str = "full",
    limit: Optional[int] = None,
    since: Optional[str] = None,
    offset: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    round: Optional[str] = None,
    stage: Optional[str] = None,
    compact: bool = False,
    timezone: Optional[str] = None,
) -> MatchCollection:
    league = await resolve_league_ref(league)
    url = await _season_tab_url(league, season, "results")
    logger.info("get_results_history url={} offset={} limit={} since={}", url, offset, limit, since)
    if not url:
        raise ValueError(f"Unknown season {season!r} for league {league}")
    return await read_list(
        url,
        "results",
        offset=offset,
        limit=limit,
        since=since,
        date_from=date_from,
        date_to=date_to,
        round=round,
        stage=stage,
        compact=compact or mode == "compact",
        timezone=timezone,
        newest_first=True,
    )
