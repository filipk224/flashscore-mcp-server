"""Paging, filters, compact rows, per-row rounds, stage fields and time zones (NFL feedback)."""
from __future__ import annotations

import asyncio
import json
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from flashscore_mcp.config import settings
from flashscore_mcp.extractors import listing, live
from flashscore_mcp.extractors.league_teams import infer_sport
from flashscore_mcp.extractors.listing import (
    Listing,
    batch_number,
    batch_url,
    build_filters,
    page_collection,
    rows_from,
    stop_rule,
)
from flashscore_mcp.models import CompactMatch, MatchResult
from flashscore_mcp.parsers.feed import initial_feeds, merge_listing, parse_list_feed
from flashscore_mcp.parsers.matches import parse_matches
from flashscore_mcp.parsers.stage import classify
from flashscore_mcp.timeutil import localize, today as utc_today, zone_name


def _ts(y, m, d, hh, mm=0) -> int:
    return int(datetime(y, m, d, hh, mm, tzinfo=timezone.utc).timestamp())


def _rec(mid, ts, home, away, rnd=None, hs=None, as_=None, ab="3"):
    parts = [f"AA÷{mid}", f"AD÷{ts}", f"AB÷{ab}", "AC÷3" if ab == "3" else "AC÷1", f"CX÷{home}", f"AE÷{home}", f"AF÷{away}"]
    if rnd:
        parts.append(f"ER÷{rnd}")
    if hs is not None:
        parts += [f"AG÷{hs}", f"AH÷{as_}", "BA÷7", "BB÷3"]
    parts += [f"WU÷{home.lower().replace(' ', '-')}", "PX÷HomeId01", f"WV÷{away.lower().replace(' ', '-')}", "PY÷AwayId01"]
    return "¬".join(parts) + "¬"


# An NFL-shaped feed, newest first: Super Bowl, Pro Bowl, a wild card game,
# then Round 18 (Sat + Sun) and the Monday night game of Round 17.
NFL_FEED = "~".join([
    "SA÷5¬",
    "ZA÷USA: NFL - Play Offs¬ZL÷/american-football/usa/nfl/¬",
    _rec("SuperBwl", _ts(2026, 2, 8, 23, 30), "New England Patriots", "Seattle Seahawks", "Final", 13, 29),
    "ZA÷USA: NFL - All Stars¬",
    _rec("ProBowl1", _ts(2026, 2, 4, 1, 0), "NFC", "AFC", "Final", 66, 52),
    "ZA÷USA: NFL - Play Offs¬",
    _rec("WildCrd1", _ts(2026, 1, 11, 18, 0), "Chicago Bears", "Green Bay Packers", "1/8-finals", 31, 27),
    "ZA÷USA: NFL¬",
    _rec("R18Sun01", _ts(2026, 1, 5, 1, 20), "Seattle Seahawks", "San Francisco 49ers", "Round 18", 13, 3),
    _rec("R18Sat01", _ts(2026, 1, 3, 21, 30), "Carolina Panthers", "Tampa Bay Buccaneers", "Round 18", 14, 16),
    _rec("R17Mon01", _ts(2025, 12, 30, 1, 15), "Atlanta Falcons", "Los Angeles Rams", "Round 17", 27, 24),
    "ZA÷USA: NFL - Pre-season¬",
    _rec("PreSea01", _ts(2025, 8, 8, 2, 0), "Seattle Seahawks", "Las Vegas Raiders", None, 23, 20),
    "",
])


def _page_html(feed: str, count: int, rendered: str = "") -> str:
    return (
        "<html><body>flashscore " + rendered +
        "<script>cjs.initialFeeds['results'] = {\n data: `" + feed + "`,\n allEventsCount: " + str(count) + ",\n seasonId: 187,\n}</script>"
        '<script>var x = {"feed_sign":"SIGN1234"};</script></body></html>'
    )


