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


def _legacy_summary(html: str) -> dict:
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


def _legacy_stats(html: str) -> list[MatchStat]:
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


def _legacy_incidents(html: str) -> list[MatchIncident]:
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


def _legacy_lineups(html: str) -> list[LineupPlayer]:
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


def _legacy_h2h(html: str) -> list[MatchResult]:
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


# ---------------------------------------------------------------------------
# Current (2026) rendered match page. The legacy regex parsers above stay as
# fallbacks for older markup and saved samples.
# ---------------------------------------------------------------------------

from .dom import Node, mid_from_href, parse_html, slice_from  # noqa: E402

_PLACEHOLDER = re.compile(r"^(loading\.*|\.\.\.|-|\?)?$", re.I)
_TERMINAL_STATUS = re.compile(
    r"finished|after pen|after et|aet|cancel|postponed|awarded|abandoned|walkover|interrupted|delayed|to finish|fro",
    re.I,
)


def _clean_name(text: str | None) -> str | None:
    value = " ".join((text or "").split())
    if not value or _PLACEHOLDER.fullmatch(value):
        return None
    return value


def _participant_name(block: Node | None) -> str | None:
    if block is None:
        return None
    for node in block.iter():
        if node is not block and node.has_class("participant__participantName"):
            name = _clean_name(node.text())
            if name:
                return name
    return None


def _breadcrumb_competition(root: Node) -> str | None:
    crumbs = root.first_testid("wcl-breadcrumbs")
    if crumbs is None:
        return None
    items = [item.text() for item in crumbs.by_testid("wcl-breadcrumbsItem")]
    items = [item for item in items if item]
    if len(items) >= 3:
        return f"{items[1].upper()}: {items[2]}"
    if len(items) == 2:
        return items[1]
    return None


def parse_summary(html: str) -> dict:
    marker = "detail__breadcrumbs" if "detail__breadcrumbs" in (html or "") else "duelParticipant"
    if "duelParticipant" not in (html or ""):
        return _legacy_summary(html)
    root = parse_html(slice_from(html, marker))
    duel = root.first_class("duelParticipant")
    if duel is None or duel.first_class("duelParticipant__home") is None:
        duel = root
    home = _participant_name(duel.first_class("duelParticipant__home"))
    away = _participant_name(duel.first_class("duelParticipant__away"))
    wrapper = duel.first_class("detailScore__wrapper")
    nums = [t for t in (wrapper.texts() if wrapper else []) if re.fullmatch(r"-?\d+", t)]
    home_score = int(nums[0]) if len(nums) >= 1 else None
    away_score = int(nums[1]) if len(nums) >= 2 else None
    status_node = duel.first_class("fixedHeaderDuel__detailStatus") or duel.first_class("detailScore__status")
    status = _clean_name(status_node.text()) if status_node else None
    minute = None
    timer = duel.first_class("eventTime") or duel.first_class("eventAndAddedTime")
    if timer is not None and timer.text():
        minute = timer.text().replace(" ", "")
    elif status and not _TERMINAL_STATUS.search(status) and re.search(r"\d|half|break|pause", status, re.I):
        minute = status
    start_node = duel.first_class("duelParticipant__startTime")
    date = time = None
    if start_node is not None:
        found = re.search(r"(\d{1,2}\.\d{1,2}\.?(?:\d{4})?)\s*(\d{1,2}:\d{2})?", start_node.text())
        if found:
            date, time = found.group(1), found.group(2)
    competition = _breadcrumb_competition(root)
    if not competition:
        legacy = _legacy_summary(html)
        competition = legacy.get("competition")
    return {
        "home_team": home,
        "away_team": away,
        "home_score": home_score,
        "away_score": away_score,
        "match_status": status,
        "minute": minute,
        "competition": competition,
        "date": date,
        "time": time,
    }


