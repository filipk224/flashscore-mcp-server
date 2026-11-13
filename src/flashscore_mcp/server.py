"""Production MCP server — no results cache, fast scrapes."""

from __future__ import annotations
import asyncio
from typing import List, Optional

from loguru import logger
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from .models import (
    Sport,
    Country,
    League,
    StandingsPage,
    MatchResult,
    MatchCollection,
    MatchDetail,
    Fixture,
    NewsItem,
    Season,
    OddsPrice,
    LeagueInfo,
)
from .extractors import archive, discovery, fixtures, league_info, news, odds, results, standings
from .extractors import live as live_ext
from .extractors import match as match_ext
from .extractors import team as team_ext
from . import __version__

mcp = FastMCP("flashscore-mcp", version=__version__)


@mcp.custom_route("/", methods=["GET"])
async def root(request: Request) -> PlainTextResponse:
    return PlainTextResponse(
        f"Flashscore MCP Server v{__version__}\n"
        "MCP endpoint: POST /mcp\n"
        "Health: GET /health\n"
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "flashscore-mcp",
            "version": __version__,
            "mcp_endpoint": "/mcp",
            "cache": False,
        }
    )


@mcp.tool()
async def list_sports() -> List[Sport]:
    """Start here: list sports from the top menu, then pass a sport slug to list_countries or get_live_matches."""
    return await discovery.list_sports()


@mcp.tool()
async def list_countries(sport: str) -> List[Country]:
    """List countries for a sport (left menu). Then pass sport and country to list_leagues."""
    return await discovery.list_countries(sport)


@mcp.tool()
async def list_leagues(sport: str, country: str) -> List[League]:
    """List leagues for sport + country (left menu, on-demand). Names include the country, such as 'NPB (Japan)'. Then pass a league name like 'Premier League (England)' to get_league, get_standings, get_results_history, or get_upcoming_fixtures."""
    return await discovery.list_leagues(sport, country)


@mcp.tool()
async def get_standings(league: str, season: str = "current", view: str = "overall") -> StandingsPage:
    """Standings for a league. Shared columns are played, wins, draws, losses, table_points, and form. Other columns are in extras. view is overall, home, or form. league may be a name with its country, such as 'Premier League (England)' or 'NBA (USA)', or a path like football/england/premier-league. For a team's recent games, pass the team to get_team_form."""
    return await standings.get_standings(league, season, view)


@mcp.tool()
async def get_results_history(
    league: str,
    season: str = "current",
    mode: str = "full",
    limit: Optional[int] = None,
    since: Optional[str] = None,
) -> List[MatchResult]:
    """Results with date, teams, status, match_id, match_url, and home_score/away_score. Period scores and notes are in extras. status is live when that game is live. Omit limit and since for the whole tab. limit is the newest N games. since is the oldest date to include. league may be a name with its country, such as 'Premier League (England)' or 'NBA (USA)', or a path like football/england/premier-league. Pass match_id or match_url to get_match for stats, incidents, lineups, and head-to-head."""
    return await results.get_results_history(league, season, mode, limit, since)


@mcp.tool()
async def get_upcoming_fixtures(
    league: str,
    limit: Optional[int] = None,
    since: Optional[str] = None,
) -> List[Fixture]:
    """Scheduled fixtures, each with match_id and match_url. Omit limit and since for every game. limit is the newest N games. since is the oldest date to include. league may be a name with its country, such as 'Premier League (England)' or 'NBA (USA)', or a path like football/england/premier-league. Pass match_id or match_url to get_match for preview details, or use get_h2h / get_team_form for pre-match context."""
    return await fixtures.get_upcoming_fixtures(league, limit, since)


@mcp.tool()
async def get_news(league: str, limit: int = 10) -> List[NewsItem]:
    """News titles and links. league may be a name with its country, such as 'Premier League (England)' or 'NBA (USA)', or a path like football/england/premier-league. For scores and fixtures, use get_results_history or get_upcoming_fixtures instead."""
    return await news.get_news(league, limit)


@mcp.tool()
async def list_archive_seasons(league: str) -> List[Season]:
    """Seasons from league_archive_data, including the winner when the page has one. league may be a name with its country, such as 'Premier League (England)' or 'NBA (USA)', or a path like football/england/premier-league. Then pass a season name to get_historical_standings or get_historical_results."""
    return await archive.list_archive_seasons(league)


@mcp.tool()
async def get_league(league: str) -> LeagueInfo:
    """Sport, country, name, season, url, tabs, and archive seasons for one league. league may be a name with its country, such as 'Premier League (England)' or 'NBA (USA)', or a path like football/england/premier-league. Then call get_standings, get_results_history, or get_upcoming_fixtures for that league."""
    return await league_info.get_league(league)


