"""Optional league for get_h2h / get_team_form, sport-restricted search, and pool sizing."""
from __future__ import annotations

import asyncio
import time
import unittest
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import patch

from flashscore_mcp import config
from flashscore_mcp import sizing
from flashscore_mcp.extractors import h2h_season as hs
from flashscore_mcp.extractors import league_teams as lt
from flashscore_mcp.extractors import match as match_ext
from flashscore_mcp.extractors import team as team_ext
from flashscore_mcp.extractors.team import TeamRef, pick_search_team
from flashscore_mcp.models import MatchResult
from flashscore_mcp.seasons import LeagueSeasons

TODAY = date(2026, 11, 18)


def _row(home, away, s1, i1, s2, i2, comp="USA: MLS", day="01.11.", mid="m1"):
    return MatchResult(
        date=day, home_team=home, away_team=away, match_id=mid, competition=comp,
        match_url=f"https://www.flashscore.com/match/football/{s1}-{i1}/{s2}-{i2}/?mid={mid}",
    )


# Match URLs list the teams alphabetically, not home then away.
MLS_ROWS = [
    _row("Los Angeles Galaxy", "Austin FC", "austin-fc", "IeT6JBE3", "los-angeles-galaxy", "U3ebh62R", mid="a"),
    _row("Los Angeles FC", "New York City", "los-angeles-fc", "txUJt9AR", "new-york-city", "vZraQYnO", mid="b"),
    _row("New York Red Bulls", "Charlotte", "charlotte-fc", "QJF7WTFB", "new-york-red-bulls", "zV5YmQAr", mid="c"),
    _row("Atlanta Utd", "St. Louis City", "atlanta-united", "EPngUvhk", "st-louis-city", "4r4sKQud", mid="d"),
]
PL = "ENGLAND: Premier League"
PL_ROWS = [
    _row("Arsenal", "Chelsea", "arsenal", "hA1Zm19f", "chelsea", "4fGZN2oK", PL, mid="e"),
    _row("Manchester Utd", "Aston Villa", "aston-villa", "W00wmLO0", "manchester-united", "ppjDR086", PL, mid="f"),
    _row("Tottenham", "Manchester City", "manchester-city", "Wtn9Stg0", "tottenham", "UDg08Ohm", PL, mid="g"),
]


def teams(rows):
    with patch.object(lt, "parse_matches", lambda html: rows):
        return lt.teams_from_results("<html/>")


def pick(query, rows):
    found, note = lt.match_league_team(query, teams(rows))
    return (found.slug if found else None), note


class LeagueResolution(unittest.TestCase):
    def resolve(self, text, sport="football", search=None):
        async def fake_json(url, timeout=8.0):
            return search

        with patch.object(lt, "get_json", fake_json):
            return asyncio.run(lt.resolve_league_path(text, sport))

    def test_paths_and_urls(self):
        self.assertEqual(self.resolve("/football/england/premier-league/"), ("football/england/premier-league", "path"))
        self.assertEqual(
            self.resolve("https://www.flashscore.com/football/usa/mls/standings/")[0], "football/usa/mls"
        )

    def test_well_known_names_and_country_forms(self):
        self.assertEqual(self.resolve("MLS")[0], "football/usa/mls")
        self.assertEqual(self.resolve("Premier League")[0], "football/england/premier-league")
        self.assertEqual(self.resolve("England: Premier League")[0], "football/england/premier-league")
        self.assertEqual(self.resolve("Premier League (England)")[0], "football/england/premier-league")

    SEARCH = [
        {"type": {"id": 1}, "sport": {"id": 3}, "name": "Premier League", "url": "premier-league", "defaultCountry": {"name": "Egypt"}},
        {"type": {"id": 2}, "sport": {"id": 1}, "name": "Premier League", "url": "premier-league-xi", "defaultCountry": {"name": "Egypt"}},
        {"type": {"id": 1}, "sport": {"id": 1}, "name": "Premier League", "url": "premier-league", "defaultCountry": {"name": "Egypt"}},
        {"type": {"id": 1}, "sport": {"id": 1}, "name": "Premier League", "url": "premier-league", "defaultCountry": {"name": "Russia"}},
    ]

    def test_search_fallback_keeps_the_sport_and_country(self):
        self.assertEqual(self.resolve("Egypt: Premier League", search=self.SEARCH)[0], "football/egypt/premier-league")
        self.assertEqual(self.resolve("Premier League (Russia)", search=self.SEARCH)[0], "football/russia/premier-league")
        self.assertEqual(
            self.resolve("Egypt: Premier League", sport="basketball", search=self.SEARCH)[0],
            "basketball/egypt/premier-league",
        )

    def test_well_known_name_of_another_sport_is_not_used(self):
        with self.assertRaises(ValueError):
            self.resolve("NBA", sport="football", search=[])
        self.assertEqual(self.resolve("NBA", sport="basketball")[0], "basketball/usa/nba")

    def test_unknown_sport_is_rejected(self):
        with self.assertRaises(ValueError):
            lt.sport_id("quidditch")

    def test_competition_label_matching(self):
        ctx = lt.LeagueContext("football/usa/mls", "MLS", "USA: MLS", None, [], "test")
        self.assertTrue(lt.competition_matches("USA: MLS", ctx))
        self.assertTrue(lt.competition_matches("USA: MLS - Play Offs", ctx))
        self.assertFalse(lt.competition_matches("USA: MLS Next Pro", ctx))
        self.assertFalse(lt.competition_matches("WORLD: Club Friendly", ctx))
        self.assertFalse(lt.competition_matches(None, ctx))


