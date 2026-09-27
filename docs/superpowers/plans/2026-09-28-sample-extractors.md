# Sample Extractors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach `flashscore-mcp-server` to return the statistics on the saved Flashscore pages, using one standings parser and one match parser, plus league identity and the default odds market.

**Architecture:** Pure functions in `src/flashscore_mcp/parsers/` turn HTML into Pydantic models. Extractors only fetch with Playwright and call those functions. The saved pages under `MCP/Flashscore MCP/flashscore page samples` are the tests. `PRD.md` is the existing production document and is not edited. Requirements for this work are `PRD-sample-extractors.md`.

**Tech Stack:** Python 3.11+, Pydantic v2, FastMCP, Playwright (fetch only), unittest. No new dependencies.

**Branch:** `sample-extractors`. Commit locally. Do not push. A push to `main` deploys the server.

**Already on this branch, and the baseline for Task 1:** `src/flashscore_mcp/models.py` (new standings and match fields), `src/flashscore_mcp/parsers/standings.py` (`parse_standings`), `tests/test_standings_samples.py` (Penrith). That test passes. Do not rewrite the standings parser unless a later test fails.

**Out of scope:** editing `PRD.md`, a live-games tool, a live flag on standings rows, match-detail pages, handicap or total odds, and bracket series winners.

---

## File map

| File | Responsibility |
|---|---|
| `src/flashscore_mcp/models.py` | Response models. Add `Season.winner` and `StandingsPage.available_seasons`. |
| `src/flashscore_mcp/parsers/standings.py` | Header-driven standings and draw detection. Already written. |
| `src/flashscore_mcp/parsers/matches.py` | One match-row parser for results, fixtures, summary, and live status. |
| `src/flashscore_mcp/parsers/odds.py` | Default odds tab: bookmaker, side, price. |
| `src/flashscore_mcp/parsers/news.py` | Article title and link. |
| `src/flashscore_mcp/parsers/archive.py` | `league_archive_data` seasons and season lookup. |
| `src/flashscore_mcp/parsers/league.py` | League identity and left-menu league links. |
| `src/flashscore_mcp/extractors/fetch.py` | Playwright fetch that returns HTML. |
| `src/flashscore_mcp/extractors/*.py` | Call `fetch_html` then the pure parser. |
| `src/flashscore_mcp/server.py` | Tool signatures and docstrings. Add `get_league` and `get_odds`. |
| `tests/test_*.py` | Offline tests. Skip when the samples directory is missing. |

Samples directory, overridable with `FLASHSCORE_SAMPLES_DIR`:

`C:\Users\filip\project\MCP\Flashscore MCP\flashscore page samples`

Run every test from the repo root:

```powershell
$env:PYTHONPATH = "src"
python tests\test_standings_samples.py -v
```

---

### Task 1: Confirm the standings baseline

**Files:**
- Test: `tests/test_standings_samples.py`
- Create (already present): `src/flashscore_mcp/parsers/standings.py`

- [ ] **Step 1: Run the existing Penrith test**

```powershell
$env:PYTHONPATH = "src"
python tests\test_standings_samples.py -v
```

Expected: `ok` for `test_rugby_league_penrith_canonical_and_points_split`.

- [ ] **Step 2: Add the other sample rows to the same test class**

Append these methods inside `StandingsSamples`. They call `parse_standings` and `load` already defined in that file.

