# Flashscore MCP Server (Private / Production)

**Private production MCP server** for structured sports data extraction from www.flashscore.com using Playwright.

Supports:
- **Local stdio** (for desktop MCP clients)
- **Apify Actor** (Standby + Streamable HTTP, automated deploy via GitHub Actions on every push to `main`)
- **General IaaS / cloud** (Railway, Fly.io, Render, DigitalOcean, AWS, Cloud Run, etc.)
- **Rumble Cloud** (automated deploy via GitHub Actions on every push to `main`)
- **Cloudflare Quick Tunnel** (`cloudflared` sidecar → `https://*.trycloudflare.com`) for HTTPS in front of the VM

## Features
- Sports discovery via top menu
- Countries & leagues via left menu (on-demand), with names like `NPB (Japan)`
- League tools accept a name with its country (for example `Premier League (England)` or `NBA (USA)`) as well as a Flashscore path
- News headings + links
- Full results history (team names, scores, and extras)
- Upcoming fixtures
- Current standings (played, wins, losses, points, form)
- Previous seasons / archives
- Modular extractors, a parser adapter for renamed site classes, and checks that tell empty pages apart from failed loads
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
- `docker-compose.yml` – local container testing (+ optional `tunnel` profile)
- `.env.example` – environment variable reference

### Build & run locally with Docker
```bash
export FLASHSCORE_MCP_TOKEN="$(openssl rand -hex 32)"
docker compose up --build
# MCP endpoint: http://127.0.0.1:8000/mcp
# Header: Authorization: Bearer $FLASHSCORE_MCP_TOKEN
```

### Deploy to common platforms

**Railway / Render / Fly.io / DigitalOcean / AWS / Cloud Run**
- Connect the repository; the Dockerfile is auto-detected on most platforms.
- Set environment variables from `.env.example`.

---

## 3. Rumble Cloud – automated deploy on push to main

Workflow: `.github/workflows/deploy-rumble-cloud.yml`

On every push to `main` (or manual run) it:

1. Builds the image and pushes to `ghcr.io/filipk224/flashscore-mcp-server:latest`
2. SSHs into the Rumble Cloud VM
3. **Installs Docker automatically if it is not present**
4. Writes `/opt/flashscore-mcp/docker-compose.yml` and `.env`
5. Pulls the image and starts/recreates the MCP container
6. Starts `cloudflare/cloudflared` as a sidecar using a **free Quick Tunnel** (`trycloudflare.com`). No Cloudflare account, DNS zone, or token is required.

### One-time GitHub setup

**Secrets** (Settings → Secrets and variables → Actions → Secrets):

| Secret | Required | Description |
|--------|----------|-------------|
| `RUMBLE_SSH_HOST` | Yes | Public IP or hostname of the Rumble Cloud VM |
| `RUMBLE_SSH_USER` | Yes | SSH username (e.g. `ubuntu`) |
| `RUMBLE_SSH_PRIVATE_KEY` | Yes | Full private key (PEM) |
| `RUMBLE_SSH_PORT` | No | SSH port (default 22) |
| `GHCR_PULL_TOKEN` | No | Only needed if the GHCR package stays **private**. A classic PAT with `read:packages` |
| `FLASHSCORE_MCP_TOKEN` | Yes | Shared bearer token (at least 16 characters). The HTTP server will not start without it. Generate with `openssl rand -hex 32`. |

**Variable** (Settings → Secrets and variables → Actions → Variables):

| Variable | Value |
|----------|-------|
| `ENABLE_RUMBLE_DEPLOY` | `true` |

### Cloudflare Quick Tunnel (`trycloudflare.com`)

On each deploy the sidecar runs:

```bash
cloudflared tunnel --no-autoupdate --url http://flashscore-mcp:8000
```

Workflow logs print `TRYCLOUDFLARE_URL=https://<random>.trycloudflare.com` and `MCP_ENDPOINT=https://<random>.trycloudflare.com/mcp`.