def _row(mid: str, home: str, away: str, pad: int = 3000) -> str:
    # Real NFL rows carry period scores and links; about 3.8 KB each.
    return (
        f'<div id="g_5_{mid}" class="event__match event__match--static">'
        f'<a href="/match/american-football/{mid}/" class="eventRowLink"></a>'
        '<div class="event__time">05.01. 01:20</div>'
        f'<div class="event__homeParticipant"><span>{home}</span></div>'
        f'<div class="event__awayParticipant"><span>{away}</span></div>'
        '<div class="event__score event__score--home">1</div><div class="event__score event__score--away">0</div>'
        f'<div class="filler">{"x" * pad}</div></div>'
    )


class StageFields(unittest.TestCase):
    def test_nfl_labels(self):
        self.assertEqual(classify("USA: NFL", "Round 7")["stage"], "regular_season")
        self.assertEqual(classify("USA: NFL", "Round 7")["round_number"], 7)
        wc = classify("USA: NFL - Play Offs", "1/8-finals")
        self.assertEqual((wc["stage"], wc["playoff_round"], wc["playoff_round_name"]), ("playoffs", "round_of_16", "Wild Card"))
        div = classify("USA: NFL - Play Offs", "Quarter-finals")
        self.assertEqual(div["playoff_round_name"], "Divisional Round")
        conf = classify("USA: NFL - Play Offs", "Semi-finals")
        self.assertEqual(conf["playoff_round_name"], "Conference Championship")
        sb = classify("USA: NFL - Play Offs", "Final")
        self.assertEqual((sb["playoff_round"], sb["playoff_round_name"]), ("final", "Super Bowl"))
        self.assertIsNone(sb["round_number"])

    def test_pro_bowl_final_is_all_star_not_playoffs(self):
        out = classify("USA: NFL - All Stars", "Final")
        self.assertEqual(out["stage"], "all_star")
        self.assertIsNone(out["playoff_round"])

    def test_preseason_and_others(self):
        self.assertEqual(classify("USA: NFL - Pre-season", None)["stage"], "preseason")
        self.assertEqual(classify("ENGLAND: Premier League", "Round 12")["round_number"], 12)
        self.assertEqual(classify("ENGLAND: Premier League", None)["stage"], "regular_season")
        cup = classify("EUROPE: Champions League - Play Offs", "Quarter-finals")
        self.assertEqual((cup["playoff_round"], cup["playoff_round_name"]), ("quarter_final", "Quarter-final"))
        self.assertEqual(classify(None, None)["stage"], None)


class ListFeed(unittest.TestCase):
    def test_rows_carry_their_own_round_kickoff_and_url(self):
        rows = {g.match_id: g for g in parse_list_feed(NFL_FEED)}
        self.assertEqual(len(rows), 7)
        mon = rows["R17Mon01"]
        self.assertEqual(mon.round, "Round 17")
        self.assertEqual(mon.kickoff_utc, "2025-12-30T01:15:00Z")
        self.assertEqual((mon.date, mon.time, mon.timezone), ("30.12.2025", "01:15", "UTC"))
        self.assertEqual(mon.competition, "USA: NFL")
        self.assertEqual(
            mon.match_url,
            f"{settings.base_url}/match/american-football/atlanta-falcons-HomeId01/los-angeles-rams-AwayId01/?mid=R17Mon01",
        )
        self.assertEqual(mon.extras["periods"][0], {"label": "1", "home": "7", "away": "3"})
        self.assertEqual(rows["ProBowl1"].competition, "USA: NFL - All Stars")

    def test_initial_feed_and_count(self):
        feeds = initial_feeds(_page_html(NFL_FEED, 335))
        data, count = feeds["results"]
        self.assertEqual(count, 335)
        self.assertEqual(len(parse_list_feed(data)), 7)

    def test_feed_round_wins_over_rendered_header(self):
        rendered = [MatchResult(home_team="Atlanta Falcons", away_team="Los Angeles Rams", match_id="R17Mon01",
                                round="Round 18", extras={"note": "x"}, match_url="https://x/match/full/?mid=R17Mon01")]
        merged = {g.match_id: g for g in merge_listing(parse_list_feed(NFL_FEED), rendered)}
        self.assertEqual(merged["R17Mon01"].round, "Round 17")
        self.assertEqual(merged["R17Mon01"].extras["note"], "x")
        self.assertEqual(merged["R17Mon01"].match_url, "https://x/match/full/?mid=R17Mon01")


