"""Central configuration - production ready with adaptable selectors for slight site changes."""

from pydantic_settings import BaseSettings
from typing import List, Dict


class Settings(BaseSettings):
    headless: bool = True
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
    browser_args: List[str] = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
    nav_timeout_ms: int = 45000
    min_delay_s: float = 1.8
    max_concurrent_pages: int = 3
    base_url: str = "https://www.flashscore.com"
    hierarchy_cache_path: str = "data/league_hierarchy.json"
    cache_ttl_hours: int = 12

    # Multi-fallback selectors for auto-adapt to slight site changes.
    # Prefer text/role first, then class patterns. Easy to extend.
    selectors: Dict[str, List[str]] = {
        "sport_links": [
            "a[href*='/football/']",
            "a[href*='/basketball/']",
            "nav a",
            "[class*='sport'] a",
        ],
        "left_menu": [
            "div.leftMenu",
            "[class*='left-menu']",
            "aside",
            "[class*='sidebar']",
            "#leftMenu",
        ],
        "country_header": [
            "[class*='country']",
            "div.country",
            "span.country_name",
            "h2, h3, h4",
        ],
        "league_link": [
            "a[href*='/']",
            "[class*='league'] a",
            "a[class*='event__']",
        ],
        "standings_table": [
            "table",
            "div.standings",
            "[class*='table']",
            "[class*='standings']",
            "div[class*='ui-table']",
        ],
        "standings_row": [
            "tr",
            "div[class*='row']",
            "[class*='table__row']",
            "[class*='standing']",
        ],
        "results_container": [
            "div.event",
            "[class*='event']",
            "[class*='match']",
            "div[class*='sportName']",
            "#live-table",
        ],
        "show_more": [
            "a[class*='more']",
            "button:has-text('Show more')",
            "a:has-text('Show more')",
            "[class*='event__more']",
        ],
        "tab_standings": ["a:has-text('Standings')", "a[href*='standings']"],
        "tab_results": ["a:has-text('Results')", "a[href*='results']"],
        "tab_fixtures": ["a:has-text('Fixtures')", "a[href*='fixtures']"],
        "tab_news": ["a:has-text('News')", "a[href*='news']"],
    }

    class Config:
        env_prefix = "FLASHSCORE_"
        env_file = ".env"


settings = Settings()
