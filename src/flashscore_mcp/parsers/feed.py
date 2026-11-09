"""Flashscore's day feed (x/feed/f_<sport>_<day>_...), read from the page's own response.

The sport page only renders rows for expanded leagues; the rest sit behind
"display matches (N)" accordions. The feed the page downloads lists every game
of the day with its kick-off timestamp, so day listings use it as the source
of truth and the rendered rows only add details such as the live minute.

Records are split by "~", fields by "¬", and key/value by "÷".
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..config import settings
from ..models import MatchResult

# AB: 1 scheduled, 2 live, 3 finished. AC refines it.
_AC_STATUS = {
    "4": "postponed",
    "5": "cancelled",
    "37": "abandoned",
}
_AC_STAGE = {
    "1": None,
    "3": "Finished",
    "4": "Postponed",
    "5": "Cancelled",
    "10": "After ET",
    "11": "After Pen.",
    "12": "1st Half",
    "13": "2nd Half",
    "38": "Half Time",
    "37": "Abandoned",
    "54": "Awarded",
    "43": "Delayed",
    "36": "Interrupted",
}


def _fields(record: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in record.split("¬"):
        if "÷" in part:
            key, value = part.split("÷", 1)
            out.setdefault(key, value)
    return out


def _int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def feed_status(ab: Optional[str], ac: Optional[str]) -> str:
    if ac in _AC_STATUS:
        return _AC_STATUS[ac]
    if ab == "2":
        return "live"
    if ab == "3":
        return "finished"
    return "scheduled"


def _norm_path(path: Optional[str]) -> str:
    raw = (path or "").strip()
    if raw.startswith("http"):
        raw = "/" + raw.split("://", 1)[1].split("/", 1)[-1]
    parts = [part for part in raw.strip("/").split("/") if part]
    return "/".join(parts[:3]).lower()


def parse_day_feed(text: str, league_path: Optional[str] = None) -> list[MatchResult]:
    """Every game in a day feed; league_path (sport/country/league) keeps one league."""
    games: list[MatchResult] = []
    league: Optional[str] = None
    keep = True
    wanted = _norm_path(league_path) if league_path else None
    for record in (text or "").split("~"):
        if record.startswith("ZA÷"):
            head = _fields(record)
            league = head.get("ZA") or None
            keep = wanted is None or _norm_path(head.get("ZL")) == wanted
            continue
        if not record.startswith("AA÷") or not keep:
            continue
        f = _fields(record)
        home, away = f.get("AE") or f.get("CX"), f.get("AF")
        if not home or not away:
            continue
        date_s = time_s = None
        ts = _int(f.get("AD"))
        if ts:
            local = datetime.fromtimestamp(ts)
            date_s, time_s = local.strftime("%d.%m.%Y"), local.strftime("%H:%M")
        status = feed_status(f.get("AB"), f.get("AC"))
        extras: dict = {}
        stage = _AC_STAGE.get(f.get("AC") or "")
        if stage and status not in ("scheduled",) and stage != "Finished":
            extras["stage"] = stage
        match_id = f.get("AA")
        games.append(
            MatchResult(
                date=date_s,
                time=time_s,
                round=f.get("ER") or None,
                home_team=home,
                away_team=away,
                status=status,
                home_score=_int(f.get("AG")) if status != "scheduled" else None,
                away_score=_int(f.get("AH")) if status != "scheduled" else None,
                match_id=match_id,
                match_url=f"{settings.base_url.rstrip('/')}/match/{match_id}/" if match_id else None,
                competition=league,
                extras=extras,
            )
        )
    return games


def merge_rows(feed: list[MatchResult], rendered: list[MatchResult]) -> list[MatchResult]:
    """Feed order and coverage, with the rendered row's details where present."""
    if not feed:
        return rendered
    by_id = {game.match_id: game for game in rendered if game.match_id}
    merged: list[MatchResult] = []
    for game in feed:
        row = by_id.pop(game.match_id, None) if game.match_id else None
        if row is None:
            merged.append(game)
            continue
        update = {
            "date": game.date or row.date,
            "time": game.time or row.time,
            "round": row.round or game.round,
            "competition": row.competition or game.competition,
            "match_url": row.match_url or game.match_url,
            "extras": {**game.extras, **row.extras},
        }
        # Rendered scores are the final ones (after ET / penalties).
        if row.home_score is None and row.away_score is None:
            update["home_score"], update["away_score"] = game.home_score, game.away_score
        if row.status in ("live", "finished", "postponed", "cancelled", "abandoned"):
            update["status"] = row.status
        else:
            update["status"] = game.status
        if update["status"] != "live":
            update["minute"] = None
        merged.append(row.model_copy(update=update))
    # Rendered rows the feed did not list (should not happen) are kept.
    merged.extend(by_id.values())
    return merged
