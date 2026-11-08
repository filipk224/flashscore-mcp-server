"""Single-match detail and head-to-head."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from loguru import logger

from ..models import MatchCollection, MatchDetail, MatchResult
from ..parsers.adapter import count_match_hints
from ..parsers.match_detail import parse_h2h, parse_incidents, parse_lineups, parse_stats, parse_summary
from .fetch import fetch_html
from .match_ref import resolve_match_ref, section_url
from .page_status import LoadFailed, page_outcome
from .team import get_team_form

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


async def _fetch_section(match_url: str, section: str) -> str:
    return await fetch_html(section_url(match_url, section))


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


async def get_match(match: str, sections: Optional[list[str]] = None) -> MatchDetail:
    match_id, match_url = resolve_match_ref(match)
    wanted = normalize_sections(sections)
    detail = MatchDetail(match_id=match_id, match_url=match_url, status="ok")
    fetched: dict[str, str] = {}

    fetch_plan: list[str] = []
    if "summary" in wanted or "incidents" in wanted:
        fetch_plan.append("summary")
    for name in ("stats", "lineups", "h2h"):
        if name in wanted:
            fetch_plan.append(name)

    for name in fetch_plan:
        try:
            fetched[name] = await _fetch_section(match_url, name)
        except LoadFailed as exc:
            target = "summary" if name == "summary" else name
            detail.errors[target] = exc.reason or "source-refused"
            if name == "summary" and "incidents" in wanted:
                detail.errors.setdefault("incidents", exc.reason or "source-refused")
            logger.warning("get_match section {} failed: {}", name, exc)

    summary_html = fetched.get("summary")
    if summary_html:
        parsed = parse_summary(summary_html)
        _apply_summary(detail, parsed)
        if "summary" in wanted:
            detail.summary = {key: value for key, value in parsed.items() if value is not None}
        if "incidents" in wanted:
            incidents = parse_incidents(summary_html)
            if incidents:
                detail.incidents = incidents
            else:
                outcome = page_outcome(
                    summary_html, tab="match", parsed_count=0, raw_hints=count_match_hints(summary_html)
                )
                if outcome[0] == "failed":
                    detail.errors["incidents"] = outcome[1] or "parse-failed"
                else:
                    detail.incidents = []

    if "stats" in wanted and "stats" in fetched:
        stats = parse_stats(fetched["stats"])
        if stats:
            detail.stats = stats
        else:
            outcome = page_outcome(fetched["stats"], tab="match", parsed_count=0)
            detail.errors["stats"] = outcome[1] or "parse-failed" if outcome[0] == "failed" else None
            if outcome[0] != "failed":
                detail.stats = []
            elif "stats" not in detail.errors or detail.errors["stats"] is None:
                detail.errors["stats"] = outcome[1] or "parse-failed"

    if "lineups" in wanted and "lineups" in fetched:
        lineups = parse_lineups(fetched["lineups"])
        if lineups:
            detail.lineups = lineups
        else:
            outcome = page_outcome(fetched["lineups"], tab="match", parsed_count=0)
            if outcome[0] == "failed":
                detail.errors["lineups"] = outcome[1] or "parse-failed"
            else:
                detail.lineups = []

    if "h2h" in wanted and "h2h" in fetched:
        h2h = parse_h2h(fetched["h2h"])
        if h2h:
            detail.h2h = h2h
        else:
            outcome = page_outcome(
                fetched["h2h"], tab="h2h", parsed_count=0, raw_hints=count_match_hints(fetched["h2h"])
            )
            if outcome[0] == "failed":
                detail.errors["h2h"] = outcome[1] or "parse-failed"
            else:
                detail.h2h = []

    detail.errors = {key: value for key, value in detail.errors.items() if value}

    got_identity = bool(detail.home_team and detail.away_team)
    requested_payload = any(
        getattr(detail, name) is not None for name in ("summary", "stats", "incidents", "lineups", "h2h")
    )
    if detail.errors and (got_identity or requested_payload):
        detail.status = "partial"
        detail.reason = "section-failed"
    elif not got_identity and not requested_payload:
        html = summary_html or next(iter(fetched.values()), "")
        status, reason = page_outcome(html, tab="match", parsed_count=0)
        if status == "failed":
            raise LoadFailed(
                f"Failed to load match {match_id}: the page did not contain usable match data.",
                reason=reason or "parse-failed",
            )
        detail.status = "empty"
        detail.reason = reason or "no-data"
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


def _team_mentioned(game: MatchResult, team: str) -> bool:
    needle = team.strip().lower()
    if not needle:
        return False
    return needle in game.home_team.lower() or needle in game.away_team.lower()


async def get_h2h(
    match: Optional[str] = None,
    team_a: Optional[str] = None,
    team_b: Optional[str] = None,
    last_n: Optional[int] = None,
    days_back: Optional[int] = None,
) -> MatchCollection:
    if match:
        detail = await get_match(match, sections=["h2h"])
        items = list(detail.h2h or [])
        if detail.status == "empty" and not items:
            return MatchCollection(status="empty", reason=detail.reason or "no-matches-scheduled", items=[])
        if detail.errors.get("h2h") and not items:
            raise LoadFailed(
                f"Failed to load head-to-head for {match}.",
                reason=detail.errors["h2h"],
            )
        items = filter_history(items, last_n, days_back)
        status = "empty" if not items else "ok"
        reason = "no-matches-scheduled" if not items else None
        errors = [f"h2h: {detail.errors['h2h']}"] if detail.errors.get("h2h") else []
        if errors and items:
            status = "partial"
            reason = "section-failed"
        return MatchCollection(status=status, reason=reason, items=items, errors=errors)

    if team_a and team_b:
        form = await get_team_form(team_a, last_n=max(last_n or 10, 40))
        items = [game for game in form.items if _team_mentioned(game, team_b)]
        items = filter_history(items, last_n, days_back)
        if not items:
            return MatchCollection(
                status="empty",
                reason=form.reason or "no-matches-scheduled",
                items=[],
                errors=form.errors,
            )
        status = "partial" if form.errors else "ok"
        return MatchCollection(
            status=status,
            reason="section-failed" if form.errors else None,
            items=items,
            errors=form.errors,
        )

    raise ValueError("Pass a match URL/id, or both team_a and team_b, then optionally last_n or days_back.")