```python
    def test_fremantle_splits_total_points_and_keeps_percentage(self):
        from flashscore_mcp.parsers.standings import parse_standings

        page = parse_standings(load(r"australian rules\standings tab (main) (standings).html"))
        row = next(r for s in page.sections for r in s.rows if r.team == "Fremantle Dockers")
        self.assertEqual(row.played, 23)
        self.assertEqual(row.wins, 19)
        self.assertEqual(row.draws, 0)
        self.assertEqual(row.losses, 4)
        self.assertEqual(row.table_points, 76)
        self.assertEqual(row.extras["TP"], {"raw": "2286:1666", "for": 2286, "against": 1666})
        self.assertEqual(row.extras["%"], "137.21")

    def test_trinec_maps_goals_and_overtime_columns(self):
        from flashscore_mcp.parsers.standings import parse_standings

        page = parse_standings(load(r"hockey\standings tab.html"))
        row = next(r for s in page.sections for r in s.rows if r.team == "Trinec")
        self.assertEqual(row.played, 3)
        self.assertEqual(row.wins, 3)
        self.assertIsNone(row.draws)
        self.assertEqual(row.table_points, 9)
        self.assertEqual(row.extras["G"], {"raw": "11:7", "for": 11, "against": 7})
        self.assertEqual(row.extras["WO"], "0")
        self.assertEqual(row.extras["LO"], "0")

    def test_dallas_is_grouped_under_western_conference(self):
        from flashscore_mcp.parsers.standings import parse_standings

        page = parse_standings(load(r"basketball\standings tab overall.html"))
        row = next(r for s in page.sections for r in s.rows if r.team == "Dallas Mavericks")
        self.assertEqual(row.section, "Western Conference")
        self.assertIsNone(row.draws)
        self.assertEqual(row.extras["PCT"], "0.000")
        self.assertEqual(row.extras["TP"]["for"], 0)

    def test_hanshin_splits_runs(self):
        from flashscore_mcp.parsers.standings import parse_standings

        page = parse_standings(load(r"baseball\standings tab.html"))
        row = next(r for s in page.sections for r in s.rows if r.team == "Hanshin Tigers")
        self.assertEqual(row.section, "Central Division")
        self.assertEqual(row.played, 134)
        self.assertEqual(row.wins, 75)
        self.assertEqual(row.draws, 1)
        self.assertEqual(row.losses, 58)
        self.assertEqual(row.extras["R"], {"raw": "493:418", "for": 493, "against": 418})
        self.assertEqual(row.extras["PCT"], "0.564")

    def test_draw_pages_have_no_rows(self):
        from flashscore_mcp.parsers.standings import parse_standings

        for rel in (
            r"australian rules\standings tab (main) (play offs).html",
            r"rugby league\standings tab (play offs).html",
        ):
            page = parse_standings(load(rel))
            self.assertEqual(page.kind, "draw")
            self.assertEqual(sum(len(s.rows) for s in page.sections), 0)
```

- [ ] **Step 3: Run the file**

```powershell
$env:PYTHONPATH = "src"
python tests\test_standings_samples.py -v
```

Expected: all methods `ok`. The current `parse_standings` already produces these values. If one fails, fix only the mapping in `parsers/standings.py`. Canonical headers are `MP W D L PTS FORM`. `WO` and `LO` stay in `extras`. A cell matching `^\d+:\d+$` becomes `{raw, for, against}`.

- [ ] **Step 4: Commit**

```powershell
git add tests\test_standings_samples.py src\flashscore_mcp\parsers\standings.py
git commit -m "test: lock standings stats from the saved pages"
```

---

### Task 2: Match rows, including a live flag on the game

**Files:**
- Create: `src/flashscore_mcp/parsers/matches.py`
- Test: `tests/test_match_samples.py`

- [ ] **Step 1: Write the failing test**

```python
"""Offline match-row checks against saved Flashscore pages."""
import os
import unittest
from pathlib import Path

SAMPLES = Path(
    os.environ.get(
        "FLASHSCORE_SAMPLES_DIR",
        r"C:\Users\filip\project\MCP\Flashscore MCP\flashscore page samples",
    )
)


def load(rel: str) -> str:
    return (SAMPLES / rel).read_text(encoding="utf-8", errors="ignore")


@unittest.skipUnless(SAMPLES.exists(), "Flashscore page samples are not on this machine")
class MatchSamples(unittest.TestCase):
    def test_basketball_final_and_quarters(self):
        from flashscore_mcp.parsers.matches import parse_matches

        game = parse_matches(load(r"basketball\results tab.html"))[0]
        self.assertEqual(game.home_team, "Golden State Valkyries W")
        self.assertEqual(game.away_team, "Seattle Storm W")
        self.assertEqual(game.date, "20.09.")
        self.assertEqual(game.time, "10:30")
        self.assertEqual(game.status, "finished")
        self.assertEqual(game.home_score, 70)
        self.assertEqual(game.away_score, 57)
        self.assertEqual(
            game.extras["periods"],
            [
                {"label": "1", "home": "21", "away": "19"},
                {"label": "2", "home": "28", "away": "6"},
                {"label": "3", "home": "15", "away": "21"},
                {"label": "4", "home": "6", "away": "11"},
            ],
        )

    def test_baseball_has_pitchers_and_no_periods(self):
        from flashscore_mcp.parsers.matches import parse_matches

        game = parse_matches(load(r"baseball\results tab.html"))[0]
        self.assertEqual(game.home_team, "Chiba Lotte Marines")
        self.assertEqual(game.away_team, "Orix Buffaloes")
        self.assertEqual(game.home_score, 0)
        self.assertEqual(game.away_score, 1)
        self.assertNotIn("periods", game.extras)
        self.assertIn("Pitchers:", game.extras["note"])

    def test_archived_volleyball_uses_the_same_parser(self):
        from flashscore_mcp.parsers.matches import parse_matches

        game = parse_matches(load(r"volleyball\previous season results tab clicked through archives.html"))[0]
        self.assertEqual(game.home_team, "Perugia")
        self.assertEqual(game.away_team, "Lube Civitanova")
        self.assertEqual(game.home_score, 3)
        self.assertEqual(game.away_score, 1)
        self.assertEqual(game.extras["periods"][0], {"label": "1", "home": "25", "away": "27"})
        self.assertIn("Winner:", game.extras["note"])

    def test_fixture_dash_is_scheduled_with_null_scores(self):
        from flashscore_mcp.parsers.matches import parse_matches

        game = parse_matches(load(r"american football\fixtures tab.html"))[0]
        self.assertEqual(game.home_team, "Atlanta Falcons")
        self.assertEqual(game.away_team, "Carolina Panthers")
        self.assertEqual(game.status, "scheduled")
        self.assertIsNone(game.home_score)
        self.assertIsNone(game.away_score)

    def test_live_attribute_marks_the_game_live(self):
        from flashscore_mcp.parsers.matches import parse_matches

        html = """
        <div class="event__match event__match--twoLine" data-live="true">
          <span class="event__stage">Q2</span>
          <div class="event__homeParticipant"><span>Home Side</span></div>
          <div class="event__awayParticipant"><span>Away Side</span></div>
          <span class="event__score event__score--home">10</span>
          <span class="event__score event__score--away">8</span>
        </div>
        """
        game = parse_matches(html)[0]
        self.assertEqual(game.status, "live")
        self.assertEqual(game.home_score, 10)
        self.assertEqual(game.away_score, 8)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm it fails**

```powershell
$env:PYTHONPATH = "src"
python tests\test_match_samples.py -v
```

Expected: `ModuleNotFoundError: No module named 'flashscore_mcp.parsers.matches'`.

- [ ] **Step 3: Write the parser**

Create `src/flashscore_mcp/parsers/matches.py`:

```python
"""One match-row parser for results, fixtures, summary, and live status."""
from __future__ import annotations

