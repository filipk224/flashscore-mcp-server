"""Production MCP server - IaaS + Apify ready, with results caching."""

from __future__ import annotations
import asyncio
from typing import List, Optional
from loguru import logger
from fastmcp import FastMCP
from .models import Sport, Country, League, StandingRow, MatchResult, Fixture, NewsItem, Season
from .extractors import discovery, standings, results, fixtures, news, archive

mcp = FastMCP("flashscore-mcp")


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
    since: Optional[str] = None,
) -> List[MatchResult]:
    """
    Full game results history.

    Returns games with: date, home_team, away_team, home_pf (points for home), away_pf (points for away).

    Caching (history never changes):
    - Past games are cached permanently / long-TTL.
    - Use since="auto" (or omit after first run) to only fetch newer games and append to cache.
    - Greatly reduces cost on Apify / cloud IaaS for repeated updates.
    """
    return await results.get_results_history(league, season, mode, limit, since)


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
    logger.info("Starting private Flashscore MCP Server v{} (Apify + IaaS + local ready)", __import__("flashscore_mcp").__version__)
    await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