def summary_ready(html: str) -> bool:
    parsed = parse_summary(html)
    return bool(parsed.get("home_team") and parsed.get("away_team"))


def parse_stats(html: str) -> list[MatchStat]:
    if 'data-testid="wcl-statistics"' not in (html or ""):
        return _legacy_stats(html)
    root = parse_html(slice_from(html, 'data-testid="wcl-statistics"'))
    stats: list[MatchStat] = []
    seen: set[tuple[str, str, str]] = set()
    for block in root.by_testid("wcl-statistics"):
        row = block.first_class("wcl-labelRow") or block
        cells = [child for child in row.children if isinstance(child, Node)]
        label = row.first_class("wcl-label") or row.first_class("wcl-name")
        name = label.text() if label else ""
        if not name or len(cells) < 3:
            continue
        home = cells[0].text()
        away_node = row.first_class("wcl-awayValue") or cells[-1]
        away = away_node.text()
        key = (name, home, away)
        if key in seen:
            continue
        seen.add(key)
        stats.append(MatchStat(name=name, home=home or None, away=away or None))
    return stats or _legacy_stats(html)


_KIND_BY_ICON = (
    ("own-goal", "own-goal"),
    ("penalty-missed", "penalty-missed"),
    ("penalty-goal", "goal"),
    ("goal", "goal"),
    ("yellow-red", "red-card"),
    ("red-card", "red-card"),
    ("yellow-card", "yellow-card"),
    ("substitution", "substitution"),
    ("var", "var"),
    ("penalty", "penalty"),
)


def _icon_kind(row: Node) -> str:
    icons = [n.testid for n in row.iter() if n.testid.startswith("wcl-icon-incidents-")]
    joined = " ".join(icons).lower()
    for needle, kind in _KIND_BY_ICON:
        if needle in joined:
            return kind
    legacy = " ".join(row.classes + [n.get("class") or "" for n in row.iter()])
    return _incident_kind(legacy)


def parse_incidents(html: str) -> list[MatchIncident]:
    if "smv__participantRow" not in (html or ""):
        return _legacy_incidents(html)
    root = parse_html(slice_from(html, "smv__verticalSections") if "smv__verticalSections" in html else html)
    incidents: list[MatchIncident] = []
    for row in root.by_class("smv__participantRow"):
        team = "home" if row.has_class("smv__homeParticipant") else "away" if row.has_class("smv__awayParticipant") else None
        time_node = row.first_class("smv__timeBox")
        players = [n for n in row.by_class("smv__playerName") if not n.has_class("smv__subDown")]
        player = players[0].text() if players else None
        score_node = row.first_class("smv__incidentHomeScore") or row.first_class("smv__incidentAwayScore")
        kind = _icon_kind(row)
        notes: list[str] = []
        sub = row.first_class("smv__subIncident")
        if sub is not None and sub.text():
            notes.append(sub.text().strip("()"))
        out = row.first_class("smv__subDown")
        if out is not None and out.text():
            notes.append(f"Out: {out.text()}")
        assist = row.first_class("smv__assist")
        if assist is not None and assist.text():
            notes.append(f"Assist: {assist.text().strip('() ')}")
        incidents.append(
            MatchIncident(
                time=time_node.text() if time_node else None,
                team=team,
                player=player or None,
                kind=kind,
                score=score_node.text() if score_node else None,
                note="; ".join(notes) or None,
            )
        )
    return incidents or _legacy_incidents(html)


_LINEUP_ROLES = {
    "starting lineups": "starter",
    "substitutes": "bench",
    "missing players": "missing",
    "coaches": "coach",
    "coach": "coach",
}


