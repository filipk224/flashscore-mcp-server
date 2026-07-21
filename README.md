# Flashscore MCP Server (Private / Production)

**Private production MCP server** for structured sports data extraction from www.flashscore.com using Playwright.

## Features
- Sports discovery via top menu
- Countries & leagues via left menu (on-demand)
- News headings + links
- Full results history (team names + PF/PA)
- Upcoming fixtures
- Current standings (MP, W, L, PF, PA, Form)
- Previous seasons / archives
- Local stdio **and online hosted** (HTTP/SSE + Docker)
- Production-ready: rate limiting, retries, modular extractors, logging, config via env, adaptable selectors

See [PRD.md](PRD.md) for full requirements.

## Quick Start (Local / Production)
```bash
uv sync
playwright install chromium
uv run flashscore-mcp
```

MCP client config example (Claude Desktop / Cursor / custom):
```json
{
  "mcpServers": {
    "flashscore": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/flashscore-mcp-server", "flashscore-mcp"]
    }
  }
}
```

## Hosted Deployment
- Use the included Dockerfile (Playwright base image).
- Supports HTTP/SSE transport for online hosting (Railway, Fly.io, private VPS, Apify, etc.).
- Configure via environment variables (see `.env.example`).
- Rate limiting, concurrency controls, and caching ready for production load.

## Project Structure
```
src/flashscore_mcp/
├── server.py
├── browser.py
├── models.py
├── config.py
└── extractors/
    ├── discovery.py
    ├── standings.py
    ├── results.py
    ├── fixtures.py
    ├── news.py
    └── archive.py
```

## License
Proprietary – Private production use only. All rights reserved.
