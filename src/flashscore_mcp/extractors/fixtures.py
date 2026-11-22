"""Upcoming fixtures, read like results (see listing.py) and kept to scheduled games."""
from __future__ import annotations

from typing import Optional

from loguru import logger

from ..models import MatchCollection
from .resolve import resolve_league_ref
from .results import _league_url, read_list


async def get_upcoming_fixtures(
    league: str,
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
    if since and not date_from:
        from ..timeutil import parse_day

        try:
            parse_day(since)
        except ValueError as exc:
            raise ValueError("since must be a full date such as 2026-09-10 (or use date_from).") from exc
        date_from = since
    league = await resolve_league_ref(league)
    url = _league_url(league, "current", "fixtures")
    logger.info("get_upcoming_fixtures url={} offset={} limit={} since={}", url, offset, limit, since)
    # Fixtures run oldest first, so date_from/since only skip early rows and
    # date_to is where loading can stop.
    return await read_list(
        url,
        "fixtures",
        offset=offset,
        limit=limit,
        date_from=date_from,
        date_to=date_to,
        round=round,
        stage=stage,
        compact=compact,
        timezone=timezone,
        newest_first=False,
        keep_status="scheduled",
    )