def parse_lineups(html: str) -> list[LineupPlayer]:
    if 'data-testid="wcl-lineupsGroup"' not in (html or ""):
        return _legacy_lineups(html)
    root = parse_html(slice_from(html, 'data-testid="wcl-lineupsGroup"'))
    players: list[LineupPlayer] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for group in root.by_testid("wcl-lineupsGroup"):
        header = group.first_testid("wcl-headerSection-text")
        title = (header.text() if header else "").strip().lower()
        role = _LINEUP_ROLES.get(title)
        if role is None:
            continue  # e.g. "Substituted players" repeats the bench
        for entry in group.find_all(lambda n: n.testid.startswith("wcl-lineupsParticipantGeneral-")):
            side = "home" if entry.testid.endswith("-left") else "away" if entry.testid.endswith("-right") else None
            name_node = entry.first_class("wcl-name")
            name = name_node.text() if name_node else ""
            if not name:
                continue
            number_node = entry.first_class("wcl-number")
            number = number_node.text() if number_node else None
            key = (name, side, role)
            if key in seen:
                continue
            seen.add(key)
            players.append(LineupPlayer(name=name, team=side, role=role, number=number or None))
    return players or _legacy_lineups(html)


def _h2h_row(row: Node) -> MatchResult | None:
    home_node = row.first_class("h2h__homeParticipant")
    away_node = row.first_class("h2h__awayParticipant")
    home = _clean_name(home_node.text()) if home_node else None
    away = _clean_name(away_node.text()) if away_node else None
    if not home or not away:
        return None
    date_node = row.first_class("wclH2h__date") or row.first_class("h2h__date")
    result = row.first_class("h2h__result")
    nums = [t for t in (result.texts() if result else []) if re.fullmatch(r"-?\d+", t)]
    home_score = int(nums[0]) if len(nums) >= 1 else None
    away_score = int(nums[1]) if len(nums) >= 2 else None
    href = row.get("href") or ""
    if not href:
        link = row.find(lambda n: n.tag == "a" and "/match/" in (n.get("href") or ""))
        href = link.get("href") if link else ""
    match_id = mid_from_href(href)
    if not match_id:
        ident = re.search(r"g_\d+_([A-Za-z0-9]+)", row.get("id") or "")
        match_id = ident.group(1) if ident else None
    event = row.first_class("h2h__event")
    competition = (event.get("title") if event else None) or None
    if href.startswith("/"):
        href = "https://www.flashscore.com" + href
    url = href or (f"https://www.flashscore.com/match/{match_id}/" if match_id else None)
    return MatchResult(
        date=date_node.text() if date_node else None,
        home_team=home,
        away_team=away,
        status="finished" if home_score is not None else "scheduled",
        home_score=home_score,
        away_score=away_score,
        match_id=match_id,
        match_url=url,
        competition=competition,
    )


def parse_h2h_sections(html: str) -> dict[str, list[MatchResult]]:
    """Every H2H block by its header: 'Last matches: X', 'Head-to-head matches'."""
    if "h2h__row" not in (html or ""):
        return {}
    marker = "h2h__section" if "h2h__section" in html else "h2h__row"
    root = parse_html(slice_from(html, marker))
    sections: dict[str, list[MatchResult]] = {}
    blocks = root.by_class("h2h__section")
    if not blocks:
        rows = [r for r in (_h2h_row(row) for row in root.by_class("h2h__row")) if r]
        return {"": rows} if rows else {}
    for block in blocks:
        header = block.first_testid("wcl-headerSection-text") or block.first_class("section__title")
        title = header.text() if header else ""
        rows = [r for r in (_h2h_row(row) for row in block.by_class("h2h__row")) if r]
        sections.setdefault(title, []).extend(rows)
    return sections


def parse_h2h(html: str) -> list[MatchResult]:
    sections = parse_h2h_sections(html)
    if sections:
        for title, rows in sections.items():
            if "head-to-head" in title.lower() or "head to head" in title.lower():
                return rows
        if list(sections) == [""]:
            return sections[""]
        # Sections exist but none is the meeting list: the teams never met.
        if any(title.lower().startswith("last matches") for title in sections):
            return []
    return _legacy_h2h(html)