import re

from ..models import MatchResult

_ROW = re.compile(r'class="event__match ')
_DATE = re.compile(r"(\d{1,2}\.\d{1,2}\.?)\s*(\d{1,2}:\d{2})?")
_PART = re.compile(
    r'class="[^"]*\bevent__part--(home|away)\b[^"]*\bevent__part--(\d+)\b[^"]*"[^>]*>(.*?)</',
    re.S,
)


def parse_matches(html: str) -> list[MatchResult]:
    marks = list(_ROW.finditer(html))
    games: list[MatchResult] = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else min(len(html), mark.start() + 12000)
        game = _one(html[mark.start() : end])
        if game:
            games.append(game)
    return games


def _one(chunk: str) -> MatchResult | None:
    home = _team(chunk, "event__homeParticipant") or _team(chunk, "event__participant--home")
    away = _team(chunk, "event__awayParticipant") or _team(chunk, "event__participant--away")
    if not home or not away:
        return None
    home_score = _score(_first_text(chunk, "event__score--home"))
    away_score = _score(_first_text(chunk, "event__score--away"))
    stage = _stage_text(chunk)
    date, time = _when(stage)
    status = _status(chunk, stage, home_score, away_score)
    extras: dict = {}
    periods = _periods(chunk)
    if periods:
        extras["periods"] = periods
    note = _note(chunk, home, away)
    if note:
        extras["note"] = note
    return MatchResult(
        date=date,
        time=time,
        home_team=home,
        away_team=away,
        status=status,
        home_score=home_score,
        away_score=away_score,
        extras=extras,
    )


def _team(chunk: str, token: str) -> str | None:
    texts = _texts_after(chunk, token, 800)
    for text in texts:
        if text.startswith("Winner:") or text.startswith("Advancing"):
            continue
        return text
    return None


def _texts_after(chunk: str, token: str, span: int) -> list[str]:
    match = re.search(rf'class="[^"]*{re.escape(token)}[^"]*"', chunk)
    if not match:
        return []
    frag = chunk[match.end() : match.end() + span]
    return [" ".join(part.split()) for part in re.findall(r">([^<]+)<", frag) if part.strip()]


def _first_text(chunk: str, token: str) -> str:
    texts = _texts_after(chunk, token, 400)
    return texts[0] if texts else ""


def _score(text: str) -> int | None:
    stripped = text.strip()
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    return None


def _stage_text(chunk: str) -> str:
    for token in ("event__stageTime", "event__stage"):
        text = _first_text(chunk, token)
        if text:
            return text
    return ""


