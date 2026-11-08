"""Tests for match detail, live/day listing, H2H, team form, and named reasons."""
from __future__ import annotations

import asyncio
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from flashscore_mcp.extractors import live, match as match_ext, team
from flashscore_mcp.extractors.match_ref import resolve_match_ref, section_url
from flashscore_mcp.extractors.page_status import LoadFailed, page_outcome
from flashscore_mcp.extractors.team import parse_search_team_paths
from flashscore_mcp.parsers.match_detail import (
    parse_h2h,
    parse_incidents,
    parse_lineups,
    parse_stats,
    parse_summary,
)
from flashscore_mcp.parsers.matches import parse_matches


def _pad(html: str, size: int = 1600) -> str:
    return html + ("<!-- flashscore filler -->" * ((size // 20) + 1))


MATCH_ROW = """
<div class="event__title">ENGLAND: Premier League</div>
<div id="g_1_AbCd1234" class="event__match event__match--live" data-live="true">
  <a href="/match/football/arsenal-chelsea/AbCd1234/">detail</a>
  <div class="event__homeParticipant">Arsenal</div>
  <div class="event__awayParticipant">Chelsea</div>
  <div class="event__score--home">2</div>
  <div class="event__score--away">1</div>
  <div class="event__stageTime">67'</div>
</div>
<div id="g_1_EfGh5678" class="event__match">
  <div class="event__homeParticipant">Liverpool</div>
  <div class="event__awayParticipant">Everton</div>
  <div class="event__score--home">0</div>
  <div class="event__score--away">0</div>
  <div class="event__stageTime">02.11. 15:00</div>
</div>
<div class="event__match">
  <div class="event__homeParticipant">Spurs</div>
  <div class="event__awayParticipant">West Ham</div>
  <div class="event__stageTime">03.11. 20:00</div>
</div>
"""

SUMMARY_HTML = """
<div class="tournamentHeader__country">ENGLAND: Premier League</div>
<div class="duelParticipant__startTime">02.11.2024 17:30</div>
<div class="duelParticipant__home"><a class="participant__participantName">Arsenal</a></div>
<div class="detailScore__wrapper"><span>2</span><span>-</span><span>1</span></div>
<div class="detailScore__status">Finished</div>
<div class="duelParticipant__away"><a class="participant__participantName">Chelsea</a></div>
<div class="smv__incident smv__incidentHome">
  <div class="smv__timeBox">23'</div>
  <div class="smv__playerName">Saka</div>
  <div class="soccer-ball smv__incidentHomeScore">1 - 0</div>
</div>
<div class="smv__incident smv__incidentAway">
  <div class="smv__timeBox">40'</div>
  <div class="smv__playerName">Palmer</div>
  <div class="ycard">Yellow</div>
</div>
"""

STATS_HTML = """
<div class="stat__row">
  <div class="stat__homeValue">14</div>
  <div class="stat__categoryName">Shots</div>
  <div class="stat__awayValue">8</div>
</div>
<div class="wcl-homeValue__abc">1.9</div>
<div class="wcl-category__abc">Expected Goals (xG)</div>
<div class="wcl-awayValue__abc">0.7</div>
"""

LINEUPS_HTML = """
<div class="lf__lineUp">
  <div class="lf__side">
    <div class="lf__player"><span class="lf__number">7</span><a class="lf__playerName">Saka</a></div>
    <div class="lf__player"><span class="lf__number">8</span><a class="lf__playerName">Odegaard</a></div>
    <div class="lf__bench"></div>
    <div class="lf__player"><span class="lf__number">9</span><a class="lf__playerName">Gabriel Jesus</a></div>
  </div>
  <div class="lf__side">
    <div class="lf__player"><span class="lf__number">20</span><a class="lf__playerName">Palmer</a></div>
    <div class="lf__bench"></div>
    <div class="lf__player"><span class="lf__number">10</span><a class="lf__playerName">Mudryk</a></div>
  </div>
</div>
"""

H2H_HTML = """
<div class="h2h__row" id="g_1_HhHh1111">
  <span class="h2h__date">12.05.2024</span>
  <span class="h2h__homeParticipant">Arsenal</span>
  <span class="h2h__result"><span>5</span><span>0</span></span>
  <span class="h2h__awayParticipant">Chelsea</span>
</div>
<div class="h2h__row">
  <span class="h2h__date">21.10.2023</span>
  <span class="h2h__homeParticipant">Chelsea</span>
  <span class="h2h__result"><span>2</span><span>2</span></span>
  <span class="h2h__awayParticipant">Arsenal</span>
</div>
"""


class MatchIdsAndLiveFields(unittest.TestCase):
    def test_match_rows_expose_id_url_minute_and_competition(self):
        games = parse_matches(MATCH_ROW)
        self.assertEqual(len(games), 3)
        live_game = games[0]
        self.assertEqual(live_game.match_id, "AbCd1234")
        self.assertEqual(
            live_game.match_url,
            "https://www.flashscore.com/match/football/arsenal-chelsea/AbCd1234/",
        )
        self.assertEqual(live_game.status, "live")
        self.assertEqual(live_game.minute, "67'")
        self.assertEqual(live_game.competition, "ENGLAND: Premier League")
        self.assertEqual(games[1].match_id, "EfGh5678")
        self.assertTrue(games[1].match_url.endswith("/match/EfGh5678/"))
        self.assertEqual(games[2].status, "scheduled")
        self.assertIsNone(games[2].match_id)


class MatchRef(unittest.TestCase):
    def test_url_and_bare_id_resolve(self):
        match_id, url = resolve_match_ref("AbCd1234")
        self.assertEqual(match_id, "AbCd1234")
        self.assertEqual(url, "https://www.flashscore.com/match/AbCd1234/")
        match_id, url = resolve_match_ref(
            "https://www.flashscore.com/match/football/arsenal-chelsea/AbCd1234/#/match-summary"
        )
        self.assertEqual(match_id, "AbCd1234")
        self.assertTrue(url.endswith("/match/AbCd1234/"))
        self.assertIn("match-statistics", section_url(url, "stats"))
        self.assertIn("h2h/overall", section_url(url, "h2h"))

    def test_blank_match_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_match_ref("  ")


class MatchDetailParsers(unittest.TestCase):
    def test_summary_stats_incidents_lineups_h2h(self):
        summary = parse_summary(SUMMARY_HTML)
        self.assertEqual(summary["home_team"], "Arsenal")
        self.assertEqual(summary["away_team"], "Chelsea")
        self.assertEqual(summary["home_score"], 2)
        self.assertEqual(summary["away_score"], 1)
        self.assertEqual(summary["match_status"], "Finished")

        incidents = parse_incidents(SUMMARY_HTML)
        self.assertEqual(len(incidents), 2)
        self.assertEqual(incidents[0].player, "Saka")
        self.assertEqual(incidents[0].kind, "goal")
        self.assertEqual(incidents[0].team, "home")
        self.assertEqual(incidents[1].kind, "yellow-card")
        self.assertEqual(incidents[1].team, "away")

        stats = parse_stats(STATS_HTML)
        names = {item.name: item for item in stats}
        self.assertEqual(names["Shots"].home, "14")
        self.assertEqual(names["Expected Goals (xG)"].away, "0.7")

        lineups = parse_lineups(LINEUPS_HTML)
        by_name = {player.name: player for player in lineups}
        self.assertEqual(by_name["Saka"].team, "home")
        self.assertEqual(by_name["Saka"].role, "starter")
        self.assertEqual(by_name["Saka"].number, "7")
        self.assertEqual(by_name["Gabriel Jesus"].role, "bench")
        self.assertEqual(by_name["Palmer"].team, "away")
        self.assertEqual(by_name["Mudryk"].role, "bench")

        h2h = parse_h2h(H2H_HTML)
        self.assertEqual(len(h2h), 2)
        self.assertEqual(h2h[0].home_score, 5)
        self.assertEqual(h2h[0].match_id, "HhHh1111")


class GetMatchTool(unittest.TestCase):
    def test_partial_result_when_one_section_fails(self):
        async def fake_fetch(url, *args, **kwargs):
            if "match-statistics" in url:
                raise LoadFailed("stats down", reason="source-refused")
            if "lineups" in url:
                return _pad("<html>flashscore " + LINEUPS_HTML + "</html>")
            if "h2h" in url:
                return _pad("<html>flashscore " + H2H_HTML + "</html>")
            return _pad("<html>flashscore " + SUMMARY_HTML + "</html>")

        async def run() -> None:
            with patch("flashscore_mcp.extractors.match.fetch_html", side_effect=fake_fetch):
                detail = await match_ext.get_match("AbCd1234")
            self.assertEqual(detail.status, "partial")
            self.assertEqual(detail.reason, "section-failed")
            self.assertEqual(detail.home_team, "Arsenal")
            self.assertEqual(detail.errors.get("stats"), "source-refused")
            self.assertEqual(len(detail.incidents or []), 2)
            self.assertTrue(detail.lineups)
            self.assertTrue(detail.h2h)

        asyncio.run(run())


class LiveAndDay(unittest.TestCase):
    def test_live_filter_and_league_header(self):
        async def run() -> None:
            html = _pad("<html>flashscore " + MATCH_ROW + "</html>")
            with patch("flashscore_mcp.extractors.live.fetch_html", return_value=html):
                result = await live.get_live_matches("football")
            self.assertEqual(result.status, "ok")
            self.assertEqual(len(result.items), 1)
            self.assertEqual(result.items[0].home_team, "Arsenal")
            self.assertEqual(result.items[0].minute, "67'")

        asyncio.run(run())

    def test_day_listing_status_filter(self):
        async def run() -> None:
            html = _pad("<html>flashscore " + MATCH_ROW + "</html>")
            with patch("flashscore_mcp.extractors.live.fetch_html", return_value=html):
                scheduled = await live.get_matches_by_day("football", day_offset=0, status="scheduled")
                finished = await live.get_matches_by_day("soccer", day_offset=0, status="finished")
            self.assertEqual([game.home_team for game in scheduled.items], ["Spurs"])
            self.assertEqual([game.home_team for game in finished.items], ["Liverpool"])

        asyncio.run(run())

    def test_day_offset_from_iso_date(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self.assertEqual(live.resolve_day_offset(None, tomorrow), 1)
        self.assertEqual(live.normalize_sport("Soccer"), "football")


class HeadToHeadAndForm(unittest.TestCase):
    def test_h2h_from_match_respects_last_n(self):
        async def fake_fetch(url, *args, **kwargs):
            return _pad("<html>flashscore " + H2H_HTML + "</html>")

        async def run() -> None:
            with patch("flashscore_mcp.extractors.match.fetch_html", side_effect=fake_fetch):
                result = await match_ext.get_h2h(match="AbCd1234", last_n=1)
            self.assertEqual(len(result.items), 1)
            self.assertEqual(result.items[0].home_score, 5)

        asyncio.run(run())

    def test_team_form_from_results_url(self):
        html = _pad("<html>flashscore " + MATCH_ROW + "</html>")

        async def run() -> None:
            with patch("flashscore_mcp.extractors.team.fetch_html", return_value=html) as mocked:
                result = await team.get_team_form("https://www.flashscore.com/team/arsenal/hA1Zm19f/", last_n=2)
            self.assertEqual(result.status, "ok")
            self.assertEqual(len(result.items), 2)
            mocked.assert_called()
            self.assertIn("/team/arsenal/hA1Zm19f/results/", mocked.call_args.args[0])

        asyncio.run(run())

    def test_search_html_finds_team_paths(self):
        html = '<a href="/team/arsenal/hA1Zm19f/">Arsenal</a>'
        self.assertEqual(parse_search_team_paths(html), ["/team/arsenal/hA1Zm19f/"])

    def test_h2h_requires_match_or_both_teams(self):
        async def run() -> None:
            with self.assertRaises(ValueError):
                await match_ext.get_h2h(team_a="Arsenal")

        asyncio.run(run())


class NamedReasons(unittest.TestCase):
    def test_no_matches_scheduled_vs_source_refused_vs_parse_failed(self):
        empty = _pad(
            '<html>flashscore<div id="live-table" class="sportName event--leagues">'
            "There are no matches scheduled.</div></html>"
        )
        self.assertEqual(
            page_outcome(empty, tab="results", parsed_count=0),
            ("empty", "no-matches-scheduled"),
        )
        challenge = _pad("<html>Just a moment... cf-challenge flashscore</html>")
        self.assertEqual(
            page_outcome(challenge, tab="results", parsed_count=0),
            ("failed", "source-refused"),
        )
        broken = _pad('<html>flashscore<div id="g_3_abc" class="event__match">broken</div></html>')
        status, reason = page_outcome(broken, tab="results", parsed_count=0, raw_hints=1)
        self.assertEqual(status, "failed")
        self.assertEqual(reason, "parse-failed")

    def test_loadfailed_carries_reason(self):
        exc = LoadFailed("nope", reason="source-refused")
        self.assertEqual(exc.reason, "source-refused")


if __name__ == "__main__":
    unittest.main()
