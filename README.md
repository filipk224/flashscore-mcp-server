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

Workflow: `.github/workflows/deploy-rumble-cloud.yml`

On every push to `main` (or manual run) it:

1. Builds the image and pushes to `ghcr.io/filipk224/flashscore-mcp-server:latest`
2. SSHs into the Rumble Cloud VM
3. **Installs Docker automatically if it is not present**
4. Creates `/opt/flashscore-mcp/docker-compose.yml` if missing
5. Pulls the image and starts/recreates the container

### One-time GitHub setup

**Secrets** (Settings → Secrets and variables → Actions → Secrets):

| Secret | Required | Description |
|--------|----------|-------------|
| `RUMBLE_SSH_HOST` | Yes | Public IP or hostname of the Rumble Cloud VM |
| `RUMBLE_SSH_USER` | Yes | SSH username (e.g. `ubuntu`) |
| `RUMBLE_SSH_PRIVATE_KEY` | Yes | Full private key (PEM) |
| `RUMBLE_SSH_PORT` | No | SSH port (default 22) |
| `GHCR_PULL_TOKEN` | No | Only needed if the GHCR package stays **private**. A classic PAT with `read:packages` |

**Variable** (Settings → Secrets and variables → Actions → Variables):

| Variable | Value |
|----------|-------|
| `ENABLE_RUMBLE_DEPLOY` | `true` |

### GHCR package visibility (important without a pull token)

Rumble Cloud VMs have no built-in “pull token”. Options:

1. **Recommended without a PAT**: make the package public  
   GitHub → your profile → Packages → `flashscore-mcp-server` → Package settings → Change visibility → Public.  
   Then the VM can `docker pull` without login.

2. **Keep private**: create a classic Personal Access Token with `read:packages`, store it as secret `GHCR_PULL_TOKEN`. The workflow will log the VM into GHCR with it.

### One-time VM notes

- Open **port 8000** in the Rumble Cloud security group / firewall for the VM.
- Prefer ≥ 2 GB RAM (Playwright + Chromium).
- You do **not** need to install Docker yourself; the deploy script does it on first run if missing.
- You do **not** need to create `docker-compose.yml` yourself; the script creates it under `/opt/flashscore-mcp` if absent.

### Verify after deploy

On the VM:
```bash
cd /opt/flashscore-mcp
sudo docker compose ps
sudo docker compose logs -f --tail=100
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

## 5. Connecting from Grok (xAI)

Grok's remote MCP client expects a **publicly reachable HTTPS** endpoint in most cases. A plain `http://PUBLIC_IP:8000/mcp` URL is frequently rejected.

Recommended options:

1. **Cloudflare Tunnel or ngrok** (fastest for testing)  
   On the VM (or any machine that can reach the container):
   ```bash
   # Cloudflare quick tunnel (no account required for temporary URL)
   cloudflared tunnel --url http://127.0.0.1:8000
   # Use the https://*.trycloudflare.com URL that is printed as the Grok connector URL
   ```
   Or with ngrok: `ngrok http 8000` and use the `https://...ngrok-free.app` URL.

2. **TLS reverse proxy** (Caddy / nginx) in front of the container if you have a domain pointed at the Rumble IP.

3. **Apify Standby** path (already HTTPS) if you prefer the Apify deployment.

The server itself is already configured with:
- `stateless_http=True`
- `json_response=True`
- CORS that exposes `Mcp-Session-Id`

These settings maximise compatibility with Grok, Claude, Cursor and other remote clients.

After a successful deploy the workflow prints the current `PUBLIC_IP` and a clear note about the HTTPS requirement. Check the GitHub Actions log for the latest run.

## Project Structure
```
.github/workflows/
  deploy-rumble-cloud.yml    # CI/CD → GHCR + Rumble Cloud VM (auto Docker install)
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
