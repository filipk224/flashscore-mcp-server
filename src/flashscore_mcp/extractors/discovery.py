"""Discovery — top menu sports + left menu countries/leagues. No delay padding."""
from __future__ import annotations
from typing import List
from urllib.parse import urljoin, urlparse
from loguru import logger
from ..browser import browser_manager, safe_goto, find_first_locator, get_all_matching
from ..config import settings
from ..models import Sport, Country, League

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
    sports: List[Sport] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, settings.base_url)
        links = await get_all_matching(page, settings.selectors["top_sports_links"])
        seen = set()
        for loc in links[:40]:
            try:
                href = await loc.get_attribute("href") or ""
                text = (await loc.inner_text()).strip()
                if not href or not text or len(text) > 40:
                    continue
                full = urljoin(settings.base_url, href)
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
            sports = [Sport(**s) for s in KNOWN_SPORTS]
    return sports

async def list_countries(sport: str) -> List[Country]:
    sport_slug = sport.lower().replace(" ", "-")
    url = f"{settings.base_url}/{sport_slug}/"
    countries: List[Country] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)
        menu = await find_first_locator(page, settings.selectors["left_menu"], timeout=1500)
        if menu:
            try:
                expands = menu.locator("button, [class*='expand'], [class*='toggle']")
                count = await expands.count()
                for i in range(min(count, 8)):
                    try:
                        await expands.nth(i).click(timeout=400)
                    except Exception:
                        pass
            except Exception:
                pass
        headers = await get_all_matching(page, settings.selectors["country_headers"] + [f"a[href*='/{sport_slug}/']"])
        seen = set()
        for h in headers[:80]:
            try:
                text = (await h.inner_text()).strip()
                href = await h.get_attribute("href") or ""
                if not text or len(text) < 2 or len(text) > 40:
                    continue
                slug = text.lower().replace(" ", "-")
                if slug in seen:
                    continue
                seen.add(slug)
                full = urljoin(settings.base_url, href) if href else f"{url}{slug}/"
                countries.append(Country(name=text.title(), slug=slug, url=full))
            except Exception:
                continue
        if not countries:
            countries = [
                Country(name="World", slug="world", url=f"{url}world/"),
                Country(name="England", slug="england", url=f"{url}england/"),
                Country(name="Australia", slug="australia", url=f"{url}australia/"),
                Country(name="USA", slug="usa", url=f"{url}usa/"),
            ]
    return countries

async def list_leagues(sport: str, country: str) -> List[League]:
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
                if not href:
                    continue
                full = urljoin(settings.base_url, href)
                path_parts = [p for p in urlparse(full).path.strip("/").split("/") if p]
                if len(path_parts) < 3 or path_parts[0] != sport_slug:
                    continue
                league_slug = path_parts[2]
                if league_slug in seen or league_slug in ("standings", "results", "fixtures", "draw", "news", "archive"):
                    continue
                seen.add(league_slug)
                name = text if text and text.lower() not in ("standings", "results", "fixtures", "news") else league_slug.replace("-", " ").title()
                leagues.append(League(name=name, slug=league_slug, url=f"{settings.base_url}/{sport_slug}/{country_slug}/{league_slug}/", sport=sport_slug, country=country_slug))
            except Exception:
                continue
        if not leagues:
            leagues = [League(name=f"{country} Main League", slug="main", url=url, sport=sport_slug, country=country_slug)]
    return leagues
