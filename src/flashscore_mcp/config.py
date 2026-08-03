"""Production config with multi-fallback selectors for auto-adaptation to slight site changes.
IaaS-friendly: all key settings overridable via FLASHSCORE_* environment variables.
"""

from pydantic_settings import BaseSettings
from typing import List, Dict


class Settings(BaseSettings):
    # Browser / scraping
    headless: bool = True
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
    browser_args: List[str] = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",  # important in containers with limited /dev/shm
    ]
    nav_timeout_ms: int = 45000
    min_delay_s: float = 1.8
    max_concurrent_pages: int = 2

    # Site
    base_url: str = "https://www.flashscore.com"

    # Caching (mount a volume on /app/data in production for persistence)
    hierarchy_cache_path: str = "data/league_hierarchy.json"
    cache_ttl_hours: int = 12

    # IaaS / HTTP server
    port: int = 8000
    host: str = "0.0.0.0"
    log_level: str = "INFO"

    # Multi-fallback selectors for auto-adaptation.
    # Order: try first, then next if not found. Prefer role/text based.
    # Update these lists when site changes slightly.
    selectors: Dict[str, List[str]] = {
        "top_sports_links": [
            "nav a[href*='/']",
            "header a[href*='/football/'], header a[href*='/basketball/']",
            "[class*='menu'] a[href*='/']",
            "a[href*='/football/'], a[href*='/volleyball/'], a[href*='/rugby']",
        ],
        "left_menu": [
            "[class*='leftMenu']",
            "aside",
            "[class*='sidebar']",
            ".menu__section",
            "[data-testid*='menu']",
        ],
        "country_headers": [
            "[class*='country']",
            "h3, h4, .heading",
            "div[class*='header']",
        ],
        "league_links": [
            "a[href*='/standings']",
            "a[href*='/results']",
            "a[href*='/fixtures']",
            "a[href*='/']",
        ],
        "standings_table": [
            "table",
            "[class*='standings'] table",
            "[class*='table']",
            "[role='table']",
            ".ui-table",
        ],
        "results_rows": [
            "[class*='event']",
            "[class*='match']",
            "[class*='result']",
            "div[class*='row']",
        ],
        "show_more": [
            "button:has-text('Show more')",
            "a:has-text('Show more')",
            "[class*='more']",
            "button[class*='load']",
        ],
    }

    class Config:
        env_prefix = "FLASHSCORE_"
        env_file = ".env"


settings = Settings()
