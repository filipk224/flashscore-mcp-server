from __future__ import annotations
import asyncio
from typing import List, Optional
from loguru import logger
from mcp.server.fastmcp import FastMCP
from .models import Sport, Country, League, StandingRow, MatchResult, Fixture, NewsItem, Season
from .extractors import discovery, standings, results, fixtures, news, archive

mcp = FastMCP(
    "flashscore-mcp",
    description="Private production Flashscore sports data MCP. Auto-adapts to slight site changes via multi-selector fallbacks. Hosted on IaaS ready.",
)

@mcp.tool()
async def list_sports() -> List[Sport]:
    """List sports from top menu. Cached + real scrape with fallbacks."""
    return await discovery.list_sports()

@mcp.tool()
async def list_countries(sport: str) -> List[Country]:
    """List countries for a sport from left menu. On-demand."""
    return await discovery.list_countries(sport)

@mcp.tool()
async def list_leagues(sport: str, country: str) -> List[League]:
    """List leagues under sport+country from left menu. On-demand."""
    return await discovery.list_leagues(sport, country)

@mcp.tool()
async def get_standings(league: str, season: str = "current") -> List[StandingRow]:
    """Current/historical standings (MP, W, L, PF, PA, Form). Accepts URL or path."""
    return await standings.get_standings(league, season)

@mcp.tool()
async def get_results_history(
    league: str,
    season: str = "current",
    mode: str = "full",
    limit: Optional[int] = None,
) -> List[MatchResult]:
    """Full results history. mode='minimal' focuses on team names + PF/PA. Handles show-more."""
    return await results.get_results_history(league, season, mode, limit)

@mcp.tool()
async def get_upcoming_fixtures(league: str, limit: int = 20) -> List[Fixture]:
    """Upcoming fixtures for a league."""
    return await fixtures.get_upcoming_fixtures(league, limit)

@mcp.tool()
async def get_news(league: str, limit: int = 10) -> List[NewsItem]:
    """News headings and links."""
    return await news.get_news(league, limit)

@mcp.tool()
async def list_archive_seasons(league: str) -> List[Season]:
    """List previous seasons for archive access."""
    return await archive.list_archive_seasons(league)

@mcp.tool()
async def get_historical_standings(league: str, season: str) -> List[StandingRow]:
    """Standings for a previous season."""
    return await standings.get_standings(league, season)

@mcp.tool()
async def get_historical_results(league: str, season: str, limit: Optional[int] = None) -> List[MatchResult]:
    """Results history for a previous season."""
    return await results.get_results_history(league, season, "full", limit)

async def main() -> None:
    logger.info("Starting private Flashscore MCP Server v{} (IaaS ready, auto-adapt selectors)", __import__("flashscore_mcp").__version__)
    await mcp.run_stdio_async()

if __name__ == "__main__":
    asyncio.run(main())
