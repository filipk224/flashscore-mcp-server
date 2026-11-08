"""Parsers for a single match page: summary, stats, incidents, lineups, H2H."""
from __future__ import annotations

import re

from ..models import LineupPlayer, MatchIncident, MatchResult, MatchStat
from .matches import parse_matches

_CLASS = re.compile(r'class="([^"]+)"')


def _texts_in(html: str, token: str, span: int = 2000) -> list[str]:
    match = re.search(rf'class="[^"]*{re.escape(token)}[^"]*"', html, re.I)
    if not match:
        return []
    fragment = html[match.end() : match.end() + span]
    return [" ".join(part.split()) for part in re.findall(r">([^<]+)<", fragment) if part.strip()]


def _first_text(html: str, token: str, span: int = 1500) -> str:
    texts = _texts_in(html, token, span)
    return texts[0] if texts else ""


def _int_score(text: str | None) -> int | None:
    if text is None:
        return None
    stripped = text.strip()
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    return None


def _pair_scores(texts: list[str]) -> tuple[int | None, int | None]:
    nums = [part for part in texts if re.fullmatch(r"-?\d+", part)]
    if len(nums) >= 2:
        return int(nums[0]), int(nums[1])
    if len(nums) == 1:
        return int(nums[0]), None
    return None, None


def parse_summary(html: str) -> dict:
    home = _first_text(html, "duelParticipant__home") or _first_text(html, "participant__participantName")
    away_block = _texts_in(html, "duelParticipant__away")
    away = away_block[0] if away_block else ""
    if home and away == home:
        names = [
            text
            for token in ("participant__participantName", "duelParticipant__home", "duelParticipant__away")
            for text in _texts_in(html, token)
        ]
        names = list(dict.fromkeys(names))
        if len(names) >= 2:
            home, away = names[0], names[1]
    home_score, away_score = _pair_scores(_texts_in(html, "detailScore__wrapper", 800))
    if home_score is None:
        home_score = _int_score(_first_text(html, "detailScore__home")) or _int_score(
            _first_text(html, "event__score--home")
        )
    if away_score is None:
        away_score = _int_score(_first_text(html, "detailScore__away")) or _int_score(
            _first_text(html, "event__score--away")
        )
    status = (
        _first_text(html, "detailScore__status")
        or _first_text(html, "fixedHeaderDuel__detailStatus")
        or _first_text(html, "tournamentHeader__country")
    )
    minute = None
    if status and not re.search(r"finished|after pen|aet|cancelled|postponed|awarded", status, re.I):
        if re.search(r"\d|half|ht|break|pause", status, re.I):
            minute = status
    competition = _first_text(html, "tournamentHeader__country") or _first_text(html, "tournamentHeader")
    start = _first_text(html, "duelParticipant__startTime")
    date = time = None
    if start:
        match = re.search(r"(\d{1,2}\.\d{1,2}\.?(?:\d{4})?)\s*(\d{1,2}:\d{2})?", start)
        if match:
            date, time = match.group(1), match.group(2)
    return {
        "home_team": home or None,
        "away_team": away or None,
        "home_score": home_score,
        "away_score": away_score,
        "match_status": (status or None),
        "minute": minute,
        "competition": competition or None,
        "date": date,
        "time": time,
    }


def parse_stats(html: str) -> list[MatchStat]:
    stats: list[MatchStat] = []
    patterns = (
        re.compile(
            r'class="[^"]*stat__row[^"]*"[\s\S]{0,1200}?'
            r'class="[^"]*stat__homeValue[^"]*"[^>]*>([^<]+)[\s\S]{0,400}?'
            r'class="[^"]*stat__categoryName[^"]*"[^>]*>([^<]+)[\s\S]{0,400}?'
            r'class="[^"]*stat__awayValue[^"]*"[^>]*>([^<]+)',
            re.I,
        ),
        re.compile(
            r'class="[^"]*wcl-homeValue[^"]*"[^>]*>([^<]+)[\s\S]{0,400}?'
            r'class="[^"]*wcl-category[^"]*"[^>]*>([^<]+)[\s\S]{0,400}?'
            r'class="[^"]*wcl-awayValue[^"]*"[^>]*>([^<]+)',
            re.I,
        ),
    )
    seen: set[tuple[str, str, str]] = set()
    for pattern in patterns:
        for home, name, away in pattern.findall(html):
            key = (name.strip(), home.strip(), away.strip())
            if not key[0] or key in seen:
                continue
            seen.add(key)
            stats.append(MatchStat(name=key[0], home=key[1], away=key[2]))
    return stats


def _incident_kind(chunk: str) -> str:
    low = chunk.lower()
    if any(token in low for token in ("soccer-ball", "incidenthomescore", "incidentawayscore", "goal")):
        if "own" in low:
            return "own-goal"
        return "goal"
    if any(token in low for token in ("rcard", "redcard", "red-card")):
        return "red-card"
    if any(token in low for token in ("ycard", "yellowcard", "yellow-card")):
        return "yellow-card"
    if any(token in low for token in ("substitution", "sub ", "lf__sub", "smv__sub")):
        return "substitution"
    if "penalty" in low:
        return "penalty"
    return "incident"


