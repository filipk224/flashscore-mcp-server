"""Production config. Fast scrape defaults — no human-delay padding."""

from pydantic_settings import BaseSettings
from typing import List, Dict


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
    max_concurrent_pages: int = 4
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
