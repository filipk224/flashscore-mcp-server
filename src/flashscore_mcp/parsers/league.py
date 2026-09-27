"""League identity and the left-menu leagues. Both markups are shared across sports."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from ..models import League, LeagueInfo
from .archive import parse_archive

_PRIMARY = ("Summary", "Odds", "News", "Results", "Fixtures", "Standings", "Archive")
_HREF = re.compile(r'<a class="leftMenu__href" href="([^"]+)">([^<]+)</a>')


def parse_league_page(html: str) -> LeagueInfo:
    sport_m = re.search(r'"sport":"([^"]+)"', html)
    country_m = re.search(r'class="leftMenu__title[^"]*"[^>]*>([^<]+)', html)
    h1_m = re.search(r"<h1>([^<]+)</h1>", html)
    season_m = re.search(r'id="season_url"[^>]*>([^<]+)', html)
    canon_m = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    tabs: list[str] = []
    for title in re.findall(r'role="tab" title="([^"]+)"', html):
        if title in _PRIMARY and title not in tabs:
            tabs.append(title)
    name = " ".join(h1_m.group(1).split()) if h1_m else ""
    return LeagueInfo(
        name=name,
        sport=sport_m.group(1) if sport_m else None,
        country=" ".join(country_m.group(1).split()) if country_m else None,
        season=season_m.group(1).strip() if season_m else None,
        url=canon_m.group(1) if canon_m else None,
        tabs=tabs,
        archive_seasons=parse_archive(html),
    )


def parse_menu_leagues(html: str) -> list[League]:
    found: list[League] = []
    seen: set[str] = set()
    for match in _HREF.finditer(html):
        href, name = match.group(1), " ".join(match.group(2).split())
        if href in seen or not name:
            continue
        seen.add(href)
        parts = [part for part in urlparse(href).path.strip("/").split("/") if part]
        slug = parts[2] if len(parts) >= 3 else name.lower().replace(" ", "-")
        sport = parts[0] if parts else None
        country = parts[1] if len(parts) > 1 else None
        found.append(League(name=name, slug=slug, url=href, sport=sport, country=country))
    return found
