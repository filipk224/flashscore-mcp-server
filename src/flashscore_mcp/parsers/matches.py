"""One match-row parser for results, fixtures, summary, and live status."""
from __future__ import annotations

import bisect
import html as html_lib
import re

from ..config import settings
from ..models import MatchResult

# The last row of the list is class="event__match--last event__match ...".
# Requiring event__match as the first class token drops that match.
_ROW = re.compile(r'class="(?:[^"]*\s)?event__match(?:\s[^"]*)?"')
_ROUND = re.compile(r'class="[^"]*event__round[^"]*"[^>]*>([^<]+)')
_ROUND_TITLE = re.compile(r'class="[^"]*event__title[^"]*"[^>]*>([^<]+)')
_DATE = re.compile(r"(\d{1,2}\.\d{1,2}\.?)\s*(\d{1,2}:\d{2})?")
_PART = re.compile(
    r'class="[^"]*\bevent__part--(home|away)\b[^"]*\bevent__part--(\d+)\b'
)


def parse_matches(html: str) -> list[MatchResult]:
    games = _parse_matches_html(html)
    if games:
        return games
    from .adapter import adapt_match_html
    adapted = adapt_match_html(html)
    if adapted != html:
        return _parse_matches_html(adapted)
    return []


_HEADER_LEAGUE = re.compile(r'data-testid="wcl-headerLeague"|class="[^"]*\bheaderLeague__wrapper\b')


def _league_headers(html: str) -> list[tuple[int, str]]:
    """(position, 'COUNTRY: League') for every current-style league header."""
    found: list[tuple[int, str]] = []
    for mark in _HEADER_LEAGUE.finditer(html):
        chunk = html[mark.start() : mark.start() + 6000]
        title = re.search(r'class="[^"]*headerLeague__title-text[^"]*"[^>]*>([^<]+)<', chunk)
        country = re.search(r'class="[^"]*headerLeague__category-text[^"]*"[^>]*>([^<]+)<', chunk)
        if not title:
            continue
        name = html_lib.unescape(" ".join(title.group(1).split()))
        if country and country.group(1).strip():
            name = f"{html_lib.unescape(country.group(1).strip())}: {name}"
        if found and found[-1][0] > mark.start() - 50:
            continue
        found.append((mark.start(), name))
    return found


def _parse_matches_html(html: str) -> list[MatchResult]:
    marks = list(_ROW.finditer(html))
    if not marks:
        marks = list(re.finditer(r'id="g_\d+_[^"]+"', html))
    headers = _league_headers(html)
    header_pos = [pos for pos, _ in headers]
    games: list[MatchResult] = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else min(len(html), mark.start() + 12000)
        preceding = html[max(0, mark.start() - 2500) : mark.start()]
        game = _one(html[mark.start() : end], preceding)
        if game:
            if headers:
                at = bisect.bisect_right(header_pos, mark.start()) - 1
                if at >= 0 and (game.competition is None or header_pos[at] > mark.start() - 2500):
                    game.competition = headers[at][1]
            games.append(game)
    return games


def _round_from(preceding: str) -> str | None:
    rounds = list(_ROUND.finditer(preceding))
    if rounds:
        text = rounds[-1].group(1).strip()
        if text:
            return " ".join(text.split())
    titles = list(_ROUND_TITLE.finditer(preceding))
    if titles:
        text = titles[-1].group(1).strip()
        if text and re.search(r"round|week|matchday|\d", text, re.I):
            return " ".join(text.split())
    return None


def _one(chunk: str, preceding: str = "") -> MatchResult | None:
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
    if _FRO.match(stage or ""):
        extras["note"] = "Final result only (no live coverage)"
    elif stage and not _DATE.search(stage) and not _CLOCK.fullmatch(stage):
        extras["stage"] = stage
    rnd = _round_from(preceding) or _round_from(chunk)
    status = _status(chunk, stage, home_score, away_score)
    match_id = _match_id(chunk, preceding)
    return MatchResult(
        date=date,
        time=time,
        round=rnd,
        home_team=home,
        away_team=away,
        status=status,
        home_score=home_score,
        away_score=away_score,
        match_id=match_id,
        match_url=_match_url(chunk, match_id),
        minute=_minute(status, stage),
        competition=_competition_from(preceding),
        extras=extras,
    )


