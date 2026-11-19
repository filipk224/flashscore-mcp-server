# Flashscore

## Features
Access 1000 leagues to 35 sports. Extract team names, scores, dates, games played, wins, losses, points, form, fixtures, previous seasons, news headings with links etc.

League tools accept the name with its country (Premier League (England) or NBA (USA)) as well as a Flashscore path.

Available tools:

    - list_sports():
							List of available sports.

    - list_countries(sport):
							List of countries with available leagues in a particular sport.

    - list_leagues(country, sport):
							List of leagues in a particular country in a particular sport.

    - get_standings():
							
    get_results_history,
    get_upcoming_fixtures,
    get_news,
    list_archive_seasons,
    get_league,
    get_odds,
    get_historical_standings,
    get_historical_results,
    get_match,
    get_live_matches,
    get_h2h,
    get_matches_by_day,
    get_team_form.

## Apify

The Actor builds from `Dockerfile.apify` and runs in Standby mode (`/mcp`).
Pick the run memory in the Actor's Standby / run settings; `actor.json` only
sets a 2 GB default and a 1 GB minimum, with no maximum, so a 16 GB, 64 GB or
any other run size works.

The server sizes its browser pool from the run at startup, so nothing needs
changing between sizes:

- pages = min((memory - 1 GB) / 512 MB, CPUs), at least 1 and at most 16.
- Apify gives about 1 CPU per 4 GB, so 4 GB runs 2 pages, 16 GB runs 4,
  32 GB runs 8 and 64 GB runs 16.
- Memory is read from `ACTOR_MEMORY_MBYTES` (set by Apify), CPUs from the
  container's CPU quota or memory / 4 GB.
- The values and their inputs are in the startup log and under `sizing` in
  `GET /health`.
- To pin a number, set `FLASHSCORE_MAX_CONCURRENT_PAGES` in the Actor's
  environment variables.

The per-page figure comes from local measurements: each Flashscore page holds
about 400-500 MB and uses about half a CPU core while it loads.

## License
Proprietary – Private production use only. All rights reserved.