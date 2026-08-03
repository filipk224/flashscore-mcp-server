# Flashscore MCP Server (Private / Production)

**Private production MCP server** for structured sports data extraction from www.flashscore.com using Playwright.

Supports:
- **Local stdio** (for desktop MCP clients)
- **Apify Actor** (Standby + Streamable HTTP)
- **General IaaS / cloud** (Railway, Fly.io, Render, DigitalOcean, AWS, Cloud Run, etc.)

## Features
- Sports discovery via top menu
- Countries & leagues via left menu (on-demand)
- News headings + links
- Full results history (team names + PF/PA) with permanent/long-TTL caching
- Upcoming fixtures
- Current standings (MP, W, L, PF, PA, Form)
- Previous seasons / archives
- Rate limiting, retries, modular extractors, adaptable multi-fallback selectors
- Configurable via environment variables

See [PRD.md](PRD.md) for full requirements.

---

## 1. Local run (stdio)

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

---

## 2. General IaaS / Cloud deployment (recommended for most hosts)

The project is now prepared for any Docker-compatible IaaS platform.

### Key files
- `Dockerfile` – production image (Playwright browsers pre-installed)
- `src/flashscore_mcp/http_server.py` – generic Streamable HTTP entrypoint
- `docker-compose.yml` – local container testing
- `.env.example` – environment variable reference

### Build & run locally with Docker
```bash
docker compose up --build
# MCP endpoint: http://localhost:8000/mcp
```

### Deploy to common platforms

**Railway**
1. Connect the GitHub repository.
2. Railway auto-detects the Dockerfile.
3. Set environment variables from `.env.example` (PORT is usually injected).
4. Add a persistent volume mounted at `/app/data` if you want results cache to survive restarts.
5. Deploy. Endpoint will be `https://<your-app>.up.railway.app/mcp`.

**Fly.io**
```bash
fly launch          # creates fly.toml from Dockerfile
fly volumes create flashscore_data --size 1
# edit fly.toml to mount the volume at /app/data
fly deploy
```

**Render**
1. New → Web Service → connect repo.
2. Runtime: Docker.
3. Set env vars. Add a Disk mounted at `/app/data` for cache persistence.

**DigitalOcean App Platform / AWS ECS / Google Cloud Run / Azure**
- Use the provided Dockerfile.
- Expose port 8000 (or the value of `$PORT`).
- Mount a persistent volume/filesystem at `/app/data` for the results cache.
- Set the environment variables listed in `.env.example`.

### Important production notes
- **Persistent cache**: Historical results are immutable and cached under `/app/data`. Mount a volume there so repeated calls stay cheap and fast.
- **Memory**: Playwright + Chromium typically needs ≥ 1–2 GB. Configure the platform accordingly.
- **Concurrency**: Keep `FLASHSCORE_MAX_CONCURRENT_PAGES` low (1–3) on small instances.
- **Health**: The image includes a HEALTHCHECK that verifies the process is listening on `$PORT`.

---

## 3. Apify Deployment

The project remains fully compatible with Apify Actors.

- `.actor/actor.json` – metadata + `usesStandbyMode: true` + `webServerMcpPath: "/mcp"`
- `src/main.py` – Apify-specific entrypoint (Actor context + HTTP server)
- `Dockerfile` – still based on `apify/actor-python-playwright`

### Deploy steps
1. Install [Apify CLI](https://docs.apify.com/cli) and log in: `apify login`
2. From the project root: `apify push`
3. Enable Standby in the Actor settings (already declared in actor.json)
4. Clients connect to `https://<your-actor-id>.apify.actor/mcp` (with Apify token)

> Note: The default `CMD` in the Dockerfile now points to the generic HTTP server.
> Apify’s platform respects the Actor configuration and can still use `src/main.py`
> when running in Actor mode. You can also override the start command in the Apify console if needed.

---

## Project Structure
```
.actor/
  actor.json
  INPUT_SCHEMA.json
src/
  main.py                      # Apify entrypoint
  flashscore_mcp/
    http_server.py             # Generic IaaS HTTP entrypoint
    server.py                  # FastMCP tools
    browser.py
    models.py
    config.py
    extractors/
Dockerfile
docker-compose.yml
requirements.txt
pyproject.toml
.env.example
README.md
PRD.md
```

## License
Proprietary – Private production use only. All rights reserved.
