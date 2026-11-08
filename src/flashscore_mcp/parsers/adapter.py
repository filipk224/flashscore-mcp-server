"""Adapt parsers when Flashscore renames CSS classes.

Known semantic fragments are mapped back to the canonical class tokens the
parsers already understand. Structural fallbacks (game ids, league URLs)
cover pages that drop the old class names entirely.
"""
from __future__ import annotations

import re
from typing import Iterable

from loguru import logger

_CLASS_ATTR = re.compile(r'class="([^"]+)"')
_ID_ROW = re.compile(
    r'(<(?:div|tr|article|li)[^>]*\sid="g_\d+_[^"]+"[^>]*)(>)',
    re.I,
)

# Canonical token -> fragments that identify a renamed class.
MATCH_HINTS: dict[str, tuple[str, ...]] = {
    "event__match": ("event__match",),
    "event__homeParticipant": ("homeparticipant", "participant--home"),
    "event__participant--home": ("participant--home",),
    "event__awayParticipant": ("awayparticipant", "participant--away"),
    "event__participant--away": ("participant--away",),
    "event__score--home": ("score--home", "homescore"),
    "event__score--away": ("score--away", "awayscore"),
    "event__stageTime": ("stagetime", "event__stage"),
    "event__stage": ("event__stage",),
    "event__round": ("event__round",),
    "event__title": ("event__title",),
}

STANDING_HINTS: dict[str, tuple[str, ...]] = {
    "ui-table": ("ui-table",),
    "ui-table__headerCell": ("headercell", "ui-table__header"),
    "ui-table__row": ("ui-table__row", "table__row"),
    "ui-table__body": ("ui-table__body", "table__body"),
    "table__cell": ("table__cell",),
}

NEWS_TESTID = "wcl-newsArticlePreview"


def class_tokens(html: str) -> set[str]:
    tokens: set[str] = set()
    for match in _CLASS_ATTR.finditer(html):
        tokens.update(match.group(1).split())
    return tokens


def _pick(tokens: Iterable[str], hints: tuple[str, ...]) -> str | None:
    lowered = [(token, token.lower()) for token in tokens]
    for hint in hints:
        needle = hint.lower()
        matches = [(token, low) for token, low in lowered if needle in low]
        if not matches:
            continue
        # Prefer an exact or suffix match, then the shortest token, so a
        # fragment like "ui-table" does not steal "ui-table__headerCell".
        matches.sort(
            key=lambda item: (
                0 if item[1] == needle else 1,
                0 if item[1].endswith(needle) else 1,
                len(item[1]),
            )
        )
        return matches[0][0]
    return None


def build_rename_map(html: str, hints: dict[str, tuple[str, ...]]) -> dict[str, str]:
    """Map discovered class tokens back to canonical names the parsers expect."""
    tokens = class_tokens(html)
    mapping: dict[str, str] = {}
    for canonical, fragments in hints.items():
        if canonical in tokens:
            continue
        found = _pick(tokens, fragments)
        if found and found != canonical:
            mapping[found] = canonical
    return mapping


def apply_class_renames(html: str, mapping: dict[str, str]) -> str:
    if not mapping:
        return html

    def repl(match: re.Match[str]) -> str:
        classes = [mapping.get(token, token) for token in match.group(1).split()]
        return f'class="{" ".join(classes)}"'

    return _CLASS_ATTR.sub(repl, html)


def ensure_match_row_classes(html: str) -> str:
    """If rows only have Flashscore game ids, tag them as event__match."""

    def repl(match: re.Match[str]) -> str:
        tag = match.group(1)
        if re.search(r'class="', tag):
            if "event__match" in tag:
                return match.group(0)
            return re.sub(r'class="([^"]*)"', r'class="\1 event__match"', tag, count=1) + match.group(2)
        return f'{tag} class="event__match"{match.group(2)}'

    return _ID_ROW.sub(repl, html)


def adapt_match_html(html: str) -> str:
    adapted = apply_class_renames(html, build_rename_map(html, MATCH_HINTS))
    adapted = ensure_match_row_classes(adapted)
    if adapted != html:
        logger.info("Match parser adapted renamed or missing class tokens")
    return adapted


def adapt_standings_html(html: str) -> str:
    adapted = apply_class_renames(html, build_rename_map(html, STANDING_HINTS))
    if adapted != html:
        logger.info("Standings parser adapted renamed class tokens")
    return adapted


def count_match_hints(html: str) -> int:
    return len(re.findall(r'id="g_\d+_', html)) + len(re.findall(r"event__match", html))


def count_standings_hints(html: str) -> int:
    return len(re.findall(r"ui-table__row", html)) + len(re.findall(r"table__row", html))


def parse_menu_leagues_from_hrefs(html: str, league_cls):
    """Structural fallback: sport/country/league URLs, ignoring CSS classes."""
    from urllib.parse import urlparse

    found = []
    seen: set[str] = set()
    skip = {"standings", "results", "fixtures", "draw", "news", "archive", "odds"}
    pattern = re.compile(
        r'href="((?:https?://(?:www\.)?flashscore\.com)?/([a-z0-9-]+)/([a-z0-9-]+)/([a-z0-9-]+)/?)"',
        re.I,
    )
    name_nearby = re.compile(r">(.*?)<", re.S)
    for match in pattern.finditer(html):
        href, sport, country, slug = match.group(1), match.group(2), match.group(3), match.group(4)
        if href in seen or slug in skip:
            continue
        seen.add(href)
        after = html[match.end() : match.end() + 400]
        texts = [" ".join(part.split()) for part in name_nearby.findall(after) if part.strip()]
        name = next((text for text in texts if len(text) > 1), slug.replace("-", " ").title())
        found.append(league_cls(name=name, slug=slug, url=href, sport=sport, country=country))
    return found


def parse_news_from_hrefs(html: str, news_cls) -> list:
    import html as html_lib

    items = []
    seen: set[str] = set()
    pattern = re.compile(
        r'<a\b([^>]*href="([^"]+/news/[^"]+)"[^>]*)>',
        re.I,
    )
    for match in pattern.finditer(html):
        attrs, link = match.group(1), html_lib.unescape(match.group(2))
        if link in seen:
            continue
        title_m = re.search(r'\btitle="([^"]+)"', attrs)
        title = html_lib.unescape(title_m.group(1)) if title_m else ""
        if not title:
            after = html[match.end() : match.end() + 300]
            inner = re.match(r"([^<]+)", after)
            if inner and inner.group(1).strip():
                title = " ".join(inner.group(1).split())
            else:
                texts = [" ".join(part.split()) for part in re.findall(r">([^<]+)<", after) if part.strip()]
                title = texts[0] if texts else ""
        if not title:
            continue
        seen.add(link)
        items.append(news_cls(title=title, link=link))
    return items
