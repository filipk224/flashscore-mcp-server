# Flashscore MCP server

The product is structured sports data from Flashscore, returned through MCP tools. Parsers are pure functions of HTML. Extractors fetch a page with Playwright and hand that HTML to the parsers. Sport changes which columns a page has; it does not change the tool surface.

Package version is `0.2.3` (`src/flashscore_mcp/__init__.py`). The FastMCP server is constructed as `FastMCP("flashscore-mcp", version=__version__)`, so the MCP handshake reports `0.2.3` rather than the FastMCP library version. The Apify Actor metadata in `.actor/actor.json` still has `"version": "0.1"`.

The [2026-09-28 sample-extractor design](../specs/2026-09-28-flashscore-sample-extractors-design.md) still describes standings, results, fixtures, news, odds, archive seasons, and league identity. This document covers what shipped after that: league-name resolution, a parser self-adapter, empty versus failed loads, match-level tools, HTTP authentication, and deploys.

## Architecture

| Area | Responsibility |
| --- | --- |
| `src/flashscore_mcp/parsers/` | Pure HTML to Pydantic models. `adapter.py` remaps renamed CSS class tokens before parsing. |
| `src/flashscore_mcp/extractors/` | Playwright fetch, then the matching parser. `resolve.py` turns a league reference into a path. `page_status.py` classifies empty versus failed pages. `match_ref.py` turns a match URL or id into a canonical URL. |
| `src/flashscore_mcp/models.py` | Response models, including `MatchResult`, `Fixture`, `MatchCollection`, and `MatchDetail`. |
| `src/flashscore_mcp/server.py` | Seventeen MCP tools, stdio entry (`main`), and the `/` and `/health` HTTP routes. |
| `src/flashscore_mcp/http_server.py` | Streamable HTTP entry with bearer authentication. |
| `src/main.py` and `.actor/` | Apify Standby MCP Actor. |

There is no `FLASHSCORE_MIN_DELAY_S` setting. An HTTP-feed-first path (Playwright only as a fallback) is not implemented.

## League references

`resolve_league_ref` in `extractors/resolve.py` accepts:

- A Flashscore path or URL, such as `football/england/premier-league`. Paths are kept as `sport/country/slug`. Full `http://` or `https://` URLs are returned unchanged.
- `Name (Country)` or `Name, Country`, such as `Premier League (England)` or `NBA, USA`.
- A bare well-known name from the `WELL_KNOWN` map (for example `NBA`, `Premier League`, `EPL`, `La Liga`). If a country is also given, it must match that mapping's country slug.

Unresolved or empty values raise `ValueError` and ask for a name with its country or a path. When a country is present and the name is not in `WELL_KNOWN` (or the well-known country does not match), the resolver searches that country's league menu.

`list_leagues` returns names that already include the country, such as `NPB (Japan)`.

## Parser adapter

`parsers/adapter.py` maps discovered class tokens back to the canonical names the parsers expect, using known semantic fragments. `ensure_match_row_classes` tags `id="g_…"` rows as `event__match` when that class is missing. `adapt_match_html` and `adapt_standings_html` run before those parsers.

The adapter does not cover pages that drop the old class names entirely.

## Empty versus failed loads

`classify_page` in `extractors/page_status.py` returns `ok`, `empty`, or `failed`. `page_outcome` adds a named reason:

| Outcome | Reason |
| --- | --- |
| empty, on results, fixtures, live, day, team, h2h, or match tabs | `no-matches-scheduled` |
| empty, on other tabs | `no-data` |
| failed, because the HTML is shorter than 1500 characters, does not contain `flashscore`, or looks like a challenge or captcha page | `source-refused` |
| failed otherwise, including leftover unparsed row markers (`raw_hints > 0`) | `parse-failed` |

`LoadFailed` is a `RuntimeError` with a `.reason`. `empty_or_raise` raises `LoadFailed` only when the page failed. A successful page with no rows returns the empty collection; filters that remove every item from a successful parse also stay empty rather than becoming a failed load.

## Response shapes

Existing list tools keep returning lists (`list[Sport]`, `list[MatchResult]`, `list[Fixture]`, and the rest). `MatchResult` and `Fixture` include `match_id` and `match_url` so a caller can pass either to `get_match`. Live rows may also include `minute` and `competition`.

Newer listing tools return `MatchCollection`: `status` (`ok`, `empty`, `failed`, or `partial`), optional `reason`, `items` (`list[MatchResult]`), and `errors` (`list[str]`).

`get_match` returns `MatchDetail`. `status` and `reason` describe the tool outcome. `match_status` is the game state from the page (for example scheduled, live, or finished). Section fields are `summary`, `stats`, `incidents`, `lineups`, and `h2h`. If some requested sections fail, they are recorded in `errors` (`dict[str, str]`) and `status` becomes `partial`; the other sections are still returned.

Each tool advertises a JSON `outputSchema` derived from these Pydantic models. FastMCP wraps bare list returns as `{ "result": [...] }` with `x-fastmcp-wrap-result: true`.

## Tools