def _incident_team(chunk: str) -> str | None:
    low = chunk.lower()
    home = "smv__incidentHome" in chunk or "incidentHome" in chunk or "smv__homeParticipant" in chunk
    away = "smv__incidentAway" in chunk or "incidentAway" in chunk or "smv__awayParticipant" in chunk
    if "smv__homeIncident" in low or home and not away:
        return "home"
    if "smv__awayIncident" in low or away and not home:
        return "away"
    if home:
        return "home"
    if away:
        return "away"
    return None


def parse_incidents(html: str) -> list[MatchIncident]:
    marks = list(re.finditer(r'class="[^"]*smv__incident\b[^"]*"', html))
    incidents: list[MatchIncident] = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else min(len(html), mark.start() + 2500)
        chunk = html[mark.start() : end]
        time = _first_text(chunk, "smv__timeBox")
        player = _first_text(chunk, "smv__playerName") or _first_text(chunk, "smv__assist")
        score_texts = _texts_in(chunk, "smv__incidentHomeScore") + _texts_in(chunk, "smv__incidentAwayScore")
        score = None
        nums = [part for part in score_texts if re.search(r"\d", part)]
        if nums:
            score = nums[0]
        note_parts = [
            text
            for text in _texts_in(chunk, "smv__incident", 800)
            if text not in {time, player} and not re.fullmatch(r"\d+", text)
        ]
        incidents.append(
            MatchIncident(
                time=time or None,
                team=_incident_team(chunk),
                player=player or None,
                kind=_incident_kind(chunk),
                score=score,
                note=" ".join(note_parts[:2]) or None,
            )
        )
    return incidents


def parse_lineups(html: str) -> list[LineupPlayer]:
    players: list[LineupPlayer] = []
    if "lf__lineUp" in html or "lf__player" in html:
        sides = list(re.finditer(r'class="[^"]*lf__side[^"]*"', html))
        for index, mark in enumerate(sides[:2]):
            end = sides[index + 1].start() if index + 1 < len(sides) else min(len(html), mark.start() + 20000)
            chunk = html[mark.start() : end]
            team = "home" if index == 0 else "away"
            names = _collect_named(chunk, ("lf__playerName", "wcl-name", "lineup-player"))
            role = "starter"
            if "lf__bench" in chunk or "Substitutes" in chunk:
                # split later by bench header if present
                pass
            bench_at = chunk.find("lf__bench")
            for name_match in re.finditer(
                r'class="[^"]*(?:lf__playerName|lf__participant)[^"]*"',
                chunk,
            ):
                fragment = chunk[name_match.end() : name_match.end() + 400]
                texts = [" ".join(part.split()) for part in re.findall(r">([^<]+)<", fragment) if part.strip()]
                if not texts:
                    continue
                name = texts[0]
                role = "bench" if bench_at != -1 and name_match.start() > bench_at else "starter"
                number = None
                preceding = chunk[max(0, name_match.start() - 300) : name_match.start()]
                num = re.search(r'class="[^"]*lf__number[^"]*"[^>]*>([^<]+)', preceding)
                if num:
                    number = num.group(1).strip()
                players.append(LineupPlayer(name=name, team=team, role=role, number=number))
        if players:
            return players
    for name in _collect_named(html, ("lf__playerName",)):
        players.append(LineupPlayer(name=name))
    return players


def _collect_named(html: str, tokens: tuple[str, ...]) -> list[str]:
    names: list[str] = []
    for token in tokens:
        for match in re.finditer(rf'class="[^"]*{re.escape(token)}[^"]*"', html):
            fragment = html[match.end() : match.end() + 400]
            texts = [" ".join(part.split()) for part in re.findall(r">([^<]+)<", fragment) if part.strip()]
            if texts:
                names.append(texts[0])
    return list(dict.fromkeys(names))


def parse_h2h(html: str) -> list[MatchResult]:
    rows = list(re.finditer(r'class="[^"]*h2h__row[^"]*"', html))
    games: list[MatchResult] = []
    for index, mark in enumerate(rows):
        end = rows[index + 1].start() if index + 1 < len(rows) else min(len(html), mark.start() + 4000)
        chunk = html[mark.start() : end]
        home = _first_text(chunk, "h2h__homeParticipant") or _first_text(chunk, "h2h__participantInner")
        away_texts = _texts_in(chunk, "h2h__awayParticipant")
        away = away_texts[0] if away_texts else ""
        if not home or not away:
            participants = _texts_in(chunk, "h2h__participant", 1200)
            participants = [part for part in participants if not re.fullmatch(r"\d+", part)]
            if len(participants) >= 2:
                home, away = participants[0], participants[1]
        if not home or not away:
            continue
        date = _first_text(chunk, "h2h__date")
        result_nums = [part for part in _texts_in(chunk, "h2h__result") if re.fullmatch(r"-?\d+", part)]
        home_score = int(result_nums[0]) if len(result_nums) >= 1 else None
        away_score = int(result_nums[1]) if len(result_nums) >= 2 else None
        match_id = None
        ident = re.search(r'id="g_\d+_([^"]+)"', chunk) or re.search(r"/match/(?:[^/]+/)*([A-Za-z0-9]{4,12})", chunk)
        if ident:
            match_id = ident.group(1)
        games.append(
            MatchResult(
                date=date or None,
                home_team=home,
                away_team=away,
                status="finished" if home_score is not None else "scheduled",
                home_score=home_score,
                away_score=away_score,
                match_id=match_id,
                match_url=f"https://www.flashscore.com/match/{match_id}/" if match_id else None,
            )
        )
    if games:
        return games
    return parse_matches(html)
