"""Upcoming fixtures from the shared match-row parser."""
from __future__ import annotations

from typing import List

from loguru import logger

from ..models import Fixture
from ..parsers.matches import parse_matches
from .fetch import fetch_html
from .results import _league_url


async def get_upcoming_fixtures(league: str, limit: int = 20) -> List[Fixture]:
    url = _league_url(league, "current", "fixtures")
    logger.info("get_upcoming_fixtures url={}", url)
    games = parse_matches(await fetch_html(url, show_more=20, until_count=limit))
    fixtures: List[Fixture] = []
    for game in games:
        if game.status != "scheduled":
            continue
        fixtures.append(Fixture(
            date=game.date,
            time=game.time,
            round=game.round,
            home_team=game.home_team,
            away_team=game.away_team,
        ))
        if len(fixtures) >= limit:
            break
    logger.info("Returning {} fixtures", len(fixtures))
    return fixtures