class RenderedRoundAttribution(unittest.TestCase):
    def test_last_game_of_a_round_keeps_its_round(self):
        # Round header rows sit above the first game of each round only. With
        # long rows the old fixed look-back missed the header, and the last
        # game of Round 18 read 'Round 17' out of its own tail.
        html = (
            '<div class="event__round event__round--static">Round 18</div>'
            + _row("R18a0001", "A", "B") + _row("R18b0002", "C", "D") + _row("R18c0003", "E", "F")
            + '<div class="event__round event__round--static">Round 17</div>'
            + _row("R17a0004", "G", "H") + _row("R17b0005", "I", "J")
        )
        rounds = {g.match_id: g.round for g in parse_matches(html)}
        self.assertEqual(rounds, {
            "R18a0001": "Round 18", "R18b0002": "Round 18", "R18c0003": "Round 18",
            "R17a0004": "Round 17", "R17b0005": "Round 17",
        })

    def test_league_header_ends_a_round_block(self):
        html = (
            '<div class="event__round">Round 3</div>' + _row("Aaaaaaa1", "A", "B")
            + '<div data-testid="wcl-headerLeague"><span class="headerLeague__title-text">Cup</span></div>'
            + _row("Bbbbbbb2", "C", "D")
        )
        rounds = {g.match_id: g.round for g in parse_matches(html)}
        self.assertEqual(rounds["Aaaaaaa1"], "Round 3")
        self.assertIsNone(rounds["Bbbbbbb2"])


def _rows():
    rows, _count, _feed = rows_from(_page_html(NFL_FEED, 7), [], "results")
    return rows


class Paging(unittest.TestCase):
    def test_offsets_and_next_offset(self):
        rows = _rows()
        first = page_collection(rows, build_filters(), 0, 3, False, complete=True)
        self.assertEqual((first.returned, first.total, first.has_more, first.next_offset), (3, 7, True, 3))
        last = page_collection(rows, build_filters(), 6, 3, False, complete=True)
        self.assertEqual((last.returned, last.has_more, last.next_offset), (1, False, None))
        self.assertEqual(last.items[0].match_id, "PreSea01")

    def test_total_from_all_events_count_when_not_fully_loaded(self):
        page = page_collection(_rows(), build_filters(), 0, 2, True, complete=False, all_count=335)
        self.assertEqual((page.total, page.has_more, page.next_offset), (335, True, 2))

    def test_byte_budget_cuts_the_page(self):
        rows = _rows() * 40
        with patch.object(settings, "page_bytes", 3000):
            page = page_collection(rows, build_filters(), 0, None, False, complete=True)
        size = len(json.dumps(page.model_dump(), separators=(",", ":")))
        self.assertLess(size, 3600)
        self.assertTrue(page.has_more)
        self.assertEqual(page.next_offset, page.returned)
        self.assertTrue(any("Page cut" in n for n in page.notes))

    def test_default_page_fits_the_gateway(self):
        rows = _rows() * 60
        for compact in (False, True):
            page = page_collection(rows, build_filters(), 0, None, compact, complete=True)
            size = len(json.dumps(page.model_dump(), separators=(",", ":")))
            self.assertLess(size, 10000, compact)
            self.assertTrue(page.has_more)

    def test_compact_rows(self):
        page = page_collection(_rows(), build_filters(), 0, 2, True, complete=True)
        row = page.items[0]
        self.assertIsInstance(row, CompactMatch)
        self.assertEqual((row.id, row.score, row.stage, row.playoff_round), ("SuperBwl", "13-29", "playoffs", "final"))
        self.assertEqual(row.kickoff_utc, "2026-02-08T23:30:00Z")
        self.assertEqual(row.home, "New England Patriots")

    def test_bad_paging_arguments(self):
        with self.assertRaises(ValueError):
            listing.check_paging(-1, None)
        with self.assertRaises(ValueError):
            listing.check_paging(0, 0)


