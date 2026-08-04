"""Real discovery extractor - top menu sports + left menu countries/leagues.
Uses multi-fallback selectors for auto-adaptation to slight site changes.
"""

from __future__ import annotations

import asyncio
import re
from typing import List
from urllib.parse import urljoin, urlparse

from loguru import logger

from ..browser import browser_manager, safe_goto, find_first_locator, get_all_matching
from ..config import settings
from ..models import Sport, Country, League


# Known good base URLs for common sports (fallback if scrape fails)
KNOWN_SPORTS = [
    {"name": "Football", "slug": "football", "url": f"{settings.base_url}/football/"},
    {"name": "Basketball", "slug": "basketball", "url": f"{settings.base_url}/basketball/"},
    {"name": "Tennis", "slug": "tennis", "url": f"{settings.base_url}/tennis/"},
    {"name": "Hockey", "slug": "hockey", "url": f"{settings.base_url}/hockey/"},
    {"name": "Volleyball", "slug": "volleyball", "url": f"{settings.base_url}/volleyball/"},
    {"name": "Rugby", "slug": "rugby", "url": f"{settings.base_url}/rugby/"},
    {"name": "Rugby League", "slug": "rugby-league", "url": f"{settings.base_url}/rugby-league/"},
    {"name": "Aussie Rules", "slug": "aussie-rules", "url": f"{settings.base_url}/aussie-rules/"},
    {"name": "Handball", "slug": "handball", "url": f"{settings.base_url}/handball/"},
    {"name": "Baseball", "slug": "baseball", "url": f"{settings.base_url}/baseball/"},
    {"name": "American Football", "slug": "american-football", "url": f"{settings.base_url}/american-football/"},
]


async def list_sports() -> List[Sport]:
    """Discover sports from top menu / homepage. Falls back to known list."""
    sports: List[Sport] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, settings.base_url)

        # Try multi-fallback to find sports links
        links = await get_all_matching(page, settings.selectors["top_sports_links"])
        seen = set()
        for loc in links[:40]:  # limit
            try:
                href = await loc.get_attribute("href") or ""
                text = (await loc.inner_text()).strip()
                if not href or not text or len(text) > 40:
                    continue
                full = urljoin(settings.base_url, href)
                # Filter to top-level sport paths like /football/, /basketball/
                path = urlparse(full).path.strip("/")
                if "/" in path or not path:
                    continue
                slug = path.lower()
                if slug in seen or slug in ("news", "favorites", "settings", "login"):
                    continue
                seen.add(slug)
                sports.append(Sport(name=text.title() if text.islower() else text, slug=slug, url=full.rstrip("/") + "/"))
            except Exception:
                continue

        if not sports:
            logger.warning("Scrape found no sports, using known fallback list")
            sports = [Sport(**s) for s in KNOWN_SPORTS]
        else:
            logger.info("Discovered {} sports from page", len(sports))

    return sports


async def list_countries(sport: str) -> List[Country]:
    """List countries for a sport by navigating to sport page and scanning left menu / country groups."""
    logger.info("list_countries for sport={}", sport)
    sport_slug = sport.lower().replace(" ", "-")
    url = f"{settings.base_url}/{sport_slug}/"

    countries: List[Country] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)

        # Try left menu first
        menu = await find_first_locator(page, settings.selectors["left_menu"])
        if menu:
            # Expand if needed (many sites have collapsible)
            try:
                expands = menu.locator("button, [class*='expand'], [class*='toggle']")
                count = await expands.count()
                for i in range(min(count, 5)):
                    try:
                        await expands.nth(i).click(timeout=1000)
                        await asyncio.sleep(0.3)
                    except Exception:
                        pass
            except Exception:
                pass

        # Collect country-like headers or links
        headers = await get_all_matching(page, settings.selectors["country_headers"] + ["a[href*='/" + sport_slug + "/']"])
        seen = set()
        for h in headers[:60]:
            try:
                text = (await h.inner_text()).strip()
                href = await h.get_attribute("href") or ""
                if not text or len(text) < 2 or len(text) > 40:
                    continue
                # Clean common noise
                if text.lower() in ("world", "europe", "asia", "africa", "america", "oceania") or re.match(r"^[A-Z]{2,}$", text) or " " not in text and text.isupper():
                    slug = text.lower().replace(" ", "-")
                    if slug not in seen:
                        seen.add(slug)
                        full = urljoin(settings.base_url, href) if href else f"{url}{slug}/"
                        countries.append(Country(name=text.title(), slug=slug, url=full))
            except Exception:
                continue

        if not countries:
            # Fallback common ones
            logger.warning("No countries scraped, using common fallback")
            countries = [
                Country(name="World", slug="world", url=f"{url}world/"),
                Country(name="England", slug="england", url=f"{url}england/"),
                Country(name="Spain", slug="spain", url=f"{url}spain/"),
                Country(name="Australia", slug="australia", url=f"{url}australia/"),
                Country(name="USA", slug="usa", url=f"{url}usa/"),
            ]

    logger.info("Found {} countries for {}", len(countries), sport)
    return countries


async def list_leagues(sport: str, country: str) -> List[League]:
    """List leagues under sport + country from left menu or country page."""
    logger.info("list_leagues sport={} country={}", sport, country)
    sport_slug = sport.lower().replace(" ", "-")
    country_slug = country.lower().replace(" ", "-")
    url = f"{settings.base_url}/{sport_slug}/{country_slug}/"

    leagues: List[League] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)

        links = await get_all_matching(page, settings.selectors["league_links"] + [f"a[href*='/{sport_slug}/{country_slug}/']"])
        seen = set()
        for loc in links[:80]:
            try:
                href = await loc.get_attribute("href") or ""
                text = (await loc.inner_text()).strip()
                if not href or not text or "standings" in text.lower() or "results" in text.lower() or "fixtures" in text.lower():
                    # Prefer the league name link, not the tab
                    if "standings" in href or "results" in href or "fixtures" in href:
                        # extract league slug from path
                        parts = [p for p in href.strip("/").split("/") if p]
                        if len(parts) >= 3:
                            league_slug = parts[2]
                            if league_slug not in seen and league_slug not in ("standings", "results", "fixtures", "draw"):
                                seen.add(league_slug)
                                full = urljoin(settings.base_url, href.split("/standings")[0].split("/results")[0].split("/fixtures")[0])
                                leagues.append(League(
                                    name=text or league_slug.replace("-", " ").title(),
                                    slug=league_slug,
                                    url=full.rstrip("/") + "/",
                                    sport=sport_slug,
                                    country=country_slug,
                                ))
                    continue
                # Direct league links
                full = urljoin(settings.base_url, href)
                path_parts = [p for p in urlparse(full).path.strip("/").split("/") if p]
                if len(path_parts) >= 3 and path_parts[0] == sport_slug and path_parts[1] == country_slug:
                    league_slug = path_parts[2]
                    if league_slug not in seen:
                        seen.add(league_slug)
                        leagues.append(League(
                            name=text,
                            slug=league_slug,
                            url=full.rstrip("/") + "/",
                            sport=sport_slug,
                            country=country_slug,
                        ))
            except Exception:
                continue

        if not leagues:
            logger.warning("No leagues found for {}/{}, returning placeholder", sport, country)
            leagues = [League(
                name=f"{country} Main League",
                slug="main",
                url=url,
                sport=sport_slug,
                country=country_slug,
            )]

    logger.info("Found {} leagues for {}/{}", len(leagues), sport, country)
    return leagues