class LeagueTeams(unittest.TestCase):
    def test_teams_and_ids_come_from_match_urls_in_either_order(self):
        found = {t.slug: (t.id, t.names) for t in teams(MLS_ROWS)}
        self.assertEqual(found["los-angeles-galaxy"], ("U3ebh62R", {"Los Angeles Galaxy"}))
        self.assertEqual(found["austin-fc"], ("IeT6JBE3", {"Austin FC"}))
        self.assertEqual(found["charlotte-fc"][1], {"Charlotte"})
        self.assertEqual(len(found), 8)

    def test_mls_short_names(self):
        self.assertEqual(pick("LAFC", MLS_ROWS)[0], "los-angeles-fc")
        self.assertEqual(pick("LA Galaxy", MLS_ROWS)[0], "los-angeles-galaxy")
        self.assertEqual(pick("la galaxy", MLS_ROWS)[0], "los-angeles-galaxy")
        self.assertEqual(pick("NYCFC", MLS_ROWS)[0], "new-york-city")
        self.assertEqual(pick("NY Red Bulls", MLS_ROWS)[0], "new-york-red-bulls")
        self.assertEqual(pick("Atlanta United", MLS_ROWS)[0], "atlanta-united")
        self.assertEqual(pick("Charlotte FC", MLS_ROWS)[0], "charlotte-fc")

    def test_premier_league_names(self):
        self.assertEqual(pick("Arsenal", PL_ROWS), ("arsenal", None))
        self.assertEqual(pick("arsenal", PL_ROWS)[0], "arsenal")
        self.assertEqual(pick("Chelsea", PL_ROWS)[0], "chelsea")
        self.assertEqual(pick("Man Utd", PL_ROWS)[0], "manchester-united")
        self.assertEqual(pick("Man City", PL_ROWS)[0], "manchester-city")
        self.assertEqual(pick("Spurs", PL_ROWS)[0], "tottenham")

    def test_ambiguous_names_say_so_and_unknown_names_miss(self):
        slug, note = pick("Los Angeles", MLS_ROWS)
        self.assertIn(slug, ("los-angeles-fc", "los-angeles-galaxy"))
        self.assertIn("also matched", note)
        self.assertEqual(pick("Lucenec", MLS_ROWS), (None, None))
        self.assertEqual(pick("LA", MLS_ROWS), (None, None))


class SportRestrictedSearch(unittest.TestCase):
    SEARCH = [
        {"type": {"id": 2}, "sport": {"id": 13}, "name": "Galaxy Gladiators Lantau", "url": "galaxy-gladiators-lantau", "id": "bNgfluFq", "defaultCountry": {"name": "Hong Kong"}},
        {"type": {"id": 2}, "sport": {"id": 1}, "name": "Los Angeles Galaxy", "url": "los-angeles-galaxy", "id": "U3ebh62R", "defaultCountry": {"name": "USA"}},
        {"type": {"id": 2}, "sport": {"id": 1}, "name": "TS Galaxy", "url": "ts-galaxy", "id": "KUDSx8jo", "defaultCountry": {"name": "South Africa"}},
    ]

    def test_other_sports_are_dropped_and_word_prefixes_beat_fuzzy(self):
        ref = pick_search_team(self.SEARCH, "LA Galaxy", sport="football")
        self.assertEqual(ref.slug, "los-angeles-galaxy")
        self.assertEqual(ref.match, "words")
        self.assertEqual(pick_search_team(self.SEARCH, "LA Galaxy", sport="cricket").slug, "galaxy-gladiators-lantau")

    def test_fuzzy_pick_is_flagged_in_the_note(self):
        ref = pick_search_team(
            [{"type": {"id": 2}, "sport": {"id": 1}, "name": "Lucenec", "url": "lucenec", "id": "Uwo2udF4"}],
            "LAFC",
            sport="football",
        )
        self.assertEqual(ref.match, "fuzzy")
        self.assertIn("did not match closely", team_ext.team_note("LAFC", ref, "by Flashscore search"))

    def test_league_first_then_global_search_fallback(self):
        ctx = lt.LeagueContext("football/usa/mls", "MLS", "USA: MLS", None, teams(MLS_ROWS), "test")
        searched = []

        async def fake_resolve(name, sport="football"):
            searched.append((name, sport))
            return TeamRef("inter-miami", "0AheRyBg", "Inter Miami", match="exact")

        async def run():
            with patch.object(match_ext, "resolve_team", fake_resolve):
                return await match_ext._resolve_pair("LAFC", "Inter Miami", "football", ctx)

        a, b, notes = asyncio.run(run())
        self.assertEqual((a.slug, a.id), ("los-angeles-fc", "txUJt9AR"))
        self.assertEqual(b.slug, "inter-miami")
        self.assertEqual(searched, [("Inter Miami", "football")])
        self.assertIn("from MLS teams", notes[0])
        self.assertIn("/team/los-angeles-fc/txUJt9AR/", notes[0])
        self.assertIn("not found among MLS teams", notes[1])


