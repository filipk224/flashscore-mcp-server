# Flashscore MCP Server (Private / Production)

**Private production MCP server** for structured sports data extraction from www.flashscore.com using Playwright.

Supports:
- **Local stdio** (for desktop MCP clients)
- **Apify Actor** (Standby + Streamable HTTP)
- **General IaaS / cloud** (Railway, Fly.io, Render, DigitalOcean, AWS, Cloud Run, etc.)
- **Rumble Cloud** (automated deploy via GitHub Actions on every push to `main`)

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

## 2. General IaaS / Cloud deployment

The project is prepared for any Docker-compatible IaaS platform.

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

**Railway / Render / Fly.io / DigitalOcean / AWS / Cloud Run**
- Connect the repository; the Dockerfile is auto-detected on most platforms.
- Set environment variables from `.env.example`.
- Mount a persistent volume at `/app/data` for the results cache.

---

## 3. Rumble Cloud – automated deploy on push to main

A GitHub Actions workflow (`.github/workflows/deploy-rumble-cloud.yml`) builds the Docker image, pushes it to GitHub Container Registry (`ghcr.io/filipk224/flashscore-mcp-server`), and deploys it to a Rumble Cloud VM over SSH on every push to `main`.

### One-time setup on Rumble Cloud

1. Create a VM (Ubuntu 22.04/24.04 recommended) with at least 2 GB RAM.
2. Install Docker and Docker Compose plugin:
   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker $USER
   # log out / in, then verify: docker compose version
   ```
3. Open port 8000 (or your chosen port) in the Rumble Cloud security group / firewall for the VM.
4. (Optional) Point a domain or floating IP to the VM.

### One-time setup in GitHub repository secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Required | Description |
|--------|----------|-------------|
| `RUMBLE_SSH_HOST` | Yes | Public IP or hostname of the Rumble Cloud VM |
| `RUMBLE_SSH_USER` | Yes | SSH username (e.g. `ubuntu`) |
| `RUMBLE_SSH_PRIVATE_KEY` | Yes | Private key that can log in as that user (full PEM content) |
| `RUMBLE_SSH_PORT` | No | SSH port (default 22) |
| `GHCR_PULL_TOKEN` | Recommended | GitHub PAT with `read:packages` scope so the VM can pull the image. If omitted the workflow falls back to `GITHUB_TOKEN` (may have limited lifetime). |

After the secrets are set, every push to `main` will:

1. Build the image
2. Push `ghcr.io/filipk224/flashscore-mcp-server:latest` (and a sha-tagged version)
3. SSH into the VM, pull the new image, and recreate the container

The workflow also creates a minimal `docker-compose.yml` on the VM on first run (under `/opt/flashscore-mcp`). You can customise that file later; subsequent deploys only pull and restart.

You can also trigger a deploy manually from the **Actions** tab (`workflow_dispatch`).

### Verifying the deployment

On the VM:
```bash
cd /opt/flashscore-mcp
docker compose ps
docker compose logs -f
```

MCP endpoint: `http://<VM-IP-or-domain>:8000/mcp`

---

## 4. Apify Deployment

The project remains fully compatible with Apify Actors.

- `.actor/actor.json` – metadata + `usesStandbyMode: true` + `webServerMcpPath: "/mcp"`
- `src/main.py` – Apify-specific entrypoint

### Deploy steps
1. Install [Apify CLI](https://docs.apify.com/cli) and log in: `apify login`
2. From the project root: `apify push`
3. Enable Standby in the Actor settings
4. Clients connect to `https://<your-actor-id>.apify.actor/mcp` (with Apify token)

---

## Project Structure
```
.github/workflows/
  deploy-rumble-cloud.yml    # CI/CD → GHCR + Rumble Cloud VM
src/
  main.py                      # Apify entrypoint
  flashscore_mcp/
    http_server.py             # Generic IaaS HTTP entrypoint
    server.py
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
