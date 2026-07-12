"""Production MCP server - IaaS ready (stdio + future HTTP/SSE)."""

from __future__ import annotations
import asyncio
from typing import List, Optional
from loguru import logger
from mcp.server.fastmcp import FastMCP
from .models import Sport, Country, League, StandingRow, MatchResult, Fixture, NewsItem, Season
from .extractors import discovery, standings, results, fixtures, news, archive

mcp = FastMCP(
    "flashscore-mcp",
    description="Private production Flashscore sports data MCP (adaptable extractors, IaaS ready)",
)


@mcp.tool()
async def list_sports() -> List[Sport]:
    """List all sports from top menu. Auto-adapts via fallback selectors + cache."""
    return await discovery.list_sports()


@mcp.tool()
async def list_countries(sport: str) -> List[Country]:
    """List countries for a sport (left menu). Resilient selectors."""
    return await discovery.list_countries(sport)


@mcp.tool()
async def list_leagues(sport: str, country: str) -> List[League]:
    """List leagues for sport+country (left menu). On-demand ready."""
    return await discovery.list_leagues(sport, country)


@mcp.tool()
async def get_standings(league: str, season: str = "current") -> List[StandingRow]:
    """Current or historical standings (MP, W, L, PF, PA, Form)."""
    return await standings.get_standings(league, season)


@mcp.tool()
async def get_results_history(
    league: str,
    season: str = "current",
    mode: str = "full",
    limit: Optional[int] = None,
) -> List[MatchResult]:
    """Full results history. mode='minimal' for team+PF/PA only. Handles show-more."""
    return await results.get_results_history(league, season, mode, limit)


@mcp.tool()
async def get_upcoming_fixtures(league: str, limit: int = 20) -> List[Fixture]:
    """Upcoming fixtures."""
    return await fixtures.get_upcoming_fixtures(league, limit)


@mcp.tool()
async def get_news(league: str, limit: int = 10) -> List[NewsItem]:
    """News headings + links."""
    return await news.get_news(league, limit)


@mcp.tool()
async def list_archive_seasons(league: str) -> List[Season]:
    """Previous seasons available."""
    return await archive.list_archive_seasons(league)


@mcp.tool()
async def get_historical_standings(league: str, season: str) -> List[StandingRow]:
    return await standings.get_standings(league, season)


@mcp.tool()
async def get_historical_results(league: str, season: str, limit: Optional[int] = None) -> List[MatchResult]:
    return await results.get_results_history(league, season, "full", limit)


async def main() -> None:
    logger.info("Starting private Flashscore MCP Server v{} (IaaS ready)", __import__("flashscore_mcp").__version__)
    # For IaaS: can switch to mcp.run_sse_async() or similar for HTTP
    await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
