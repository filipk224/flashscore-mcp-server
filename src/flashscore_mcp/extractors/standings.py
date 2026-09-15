"""Standings extractor — header-aware, no cache."""
from __future__ import annotations
import re
from typing import List
from loguru import logger
from ..browser import browser_manager, safe_goto, find_first_locator
from ..config import settings
from ..models import StandingRow
from .results import _league_url
from .parse_util import parse_int

def _norm(h: str) -> str:
    return re.sub(r"[^a-z#]", "", (h or "").lower())

def _map_headers(headers: List[str]) -> dict:
    idx = {}
    for i, h in enumerate(headers):
        n = _norm(h)
        if n in ("#", "pos", "rk", "rank") or n == "":
            idx.setdefault("pos", i)
        elif n in ("team", "club", "name"):
            idx["team"] = i
        elif n in ("mp", "p", "pl", "gp", "g"):
            idx["played"] = i
        elif n in ("w", "win", "wins"):
            idx["wins"] = i
        elif n in ("l", "loss", "losses"):
            idx["losses"] = i
        elif n in ("d", "draw", "draws"):
            idx["draws"] = i
        elif n in ("gf", "pf", "f", "for", "ptsfor"):
            idx["pf"] = i
        elif n in ("ga", "pa", "a", "against", "ptsagainst"):
            idx["pa"] = i
        elif n in ("gd", "pd", "diff"):
            idx["pd"] = i
        elif n in ("pts", "points", "pt"):
            idx["points"] = i
        elif n in ("form", "last5"):
            idx["form"] = i
    return idx

async def get_standings(league: str, season: str = "current") -> List[StandingRow]:
    url = _league_url(league, season, "standings")
    logger.info("get_standings url={}", url)
    rows: List[StandingRow] = []
    async with browser_manager.new_page() as page:
        await safe_goto(page, url)
        table = await find_first_locator(page, settings.selectors["standings_table"], timeout=3000)
        if not table:
            logger.warning("No standings table found")
            return rows
        data = await table.evaluate("""el => {
              const rows = Array.from(el.querySelectorAll('tr'));
              return rows.map(r => Array.from(r.querySelectorAll('th,td')).map(c => (c.innerText||'').trim()));
            }""")
    if not data:
        return rows
    header = data[0] if data else []
    col = _map_headers(header)
    start = 1 if col else 0
    if not col:
        col = {"pos": 0, "team": 1, "played": 2, "wins": 3, "draws": 4, "losses": 5, "pf": 6, "pa": 7, "points": 9}
    def cell(r, key):
        i = col.get(key)
        if i is None or i >= len(r):
            return ""
        return r[i]
    pos_fallback = 0
    for r in data[start:]:
        if len(r) < 3:
            continue
        team = cell(r, "team") or (r[1] if len(r) > 1 else "")
        if not team or team.lower() in ("team", "club"):
            continue
        pos_fallback += 1
        pos = parse_int(cell(r, "pos")) or pos_fallback
        played = parse_int(cell(r, "played")) or 0
        wins = parse_int(cell(r, "wins")) or 0
        losses = parse_int(cell(r, "losses")) or 0
        draws = parse_int(cell(r, "draws"))
        pf = parse_int(cell(r, "pf")) or 0
        pa = parse_int(cell(r, "pa")) or 0
        points = parse_int(cell(r, "points"))
        form = cell(r, "form") or None
        if not form and r:
            last = r[-1]
            if re.fullmatch(r"[WLDT?]{1,10}", last.replace(" ", "")):
                form = last.replace(" ", "")
        rows.append(StandingRow(position=pos, team=team.split("\n")[0].strip(), played=played, wins=wins, losses=losses, draws=draws, pf=pf, pa=pa, points=points, form=form))
    logger.info("Parsed {} standing rows", len(rows))
    return rows
