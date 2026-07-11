from __future__ import annotations
from typing import List
from loguru import logger
from ..models import StandingRow

async def get_standings(league: str, season: str = "current") -> List[StandingRow]:
    logger.info("get_standings {} {}", league, season)
    return [StandingRow(position=1, team="Example Team", played=10, wins=7, losses=2, draws=1, pf=25, pa=12, pd=13, points=22, form="WWLWW")]
