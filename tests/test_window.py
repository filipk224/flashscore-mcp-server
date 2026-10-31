"""The game window stops at the caller's count or date, and nowhere else."""
import unittest
from types import SimpleNamespace

from flashscore_mcp.extractors.window import take_until


def game(date: str) -> SimpleNamespace:
    return SimpleNamespace(date=date)


class TakeUntil(unittest.TestCase):
    def test_no_bounds_returns_every_game(self):
        games = [game("02.11."), game("31.10."), game("30.09.")]
        self.assertEqual(take_until(games), games)

    def test_limit_is_the_newest_n(self):
        games = [game("02.11."), game("31.10."), game("30.09.")]
        self.assertEqual([item.date for item in take_until(games, limit=2)], ["02.11.", "31.10."])

    def test_since_includes_that_date_and_stops_before_older_games(self):
        games = [game("02.11."), game("31.10."), game("01.10."), game("30.09.")]
        self.assertEqual(
            [item.date for item in take_until(games, since="01.10.")],
            ["02.11.", "31.10.", "01.10."],
        )

    def test_year_wrap_keeps_january_and_stops_in_december(self):
        games = [game("15.01."), game("02.01."), game("28.12."), game("01.12."), game("30.11.")]
        self.assertEqual(
            [item.date for item in take_until(games, since="01.12.")],
            ["15.01.", "02.01.", "28.12.", "01.12."],
        )

    def test_since_with_a_year_anchors_yearless_games(self):
        games = [game("15.01."), game("28.12."), game("30.09.")]
        self.assertEqual(
            [item.date for item in take_until(games, since="01.10.2025")],
            ["15.01.", "28.12."],
        )

    def test_limit_and_since_stop_at_whichever_comes_first(self):
        games = [game("02.11."), game("31.10."), game("15.10.")]
        self.assertEqual(
            [item.date for item in take_until(games, limit=1, since="01.10.")],
            ["02.11."],
        )

    def test_zero_limit_returns_nothing(self):
        self.assertEqual(take_until([game("02.11.")], limit=0), [])


if __name__ == "__main__":
    unittest.main()
