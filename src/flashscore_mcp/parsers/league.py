"""League identity and the left-menu leagues. Both markups are shared across sports."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from ..models import League, LeagueInfo
from ..seasons import LeagueSeasons
from .archive import parse_archive

_PRIMARY = ("Summary", "Odds", "News", "Results", "Fixtures", "Standings", "Archive")
_HREF = re.compile(r'<a class="leftMenu__href" href="([^"]+)">([^<]+)</a>')


# Internal sport names in the page script differ from the URL/menu slugs that
# list_sports returns (soccer vs football).
_INTERNAL_SPORT = {"soccer": "football", "ice-hockey": "hockey", "aussie-rules": "aussie-rules"}


def _sport_slug(canonical: str | None, internal: str | None) -> str | None:
    if canonical:
        parts = [part for part in urlparse(canonical).path.strip("/").split("/") if part]
        if len(parts) >= 3:
            return parts[0]
    if internal:
        key = internal.strip().lower().replace("_", "-")
        return _INTERNAL_SPORT.get(key, key)
    return None


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
    season_text = season_m.group(1).strip() if season_m else None
    archive = parse_archive(html)
    season_format = LeagueSeasons(name, season_text, tuple(item.name for item in archive)).format
    return LeagueInfo(
        name=name,
        sport=_sport_slug(canon_m.group(1) if canon_m else None, sport_m.group(1) if sport_m else None),
        country=" ".join(country_m.group(1).split()) if country_m else None,
        season=season_text,
        season_format=season_format,
        url=canon_m.group(1) if canon_m else None,
        tabs=tabs,
        archive_seasons=archive,
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
    if found:
        return found
    from .adapter import parse_menu_leagues_from_hrefs
    return parse_menu_leagues_from_hrefs(html, League)


_SEO_BLOCK = re.compile(r'class="left_menu_categories_seo"[^>]*>(.*?)</div>', re.S)
_SEO_LINK = re.compile(r'<a href="([^"]+)"[^>]*>([^<]+)</a>')
_LMC_ITEM = re.compile(
    r'<a[^>]*class="[^"]*lmc__item[^"]*"[^>]*href="([^"]+)"[^>]*>\s*(?:<[^>]+>\s*)*([^<]+)<'
)


def parse_menu_countries(html: str, sport: str) -> list[tuple[str, str, str]]:
    """(name, slug, path) for every country in a sport's left menu.

    The visible menu renders the first ~22 countries and hides the rest behind
    "Show more"; the page also ships the full list as plain SEO links, which is
    what this reads. Paths are /<sport>/<country>/ only (league links skipped).
    """
    import html as html_lib

    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    sport = sport.strip("/").lower()
    sources = [m.group(1) for m in _SEO_BLOCK.finditer(html)]
    pairs = [pair for block in sources for pair in _SEO_LINK.findall(block)]
    if not pairs:
        pairs = _LMC_ITEM.findall(html)
    for href, name in pairs:
        path = urlparse(href).path if href.startswith("http") else href
        parts = [part for part in path.strip("/").split("/") if part]
        if len(parts) != 2 or parts[0] != sport:
            continue
        slug = parts[1]
        if slug in seen:
            continue
        seen.add(slug)
        out.append((html_lib.unescape(" ".join(name.split())), slug, "/" + "/".join(parts) + "/"))
    return out
