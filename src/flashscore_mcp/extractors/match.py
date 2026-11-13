"""Single-match detail and head-to-head."""
from __future__ import annotations

import asyncio
import time
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from loguru import logger

from ..models import MatchCollection, MatchDetail, MatchResult
from ..parsers.adapter import count_match_hints
from ..parsers.match_detail import parse_h2h, parse_incidents, parse_lineups, parse_stats, parse_summary
from .fetch import fetch_html
from ..seasons import SeasonPlan, parse_label
from .h2h_season import SeasonScan, scan_season
from .match_page import load_match_page
from .match_ref import resolve_match_ref
from ..config import settings
from ..errors import SECTION_TIMEOUT, BusyError
from .page_status import LoadFailed, page_outcome
from .team import TeamRef, resolve_team
from ..parsers.matches import parse_matches

ALL_SECTIONS = ("summary", "stats", "incidents", "lineups", "h2h")


def normalize_sections(sections: Optional[Iterable[str]]) -> list[str]:
    if not sections:
        return list(ALL_SECTIONS)
    wanted: list[str] = []
    aliases = {"statistics": "stats", "line-ups": "lineups", "lineup": "lineups", "events": "incidents"}
    for raw in sections:
        name = aliases.get(str(raw).strip().lower(), str(raw).strip().lower())
        if name in ALL_SECTIONS and name not in wanted:
            wanted.append(name)
    if not wanted:
        raise ValueError(
            "sections must be one or more of: summary, stats, incidents, lineups, h2h"
        )
    return wanted


def _apply_summary(detail: MatchDetail, parsed: dict) -> None:
    detail.home_team = parsed.get("home_team") or detail.home_team
    detail.away_team = parsed.get("away_team") or detail.away_team
    detail.home_score = parsed.get("home_score") if parsed.get("home_score") is not None else detail.home_score
    detail.away_score = parsed.get("away_score") if parsed.get("away_score") is not None else detail.away_score
    detail.match_status = parsed.get("match_status") or detail.match_status
    detail.minute = parsed.get("minute") or detail.minute
    detail.competition = parsed.get("competition") or detail.competition
    detail.date = parsed.get("date") or detail.date
    detail.time = parsed.get("time") or detail.time


def _section_outcome(html: str, tab: str, hints: int = 0) -> tuple[str, str | None]:
    return page_outcome(html, tab=tab, parsed_count=0, raw_hints=hints)


async def get_match(
    match: str,
    sections: Optional[list[str]] = None,
    h2h_more: int = 0,
) -> MatchDetail:
    match_id, match_url = resolve_match_ref(match)
    wanted = normalize_sections(sections)
    detail = MatchDetail(match_id=match_id, match_url=match_url, status="ok")

    plan: list[str] = []
    if "summary" in wanted or "incidents" in wanted:
        plan.append("summary")
    for name in ("stats", "lineups", "h2h"):
        if name in wanted:
            plan.append(name)

    page = await load_match_page(match_url, plan, h2h_more=h2h_more)
    if page.url and "mid=" in page.url:
        detail.match_url = page.url.split("#", 1)[0]
    fetched = page.html
    for name, reason in page.errors.items():
        detail.errors[name] = reason
        if name == "summary" and "incidents" in wanted:
            detail.errors.setdefault("incidents", reason)

    # Identity comes from whichever tab loaded: the duel header is on every tab.
    for name in ("summary", "h2h", "stats", "lineups"):
        html = fetched.get(name)
        if html:
            _apply_summary(detail, parse_summary(html))
            if detail.home_team and detail.away_team:
                break

    summary_html = fetched.get("summary")
    if summary_html:
        if "summary" in wanted:
            parsed = parse_summary(summary_html)
            detail.summary = {key: value for key, value in parsed.items() if value is not None}
        if "incidents" in wanted:
            incidents = parse_incidents(summary_html)
            if incidents:
                detail.incidents = incidents
                detail.errors.pop("incidents", None)
            elif "incidents" in detail.errors:
                pass  # the timeline did not render in time: keep the timeout error
            elif detail.home_team and detail.away_team:
                # Hydrated page with no timeline: a scheduled game or one
                # without incidents is empty, not failed.
                detail.incidents = []
            else:
                outcome = _section_outcome(summary_html, "match", count_match_hints(summary_html))
                detail.errors["incidents"] = outcome[1] if outcome[0] == "failed" else "parse-failed"

    parsers = {"stats": parse_stats, "lineups": parse_lineups, "h2h": parse_h2h}
    for name, parser in parsers.items():
        if name not in wanted:
            continue
        if name in page.missing:
            setattr(detail, name, [])
            continue
        html = fetched.get(name)
        if html is None:
            detail.errors.setdefault(name, "source-refused")
            continue
        items = parser(html)
        if items:
            setattr(detail, name, items)
            continue
        hydrated = bool(detail.home_team and detail.away_team)
        outcome = _section_outcome(html, "h2h" if name == "h2h" else "match")
        if hydrated or outcome[0] != "failed":
            setattr(detail, name, [])
        else:
            detail.errors[name] = outcome[1] or "parse-failed"

    detail.errors = {key: value for key, value in detail.errors.items() if value}

    got_identity = bool(detail.home_team and detail.away_team)
    requested_payload = any(
        getattr(detail, name) for name in ("summary", "stats", "incidents", "lineups", "h2h")
    )
    if detail.errors and (got_identity or requested_payload):
        detail.status = "partial"
        detail.reason = "section-failed"
    elif not got_identity and not requested_payload:
        if detail.errors and all(str(v).startswith("timeout") for v in detail.errors.values()):
            raise LoadFailed(
                f"Timed out loading match {match_id}: nothing was read within the time budget. "
                "Retry; the page may be slow to start.",
                reason=SECTION_TIMEOUT,
            )
        html = summary_html or next(iter(fetched.values()), "")
        status, reason = page_outcome(html, tab="match", parsed_count=0)
        if status == "failed" or not html:
            raise LoadFailed(
                f"Failed to load match {match_id}: the page did not render match data "
                "(unknown match id or the source refused the request).",
                reason=reason or "source-refused",
            )
        detail.status = "empty"
        detail.reason = "no-data"
    return detail


