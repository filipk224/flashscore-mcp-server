# Flashscore MCP Server (Private Production)

Private production MCP server for structured sports data from www.flashscore.com using Playwright.

**Auto-adapts to slight site changes** via multi-selector fallbacks + logging.

**IaaS ready** (Docker + env config for Railway / Fly.io / AWS / DigitalOcean / any container host).

## Features
- Sports (top menu) + Countries/Leagues (left menu) — on-demand
- News, full results history (team + PF/PA), fixtures, standings (MP/W/L/PF/PA/Form), archives
- Local stdio + hosted Docker
- Production: rate limiting, retries, concurrency, modular extractors, multi-selector auto-adapt, caching, logging

## Quick Start
```bash
uv sync
playwright install chromium
uv run flashscore-mcp
```

## IaaS Hosting
```bash
docker build -t flashscore-mcp .
docker run -p 8000:8000 -e FLASHSCORE_HEADLESS=true flashscore-mcp
```
Deploy the Docker image to your preferred IaaS (Railway, Fly, Render, AWS ECS, etc.). Use env vars from `.env.example`. For long-running hosted use, consider adding an HTTP/SSE transport wrapper (FastMCP supports it).

## License
Proprietary — private production use only.