def _game(mid, day, comp="USA: MLS"):
    return MatchResult(
        date=day, home_team="Los Angeles FC", away_team="Los Angeles Galaxy", match_id=mid, competition=comp,
        match_url=f"https://www.flashscore.com/match/football/los-angeles-fc-txUJt9AR/los-angeles-galaxy-U3ebh62R/?mid={mid}",
    )


def _filler(mid, day):
    return MatchResult(
        date=day, home_team="Other", away_team="Team", match_id=mid,
        match_url=f"https://www.flashscore.com/match/football/other-oooooooo/team-tttttttt/?mid={mid}",
    )


MLS = LeagueSeasons("MLS", "2026", ("MLS 2026", "MLS 2025", "MLS 2024"))
LAFC = TeamRef("los-angeles-fc", "txUJt9AR", "Los Angeles FC")
GALAXY = TeamRef("los-angeles-galaxy", "U3ebh62R", "Los Angeles Galaxy")


class ExplicitLeagueSeason(unittest.TestCase):
    def scan(self, season, league_seasons, league_given=True):
        state = hs.SeasonScan()
        guessed = []
        rows = [
            _filler("f1", "08.11."), _game("g26", "26.10."), _filler("f2", "20.03."), _filler("f3", "10.12."),
            _game("g25b", "20.07."), _game("g25a", "19.05."), _filler("f4", "10.03."),
            _filler("f5", "01.12."), _filler("f6", "01.10."), _filler("f7", "01.09."),
        ]
        loads = []

        async def fake_guess(ref, deadline, st):
            guessed.append(ref)
            return LeagueSeasons("Premier League", "2026-2027", ("Premier League 2026/2027",))

        @asynccontextmanager
        async def new_page(queue_wait_s=None):
            async def content():
                return ""
            yield type("P", (), {"url": "", "content": staticmethod(content)})()

        async def goto(page, url):
            loads.append(url)

        async def never(page):
            return False

        def parse(html):
            return rows if loads and loads[-1].endswith("/results/") else []

        async def run():
            await hs.scan_season(
                LAFC, GALAXY, season, state, time.monotonic() + 30, today=TODAY,
                league_seasons=league_seasons, league_given=league_given,
            )

        with patch.object(hs, "read_league_seasons", fake_guess), \
             patch.object(hs.browser_manager, "new_page", new_page), \
             patch.object(hs, "_goto_list", goto), \
             patch.object(hs, "parse_matches", parse), \
             patch.object(hs, "_show_more_once", never), \
             patch.object(hs, "_visible_show_more", never):
            asyncio.run(run())
        return state, guessed

    def test_explicit_league_format_is_used_without_guessing(self):
        state, guessed = self.scan("2025", MLS)
        self.assertEqual(guessed, [])
        self.assertEqual((state.plan.start, state.plan.end), (date(2025, 1, 1), date(2025, 12, 31)))
        self.assertEqual(state.plan.label, "2025")
        self.assertEqual(sorted(state.items), ["g25a", "g25b"])
        self.assertIn("read from MLS", state.plan.notes[0])

    def test_current_season_from_explicit_calendar_league(self):
        state, _ = self.scan(None, MLS)
        self.assertEqual(state.plan.label, "2026")
        self.assertEqual(list(state.items), ["g26"])

    def test_explicit_league_with_unreadable_format_falls_back_and_says_so(self):
        state, guessed = self.scan("2025", None)
        self.assertEqual(guessed, [])
        self.assertEqual(state.plan.start, date(2025, 7, 1))
        self.assertTrue(any("July to June" in n for n in state.plan.notes))

    def test_without_league_the_guess_is_used_and_noted(self):
        state, guessed = self.scan("2025", None, league_given=False)
        self.assertEqual(guessed, [LAFC])
        self.assertEqual(state.plan.label, "2025/2026")
        self.assertTrue(any("pass league to choose it" in n for n in state.plan.notes))

    def test_league_only_filter(self):
        ctx = lt.LeagueContext("football/usa/mls", "MLS", "USA: MLS", MLS, [], "test")
        scan = hs.SeasonScan(items={"a": _game("a", "01.05.2025"), "b": _game("b", "01.07.2025", "USA: Leagues Cup")})
        notes = []
        match_ext._league_filter(scan, ctx, True, notes)
        self.assertEqual(list(scan.items), ["a"])
        self.assertIn("league_only", notes[0])
        scan2 = hs.SeasonScan(items=dict(scan.items))
        notes2 = []
        match_ext._league_filter(scan2, ctx, False, notes2)
        self.assertIn("All competitions", notes2[0])

    def test_league_only_without_league_is_rejected(self):
        with self.assertRaises(ValueError):
            asyncio.run(match_ext.get_h2h(team_a="A", team_b="B", league_only=True))