def _when(stage: str) -> tuple[str | None, str | None]:
    match = _DATE.search(stage)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def _status(chunk: str, stage: str, home: int | None, away: int | None) -> str:
    if re.search(r'data-live="true"', chunk[:2000]):
        return "live"
    if stage and not _DATE.search(stage) and stage.strip().lower() != "finished":
        return "live"
    if home is None and away is None:
        return "scheduled"
    return "finished"


def _periods(chunk: str) -> list[dict]:
    home: dict[str, str] = {}
    away: dict[str, str] = {}
    for match in _PART.finditer(chunk):
        side, label, inner = match.group(1), match.group(2), match.group(3)
        text = " ".join(re.sub(r"<[^>]+>", " ", inner).split())
        if not text:
            continue
        bucket = home if side == "home" else away
        bucket.setdefault(label, text)
    labels = sorted(set(home) | set(away), key=int)
    return [
        {"label": label, "home": home.get(label, ""), "away": away.get(label, "")}
        for label in labels
    ]


def _note(chunk: str, home: str, away: str) -> str | None:
    pitcher = _first_text(chunk, "event__pitchers")
    if pitcher:
        return pitcher
    notes = []
    for text in _texts_after(chunk, "event__homeParticipant", 800) + _texts_after(chunk, "event__participant--home", 800):
        if text.startswith("Winner:") or text.startswith("Advancing"):
            notes.append(text)
    return " ".join(notes) or None
```

Finished sample rows contain `data-live="false"`. `_status` returns `live` only when the row contains `data-live="true"`, or when the stage text is neither a date nor "Finished".

- [ ] **Step 4: Run the test**

```powershell
$env:PYTHONPATH = "src"
python tests\test_match_samples.py -v
```

Expected: five methods `ok`.

- [ ] **Step 5: Commit**

```powershell
git add src\flashscore_mcp\parsers\matches.py tests\test_match_samples.py
git commit -m "feat: parse match rows, period scores, and live status"
```

---

### Task 3: Odds, news, and archive seasons

**Files:**
- Create: `src/flashscore_mcp/parsers/odds.py`
- Create: `src/flashscore_mcp/parsers/news.py`
- Create: `src/flashscore_mcp/parsers/archive.py`
- Modify: `src/flashscore_mcp/models.py` (`Season` and `StandingsPage`)
- Test: `tests/test_page_bits.py`

- [ ] **Step 1: Add the two model fields**

In `Season`, add:

```python
    winner: Optional[str] = None
```

In `StandingsPage`, add:

```python
    available_seasons: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Write the failing test**

```python
"""Odds, news, and archive JSON from saved pages."""
import os
import unittest
from pathlib import Path

SAMPLES = Path(
    os.environ.get(
        "FLASHSCORE_SAMPLES_DIR",
        r"C:\Users\filip\project\MCP\Flashscore MCP\flashscore page samples",
    )
)


def load(rel: str) -> str:
    return (SAMPLES / rel).read_text(encoding="utf-8", errors="ignore")


@unittest.skipUnless(SAMPLES.exists(), "Flashscore page samples are not on this machine")
class PageBits(unittest.TestCase):
    def test_baseball_odds_include_bet365_fukuoka(self):
        from flashscore_mcp.parsers.odds import parse_odds

        prices = parse_odds(load(r"baseball\odds tab.html"))
        match = next(
            p for p in prices
            if p.bookmaker == "bet365" and "Fukuoka" in p.side and p.price == "2.30"
        )
        self.assertEqual(match.side, "Fukuoka S. Hawks")

    def test_odds_parser_returns_empty_when_the_tab_has_no_cells(self):
        from flashscore_mcp.parsers.odds import parse_odds

        self.assertEqual(parse_odds("<html><body>No odds here</body></html>"), [])

    def test_basketball_news_has_a_title_and_a_link(self):
        from flashscore_mcp.parsers.news import parse_news

        items = parse_news(load(r"basketball\news tab.html"))
        self.assertGreater(len(items), 0)
        self.assertIn("Thompson", items[0].title)
        self.assertIn("/news/", items[0].link)

    def test_archive_json_includes_the_previous_season_and_winner(self):
        from flashscore_mcp.parsers.archive import parse_archive, resolve_season

        seasons = parse_archive(load(r"basketball\archive tab.html"))
        previous = next(s for s in seasons if "2025" in s.name)
        self.assertIn("wnba-2025", previous.url or "")
        self.assertEqual(previous.winner, "Las Vegas Aces W")
        url, names = resolve_season(seasons, "WNBA 2025")
        self.assertIn("wnba-2025", url or "")
        missing, listed = resolve_season(seasons, "WNBA 1999")
        self.assertIsNone(missing)
        self.assertIn("WNBA 2025", listed)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run it and confirm import failure**

```powershell
$env:PYTHONPATH = "src"
python tests\test_page_bits.py -v
```

Expected: `ModuleNotFoundError` for `flashscore_mcp.parsers.odds`.

- [ ] **Step 4: Write the three parsers**

`src/flashscore_mcp/parsers/odds.py`:

```python
"""Default odds tab. Bookmaker, side, and price."""
from __future__ import annotations

