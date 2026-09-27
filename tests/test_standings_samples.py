"""Offline standings checks against saved Flashscore pages."""
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
class StandingsSamples(unittest.TestCase):
    def test_rugby_league_penrith_canonical_and_points_split(self):
        from flashscore_mcp.parsers.standings import parse_standings

        page = parse_standings(load(r"rugby league\standings tab (main).html"))
        self.assertEqual(page.kind, "table")
        row = next(r for s in page.sections for r in s.rows if r.team == "Penrith Panthers")
        self.assertEqual(row.played, 24)
        self.assertEqual(row.wins, 18)
        self.assertEqual(row.losses, 6)
        self.assertIsNone(row.draws)
        self.assertEqual(row.table_points, 42)
        self.assertEqual(row.form, "WWWLL")
        self.assertEqual(row.extras["TP"], {"raw": "683:347", "for": 683, "against": 347})

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

    def test_remaining_sampled_sports_keep_their_scoring_column(self):
        from flashscore_mcp.parsers.standings import parse_standings

        jags = parse_standings(load(r"american football\standings tab overall.html"))
        jag = next(r for s in jags.sections for r in s.rows if r.team == "Jacksonville Jaguars")
        self.assertEqual(jag.extras["TP"], {"raw": "34:10", "for": 34, "against": 10})
        self.assertEqual(jag.extras["PCT"], "1.000")

        padova = parse_standings(load(r"volleyball\standings tab.html"))
        pad = next(r for s in padova.sections for r in s.rows if r.team == "Padova")
        self.assertEqual(pad.extras["S"], {"raw": "0:0", "for": 0, "against": 0})
        self.assertEqual(pad.table_points, 0)

        wales = parse_standings(load(r"rugby union\standings tab.html"))
        wal = next(r for s in wales.sections for r in s.rows if r.team == "Wales")
        self.assertEqual(wal.extras["TP"], {"raw": "0:0", "for": 0, "against": 0})
        self.assertEqual(wal.draws, 0)

    def test_draw_pages_have_no_rows(self):
        from flashscore_mcp.parsers.standings import parse_standings

        for rel in (
            r"australian rules\standings tab (main) (play offs).html",
            r"rugby league\standings tab (play offs).html",
        ):
            page = parse_standings(load(rel))
            self.assertEqual(page.kind, "draw", rel)
            self.assertEqual(sum(len(s.rows) for s in page.sections), 0)


if __name__ == "__main__":
    unittest.main()
