"""Shared match-row parser against every sampled sport that has a results or fixtures page."""
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

        games = [
            game for game in parse_matches(load(r"basketball\results tab.html"))
            if game.status == "finished" and len(game.extras.get("periods") or []) == 4
        ]
        self.assertGreater(len(games), 0)
        game = games[0]
        self.assertTrue(game.home_team)
        self.assertTrue(game.away_team)
        self.assertRegex(game.date or "", r"\d{1,2}\.\d{1,2}\.")
        self.assertRegex(game.time or "", r"\d{1,2}:\d{2}")
        self.assertIsInstance(game.home_score, int)
        self.assertIsInstance(game.away_score, int)
        self.assertEqual([period["label"] for period in game.extras["periods"]], ["1", "2", "3", "4"])

    def test_baseball_has_pitchers_and_no_periods(self):
        from flashscore_mcp.parsers.matches import parse_matches

        games = parse_matches(load(r"baseball\results tab.html"))
        noted = [game for game in games if "Pitchers:" in (game.extras.get("note") or "")]
        self.assertGreater(len(noted), 0)
        game = noted[0]
        self.assertTrue(game.home_team)
        self.assertTrue(game.away_team)
        self.assertIsInstance(game.home_score, int)
        self.assertIsInstance(game.away_score, int)
        self.assertNotIn("periods", game.extras)

    def test_archived_volleyball_uses_the_same_parser(self):
        from flashscore_mcp.parsers.matches import parse_matches

        games = parse_matches(load(r"volleyball\previous season results tab clicked through archives.html"))
        finished = [game for game in games if game.status == "finished" and game.extras.get("periods")]
        self.assertGreater(len(finished), 0)
        game = finished[0]
        self.assertIsInstance(game.home_score, int)
        self.assertIsInstance(game.away_score, int)
        self.assertIn("label", game.extras["periods"][0])
        self.assertIn("home", game.extras["periods"][0])
        self.assertIn("away", game.extras["periods"][0])

    def test_fixture_dash_is_scheduled_with_null_scores(self):
        from flashscore_mcp.parsers.matches import parse_matches

        scheduled = [
            game for game in parse_matches(load(r"american football\fixtures tab.html"))
            if game.status == "scheduled"
        ]
        self.assertGreater(len(scheduled), 0)
        game = scheduled[0]
        self.assertTrue(game.home_team)
        self.assertTrue(game.away_team)
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

    def test_same_parser_reads_every_sampled_sport(self):
        from flashscore_mcp.parsers.matches import parse_matches

        pages = [
            r"american football\results tab.html",
            r"australian rules\results tab.html",
            r"baseball\results tab.html",
            r"basketball\results tab.html",
            r"hockey\results tab.html",
            r"rugby league\results tab.html",
            r"rugby union\fixtures tab.html",
            r"volleyball\previous season results tab clicked through archives.html",
        ]
        for rel in pages:
            games = parse_matches(load(rel))
            self.assertGreater(len(games), 0, rel)
            self.assertTrue(games[0].home_team, rel)
            self.assertTrue(games[0].away_team, rel)


if __name__ == "__main__":
    unittest.main()