| Tool | Arguments | Returns | Next step |
| --- | --- | --- | --- |
| `list_sports` | none | `list[Sport]` | Pass a sport slug to `list_countries` or `get_live_matches`. |
| `list_countries` | `sport` | `list[Country]` | Pass sport and country to `list_leagues`. |
| `list_leagues` | `sport`, `country` | `list[League]` | Pass a country-qualified name to league tools. |
| `get_league` | `league` | `LeagueInfo` | Then `get_standings`, `get_results_history`, or `get_upcoming_fixtures`. |
| `get_standings` | `league`, `season="current"`, `view="overall"` | `StandingsPage` | Shared columns are played, wins, draws, losses, `table_points`, and form. Other columns stay in `extras`. `view` is `overall`, `home`, or `form`. |
| `get_results_history` | `league`, `season="current"`, `mode="full"`, `limit`, `since` | `list[MatchResult]` | Pass `match_id` or `match_url` to `get_match`. |
| `get_upcoming_fixtures` | `league`, `limit`, `since` | `list[Fixture]` | Pass `match_id` or `match_url` to `get_match`, or use `get_h2h` / `get_team_form`. |
| `get_news` | `league`, `limit=10` | `list[NewsItem]` | Titles and links only. |
| `get_odds` | `league`, `season="current"` | `list[OddsPrice]` | Default odds tab: bookmaker, side, and price. An archived season with no Odds tab returns an empty list. |
| `list_archive_seasons` | `league` | `list[Season]` | Includes `winner` when the page has one. Then pass a season name to the historical tools. |
| `get_historical_standings` | `league`, `season` | `StandingsPage` | Same table layout as the current season. |
| `get_historical_results` | `league`, `season`, `limit`, `since` | `list[MatchResult]` | Same match row as the current season, including `match_id` and `match_url`. |
| `get_match` | `match`, `sections=None` | `MatchDetail` | `match` is a URL or a 4–12 character alphanumeric Flashscore id. `sections` defaults to all of `summary`, `stats`, `incidents`, `lineups`, and `h2h`. Aliases include `statistics` → `stats`, `line-ups`/`lineup` → `lineups`, and `events` → `incidents`. |
| `get_live_matches` | `sport`, `country=None`, `league=None` | `MatchCollection` | Live games with score, minute, and status. Then pass `match_id` to `get_match`. |
| `get_h2h` | `match=None`, `team_a=None`, `team_b=None`, `last_n=None`, `days_back=None` | `MatchCollection` | Pass a match id or URL, or both `team_a` and `team_b`. `last_n` keeps the newest N meetings; `days_back` keeps meetings in that many days. Head-to-head is also a `get_match` section. |
| `get_matches_by_day` | `sport`, `day_offset=None`, `date=None`, `status="all"`, `league=None` | `MatchCollection` | `day_offset` is `0` today, `-1` yesterday, `1` tomorrow. `date` is `YYYY-MM-DD`. `status` is `all`, `live`, `finished`, or `scheduled`. |
| `get_team_form` | `team`, `last_n=10` | `MatchCollection` | `team` may be a Flashscore team URL or path such as `/team/arsenal/hA1Zm19f/`, or a team name. |

League arguments on the older tools accept the same references as `resolve_league_ref`.

## Transports

### stdio

`uv run flashscore-mcp` or `flashscore_mcp.server:main` runs the MCP server over stdio.

### Streamable HTTP

`src/flashscore_mcp/http_server.py` serves Streamable HTTP with `stateless_http=True` and `json_response=True`. A bearer token from `FLASHSCORE_MCP_TOKEN` is required (at least 16 characters). The process exits on startup without one. Comparisons use `hmac.compare_digest`. CORS preflight (`OPTIONS`) is allowed without a token; every other HTTP request needs `Authorization: Bearer <token>`.

The process listens on `HOST` (default `0.0.0.0`) and `PORT` (default `8000`) so a sidecar on the same Docker network can reach it. `docker-compose.yml` publishes only `127.0.0.1:8000:8000`. A Cloudflare Quick Tunnel provides HTTPS to that container over the Docker network; the tunnel is not authentication. Clients must still send the bearer token. Port 8000 must not be reachable on the public internet.

### Apify Standby

`src/main.py` with `.actor/actor.json` (`usesStandbyMode: true`, `webServerMcpPath: "/mcp"`, `dockerfile: "./Dockerfile.apify"`). Input schema is `.actor/INPUT_SCHEMA.json`. Output schema is `.actor/OUTPUT_SCHEMA.json` (`actorOutputSchemaVersion: 1`). This Actor does not write a dataset with `Actor.pushData()`. The output schema therefore uses URL templates:

- `mcpEndpoint`: `{{run.containerUrl}}/mcp`
- `health`: `{{run.containerUrl}}/health`

Apify platform authentication is an Apify API token, not `FLASHSCORE_MCP_TOKEN`. The published Actor id is `SrutgzUV5rcOoni30`.

`GET /health` returns JSON with `status`, `service`, `version`, `mcp_endpoint`, and `cache: false`.

## Deploys

On push to `main`:

- `.github/workflows/deploy-apify.yml` runs `apify/push-actor-action@v1` with the `APIFY_TOKEN` GitHub Actions secret.
- `.github/workflows/deploy-rumble-cloud.yml` SSHes to the host, runs `docker logout ghcr.io` before an anonymous pull of the public `ghcr.io/filipk224/flashscore-mcp-server:latest` image, and recreates the compose stack. It does not use a `GHCR_PULL_TOKEN`. Appleboy SSH scripts must not contain `case`/`;;` (the action cannot parse `;;`). The public port-8000 probe must not treat a refused or timed-out connection as a script failure under `script_stop` / `set -e`.

This branch's `.actorignore` and `.dockerignore` control what Apify and Docker uploads include. They skip PRD files, `tests/`, and `.github/` (and additional files listed in those ignore files). The Superpowers documents under `docs/` are not ignored.

## Tests

The suite is `unittest`. Tests that need saved Flashscore page samples skip when that directory is missing (`FLASHSCORE_SAMPLES_DIR`). `tests/test_apify_http.py` checks that every tool in `tools/list` advertises an object `outputSchema` with `properties`, and that `actor.json` points at the output schema templates above.
