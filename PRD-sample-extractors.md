# Flashscore MCP — Sample Extractors PRD

**Version:** 1.0
**Status:** Approved design, not yet implemented
**Product:** `filipk224/flashscore-mcp-server`
**Source of truth for markup:** `MCP/Flashscore MCP/flashscore page samples`
**Companion to:** `PRD.md` (v0.1.2), which stays the production document for deployment, hosting, and the original tool list. This file is the requirements for the sample-based extractors only. Do not edit `PRD.md` as part of this work.

---

## Problem

The server returns one standings shape (`played`, `wins`, `losses`, `pf`, `pa`, `form`) and one result shape (`home_pf`, `away_pf`), and it guesses those cells by position. The saved Flashscore pages do not match that shape. Each sport prints different statistics. Callers need those statistics, with sport only as a label on the league.

## Goal

Extract the statistics that are actually on the sampled pages, through the existing MCP tools, plus league identity and odds. Parsers are pure functions of HTML. Playwright only fetches the page. The saved samples are the test suite, and the same parsers read a page fetched later, including a game that was not in the samples.

## First sports

American football, Aussie rules, baseball, basketball, hockey, rugby league, rugby union, and volleyball. Those are the sports with saved pages. A sport with no sample is out of this release.

Archived seasons use the same layout as the current season of that sport. Odds, News, Fixtures, and Archive use one layout across these sports. Archived seasons have no Odds tab.

## Success

A caller can ask for a sampled league and receive:

- Standings rows whose shared columns use fixed names, and whose other columns are still present
- Results and fixtures with a final score, period scores when the row has them, and a live flag only when that game is live
- The leagues, seasons, news, and default odds the page offers

Offline tests against the saved HTML pass without a browser.

---

## Standings contract

One header-driven parser. A header that is absent on that page leaves the field null. A missing header is never stored as zero.

Rows are grouped by the section heading on the page (conference, division, or a single table). The section name is the participant-column header when that header is not "Team".

| Header on the page | Field |
|---|---|
| MP | `played` |
| W | `wins` |
| D | `draws` |
| L | `losses` |
| Pts | `table_points` |
| Form | `form` |

Every other header is returned in `extras` under that header text.

- `TP`, `G`, `S`, and `R`, when the cell is `N:M`, are `{raw, for, against}`. The raw string stays. Example: `683:347` is for 683, against 347.
- `PCT`, `%`, `WO`, and `LO` stay raw strings (`0.564`, `137.21`, `0`).
- A scoring cell that is not `N:M` stays a raw string.

Columns seen on the samples:

| Sport | Columns besides the shared ones | Page structure |
|---|---|---|
| American football | TP, PCT | Conference and division blocks |
| Aussie rules | TP, %, Pts | Playoffs and wild card are brackets |
| Baseball | R, PCT | Division blocks |
| Basketball | TP, PCT | Conference and division blocks, plus a Home table |
| Hockey | WO, LO, G, Pts | One table |
| Rugby league | TP, Pts | Pre-season is a table. Playoffs are a bracket |
| Rugby union | TP, Pts | One table |
| Volleyball | S, Pts | One table |

`get_standings` accepts `view`: `overall` (default), `home`, or `form`, when that sub-tab exists on the page.

A bracket page (playoffs, wild card, draw) returns `kind: "draw"` and no standings rows. A page with no table returns an empty table and does not raise.

## Results contract

Fixed keys: `date`, `time`, `home_team`, `away_team`, `status`, `home_score`, `away_score`.

`status` is `scheduled`, `live`, or `finished`.

`extras.periods` is the ordered period pairs from the match row (quarters, sets, goals and behinds). Each pair is `{label, home, away}` and keeps the cell text, including values such as `19.8`. `extras.note` holds the non-score line (pitchers, winner, "Advancing to next round"). A dash score is null.

The match-row parser serves results, fixtures, and the summary tab.

### Live

There is no live-games tool, and standings rows do not carry a live flag. When a game the match parser already returns is marked live (`data-live="true"`, or a stage that is not a date and not "Finished"), set `status` to `live`. That is the whole live feature. A game that was not in the saved HTML still parses with this parser.

## Odds, news, archive, leagues

These tabs share their markup across the eight sports.

- **Odds.** Bookmaker, side, and price from the odds tab (`wcl-oddsCell` and the bookmaker name). This release reads the default market on the saved odds tab. `get_odds` on an archived season returns an empty list.
- **News.** Title and link.
- **Archive.** Seasons from the embedded `league_archive_data`: name, url, and winner. An unknown season name returns the season names that list actually contains. Historical standings and results open that season URL and use the same parsers as the current season.
- **Leagues.** `get_league` returns sport, country, name, season, url, the tabs on the page, and the archive seasons. `list_leagues` reads the left-menu league links and the top-leagues object on the page.

## Tools

| Tool | This release |
|---|---|
| `list_sports`, `list_countries`, `list_leagues` | Stay. League list comes from the left menu and the top-leagues object. |
| `get_standings`, `get_historical_standings` | Return the standings contract, including `kind` and sections. |
| `get_results_history`, `get_historical_results` | Return the results contract. |
| `get_upcoming_fixtures` | Same match parser. A row with a dash score is a fixture. |
| `get_news`, `list_archive_seasons` | Stay, fed by the shared parsers. |
| `get_league` | New. League identity, tabs, and archive seasons. |
| `get_odds` | New. Bookmaker, side, and price. |

## Acceptance

Tests read the sample HTML and do not open a browser. Each of these holds:

- Penrith Panthers: played 24, wins 18, losses 6, draws null, table points 42, form `WWWLL`, TP for 683 against 347
- Fremantle Dockers: TP for 2286 against 1666
- Trinec: G for 11 against 7, table points 9
- Basketball and baseball results include a final score. Baseball includes the pitchers line and has no period parts
- Volleyball's archived results page parses with the same match parser as a current results page
- The baseball odds sample yields a bookmaker and a price
- Aussie rules and rugby league playoff samples return `kind: "draw"`
- A small match row with `data-live="true"` has `status` `live`

## Out of scope

- A separate live-games tool, or a live flag on a standings row
- A typed schema per sport
- Player stats, lineups, and the in-play clock
- Handicap and total odds
- Parsing the playoff bracket into series winners
- Sports that have no saved page
- Replacing the server's deployment, hosting, or transport

## Follow-up markup

These are not part of this release. Saved pages for them would unlock a later extractor.

1. Match detail, one finished and one live, for a sport in each scoring family. Player stats, lineups, and the in-play clock are not on the league pages. Marking a league-page game live does not need this file.
2. The odds tab with a second market selected (handicap or total). The saved odds tab has the default price only.

Playoff bracket markup is already in the samples. A bracket extractor can follow this release without a new save.
