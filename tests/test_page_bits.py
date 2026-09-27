"""Odds, news, and archive JSON. These tabs share their markup across sports."""
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
        self.assertGreater(len(prices), 0)
        price = prices[0]
        self.assertTrue(price.bookmaker)
        self.assertTrue(price.side)
        self.assertRegex(price.price, r"^\d+(?:\.\d+)?$")

    def test_odds_parser_returns_empty_when_the_tab_has_no_cells(self):
        from flashscore_mcp.parsers.odds import parse_odds

        self.assertEqual(parse_odds("<html><body>No odds here</body></html>"), [])

    def test_news_cards_parse_on_every_saved_news_tab(self):
        from flashscore_mcp.parsers.news import parse_news

        for rel in (
            r"basketball\news tab.html",
            r"american football\news tab.html",
            r"australian rules\news tab.html",
        ):
            items = parse_news(load(rel))
            self.assertGreater(len(items), 0, rel)
            self.assertTrue(items[0].title, rel)
            self.assertIn("/news/", items[0].link, rel)

    def test_archive_json_includes_the_previous_season_and_winner(self):
        from flashscore_mcp.parsers.archive import parse_archive, resolve_season

        seasons = parse_archive(load(r"basketball\archive tab.html"))
        previous = next(season for season in seasons if "2025" in season.name)
        self.assertIn("wnba-2025", previous.url or "")
        self.assertEqual(previous.winner, "Las Vegas Aces W")
        url, _names = resolve_season(seasons, "WNBA 2025")
        self.assertIn("wnba-2025", url or "")
        missing, listed = resolve_season(seasons, "not-a-real-season")
        self.assertIsNone(missing)
        self.assertIn("WNBA 2025", listed)

    def test_archive_object_is_present_on_other_sports(self):
        from flashscore_mcp.parsers.archive import parse_archive

        for rel in (
            r"american football\archive tab.html",
            r"baseball\initial league page.html",
            r"hockey\initial league page.html",
        ):
            seasons = parse_archive(load(rel))
            self.assertGreater(len(seasons), 0, rel)


if __name__ == "__main__":
    unittest.main()