def _parse_game_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    match = re_search_date(value)
    if not match:
        return None
    day, month, year = int(match.group(1)), int(match.group(2)), match.group(3)
    year_i = int(year) if year else date.today().year
    if year and len(year) == 2:
        year_i = 2000 + int(year)
    try:
        parsed = date(year_i, month, day)
    except ValueError:
        return None
    if not year and parsed > date.today() + timedelta(days=30):
        parsed = date(year_i - 1, month, day)
    return parsed


def re_search_date(value: str):
    import re

    return re.search(r"(\d{1,2})\.(\d{1,2})\.?(\d{2,4})?", value)


def filter_history(
    items: list[MatchResult], last_n: Optional[int], days_back: Optional[int]
) -> list[MatchResult]:
    filtered = items
    if days_back is not None:
        cutoff = date.today() - timedelta(days=days_back)
        kept: list[MatchResult] = []
        for item in filtered:
            parsed = _parse_game_date(item.date)
            if parsed is None or parsed >= cutoff:
                kept.append(item)
        filtered = kept
    if last_n is not None:
        filtered = filtered[: max(0, last_n)]
    return filtered


H2H_EMPTY_REASON = "no-meetings"
_H2H_PAGE_ROWS = 5  # Flashscore shows five meetings before "Show more matches"


def _team_mentioned(game: MatchResult, team: str) -> bool:
    needle = team.strip().lower()
    if not needle:
        return False
    return needle in game.home_team.lower() or needle in game.away_team.lower()


def _involves(game: MatchResult, ref: TeamRef) -> bool:
    url = game.match_url or ""
    if ref.id and f"-{ref.id}/" in url:
        return True
    name = (ref.name or "").strip().lower()
    return bool(name) and name in (game.home_team.lower(), game.away_team.lower())