That hostname is **ephemeral**: it changes whenever the `flashscore-mcp-tunnel` container is recreated (every push to `main`). Point Grok at the latest `MCP_ENDPOINT` from the Actions log.

The Quick Tunnel stays free and only provides HTTPS. It does not authenticate callers. Every request, including `/health` and `/mcp`, must include `Authorization: Bearer <FLASHSCORE_MCP_TOKEN>`. Port 8000 is bound to localhost on the VM; the tunnel reaches the container over the Docker network, so the raw port is not published on the public internet.

### GHCR package visibility

Rumble Cloud VMs have no built-in “pull token”. Options:

1. **Recommended without a PAT**: make the package public  
   GitHub → Packages → `flashscore-mcp-server` → Package settings → Public.
2. **Keep private**: classic PAT with `read:packages` as `GHCR_PULL_TOKEN`.

### Verify after deploy

On the VM:
```bash
cd /opt/flashscore-mcp
sudo docker compose --env-file .env ps
sudo docker compose --env-file .env logs -f --tail=100
```

Local (on the VM): `http://127.0.0.1:8000/mcp`  
Public HTTPS: `https://<random>.trycloudflare.com/mcp` (from the deploy job’s `MCP_ENDPOINT`)  
Both require `Authorization: Bearer <FLASHSCORE_MCP_TOKEN>`.

---

## 4. Apify Deployment

The project remains fully compatible with Apify Actors.

- `.actor/actor.json` – metadata + `usesStandbyMode: true` + `webServerMcpPath: "/mcp"`
- `src/main.py` – Apify-specific entrypoint

The Apify entrypoint serves Streamable HTTP with `stateless_http` and `json_response` enabled, matching the generic IaaS server. Authentication is the platform Apify token, not `FLASHSCORE_MCP_TOKEN`. The Standby idle timeout is configured in the Actor Standby settings in Apify Console; the optional `idleTimeoutSecs` input is informational only.

### Automated deploy

On every push to `main`, [`.github/workflows/deploy-apify.yml`](.github/workflows/deploy-apify.yml) runs the official [`apify/push-actor-action`](https://github.com/apify/push-actor-action). That is the same as `apify push`: it uploads the Actor (using `Dockerfile.apify` from `.actor/actor.json`) and waits for the platform build to finish. You can also run **Deploy to Apify** manually from the Actions tab.

1. In [Apify Console](https://console.apify.com/), go to Settings → API & Integrations and create an API token
2. In this GitHub repo, add a secret named `APIFY_TOKEN` (Settings → Secrets and variables → Actions)
3. Push to `main`, or dispatch the workflow by hand

The first successful push creates or updates the Actor named `flashscore-mcp-server` on your Apify account.

### Manual deploy
1. Install [Apify CLI](https://docs.apify.com/cli) and log in: `apify login`
2. From the project root: `apify push`
3. Enable Standby in the Actor settings and set the idle timeout there if you want the instance to stay warm longer
4. Clients connect to `https://<your-actor-id>.apify.actor/mcp` (with an Apify token)

---

## 5. Connecting from Grok (xAI)

Grok's remote MCP client expects a **publicly reachable HTTPS** endpoint. Use the `MCP_ENDPOINT` printed by the latest Rumble deploy (`https://<random>.trycloudflare.com/mcp`) and send the shared bearer token:

```json
{
  "mcpServers": {
    "flashscore": {
      "url": "https://<random>.trycloudflare.com/mcp",
      "headers": {
        "Authorization": "Bearer <FLASHSCORE_MCP_TOKEN>"
      }
    }
  }
}
```

The server is configured with `stateless_http=True`, `json_response=True`, CORS that exposes `Mcp-Session-Id`, and required bearer authentication.

## Project Structure
```
.github/workflows/
  deploy-apify.yml           # CI/CD → Apify Actor push + build
  deploy-rumble-cloud.yml    # CI/CD → GHCR + Rumble + trycloudflare sidecar
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
