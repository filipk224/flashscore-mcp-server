"""Default odds tab. The same cell markup is used for every sampled sport."""
from __future__ import annotations

import re

from ..models import OddsPrice

_CELL = re.compile(r'data-testid="wcl-oddsCell"')


def parse_odds(html: str) -> list[OddsPrice]:
    prices: list[OddsPrice] = []
    for match in _CELL.finditer(html):
        before = html[max(0, match.start() - 2500) : match.start()]
        books = re.findall(r'<img[^>]*title="([^"]+)"', before)
        names = re.findall(r'fp-entityName_[^"]*"[^>]*>([^<]+)', before)
        side = " ".join(names[-1].split()) if names else ""
        fragment = html[match.end() : match.end() + 4000]
        next_cell = fragment.find('data-testid="wcl-oddsCell"')
        if next_cell > 0:
            fragment = fragment[:next_cell]
        texts = [" ".join(part.split()) for part in re.findall(r">([^<]+)<", fragment) if part.strip()]
        price = next((text for text in texts if re.fullmatch(r"\d+(?:\.\d+)?", text)), "")
        if not side or not price:
            continue
        prices.append(OddsPrice(bookmaker=books[-1] if books else None, side=side, price=price))
    return prices
