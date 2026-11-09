"""News titles, links, dates, and summaries. The article card markup is shared across sports."""
from __future__ import annotations

import html as html_lib
import re
from datetime import datetime, timedelta
from typing import Optional

from ..models import NewsItem

_ANCHOR = re.compile(r'<a\b[^>]*data-testid="wcl-newsArticlePreview"[^>]*>')
_META_INFO = re.compile(r'data-testid="wcl-newsMetaInfo"[^>]*>(?:\s*<[^>]+>)*\s*([^<]+)<')
_DESCRIPTION = re.compile(
    r'<meta\s+(?:name="description"|property="og:description")\s+content="([^"]*)"', re.I
)
_RELATIVE = re.compile(r"^(\d+)\s*(min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)\s+ago$", re.I)
_DAYWORD = re.compile(r"^(today|yesterday)\s+(\d{1,2}:\d{2})$", re.I)
_ABSOLUTE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+(\d{1,2}:\d{2}))?$")
DATE_FORMAT = "%d.%m.%Y %H:%M"


def normalize_news_date(text: Optional[str], now: Optional[datetime] = None) -> Optional[str]:
    """'2 h ago' / 'Yesterday 18:33' / '07.11.2026 21:19' -> 'dd.mm.yyyy HH:MM'."""
    raw = " ".join((text or "").split())
    if not raw:
        return None
    now = now or datetime.now()
    rel = _RELATIVE.match(raw)
    if rel:
        amount, unit = int(rel.group(1)), rel.group(2).lower()
        delta = timedelta(minutes=amount) if unit.startswith("m") else (
            timedelta(days=amount) if unit.startswith("d") else timedelta(hours=amount)
        )
        return (now - delta).strftime(DATE_FORMAT)
    word = _DAYWORD.match(raw)
    if word:
        day = now.date() - timedelta(days=1 if word.group(1).lower() == "yesterday" else 0)
        hour, minute = (int(part) for part in word.group(2).split(":"))
        return datetime(day.year, day.month, day.day, hour, minute).strftime(DATE_FORMAT)
    absolute = _ABSOLUTE.match(raw)
    if absolute:
        day, month, year, clock = absolute.groups()
        stamp = f"{int(day):02d}.{int(month):02d}.{year}"
        return f"{stamp} {clock}" if clock else stamp
    return raw


def _card_end(html: str, start: int) -> int:
    end = html.find("</a>", start)
    return end if end > 0 else min(len(html), start + 6000)


def parse_news(html: str, now: Optional[datetime] = None) -> list[NewsItem]:
    items: list[NewsItem] = []
    seen: set[str] = set()
    for match in _ANCHOR.finditer(html):
        tag = match.group(0)
        title_m = re.search(r'title="([^"]+)"', tag)
        href_m = re.search(r'href="([^"]+)"', tag)
        if not title_m or not href_m:
            continue
        link = html_lib.unescape(href_m.group(1))
        if link in seen:
            continue
        seen.add(link)
        card = html[match.end() : _card_end(html, match.end())]
        meta = _META_INFO.search(card)
        date = normalize_news_date(html_lib.unescape(meta.group(1)), now) if meta else None
        items.append(NewsItem(title=html_lib.unescape(title_m.group(1)), link=link, date=date))
    if items:
        return items
    from .adapter import parse_news_from_hrefs
    return parse_news_from_hrefs(html, NewsItem)


def article_id(link: str) -> Optional[str]:
    found = re.search(r"/news/[^/]+/([A-Za-z0-9]{6,12})/?", link or "")
    return found.group(1) if found else None


def parse_article_page(html: str, link: str) -> dict:
    """Summary (meta description) and exact publish time from one article page."""
    out: dict = {}
    desc = _DESCRIPTION.search(html or "")
    if desc:
        text = " ".join(html_lib.unescape(desc.group(1)).split())
        if text:
            out["summary"] = text
    ident = article_id(link)
    if ident:
        stamp = re.search(rf'"published":(\d{{9,11}})[^{{}}]{{0,600}}?\\/{re.escape(ident)}\\/"', html or "")
        if stamp:
            out["date"] = datetime.fromtimestamp(int(stamp.group(1))).strftime(DATE_FORMAT)
    return out