class Filters(unittest.TestCase):
    def test_round_stage_and_dates(self):
        rows = _rows()
        by_round = page_collection(rows, build_filters(round="Round 18"), 0, None, True, complete=True)
        self.assertEqual({r.id for r in by_round.items}, {"R18Sun01", "R18Sat01"})
        self.assertEqual(
            {r.id for r in page_collection(rows, build_filters(round="17"), 0, None, True, complete=True).items},
            {"R17Mon01"},
        )
        wc = page_collection(rows, build_filters(round="wild_card"), 0, None, True, complete=True)
        self.assertEqual([r.id for r in wc.items], ["WildCrd1"])
        sb = page_collection(rows, build_filters(round="Super Bowl"), 0, None, True, complete=True)
        self.assertEqual([r.id for r in sb.items], ["SuperBwl"])
        reg = page_collection(rows, build_filters(stage="regular season"), 0, None, True, complete=True)
        self.assertEqual(reg.total, 3)
        dated = page_collection(rows, build_filters("2026-01-01", "2026-01-31"), 0, None, True, complete=True)
        self.assertEqual({r.id for r in dated.items}, {"R18Sun01", "R18Sat01", "WildCrd1"})
        with self.assertRaises(ValueError):
            build_filters(stage="overtime")
        with self.assertRaises(ValueError):
            build_filters("2026-02-01", "2026-01-01")

    def test_date_filter_in_a_timezone(self):
        rows = _rows()
        # Monday night 30.12. 01:15 UTC is Monday 29.12. in New York.
        ny = page_collection(rows, build_filters("2025-12-29", "2025-12-29", timezone="America/New_York"),
                             0, None, False, complete=True)
        self.assertEqual([g.match_id for g in ny.items], ["R17Mon01"])
        self.assertEqual((ny.items[0].date, ny.items[0].time), ("29.12.2025", "20:15"))
        self.assertEqual(ny.items[0].kickoff_local, "2025-12-29T20:15-05:00")
        self.assertEqual(ny.timezone, "America/New_York")
        utc = page_collection(rows, build_filters("2025-12-29", "2025-12-29"), 0, None, False, complete=True)
        self.assertEqual(utc.items, [])

    def test_stop_rule(self):
        rows = _rows()
        self.assertTrue(stop_rule(build_filters(), 0, 3, True)(rows))
        self.assertFalse(stop_rule(build_filters(), 0, 10, True)(rows))
        # Results run newest first: a row before date_from means the range is loaded.
        self.assertTrue(stop_rule(build_filters("2025-12-01"), 0, None, True)(rows))
        self.assertFalse(stop_rule(build_filters("2025-01-01"), 0, None, True)(rows))
        self.assertFalse(stop_rule(build_filters(round="Round 1"), 0, 5, True)(rows))

    def test_closed_date_range_gives_a_total(self):
        page = page_collection(_rows(), build_filters("2026-01-01", "2026-01-31"), 0, None, True,
                               complete=False, all_count=335)
        self.assertEqual((page.total, page.has_more), (3, False))


class TimeZones(unittest.TestCase):
    def test_localize_and_labels(self):
        game = MatchResult(home_team="A", away_team="B", date="05.01.2026", time="01:20", kickoff_utc="2026-01-05T01:20:00Z")
        (local,) = localize([game], "America/Los_Angeles")
        self.assertEqual((local.date, local.time, local.timezone), ("04.01.2026", "17:20", "America/Los_Angeles"))
        (same,) = localize([game])
        self.assertEqual((same.date, same.timezone, same.kickoff_local), ("05.01.2026", "UTC", None))
        (no_ts,) = localize([MatchResult(home_team="A", away_team="B", date="05.01.26")], "Europe/London")
        self.assertEqual(no_ts.timezone, "UTC")
        with self.assertRaises(ValueError):
            zone_name("Mars/Olympus")

    def test_infer_sport_from_league(self):
        self.assertEqual(infer_sport("NFL", None), "american-football")
        self.assertEqual(infer_sport("/basketball/usa/nba/", None), "basketball")
        self.assertEqual(infer_sport("NFL", "football"), "football")
        self.assertEqual(infer_sport(None, None), "football")


