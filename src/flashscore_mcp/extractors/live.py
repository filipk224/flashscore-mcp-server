"""Live matches and day listings across a sport (optionally one league)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import quote

from loguru import logger

from ..config import settings
from ..models import MatchCollection, MatchResult
from ..parsers.adapter import count_match_hints
from ..parsers.matches import parse_matches
from ..parsers.feed import merge_rows, parse_day_feed
from .fetch import DayPage, fetch_day, fetch_html
from ..errors import BusyError
from .page_status import LoadFailed, page_outcome
from .resolve import parse_name_and_country, resolve_league_ref
from .results import _league_url, read_list, resolve_archive_season
from ..timeutil import game_day, localize, today, zone_name

_SPORT_ALIASES = {"soccer": "football"}
_STATUS_ALIASES = {
    "all": "all",
    "any": "all",
    "": "all",
    "live": "live",
    "finished": "finished",
    "result": "finished",
    "results": "finished",
    "scheduled": "scheduled",
    "fixture": "scheduled",
    "fixtures": "scheduled",
    "upcoming": "scheduled",
}


def normalize_sport(sport: str) -> str:
    slug = (sport or "").strip().strip("/").lower().replace(" ", "-")
    if not slug:
        raise ValueError("sport is required, for example 'football' or 'basketball'.")
    return _SPORT_ALIASES.get(slug, slug)


def normalize_status(status: Optional[str]) -> str:
    key = (status or "all").strip().lower()
    if key not in _STATUS_ALIASES:
        raise ValueError("status must be one of: all, live, finished, scheduled")
    return _STATUS_ALIASES[key]


def resolve_day_offset(day_offset: Optional[int], date_str: Optional[str], tz: Optional[str] = None) -> int:
    """Days from today (in tz, UTC by default) to the requested day."""
    if date_str:
        try:
            target = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("date must be YYYY-MM-DD") from exc
        return (target - today(tz)).days
    if day_offset is None:
        return 0
    return int(day_offset)


def _parse_game_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    parts = value.strip().rstrip(".").split(".")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        year = date.today().year if len(parts) == 2 else int(parts[2])
        if year < 100:
            year += 2000
        try:
            parsed = date(year, int(parts[1]), int(parts[0]))
        except ValueError:
            return None
        if len(parts) == 2 and parsed > date.today() + timedelta(days=30):
            parsed = date(year - 1, int(parts[1]), int(parts[0]))
        return parsed
    return None


def _target_date(day_offset: int, tz: Optional[str] = None) -> date:
    return today(tz) + timedelta(days=day_offset)


def filter_status(items: list[MatchResult], status: str) -> list[MatchResult]:
    if status == "all":
        return items
    return [item for item in items if item.status == status]


def _league_label(league: str) -> tuple[Optional[str], Optional[str]]:
    return parse_name_and_country(league)


def matches_league(game: MatchResult, league: str, resolved: Optional[str] = None) -> bool:
    header = (game.competition or "").lower()
    name, country = _league_label(league)
    needles = [part.lower() for part in (name, country) if part]
    if name and name.lower() in header:
        if country and country.lower() not in header and ":" in header:
            # Header like "ENGLAND: Premier League" should match both.
            if country.lower() not in header:
                pass
        return True
    if country and country.lower() in header and not name:
        return True
    if resolved:
        slug = resolved.rstrip("/").split("/")[-1].replace("-", " ")
        if slug and slug in header:
            return True
    combined = f"{game.home_team} {game.away_team}".lower()
    return False if needles else True


# The day picker on a sport page reaches a week either side of today.
MAX_PICKER_DAYS = 7


def _sport_day_url(sport: str, day_offset: int = 0) -> str:
    """Sport landing page. The day is chosen with the picker, not a query."""
    return f"{settings.base_url.rstrip('/')}/{quote(sport, safe='-')}/"


def _day_items(day: DayPage, league_path: Optional[str] = None) -> tuple[list[MatchResult], list[MatchResult]]:
    """(merged games, rendered rows) for one day page."""
    rendered = parse_matches(day.html)
    feed = parse_day_feed(day.feed, league_path) if day.feed else []
    if league_path and feed:
        ids = {game.match_id for game in feed}
        rendered = [game for game in rendered if game.match_id in ids]
    elif league_path and not feed:
        rendered = []
    return merge_rows(feed, rendered), rendered


async def _optional_league_path(league: Optional[str], country: Optional[str]) -> Optional[str]:
    if not league:
        return None
    ref = league
    if country and "(" not in league and "," not in league:
        ref = f"{league} ({country})"
    return await resolve_league_ref(ref)


def _collection(html: str, items: list[MatchResult], tab: str) -> MatchCollection:
    if items:
        return MatchCollection(status="ok", items=items)
    status, reason = page_outcome(html, tab=tab, parsed_count=0, raw_hints=count_match_hints(html))
    if status == "failed":
        raise LoadFailed(
            f"Failed to load {tab}: the page did not contain usable match data.",
            reason=reason or "parse-failed",
        )
    return MatchCollection(status="empty", reason=reason or "no-matches-scheduled", items=[])



def _after_filter(
    html: str,
    items: list[MatchResult],
    parsed: list[MatchResult],
    tab: str,
) -> MatchCollection:
    if items:
        return MatchCollection(status="ok", items=items)
    if parsed:
        return MatchCollection(status="empty", reason="no-matches-scheduled", items=[])
    return _collection(html, items, tab)


async def get_live_matches(
    sport: str,
    country: Optional[str] = None,
    league: Optional[str] = None,
) -> MatchCollection:
    sport = normalize_sport(sport)
    resolved = await _optional_league_path(league, country)
    day_sport = sport
    if resolved and not resolved.startswith("http"):
        day_sport = resolved.strip("/").split("/")[0] or sport
    url = _sport_day_url(day_sport, 0)
    logger.info("get_live_matches url={} league={}", url, resolved)
    day = await fetch_day(url, 0, live_tab=True)
    html = day.html
    parsed, _rendered = _day_items(day, resolved)
    if resolved and day.feed and not parsed:
        return MatchCollection(status="empty", reason="no-matches-scheduled", items=[])
    items = [game for game in parsed if game.status == "live"]
    if country:
        items = [game for game in items if matches_league(game, country, None) or (
            game.competition and country.lower() in game.competition.lower()
        )]
    return _after_filter(html, items, parsed, "live")


async def get_matches_by_day(
    sport: str,
    day_offset: Optional[int] = None,
    date: Optional[str] = None,
    status: str = "all",
    league: Optional[str] = None,
    timezone: Optional[str] = None,
    offset: Optional[int] = None,
    limit: Optional[int] = None,
    compact: bool = False,
) -> MatchCollection:
    from .listing import build_filters, check_paging, page_collection

    sport = normalize_sport(sport)
    wanted_status = normalize_status(status)
    tz_label = zone_name(timezone)  # ValueError for an unknown zone
    off, lim = check_paging(offset, limit)
    day_offset_v = resolve_day_offset(day_offset, date, timezone)
    target = _target_date(day_offset_v, timezone)
    resolved = await _optional_league_path(league, None)
    day_filter = build_filters(target.isoformat(), target.isoformat(), timezone=timezone)

    if abs(day_offset_v) <= MAX_PICKER_DAYS:
        day_sport = sport
        if resolved and not resolved.startswith("http"):
            day_sport = resolved.strip("/").split("/")[0] or sport
        url = _sport_day_url(day_sport, day_offset_v)
        logger.info("get_matches_by_day url={} offset={} league={} tz={}", url, day_offset_v, resolved, tz_label)
        day = await fetch_day(url, day_offset_v, timezone_id=tz_label)
        if day_offset_v != 0 and not day.feed and not _label_matches(day.label, target):
            raise LoadFailed(
                f"Could not switch the {day_sport} page to {target.isoformat()} "
                f"(day picker showed {day.label!r}).",
                reason="parse-failed",
            )
        parsed, _rendered = _day_items(day, resolved)
        if day.feed:
            # A day feed also carries late games from the evening before and
            # early ones after midnight; keep only the requested date.
            parsed = [game for game in parsed if _same_day(game, target, timezone)]
        items = filter_status(parsed, wanted_status)
        if items:
            from ..parsers.stage import apply_stage

            page = page_collection(
                [apply_stage(g) for g in items], build_filters(timezone=timezone), off, lim, compact,
                complete=True, newest_first=False,
            )
            page.notes[-1] = page.notes[-1].replace("oldest first", "in page order")
            return page
        if day.feed or parsed:
            # The day loaded; that league or status simply has no games.
            return MatchCollection(status="empty", reason="no-matches-scheduled", items=[], timezone=tz_label)
        empty = _collection(day.html, [], "day")
        empty.timezone = tz_label
        return empty

    if resolved:
        return await _league_day(resolved, target, wanted_status, timezone, off, lim, compact, day_filter)

    raise ValueError(
        f"Flashscore's day picker covers {MAX_PICKER_DAYS} days either side of today. "
        "For an older or later date pass a league (such as 'NFL' or 'Premier League (England)'), "
        "which reads that day from the league's season results or fixtures."
    )


async def _season_url_for(resolved: str, target: date) -> tuple[Optional[str], Optional[str]]:
    """(season base URL, season name) of the league season that contains target."""
    from ..seasons import CALENDAR, archive_name_for, format_from_archive
    from .results import archive_seasons

    seasons = await archive_seasons(resolved)
    names = [item.name for item in seasons]
    fmt = format_from_archive(names)
    if fmt is None:
        return None, None
    start_year = target.year if fmt == CALENDAR else (target.year if target.month >= 7 else target.year - 1)
    name = archive_name_for(names, start_year, fmt)
    if not name:
        return None, None
    url = next((item.url for item in seasons if item.name == name), None)
    if not url:
        return None, name
    from urllib.parse import urljoin

    return urljoin(settings.base_url, url).rstrip("/") + "/", name


async def _league_day(
    resolved: str,
    target: date,
    wanted_status: str,
    timezone: Optional[str],
    off: int,
    lim: Optional[int],
    compact: bool,
    day_filter,
) -> MatchCollection:
    """A date outside the day picker: that league's season list for the date."""
    base, season_name = await _season_url_for(resolved, target)
    notes: list[str] = []
    if base is None:
        base = _league_url(resolved, "current", "")
        notes.append("The season for that date could not be found in the league's archive; the current season was read.")
    else:
        notes.append(f"Read {season_name} ({base}).")
    now = today(timezone)
    tabs = []
    if target <= now:
        tabs.append("results")
    if target >= now:
        tabs.append("fixtures")
    keep_status = None if wanted_status == "all" else wanted_status
    pages: list[MatchCollection] = []
    errors: list[str] = []
    for tab in tabs:
        try:
            pages.append(
                await read_list(
                    f"{base}{tab}/",
                    tab,
                    offset=off,
                    limit=lim,
                    date_from=target.isoformat(),
                    date_to=target.isoformat(),
                    compact=compact,
                    timezone=timezone,
                    newest_first=(tab == "results"),
                    keep_status=keep_status,
                    notes=list(notes),
                )
            )
        except BusyError:
            raise
        except LoadFailed as exc:
            errors.append(f"{tab}: {exc.reason}")
    if not pages:
        raise LoadFailed("Failed to load the day listing for that league.", reason="source-refused")
    page = pages[0]
    for extra in pages[1:]:
        page.items.extend(extra.items)
        page.returned = len(page.items)
        page.has_more = bool(page.has_more or extra.has_more)
        if extra.status == "ok":
            page.status, page.reason = "ok", None
    page.errors.extend(errors)
    if errors and page.status == "ok":
        page.status, page.reason = "partial", "section-failed"
    if page.status == "empty":
        page.reason = "no-matches-scheduled"
    return page


def _label_matches(label: Optional[str], target: date) -> bool:
    if not label:
        return False
    return target.strftime("%B") in label and str(target.day) in label


def _same_day(game: MatchResult, target: date, tz: Optional[str] = None) -> bool:
    parsed = game_day(game, tz) or _parse_game_date(game.date)
    if parsed is None:
        return False
    return parsed == target
