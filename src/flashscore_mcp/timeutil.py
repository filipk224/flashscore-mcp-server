"""Times in tool output: always labelled, UTC by default, optionally converted.

Browser pages are opened with timezone UTC, so the date and time Flashscore
renders, and every day boundary it applies, are UTC. Feed rows also carry the
kick-off as a Unix timestamp, which becomes ``kickoff_utc`` (ISO 8601 with Z).

A caller may pass an IANA ``timezone`` such as 'America/New_York'. Then
``date`` and ``time`` are given in that zone, ``kickoff_local`` carries the
offset, and ``timezone`` names the zone; ``kickoff_utc`` stays UTC.
"""
from __future__ import annotations

from datetime import date, datetime, timezone as dt_timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC_NAME = "UTC"
DATE_FMT = "%d.%m.%Y"
TIME_FMT = "%H:%M"


def zone(name: Optional[str]):
    """ZoneInfo for an IANA name; None or 'UTC'/'Z' is UTC. ValueError when unknown."""
    raw = (name or "").strip()
    if not raw or raw.upper() in ("UTC", "Z", "GMT", "ETC/UTC"):
        return dt_timezone.utc
    try:
        return ZoneInfo(raw)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(
            f"Unknown timezone {name!r}. Use an IANA name such as 'America/New_York', "
            "'Europe/London' or 'Australia/Adelaide', or omit it for UTC."
        ) from exc


def zone_name(name: Optional[str]) -> str:
    tz = zone(name)
    return UTC_NAME if tz is dt_timezone.utc else str(tz)


def browser_timezone_id(name: Optional[str]) -> str:
    """Playwright timezone_id for a request (Chromium takes IANA names and 'UTC')."""
    return zone_name(name)


def today(name: Optional[str] = None) -> date:
    """Today's date in the zone (UTC by default), not the host's local date."""
    return datetime.now(zone(name)).date()


def from_ts(ts: Optional[int]) -> Optional[datetime]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=dt_timezone.utc)
    except (OverflowError, OSError, ValueError, TypeError):
        return None


def iso_utc(moment: datetime) -> str:
    return moment.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_utc(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt_timezone.utc)
    except ValueError:
        return None


def parse_day(value: Optional[str]) -> Optional[date]:
    """'2025-09-07', '07.09.2025' or '07.09.25' to a date; None for empty. ValueError when unreadable."""
    raw = (value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unreadable date {value!r}: use YYYY-MM-DD (or DD.MM.YYYY).")


def localize(items: Iterable, name: Optional[str] = None) -> list:
    """Label every row's date/time zone, converting rows with a known kick-off."""
    tz = zone(name)
    label = zone_name(name)
    out = []
    for game in items:
        moment = parse_iso_utc(getattr(game, "kickoff_utc", None))
        update: dict = {"timezone": label}
        if moment is not None:
            local = moment.astimezone(tz)
            update["date"] = local.strftime(DATE_FMT)
            update["time"] = local.strftime(TIME_FMT)
            update["kickoff_local"] = None if tz is dt_timezone.utc else local.isoformat(timespec="minutes")
        else:
            # A row without a timestamp keeps the UTC date/time the page showed.
            update["timezone"] = UTC_NAME if (getattr(game, "date", None) or getattr(game, "time", None)) else None
        out.append(game.model_copy(update=update))
    return out


def game_day(game, name: Optional[str] = None) -> Optional[date]:
    """The row's calendar day in the zone, when its year is known."""
    moment = parse_iso_utc(getattr(game, "kickoff_utc", None))
    if moment is not None:
        return moment.astimezone(zone(name)).date()
    raw = (getattr(game, "date", None) or "").strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None
