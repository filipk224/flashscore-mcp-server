"""Season-scoped get_h2h by team names, plus the Apify schema files."""
from __future__ import annotations

import asyncio
import json
import unittest
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from unittest.mock import patch

from flashscore_mcp.config import settings
from flashscore_mcp.errors import LoadFailed
from flashscore_mcp.extractors import h2h_season as hs
from flashscore_mcp.extractors import match as match_ext
from flashscore_mcp.extractors.team import TeamRef
from flashscore_mcp.models import MatchResult
from flashscore_mcp.seasons import LeagueSeasons, plan_season

ARS = TeamRef("arsenal", "hA1Zm19f", "Arsenal")
CHE = TeamRef("chelsea", "4fGZN2oK", "Chelsea")
TODAY = date(2026, 11, 12)


def _plan(season):
    return plan_season(season if season not in (None, "all") else None, LeagueSeasons("Premier League", "2026-2027", ("Premier League 2026/2027",)), TODAY)


def game(mid, day, opp=CHE, home="Arsenal", away="Chelsea", hs_=1, as_=0):
    return MatchResult(
        date=day,
        home_team=home,
        away_team=away,
        home_score=hs_,
        away_score=as_,
        match_id=mid,
        match_url=f"https://www.flashscore.com/match/football/arsenal-{ARS.id}/{opp.slug}-{opp.id}/?mid={mid}",
    )


def other(mid, day):
    return MatchResult(
        date=day, home_team="Arsenal", away_team="Spurs", match_id=mid,
        match_url=f"https://www.flashscore.com/match/football/arsenal-{ARS.id}/spurs-xxxxxxxx/?mid={mid}",
    )


class YearAssignment(unittest.TestCase):
    def rows(self, *days):
        return [other(f"id{i}", d) for i, d in enumerate(days)]

    def test_results_wrap_back_a_year(self):
        days = hs.assign_years(self.rows("08.11.", "02.11.", "28.12.", "05.07."), "results", TODAY)
        self.assertEqual(days, [date(2026, 11, 8), date(2026, 11, 2), date(2025, 12, 28), date(2025, 7, 5)])

    def test_results_row_after_today_belongs_to_last_year(self):
        self.assertEqual(hs.assign_years(self.rows("20.12."), "results", TODAY), [date(2025, 12, 20)])

    def test_fixtures_wrap_forward_a_year(self):
        days = hs.assign_years(self.rows("22.11.", "30.12.", "03.01.", "31.05."), "fixtures", TODAY)
        self.assertEqual(days, [date(2026, 11, 22), date(2026, 12, 30), date(2027, 1, 3), date(2027, 5, 31)])

    def test_a_block_listed_months_out_of_order_keeps_its_year(self):
        # Real Arsenal results: after 06.08.2022 the list jumps to the Nov 2022 Europa League block.
        days = hs.assign_years(
            self.rows("13.08.2022", "06.08.2022", "04.11.", "28.10.", "09.09.", "30.07.", "17.05."), "results", date(2022, 12, 1)
        )
        self.assertEqual(
            days[2:],
            [date(2022, 11, 4), date(2022, 10, 28), date(2022, 9, 9), date(2022, 7, 30), date(2022, 5, 17)],
        )

    def test_explicit_year_is_trusted_and_bad_dates_are_none(self):
        days = hs.assign_years(self.rows("09.11.2025", "29.02.", None), "results", TODAY)
        self.assertEqual(days[0], date(2025, 11, 9))
        self.assertEqual(days[1], date(2024, 2, 29))  # the only leap year that fits
        self.assertIsNone(hs.assign_years(self.rows("29.02.2025"), "results", TODAY)[0])
        self.assertIsNone(days[2])


class FakePage:
    def __init__(self):
        self.url = ""

    async def content(self):
        return "<html></html>"


