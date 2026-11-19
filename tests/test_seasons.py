"""Season labels: calendar vs split year, windows, archive mapping, and the H2H load cap."""
from __future__ import annotations

import asyncio
import time
import unittest
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import patch

from flashscore_mcp.config import settings
from flashscore_mcp.extractors import h2h_season as hs
from flashscore_mcp.extractors import match as match_ext
from flashscore_mcp.extractors.team import TeamRef
from flashscore_mcp.models import MatchResult, Season
from flashscore_mcp.parsers.archive import resolve_season
from flashscore_mcp.parsers.league import parse_league_page
from flashscore_mcp.seasons import (
    CALENDAR,
    SPLIT,
    LeagueSeasons,
    archive_name_for,
    format_from_archive,
    match_archive,
    needs_league,
    parse_label,
    plan_season,
    window_for,
)

TODAY = date(2026, 11, 13)
MLS = LeagueSeasons("MLS", "2026", ("MLS 2026", "MLS 2025", "MLS 2024", "MLS 2023"))
PL = LeagueSeasons(
    "Premier League",
    "2026-2027",
    ("Premier League 2026/2027", "Premier League 2025/2026", "Premier League 2024/2025", "Premier League 2023/2024"),
)


class LabelParsing(unittest.TestCase):
    def test_calendar_and_split_labels(self):
        self.assertEqual(parse_label("2026").format, CALENDAR)
        self.assertEqual(parse_label("MLS 2025").label, "2025")
        for text in ("2025/2026", "2025-2026", "2025/26", "2025-26", "Premier League 2025/2026"):
            label = parse_label(text)
            self.assertEqual((label.start_year, label.end_year, label.format, label.label), (2025, 2026, SPLIT, "2025/2026"), text)

    def test_no_year_and_bad_pairs(self):
        self.assertIsNone(parse_label(""))
        self.assertIsNone(parse_label("current"))
        with self.assertRaises(ValueError):
            parse_label("2025/2027")

    def test_format_comes_from_the_archive_names(self):
        self.assertEqual(format_from_archive(MLS.archive_names), CALENDAR)
        self.assertEqual(format_from_archive(PL.archive_names), SPLIT)
        self.assertIsNone(format_from_archive(["Qualifiers", "Playoffs"]))

    def test_league_format_prefers_the_page_label(self):
        self.assertEqual(MLS.format, CALENDAR)
        self.assertEqual(PL.format, SPLIT)
        self.assertEqual(LeagueSeasons("X", None, ("X 2026/2027",)).format, SPLIT)
        self.assertEqual(LeagueSeasons("X", None, ("X 2026",)).current_start_year, 2026)
        self.assertIsNone(LeagueSeasons("X", None, ()).format)


class Windows(unittest.TestCase):
    def test_calendar_year_window(self):
        self.assertEqual(window_for(2025, CALENDAR), (date(2025, 1, 1), date(2025, 12, 31)))

    def test_split_year_window(self):
        self.assertEqual(window_for(2025, SPLIT), (date(2025, 7, 1), date(2026, 6, 30)))

    def test_current_season_follows_the_league_label(self):
        mls = plan_season(None, MLS, TODAY)
        self.assertEqual((mls.label, mls.format, mls.start, mls.end), ("2026", CALENDAR, date(2026, 1, 1), date(2026, 12, 31)))
        pl = plan_season("current", PL, TODAY)
        self.assertEqual((pl.label, pl.format, pl.start, pl.end), ("2026/2027", SPLIT, date(2026, 7, 1), date(2027, 6, 30)))

    def test_bare_year_uses_the_league_format(self):
        self.assertEqual(plan_season("2025", MLS, TODAY).label, "2025")
        self.assertEqual(plan_season("2025", PL, TODAY).label, "2025/2026")
        self.assertEqual(plan_season("2025-26", PL, TODAY).start, date(2025, 7, 1))

    def test_season_before_the_new_one_starts_still_uses_the_league_label(self):
        # In March the football fallback says 2025/26; the league label says 2026 for a calendar league.
        self.assertEqual(plan_season(None, MLS, date(2026, 3, 1)).label, "2026")

    def test_notes_name_the_format_and_its_source(self):
        plan = plan_season("2025", MLS, TODAY)
        self.assertIn("calendar-year", plan.notes[0])
        self.assertIn("MLS", plan.notes[0])

    def test_fallback_to_july_june_says_so(self):
        plan = plan_season("2025", None, TODAY)
        self.assertEqual((plan.format, plan.start, plan.end), (SPLIT, date(2025, 7, 1), date(2026, 6, 30)))
        self.assertIn("could not be determined", plan.notes[0])
        self.assertIn("July to June", plan.notes[0])
        unreadable = plan_season(None, LeagueSeasons("Odd Cup", None, ()), TODAY)
        self.assertIn("could not be read", unreadable.notes[0])
        self.assertEqual(unreadable.label, "2026/2027")  # July-June current season in November

    def test_split_request_on_a_calendar_league_is_flagged(self):
        plan = plan_season("2025/26", MLS, TODAY)
        self.assertEqual(plan.format, SPLIT)
        self.assertIn("calendar-year seasons", plan.notes[0])

    def test_season_missing_from_the_archive_is_noted(self):
        plan = plan_season("2005", MLS, TODAY)
        self.assertTrue(any("archive list" in n for n in plan.notes))
        self.assertFalse(any("archive list" in n for n in plan_season("2025", MLS, TODAY).notes))

    def test_bad_season_raises(self):
        for bad in ("next year", "2025/2027"):
            with self.assertRaises(ValueError):
                plan_season(bad, PL, TODAY)

    def test_only_a_two_year_season_skips_the_league_lookup(self):
        self.assertFalse(needs_league("2025/26"))
        self.assertTrue(needs_league("2025"))
        self.assertTrue(needs_league(None))
        self.assertTrue(needs_league("current"))


