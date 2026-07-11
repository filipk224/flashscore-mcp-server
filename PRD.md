# Flashscore MCP Server - Private Production PRD

**Version:** 0.1 | **Status:** Production Skeleton | **Private**

Private MCP server for Flashscore.com data via Playwright.

**Key Requirements Met:**
- Sports top menu, countries/leagues left menu
- On-demand league choice
- News, results history, fixtures, standings (MP, W, L, PF, PA, Form), archives
- Local + online hosted
- Adaptable to site changes (modular)

Tools: list_sports, list_countries, list_leagues, get_standings, get_results_history, get_upcoming_fixtures, get_news, list_archive_seasons + historical variants.

Architecture: FastMCP + Playwright BrowserManager + modular extractors + Pydantic.
