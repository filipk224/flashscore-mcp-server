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

## Paging, filters and time zones

List tools (`get_results_history`, `get_historical_results`,
`get_upcoming_fixtures`, `get_team_form`, `get_matches_by_day`) return one page
of rows that fits the client gateway (about 9 KB of JSON by default):

- `offset` / `limit` page through the list; each reply carries `total`,
  `returned`, `has_more` and `next_offset`. Call again with
  `offset=next_offset` until `has_more` is false. Pages read from the same
  list are cached for a short time, so follow-up pages answer at once.
- `compact=true` returns short rows (id, kickoff_utc, date, round, stage,
  home, away, score, status), so more rows fit in one page.
- Filters: `date_from` / `date_to` (YYYY-MM-DD), `round` ("Round 7", "7",
  "Wild Card", "Super Bowl", "final") and `stage` (`regular_season`,
  `playoffs`, `all_star`, `preseason`, ...). `get_team_form` also takes
  `season` ("2025/26").
- Every row keeps Flashscore's own `round` label and adds `stage`,
  `round_number`, `playoff_round` and `playoff_round_name` (NFL: Wild Card,
  Divisional Round, Conference Championship, Super Bowl). Rounds come from
  each game's own feed record, so Thursday and Monday games stay in their week.
- Times are UTC by default (`timezone` is "UTC" in each reply, and rows carry
  `kickoff_utc`). Pass an IANA `timezone` such as `America/New_York` to get
  `date`, `time` and `kickoff_local` in that zone; date filters and
  `get_matches_by_day` days then follow that zone too.
- `get_matches_by_day` with a `league` reads that league's season for dates
  outside the day picker's range (for example a 2025 date).
- `get_h2h` with `league` set and no `sport` infers the sport from the league
  (`league="NFL"` uses american-football).

Settings: `FLASHSCORE_PAGE_BYTES` (page size), `FLASHSCORE_LIST_BUDGET_S`
(time to load a list), `FLASHSCORE_LIST_CACHE_S` and
`FLASHSCORE_LIST_CACHE_ARCHIVE_S` (how long loaded lists are reused).

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