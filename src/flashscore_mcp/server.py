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
    Fixture,
    NewsItem,
    Season,
    OddsPrice,
    LeagueInfo,
)
from .extractors import archive, discovery, fixtures, league_info, news, odds, results, standings
from . import __version__

mcp = FastMCP("flashscore-mcp")


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
    """List sports from the top menu."""
    return await discovery.list_sports()


@mcp.tool()
async def list_countries(sport: str) -> List[Country]:
    """List countries for a sport (left menu)."""
    return await discovery.list_countries(sport)


@mcp.tool()
async def list_leagues(sport: str, country: str) -> List[League]:
    """List leagues for sport + country (left menu, on-demand)."""
    return await discovery.list_leagues(sport, country)


@mcp.tool()
async def get_standings(league: str, season: str = "current", view: str = "overall") -> StandingsPage:
    """Standings for a league. Shared columns are played, wins, draws, losses, table_points, and form. Other columns are in extras. view is overall, home, or form."""
    return await standings.get_standings(league, season, view)


@mcp.tool()
async def get_results_history(
    league: str,
    season: str = "current",
    mode: str = "full",
    limit: Optional[int] = None,
    since: Optional[str] = None,
) -> List[MatchResult]:
    """Results with date, teams, status, and home_score/away_score. Period scores and notes are in extras. status is live when that game is live."""
    return await results.get_results_history(league, season, mode, limit, since)


@mcp.tool()
async def get_upcoming_fixtures(league: str, limit: int = 20) -> List[Fixture]:
    """Fixtures. Rows with a dash score."""
    return await fixtures.get_upcoming_fixtures(league, limit)


@mcp.tool()
async def get_news(league: str, limit: int = 10) -> List[NewsItem]:
    """News titles and links."""
    return await news.get_news(league, limit)


@mcp.tool()
async def list_archive_seasons(league: str) -> List[Season]:
    """Seasons from league_archive_data, including the winner when the page has one."""
    return await archive.list_archive_seasons(league)


@mcp.tool()
async def get_league(league: str) -> LeagueInfo:
    """Sport, country, name, season, url, tabs, and archive seasons for one league."""
    return await league_info.get_league(league)


@mcp.tool()
async def get_odds(league: str, season: str = "current") -> list[OddsPrice]:
    """Default odds tab: bookmaker, side, and price. An archived season with no Odds tab returns an empty list."""
    return await odds.get_odds(league, season)


@mcp.tool()
async def get_historical_standings(league: str, season: str) -> StandingsPage:
    """Standings for a named archive season. The table layout matches the current season."""
    return await standings.get_standings(league, season)


@mcp.tool()
async def get_historical_results(league: str, season: str, limit: Optional[int] = None) -> List[MatchResult]:
    """Results for a named archive season, parsed with the same match row as the current season."""
    return await results.get_results_history(league, season, "full", limit)


async def _amain() -> None:
    logger.info("Starting Flashscore MCP Server v{}", __version__)
    await mcp.run_stdio_async()


def main() -> None:
    """Sync CLI entrypoint used by `uv run flashscore-mcp`."""
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
