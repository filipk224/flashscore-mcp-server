"""Upcoming fixtures — no cache. Filter out already-played games."""
from __future__ import annotations
from typing import List
from loguru import logger
from ..browser import browser_manager, safe_goto, click_show_more
from ..models import Fixture
from .parse_util import EXTRACT_MATCHES_JS, is_future, looks_like_team, parse_int, split_datetime
from .results import _league_url

async def get_upcoming_fixtures(league: str, limit: int = 20) -> List[Fixture]:
    url = _league_url(league, "current", "fixtures")
    logger.info("get_upcoming_fixtures url={}", url)
    fixtures: List[Fixture] = []
    seen = set()
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)
        await click_show_more(page, max_clicks=6)
        rows = await page.evaluate(EXTRACT_MATCHES_JS)
    for row in rows:
        home = row.get("home") or ""
        away = row.get("away") or ""
        date, time = split_datetime(row.get("time") or "")
        if not looks_like_team(home) or not looks_like_team(away):
            text = row.get("text") or ""
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            teams = [l for l in lines if looks_like_team(l)]
            if len(teams) >= 2:
                home, away = teams[0], teams[1]
            if not date:
                date, time = split_datetime(lines[0] if lines else "")
        if not looks_like_team(home) or not looks_like_team(away):
            continue
        home_s = parse_int(row.get("home_score") or "")
        away_s = parse_int(row.get("away_score") or "")
        finished = bool(row.get("finished")) or (home_s is not None and away_s is not None)
        if finished:
            continue
        if date and not is_future(date, time):
            continue
        key = (date, time, home, away)
        if key in seen:
            continue
        seen.add(key)
        fixtures.append(Fixture(date=date, time=time, home_team=home, away_team=away))
        if len(fixtures) >= limit:
            break
    logger.info("Returning {} fixtures", len(fixtures))
    return fixtures
