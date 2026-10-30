"""Archive seasons from the league_archive_data object embedded on league pages."""
from __future__ import annotations

import json
import re

from ..models import Season

_MARKER = "league_archive_data = "


def parse_archive(html: str) -> list[Season]:
    start = html.find(_MARKER)
    if start < 0:
        return []
    payload, _end = json.JSONDecoder().raw_decode(html[start + len(_MARKER) :])
    seasons: list[Season] = []
    for row in payload.get("seasons") or []:
        winner = None
        winners = row.get("winners") or {}
        if isinstance(winners, dict) and winners.get("1"):
            winner = (winners["1"] or {}).get("name")
        seasons.append(Season(name=row.get("name") or "", url=row.get("url"), winner=winner))
    return [season for season in seasons if season.name]


def _norm(s: str) -> str:
    return re.sub(r"[\s/\-]+", "", s.lower())


def resolve_season(seasons: list[Season], season: str) -> tuple[str | None, list[str]]:
    names = [item.name for item in seasons]
    wanted = season.strip().lower()
    wanted_norm = _norm(wanted)
    for item in seasons:
        name_l = item.name.lower()
        if name_l == wanted or wanted in name_l or _norm(item.name) == wanted_norm or wanted_norm in _norm(item.name):
            return item.url, names
    return None, names