class FeedBatches(unittest.TestCase):
    def test_batch_number_and_url(self):
        tr = "https://global.flashscore.ninja/2/x/feed/tr_2_200_rJVAIaHo_187_1_0_en_1"
        pr = "https://global.flashscore.ninja/2/x/feed/pr_2_200_f5h1oOee_2_0_en_1"
        self.assertEqual((batch_number(tr), batch_number(pr)), (1, 2))
        self.assertEqual(batch_url(tr, 3), "https://global.flashscore.ninja/2/x/feed/tr_2_200_rJVAIaHo_187_3_0_en_1")

    def test_cached_list_reads_next_batches_from_the_feed(self):
        url = "https://www.flashscore.com/american-football/usa/nfl-2025-2026/results/"
        more = "~".join(["SA÷5¬", "ZA÷USA: NFL¬", _rec("R16Thu01", _ts(2025, 12, 19, 1, 15), "X", "Y", "Round 16", 1, 0), ""])
        listing._cache[url] = listing._Cached(
            at=__import__("time").monotonic(), html=_page_html(NFL_FEED, 8), batches={},
            template="https://global.flashscore.ninja/2/x/feed/tr_2_200_T_187_1_0_en_1", sign="SIGN1234", complete=False,
        )
        calls = []

        async def fake_feed(u, sign, timeout=10.0):
            calls.append((u, sign))
            return 200, more

        async def run():
            with patch("flashscore_mcp.extractors.http_util.get_feed", side_effect=fake_feed):
                return await listing.fetch_listing(url, enough=lambda rows: len(rows) >= 8)

        try:
            out = asyncio.run(run())
        finally:
            listing._cache.pop(url, None)
        self.assertEqual(len(out.items), 8)
        self.assertTrue(out.complete)
        self.assertEqual(out.items[-1].round, "Round 16")
        self.assertEqual(calls, [("https://global.flashscore.ninja/2/x/feed/tr_2_200_T_187_1_0_en_1", "SIGN1234")])


class ReadListAndDays(unittest.TestCase):
    def test_results_tool_pages_a_season(self):
        from flashscore_mcp.extractors import results

        async def fake_listing(url, enough=None, **kwargs):
            rows = _rows()
            return Listing(items=rows, html="<html></html>", all_count=7, complete=True, from_feed=True)

        async def run():
            with patch.object(results, "fetch_listing", side_effect=fake_listing), \
                 patch.object(results, "resolve_league_ref", return_value="american-football/usa/nfl"), \
                 patch.object(results, "_season_tab_url", return_value="https://x/nfl-2025-2026/results/"):
                return await results.get_results_history("NFL", "2025/26", compact=True, offset=2, limit=2, stage="regular_season")

        page = asyncio.run(run())
        self.assertEqual([r.id for r in page.items], ["R17Mon01"])
        self.assertEqual((page.total, page.has_more, page.timezone), (3, False, "UTC"))

    def test_old_date_reads_that_seasons_results(self):
        target = "2025-12-29"
        seen = {}

        async def fake_season(resolved, day):
            seen["day"] = day
            return "https://www.flashscore.com/american-football/usa/nfl-2025-2026/", "NFL 2025/2026"

        async def fake_read_list(url, tab, **kwargs):
            seen.setdefault("urls", []).append(url)
            filters = build_filters(kwargs["date_from"], kwargs["date_to"], timezone=kwargs["timezone"])
            return page_collection(_rows(), filters, 0, None, kwargs["compact"], complete=True, notes=kwargs["notes"])

        async def run():
            with patch.object(live, "_season_url_for", side_effect=fake_season), \
                 patch.object(live, "read_list", side_effect=fake_read_list), \
                 patch.object(live, "_optional_league_path", return_value="american-football/usa/nfl"):
                return await live.get_matches_by_day("american-football", date=target, league="NFL", timezone="America/New_York")

        page = asyncio.run(run())
        self.assertEqual(seen["day"], date(2025, 12, 29))
        self.assertEqual(seen["urls"], ["https://www.flashscore.com/american-football/usa/nfl-2025-2026/results/"])
        self.assertEqual([g.match_id for g in page.items], ["R17Mon01"])
        self.assertIn("NFL 2025/2026", page.notes[0])

    def test_day_offset_uses_the_zone_today(self):
        tomorrow = (utc_today() + timedelta(days=1)).isoformat()
        self.assertEqual(live.resolve_day_offset(None, tomorrow), 1)


