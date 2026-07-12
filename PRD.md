# Flashscore MCP Server - Private Production PRD

**Version:** 0.1.2  
**Status:** Production Skeleton + Real Extractors + Caching  
**Visibility:** Private / Proprietary  
**Hosting:** Local + Apify + Cloud IaaS

---

## Executive Summary

Private production **Model Context Protocol (MCP) server** for structured sports data from www.flashscore.com using Playwright.

- Sports via **top menu**
- Countries & leagues via **left menu**
- On-demand league selection
- News, full results history, fixtures, standings (MP, W, L, PF, PA, Form), archives
- Multi-fallback selectors for auto-adaptation to slight site changes
- **Persistent caching of historical results** (never change) + incremental updates
- Hosted on **Apify**, cloud IaaS, and locally

---

## Goals
1. Full coverage of sports / countries / leagues
2. Robust Playwright extraction with retries, rate limiting, multi-fallback selectors
3. Clean Pydantic-validated JSON outputs
4. Support current + historical seasons
5. Production deployment: Local + Apify + any cloud IaaS (Docker, healthchecks, env config)
6. Efficient history handling via permanent cache of past games

---

## Scope

### In Scope
- Discovery tools (top menu sports, left menu countries/leagues)
- Standings table
- **Full game results history** — games with: date, home team, away team, points home (home_pf), points away (away_pf)
- Upcoming fixtures
- News headings + links
- Previous seasons / archives
- **Caching strategy for results**:
  - Historical results are immutable → cache permanently (or very long TTL, e.g. 30–90 days or indefinite)
  - On update, only fetch newer games since last known date/game
  - Merge new games into the cache
  - This avoids re-fetching entire history and dramatically reduces load/cost on Apify/cloud
- Modular extractors + config-driven selectors for easy adaptation to site changes
- IaaS readiness (Docker, concurrency limits, logging)

### Out of Scope (Initial)
- Live in-play events
- Detailed match stats / lineups (unless easy)
- Odds
- Login / personalized features

---

## Functional Requirements

### Tools
- `list_sports()` — top menu
- `list_countries(sport)` — left menu
- `list_leagues(sport, country)` — left menu, on-demand
- `get_standings(league, season="current")` — MP, W, L, PF, PA, Form
- `get_results_history(league, season="current", mode="full"|"minimal", limit=None, since=None)`
  - Returns list of games: **date, home_team, away_team, home_pf, away_pf**
  - `mode="minimal"` focuses on exactly those fields
  - Supports `since` (date or last game id) for incremental fetch
  - Uses permanent/ long-TTL cache of historical results; only pulls newer games and appends to cache
- `get_upcoming_fixtures(league, limit)`
- `get_news(league, limit)`
- `list_archive_seasons(league)`
- Historical variants of standings/results

### Caching Policy for Results (Critical)
- Past completed games **never change** → store them permanently (or TTL ≥ 30 days, preferably indefinite for history).
- Cache key: league + season (or league slug).
- On request:
  1. Load existing cached games.
  2. Determine latest date / last game in cache.
  3. Fetch only newer games (or full if no cache).
  4. Append new games to cache and return the (full or filtered) list.
- This makes daily/regular updates extremely cheap and fast, especially important for Apify and cloud IaaS billing.
- Cache location: local file (data/) or configurable backend (for multi-instance IaaS use Redis/S3 later).

---

## Non-Functional
- **Adaptability**: Multi-fallback selectors in config.py. First successful selector is used. Easy to extend lists when site changes slightly.
- **Performance**: Caching of hierarchy + permanent results history + rate limiting + concurrency control.
- **Reliability**: Retries, logging, graceful fallbacks.
- **Deployment**:
  - Local (stdio)
  - Apify (Actors / custom Docker)
  - Any cloud IaaS (Railway, Fly.io, AWS ECS, DigitalOcean, etc.) via provided Dockerfile + healthcheck
- **Security**: Env-based config, no secrets in code, private repo.

---

## Architecture
BrowserManager (Playwright, rate-limited, stealth)  
→ Modular Extractors (discovery, standings, results with cache, …)  
→ FastMCP tools  
→ Pydantic models  

Results cache layer sits between extractor and storage.

---

## Implementation Notes
- Results cache implemented with simple JSON files first (data/results_{league_slug}.json). Extendable to Redis/S3 for multi-instance Apify/cloud.
- Recommended TTL for pure history: none (permanent) or 90 days. For live/current season partial updates use shorter TTL on the “latest” slice.
- Clarification: `get_results_history` always returns games with **date + home_team + away_team + home_pf + away_pf**. Additional fields can be added later if needed.

---

**End of PRD v0.1.2**  
Ready for continued production hardening and Apify deployment.