import re

from ..models import OddsPrice

_CELL = re.compile(r'data-testid="wcl-oddsCell"')


def parse_odds(html: str) -> list[OddsPrice]:
    prices: list[OddsPrice] = []
    for match in _CELL.finditer(html):
        before = html[max(0, match.start() - 2500) : match.start()]
        books = re.findall(r'<img[^>]*title="([^"]+)"', before)
        names = re.findall(r'fp-entityName_[^"]*"[^>]*>([^<]+)', before)
        side = " ".join(names[-1].split()) if names else ""
        frag = html[match.end() : match.end() + 500]
        texts = [" ".join(part.split()) for part in re.findall(r">([^<]+)<", frag) if part.strip()]
        price = texts[0] if texts else ""
        if not side or not price:
            continue
        prices.append(OddsPrice(bookmaker=books[-1] if books else None, side=side, price=price))
    return prices
```

`src/flashscore_mcp/parsers/news.py`:

```python
"""News article titles and links."""
from __future__ import annotations

import html as html_lib
import re

from ..models import NewsItem

_ANCHOR = re.compile(r'<a\b[^>]*data-testid="wcl-newsArticlePreview"[^>]*>')


def parse_news(html: str) -> list[NewsItem]:
    items: list[NewsItem] = []
    seen: set[str] = set()
    for match in _ANCHOR.finditer(html):
        tag = match.group(0)
        title_m = re.search(r'title="([^"]+)"', tag)
        href_m = re.search(r'href="([^"]+)"', tag)
        if not title_m or not href_m:
            continue
        link = html_lib.unescape(href_m.group(1))
        if link in seen:
            continue
        seen.add(link)
        items.append(NewsItem(title=html_lib.unescape(title_m.group(1)), link=link))
    return items
```

`src/flashscore_mcp/parsers/archive.py`:

```python
"""Archive seasons embedded as league_archive_data, plus name lookup."""
from __future__ import annotations

import json

from ..models import Season

_MARKER = "league_archive_data = "


def parse_archive(html: str) -> list[Season]:
    start = html.find(_MARKER)
    if start < 0:
        return []
    payload, _ = json.JSONDecoder().raw_decode(html[start + len(_MARKER) :])
    seasons: list[Season] = []
    for row in payload.get("seasons") or []:
        winner = None
        winners = row.get("winners") or {}
        if isinstance(winners, dict) and winners.get("1"):
            winner = (winners["1"] or {}).get("name")
        seasons.append(Season(name=row.get("name") or "", url=row.get("url"), winner=winner))
    return [s for s in seasons if s.name]


def resolve_season(seasons: list[Season], season: str) -> tuple[str | None, list[str]]:
    names = [s.name for s in seasons]
    wanted = season.strip().lower()
    for item in seasons:
        if item.name.lower() == wanted or wanted in item.name.lower():
            return item.url, names
    return None, names
```

- [ ] **Step 5: Run the test**

```powershell
$env:PYTHONPATH = "src"
python tests\test_page_bits.py -v
```

Expected: four methods `ok`.

- [ ] **Step 6: Commit**

```powershell
git add src\flashscore_mcp\models.py src\flashscore_mcp\parsers\odds.py src\flashscore_mcp\parsers\news.py src\flashscore_mcp\parsers\archive.py tests\test_page_bits.py
git commit -m "feat: parse odds, news, and archive seasons from page markup"
```

---

### Task 4: League identity and the left-menu leagues

**Files:**
- Create: `src/flashscore_mcp/parsers/league.py`
- Test: `tests/test_leagues.py`

- [ ] **Step 1: Write the failing test**

```python
"""League identity and the leagues offered in the left menu."""
import os
import unittest
from pathlib import Path

SAMPLES = Path(
    os.environ.get(
        "FLASHSCORE_SAMPLES_DIR",
        r"C:\Users\filip\project\MCP\Flashscore MCP\flashscore page samples",
    )
)


def load(rel: str) -> str:
    return (SAMPLES / rel).read_text(encoding="utf-8", errors="ignore")