class H2hSeasonFeedFallback(unittest.TestCase):
    def test_old_season_meeting_found_from_the_feed(self):
        # The rendered page holds the 2026 season only and Show more does not
        # load (slow or 503 feed host); the page feed says 637 rows exist. The
        # 2024 meeting is read from the feed batches.
        import time as _time
        from contextlib import asynccontextmanager

        from flashscore_mcp.extractors import h2h_season as hs
        from flashscore_mcp.extractors.team import TeamRef

        sea = TeamRef("seattle-seahawks", "f5h1oOee", "Seattle Seahawks")
        buf = TeamRef("buffalo-bills", "t2lcn4tk", "Buffalo Bills")
        page_feed = "~".join(["SA÷5¬", "ZA÷USA: NFL¬",
                              _rec("Now00001", _ts(2026, 11, 15, 21, 5), "Seattle Seahawks", "Arizona Cardinals", "Round 11", 20, 17), ""])
        old = "~".join(["SA÷5¬", "ZA÷USA: NFL¬",
                        _rec("UgP5N0io", _ts(2024, 10, 27, 20, 25), "Seattle Seahawks", "Buffalo Bills", "Round 8", 10, 31),
                        _rec("Old00002", _ts(2024, 6, 1, 1, 0), "Seattle Seahawks", "Other Team", None, 1, 0),
                        _rec("Old00003", _ts(2024, 1, 7, 1, 0), "Seattle Seahawks", "Other Team", "Round 18", 1, 0),
                        _rec("Old00004", _ts(2024, 1, 1, 1, 0), "Seattle Seahawks", "Buffalo Bills", "Round 17", 1, 0), ""])

        class Page:
            async def content(self):
                return _page_html(page_feed, 637)

        @asynccontextmanager
        async def new_page(queue_wait_s=None):
            yield Page()

        async def noop(*a, **k):
            return False

        seen = {}

        async def fake_listing(url, enough=None, budget_s=None, **kwargs):
            seen["url"] = url
            rows = parse_list_feed(page_feed) + parse_list_feed(old)
            self.assertTrue(enough(rows))
            return Listing(items=rows, all_count=637, clicks=3, from_feed=True)

        plan_league = hs.LeagueSeasons("NFL", "2026/2027", ("NFL 2026/2027", "NFL 2025/2026", "NFL 2024/2025"))
        state = hs.SeasonScan()

        async def run():
            await hs.scan_season(sea, buf, "2024/25", state, _time.monotonic() + 30, today=date(2026, 11, 19),
                                 league_seasons=plan_league, league_given=True)

        with patch.object(hs.browser_manager, "new_page", new_page), \
             patch.object(hs, "_goto_list", noop), \
             patch.object(hs, "_show_more_once", noop), \
             patch.object(hs, "_visible_show_more", noop), \
             patch.object(listing, "fetch_listing", side_effect=fake_listing):
            asyncio.run(run())
        self.assertEqual(seen["url"], sea.url + "results/")
        self.assertEqual(list(state.items), ["UgP5N0io"])
        self.assertEqual(state.items["UgP5N0io"].date, "27.10.2024")
        self.assertEqual(state.items["UgP5N0io"].stage, "regular_season")
        self.assertFalse(state.capped)



class H2hBudget(unittest.TestCase):
    def test_full_history_reply_is_not_held_by_work_that_ignores_cancel(self):
        import time as _time

        from flashscore_mcp.errors import LoadFailed
        from flashscore_mcp.extractors import match

        async def stubborn(*args, **kwargs):
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                await asyncio.sleep(1.0)  # a navigation winding down long after the cancel
                raise

        async def run():
            with patch.object(match, "_full_history_h2h", stubborn), patch.object(settings, "h2h_budget_s", 0.2):
                start = _time.monotonic()
                with self.assertRaises(LoadFailed):
                    await match._get_h2h(team_a="A", team_b="B", season="all")
                return _time.monotonic() - start

        self.assertLess(asyncio.run(run()), 0.8)


if __name__ == "__main__":
    unittest.main()
