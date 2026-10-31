"""Stop a newest-first game list at the caller's limit or date. No other cap."""
from __future__ import annotations

import re
from typing import Optional, Sequence, TypeVar

from loguru import logger

T = TypeVar("T")

_DATE = re.compile(r"(\d{1,2})\.(\d{1,2})\.?(?:(\d{2,4}))?")
_SYNTHETIC_YEAR = 4000


def _date_parts(value: Optional[str]) -> Optional[tuple[Optional[int], int, int]]:
    if not value:
        return None
    match = _DATE.search(value.strip())
    if not match:
        return None
    day, month = int(match.group(1)), int(match.group(2))
    if not 1 <= day <= 31 or not 1 <= month <= 12:
        return None
    year = None
    if match.group(3):
        year = int(match.group(3))
        if year < 100:
            year += 2000
    return year, month, day


def _game_date(game: T) -> Optional[str]:
    if isinstance(game, dict):
        return game.get("date") or game.get("Date")
    return getattr(game, "date", None)


def _newest_dated(games: Sequence[T]) -> Optional[tuple[Optional[int], int, int]]:
    for game in games:
        parts = _date_parts(_game_date(game))
        if parts is not None:
            return parts
    return None


def _anchor_year(since_year: Optional[int], since_month: int, since_day: int, games: Sequence[T]) -> int:
    newest = _newest_dated(games)
    if newest and newest[0] is not None:
        return newest[0]
    if since_year is not None:
        if newest and (newest[1], newest[2]) < (since_month, since_day):
            return since_year + 1
        return since_year
    return _SYNTHETIC_YEAR


def _since_boundary(since: str, games: Sequence[T]) -> Optional[tuple[int, int, int]]:
    parts = _date_parts(since)
    if parts is None:
        logger.warning("Ignoring unparsed since={!r}", since)
        return None
    year, month, day = parts
    anchor = _anchor_year(year, month, day, games)
    if year is None:
        year = anchor - 1 if _newest_dated(games) and (_newest_dated(games)[1], _newest_dated(games)[2]) < (month, day) else anchor
    return year, month, day


def take_until(games: Sequence[T], limit: Optional[int] = None, since: Optional[str] = None) -> list[T]:
    """Newest-first games, through the caller's newest-N and oldest date.

    Omit both and the list is unchanged. A game on the since date is included.
    Dates without a year walk backward, wrapping from January to December.
    """
    if limit is not None and limit < 0:
        raise ValueError("limit must be zero or a positive number of games")
    boundary = _since_boundary(since, games) if since else None
    newest = _newest_dated(games)
    cursor_year = newest[0] if newest and newest[0] is not None else _anchor_year(
        boundary[0] if boundary else None,
        boundary[1] if boundary else 1,
        boundary[2] if boundary else 1,
        games,
    )
    previous_month_day: Optional[tuple[int, int]] = None
    chosen: list[T] = []
    for game in games:
        if limit is not None and len(chosen) >= limit:
            break
        if boundary is not None:
            parts = _date_parts(_game_date(game))
            if parts is not None:
                year, month, day = parts
                if year is None:
                    if previous_month_day is not None and (month, day) > previous_month_day:
                        cursor_year -= 1
                    year = cursor_year
                else:
                    cursor_year = year
                previous_month_day = (month, day)
                if (year, month, day) < boundary:
                    break
        chosen.append(game)
    return chosen