def _env(pages_by_url, more_clicks=None):
    """Patch the browser layer. pages_by_url: url suffix -> list of row lists (one per load/click)."""
    loads = {"n": 0}
    state = {}

    @asynccontextmanager
    async def new_page(queue_wait_s=None):
        yield FakePage()

    async def goto(page, url):
        page.url = url
        state["url"] = url
        state["step"] = 0
        state.setdefault("visited", []).append(url)

    def parse(html):
        for suffix, steps in pages_by_url.items():
            if state["url"].endswith(suffix):
                return steps[min(state["step"], len(steps) - 1)]
        return []

    async def more_once(page):
        steps = next(v for k, v in pages_by_url.items() if state["url"].endswith(k))
        if state["step"] + 1 >= len(steps):
            return False
        state["step"] += 1
        return True

    async def visible_more(page):
        steps = next(v for k, v in pages_by_url.items() if state["url"].endswith(k))
        return object() if state["step"] + 1 < len(steps) else None

    _env.last_state = state
    return [
        patch.object(hs.browser_manager, "new_page", new_page),
        patch.object(hs, "_goto_list", goto),
        patch.object(hs, "parse_matches", parse),
        patch.object(hs, "_show_more_once", more_once),
        patch.object(hs, "_visible_show_more", visible_more),
    ]


def _scan(pages, season, cap=6, deadline_s=30.0, today=TODAY):
    import time

    state = hs.SeasonScan()

    async def run():
        await hs.scan_season(ARS, CHE, season, state, time.monotonic() + deadline_s, max_loads=cap, today=today)

    patchers = _env(pages)
    for p in patchers:
        p.start()
    try:
        asyncio.run(run())
    finally:
        for p in patchers:
            p.stop()
    return state


CURRENT = "2026/2027"


class ScanBehaviour(unittest.TestCase):
    def test_stops_once_the_page_is_past_the_season_start(self):
        results = [[
            game("m1", "08.11."), other("x1", "02.11."), game("m2", "07.09."), other("x2", "20.08."),
            other("x3", "20.06."), other("x4", "10.06."), other("x5", "01.06."),  # before 1 July: the season is fully on the page
        ], [other("never", "01.01.")]]
        state = _scan({"/results/": results, "/fixtures/": [[game("f1", "14.03.")]]}, CURRENT)
        self.assertEqual(set(state.items), {"m1", "m2", "f1"})
        self.assertEqual(state.loads, 2)  # one load per tab, no Show more clicks
        self.assertFalse(state.capped)
        self.assertEqual(state.items["m2"].date, "07.09.2026")  # year added
        self.assertEqual(state.items["f1"].date, "14.03.2027")

    def test_other_opponents_and_other_seasons_are_ignored(self):
        results = [[other("x1", "08.11."), game("old", "10.03."), other("x2", "20.06.")]]
        state = _scan({"/results/": results, "/fixtures/": [[]]}, CURRENT)
        self.assertEqual(state.items, {})

    def test_load_cap_marks_the_search_capped(self):
        # Every page is still inside the season and more rows are available.
        step = [[game("m1", "08.11.")], [game("m1", "08.11."), game("m2", "07.09.")],
                [game("m1", "08.11."), game("m2", "07.09."), other("x", "10.08.")],
                [game("m1", "08.11."), game("m2", "07.09."), other("x", "10.08."), other("y", "05.08.")]]
        state = _scan({"/results/": step, "/fixtures/": [[]]}, CURRENT, cap=3)
        self.assertTrue(state.capped)
        self.assertLessEqual(state.loads, 3)
        self.assertIn("m1", state.items)

    def test_cap_not_reported_when_the_list_is_exhausted(self):
        steps = [[game("m1", "08.11.")], [game("m1", "08.11."), game("m2", "07.09.")]]
        state = _scan({"/results/": steps, "/fixtures/": [[]]}, CURRENT, cap=6)
        self.assertFalse(state.capped)
        self.assertEqual(set(state.items), {"m1", "m2"})

    def test_past_season_skips_fixtures(self):
        import time

        past = "2024/2025"
        results = [[game("p1", "17.03.2025"), other("x", "20.06.2024")]]
        patchers = _env({"/results/": results, "/fixtures/": [[]]})
        for p in patchers:
            p.start()
        try:
            found = hs.SeasonScan()
            asyncio.run(hs.scan_season(ARS, CHE, past, found, time.monotonic() + 30, today=TODAY))
        finally:
            for p in patchers:
                p.stop()
        visited = _env.last_state["visited"]
        self.assertTrue(visited and all(u.endswith("/results/") for u in visited))
        self.assertEqual(set(found.items), {"p1"})

    def test_deadline_raises_and_keeps_what_was_found(self):
        import time

        state = hs.SeasonScan()

        async def slow_tab(url, tab, ref_b, window, st, cap, deadline, today):
            st.items["m1"] = game("m1", "08.11.2026")
            await asyncio.sleep(5)

        async def run():
            with patch.object(hs, "_scan_tab", slow_tab):
                await hs.scan_season(ARS, CHE, CURRENT, state, time.monotonic() + 0.2, today=TODAY)

        with self.assertRaises(asyncio.TimeoutError):
            asyncio.run(run())
        self.assertIn("m1", state.items)


