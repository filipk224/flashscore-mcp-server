# Flashscore sample extractors

The statistics are the product. Sport only changes which columns a page has. Parsers are pure functions of HTML. The saved pages in `MCP/Flashscore MCP/flashscore page samples` are the tests. Playwright only fetches a page and hands the HTML to those parsers.

First sports: American football, Aussie rules, baseball, basketball, hockey, rugby league, rugby union, volleyball. Archived seasons use the same layout as the current season. Odds, News, Fixtures, and Archive share one layout across these sports. Archived seasons have no Odds tab.

## Standings

One header-driven parser. Missing headers are null, not zero. Rows are grouped by the section heading on the page (the participant column's header when it is not "Team").

| Header | Field |
|---|---|
| MP | played |
| W | wins |
| D | draws |
| L | losses |
| Pts | table_points |
| Form | form |

Every other header stays in `extras` under that header text. A cell shaped `N:M` (`TP`, `G`, `S`, `R`) is `{raw, for, against}` and keeps the raw string. `PCT`, `%`, `WO`, and `LO` stay raw strings.

A bracket page (playoffs, wild card, draw) returns `kind: "draw"` and no rows. `view` selects Overall, Home, or Form when that sub-tab exists. Default is Overall.

## Results

Fixed keys: date, time, home_team, away_team, status (`scheduled`, `live`, `finished`), home_score, away_score.

`extras.periods` is the ordered period pairs from `event__part`, each `{label, home, away}`. Cell text is kept as shown, including Aussie rules `19.8`. `extras.note` holds the non-score line (pitchers, winner, advancing). A dash score is null.

The only live behavior is `status: "live"` when the match row has `data-live="true"` or a stage that is not a date and not "Finished". There is no live tool and no live flag on standings rows. A game that was not in the saved HTML still parses with this match parser.

## Tools

Existing discovery, standings, results, fixtures, news, archive, and historical wrappers stay. Their payloads use the shapes above.

- `get_league` returns sport, country, name, season, url, tabs, and archive seasons
- `get_odds` returns bookmaker, side, and price. An archived season returns an empty list

An unknown season name returns the season names the archive listed. A page with no table returns an empty table.

## Later markup

Match detail (finished and live) for player stats and the in-play clock. An odds tab with a second market selected, if handicap or total prices are needed. Playoff bracket markup is already saved. A bracket extractor can follow without a new save.
