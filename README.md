# Flashscore MCP Server (Private Production)

Private production MCP server for structured sports data from www.flashscore.com using Playwright.

## Features
- Sports (top menu) + Countries/Leagues (left menu) on-demand
- News, full results history (PF/PA), fixtures, standings (MP/W/L/PF/PA/Form), archives
- Local stdio + hosted Docker/HTTP
- Production: rate limiting, retries, modular extractors, env config, logging

See PRD.md for details.

## Quick Start
```bash
uv sync
playwright install chromium
uv run flashscore-mcp
```

## Hosted
Use Dockerfile. Configure with .env.

## License
Proprietary - private production use only.
