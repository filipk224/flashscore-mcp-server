"""Regression tests for the bugs found live-testing the deployed server (v0.2.3); fixed in v0.2.4.

Fixtures are trimmed copies of the markup Flashscore rendered in November 2026.
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from flashscore_mcp.extractors import live, match as match_ext
from flashscore_mcp.extractors.fetch import DayPage
from flashscore_mcp.extractors.match_page import MatchPage
from flashscore_mcp.extractors.match_ref import resolve_match_ref, section_url
from flashscore_mcp.extractors.page_status import page_outcome
from flashscore_mcp.extractors.team import TeamRef, pick_search_team, team_ref_from_url
from flashscore_mcp.parsers.feed import merge_rows, parse_day_feed
from flashscore_mcp.parsers.league import parse_league_page, parse_menu_countries
from flashscore_mcp.parsers.match_detail import (
    parse_h2h,
    parse_incidents,
    parse_lineups,
    parse_stats,
    parse_summary,
)
from flashscore_mcp.parsers.matches import parse_matches
from flashscore_mcp.parsers.news import normalize_news_date, parse_article_page, parse_news
from flashscore_mcp.parsers.standings import parse_standings


def _pad(html: str, size: int = 1600) -> str:
    return html + ("<!-- flashscore filler -->" * ((size // 20) + 1))


MID_URL = "https://www.flashscore.com/match/football/aston-villa-W00wmLO0/manchester-united-ppjDR086/?mid=Me9aWSp3"

DUEL = """
<nav class="wcl-breadcrumbs_0ZcSd detail__breadcrumbs--content" data-testid="wcl-breadcrumbs"><ol>
<li data-testid="wcl-breadcrumbsItem"><a><span>Football</span></a></li>
<li data-testid="wcl-breadcrumbsItem"><a><span>England</span></a></li>
<li data-testid="wcl-breadcrumbsItem"><a><span>Premier League - Round 10</span></a></li></ol></nav>
<div class="duelParticipant__container"><div class="duelParticipant">
<div class="duelParticipant__startTime"><div class="">09.11.2026 03:00</div></div>
<div class="duelParticipant__home "><button type="button" class="participant__myTeamsIcon"><svg><path d="M1"></path></svg></button>
<a class="participant__participantLink" href="/team/manchester-united/ppjDR086/"><img alt="Manchester Utd" src="x.png"></a>
<div class="participant__participantNameWrapper"><div class="participant__participantName participant__overflow">
<a href="/team/manchester-united/ppjDR086/" class="participant__participantName participant__overflow ">{home}</a></div></div></div>
<div class="duelParticipant__score"><div class="detailScore__matchInfo"><div class="detailScore__wrapper"><span>4</span><span class="detailScore__divider">-</span><span>4</span></div>
<div class="detailScore__statusWithPenalties"><div class="detailScore__status"><span class="fixedHeaderDuel__detailStatus">Finished</span><div class="eventAndAddedTime"></div></div></div></div></div>
<div class="duelParticipant__away "><div class="participant__participantNameWrapper"><div class="participant__participantName participant__overflow">
<a href="/team/aston-villa/W00wmLO0/" class="participant__participantName participant__overflow ">{away}</a></div></div></div>
</div></div>
"""

INCIDENTS = """
<div class="smv__verticalSections section"><ol class="smv__period-list">
<li class="smv__participantRow smv__awayParticipant"><div class="smv__incident"><div role="img" class="smv__timeBox">1'</div>
<button class="wcl-tooltip-trigger"><div class="smv__incidentIcon"><div class="smv__incidentAwayScore">0 - 1</div>
<svg data-testid="wcl-icon-incidents-goal-soccer"><path d="M1"></path></svg></div></button>
<a href="/player/alysson/2m3ojzuh/" class="smv__playerName"><div>Alysson</div></a>
<div class="smv__assist smv__assistAway"><span aria-hidden="true">(</span><a href="/player/x/">McGinn J.</a><span aria-hidden="true">)</span></div></div></li>
<li class="smv__participantRow smv__homeParticipant"><div class="smv__incident"><div role="img" class="smv__timeBox">16'</div>
<button><div class="smv__incidentIcon"><svg data-testid="wcl-icon-incidents-penalty-goal"><path d="M1"></path></svg>
<div class="smv__incidentHomeScore">1 - 2</div></div></button>
<a href="/player/fernandes-bruno/GYvAMDm2/" class="smv__playerName"><div>Fernandes B.</div></a><div class="smv__subIncident">(Penalty)</div></div></li>
<li class="smv__participantRow smv__homeParticipant"><div class="smv__incident"><div role="img" class="smv__timeBox">66'</div>
<button><div class="smv__incidentIconSub"><svg data-testid="wcl-icon-incidents-substitution"><path d="M1"></path></svg></div></button>
<a href="/player/mount-mason/lOA8VKIK/" class="smv__playerName">Mount M.</a>
<div class="smv__incidentSubOut "><a href="/player/t/" class="smv__subDown smv__playerName">Tielemans Y.</a></div></div></li>
<li class="smv__participantRow smv__awayParticipant"><div class="smv__incident"><div class="smv__timeBox">70'</div>
<svg data-testid="wcl-icon-incidents-yellow-card"><path d="M1"></path></svg>
<a class="smv__playerName">Konsa E.</a></div></li>
</ol></div>
"""

STATS = """
<div class="wcl-statistics_vZTGP" data-testid="wcl-statistics"><div class="wcl-labelRow_42JBQ">
<div><div class="wcl-value_Ywp3J">3.55</div></div>
<div class="wcl-label_sO4bA"><span class="wcl-name_2lXWg">Expected goals (xG)</span></div>
<div class="wcl-awayValue_smmfR"><div class="wcl-value_Ywp3J">2.88</div></div></div>
<div class="wcl-chart_K49-h"><div data-side="home"></div></div></div>
<div class="wcl-statistics_vZTGP" data-testid="wcl-statistics"><div class="wcl-labelRow_42JBQ">
<div><div class="wcl-value_Ywp3J">56%</div></div>
<div class="wcl-label_sO4bA"><span class="wcl-name_2lXWg">Ball possession</span></div>
<div class="wcl-awayValue_smmfR"><div class="wcl-value_Ywp3J">44%</div></div></div></div>
"""

def _lineup_player(side: str, number: str, name: str) -> str:
    return (
        f'<div class="wcl-participant_YylQz"><div class="wcl-participant_v7u5b" data-testid="wcl-lineupsParticipantGeneral-{side}">'
        f'<div class="wcl-mainRow_IaUrm"><span class="wcl-number_lTBFk">{number}</span><img alt="x">'
        f'<button class="wcl-nameWrapper_CgKPn"><span class="wcl-name_ZggyJ">{name}</span></button></div></div></div>'
    )


def _lineup_group(title: str, left: list[tuple[str, str]], right: list[tuple[str, str]]) -> str:
    return (
        '<div class="wcl-section_rcg7C" data-testid="wcl-lineupsGroup">'
        f'<div data-testid="wcl-headerSection-text"><span>{title}</span></div>'
        '<div class="wcl-sides_NDsxx"><div class="wcl-side_R64pI">'
        + "".join(_lineup_player("left", n, p) for n, p in left)
        + '</div><div class="wcl-side_R64pI">'
        + "".join(_lineup_player("right", n, p) for n, p in right)
        + "</div></div></div>"
    )


LINEUPS = (
    _lineup_group("Substituted players", [("", "Heaven A.")], [])
    + _lineup_group("Starting Lineups", [("1", "Lammens S."), ("3", "Mazraoui N.")], [("23", "Martinez E.")])
    + _lineup_group("Substitutes", [("6", "Heaven A.")], [("17", "Bailey L.")])
    + _lineup_group("Coaches", [("", "Carrick M.")], [("", "Emery U.")])
)


def _h2h_row(mid: str, day: str, home: str, away: str, hs: int, as_: int) -> str:
    return (
        f'<a href="https://www.flashscore.com/match/football/a-1/b-2/?mid={mid}" class="h2h__row ">'
        f'<span class="wclH2h__date"><span>{day}</span></span>'
        '<span class="h2h__event " title="Premier League (England)"><span>PL</span></span>'
        f'<div class="h2h__participant h2h__homeParticipant"><div><img alt="{home}"><span class="wcl-name_jjfMf">{home}</span></div></div>'
        f'<div class="h2h__participant h2h__awayParticipant"><div><span class="wcl-name_jjfMf">{away}</span></div></div>'
        f'<span class="h2h__result h2h__result--final"><span>{hs}</span><span>{as_}</span></span>'
        '<span class="h2h__icon"><div><span>D</span></div></span></a>'
    )


def _h2h_section(title: str, rows: str) -> str:
    return (
        '<div class="h2h__section section "><div data-testid="wcl-headerSection-text">'
        f'<span>{title}</span></div><div class="rows">{rows}</div></div>'
    )


H2H = '<div class="h2h">' + (
    _h2h_section("Last matches: Manchester Utd", _h2h_row("Me9aWSp3", "09.11.26", "Manchester Utd", "Aston Villa", 4, 4)
                 + _h2h_row("8rnngLzB", "05.11.26", "AS Roma", "Manchester Utd", 1, 1))
    + _h2h_section("Last matches: Aston Villa", _h2h_row("Qq1Qq1Qq", "02.11.26", "Aston Villa", "Leeds", 2, 0))
    + _h2h_section("Head-to-head matches", _h2h_row("Me9aWSp3", "09.11.26", "Manchester Utd", "Aston Villa", 4, 4)
                   + _h2h_row("UgXnfPvC", "16.03.26", "Manchester Utd", "Aston Villa", 3, 1))
) + "</div>"


class MatchDetailCurrentMarkup(unittest.TestCase):
    def test_placeholder_names_are_not_team_names(self):
        loading = parse_summary(DUEL.replace("{home}", "Loading...").replace("{away}", "Loading..."))
        self.assertIsNone(loading["home_team"])
        self.assertIsNone(loading["away_team"])

    def test_hydrated_summary(self):
        parsed = parse_summary(DUEL.replace("{home}", "Manchester Utd").replace("{away}", "Aston Villa"))
        self.assertEqual(parsed["home_team"], "Manchester Utd")
        self.assertEqual(parsed["away_team"], "Aston Villa")
        self.assertEqual((parsed["home_score"], parsed["away_score"]), (4, 4))
        self.assertEqual(parsed["match_status"], "Finished")
        self.assertIsNone(parsed["minute"])
        self.assertEqual((parsed["date"], parsed["time"]), ("09.11.2026", "03:00"))
        self.assertEqual(parsed["competition"], "ENGLAND: Premier League - Round 10")

    def test_incidents_team_kind_and_notes(self):
        incidents = parse_incidents(INCIDENTS)
        self.assertEqual(len(incidents), 4)
        first, pen, sub, card = incidents
        self.assertEqual((first.team, first.kind, first.player, first.score), ("away", "goal", "Alysson", "0 - 1"))
        self.assertEqual(first.note, "Assist: McGinn J.")
        self.assertEqual((pen.team, pen.kind, pen.note), ("home", "goal", "Penalty"))
        self.assertEqual((sub.kind, sub.player, sub.note), ("substitution", "Mount M.", "Out: Tielemans Y."))
        self.assertEqual((card.team, card.kind), ("away", "yellow-card"))

    def test_stats(self):
        stats = {item.name: item for item in parse_stats(STATS)}
        self.assertEqual((stats["Expected goals (xG)"].home, stats["Expected goals (xG)"].away), ("3.55", "2.88"))
        self.assertEqual(stats["Ball possession"].home, "56%")

    def test_lineups_roles_and_sides(self):
        players = parse_lineups(LINEUPS)
        by = {(p.name, p.role): p for p in players}
        self.assertEqual(by[("Lammens S.", "starter")].team, "home")
        self.assertEqual(by[("Lammens S.", "starter")].number, "1")
        self.assertEqual(by[("Martinez E.", "starter")].team, "away")
        self.assertEqual(by[("Heaven A.", "bench")].number, "6")
        self.assertEqual(by[("Emery U.", "coach")].team, "away")
        # "Substituted players" repeats the bench and is skipped.
        self.assertEqual(sum(1 for p in players if p.name == "Heaven A."), 1)

    def test_h2h_reads_only_meetings_with_mid_ids(self):
        rows = parse_h2h(H2H)
        self.assertEqual([r.match_id for r in rows], ["Me9aWSp3", "UgXnfPvC"])
        self.assertEqual((rows[1].home_score, rows[1].away_score), (3, 1))
        self.assertEqual(rows[0].competition, "Premier League (England)")
        self.assertTrue(rows[0].match_url.endswith("?mid=Me9aWSp3"))

    def test_h2h_without_meetings_is_empty(self):
        only_form = '<div class="h2h">' + _h2h_section(
            "Last matches: A", _h2h_row("Zz1Zz1Zz", "01.11.26", "A", "C", 1, 0)
        ) + "</div>"
        self.assertEqual(parse_h2h(only_form), [])
        self.assertEqual(page_outcome(_pad("<html>flashscore No matches found.</html>"), tab="h2h", parsed_count=0), ("empty", "no-meetings"))


class MatchRefsCurrentUrls(unittest.TestCase):
    def test_mid_urls_resolve_to_the_match_not_the_sport(self):
        self.assertEqual(resolve_match_ref(MID_URL)[0], "Me9aWSp3")
        self.assertEqual(resolve_match_ref(MID_URL.replace("/?mid", "/h2h/overall/?mid"))[0], "Me9aWSp3")
        with self.assertRaises(ValueError):
            resolve_match_ref("/match/football/aston-villa-W00wmLO0/manchester-united-ppjDR086/")

    def test_section_urls_use_current_paths(self):
        self.assertEqual(
            section_url(MID_URL, "stats"),
            "https://www.flashscore.com/match/football/aston-villa-W00wmLO0/manchester-united-ppjDR086/summary/stats/?mid=Me9aWSp3",
        )
        self.assertIn("/h2h/overall/?mid=Me9aWSp3", section_url(MID_URL, "h2h"))
        self.assertIn("/summary/lineups/?mid=", section_url(MID_URL, "lineups"))


def _page(**html) -> MatchPage:
    page = MatchPage()
    page.url = MID_URL
    page.html = {key: _pad("<html>flashscore " + value + "</html>") for key, value in html.items()}
    return page


class GetMatchAndH2HTools(unittest.TestCase):
    def test_get_match_all_sections_from_one_page(self):
        duel = DUEL.replace("{home}", "Manchester Utd").replace("{away}", "Aston Villa")

        async def fake_load(url, sections, h2h_more=0, **kwargs):
            return _page(summary=duel + INCIDENTS, stats=duel + STATS, lineups=duel + LINEUPS, h2h=duel + H2H)

        async def run():
            with patch("flashscore_mcp.extractors.match.load_match_page", side_effect=fake_load):
                detail = await match_ext.get_match("Me9aWSp3")
            self.assertEqual(detail.status, "ok")
            self.assertEqual(detail.home_team, "Manchester Utd")
            self.assertEqual(detail.match_url, MID_URL)
            self.assertEqual(len(detail.incidents), 4)
            self.assertEqual(len(detail.stats), 2)
            self.assertTrue(detail.lineups)
            self.assertEqual(len(detail.h2h), 2)
            self.assertEqual(detail.errors, {})

        asyncio.run(run())

    def test_unhydrated_page_is_a_failure_not_loading_names(self):
        loading = DUEL.replace("{home}", "Loading...").replace("{away}", "Loading...")

        async def fake_load(url, sections, h2h_more=0, **kwargs):
            page = _page(summary=loading)
            page.errors = {"stats": "timeout"}
            return page

        async def run():
            with patch("flashscore_mcp.extractors.match.load_match_page", side_effect=fake_load):
                detail = await match_ext.get_match("Me9aWSp3", ["summary", "stats"])
            self.assertIsNone(detail.home_team)
            self.assertNotEqual(detail.status, "ok")

        asyncio.run(run())

    def test_h2h_by_team_names_reads_a_meeting_page(self):
        refs = {
            "Arsenal": TeamRef("arsenal", "hA1Zm19f", "Arsenal"),
            "Chelsea": TeamRef("chelsea", "4fGZN2oK", "Chelsea"),
        }
        fixtures = _pad(
            '<html>flashscore <div class="sportName soccer">'
            '<div id="g_1_KkKkKkKk" class="event__match event__match--scheduled">'
            '<a href="https://www.flashscore.com/match/football/arsenal-hA1Zm19f/chelsea-4fGZN2oK/?mid=KkKkKkKk" class="eventRowLink"></a>'
            '<div class="event__time">14.12. 03:30</div>'
            '<div class="event__homeParticipant"><span>Chelsea</span></div>'
            '<div class="event__awayParticipant"><span>Arsenal</span></div></div></div></html>'
        )
        meetings = '<div class="h2h">' + _h2h_section(
            "Head-to-head matches", _h2h_row("AaAaAaAa", "07.09.26", "Arsenal", "Chelsea", 2, 1)
        ) + "</div>"
        loaded = []

        async def fake_resolve(name):
            return refs[name]

        async def fake_fetch(url, *args, **kwargs):
            self.assertIn("/team/arsenal/hA1Zm19f/", url)
            return fixtures

        async def fake_load(url, sections, h2h_more=0, **kwargs):
            loaded.append(url)
            return _page(h2h=DUEL.replace("{home}", "Chelsea").replace("{away}", "Arsenal") + meetings)

        async def run():
            with patch("flashscore_mcp.extractors.match.resolve_team", side_effect=fake_resolve), \
                 patch("flashscore_mcp.extractors.match.fetch_html", side_effect=fake_fetch), \
                 patch("flashscore_mcp.extractors.match.load_match_page", side_effect=fake_load):
                result = await match_ext.get_h2h(team_a="Arsenal", team_b="Chelsea", season="all")
            self.assertEqual(result.status, "ok")
            self.assertEqual([(g.home_team, g.home_score, g.away_score) for g in result.items], [("Arsenal", 2, 1)])
            self.assertIn("/match/KkKkKkKk/", loaded[0])

        asyncio.run(run())


class TeamResolution(unittest.TestCase):
    SEARCH = [
        {"id": "8CKOoQdn", "url": "arsenal", "name": "Arsenal W", "type": {"id": 2}, "gender": {"name": "Women"},
         "defaultCountry": {"name": "England"}},
        {"id": "zoYzAZW6", "url": "arsenal-sarandi", "name": "Arsenal Sarandi", "type": {"id": 2},
         "gender": {"name": "Men"}, "defaultCountry": {"name": "Argentina"}},
        {"id": "hA1Zm19f", "url": "arsenal", "name": "Arsenal", "type": {"id": 2}, "gender": {"name": "Men"},
         "defaultCountry": {"name": "England"}},
        {"id": "p1", "url": "saka-bukayo", "name": "Saka Bukayo", "type": {"id": 3}},
    ]

    def test_exact_men_team_wins(self):
        ref = pick_search_team(self.SEARCH, "Arsenal")
        self.assertEqual(ref.path, "/team/arsenal/hA1Zm19f/")

    def test_country_hint_filters(self):
        ref = pick_search_team(self.SEARCH, "Arsenal", "Argentina")
        self.assertEqual(ref.id, "zoYzAZW6")

    def test_url_still_parses(self):
        self.assertEqual(team_ref_from_url("/team/arsenal/hA1Zm19f/").id, "hA1Zm19f")
        self.assertIsNone(pick_search_team({"error": 1}, "Arsenal"))


SEO_MENU = (
    '<div id="category-left-menu"><a class="lmc__element lmc__item " href="/football/albania/">'
    '<span class="lmc__elementName">Albania</span></a><span class="lmc__itemMore">Show more</span></div>'
    '<div class="left_menu_categories_seo"> '
    + " ".join(f'<a href="/football/{slug}/">{name}</a>' for slug, name in [
        ("albania", "Albania"), ("botswana", "Botswana"), ("england", "England"),
        ("antigua-barbuda", "Antigua &amp; Barbuda"), ("world", "World"),
    ])
    + ' <a href="/football/england/premier-league/">Premier League</a> </div>'
)


class CountriesAndLeague(unittest.TestCase):
    def test_full_country_list_from_menu_seo_block(self):
        found = parse_menu_countries(SEO_MENU, "football")
        slugs = [slug for _name, slug, _path in found]
        self.assertEqual(slugs, ["albania", "botswana", "england", "antigua-barbuda", "world"])
        self.assertIn(("Antigua & Barbuda", "antigua-barbuda", "/football/antigua-barbuda/"), found)

    def test_league_sport_is_the_menu_slug(self):
        html = ('<link rel="canonical" href="https://www.flashscore.com/football/england/premier-league/">'
                '<script>var x = {"sport":"soccer"};</script><h1>Premier League</h1>')
        self.assertEqual(parse_league_page(html).sport, "football")
        self.assertEqual(parse_league_page('<script>{"sport":"soccer"}</script>').sport, "football")


HEADER = (
    '<div class="headerLeague__wrapper"><div class="headerLeague" data-testid="wcl-headerLeague">'
    '<a title="Premier League" href="/football/england/premier-league/" class="headerLeague__title">'
    '<span class="headerLeague__title-text">Premier League</span></a><div class="headerLeague__meta">'
    '<span class="headerLeague__category"><span class="headerLeague__category-text">ENGLAND</span></span></div></div></div>'
)


def _row(mid: str, cls: str, stage: str, home: str, away: str, hs: str = "", as_: str = "", live_attr: str = "false") -> str:
    scores = ""
    if hs != "":
        scores = (
            f'<span class="event__score event__score--home" data-live="{live_attr}">{hs}</span>'
            f'<span class="event__score event__score--away" data-live="{live_attr}">{as_}</span>'
        )
    return (
        f'<div id="g_1_{mid}" class="event__match event__match--withRowLink {cls} event__match--twoLine">'
        f'<a href="https://www.flashscore.com/match/football/a-1/b-2/?mid={mid}" class="eventRowLink"></a>'
        f'<div class="event__stage"><div class="event__stage--block">{stage}</div></div>'
        f'<div class="event__homeParticipant"><span class="wcl-name_jjfMf">{home}</span></div>'
        f'<div class="event__awayParticipant"><span class="wcl-name_jjfMf">{away}</span></div>{scores}</div>'
    )


DAY_ROWS = HEADER + (
    _row("LiveLive", "event__match--live", '2<span class="blink">&nbsp;</span>', "Viktoria", "Ahrobiznes", "1", "0", "true")
    + _row("FroFro11", "event__match--live", "FRO", "Lower A", "Lower B")
    + _row("PostPon1", "", "Postponed", "Urartu", "Ararat")
    + _row("AfterPen", "", "After Pen.", "Vasco", "Palmeiras", "2", "1")
    + _row("Finish01", "", "Finished", "Brighton", "Brentford", "2", "0")
    + '<div id="g_1_Sched001" class="event__match event__match--scheduled">'
      '<a href="/match/football/c-3/d-4/?mid=Sched001" class="eventRowLink"></a>'
      '<div class="event__time">23:00</div><div class="event__homeParticipant"><span>Wadi Degla</span></div>'
      '<div class="event__awayParticipant"><span>Kahrabaa</span></div></div>'
)


class MatchRowStatuses(unittest.TestCase):
    def test_statuses_minutes_competition_and_urls(self):
        games = {g.match_id: g for g in parse_matches(DAY_ROWS)}
        live_game = games["LiveLive"]
        self.assertEqual((live_game.status, live_game.minute), ("live", "2'"))
        self.assertEqual((live_game.home_score, live_game.away_score), (1, 0))
        self.assertEqual(live_game.competition, "ENGLAND: Premier League")
        self.assertTrue(live_game.match_url.endswith("?mid=LiveLive"))
        self.assertIsNone(games["FroFro11"].minute)
        self.assertIn("Final result only", games["FroFro11"].extras.get("note", ""))
        self.assertEqual(games["PostPon1"].status, "postponed")
        self.assertEqual(games["AfterPen"].status, "finished")
        self.assertEqual(games["Finish01"].status, "finished")
        self.assertEqual((games["Sched001"].status, games["Sched001"].time), ("scheduled", "23:00"))


def _ts(day: date, hh: int, mm: int = 0) -> int:
    return int(datetime(day.year, day.month, day.day, hh, mm).timestamp())


def _feed(today: date) -> str:
    yday = today - timedelta(days=1)
    return "~".join([
        "SA÷1¬",
        "ZA÷ENGLAND: Premier League¬ZL÷/football/england/premier-league/¬",
        f"AA÷Finish01¬AD÷{_ts(today, 0, 30)}¬AB÷3¬AC÷3¬AE÷Brighton¬AF÷Brentford¬AG÷2¬AH÷0¬",
        f"AA÷Hidden01¬AD÷{_ts(today, 2, 0)}¬AB÷3¬AC÷3¬AE÷Sunderland¬AF÷Chelsea¬AG÷1¬AH÷0¬",
        f"AA÷Yday0001¬AD÷{_ts(yday, 23, 30)}¬AB÷3¬AC÷3¬AE÷Late¬AF÷Game¬AG÷1¬AH÷1¬",
        "ZA÷SPAIN: LaLiga¬ZL÷/football/spain/laliga/¬",
        f"AA÷Sched001¬AD÷{_ts(today, 23, 0)}¬AB÷1¬AC÷1¬AE÷Wadi Degla¬AF÷Kahrabaa¬",
        f"AA÷PostPon1¬AD÷{_ts(today, 1, 0)}¬AB÷3¬AC÷4¬AE÷Urartu¬AF÷Ararat¬",
        "",
    ])


class DayFeed(unittest.TestCase):
    def test_feed_has_every_game_with_kickoff(self):
        today = date.today()
        games = {g.match_id: g for g in parse_day_feed(_feed(today))}
        self.assertEqual(games["Hidden01"].date, today.strftime("%d.%m.%Y"))
        self.assertEqual(games["Hidden01"].time, "02:00")
        self.assertEqual(games["PostPon1"].status, "postponed")
        self.assertEqual(games["Sched001"].competition, "SPAIN: LaLiga")
        self.assertIsNone(games["Sched001"].home_score)
        only_pl = parse_day_feed(_feed(today), "football/england/premier-league")
        self.assertEqual({g.match_id for g in only_pl}, {"Finish01", "Hidden01", "Yday0001"})

    def test_merge_keeps_rendered_detail(self):
        merged = {g.match_id: g for g in merge_rows(parse_day_feed(_feed(date.today())), parse_matches(DAY_ROWS))}
        self.assertEqual(merged["Finish01"].time, "00:30")
        self.assertTrue(merged["Finish01"].match_url.endswith("?mid=Finish01"))
        self.assertIn("LiveLive", merged)  # rendered-only rows survive

    def test_day_listing_uses_target_date_and_feed(self):
        today = date.today()

        async def fake_day(url, offset=0, live_tab=False):
            self.assertEqual(offset, -1)
            yday = today - timedelta(days=1)
            feed = "~".join([
                "ZA÷ENGLAND: Premier League¬ZL÷/football/england/premier-league/¬",
                f"AA÷Old00001¬AD÷{_ts(yday, 15, 0)}¬AB÷3¬AC÷3¬AE÷A¬AF÷B¬AG÷1¬AH÷0¬",
                f"AA÷Next0001¬AD÷{_ts(today, 0, 30)}¬AB÷3¬AC÷3¬AE÷C¬AF÷D¬AG÷0¬AH÷0¬",
            ])
            return DayPage(html=_pad("<html>flashscore</html>"), feed=feed, offset=offset)

        async def run():
            with patch("flashscore_mcp.extractors.live.fetch_day", side_effect=fake_day):
                result = await live.get_matches_by_day("football", day_offset=-1, status="finished")
            self.assertEqual([g.match_id for g in result.items], ["Old00001"])
            self.assertEqual(result.items[0].date, (today - timedelta(days=1)).strftime("%d.%m.%Y"))
            self.assertEqual(result.items[0].time, "15:00")

        asyncio.run(run())


STANDINGS = """
<div class="ui-table"><div class="ui-table__header">
<div class="ui-table__headerCell ui-table__headerCell--rank">#</div>
<div class="ui-table__headerCell ui-table__headerCell--participant">Team</div>
<div class="ui-table__headerCell">MP</div><div class="ui-table__headerCell">PTS</div>
<div class="ui-table__headerCell ui-table__headerCell--form">Form</div></div>
<div class="ui-table__body"><div class="ui-table__row">
<div class="table__cell table__cell--rank"><div class="tableCellRank">20.</div></div>
<div class="table__cell table__cell--participant"><a class="tableCellParticipant__name">Crystal Palace</a></div>
<span class="table__cell table__cell--value">10</span><span class="table__cell table__cell--value table__cell--points">7</span>
<div class="table__cell table__cell--form">
<a href="/m/?mid=1" class="tableCellFormIcon tableCellFormIcon--TBD"><div data-testid="wcl-badgeForm-unknown"><span>?</span></div></a>
<a href="/m/?mid=2" class="tableCellFormIcon"><div data-testid="wcl-badgeForm-lose"><span>L</span></div></a>
<a href="/m/?mid=3" class="tableCellFormIcon"><div data-testid="wcl-badgeForm-lose"><span>L</span></div></a>
<a href="/m/?mid=4" class="tableCellFormIcon"><div data-testid="wcl-badgeForm-draw"><span>D</span></div></a>
<a href="/m/?mid=5" class="tableCellFormIcon"><div data-testid="wcl-badgeForm-lose"><span>L</span></div></a>
<a href="/m/?mid=6" class="tableCellFormIcon"><div data-testid="wcl-badgeForm-win"><span>W</span></div></a>
</div></div></div></div>
<div class="tableLegend"><div class="tableLegend__row"><span>Promotion - Champions League (League phase)</span></div>
<div class="tableLegend__row"><span>Relegation - Championship</span></div><div>W D L T</div></div>
"""


class StandingsForm(unittest.TestCase):
    def test_last_row_form_is_five_played_results(self):
        page = parse_standings(STANDINGS)
        row = page.sections[0].rows[0]
        self.assertEqual(row.team, "Crystal Palace")
        self.assertEqual(row.form, "LLDLW")


NEWS_LIST = """
<a class="wcl-article_UN5m8" data-testid="wcl-newsArticlePreview" title="Winners and Losers"
 href="https://www.flashscore.com/news/winners-and-losers/GKYtHp9U/" target="_blank"><div><h3>Winners and Losers</h3>
