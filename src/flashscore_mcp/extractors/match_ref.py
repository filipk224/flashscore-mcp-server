"""Resolve a match URL or Flashscore match id to a canonical URL."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from ..config import settings

_ID = re.compile(r"^[A-Za-z0-9]{4,12}$")
_IN_PATH = re.compile(r"/match/(?:[^/]+/)*([A-Za-z0-9]{4,12})/?")


def resolve_match_ref(match: str) -> tuple[str, str]:
    """Return (match_id, match_url)."""
    raw = (match or "").strip()
    if not raw:
        raise ValueError("match is required; pass a match URL or Flashscore match id.")
    if _ID.fullmatch(raw):
        return raw, f"{settings.base_url.rstrip('/')}/match/{raw}/"

    path = raw
    if raw.startswith("http"):
        parsed = urlparse(raw)
        path = parsed.path
    path = path.split("#", 1)[0].split("?", 1)[0]
    found = _IN_PATH.search(path if path.startswith("/") else f"/{path}")
    if found:
        match_id = found.group(1)
        return match_id, f"{settings.base_url.rstrip('/')}/match/{match_id}/"
    raise ValueError(
        "Could not parse a match id from that value. "
        "Pass a Flashscore match URL or an id such as the match_id from get_results_history."
    )


def section_url(match_url: str, section: str) -> str:
    base = match_url.rstrip("/") + "/"
    fragments = {
        "summary": "#/match-summary",
        "incidents": "#/match-summary",
        "stats": "#/match-summary/match-statistics/0",
        "lineups": "#/match-summary/lineups",
        "h2h": "#/h2h/overall",
    }
    return base + fragments.get(section, "#/match-summary")
