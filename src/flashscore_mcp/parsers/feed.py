"""Flashscore's day feed (x/feed/f_<sport>_<day>_...), read from the page's own response.

The sport page only renders rows for expanded leagues; the rest sit behind
"display matches (N)" accordions. The feed the page downloads lists every game
of the day with its kick-off timestamp, so day listings use it as the source
of truth and the rendered rows only add details such as the live minute.

Records are split by "~", fields by "¬", and key/value by "÷".
"""
from __future__ import annotations

from typing import Optional

from ..config import settings
from ..models import MatchResult
from ..timeutil import from_ts, iso_utc

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
        date_s = time_s = kickoff = None
        moment = from_ts(_int(f.get("AD")))
        if moment:
            date_s, time_s = moment.strftime("%d.%m.%Y"), moment.strftime("%H:%M")
            kickoff = iso_utc(moment)
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
                kickoff_utc=kickoff,
                timezone="UTC" if kickoff else None,
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
            # The feed's round belongs to the row itself; rendered headers do not.
            "round": game.round or row.round,
            "competition": row.competition or game.competition,
            "kickoff_utc": game.kickoff_utc or row.kickoff_utc,
            "timezone": game.timezone or row.timezone,
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


# ---------------------------------------------------------------------------
# League and team list feeds (results / fixtures tabs)
# ---------------------------------------------------------------------------
#
# A league or team results/fixtures page embeds its first batch of rows as
# cjs.initialFeeds['results'] (or 'fixtures') in the same "~"/"¬"/"÷" format,
# with allEventsCount for the whole tab. Each "Show more matches" click loads
# the next batch from x/feed/t?_..., which the page fetches itself. Every row
# record carries its own round (ER), kick-off timestamp (AD) and id (AA), and
# sits under its competition header (ZA). Reading the round from the row is
# what keeps a Thursday or Monday night game in its real round: the rendered
# list only shows a round header above the first game of each round.

import re as _re  # noqa: E402

_INITIAL_FEED = _re.compile(
    r"initialFeeds\[['\"](?P<key>[\w-]+)['\"]\]\s*=\s*\{\s*data:\s*`(?P<data>[^`]*)`(?P<tail>[^}]{0,400})",
    _re.S,
)
_ALL_COUNT = _re.compile(r"allEventsCount:\s*(\d+)")


def initial_feeds(html: str) -> dict[str, tuple[str, Optional[int]]]:
    """{key: (feed text, allEventsCount)} from a page's cjs.initialFeeds blocks."""
    found: dict[str, tuple[str, Optional[int]]] = {}
    for match in _INITIAL_FEED.finditer(html or ""):
        count = _ALL_COUNT.search(match.group("tail"))
        found.setdefault(match.group("key"), (match.group("data"), int(count.group(1)) if count else None))
    return found


# Feed sport ids (SA) to URL slugs; first slug per id wins.
_SPORT_SLUGS = {
    1: "football", 2: "tennis", 3: "basketball", 4: "hockey", 5: "american-football",
    6: "baseball", 7: "handball", 8: "rugby-union", 9: "floorball", 11: "futsal",
    12: "volleyball", 13: "cricket", 14: "darts", 15: "snooker", 18: "aussie-rules", 19: "rugby-league",
}


def _feed_match_url(f: dict[str, str], sport: Optional[int]) -> Optional[str]:
    """/match/<sport>/<home-slug>-<id>/<away-slug>-<id>/?mid=<id>, as the rendered rows link it."""
    match_id = f.get("AA")
    if not match_id:
        return None
    base = settings.base_url.rstrip("/")
    slug = _SPORT_SLUGS.get(sport or 0)
    home_slug, home_id, away_slug, away_id = f.get("WU"), f.get("PX"), f.get("WV"), f.get("PY")
    if slug and home_slug and home_id and away_slug and away_id:
        return f"{base}/match/{slug}/{home_slug}-{home_id}/{away_slug}-{away_id}/?mid={match_id}"
    return f"{base}/match/{match_id}/"