class ArchiveMapping(unittest.TestCase):
    def test_labels_map_to_archive_names_in_the_leagues_format(self):
        self.assertEqual(match_archive(list(PL.archive_names), "2025/26"), "Premier League 2025/2026")
        self.assertEqual(match_archive(list(PL.archive_names), "2025-2026"), "Premier League 2025/2026")
        self.assertEqual(match_archive(list(PL.archive_names), "2025"), "Premier League 2025/2026")
        self.assertEqual(match_archive(list(MLS.archive_names), "2025"), "MLS 2025")
        self.assertIsNone(match_archive(list(MLS.archive_names), "2025/26"))  # MLS has no split seasons
        self.assertIsNone(match_archive(list(PL.archive_names), "1999"))
        self.assertEqual(archive_name_for(list(PL.archive_names), 2024, SPLIT), "Premier League 2024/2025")

    def test_resolve_season_for_historical_tools_uses_the_same_labels(self):
        pl = [Season(name=n, url=f"/football/england/premier-league-{n[-9:-5]}-{n[-4:]}/") for n in PL.archive_names]
        mls = [Season(name=n, url=f"/football/usa/mls-{n[-4:]}/") for n in MLS.archive_names]
        self.assertEqual(resolve_season(pl, "2025/26")[0], pl[1].url)
        self.assertEqual(resolve_season(pl, "2024-2025")[0], pl[2].url)
        self.assertEqual(resolve_season(mls, "2025")[0], mls[1].url)
        self.assertEqual(resolve_season(mls, "MLS 2024")[0], mls[2].url)  # the full name still works
        self.assertIsNone(resolve_season(mls, "2025/26")[0])
        url, names = resolve_season(mls, "nonsense")
        self.assertIsNone(url)
        self.assertEqual(names, list(MLS.archive_names))

    def test_league_page_reports_its_season_format(self):
        html = lambda label, name: (
            f'<h1>{name}</h1><span id="season_url">{label}</span>'
            'league_archive_data = {"seasons": [{"name": "%s", "url": "/x/"}]}' % name
        )
        self.assertEqual(parse_league_page(html("2026", "MLS 2026")).season_format, CALENDAR)
        self.assertEqual(parse_league_page(html("2026-2027", "Premier League 2026/2027")).season_format, SPLIT)


class MainLeague(unittest.TestCase):
    def link(self, href):
        return f'<a title="x" href="{href}" class="headerLeague__title">x</a>'

    def test_most_frequent_league_wins_and_friendlies_are_ignored(self):
        html = (
            self.link("/football/usa/mls/") * 3
            + self.link("/football/north-america/leagues-cup/")
            + self.link("/football/world/club-friendly/") * 5
        )
        self.assertEqual(hs.main_league_path(html), "/football/usa/mls/")
        self.assertIsNone(hs.main_league_path("<html></html>"))


ARS = TeamRef("la-galaxy", "gal12345", "LA Galaxy")
LAFC = TeamRef("lafc", "lafc1234", "LAFC")


def _game(mid, day, home="LA Galaxy", away="LAFC"):
    return MatchResult(
        date=day, home_team=home, away_team=away, home_score=1, away_score=0, match_id=mid,
        match_url=f"https://www.flashscore.com/match/football/la-galaxy-gal12345/lafc-lafc1234/?mid={mid}",
    )


