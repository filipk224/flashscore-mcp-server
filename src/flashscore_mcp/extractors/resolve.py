"""Resolve a human league name (with its country) to a Flashscore path."""
from __future__ import annotations

import re
from typing import Optional

from loguru import logger

# Well-known competitions: the name already implies a country (and sport).
# Keys are normalize_key() results.
WELL_KNOWN: dict[str, str] = {
    "nba": "basketball/usa/nba",
    "wnba": "basketball/usa/wnba",
    "euroleague": "basketball/europe/euroleague",
    "nbl": "basketball/australia/nbl",
    "premier league": "football/england/premier-league",
    "epl": "football/england/premier-league",
    "english premier league": "football/england/premier-league",
    "championship": "football/england/championship",
    "fa cup": "football/england/fa-cup",
    "la liga": "football/spain/laliga",
    "laliga": "football/spain/laliga",
    "bundesliga": "football/germany/bundesliga",
    "serie a": "football/italy/serie-a",
    "ligue 1": "football/france/ligue-1",
    "eredivisie": "football/netherlands/eredivisie",
    "primeira liga": "football/portugal/liga-portugal",
    "mls": "football/usa/mls",
    "liga mx": "football/mexico/liga-mx",
    "a league": "football/australia/a-league",
    "a league men": "football/australia/a-league",
    "a league women": "football/australia/a-league-women",
    "champions league": "football/europe/champions-league",
    "uefa champions league": "football/europe/champions-league",
    "ucl": "football/europe/champions-league",
    "europa league": "football/europe/europa-league",
    "conference league": "football/europe/conference-league",
    "world cup": "football/world/world-cup",
    "nfl": "american-football/usa/nfl",
    "nhl": "hockey/usa/nhl",
    "mlb": "baseball/usa/mlb",
    "npb": "baseball/japan/npb",
    "nrl": "rugby-league/australia/nrl",
    "super rugby": "rugby/world/super-rugby",
    "six nations": "rugby/europe/six-nations",
    "afl": "aussie-rules/australia/afl",
    "australian football league": "aussie-rules/australia/afl",
}

_COUNTRY_ALIASES = {
    "usa": "usa",
    "us": "usa",
    "united states": "usa",
    "united states of america": "usa",
    "uk": "england",
    "great britain": "england",
    "england": "england",
    "scotland": "scotland",
    "wales": "wales",
    "australia": "australia",
    "aus": "australia",
    "spain": "spain",
    "germany": "germany",
    "italy": "italy",
    "france": "france",
    "japan": "japan",
    "mexico": "mexico",
    "netherlands": "netherlands",
    "portugal": "portugal",
    "europe": "europe",
    "world": "world",
}

_NAME_COUNTRY = re.compile(
    r"^(?P<name>.+?)\s*(?:\((?P<country>[^)]+)\)|,\s*(?P<country2>.+))$"
)

_SPORTS_TO_TRY = (
    "football",
    "basketball",
    "hockey",
    "baseball",
    "american-football",
    "rugby",
    "rugby-league",
    "aussie-rules",
    "volleyball",
    "handball",
    "tennis",
)


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def country_slug(value: str) -> str:
    key = normalize_key(value)
    return _COUNTRY_ALIASES.get(key, slugify(value))


def country_label(slug: str) -> str:
    special = {"usa": "USA", "uae": "UAE", "uk": "UK"}
    if slug in special:
        return special[slug]
    return slug.replace("-", " ").title()


def parse_name_and_country(league: str) -> tuple[str, Optional[str]]:
    text = league.strip()
    match = _NAME_COUNTRY.match(text)
    if not match:
        return text, None
    name = match.group("name").strip()
    country = (match.group("country") or match.group("country2") or "").strip()
    return name, country or None


def lookup_known(name: str, country: Optional[str] = None) -> Optional[str]:
    path = WELL_KNOWN.get(normalize_key(name))
    if not path:
        return None
    if country and country_slug(country) != path.split("/")[1]:
        return None
    return path


def looks_like_path(league: str) -> bool:
    raw = league.strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        return True
    parts = [part for part in raw.strip("/").split("/") if part]
    return len(parts) >= 3 and " " not in raw


async def resolve_league_ref(league: str) -> str:
    """Return a URL or sport/country/slug path for extractor use."""
    raw = (league or "").strip()
    if not raw:
        raise ValueError(
            "League is required. Use a name with its country, such as "
            "'Premier League (England)', or a path like football/england/premier-league."
        )
    if looks_like_path(raw):
        if raw.startswith("http://") or raw.startswith("https://"):
            return raw
        parts = [part for part in raw.strip("/").split("/") if part]
        return "/".join(parts[:3])

    name, country = parse_name_and_country(raw)
    known = lookup_known(name, country)
    if known:
        logger.info("Resolved league {} -> {} (well-known)", raw, known)
        return known

    if country:
        found = await _discover_named_league(name, country)
        if found:
            logger.info("Resolved league {} -> {} (country menu)", raw, found)
            return found

    raise ValueError(
        f"Could not resolve league {raw!r}. Use the league name with the country "
        "it belongs to, such as 'NBA (USA)' or 'Premier League (England)', "
        "or a path like basketball/usa/nba."
    )


async def _discover_named_league(name: str, country: str) -> Optional[str]:
    from . import discovery

    target = normalize_key(name)
    target_slug = slugify(name)
    country_key = country_slug(country)
    sports: list[str] = []
    known = WELL_KNOWN.get(target)
    if known:
        sports.append(known.split("/")[0])
    sports.extend(_SPORTS_TO_TRY)
    for sport in dict.fromkeys(sports):
        try:
            leagues = await discovery.list_leagues(sport, country_key)
        except Exception as exc:
            logger.debug("list_leagues {} / {} failed: {}", sport, country_key, exc)
            continue
        for item in leagues:
            item_name = normalize_key(item.name.split("(")[0])
            if item_name == target or normalize_key(item.slug) == target or item.slug == target_slug:
                sport_slug = item.sport or sport
                country_val = item.country or country_key
                return f"{sport_slug}/{country_val}/{item.slug}"
    return None
