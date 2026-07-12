# Flashscore MCP Server (Private Production)

Private production MCP for www.flashscore.com.

## Highlights
- Auto-adapts to slight site changes (multi-fallback selectors in config.py)
- **Permanent / long-TTL cache of historical game results** (date + home/away teams + PF/PA). Only newer games are fetched on subsequent calls → huge savings on Apify & cloud.
- Real discovery + standings/results/fixtures/news/archive extractors
- Hosted on **Apify**, any cloud IaaS, and locally

## What get_results_history returns
Exactly: list of games with  
`date`, `home_team`, `away_team`, `home_pf`, `away_pf`

## Caching Policy (Results)
- Past completed games never change → cached permanently (or TTL 30–90+ days)
- First call: full history (with show-more)
- Later calls: pass `since="auto"` or omit → only newer games scraped and appended to cache
- Cache files live in `data/results_*.json`

## Quick Start
```bash
uv sync && playwright install chromium
uv run flashscore-mcp
```

## Hosting
- **Local**: stdio
- **Apify**: use Dockerfile as custom Actor base
- **Cloud IaaS** (Railway, Fly, DO, AWS…): Dockerfile + healthcheck + env vars from .env.example

See PRD.md for full requirements.

## License
Proprietary – private production use only.
