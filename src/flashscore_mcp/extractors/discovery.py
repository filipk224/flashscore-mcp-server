from __future__ import annotations
import json
from pathlib import Path
from typing import List
from loguru import logger
from ..browser import browser_manager, safe_goto
from ..config import settings
from ..models import Sport, Country, League

async def list_sports() -> List[Sport]:
    cache = Path(settings.hierarchy_cache_path)
    if cache.exists():
        data = json.loads(cache.read_text())
        if "sports" in data:
            return [Sport(**s) for s in data["sports"]]
    async with browser_manager.new_page() as page:
        await safe_goto(page, settings.base_url)
        logger.warning("Placeholder - implement real top menu scrape")
        sports = [
            Sport(name="Football", slug="football", url=f"{settings.base_url}/football/"),
            Sport(name="Basketball", slug="basketball", url=f"{settings.base_url}/basketball/"),
            Sport(name="Volleyball", slug="volleyball", url=f"{settings.base_url}/volleyball/"),
            Sport(name="Rugby League", slug="rugby-league", url=f"{settings.base_url}/rugby-league/"),
            Sport(name="Aussie Rules", slug="aussie-rules", url=f"{settings.base_url}/aussie-rules/"),
            Sport(name="Handball", slug="handball", url=f"{settings.base_url}/handball/"),
            Sport(name="Baseball", slug="baseball", url=f"{settings.base_url}/baseball/"),
        ]
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"sports": [s.model_dump() for s in sports]}, indent=2))
        return sports

async def list_countries(sport: str) -> List[Country]:
    logger.info("list_countries {}", sport)
    return [Country(name="World", slug="world"), Country(name="England", slug="england"), Country(name="Australia", slug="australia")]

async def list_leagues(sport: str, country: str) -> List[League]:
    logger.info("list_leagues {} / {}", sport, country)
    return [League(name="Example", slug="example", url=f"{settings.base_url}/{sport}/{country}/example/", sport=sport, country=country)]
