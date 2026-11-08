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
from .fetch import fetch_html
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


def _sport_day_url(sport: str, day_offset: int) -> str:
    base = f"{settings.base_url.rstrip('/')}/{quote(sport, safe='-')}/"
    if day_offset == 0:
        return base
    return f"{base}?d={day_offset}"


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
    if resolved:
        url = _league_url(resolved, "current", "")
        logger.info("get_live_matches league url={}", url)
        html = await fetch_html(url, full=True)
        parsed = parse_matches(html)
        items = [game for game in parsed if game.status == "live"]
        return _after_filter(html, items, parsed, "live")

    url = _sport_day_url(sport, 0)
    logger.info("get_live_matches sport url={}", url)
    html = await fetch_html(url, full=True)
    parsed = parse_matches(html)
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

    url = _sport_day_url(sport, offset)
    logger.info("get_matches_by_day url={}", url)
    html = await fetch_html(url, full=True)
    parsed = parse_matches(html)
    items = parsed
    if league:
        items = [game for game in items if matches_league(game, league, resolved)]
    items = filter_status(items, wanted_status)
    return _after_filter(html, items, parsed, "day")


def _same_day(game: MatchResult, target: date) -> bool:
    parsed = _parse_game_date(game.date)
    if parsed is None:
        return False
    return parsed == target
