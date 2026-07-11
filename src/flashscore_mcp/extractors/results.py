from __future__ import annotations
from typing import List, Optional
from loguru import logger
from ..models import MatchResult

async def get_results_history(league: str, season: str = "current", mode: str = "full", limit: Optional[int] = None) -> List[MatchResult]:
    logger.info("get_results_history {} {} {}", league, season, mode)
    return [MatchResult(date="2026-07-10", home_team="Team A", away_team="Team B", home_pf=2, away_pf=1)]