def _match_id(chunk: str, preceding: str = "") -> str | None:
    # The id usually sits just before class="event__match", so it is in the
    # preceding tail. Searching the whole chunk first can pick up the next row.
    near = preceding[-120:] + chunk[:80]
    found = list(re.finditer(r'id="g_\d+_([^"]+)"', near))
    if found:
        return found[-1].group(1)
    return None


def _match_url(chunk: str, match_id: str | None) -> str | None:
    href = re.search(r'href="((?:https?://[^"]+)?/match/[^"#]+)"', chunk)
    if href:
        path = html_lib.unescape(href.group(1))
        if "?" not in path:
            path = path.rstrip("/") + "/"
        if path.startswith("http"):
            return path
        return settings.base_url.rstrip("/") + path
    if match_id:
        return f"{settings.base_url.rstrip('/')}/match/{match_id}/"
    return None


def _minute(status: str, stage: str) -> str | None:
    if status != "live" or not stage or _DATE.search(stage) or _CLOCK.fullmatch(stage.strip()):
        return None
    if _FRO.match(stage.strip()):
        return None
    text = " ".join(stage.replace("\xa0", " ").split())
    # Football rows render the minute as "67" plus a blinking apostrophe span.
    if re.fullmatch(r"\d{1,3}(?:\+\d{1,2})?", text):
        text += "'"
    return text or None


def _competition_from(preceding: str) -> str | None:
    titles = list(_ROUND_TITLE.finditer(preceding))
    if not titles:
        return None
    text = " ".join(titles[-1].group(1).split())
    if not text:
        return None
    if re.search(r"round|week|matchday", text, re.I) and ":" not in text:
        return None
    return text


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
    for token in ("event__stageTime", "event__stage--block", "event__stage", "event__time"):
        text = _first_text(chunk, token)
        if text:
            return text.replace("\xa0", " ").strip()
    return ""


def _when(stage: str) -> tuple[str | None, str | None]:
    match = _DATE.search(stage)
    if not match:
        clock = _CLOCK.fullmatch(stage.strip()) if stage else None
        return (None, clock.group(1)) if clock else (None, None)
    return match.group(1), match.group(2)


_CLOCK = re.compile(r"(\d{1,2}:\d{2})")
_FINISHED_STAGES = re.compile(
    r"^(finished|ft|aet|after pen\.?|after penalties|after et|after extra time|awarded|walkover|retired|wo)$", re.I
)
_OTHER_STAGES = (
    (re.compile(r"^postponed$", re.I), "postponed"),
    (re.compile(r"^cancell?ed$|^canceled$", re.I), "cancelled"),
    (re.compile(r"^abandoned$", re.I), "abandoned"),
    (re.compile(r"^(delayed|tbd)$", re.I), "scheduled"),
)
# "FRO" is Flashscore's "Final result only": the game has no live coverage,
# so there is no minute and the score only appears once it is final.
_FRO = re.compile(r"^(fro|final result only)$", re.I)


def _status(chunk: str, stage: str, home: int | None, away: int | None) -> str:
    opening = chunk[:600]
    text = (stage or "").strip()
    if _FINISHED_STAGES.match(text):
        return "finished"
    for pattern, value in _OTHER_STAGES:
        if pattern.match(text):
            return value
    if re.search(r'event__match--live\b', opening) or re.search(r'data-live="true"', chunk[:4000]):
        return "live"
    if re.search(r'event__match--scheduled\b', opening):
        return "scheduled"
    if text and (_DATE.search(text) or _CLOCK.fullmatch(text)):
        return "scheduled" if home is None and away is None else "finished"
    if text and not re.search(r"\d{1,2}\.\d{1,2}\.", text):
        # Legacy rows: a bare stage such as 67' or "Half Time" means live.
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
