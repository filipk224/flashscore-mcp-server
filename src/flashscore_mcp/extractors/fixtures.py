"""Upcoming fixtures from the shared match-row parser."""
from __future__ import annotations

from typing import List, Optional

from loguru import logger

from ..models import Fixture
from ..parsers.matches import parse_matches
from .fetch import fetch_html
from .results import _league_url
from .window import take_until


async def get_upcoming_fixtures(
    league: str,
    limit: Optional[int] = None,
    since: Optional[str] = None,
) -> List[Fixture]:
    url = _league_url(league, "current", "fixtures")
    logger.info("get_upcoming_fixtures url={} limit={} since={}", url, limit, since)
    # Scheduled rows are only known after parsing, so a raw row count would
    # stop short of the caller's fixture count. Load the tab, then cut.
    games = [
        game
        for game in parse_matches(await fetch_html(url, full=True))
        if game.status == "scheduled"
    ]
    fixtures = [
        Fixture(
            date=game.date,
            time=game.time,
            round=game.round,
            home_team=game.home_team,
            away_team=game.away_team,
        )
        for game in take_until(games, limit=limit, since=since)
    ]
    logger.info("Returning {} fixtures", len(fixtures))
    return fixtures