def _filler(mid, day):
    return MatchResult(
        date=day, home_team="Other", away_team="Team", match_id=mid,
        match_url=f"https://www.flashscore.com/match/football/other-oooooooo/team-tttttttt/?mid={mid}",
    )


class CalendarYearScan(unittest.TestCase):
    def _scan(self, season, league):
        state = hs.SeasonScan()

        async def fake_league(ref, deadline, st):
            return league

        pages = {
            "/results/": [[_game("g26", "08.11."), _game("g25b", "02.11.")]],
        }
        # Results newest first, across the 2026 -> 2025 -> 2024 wraps.
        pages["/results/"] = [[
            _filler("f1", "08.11."), _filler("f2", "01.10."),
            _game("g26", "01.06."), _filler("f3", "10.03."), _game("g25", "30.11."),
            _filler("f4", "10.10."), _game("g25b", "10.03."), _game("g24", "20.10."),
        ]]
        pages["/fixtures/"] = [[_game("f26", "20.12.")]]
        loads = []

        @asynccontextmanager
        async def new_page(queue_wait_s=None):
            yield type("P", (), {"url": "", "content": staticmethod(_noop)})()

        async def goto(page, url):
            page.url = url
            loads.append(url)

        step = {}

        def parse(html):
            url = loads[-1]
            for suffix, rows in pages.items():
                if url.endswith(suffix):
                    return rows[0]
            return []

        async def never_more(page):
            return False

        async def run():
            await hs.scan_season(ARS, LAFC, season, state, time.monotonic() + 30, today=TODAY)

        with patch.object(hs, "read_league_seasons", fake_league), \
             patch.object(hs.browser_manager, "new_page", new_page), \
             patch.object(hs, "_goto_list", goto), \
             patch.object(hs, "parse_matches", parse), \
             patch.object(hs, "_show_more_once", never_more), \
             patch.object(hs, "_visible_show_more", never_more):
            asyncio.run(run())
        return state

    def test_calendar_year_season_picks_that_calendar_year(self):
        state = self._scan("2025", MLS)
        self.assertEqual(state.plan.label, "2025")
        # 2026 rows are current-year, 30.11.2025 and 10.03.2025 are in 2025, 20.10.2024 is not.
        self.assertEqual(set(state.items), {"g25", "g25b"})

    def test_current_calendar_season_includes_this_years_games_and_fixtures(self):
        state = self._scan(None, MLS)
        self.assertEqual(state.plan.label, "2026")
        self.assertEqual(set(state.items), {"g26", "f26"})

    def test_same_games_under_a_split_year_league_use_july_june(self):
        state = self._scan("2025", PL)
        self.assertEqual(state.plan.label, "2025/2026")
        self.assertEqual(set(state.items), {"g26", "g25"})  # 30.11.2025 and 08.06.2026, not 10.03.2025

    def test_unreadable_league_falls_back_and_notes_it(self):
        state = self._scan("2025", None)
        self.assertEqual(state.plan.label, "2025/2026")
        self.assertIn("July to June", state.plan.notes[0])


async def _noop():
    return "<html></html>"


class LoadCap(unittest.TestCase):
    def test_cap_scales_with_how_far_back_the_season_is(self):
        current = plan_season(None, PL, TODAY)
        four_back = plan_season("2022/23", PL, TODAY)
        self.assertEqual(four_back.seasons_back, 4)
        self.assertEqual(hs.effective_cap(15, current), 6)
        self.assertEqual(hs.effective_cap(15, four_back), 11)
        self.assertEqual(hs.effective_cap(15, plan_season("2000/01", PL, TODAY)), 15)  # ceiling
        self.assertEqual(hs.effective_cap(2, four_back), 2)  # a small configured cap always wins

    def test_default_ceiling_is_raised(self):
        self.assertEqual(settings.h2h_max_loads, 15)

    def test_load_cap_reason_is_kept_and_reports_the_limit(self):
        scan = hs.SeasonScan(loads=11, capped=True, cap=11, plan=plan_season("2022/23", PL, TODAY))
        result = match_ext._season_collection(scan, scan.plan, TeamRef("a", "aaaaaaaa"), TeamRef("b", "bbbbbbbb"), None, None, 40)
        self.assertEqual((result.status, result.reason), ("partial", "load-cap"))
        self.assertIn("limit 11", result.errors[0])
        self.assertTrue(result.notes)  # the season note travels with the result


if __name__ == "__main__":
    unittest.main()
