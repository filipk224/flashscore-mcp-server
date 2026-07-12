# Flashscore MCP Server (Private Production / IaaS)

Private production-ready MCP server for www.flashscore.com sports data.

## Key Features
- **Auto-adapts** to slight site changes via multi-fallback selectors (config.py)
- Real extractors for discovery (top menu sports, left menu countries/leagues)
- Standings, results history (PF/PA mode + show-more), fixtures, news, archives
- Caching, rate limiting, retries, logging
- **IaaS ready**: Docker, healthcheck, env config, concurrent controls

## Quick Start (Local)
```bash
uv sync
playwright install chromium
uv run flashscore-mcp
```

## IaaS Hosting (Railway / Fly / DO / AWS etc.)
1. Use the Dockerfile
2. Set env vars from `.env.example`
3. For HTTP/SSE transport (recommended for hosted), extend server.py with `mcp.run_sse_async()` or platform-specific
4. Scale concurrency carefully (browser RAM)

## Config
All selectors live in `src/flashscore_mcp/config.py` as lists of fallbacks.  
Update the lists when Flashscore changes class names — the first working selector is used automatically.

## Tools
list_sports, list_countries, list_leagues, get_standings, get_results_history, get_upcoming_fixtures, get_news, list_archive_seasons + historical variants.

## License
Proprietary – private production use only.