<div data-testid="wcl-newsMetaGroup"><div class="wcl-metaInfo_7JoZH"><div data-testid="wcl-newsMetaInfo"><span>2 h ago</span></div></div></div></div></a>
<a class="wcl-article_UN5m8" data-testid="wcl-newsArticlePreview" title="Older"
 href="https://www.flashscore.com/news/older/Gv7NbZGa/"><div><div data-testid="wcl-newsMetaInfo"><span>07.11.2026 09:41</span></div></div></a>
"""

ARTICLE = (
    '<meta name="description" content="The final weekend brought plenty of talking points &amp; more.">'
    '<script>{"body":"x","published":1794207682,"editedAt":null,"credit":"P","url":"https:\\/\\/www.flashscore.com\\/news\\/winners-and-losers\\/GKYtHp9U\\/"}</script>'
)


class NewsDatesAndSummaries(unittest.TestCase):
    def test_list_dates_are_normalized(self):
        now = datetime(2026, 11, 9, 19, 30)
        items = parse_news(NEWS_LIST, now=now)
        self.assertEqual(items[0].date, "09.11.2026 17:30")
        self.assertEqual(items[1].date, "07.11.2026 09:41")
        self.assertEqual(normalize_news_date("Yesterday 18:33", now), "08.11.2026 18:33")

    def test_article_page_gives_summary_and_exact_time(self):
        found = parse_article_page(ARTICLE, "https://www.flashscore.com/news/winners-and-losers/GKYtHp9U/")
        self.assertEqual(found["summary"], "The final weekend brought plenty of talking points & more.")
        self.assertEqual(found["date"], datetime.fromtimestamp(1794207682).strftime("%d.%m.%Y %H:%M"))


if __name__ == "__main__":
    unittest.main()


class OddsEmptyMessageTests(unittest.TestCase):
    def test_no_betting_odds_message_is_empty_not_failed(self):
        from flashscore_mcp.extractors.page_status import page_outcome

        html = _pad(
            "<html><script>grecaptcha captcha</script>flashscore"
            "<div>No betting odds were found.</div></html>"
        )
        self.assertEqual(page_outcome(html, tab="odds", parsed_count=0), ("empty", "no-data"))
