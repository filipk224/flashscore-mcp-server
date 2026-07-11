from __future__ import annotations
from typing import List
from loguru import logger
from ..models import Season

async def list_archive_seasons(league: str) -> List[Season]:
    logger.info("list_archive_seasons {}", league)
    return [Season(name="2025/2026"), Season(name="2024/2025"), Season(name="2023/2024")]
