# Flashscore MCP Server (Private / Production)

**Private production MCP server** for structured sports data extraction from www.flashscore.com using Playwright.

Ready for **Apify Actor** deployment (Standby mode + Streamable HTTP MCP endpoint).

## Features
- Sports discovery via top menu
- Countries & leagues via left menu (on-demand)
- News headings + links
- Full results history (team names + PF/PA)
- Upcoming fixtures
- Current standings (MP, W, L, PF, PA, Form)
- Previous seasons / archives
- Local stdio **and** Apify hosted (HTTP/SSE + Standby)
- Production-ready: rate limiting, retries, modular extractors, logging, config via env, adaptable selectors

See [PRD.md](PRD.md) for full requirements.

## Apify Deployment (recommended)

The project is structured as an Apify Actor:

- `.actor/actor.json` – metadata + `usesStandbyMode: true` + `webServerMcpPath: "/mcp"`
- `Dockerfile` – based on `apify/actor-python-playwright`
- `src/main.py` – starts FastMCP over Streamable HTTP on the Actor web-server port
- `requirements.txt` – Apify SDK + FastMCP + Playwright + deps

### Deploy steps
1. Install [Apify CLI](https://docs.apify.com/cli) and log in: `apify login`
2. From the project root: `apify push`
3. Enable Standby in the Actor settings (or it is already declared in actor.json)
4. Clients connect to `https://<your-actor-id>.apify.actor/mcp` (with Apify token)

### Local run (stdio)
```bash
uv sync
playwright install chromium
uv run flashscore-mcp
```

MCP client config example:
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

## Project Structure
```
.actor/
  actor.json
  INPUT_SCHEMA.json
src/
  main.py                 # Apify entrypoint
  flashscore_mcp/
    server.py
    browser.py
    models.py
    config.py
    extractors/
Dockerfile
requirements.txt
pyproject.toml
README.md
PRD.md
```

## License
Proprietary – Private production use only. All rights reserved.
