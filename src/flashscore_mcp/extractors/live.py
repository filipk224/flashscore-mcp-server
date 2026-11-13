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
from .results import _league_url

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


def resolve_day_offset(day_offset: Optional[int], date_str: Optional[str]) -> int:
    if date_str:
        try:
            target = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("date must be YYYY-MM-DD") from exc
        return (target - date.today()).days
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


def _target_date(day_offset: int) -> date:
    return date.today() + timedelta(days=day_offset)


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
) -> MatchCollection:
    sport = normalize_sport(sport)
    wanted_status = normalize_status(status)
    offset = resolve_day_offset(day_offset, date)
    target = _target_date(offset)
    resolved = await _optional_league_path(league, None)

    if abs(offset) <= MAX_PICKER_DAYS:
        day_sport = sport
        if resolved and not resolved.startswith("http"):
            day_sport = resolved.strip("/").split("/")[0] or sport
        url = _sport_day_url(day_sport, offset)
        logger.info("get_matches_by_day url={} offset={} league={}", url, offset, resolved)
        day = await fetch_day(url, offset)
        if offset != 0 and not day.feed and not _label_matches(day.label, target):
            raise LoadFailed(
                f"Could not switch the {day_sport} page to {target.isoformat()} "
                f"(day picker showed {day.label!r}).",
                reason="parse-failed",
            )
        parsed, _rendered = _day_items(day, resolved)
        if day.feed:
            # A day feed also carries late games from the evening before and
            # early ones after midnight; keep only the requested date.
            parsed = [game for game in parsed if _same_day(game, target)]
        items = filter_status(parsed, wanted_status)
        if items:
            return MatchCollection(status="ok", items=items)
        if day.feed or parsed:
            # The day loaded; that league or status simply has no games.
            return MatchCollection(status="empty", reason="no-matches-scheduled", items=[])
        return _collection(day.html, [], "day")

    if resolved:
        results_url = _league_url(resolved, "current", "results")
        fixtures_url = _league_url(resolved, "current", "fixtures")
        logger.info("get_matches_by_day league results={} fixtures={}", results_url, fixtures_url)
        html_parts: list[str] = []
        items: list[MatchResult] = []
        errors: list[str] = []
        for url in (results_url, fixtures_url):
            try:
                html = await fetch_html(url, full=True)
                html_parts.append(html)
                items.extend(parse_matches(html))
            except BusyError:
                raise
            except LoadFailed as exc:
                errors.append(f"{url}: {exc.reason}")
        dated = [game for game in items if _same_day(game, target)]
        dated = filter_status(dated, wanted_status)
        if dated:
            return MatchCollection(
                status="partial" if errors else "ok",
                reason="section-failed" if errors else None,
                items=dated,
                errors=errors,
            )
        html = html_parts[0] if html_parts else ""
        if not html and errors:
            raise LoadFailed("Failed to load day listing for that league.", reason="source-refused")
        if items:
            return MatchCollection(
                status="partial" if errors else "empty",
                reason="section-failed" if errors else "no-matches-scheduled",
                items=[],
                errors=errors,
            )
        empty = _collection(html, [], "day")
        empty.errors = errors
        if errors:
            empty.status = "partial" if empty.status == "ok" else empty.status
        return empty

    raise ValueError(
        f"Flashscore's day picker covers {MAX_PICKER_DAYS} days either side of today. "
        "For an older or later date pass a league, which reads that league's results and fixtures."
    )


def _label_matches(label: Optional[str], target: date) -> bool:
    if not label:
        return False
    return target.strftime("%B") in label and str(target.day) in label


def _same_day(game: MatchResult, target: date) -> bool:
    parsed = _parse_game_date(game.date)
    if parsed is None:
        return False
    return parsed == target