class GetH2HBySeason(unittest.TestCase):
    def _run(self, scan_fn, **kw):
        async def fake_resolve(name):
            return {"Arsenal": ARS, "Chelsea": CHE}[name]

        async def run():
            with patch.object(match_ext, "resolve_team", side_effect=fake_resolve), \
                 patch.object(match_ext, "scan_season", scan_fn):
                return await match_ext.get_h2h(team_a="Arsenal", team_b="Chelsea", **kw)

        return asyncio.run(run())

    def test_meetings_found_are_ok_and_newest_first(self):
        async def scan(ref_a, ref_b, season, state, deadline, **kw):
            state.plan = _plan(season)
            state.items["a"] = game("a", "01.12.2025")
            state.items["b"] = game("b", "02.03.2026")

        result = self._run(scan, season="2025/26")
        self.assertEqual((result.status, result.reason, result.errors), ("ok", None, []))
        self.assertEqual([g.match_id for g in result.items], ["b", "a"])

    def test_no_meetings_is_empty_with_reason_not_a_timeout(self):
        async def scan(ref_a, ref_b, season, state, deadline, **kw):
            state.plan = _plan(season)

        result = self._run(scan, season="2025/26")
        self.assertEqual((result.status, result.reason), ("empty", "no-meetings"))
        self.assertIn("2025/2026", result.errors[0])
        self.assertFalse(any(e.startswith("timeout") for e in result.errors))

    def test_timeout_is_partial_with_timeout_error_and_partial_items(self):
        async def scan(ref_a, ref_b, season, state, deadline, **kw):
            state.plan = _plan(season)
            state.items["a"] = game("a", "01.12.2025")
            raise asyncio.TimeoutError()

        result = self._run(scan, season="2025/26")
        self.assertEqual((result.status, result.reason), ("partial", "timeout"))
        self.assertTrue(result.errors[0].startswith("timeout"))
        self.assertEqual([g.match_id for g in result.items], ["a"])

    def test_timeout_with_nothing_found_is_not_reported_as_no_meetings(self):
        async def scan(ref_a, ref_b, season, state, deadline, **kw):
            state.plan = _plan(season)
            raise asyncio.TimeoutError()

        result = self._run(scan)
        self.assertEqual((result.status, result.reason, result.items), ("partial", "timeout", []))

    def test_load_cap_is_partial_with_load_cap_reason(self):
        async def scan(ref_a, ref_b, season, state, deadline, **kw):
            state.plan = _plan(season)
            state.loads, state.capped = 6, True

        result = self._run(scan)
        self.assertEqual((result.status, result.reason), ("partial", "load-cap"))
        self.assertTrue(result.errors[0].startswith("load-cap"))

    def test_season_defaults_to_current_and_is_passed_through(self):
        seen = []

        async def scan(ref_a, ref_b, season, state, deadline, **kw):
            state.plan = _plan(season)
            seen.append(state.plan.label)

        self._run(scan)
        self._run(scan, season="2024-2025")
        self.assertEqual(seen[0], plan_season(None, None).label)
        self.assertEqual(seen[1], "2024/2025")

    def test_last_n_applies_to_the_season_list(self):
        async def scan(ref_a, ref_b, season, state, deadline, **kw):
            state.plan = _plan(season)
            for i, day in enumerate(("01.09.2025", "01.12.2025", "02.03.2026")):
                state.items[str(i)] = game(str(i), day)

        result = self._run(scan, season="2025/26", last_n=1)
        self.assertEqual([g.match_id for g in result.items], ["2"])

    def test_overall_budget_bounds_the_whole_call(self):
        async def slow_scan(ref_a, ref_b, window, state, deadline, **kw):
            await asyncio.sleep(0.5)  # ignores the deadline; the budget must still bound it

        async def slow_resolve(name):
            await asyncio.sleep(5)

        async def run():
            with patch.object(settings, "h2h_budget_s", 0.3), \
                 patch.object(match_ext, "resolve_team", side_effect=slow_resolve):
                return await match_ext.get_h2h(team_a="Arsenal", team_b="Chelsea")

        with self.assertRaises(LoadFailed) as ctx:
            asyncio.run(run())
        self.assertTrue(ctx.exception.reason.startswith("timeout"))

    def test_bad_season_is_a_value_error(self):
        async def scan(ref_a, ref_b, season, state, deadline, **kw):
            state.plan = _plan(season)

        with self.assertRaises(ValueError):
            self._run(scan, season="next year")

    def test_season_all_uses_the_full_history_path_under_the_budget(self):
        async def never(*args, **kw):
            await asyncio.sleep(5)

        async def run():
            with patch.object(settings, "h2h_budget_s", 0.2), \
                 patch.object(match_ext, "_full_history_h2h", never):
                return await match_ext.get_h2h(team_a="Arsenal", team_b="Chelsea", season="all")

        with self.assertRaises(LoadFailed) as ctx:
            asyncio.run(run())
        self.assertTrue(ctx.exception.reason.startswith("timeout"))


