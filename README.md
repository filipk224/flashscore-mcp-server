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

### MCP client config example (Claude Desktop / Cursor / Grok Build CLI)
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

Or with Grok Build CLI:
```bash
grok mcp add flashscore -- uv run --directory /path/to/flashscore-mcp-server flashscore-mcp
```

## Connecting to Grok (grok.com Connectors)

Grok supports custom MCP connectors (Bring Your Own MCP).

**Requirement**: The server must be reachable over the public internet via Streamable HTTP or SSE transport.

### Option 1: Hosted deployment (recommended)
1. Deploy using the included `Dockerfile` (Railway, Fly.io, Render, private VPS, etc.).
2. Expose the HTTP/SSE endpoint (the server supports it when run in hosted mode).
3. Go to [https://grok.com/connectors](https://grok.com/connectors)
4. Click **New Connector** → **Custom**
5. Enter:
   - **Name**: Flashscore
   - **Server URL**: `https://your-deployed-url/mcp` (or the SSE/HTTP endpoint your deployment exposes)
6. Save. Grok will discover the tools (`list_sports`, `get_results_history`, `get_standings`, `get_news`, etc.).

### Option 2: Local + Tunnel
1. Run the server locally (stdio is default; for HTTP you may need to adjust the entrypoint or use a wrapper).
2. Expose it with a tunnel:
   ```bash
   # ngrok
   ngrok http 3001   # or whatever port you expose

   # or Cloudflare Tunnel (no account needed for quick tunnels)
   cloudflared tunnel --url http://localhost:3001
   ```
3. Copy the public HTTPS URL and add it as a Custom connector on [https://grok.com/connectors](https://grok.com/connectors).

**Note**: Pure stdio servers work great with Grok Build CLI and other local clients, but the web Connectors UI requires a public URL.

## Hosted Deployment
- Use the included Dockerfile (Playwright base image).
- Supports HTTP/SSE transport for online hosting (Railway, Fly.io, private VPS, etc.).
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
