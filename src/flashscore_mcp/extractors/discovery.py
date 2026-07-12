"""Discovery of sports (top) and countries/leagues (left). Auto-adapts via multi-selectors + caching."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List
from urllib.parse import urljoin

from loguru import logger

from ..browser import browser_manager, safe_goto, find_all
from ..config import settings
from ..models import Sport, Country, League


async def list_sports() -> List[Sport]:
    cache = Path(settings.hierarchy_cache_path)
    if cache.exists():
        try:
            data = json.loads(cache.read_text())
            if "sports" in data and data["sports"]:
                logger.info("Loaded {} sports from cache", len(data["sports"]))
                return [Sport(**s) for s in data["sports"]]
        except Exception as e:
            logger.warning("Cache load failed: {}", e)

    sports: List[Sport] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, settings.base_url)
        known = [
            ("Football", "football"),
            ("Basketball", "basketball"),
            ("Tennis", "tennis"),
            ("Hockey", "hockey"),
            ("Volleyball", "volleyball"),
            ("Rugby", "rugby"),
            ("Rugby League", "rugby-league"),
            ("Aussie Rules", "aussie-rules"),
            ("Handball", "handball"),
            ("Baseball", "baseball"),
            ("American Football", "american-football"),
            ("Cricket", "cricket"),
            ("Darts", "darts"),
            ("Golf", "golf"),
        ]
        for name, slug in known:
            url = f"{settings.base_url}/{slug}/"
            sports.append(Sport(name=name, slug=slug, url=url))

        links = await find_all(page, settings.selectors["sport_links"])
        for link in links[:50]:
            try:
                href = await link.get_attribute("href") or ""
                text = (await link.inner_text()).strip()
                if href and text and any(s in href for s in ["/football/", "/basketball/", "/volleyball/", "/rugby", "/handball", "/baseball"]):
                    full = urljoin(settings.base_url, href)
                    slug = href.strip("/").split("/")[0] if href.startswith("/") else href
                    if not any(s.slug == slug for s in sports):
                        sports.append(Sport(name=text or slug.title(), slug=slug, url=full))
            except Exception:
                continue

        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"sports": [s.model_dump() for s in sports]}, indent=2))
        logger.info("Discovered/seeded {} sports", len(sports))
        return sports


async def list_countries(sport: str) -> List[Country]:
    """Navigate to sport page and extract countries from left menu using multi-selectors."""
    logger.info("list_countries for sport={}", sport)
    sport_url = f"{settings.base_url}/{sport.strip('/')}/"
    countries: List[Country] = []

    async with browser_manager.new_page() as page:
        await safe_goto(page, sport_url)
        all_links = await find_all(page, ["a[href*='/" + sport + "/']", "a[href*='/']"])
        seen = set()
        for link in all_links[:200]:
            try:
                href = await link.get_attribute("href") or ""
                if f"/{sport}/" in href and href.count("/") >= 3:
                    parts = [p for p in href.strip("/").split("/") if p]
                    if len(parts) >= 2 and parts[0] == sport:
                        country_slug = parts[1]
                        if country_slug not in seen:
                            seen.add(country_slug)
                            name = country_slug.replace("-", " ").title()
                            countries.append(Country(name=name, slug=country_slug, url=f"{settings.base_url}/{sport}/{country_slug}/"))
            except Exception:
                continue

        if not countries:
            for c in ["england", "spain", "germany", "italy", "france", "australia", "usa", "brazil", "argentina", "world"]:
                countries.append(Country(name=c.title(), slug=c, url=f"{settings.base_url}/{sport}/{c}/"))

        logger.info("Found {} countries for {}", len(countries), sport)
        return countries[:100]


async def list_leagues(sport: str, country: str) -> List[League]:
    """Extract leagues under sport/country from left menu or page."""
    logger.info("list_leagues {} / {}", sport, country)
    url = f"{settings.base_url}/{sport.strip('/')}/{country.strip('/')}/"
    leagues: List[League] = []

    async with browser_manager.new_page() as page:
        await safe_goto(page, url)
        links = await find_all(page, [f"a[href*='/{sport}/{country}/']", "a[href*='/']"])
        seen = set()
        for link in links[:100]:
            try:
                href = await link.get_attribute("href") or ""
                text = (await link.inner_text()).strip()
                if f"/{sport}/{country}/" in href and href.count("/") >= 3:
                    parts = [p for p in href.strip("/").split("/") if p]
                    if len(parts) >= 3:
                        league_slug = parts[2]
                        if league_slug not in seen and text:
                            seen.add(league_slug)
                            full = urljoin(settings.base_url, href)
                            leagues.append(League(
                                name=text or league_slug.replace("-", " ").title(),
                                slug=league_slug,
                                url=full.rstrip("/") + "/",
                                sport=sport,
                                country=country,
                            ))
            except Exception:
                continue

        if not leagues:
            leagues.append(League(
                name="Main League",
                slug="main",
                url=url,
                sport=sport,
                country=country,
            ))

        logger.info("Found {} leagues for {}/{}", len(leagues), sport, country)
        return leagues
