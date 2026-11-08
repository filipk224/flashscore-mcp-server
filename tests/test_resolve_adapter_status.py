"""Sample-free tests for league names, class adaptation, and empty-vs-failed loads."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from flashscore_mcp.extractors.page_status import LoadFailed, classify_page, empty_or_raise
from flashscore_mcp.extractors.resolve import (
    lookup_known,
    looks_like_path,
    parse_name_and_country,
    resolve_league_ref,
)
from flashscore_mcp.parsers.adapter import adapt_match_html, adapt_standings_html
from flashscore_mcp.parsers.league import parse_menu_leagues
from flashscore_mcp.parsers.matches import parse_matches
from flashscore_mcp.parsers.news import parse_news
from flashscore_mcp.parsers.standings import parse_standings


def _pad(html: str, size: int = 1600) -> str:
    return html + ("<!-- flashscore filler -->" * ((size // 20) + 1))


class LeagueResolve(unittest.TestCase):
    def test_name_and_country_from_parentheses_or_comma(self):
        self.assertEqual(parse_name_and_country("Premier League (England)"), ("Premier League", "England"))
        self.assertEqual(parse_name_and_country("NBA, USA"), ("NBA", "USA"))
        self.assertEqual(parse_name_and_country("NBA"), ("NBA", None))

    def test_well_known_names_include_their_country_path(self):
        self.assertEqual(lookup_known("NBA"), "basketball/usa/nba")
        self.assertEqual(lookup_known("Premier League", "England"), "football/england/premier-league")
        self.assertEqual(lookup_known("NPB"), "baseball/japan/npb")
        self.assertIsNone(lookup_known("NBA", "England"))

    def test_paths_and_urls_are_left_alone(self):
        self.assertTrue(looks_like_path("basketball/usa/nba"))
        self.assertTrue(looks_like_path("https://www.flashscore.com/football/england/premier-league/"))
        self.assertFalse(looks_like_path("NBA (USA)"))
        self.assertFalse(looks_like_path("Premier League"))

    def test_resolve_known_names_and_paths(self):
        async def run() -> None:
            self.assertEqual(await resolve_league_ref("NBA (USA)"), "basketball/usa/nba")
            self.assertEqual(await resolve_league_ref("Premier League (England)"), "football/england/premier-league")
            self.assertEqual(await resolve_league_ref("basketball/usa/nba"), "basketball/usa/nba")
            self.assertEqual(
                await resolve_league_ref("https://www.flashscore.com/football/england/premier-league/"),
                "https://www.flashscore.com/football/england/premier-league/",
            )

        asyncio.run(run())

    def test_unknown_named_league_does_not_pretend_to_succeed(self):
        async def run() -> None:
            with patch(
                "flashscore_mcp.extractors.resolve._discover_named_league",
                return_value=None,
            ):
                with self.assertRaises(ValueError):
                    await resolve_league_ref("Unknown League (Narnia)")

        asyncio.run(run())

    def test_blank_league_is_rejected(self):
        async def run() -> None:
            with self.assertRaises(ValueError):
                await resolve_league_ref("  ")

        asyncio.run(run())


class ParserAdapter(unittest.TestCase):
    def test_renamed_match_classes_still_parse(self):
        html = """
        <div id="g_3_abc123" class="someRow">
          <div class="wcl-event__homeParticipant">Lakers</div>
          <div class="wcl-event__awayParticipant">Celtics</div>
          <div class="wcl-event__score--home">110</div>
          <div class="wcl-event__score--away">98</div>
          <div class="wcl-event__stageTime">02.11. 20:00</div>
        </div>
        """
        games = parse_matches(html)
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0].home_team, "Lakers")
        self.assertEqual(games[0].away_team, "Celtics")
        self.assertEqual(games[0].home_score, 110)
        self.assertEqual(games[0].away_score, 98)

    def test_canonical_match_markup_is_unchanged_by_the_adapter(self):
        html = """
        <div id="g_3_xyz" class="event__match">
          <div class="event__homeParticipant">Home</div>
          <div class="event__awayParticipant">Away</div>
          <div class="event__score--home">1</div>
          <div class="event__score--away">0</div>
        </div>
        """
        self.assertEqual(adapt_match_html(html), html)
        games = parse_matches(html)
        self.assertEqual(games[0].home_team, "Home")
        self.assertEqual(games[0].away_team, "Away")

    def test_renamed_standings_classes_still_parse(self):
        html = """
        <div class="wcl-ui-table">
          <div class="wcl-ui-table__headerCell headerCell--rank">#</div>
          <div class="wcl-ui-table__headerCell headerCell--participant">Team</div>
          <div class="wcl-ui-table__headerCell headerCell--value">MP</div>
          <div class="wcl-ui-table__headerCell headerCell--value">W</div>
          <div class="wcl-ui-table__headerCell headerCell--value">L</div>
          <div class="wcl-ui-table__headerCell headerCell--value">PTS</div>
          <div class="wcl-ui-table__body">
            <div class="wcl-ui-table__row">
              <div class="wcl-table__cell cell--rank">1</div>
              <div class="wcl-table__cell cell--participant">Lakers</div>
              <div class="wcl-table__cell cell--value">10</div>
              <div class="wcl-table__cell cell--value">8</div>
              <div class="wcl-table__cell cell--value">2</div>
              <div class="wcl-table__cell cell--value">16</div>
            </div>
          </div>
        </div>
        """
        adapted = adapt_standings_html(html)
        self.assertIn("ui-table", adapted)
        page = parse_standings(html)
        self.assertEqual(page.kind, "table")
        self.assertEqual(len(page.sections), 1)
        self.assertEqual(page.sections[0].rows[0].team, "Lakers")
        self.assertEqual(page.sections[0].rows[0].played, 10)
        self.assertEqual(page.sections[0].rows[0].table_points, 16)

    def test_menu_leagues_fall_back_to_hrefs_without_old_classes(self):
        html = '<nav><a href="/baseball/japan/npb/">NPB</a></nav>'
        leagues = parse_menu_leagues(html)
        self.assertEqual(leagues[0].slug, "npb")
        self.assertEqual(leagues[0].sport, "baseball")
        self.assertEqual(leagues[0].country, "japan")

    def test_news_falls_back_to_hrefs_without_old_test_ids(self):
        html = '<a href="https://www.flashscore.com/news/nba-preview/" title="NBA preview">NBA preview</a>'
        items = parse_news(html)
        self.assertEqual(items[0].title, "NBA preview")
        self.assertIn("/news/nba-preview/", items[0].link)


class PageStatus(unittest.TestCase):
    def test_short_or_challenge_pages_are_failed_loads(self):
        self.assertEqual(classify_page("<html></html>", tab="results", parsed_count=0), "failed")
        challenge = _pad("<html>Just a moment... cf-challenge flashscore</html>")
        self.assertEqual(classify_page(challenge, tab="results", parsed_count=0), "failed")

    def test_successful_empty_results_page(self):
        html = _pad(
            '<html>flashscore<div id="live-table" class="sportName event--leagues">'
            "There are no matches scheduled.</div></html>"
        )
        self.assertEqual(classify_page(html, tab="results", parsed_count=0), "empty")
        self.assertEqual(empty_or_raise(html, "results", []), [])

    def test_unparsed_match_rows_are_a_failed_load(self):
        html = _pad('<html>flashscore<div id="g_3_abc" class="event__match">broken</div></html>')
        self.assertEqual(
            classify_page(html, tab="results", parsed_count=0, raw_hints=1),
            "failed",
        )
        with self.assertRaises(LoadFailed):
            empty_or_raise(html, "results", [], raw_hints=1)

    def test_parsed_rows_are_ok(self):
        html = _pad("<html>flashscore</html>")
        self.assertEqual(classify_page(html, tab="results", parsed_count=3), "ok")


if __name__ == "__main__":
    unittest.main()