# Period scores: home BA, BC, BE, BG, BI (5th = overtime), away BB, BD, BF, BH, BJ.
_PERIOD_KEYS = (("BA", "BB"), ("BC", "BD"), ("BE", "BF"), ("BG", "BH"), ("BI", "BJ"))


def _feed_periods(f: dict[str, str]) -> list[dict]:
    out = []
    for index, (home, away) in enumerate(_PERIOD_KEYS, start=1):
        if home in f or away in f:
            out.append({"label": str(index), "home": f.get(home, ""), "away": f.get(away, "")})
    return out


def _list_row(f: dict[str, str], competition: Optional[str], sport: Optional[int] = None) -> Optional[MatchResult]:
    home, away = f.get("AE") or f.get("CX"), f.get("AF")
    if not home or not away:
        return None
    from ..timeutil import DATE_FMT, TIME_FMT, from_ts, iso_utc

    moment = from_ts(_int(f.get("AD")))
    status = feed_status(f.get("AB"), f.get("AC"))
    extras: dict = {}
    stage = _AC_STAGE.get(f.get("AC") or "")
    if stage and status not in ("scheduled",) and stage != "Finished":
        extras["stage"] = stage
    note = f.get("AM")
    if note:
        extras["note"] = note
    periods = _feed_periods(f)
    if periods and status != "scheduled":
        extras["periods"] = periods
    match_id = f.get("AA")
    return MatchResult(
        date=moment.strftime(DATE_FMT) if moment else None,
        time=moment.strftime(TIME_FMT) if moment else None,
        round=(f.get("ER") or "").strip() or None,
        home_team=home,
        away_team=away,
        status=status,
        home_score=_int(f.get("AG")) if status != "scheduled" else None,
        away_score=_int(f.get("AH")) if status != "scheduled" else None,
        match_id=match_id,
        match_url=_feed_match_url(f, sport),
        competition=competition,
        extras=extras,
        kickoff_utc=iso_utc(moment) if moment else None,
        timezone="UTC" if moment else None,
    )


def parse_list_feed(text: str) -> list[MatchResult]:
    """Rows of a results/fixtures feed in feed order, each with its own round."""
    games: list[MatchResult] = []
    competition: Optional[str] = None
    sport: Optional[int] = None
    for record in (text or "").split("~"):
        if record.startswith("SA÷"):
            sport = _int(_fields(record).get("SA"))
            continue
        if record.startswith("ZA÷"):
            competition = _fields(record).get("ZA") or None
            continue
        if not record.startswith("AA÷"):
            continue
        game = _list_row(_fields(record), competition, sport)
        if game is not None:
            games.append(game)
    return games


def merge_listing(feed: list[MatchResult], rendered: list[MatchResult]) -> list[MatchResult]:
    """Feed rows (order, round, competition, kick-off) with rendered details.

    The rendered row adds period scores, winner notes and the full match URL.
    Rendered rows the feed does not list are appended, so nothing is lost when
    a feed batch was not captured.
    """
    if not feed:
        return rendered
    by_id = {game.match_id: game for game in rendered if game.match_id}
    merged: list[MatchResult] = []
    seen: set[str] = set()
    for game in feed:
        if game.match_id in seen:
            continue
        if game.match_id:
            seen.add(game.match_id)
        row = by_id.pop(game.match_id, None) if game.match_id else None
        if row is None:
            merged.append(game)
            continue
        update = {
            "match_url": row.match_url or game.match_url,
            "extras": {**game.extras, **row.extras},
            "minute": row.minute if row.status == "live" else None,
        }
        if row.home_score is not None or row.away_score is not None:
            update["home_score"], update["away_score"] = row.home_score, row.away_score
        if row.status in ("live", "postponed", "cancelled", "abandoned"):
            update["status"] = row.status
        merged.append(game.model_copy(update=update))
    merged.extend(game for game in by_id.values() if game.match_id not in seen)
    return merged
