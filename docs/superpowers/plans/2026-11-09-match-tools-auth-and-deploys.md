# Match tools, authentication, and deploys

> **Status (2026-11-09):** Completed. This is a historical record of work that followed the sample-extractor plan. Do not re-implement these items. The design is `docs/superpowers/specs/2026-11-09-flashscore-mcp-server-design.md`. The original extractor plan is `docs/superpowers/plans/2026-09-28-sample-extractors.md`.

**Goal:** After the sample extractors landed, teach the server to resolve league names with their country, adapt to renamed CSS classes, tell empty pages apart from failed loads, expose match-level tools, lock down Streamable HTTP, and deploy to Apify and Rumble without opening port 8000 on the public internet.

**Already on `main` when this record was written:** package version `0.2.3`, seventeen MCP tools, bearer-authenticated HTTP bound to localhost in compose, Apify input and output schemas, and the Rumble deploy hardening described below.

---

- [x] **League references include country knowledge.** `resolve_league_ref` accepts `Name (Country)`, `Name, Country`, well-known bare names, and Flashscore paths or URLs. `list_leagues` returns names that include the country.

- [x] **Parser self-adapter.** `parsers/adapter.py` remaps renamed class tokens and tags `id="g_…"` rows as `event__match` when that class is missing. It does not cover pages that drop the old class names entirely.

- [x] **Empty results versus failed loads.** `classify_page` / `page_outcome` / `LoadFailed.reason` distinguish `ok`, `empty` (`no-matches-scheduled` or `no-data`), and `failed` (`source-refused` or `parse-failed`). `empty_or_raise` raises only on a failed page, not when a successful parse is empty or a filter removes every item.

- [x] **Match identifiers on listings.** `MatchResult` and `Fixture` include `match_id` and `match_url` so callers can pass either to `get_match`.

- [x] **`get_match`.** Accepts a match URL or a 4–12 character alphanumeric id. Optional `sections`: `summary`, `stats`, `incidents`, `lineups`, `h2h` (all of them if omitted). Failed sections are recorded in `MatchDetail.errors` and `status` becomes `partial`.

- [x] **`get_live_matches`.** Live games for a required `sport`, optionally filtered by `country` or `league`, returned as `MatchCollection` with score, minute, and status.

- [x] **`get_h2h`.** Standalone head-to-head from a match ref or `team_a` plus `team_b`, with optional `last_n` and `days_back`. Also available as a `get_match` section.

- [x] **`get_matches_by_day`.** A day's games for a sport without knowing the league first (`day_offset` or `date`, optional `status` and `league`).

- [x] **`get_team_form`.** Recent results for a team URL, path, or name (`last_n`, default 10).

- [x] **Chaining descriptions.** Tool docstrings name the next useful call (for example, pass `match_id` from results or live listings to `get_match`).

- [x] **HTTP bearer authentication.** `FLASHSCORE_MCP_TOKEN` is required (minimum 16 characters, compared with `hmac.compare_digest`). The HTTP process refuses to start without it. Compose publishes `127.0.0.1:8000:8000`. The container still listens on `0.0.0.0` inside the network so the Cloudflare Quick Tunnel sidecar can reach `/mcp` over HTTPS. The tunnel is not a substitute for the bearer token. Public TCP 8000 stays closed.

- [x] **Apify on-commit deploy.** `.github/workflows/deploy-apify.yml` uses `apify/push-actor-action@v1` and the `APIFY_TOKEN` secret. `actor.json` `"input"` is `./INPUT_SCHEMA.json` (resolved from `.actor/`). `"output"` is `./OUTPUT_SCHEMA.json`, with `{{run.containerUrl}}/mcp` and `{{run.containerUrl}}/health` templates, because this Standby Actor does not write a dataset.

- [x] **Rumble deploy hardening.** No `case`/`;;` in appleboy SSH scripts (length checks use `wc -c`). No `GHCR_PULL_TOKEN`; `docker logout ghcr.io` runs before an anonymous pull of the public image. The “public :8000 should be closed” probe runs under `set +e` so a refused connection does not abort the script. The host firewall drops public TCP 8000 while localhost and the tunnel still reach the container.

- [x] **Ignore files for deploys.** Apify and Docker ignore `PRD*.md`, `tests/`, and `.github/` (this branch also lists additional files in `.actorignore` and `.dockerignore`). Superpowers docs under `docs/` are not ignored.

**Out of scope (not done):** an HTTP-feed-first extractor with Playwright only as a fallback.
