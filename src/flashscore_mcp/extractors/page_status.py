"""Tell empty-but-valid pages apart from failed loads."""
from __future__ import annotations

import re

from loguru import logger

class LoadFailed(RuntimeError):
    """The page did not load or could not be parsed; this is not an empty result."""

    def __init__(self, message: str, reason: str = "parse-failed"):
        super().__init__(message)
        self.reason = reason


_EMPTY_HINTS = (
    "no matches",
    "there are no matches",
    "currently no matches",
    "no events scheduled",
    "no data available",
    "no games found",
    "there are no games",
    "no news",
    "no articles",
)

# Messages the site renders in place of a tab's content. They are checked
# before the fail hints because ad scripts on these pages can mention
# "captcha" and the like even when the page loaded fine.
_SITE_EMPTY_MESSAGES = (
    "no betting odds were found",
)

_FAIL_HINTS = (
    "cf-challenge",
    "cf-browser-verification",
    "just a moment",
    "access denied",
    "attention required",
    "captcha",
    "enable javascript",
)


def classify_page(html: str, *, tab: str, parsed_count: int, raw_hints: int = 0) -> str:
    """Return 'ok', 'empty', or 'failed'."""
    if parsed_count > 0:
        return "ok"
    text = html or ""
    low = text.lower()
    if len(text) < 1500:
        return "failed"
    if "flashscore" not in low:
        return "failed"
    if raw_hints == 0 and any(msg in low for msg in _SITE_EMPTY_MESSAGES):
        return "empty"
    if any(hint in low for hint in _FAIL_HINTS):
        return "failed"
    if raw_hints > 0:
        return "failed"
    if any(hint in low for hint in _EMPTY_HINTS):
        return "empty"
    if tab in {"results", "fixtures", "live", "day", "team", "h2h", "match"}:
        has_shell = bool(
            re.search(r'id="live-table"|event--leagues|leagues--static|sportName', text)
        )
        has_rows = bool(re.search(r'id="g_\d+_|event__match', text))
        if has_shell and not has_rows:
            return "empty"
        return "failed"
    if tab == "standings":
        if "draw__bracket" in text or "ui-table" in text:
            return "empty"
        return "failed"
    if tab == "news":
        if "news" in low:
            return "empty"
        return "failed"
    if tab == "odds":
        has_unparsed = bool(re.search(r"oddsValue|odds__odd|wcl-odds", text))
        return "failed" if has_unparsed else "empty"
    if tab == "archive":
        if "league_archive_data" in text:
            return "empty"
        return "failed"
    if tab in {"leagues", "league"}:
        return "empty" if "flashscore" in low else "failed"
    return "failed"


def page_outcome(html: str, *, tab: str, parsed_count: int, raw_hints: int = 0) -> tuple[str, str | None]:
    """Return (status, reason) with named empty/failure reasons."""
    status = classify_page(html, tab=tab, parsed_count=parsed_count, raw_hints=raw_hints)
    if status == "ok":
        return "ok", None
    if status == "empty":
        if tab == "h2h":
            # Head-to-head is history, not a schedule: the teams have not met.
            return "empty", "no-meetings"
        if tab in {"results", "fixtures", "live", "day", "team", "match"}:
            return "empty", "no-matches-scheduled"
        return "empty", "no-data"
    text = html or ""
    low = text.lower()
    if len(text) < 1500 or "flashscore" not in low or any(hint in low for hint in _FAIL_HINTS):
        return "failed", "source-refused"
    return "failed", "parse-failed"


def empty_or_raise(html: str, tab: str, items, raw_hints: int = 0):
    status, reason = page_outcome(html, tab=tab, parsed_count=len(items), raw_hints=raw_hints)
    if status == "failed":
        logger.error("Failed to load {} (not an empty result); reason={} raw_hints={}", tab, reason, raw_hints)
        raise LoadFailed(
            f"Failed to load {tab}: the page did not contain usable {tab} data. "
            "This is a failed load, not an empty result.",
            reason=reason or "parse-failed",
        )
    if status == "empty":
        logger.info("{} page loaded successfully but has no data ({})", tab.capitalize(), reason)
    return items
