"""Resolve a match URL or Flashscore match id to a canonical URL."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from ..config import settings

_ID = re.compile(r"^[A-Za-z0-9]{6,12}$")
# Legacy ids sit as the last path segment: /match/AbCd1234/ or
# /match/football/arsenal-chelsea/AbCd1234/. Current URLs carry the id in
# ?mid= and their path segments are team slugs (/match/football/a-ID/b-ID/).
_IN_PATH = re.compile(r"/match/(?:[^/]+/)*?([A-Za-z0-9]{8})/?$")
_SECTION_TAILS = ("summary", "h2h", "odds", "standings", "news", "video", "report", "lineups", "stats", "player-stats", "live-commentary", "overall", "home", "away")


def _strip_section_tail(path: str) -> str:
    parts = [part for part in path.strip("/").split("/") if part]
    while parts and parts[-1] in _SECTION_TAILS:
        parts.pop()
    return "/" + "/".join(parts) + "/"


def resolve_match_ref(match: str) -> tuple[str, str]:
    """Return (match_id, match_url)."""
    raw = (match or "").strip()
    if not raw:
        raise ValueError("match is required; pass a match URL or Flashscore match id.")
    if _ID.fullmatch(raw):
        return raw, f"{settings.base_url.rstrip('/')}/match/{raw}/"

    text = raw if raw.startswith("http") else "https://www.flashscore.com/" + raw.lstrip("/")
    parsed = urlparse(text)
    mid = parse_qs(parsed.query).get("mid", [None])[0]
    if not mid:
        frag_q = parsed.fragment.split("?", 1)[1] if "?" in parsed.fragment else ""
        mid = parse_qs(frag_q).get("mid", [None])[0]
    if mid and _ID.fullmatch(mid):
        return mid, f"{settings.base_url.rstrip('/')}/match/{mid}/"
    path = _strip_section_tail(parsed.path)
    found = _IN_PATH.search(path)
    if found and "/match/" in path:
        segs = [s for s in path.strip("/").split("/") if s]
        # /match/<sport>/<home-slug-id>/<away-slug-id>/ has no bare id.
        if not (len(segs) == 4 and all("-" in s for s in segs[2:])):
            match_id = found.group(1)
            return match_id, f"{settings.base_url.rstrip('/')}/match/{match_id}/"
    raise ValueError(
        "Could not parse a match id from that value. "
        "Pass a Flashscore match URL (with ?mid=) or an id such as the match_id from get_results_history."
    )


_PATH_TAILS = {
    "summary": "",
    "incidents": "",
    "stats": "summary/stats/",
    "lineups": "summary/lineups/",
    "h2h": "h2h/overall/",
}
_LEGACY_FRAGMENTS = {
    "summary": "#/match-summary",
    "incidents": "#/match-summary",
    "stats": "#/match-summary/match-statistics/0",
    "lineups": "#/match-summary/lineups",
    "h2h": "#/h2h/overall",
}


def section_url(match_url: str, section: str) -> str:
    """URL of one match tab.

    Current pages (/match/<sport>/<home>/<away>/?mid=ID) use real paths such
    as summary/stats/; the legacy /match/ID/ form keeps its #/ fragments,
    which Flashscore still redirects to the summary page.
    """
    parsed = urlparse(match_url)
    mid = parse_qs(parsed.query).get("mid", [None])[0]
    if mid:
        base = _strip_section_tail(parsed.path)
        tail = _PATH_TAILS.get(section, "")
        return f"{parsed.scheme}://{parsed.netloc}{base}{tail}?mid={mid}"
    base = match_url.split("#", 1)[0].rstrip("/") + "/"
    return base + _LEGACY_FRAGMENTS.get(section, "#/match-summary")
