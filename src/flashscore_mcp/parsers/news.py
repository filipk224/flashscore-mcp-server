"""News titles and links. The article card markup is shared across sports."""
from __future__ import annotations

import html as html_lib
import re

from ..models import NewsItem

_ANCHOR = re.compile(r'<a\b[^>]*data-testid="wcl-newsArticlePreview"[^>]*>')


def parse_news(html: str) -> list[NewsItem]:
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
        items.append(NewsItem(title=html_lib.unescape(title_m.group(1)), link=link))
    return items
