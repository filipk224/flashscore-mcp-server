"""Production MCP server — no results cache, fast scrapes."""

from __future__ import annotations
import asyncio
from typing import List, Optional

from loguru import logger
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from .models import Sport, Country, League, StandingRow, MatchResult, Fixture, NewsItem, Season
from .extractors import discovery, standings, results, fixtures, news, archive
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
async def get_standings(league: str, season: str = "current") -> List[StandingRow]:
    """Standings: MP, W, L, PF, PA, Form. No cache."""
    return await standings.get_standings(league, season)


@mcp.tool()
async def get_results_history(
    league: str,
    season: str = "current",
    mode: str = "full",
    limit: Optional[int] = None,
    since: Optional[str] = None,
) -> List[MatchResult]:
    """Live results history: date, home_team, away_team, home_pf, away_pf. No cache."""
    return await results.get_results_history(league, season, mode, limit, since)


@mcp.tool()
async def get_upcoming_fixtures(league: str, limit: int = 20) -> List[Fixture]:
    """Upcoming fixtures only (played games filtered out). No cache."""
    return await fixtures.get_upcoming_fixtures(league, limit)


@mcp.tool()
async def get_news(league: str, limit: int = 10) -> List[NewsItem]:
    """News headings + links from the league news tab."""
    return await news.get_news(league, limit)


@mcp.tool()
async def list_archive_seasons(league: str) -> List[Season]:
    """Previous seasons from the archive tab."""
    return await archive.list_archive_seasons(league)


@mcp.tool()
async def get_historical_standings(league: str, season: str) -> List[StandingRow]:
    return await standings.get_standings(league, season)


@mcp.tool()
async def get_historical_results(league: str, season: str, limit: Optional[int] = None) -> List[MatchResult]:
    return await results.get_results_history(league, season, "full", limit)


async def _amain() -> None:
    logger.info("Starting Flashscore MCP Server v{}", __version__)
    await mcp.run_stdio_async()


def main() -> None:
    """Sync CLI entrypoint used by `uv run flashscore-mcp`."""
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
