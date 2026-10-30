"""Production config. Fast scrape defaults — no human-delay padding."""

from pydantic_settings import BaseSettings
from typing import List, Dict


class Settings(BaseSettings):
    headless: bool = True
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
    browser_args: List[str] = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
    ]
    nav_timeout_ms: int = 25000
    min_delay_s: float = 0.0
    max_concurrent_pages: int = 4
    base_url: str = "https://www.flashscore.com"
    port: int = 8000
    host: str = "0.0.0.0"
    log_level: str = "INFO"

    selectors: Dict[str, List[str]] = {
        "top_sports_links": [
            "nav a[href^='/']",
            "header a[href*='/football/']",
            "[class*='menu'] a[href^='/']",
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