@unittest.skipUnless(SAMPLES.exists(), "Flashscore page samples are not on this machine")
class LeagueSamples(unittest.TestCase):
    def test_baseball_league_page_exposes_sport_tabs_and_archive(self):
        from flashscore_mcp.parsers.league import parse_league_page

        info = parse_league_page(load(r"baseball\initial league page.html"))
        self.assertEqual(info.sport, "baseball")
        self.assertIn("Odds", info.tabs)
        self.assertIn("Standings", info.tabs)
        self.assertTrue(any("2025" in s.name for s in info.archive_seasons))

    def test_left_menu_lists_npb(self):
        from flashscore_mcp.parsers.league import parse_menu_leagues

        leagues = parse_menu_leagues(load(r"baseball\odds tab.html"))
        npb = next(l for l in leagues if l.name == "NPB")
        self.assertIn("/baseball/japan/npb/", npb.url)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it and confirm import failure**

```powershell
$env:PYTHONPATH = "src"
python tests\test_leagues.py -v
```

Expected: `ModuleNotFoundError: No module named 'flashscore_mcp.parsers.league'`.

- [ ] **Step 3: Write the parser**

`src/flashscore_mcp/parsers/league.py`:

```python
"""League identity from a league page, and league links from the left menu."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from ..models import League, LeagueInfo
from .archive import parse_archive

_PRIMARY = ("Summary", "Odds", "News", "Results", "Fixtures", "Standings", "Archive")
_HREF = re.compile(r'<a class="leftMenu__href" href="([^"]+)">([^<]+)</a>')


def parse_league_page(html: str) -> LeagueInfo:
    sport_m = re.search(r'"sport":"([^"]+)"', html)
    country_m = re.search(r'class="leftMenu__title[^"]*"[^>]*>([^<]+)', html)
    h1_m = re.search(r"<h1>([^<]+)</h1>", html)
    season_m = re.search(r'id="season_url"[^>]*>([^<]+)', html)
    canon_m = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    tabs = []
    for title in re.findall(r'role="tab" title="([^"]+)"', html):
        if title in _PRIMARY and title not in tabs:
            tabs.append(title)
    name = " ".join(h1_m.group(1).split()) if h1_m else ""
    return LeagueInfo(
        name=name,
        sport=sport_m.group(1) if sport_m else None,
        country=" ".join(country_m.group(1).split()) if country_m else None,
        season=season_m.group(1).strip() if season_m else None,
        url=canon_m.group(1) if canon_m else None,
        tabs=tabs,
        archive_seasons=parse_archive(html),
    )


def parse_menu_leagues(html: str) -> list[League]:
    found: list[League] = []
    seen: set[str] = set()
    for match in _HREF.finditer(html):
        href, name = match.group(1), " ".join(match.group(2).split())
        if href in seen or not name:
            continue
        seen.add(href)
        parts = [p for p in urlparse(href).path.strip("/").split("/") if p]
        slug = parts[2] if len(parts) >= 3 else name.lower().replace(" ", "-")
        sport = parts[0] if parts else None
        country = parts[1] if len(parts) > 1 else None
        found.append(League(name=name, slug=slug, url=href, sport=sport, country=country))
    return found
```

- [ ] **Step 4: Run the test**

```powershell
$env:PYTHONPATH = "src"
python tests\test_leagues.py -v
```

Expected: both methods `ok`. If the country title selector misses, the sport and tabs assertions still define this task. Adjust only the country regex if `info.country` is needed later; this test does not require it.

- [ ] **Step 5: Commit**

```powershell
git add src\flashscore_mcp\parsers\league.py tests\test_leagues.py
git commit -m "feat: read league identity and left-menu leagues from markup"
```

---

### Task 5: Fetch HTML and point the existing tools at the parsers

**Files:**
- Create: `src/flashscore_mcp/extractors/fetch.py`
- Modify: `src/flashscore_mcp/extractors/standings.py`
- Modify: `src/flashscore_mcp/extractors/results.py`
- Modify: `src/flashscore_mcp/extractors/fixtures.py`
- Modify: `src/flashscore_mcp/extractors/news.py`
- Modify: `src/flashscore_mcp/extractors/archive.py`
- Modify: `src/flashscore_mcp/extractors/discovery.py` (`list_leagues` only)
- Create: `src/flashscore_mcp/extractors/odds.py`
- Create: `src/flashscore_mcp/extractors/league_info.py`

- [ ] **Step 1: Add the fetch helper**

`src/flashscore_mcp/extractors/fetch.py`:

```python
"""Playwright fetch. Parsers never open a browser."""
from __future__ import annotations

from ..browser import browser_manager, click_show_more, safe_goto


async def fetch_html(url: str, show_more: int = 0) -> str:
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)
        if show_more:
            await click_show_more(page, max_clicks=show_more)
        return await page.content()
```