def _more_clicks(last_n: Optional[int], days_back: Optional[int]) -> int:
    if last_n is not None:
        return max(0, -(-(last_n - _H2H_PAGE_ROWS) // _H2H_PAGE_ROWS))
    if days_back is not None:
        return min(6, max(0, days_back // 365))
    return 1


async def _find_meeting(ref_a: TeamRef, ref_b: TeamRef) -> Optional[str]:
    """Any game between the two teams, from team A's fixtures then results."""
    for tab, until in (("fixtures", None), ("results", 80)):
        url = f"{ref_a.url}{tab}/"
        try:
            html = await fetch_html(url, full=until is not None, until_count=until)
        except BusyError:
            raise
        except LoadFailed as exc:
            logger.warning("h2h meeting search {} failed: {}", url, exc)
            continue
        for game in parse_matches(html):
            if _involves(game, ref_b) and game.match_id:
                logger.info("h2h meeting for {} v {} -> {}", ref_a.path, ref_b.path, game.match_id)
                return game.match_id
    return None


def _h2h_collection(detail: MatchDetail, label: str, last_n, days_back) -> MatchCollection:
    items = list(detail.h2h or [])
    if detail.errors.get("h2h") and not items:
        raise LoadFailed(f"Failed to load head-to-head for {label}.", reason=detail.errors["h2h"])
    if detail.status == "empty" and not items:
        return MatchCollection(status="empty", reason=H2H_EMPTY_REASON, items=[])
    items = filter_history(items, last_n, days_back)
    if not items:
        return MatchCollection(status="empty", reason=H2H_EMPTY_REASON, items=[])
    errors = [f"h2h: {detail.errors['h2h']}"] if detail.errors.get("h2h") else []
    if errors:
        return MatchCollection(status="partial", reason="section-failed", items=items, errors=errors)
    return MatchCollection(status="ok", items=items)


def _season_collection(
    scan: SeasonScan, window: SeasonPlan, ref_a: TeamRef, ref_b: TeamRef, last_n, days_back, budget_s: float
) -> MatchCollection:
    games = sorted(
        scan.items.values(),
        key=lambda g: _parse_game_date(g.date) or date.min,
        reverse=True,
    )
    items = filter_history(games, last_n, days_back)
    errors: list[str] = []
    notes = list(window.notes)
    reason: Optional[str] = None
    if scan.timed_out:
        reason = "timeout"
        errors.append(
            f"timeout: the {window.label} search stopped after {budget_s:.0f}s; "
            "the meetings listed may be incomplete. Retry, or pass a match URL."
        )
    elif scan.capped:
        reason = "load-cap"
        errors.append(
            f"load-cap: stopped after {scan.loads} page loads (limit {scan.cap}) before reaching the "
            f"start of {window.label}; the meetings listed may be incomplete."
        )
    if errors:
        return MatchCollection(status="partial", reason=reason, items=items, errors=errors, notes=notes)
    if not items:
        return MatchCollection(
            status="empty",
            reason=H2H_EMPTY_REASON,
            items=[],
            errors=[f"No meetings between {ref_a.path} and {ref_b.path} in season {window.label}."],
            notes=notes,
        )
    return MatchCollection(status="ok", items=items, notes=notes)


async def _season_h2h(team_a: str, team_b: str, season: Optional[str], last_n, days_back) -> MatchCollection:
    budget = settings.h2h_budget_s
    deadline = time.monotonic() + budget
    scan = SeasonScan()
    try:
        ref_a = await asyncio.wait_for(resolve_team(team_a), timeout=max(0.1, deadline - time.monotonic()))
        ref_b = await asyncio.wait_for(resolve_team(team_b), timeout=max(0.1, deadline - time.monotonic()))
    except asyncio.TimeoutError:
        raise LoadFailed(
            f"Timed out after {budget:.0f}s looking up the teams. Retry, or pass team URLs.",
            reason=SECTION_TIMEOUT,
        ) from None
    if ref_a.id == ref_b.id:
        raise ValueError("team_a and team_b are the same team.")
    try:
        await scan_season(ref_a, ref_b, season, scan, deadline)
    except asyncio.TimeoutError:
        scan.timed_out = True
    if scan.plan is None:
        # Out of time before the season's dates were known.
        return MatchCollection(
            status="partial",
            reason="timeout",
            items=[],
            errors=[
                f"timeout: the season search stopped after {budget:.0f}s while reading the league's "
                "season format. Retry, or pass a match URL."
            ],
        )
    return _season_collection(scan, scan.plan, ref_a, ref_b, last_n, days_back, budget)


async def get_h2h(
    match: Optional[str] = None,
    team_a: Optional[str] = None,
    team_b: Optional[str] = None,
    last_n: Optional[int] = None,
    days_back: Optional[int] = None,
    season: Optional[str] = None,
) -> MatchCollection:
    clicks = _more_clicks(last_n, days_back)
    if match:
        detail = await get_match(match, sections=["h2h"], h2h_more=clicks)
        return _h2h_collection(detail, match, last_n, days_back)

    if team_a and team_b:
        if (season or "").strip().lower() != "all":
            if (season or "").strip().lower() not in ("", "current"):
                parse_label(season)  # ValueError for an unusable season, before any page loads
            return await _season_h2h(team_a, team_b, season, last_n, days_back)
        # season="all": the full history from a meeting page, under one budget.
        try:
            return await asyncio.wait_for(
                _full_history_h2h(team_a, team_b, clicks, last_n, days_back),
                timeout=settings.h2h_budget_s,
            )
        except asyncio.TimeoutError:
            raise LoadFailed(
                f"Timed out after {settings.h2h_budget_s:.0f}s reading head-to-head for {team_a} v {team_b}. "
                "Retry, use a single season, or pass a match URL.",
                reason=SECTION_TIMEOUT,
            ) from None

    raise ValueError(
        "Pass a match URL/id, or both team_a and team_b, then optionally season, last_n or days_back."
    )


async def _full_history_h2h(team_a: str, team_b: str, clicks: int, last_n, days_back) -> MatchCollection:
    ref_a = await resolve_team(team_a)
    ref_b = await resolve_team(team_b)
    if ref_a.id == ref_b.id:
        raise ValueError("team_a and team_b are the same team.")
    meeting = await _find_meeting(ref_a, ref_b)
    if not meeting:
        meeting = await _find_meeting(ref_b, ref_a)
    if not meeting:
        return MatchCollection(
            status="empty",
            reason=H2H_EMPTY_REASON,
            items=[],
            errors=[f"No recent or scheduled game between {ref_a.path} and {ref_b.path} to read H2H from."],
        )
    detail = await get_match(meeting, sections=["h2h"], h2h_more=clicks)
    return _h2h_collection(detail, f"{team_a} v {team_b}", last_n, days_back)