GB = 1024


class PoolSizing(unittest.TestCase):
    def size(self, env=None, cgroup_mem=None, cgroup_cpu=None, os_cpus=8, host_mem=None, explicit=None):
        return sizing.size_for(
            env or {},
            explicit_pages=explicit,
            cgroup_mem=lambda: cgroup_mem,
            cgroup_cpu=lambda: cgroup_cpu,
            os_cpus=lambda: os_cpus,
            host_mem=lambda: host_mem,
        )

    def test_apify_sizes_scale_continuously(self):
        expected = {1: 1, 2: 2, 4: 2, 8: 2, 16: 4, 32: 8, 48: 12, 64: 16, 128: 16}
        for gb, pages in expected.items():
            got = self.size({"ACTOR_MEMORY_MBYTES": str(gb * GB)})
            self.assertEqual(got.max_concurrent_pages, pages, f"{gb} GB")
            self.assertEqual(got.memory_source, "ACTOR_MEMORY_MBYTES")
            self.assertEqual(got.cpu_source, "apify-memory")
            self.assertEqual(got.pages_source, "computed")

    def test_16_and_64_gb_inputs_are_reported(self):
        small = self.size({"ACTOR_MEMORY_MBYTES": "16384"})
        self.assertEqual((small.memory_mb, small.cpus, small.memory_pages, small.cpu_pages), (16384, 4.0, 30, 4))
        big = self.size({"APIFY_MEMORY_MBYTES": "65536"})
        self.assertEqual((big.memory_source, big.cpus, big.memory_pages, big.cpu_pages), ("APIFY_MEMORY_MBYTES", 16.0, 126, 16))
        self.assertEqual(big.max_concurrent_pages, 16)
        self.assertIn("max_concurrent_pages", big.as_dict())

    def test_cgroup_quota_beats_the_memory_estimate(self):
        got = self.size({"ACTOR_MEMORY_MBYTES": "65536"}, cgroup_cpu=6.0)
        self.assertEqual((got.cpus, got.cpu_source, got.max_concurrent_pages), (6.0, "cgroup", 6))

    def test_memory_is_the_limit_on_a_small_box_with_many_cpus(self):
        got = self.size(cgroup_mem=3 * GB, os_cpus=32)
        self.assertEqual((got.memory_source, got.cpu_source, got.max_concurrent_pages), ("cgroup", "os", 4))

    def test_meminfo_and_cpu_count_without_apify_or_cgroup(self):
        got = self.size(host_mem=16000, os_cpus=8)
        self.assertEqual((got.memory_source, got.max_concurrent_pages), ("meminfo", 8))

    def test_nothing_known_uses_the_default(self):
        got = self.size(os_cpus=None)
        self.assertEqual((got.max_concurrent_pages, got.pages_source), (sizing.DEFAULT_PAGES, "default"))

    def test_explicit_setting_wins(self):
        got = self.size({"ACTOR_MEMORY_MBYTES": "65536"}, explicit=3)
        self.assertEqual((got.max_concurrent_pages, got.pages_source, got.cpu_pages), (3, "env", 16))

    def test_apply_sizing_respects_an_explicit_env_value(self):
        explicit = config.Settings(max_concurrent_pages=5)
        chosen = config.apply_sizing(explicit, {"ACTOR_MEMORY_MBYTES": "65536"}, cgroup_cpu=lambda: None)
        self.assertEqual((explicit.max_concurrent_pages, chosen.pages_source), (5, "env"))
        auto = config.Settings()
        chosen = config.apply_sizing(auto, {"ACTOR_MEMORY_MBYTES": "16384"}, cgroup_cpu=lambda: None)
        self.assertEqual((auto.max_concurrent_pages, chosen.pages_source), (4, "computed"))
        self.assertIn("max_concurrent_pages=4", config.sizing_summary(chosen))


if __name__ == "__main__":
    unittest.main()
