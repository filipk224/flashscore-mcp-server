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
        self.assertTrue(any("2025" in season.name for season in info.archive_seasons))

    def test_left_menu_lists_npb(self):
        from flashscore_mcp.parsers.league import parse_menu_leagues

        leagues = parse_menu_leagues(load(r"baseball\odds tab.html"))
        npb = next(league for league in leagues if league.name == "NPB")
        self.assertIn("/baseball/japan/npb/", npb.url)

    def test_left_menu_markup_is_present_on_other_sports(self):
        from flashscore_mcp.parsers.league import parse_menu_leagues

        for rel in (
            r"basketball\initial league page.html",
            r"hockey\initial league page.html",
            r"rugby league\initial league page.html",
        ):
            leagues = parse_menu_leagues(load(rel))
            self.assertGreater(len(leagues), 0, rel)


if __name__ == "__main__":
    unittest.main()
