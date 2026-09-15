"""Archive seasons — /archive/ tab. Single-year names when possible."""
from __future__ import annotations
import re
from typing import List
from urllib.parse import urljoin
from loguru import logger
from ..browser import browser_manager, safe_goto
from ..config import settings
from ..models import Season
from .results import _league_url

_YEAR_RE = re.compile(r"(20\d{2})")

def _season_name(text: str) -> str:
    text = (text or "").strip()
    years = _YEAR_RE.findall(text)
    if not years:
        return text
    if len(years) == 1 or years[0] == years[1]:
        return years[0]
    if re.search(r"20\d{2}\s*/\s*20\d{2}", text):
        return f"{years[0]}/{years[1]}"
    return years[0]

async def list_archive_seasons(league: str) -> List[Season]:
    url = _league_url(league, "current", "archive")
    logger.info("list_archive_seasons url={}", url)
    seasons: List[Season] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)
        raw = await page.evaluate("""() => {
              const nodes = Array.from(document.querySelectorAll("a[href*='-20'], [class*='archive'] a, table a, [class*='season'] a"));
              return nodes.map(a => ({name: (a.innerText || '').trim(), href: a.getAttribute('href') || ''}));
            }""")
    seen = set()
    for row in raw:
        name = _season_name(row.get("name") or "")
        if not _YEAR_RE.search(name) or name in seen:
            continue
        seen.add(name)
        href = row.get("href") or ""
        seasons.append(Season(name=name, url=urljoin(settings.base_url, href) if href else None))
    logger.info("Found {} archive seasons", len(seasons))
    return seasons
