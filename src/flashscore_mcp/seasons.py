"""Season labels shared by every tool that takes a season.

Flashscore shows a season label under the league name on the league page and
lists archived seasons on /archive/. There are two formats:

* split year, spanning two years: 'Premier League 2025/2026' (page label '2025-2026')
* calendar year, one year: 'MLS 2025' (page label '2025')

The format belongs to the league, so it is read from the league's own labels.
Only when no league label is available does a bare year fall back to the
football July-to-June season.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

CALENDAR = "calendar"
SPLIT = "split"

_PAIR = re.compile(r"(?<!\d)(\d{4})\s*[/\-\u2013]\s*(\d{4}|\d{2})(?!\d)")
_YEAR = re.compile(r"(?<!\d)(\d{4})(?!\d)")


@dataclass(frozen=True)
class SeasonLabel:
    """A parsed season label: its first year and, for split years, its second."""

    start_year: int
    end_year: Optional[int] = None  # None for a calendar-year label

    @property
    def format(self) -> str:
        return SPLIT if self.end_year else CALENDAR

    @property
    def label(self) -> str:
        """Canonical text, the same as the archive page: '2025/2026' or '2025'."""
        return f"{self.start_year}/{self.end_year}" if self.end_year else str(self.start_year)


def parse_label(text: Optional[str]) -> Optional[SeasonLabel]:
    """Read '2025/2026', '2025-26', 'Premier League 2025/2026' or 'MLS 2025'.

    Returns None when the text holds no year. A pair that is not two
    consecutive years ('2025/2027') raises ValueError.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    pair = _PAIR.search(raw)
    if pair:
        start = int(pair.group(1))
        tail = pair.group(2)
        end = int(tail) if len(tail) == 4 else (start // 100) * 100 + int(tail)
        if end != start + 1:
            raise ValueError(f"season {text!r} must span two consecutive years, such as 2025/26.")
        return SeasonLabel(start, end)
    year = _YEAR.search(raw)
    if year:
        return SeasonLabel(int(year.group(1)))
    return None


def window_for(start_year: int, fmt: str) -> tuple[date, date]:
    """Date range of a season: Jan-Dec for calendar years, 1 July to 30 June for split years."""
    if fmt == CALENDAR:
        return date(start_year, 1, 1), date(start_year, 12, 31)
    return date(start_year, 7, 1), date(start_year + 1, 6, 30)


def fallback_current_start_year(today: Optional[date] = None) -> int:
    """Current season start when no league label exists: July to June."""
    today = today or date.today()
    return today.year if today.month >= 7 else today.year - 1


def _safe_label(text: str) -> Optional[SeasonLabel]:
    try:
        return parse_label(text)
    except ValueError:
        return None


def format_from_archive(names: Iterable[str]) -> Optional[str]:
    """League format from archive season names; the newest entries decide."""
    for name in list(names)[:3]:
        label = _safe_label(name)
        if label:
            return label.format
    return None


def archive_name_for(names: Iterable[str], start_year: int, fmt: str) -> Optional[str]:
    """The archive entry for a season, matched on its first year and format."""
    for name in names:
        label = _safe_label(name)
        if label and label.start_year == start_year and label.format == fmt:
            return name
    return None


def match_archive(names: list[str], wanted: str) -> Optional[str]:
    """Archive season name for a user's text: '2025/26', '2025-2026', '2025' or the full name.

    A bare year matches a calendar-year entry for that year, else the split
    season that starts in it. A two-year text matches only a split entry.
    """
    try:
        target = parse_label(wanted)
    except ValueError:
        return None
    if target is None:
        return None
    if target.end_year:
        return archive_name_for(names, target.start_year, SPLIT)
    return archive_name_for(names, target.start_year, CALENDAR) or archive_name_for(
        names, target.start_year, SPLIT
    )


@dataclass(frozen=True)
class LeagueSeasons:
    """What a league page shows about its seasons."""

    name: str
    page_label: Optional[str]  # label under the league name, e.g. '2026' or '2026-2027'
    archive_names: tuple[str, ...] = ()

    @property
    def format(self) -> Optional[str]:
        label = _safe_label(self.page_label or "")
        if label:
            return label.format
        return format_from_archive(self.archive_names)

    @property
    def current_start_year(self) -> Optional[int]:
        label = _safe_label(self.page_label or "")
        if label:
            return label.start_year
        for name in self.archive_names[:1]:
            first = _safe_label(name)
            if first:
                return first.start_year
        return None


@dataclass(frozen=True)
class SeasonPlan:
    """The season to search: its dates, its label, and how it was decided."""

    start: date
    end: date
    label: str
    format: str
    current_start_year: int
    start_year: int
    notes: tuple[str, ...] = ()

    @property
    def seasons_back(self) -> int:
        return max(0, self.current_start_year - self.start_year)


def needs_league(season: Optional[str]) -> bool:
    """False when the text alone fixes the format, which only a two-year season does."""
    raw = (season or "").strip().lower()
    if raw in ("", "current"):
        return True
    label = parse_label(raw)
    return not (label and label.end_year)


def plan_season(
    season: Optional[str],
    league: Optional[LeagueSeasons] = None,
    today: Optional[date] = None,
) -> SeasonPlan:
    """Window and label for a season request, in the league's own format.

    ``season`` is None/'current', a bare year ('2025'), or a two-year season
    ('2025/26', '2025-2026'). With a league, its page label gives the format
    and the current season; without one, July to June is the fallback and the
    notes say so.
    """
    raw = (season or "").strip().lower()
    parsed: Optional[SeasonLabel] = None
    if raw not in ("", "current"):
        parsed = parse_label(raw)
        if parsed is None:
            raise ValueError(
                "season must look like '2025/26', '2025-2026', '2025', 'current' or 'all'."
            )
    notes: list[str] = []
    league_fmt = league.format if league else None
    league_current = league.current_start_year if league else None
    fallback_year = fallback_current_start_year(today)
    current_year = league_current if league_current is not None else fallback_year

    if parsed and parsed.end_year:
        fmt, start_year = SPLIT, parsed.start_year
        if league_fmt == CALENDAR:
            notes.append(
                f"{league.name} uses calendar-year seasons, but the split-year season {parsed.label} "
                "was requested, so 1 July to 30 June was used."
            )
    elif league_fmt:
        fmt = league_fmt
        start_year = parsed.start_year if parsed else current_year
    else:
        fmt = SPLIT
        start_year = parsed.start_year if parsed else fallback_year
        who = f"The season format of {league.name} could not be read" if league else (
            "The league's season format could not be determined"
        )
        notes.append(f"{who}, so a July to June season was assumed.")

    start, end = window_for(start_year, fmt)
    label = SeasonLabel(start_year, start_year + 1 if fmt == SPLIT else None).label
    if league and league_fmt and not (parsed and parsed.end_year and league_fmt == CALENDAR):
        notes.insert(
            0,
            f"Season {label}: {'calendar-year' if fmt == CALENDAR else 'split-year'} format read from "
            f"{league.name}; dates {start:%d.%m.%Y} to {end:%d.%m.%Y}.",
        )
        names = list(league.archive_names)
        if names and start_year != current_year and not archive_name_for(names, start_year, fmt):
            notes.append(f"Season {label} is not in the league's archive list; the dates above were used anyway.")
    return SeasonPlan(start, end, label, fmt, current_year, start_year, tuple(notes))
