"""Production config. Fast scrape defaults — no human-delay padding."""

import os
from typing import Dict, List, Optional

from pydantic_settings import BaseSettings

from .sizing import Sizing, size_for


class Settings(BaseSettings):
    headless: bool = True
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/156.0.0.0 Safari/537.36"
    )
    browser_args: List[str] = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
    ]
    nav_timeout_ms: int = 25000
    # Abort images, fonts, media and ad/analytics hosts in scrape pages.
    block_assets: bool = True
    # Browser pages open at once. Unset means computed from the run's memory
    # and CPUs (see sizing.py); an explicit value always wins.
    max_concurrent_pages: Optional[int] = None
    # A call that cannot get a browser slot within this many seconds fails
    # with a "busy, retry" error instead of queueing until the client gateway
    # gives up (the Apify gateway cuts requests off at about 60 s).
    queue_wait_s: float = 15.0
    # Whole get_match budget in seconds, queue wait included. Sections that
    # are not loaded when it runs out are reported as timeouts in errors.
    match_budget_s: float = 40.0
    # get_h2h by team names: one overall time budget in seconds (team lookup
    # included) and the ceiling for page loads plus "Show more" clicks the
    # season search may spend (older seasons get more, up to this). Results found before a bound hit are still returned.
    h2h_budget_s: float = 40.0
    h2h_max_loads: int = 15
    # Results/fixtures/team lists: one time budget in seconds for loading a
    # list (page load plus "Show more" batches). Rows loaded before it runs
    # out are returned as a partial page.
    list_budget_s: float = 45.0
    # Byte budget of one list page (JSON). The connector gateway keeps about
    # 20 KB of a response and drops the rest, so pages stay well under it;
    # callers page on with offset/next_offset.
    page_bytes: int = 9000
    # Seconds a read list is reused for the next page: current-season lists
    # (scores change) and archived seasons (fixed).
    list_cache_s: float = 90.0
    list_cache_archive_s: float = 1800.0
    base_url: str = "https://www.flashscore.com"
    port: int = 8000
    host: str = "0.0.0.0"
    log_level: str = "INFO"

    selectors: Dict[str, List[str]] = {
        "top_sports_links": [
            ".wclNavigation--scores a[href]",
            "nav a[href^='/']",
            "header a[href*='/football/']",
        ],
        "left_menu": [
            "[class*='leftMenu']",
            "aside",
            "[class*='sidebar']",
            ".menu__section",
        ],
        "country_headers": [
            ".lmc__item",
            "[class*='lmc__item']",
            "[class*='lmc__header']",
            "[class*='country']",
            "h3, h4",
        ],
        "league_links": [
            "a[href*='/standings']",
            "a[href*='/results']",
            "a[href*='/fixtures']",
            ".lmc__item a",
        ],
        "standings_table": [
            ".ui-table",
            "[class*='ui-table']",
            "[class*='tableWrapper'] table",
            "table",
            "[class*='standings'] table",
            "[role='table']",
            ".ui-table__body",
        ],
        "results_rows": [
            ".event__match",
            "[class*='event__match']",
            "[id^='g_']",
            "[class*='event__round']",
        ],
        "show_more": [
            "a.event__more",
            ".event__more",
            ".lmc__itemMore",
            "a:has-text('Show more matches')",
            "button:has-text('Show more')",
            "a:has-text('Show more')",
            "span:has-text('Show more')",
            "[class*='itemMore']",
        ],
        "news_items": [
            "a[href*='/news/']",
            "article a",
            "[class*='news'] a",
        ],
        "archive_rows": [
            "a[href*='/']",
            "[class*='archive'] a",
            "table a",
        ],
    }

    class Config:
        env_prefix = "FLASHSCORE_"
        env_file = ".env"


settings = Settings()


def apply_sizing(target: Settings, env=None, **detectors) -> Sizing:
    """Set max_concurrent_pages from the run's size unless it was set explicitly."""
    explicit = target.max_concurrent_pages if "max_concurrent_pages" in target.model_fields_set else None
    chosen = size_for(dict(os.environ if env is None else env), explicit_pages=explicit, **detectors)
    target.max_concurrent_pages = chosen.max_concurrent_pages
    return chosen


SIZING = apply_sizing(settings)


def sizing_summary(chosen: Sizing = None) -> str:
    chosen = chosen or SIZING
    return (
        f"Browser pool: max_concurrent_pages={chosen.max_concurrent_pages} ({chosen.pages_source}); "
        f"memory={chosen.memory_mb} MB ({chosen.memory_source}) -> {chosen.memory_pages} pages at "
        f"{chosen.mb_per_page} MB each after {chosen.base_mb} MB base; cpus={chosen.cpus} ({chosen.cpu_source}) "
        f"-> {chosen.cpu_pages} pages; cap {chosen.max_pages}"
    )