- [ ] **Step 2: Replace the body of each extractor**

Keep `_league_url` in `extractors/results.py`. It is the URL builder the other modules already import.

`extractors/standings.py` becomes:

```python
"""Standings. Fetch the page, parse the saved-page markup."""
from __future__ import annotations

from urllib.parse import urljoin

from loguru import logger

from ..config import settings
from ..models import StandingsPage
from ..parsers.archive import parse_archive, resolve_season
from ..parsers.standings import parse_standings
from .fetch import fetch_html
from .results import _league_url

_VIEW_TAIL = {
    "overall": "/standings/overall/",
    "home": "/standings/home/",
    "away": "/standings/away/",
    "form": "/form/",
}


def _view_url(html: str, view: str) -> str | None:
    tail = _VIEW_TAIL.get(view)
    if not tail:
        return None
    import re
    match = re.search(rf'href="([^"]*{tail})"', html)
    return match.group(1) if match else None


async def get_standings(league: str, season: str = "current", view: str = "overall") -> StandingsPage:
    url = _league_url(league, "current", "standings")
    logger.info("get_standings url={} season={} view={}", url, season, view)
    html = await fetch_html(url)
    if season not in ("current", "", None):
        seasons = parse_archive(html)
        target, names = resolve_season(seasons, season)
        if not target:
            return StandingsPage(kind="unknown-season", available_seasons=names)
        base = urljoin(settings.base_url, target)
        url = base.rstrip("/") + "/standings/"
        html = await fetch_html(url)
    found = _view_url(html, view)
    if view != "overall" and found:
        html = await fetch_html(urljoin(settings.base_url, found))
    return parse_standings(html)
```

`get_results_history` in `extractors/results.py` keeps its signature and becomes a fetch plus `parse_matches`:

```python
async def get_results_history(
    league: str,
    season: str = "current",
    mode: str = "full",
    limit: Optional[int] = None,
    since: Optional[str] = None,
) -> List[MatchResult]:
    url = _league_url(league, "current", "results")
    if season not in ("current", "", None):
        html = await fetch_html(url)
        target, _names = resolve_season(parse_archive(html), season)
        if target:
            url = urljoin(settings.base_url, target).rstrip("/") + "/results/"
    html = await fetch_html(url, show_more=8)
    games = parse_matches(html)
    if since:
        games = [g for g in games if not g.date or g.date > since]
    if limit:
        games = games[:limit]
    return games
```

`get_upcoming_fixtures` returns fixtures built from scheduled match rows:

```python
async def get_upcoming_fixtures(league: str, limit: int = 20) -> List[Fixture]:
    url = _league_url(league, "current", "fixtures")
    games = parse_matches(await fetch_html(url, show_more=4))
    fixtures: List[Fixture] = []
    for game in games:
        if game.status != "scheduled":
            continue
        fixtures.append(Fixture(
            date=game.date,
            time=game.time,
            home_team=game.home_team,
            away_team=game.away_team,
        ))
        if len(fixtures) >= limit:
            break
    return fixtures
```

`get_news`:

```python
async def get_news(league: str, limit: int = 10) -> List[NewsItem]:
    url = _league_url(league, "current", "news")
    return parse_news(await fetch_html(url))[:limit]
```

`list_archive_seasons`:

```python
async def list_archive_seasons(league: str) -> List[Season]:
    url = _league_url(league, "current", "archive")
    return parse_archive(await fetch_html(url))
```

`list_leagues` in `discovery.py` fetches `/{sport}/{country}/` and returns `parse_menu_leagues` on that HTML. Keep the slug filter that drops `standings`, `results`, `fixtures`, `news`, and `archive`. Delete the hardcoded `"Main League"` fallback.

`extractors/odds.py`:

```python
"""Odds tab. An archived season has no odds tab and returns an empty list."""
from __future__ import annotations

from urllib.parse import urljoin

from ..config import settings
from ..models import OddsPrice
from ..parsers.archive import parse_archive, resolve_season
from ..parsers.odds import parse_odds
from .fetch import fetch_html
from .results import _league_url


async def get_odds(league: str, season: str = "current") -> list[OddsPrice]:
    url = _league_url(league, "current", "odds")
    if season not in ("current", "", None):
        html = await fetch_html(_league_url(league, "current", "standings"))
        target, _names = resolve_season(parse_archive(html), season)
        if not target:
            return []
        html = await fetch_html(urljoin(settings.base_url, target))
        if 'title="Odds"' not in html:
            return []
        url = urljoin(settings.base_url, target).rstrip("/") + "/odds/"
    return parse_odds(await fetch_html(url))
```

