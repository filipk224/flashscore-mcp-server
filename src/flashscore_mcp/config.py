from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    headless: bool = True
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    browser_args: List[str] = ["--disable-blink-features=AutomationControlled"]
    nav_timeout_ms: int = 30000
    min_delay_s: float = 1.5
    max_concurrent_pages: int = 2
    base_url: str = "https://www.flashscore.com"
    hierarchy_cache_path: str = "data/league_hierarchy.json"
    class Config:
        env_prefix = "FLASHSCORE_"
        env_file = ".env"

settings = Settings()