ACTOR_DIR = Path(__file__).resolve().parent.parent / ".actor"


class ActorSchemas(unittest.TestCase):
    def _actor(self):
        return json.loads((ACTOR_DIR / "actor.json").read_text())

    def test_actor_json_keeps_existing_fields(self):
        actor = self._actor()
        self.assertEqual(actor["dockerfile"], "../Dockerfile.apify")
        self.assertEqual(actor["input"], "./INPUT_SCHEMA.json")
        self.assertEqual(actor["output"], "./OUTPUT_SCHEMA.json")
        self.assertTrue(actor["usesStandbyMode"])
        self.assertEqual(actor["webServerMcpPath"], "/mcp")

    def test_every_referenced_schema_file_exists_and_parses(self):
        actor = self._actor()
        refs = [actor["webServerSchema"], actor["storages"]["dataset"], actor["storages"]["keyValueStore"]]
        for ref in refs:
            self.assertIsInstance(ref, str)
            self.assertTrue(ref.startswith("./"), ref)
            json.loads((ACTOR_DIR / ref).read_text())

    def test_openapi_describes_the_real_routes(self):
        spec = json.loads((ACTOR_DIR / self._actor()["webServerSchema"]).read_text())
        self.assertTrue(spec["openapi"].startswith("3."))
        self.assertEqual(set(spec["paths"]), {"/", "/health", "/mcp"})
        self.assertIn("post", spec["paths"]["/mcp"])
        self.assertIn("get", spec["paths"]["/health"])
        self.assertIn("get", spec["paths"]["/"])

    def test_dataset_schema_has_views(self):
        schema = json.loads((ACTOR_DIR / self._actor()["storages"]["dataset"]).read_text())
        self.assertEqual(schema["actorSpecification"], 1)
        self.assertTrue(schema["views"])
        for view in schema["views"].values():
            self.assertIn("title", view)
            self.assertIn("transformation", view)
            self.assertEqual(view["display"]["component"], "table")

    def test_key_value_store_schema_collections(self):
        schema = json.loads((ACTOR_DIR / self._actor()["storages"]["keyValueStore"]).read_text())
        self.assertEqual(schema["actorKeyValueStoreSchemaVersion"], 1)
        self.assertIn("title", schema)
        self.assertTrue(schema["collections"])
        for name, collection in schema["collections"].items():
            self.assertIn("title", collection, name)
            self.assertEqual(("key" in collection) + ("keyPrefix" in collection), 1, name)


if __name__ == "__main__":
    unittest.main()