`extractors/league_info.py`:

```python
"""League identity for get_league."""
from __future__ import annotations

from ..models import LeagueInfo
from ..parsers.league import parse_league_page
from .fetch import fetch_html
from .results import _league_url


async def get_league(league: str) -> LeagueInfo:
    url = _league_url(league, "current", "standings")
    root = url[: -len("standings/")]
    return parse_league_page(await fetch_html(root))
```

`_league_url(league, "current", "standings")` ends in `standings/`. Slicing off that suffix leaves the league root, which contains the tabs and `league_archive_data`.

- [ ] **Step 3: Import-check the package**

```powershell
$env:PYTHONPATH = "src"
python -c "from flashscore_mcp.extractors import standings, results, fixtures, news, archive, discovery; from flashscore_mcp.extractors import odds, league_info; print('imports ok')"
```

Expected: `imports ok`. Add `odds` and `league_info` to `extractors/__init__.py` if that import fails.

- [ ] **Step 4: Re-run the offline tests**

```powershell
$env:PYTHONPATH = "src"
python tests\test_standings_samples.py -v
python tests\test_match_samples.py -v
python tests\test_page_bits.py -v
python tests\test_leagues.py -v
```

Expected: all `ok`. These tests do not open a browser.

- [ ] **Step 5: Commit**

```powershell
git add src\flashscore_mcp\extractors
git commit -m "feat: fetch pages and parse them with the sample parsers"
```

---

### Task 6: MCP tools

**Files:**
- Modify: `src/flashscore_mcp/server.py`

- [ ] **Step 1: Update imports and return types**

Import `StandingsPage`, `OddsPrice`, and `LeagueInfo` from `.models`. Import `odds` and `league_info` from `.extractors`.

Replace the standings, results, fixtures, news, and archive tool bodies so they return the new extractor results. Set the docstrings to:

- `get_standings`: "Standings for a league. Shared columns are played, wins, draws, losses, table_points, and form. Other columns are in extras. view is overall, home, or form."
- `get_results_history`: "Results with date, teams, status, and home_score/away_score. Period scores and notes are in extras. status is live when that game is live."
- `get_upcoming_fixtures`: "Fixtures. Rows with a dash score."
- `get_news`: "News titles and links."
- `list_archive_seasons`: "Seasons from league_archive_data, including the winner when the page has one."

Add:

```python
@mcp.tool()
async def get_league(league: str) -> LeagueInfo:
    """Sport, country, name, season, url, tabs, and archive seasons for one league."""
    return await league_info.get_league(league)


@mcp.tool()
async def get_odds(league: str, season: str = "current") -> list[OddsPrice]:
    """Default odds tab: bookmaker, side, and price. An archived season with no Odds tab returns an empty list."""
    return await odds.get_odds(league, season)
```

`get_standings` signature:

```python
async def get_standings(league: str, season: str = "current", view: str = "overall") -> StandingsPage:
```

`get_historical_standings` calls `standings.get_standings(league, season)` and returns `StandingsPage`. An unknown season comes back as `kind="unknown-season"` with `available_seasons` filled. There is no `get_live_games` tool.

- [ ] **Step 2: Confirm the module imports**

```powershell
$env:PYTHONPATH = "src"
python -c "from flashscore_mcp.server import get_standings, get_odds, get_league, get_results_history; print('tools ok')"
```

Expected: `tools ok`.

- [ ] **Step 3: Commit**

```powershell
git add src\flashscore_mcp\server.py src\flashscore_mcp\extractors\__init__.py
git commit -m "feat: expose sample-based standings, results, league info, and odds"
```

Do not commit `PRD.md`. It must stay byte-for-byte as on `main`.

```powershell
git diff main -- PRD.md
```

Expected: no diff.

---

## Self-check against the requirements

| Requirement | Task |
|---|---|
| Eight sampled sports, canonical columns plus extras, `N:M` split | Task 1 |
| Draw pages return `kind: "draw"` | Task 1 |
| Results, periods, pitchers, winner note, dash fixtures | Task 2 |
| Archived volleyball uses the same match parser | Task 2 |
| `status: "live"` only, no live tool | Task 2 and Task 6 |
| Odds, news, archive winner, unknown season names | Task 3 |
| `get_league` and left-menu leagues | Task 4 and Task 6 |
| `view` overall / home / form | Task 5 |
| Archived season with no Odds tab returns `[]` | Task 5 `get_odds` |
| `PRD.md` unchanged | Task 6 last command |
| Match detail and a second odds market | Not in this plan |
