"""One match-row parser for results, fixtures, summary, and live status."""
from __future__ import annotations

import re

from ..models import MatchResult

_ROW = re.compile(r'class="event__match ')
_DATE = re.compile(r"(\d{1,2}\.\d{1,2}\.?)\s*(\d{1,2}:\d{2})?")
_PART = re.compile(
    r'class="[^"]*\bevent__part--(home|away)\b[^"]*\bevent__part--(\d+)\b'
)


def parse_matches(html: str) -> list[MatchResult]:
    marks = list(_ROW.finditer(html))
    games: list[MatchResult] = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else min(len(html), mark.start() + 12000)
        game = _one(html[mark.start() : end])
        if game:
            games.append(game)
    return games


def _one(chunk: str) -> MatchResult | None:
    home = _team(chunk, "event__homeParticipant") or _team(chunk, "event__participant--home")
    away = _team(chunk, "event__awayParticipant") or _team(chunk, "event__participant--away")
    if not home or not away:
        return None
    home_score = _score(_first_text(chunk, "event__score--home"))
    away_score = _score(_first_text(chunk, "event__score--away"))
    stage = _stage_text(chunk)
    date, time = _when(stage)
    extras: dict = {}
    periods = _periods(chunk)
    if periods:
        extras["periods"] = periods
    note = _note(chunk)
    if note:
        extras["note"] = note
    return MatchResult(
        date=date,
        time=time,
        home_team=home,
        away_team=away,
        status=_status(chunk, stage, home_score, away_score),
        home_score=home_score,
        away_score=away_score,
        extras=extras,
    )


def _team(chunk: str, token: str) -> str | None:
    for text in _texts_after(chunk, token, 800):
        if text.startswith("Winner:") or text.startswith("Advancing"):
            continue
        return text
    return None


def _texts_after(chunk: str, token: str, span: int) -> list[str]:
    match = re.search(rf'class="[^"]*{re.escape(token)}[^"]*"', chunk)
    if not match:
        return []
    fragment = chunk[match.end() : match.end() + span]
    return [" ".join(part.split()) for part in re.findall(r">([^<]+)<", fragment) if part.strip()]


def _first_text(chunk: str, token: str) -> str:
    texts = _texts_after(chunk, token, 400)
    return texts[0] if texts else ""


def _score(text: str) -> int | None:
    stripped = text.strip()
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    return None


def _stage_text(chunk: str) -> str:
    for token in ("event__stageTime", "event__stage"):
        text = _first_text(chunk, token)
        if text:
            return text
    return ""


def _when(stage: str) -> tuple[str | None, str | None]:
    match = _DATE.search(stage)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def _status(chunk: str, stage: str, home: int | None, away: int | None) -> str:
    if re.search(r'data-live="true"', chunk[:2000]):
        return "live"
    if stage and not _DATE.search(stage) and stage.strip().lower() != "finished":
        return "live"
    if home is None and away is None:
        return "scheduled"
    return "finished"


def _periods(chunk: str) -> list[dict]:
    home: dict[str, str] = {}
    away: dict[str, str] = {}
    marks = list(_PART.finditer(chunk))
    for index, match in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else match.end() + 300
        fragment = chunk[match.end() : end]
        texts = [" ".join(part.split()) for part in re.findall(r">([^<]+)<", fragment) if part.strip()]
        if not texts:
            continue
        bucket = home if match.group(1) == "home" else away
        bucket.setdefault(match.group(2), texts[0])
    labels = sorted(set(home) | set(away), key=int)
    return [{"label": label, "home": home.get(label, ""), "away": away.get(label, "")} for label in labels]


def _note(chunk: str) -> str | None:
    pitcher = _first_text(chunk, "event__pitchers")
    if pitcher:
        return pitcher
    notes = [
        text
        for token in ("event__homeParticipant", "event__participant--home", "event__awayParticipant")
        for text in _texts_after(chunk, token, 800)
        if text.startswith("Winner:") or text.startswith("Advancing")
    ]
    return " ".join(dict.fromkeys(notes)) or None
