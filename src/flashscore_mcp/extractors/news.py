from __future__ import annotations
from typing import List
from loguru import logger
from ..models import NewsItem

async def get_news(league: str, limit: int = 10) -> List[NewsItem]:
    logger.info("get_news {} {}", league, limit)
    return [NewsItem(title="Example preview", link="https://www.flashscore.com/news/example/", date="2026-07-11")]
