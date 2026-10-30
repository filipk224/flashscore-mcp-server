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

_SKIP_SLUGS = {"news", "favorites", "settings", "login"}


async def list_sports() -> List[Sport]:
    sports: List[Sport] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, settings.base_url)
        more = page.locator(".wclNavigation--scores button", has_text="MORE")
        if await more.count():
            try:
                await more.first.click(timeout=2000)
            except Exception:
                logger.debug("Scores nav did not expand")
        links = await get_all_matching(page, settings.selectors["top_sports_links"])
        seen = set()
        for loc in links[:80]:
            try:
                href = await loc.get_attribute("href") or ""
                label = " ".join((await loc.inner_text()).split())
                if not href or not label or len(label) > 40:
                    continue
                full = urljoin(settings.base_url, href)
                path = urlparse(full).path.strip("/")
                if not path and label.lower() in {"football", "soccer"}:
                    path = "football"
                    full = f"{settings.base_url}/football/"
                if not path or path.count("/") > 1:
                    continue
                slug = path.lower()
                if slug in seen or slug in _SKIP_SLUGS:
                    continue
                seen.add(slug)
                name = label.title() if label.isupper() else label
                sports.append(Sport(name=name, slug=slug, url=full.rstrip("/") + "/"))
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
        # Click "Show more" for full country list if present
        try:
            more = page.locator(".lmc__itemMore, [class*='itemMore'], a:has-text('Show more'), button:has-text('Show more')")
            if await more.count() > 0:
                await more.first.click(timeout=5000)
                await page.wait_for_timeout(1500)
        except Exception:
            pass
        # Primary: country items in left menu
        items = page.locator(".lmc__item")
        count = await items.count()
        seen = set()
        for i in range(min(count, 300)):
            try:
                loc = items.nth(i)
                text = (await loc.inner_text()).strip()
                if not text or len(text) < 2 or len(text) > 50 or text.lower() in ("show more", "my teams", "rankings"):
                    continue
                slug = text.lower().replace(" ", "-").replace("&", "and")
                if slug in seen:
                    continue
                seen.add(slug)
                # Try to find href
                href = ""
                a = loc.locator("a").first
                if await a.count() > 0:
                    href = await a.get_attribute("href") or ""
                full = urljoin(settings.base_url, href) if href else f"{url}{slug}/"
                countries.append(Country(name=text.title(), slug=slug, url=full))
            except Exception:
                continue
        if not countries:
            # Fallback to known major ones
            countries = [
                Country(name="World", slug="world", url=f"{url}world/"),
                Country(name="England", slug="england", url=f"{url}england/"),
                Country(name="Spain", slug="spain", url=f"{url}spain/"),
                Country(name="Germany", slug="germany", url=f"{url}germany/"),
                Country(name="Italy", slug="italy", url=f"{url}italy/"),
                Country(name="France", slug="france", url=f"{url}france/"),
                Country(name="Australia", slug="australia", url=f"{url}australia/"),
                Country(name="USA", slug="usa", url=f"{url}usa/"),
            ]
    logger.info("list_countries {} -> {}", sport_slug, len(countries))
    return countries

_TAB_SLUGS = {"standings", "results", "fixtures", "draw", "news", "archive", "odds"}


async def list_leagues(sport: str, country: str) -> List[League]:
    sport_slug = sport.lower().replace(" ", "-")
    country_slug = country.lower().replace(" ", "-")
    url = f"{settings.base_url}/{sport_slug}/{country_slug}/"
    from .fetch import fetch_html
    from ..parsers.league import parse_menu_leagues

    html = await fetch_html(url)
    leagues: List[League] = []
    seen = set()
    for league in parse_menu_leagues(html):
        if league.sport and league.sport != sport_slug:
            continue
        if league.country and league.country != country_slug:
            continue
        if league.slug in seen or league.slug in _TAB_SLUGS:
            continue
        seen.add(league.slug)
        full = urljoin(settings.base_url, league.url)
        leagues.append(league.model_copy(update={"url": full, "sport": sport_slug, "country": country_slug}))
    logger.info("list_leagues {} / {} -> {}", sport_slug, country_slug, len(leagues))
    return leagues
