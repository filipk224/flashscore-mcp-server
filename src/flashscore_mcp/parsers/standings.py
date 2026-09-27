"""Header-driven standings parser for saved and live Flashscore pages."""
from __future__ import annotations

import re

from ..models import StandingRow, StandingSection, StandingsPage

_CANONICAL = {
    "MP": "played",
    "W": "wins",
    "D": "draws",
    "L": "losses",
    "PTS": "table_points",
    "FORM": "form",
}
_TEAM_HEADERS = {"TEAM", "CLUB", "NAME"}
_PAIR = re.compile(r"^(\d+):(\d+)$")
_FORM_LETTER = re.compile(r"\b([WLDT])\b")
_TABLE = re.compile(r'class="([^"]*\bui-table\b[^"]*)"')
_HEADER_CELL = re.compile(r'class="([^"]*\bui-table__headerCell\b[^"]*)"')
_ROW = re.compile(r'class="([^"]*\bui-table__row\b[^"]*)"')
_CELL = re.compile(r'class="([^"]*\btable__cell\b[^"]*)"')


def parse_standings(html: str) -> StandingsPage:
    tables = _tables(html)
    sections: list[StandingSection] = []
    for table in tables:
        section = _parse_table(table)
        if section.rows:
            sections.append(section)
    if sections:
        return StandingsPage(kind="table", sections=sections)
    if "draw__bracket" in html:
        return StandingsPage(kind="draw", sections=[])
    return StandingsPage(kind="table", sections=[])


def _tables(html: str) -> list[str]:
    starts = [m.start() for m in _TABLE.finditer(html)]
    chunks = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(html)
        chunks.append(html[start:end])
    return chunks


def _parse_table(table: str) -> StandingSection:
    body_at = table.find("ui-table__body")
    header_html = table[:body_at] if body_at >= 0 else table
    body_html = table[body_at:] if body_at >= 0 else ""
    headers = _cells(header_html, _HEADER_CELL)
    section_name = _section_name(headers)
    stat_headers = [h for h in headers if h["role"] == "stat"]
    rows: list[StandingRow] = []
    for row_html in _row_chunks(body_html):
        cells = [c for c in _cells(row_html, _CELL) if c["role"] != "wrapper"]
        row = _row_from_cells(cells, stat_headers, section_name)
        if row:
            rows.append(row)
    return StandingSection(name=section_name, rows=rows)


def _section_name(headers: list[dict]) -> str | None:
    for header in headers:
        if header["role"] == "participant":
            text = header["text"]
            if text.upper() in _TEAM_HEADERS or not text:
                return None
            return text
    return None


def _row_from_cells(cells: list[dict], stat_headers: list[dict], section: str | None) -> StandingRow | None:
    by_role = {c["role"]: c for c in cells if c["role"] in {"rank", "participant", "form"}}
    values = [c for c in cells if c["role"] == "value"]
    team = (by_role.get("participant") or {}).get("text") or ""
    team = team.split("  ")[0].strip()
    if not team or team.upper() in _TEAM_HEADERS:
        return None
    position = _int_first((by_role.get("rank") or {}).get("text") or "") or 0
    data: dict = {
        "position": position,
        "team": team,
        "section": section,
        "extras": {},
    }
    form = _form_text((by_role.get("form") or {}).get("text") or "")
    if form:
        data["form"] = form
    for header, cell in zip(stat_headers, values):
        key = header["text"].strip()
        canon = _CANONICAL.get(key.upper())
        if canon == "form":
            parsed = _form_text(cell["text"])
            if parsed:
                data["form"] = parsed
            continue
        if canon:
            data[canon] = _int_first(cell["text"])
            continue
        data["extras"][key] = _extra(cell["text"])
    return StandingRow(**data)


def _extra(text: str):
    raw = " ".join(text.split())
    pair = _PAIR.fullmatch(raw)
    if not pair:
        return raw
    return {"raw": raw, "for": int(pair.group(1)), "against": int(pair.group(2))}


def _form_text(text: str) -> str | None:
    letters = _FORM_LETTER.findall(text)
    return "".join(letters) or None


def _int_first(text: str) -> int | None:
    match = re.search(r"-?\d+", text.replace(",", ""))
    return int(match.group(0)) if match else None


def _row_chunks(body: str) -> list[str]:
    marks = list(_ROW.finditer(body))
    chunks = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        chunks.append(body[mark.start() : end])
    return chunks


def _cells(chunk: str, pattern: re.Pattern) -> list[dict]:
    marks = list(pattern.finditer(chunk))
    cells = []
    for i, mark in enumerate(marks):
        cls = mark.group(1)
        end = marks[i + 1].start() if i + 1 < len(marks) else len(chunk)
        # A wrapper div contains the real cell. Keep the inner element.
        if _role(cls) == "wrapper" and i + 1 < len(marks) and marks[i + 1].start() < end:
            continue
        frag = chunk[mark.end() : end]
        name = re.search(r'class="[^"]*\btableCellParticipant__name\b[^"]*"[^>]*>([^<]+)', frag)
        texts = re.findall(r">([^<]*)<", frag)
        text = " ".join(t.strip() for t in texts if t.strip())
        if name:
            text = name.group(1).strip()
        cells.append({"role": _role(cls), "text": text, "class": cls})
    return cells


def _role(cls: str) -> str:
    if "headerCell--rank" in cls or "cell--rank" in cls:
        return "rank"
    if "headerCell--participant" in cls or "cell--participant" in cls:
        return "participant"
    if "cell--form" in cls or "headerCell--form" in cls:
        return "form"
    if "cell--value" in cls or "headerCell" in cls:
        return "value" if "cell--value" in cls else "stat"
    if cls.strip() in {"table__cell", "ui-table__headerCell"} or "--" not in cls:
        return "wrapper"
    return "value"