@mcp.tool()
async def get_odds(league: str, season: str = "current") -> list[OddsPrice]:
    """Default odds tab: bookmaker, side, and price. An archived season with no Odds tab returns an empty list. league may be a name with its country, such as 'Premier League (England)' or 'NBA (USA)', or a path like football/england/premier-league. For a single game's incidents or lineups, pass its match_id from get_results_history to get_match."""
    return await odds.get_odds(league, season)


@mcp.tool()
async def get_historical_standings(league: str, season: str) -> StandingsPage:
    """Standings for a named archive season. The table layout matches the current season. league may be a name with its country, such as 'Premier League (England)' or 'NBA (USA)', or a path like football/england/premier-league. Use list_archive_seasons first if you do not know the season name."""
    return await standings.get_standings(league, season)


@mcp.tool()
async def get_historical_results(
    league: str,
    season: str,
    limit: Optional[int] = None,
    since: Optional[str] = None,
) -> List[MatchResult]:
    """Results for a named archive season, parsed with the same match row as the current season. Each result includes match_id and match_url. Omit limit and since for the whole season. limit is the newest N games. since is the oldest date to include. league may be a name with its country, such as 'Premier League (England)' or 'NBA (USA)', or a path like football/england/premier-league. Pass match_id to get_match for detail."""
    return await results.get_results_history(league, season, "full", limit, since)



@mcp.tool()
async def get_match(match: str, sections: Optional[List[str]] = None) -> MatchDetail:
    """Match detail for a match_id or match_url from get_results_history, get_upcoming_fixtures, get_live_matches, or get_matches_by_day. Optional sections: summary, stats, incidents, lineups, h2h (all of them if omitted). Failed sections are reported in errors and the rest is still returned."""
    return await match_ext.get_match(match, sections)


@mcp.tool()
async def get_live_matches(sport: str, country: Optional[str] = None, league: Optional[str] = None) -> MatchCollection:
    """What's on right now: live games with score, minute, and status. sport is required, such as football. Optionally filter by country or a league name like 'NBA (USA)'. Then pass match_id to get_match for stats, incidents, lineups, or head-to-head."""
    return await live_ext.get_live_matches(sport, country, league)


@mcp.tool()
async def get_h2h(
    match: Optional[str] = None,
    team_a: Optional[str] = None,
    team_b: Optional[str] = None,
    last_n: Optional[int] = None,
    days_back: Optional[int] = None,
    season: Optional[str] = None,
) -> MatchCollection:
    """Head-to-head history. Pass a match_id or match_url (full history from that match's H2H tab), or both team_a and team_b. With team names the search is limited to one season, because two teams meet only a few times in a season. The season follows the league's own format, read from the label under the league name and its archive list: a calendar year such as '2025' for MLS, or a split year such as '2025/2026' for the Premier League. season defaults to the current one; pass '2025', '2025/26' or '2025-2026' (the same labels as the archive page); season='all' reads the full history instead (slower). If the format cannot be read, July to June is assumed and notes say so. The search has a time budget and a page-load cap, so a result with status 'partial' and reason 'timeout' or 'load-cap' (see errors) may be missing meetings, while status 'empty' with reason 'no-meetings' means the teams did not meet in that season. last_n keeps the newest N meetings; days_back keeps meetings in that many days. You can also request h2h as a get_match section."""
    return await match_ext.get_h2h(match, team_a, team_b, last_n, days_back, season)


@mcp.tool()
async def get_matches_by_day(
    sport: str,
    day_offset: Optional[int] = None,
    date: Optional[str] = None,
    status: str = "all",
    league: Optional[str] = None,
) -> MatchCollection:
    """List a day's games for a sport without knowing the league first. day_offset is 0 for today, -1 for yesterday, 1 for tomorrow; date is YYYY-MM-DD. status is all, live, finished, or scheduled. Optionally filter by a league name like 'Premier League (England)'. Then pass match_id to get_match."""
    return await live_ext.get_matches_by_day(sport, day_offset, date, status, league)


@mcp.tool()
async def get_team_form(team: str, last_n: int = 10) -> MatchCollection:
    """Recent results for match-preview context. team may be a Flashscore team URL or path such as /team/arsenal/hA1Zm19f/, or a team name. last_n is how many recent games to return. Pass a match_id from those games to get_match."""
    return await team_ext.get_team_form(team, last_n)


async def _amain() -> None:
    logger.info("Starting Flashscore MCP Server v{}", __version__)
    await mcp.run_stdio_async()


def main() -> None:
    """Sync CLI entrypoint used by `uv run flashscore-mcp`."""
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
