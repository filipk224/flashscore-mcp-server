"""Upcoming fixtures from the shared match-row parser."""
from __future__ import annotations

from typing import List, Optional

from loguru import logger

from ..models import Fixture
from ..parsers.adapter import count_match_hints
from ..parsers.matches import parse_matches
from .fetch import fetch_html
from .page_status import empty_or_raise
from .resolve import resolve_league_ref
from .results import _league_url
from .window import take_until


async def get_upcoming_fixtures(
    league: str,
    limit: Optional[int] = None,
    since: Optional[str] = None,
) -> List[Fixture]:
    league = await resolve_league_ref(league)
    url = _league_url(league, "current", "fixtures")
    logger.info("get_upcoming_fixtures url={} limit={} since={}", url, limit, since)
    # Scheduled rows are only known after parsing, so a raw row count would
    # stop short of the caller's fixture count. Load the tab, then cut.
    html = await fetch_html(url, full=True)
    parsed = parse_matches(html)
    games = [game for game in parsed if game.status == "scheduled"]
    fixtures = [
        Fixture(
            date=game.date,
            time=game.time,
            round=game.round,
            home_team=game.home_team,
            away_team=game.away_team,
            url=game.match_url,
            match_id=game.match_id,
            match_url=game.match_url,
        )
        for game in take_until(games, limit=limit, since=since)
    ]
    if not parsed:
        empty_or_raise(html, "fixtures", fixtures, raw_hints=count_match_hints(html))
    logger.info("Returning {} fixtures", len(fixtures))
    return fixtures
