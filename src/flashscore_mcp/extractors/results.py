"""Results history — no cache. Live scrape every call. Fast, hardened parse."""
from __future__ import annotations
from typing import List, Optional
from loguru import logger
from ..browser import browser_manager, safe_goto, click_show_more
from ..config import settings
from ..models import MatchResult
from .parse_util import EXTRACT_MATCHES_JS, looks_like_team, parse_int, parse_score_pair, split_datetime

def _league_url(league: str, season: str, tab: str) -> str:
    if league.startswith("http"):
        base = league.rstrip("/")
        for suffix in ("/results", "/fixtures", "/standings", "/news", "/archive"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
        return f"{base}/{tab}/"
    key = league.strip("/")
    if season and season not in ("current",) and season.isdigit() and f"-{season}" not in key:
        parts = key.split("/")
        parts[-1] = f"{parts[-1]}-{season}"
        key = "/".join(parts)
    return f"{settings.base_url}/{key}/{tab}/"

def _row_to_result(row: dict) -> Optional[MatchResult]:
    home = row.get("home") or ""
    away = row.get("away") or ""
    home_pf = parse_int(row.get("home_score") or "")
    away_pf = parse_int(row.get("away_score") or "")
    date, time = split_datetime(row.get("time") or "")
    if (not looks_like_team(home) or not looks_like_team(away) or home_pf is None or away_pf is None):
        text = row.get("text") or ""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for line in lines:
            pair = parse_score_pair(line)
            if pair:
                home_pf, away_pf = pair
                break
        teams = [l for l in lines if looks_like_team(l)]
        if len(teams) >= 2:
            home, away = teams[0], teams[1]
        if not date:
            date, time = split_datetime(lines[0] if lines else "")
    if not looks_like_team(home) or not looks_like_team(away):
        return None
    if home_pf is None or away_pf is None:
        return None
    return MatchResult(date=date or time, home_team=home, away_team=away, home_pf=home_pf, away_pf=away_pf)

async def get_results_history(league: str, season: str = "current", mode: str = "full", limit: Optional[int] = None, since: Optional[str] = None) -> List[MatchResult]:
    url = _league_url(league, season, "results")
    logger.info("get_results_history url={} limit={}", url, limit)
    results: List[MatchResult] = []
    seen = set()
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)
        await click_show_more(page, max_clicks=14)
        rows = await page.evaluate(EXTRACT_MATCHES_JS)
    for row in rows:
        parsed = _row_to_result(row)
        if not parsed:
            continue
        if since and parsed.date and parsed.date <= since:
            continue
        key = (parsed.date, parsed.home_team, parsed.away_team, parsed.home_pf, parsed.away_pf)
        if key in seen:
            continue
        seen.add(key)
        results.append(parsed)
    if limit:
        results = results[:limit]
    logger.info("Returning {} results (no cache)", len(results))
    return results
