"""Results history extractor with permanent/ long-TTL caching of immutable past games
+ incremental fetch of only newer games. Perfect for Apify / cloud cost savings.

What is returned: list of games with date, home_team, away_team, home_pf, away_pf.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from loguru import logger

from ..browser import browser_manager, safe_goto, find_first_locator, get_all_matching
from ..config import settings
from ..models import MatchResult


def _cache_path(league_key: str, season: str = "current") -> Path:
    safe = league_key.replace("/", "_").replace(":", "_").replace(" ", "_")[:80]
    return Path(settings.hierarchy_cache_path).parent / f"results_{safe}_{season}.json"


def _load_cache(path: Path) -> List[dict]:
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return data.get("games", [])
        except Exception as e:
            logger.warning("Results cache load failed: {}", e)
    return []


def _save_cache(path: Path, games: List[dict]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Sort by date descending if possible
        path.write_text(json.dumps({
            "updated": datetime.utcnow().isoformat(),
            "count": len(games),
            "games": games,
        }, indent=2))
        logger.info("Saved {} games to cache {}", len(games), path.name)
    except Exception as e:
        logger.warning("Results cache save failed: {}", e)


def _latest_date(games: List[dict]) -> Optional[str]:
    dates = [g.get("date") for g in games if g.get("date")]
    if not dates:
        return None
    # Assume YYYY-MM-DD or similar sortable
    return max(dates)


async def get_results_history(
    league: str,
    season: str = "current",
    mode: str = "full",
    limit: Optional[int] = None,
    since: Optional[str] = None,  # date string or "auto" to use cache latest
) -> List[MatchResult]:
    """
    Fetch game results: date, home_team, away_team, home_pf, away_pf.

    Caching strategy (history never changes):
    - Load existing permanent/long-TTL cache of past games.
    - Only scrape newer games (using `since` or auto from cache).
    - Merge new games into cache and return.
    - Recommended: treat history as permanent (no TTL) or TTL >= 30-90 days.
    """
    logger.info("get_results_history league={} season={} mode={} since={}", league, season, mode, since)

    # Resolve key + URL
    if league.startswith("http"):
        league_key = league
        url = league.rstrip("/") + "/results/"
    else:
        league_key = league.strip("/")
        url = f"{settings.base_url}/{league_key}/results/"

    cache_file = _cache_path(league_key, season)
    cached_games = _load_cache(cache_file)

    # Determine since date for incremental
    effective_since = since
    if effective_since == "auto" or (effective_since is None and cached_games):
        effective_since = _latest_date(cached_games)
        if effective_since:
            logger.info("Incremental mode: only fetching games after {}", effective_since)

    # Scrape (full or incremental)
    new_games: List[dict] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)

        # Click show more a few times (more aggressive for first full load)
        clicks = 8 if not cached_games else 3
        for _ in range(clicks):
            more = await find_first_locator(page, settings.selectors["show_more"], timeout=2000)
            if more:
                try:
                    await more.click()
                    await page.wait_for_timeout(900)
                except Exception:
                    break
            else:
                break

        events = await get_all_matching(page, settings.selectors["results_rows"])
        for ev in events:
            try:
                text = await ev.inner_text()
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if len(lines) < 2:
                    continue

                # Parse date, home, away, score
                date = lines[0] if lines else None
                home = "Home"
                away = "Away"
                home_pf = 0
                away_pf = 0

                # Heuristic: find score line
                for l in lines:
                    if "-" in l and any(c.isdigit() for c in l):
                        # possible "1-0" or "TeamA 1-0 TeamB"
                        parts = l.replace("–", "-").split("-")
                        if len(parts) >= 2:
                            try:
                                home_pf = int("".join(filter(str.isdigit, parts[0].split()[-1] if parts[0].split() else parts[0])) or 0)
                                away_pf = int("".join(filter(str.isdigit, parts[1].split()[0] if parts[1].split() else parts[1])) or 0)
                            except Exception:
                                pass
                        break

                # Teams often in separate lines or around score
                if len(lines) >= 3:
                    home = lines[1]
                    away = lines[2]
                # Better: look for team names via sub-elements later

                game = {
                    "date": date,
                    "home_team": home,
                    "away_team": away,
                    "home_pf": home_pf,
                    "away_pf": away_pf,
                }

                # Incremental filter
                if effective_since and date and date <= effective_since:
                    continue  # already have older or equal

                new_games.append(game)
            except Exception:
                continue

    # Merge: existing + new (dedup by date+home+away roughly)
    existing_keys = {(g.get("date"), g.get("home_team"), g.get("away_team")) for g in cached_games}
    merged = list(cached_games)
    added = 0
    for g in new_games:
        key = (g.get("date"), g.get("home_team"), g.get("away_team"))
        if key not in existing_keys:
            merged.append(g)
            existing_keys.add(key)
            added += 1

    if added or not cached_games:
        _save_cache(cache_file, merged)

    # Convert to models, apply limit
    results = [
        MatchResult(
            date=g.get("date"),
            home_team=g.get("home_team", ""),
            away_team=g.get("away_team", ""),
            home_pf=g.get("home_pf", 0),
            away_pf=g.get("away_pf", 0),
        )
        for g in merged
    ]

    # Newest first roughly
    results = results[::-1] if results else results
    if limit:
        results = results[:limit]

    logger.info("Returning {} results ({} new added to cache)", len(results), added)
    return results
