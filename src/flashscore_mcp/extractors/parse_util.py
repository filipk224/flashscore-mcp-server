"""Shared parse helpers for Flashscore event rows."""
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Optional, Tuple

_SCORE_RE = re.compile(r"(\d+)\s*[-\u2013]\s*(\d+)")
_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")
_DATE_RE = re.compile(r"\b(\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)\b")
_NOISE = {
    "ft", "aet", "pen", "live", "finished", "scheduled", "postponed",
    "cancelled", "canceled", "awarded", "walkover", "show more",
    "standings", "results", "fixtures",
}

def parse_int(text: str) -> Optional[int]:
    if text is None:
        return None
    cleaned = text.strip().replace(",", "")
    if not cleaned:
        return None
    m = re.search(r"^-?\d+$", cleaned)
    if m:
        return int(cleaned)
    m = re.search(r"(-?\d+)", cleaned)
    return int(m.group(1)) if m else None

def parse_score_pair(text: str) -> Optional[Tuple[int, int]]:
    if not text:
        return None
    t = text.replace("\u2013", "-").replace("\u2014", "-")
    m = _SCORE_RE.search(t)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None

def looks_like_team(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    if len(t) < 2 or len(t) > 60:
        return False
    low = t.lower()
    if low in _NOISE:
        return False
    if _SCORE_RE.search(t):
        return False
    if _TIME_RE.fullmatch(t):
        return False
    if re.fullmatch(r"\d+[./-]\d+(?:[./-]\d+)?", t):
        return False
    return True

def split_datetime(text: str) -> Tuple[Optional[str], Optional[str]]:
    if not text:
        return None, None
    t = text.strip()
    time_m = _TIME_RE.search(t)
    date_m = _DATE_RE.search(t)
    date = date_m.group(1) if date_m else None
    time = time_m.group(1) if time_m else None
    if not date and not time:
        compact = re.search(r"(\d{1,2}\.\d{1,2}\.?)\s*(\d{1,2}:\d{2})?", t)
        if compact:
            date = compact.group(1)
            time = compact.group(2)
        else:
            date = t
    return date, time

def parse_fixture_datetime(date_s: Optional[str], time_s: Optional[str]) -> Optional[datetime]:
    if not date_s:
        return None
    raw = f"{date_s} {time_s or ''}".strip()
    raw = raw.replace(".", "/").replace("-", "/")
    now = datetime.now(timezone.utc)
    candidates = ["%d/%m/%Y %H:%M", "%d/%m/%y %H:%M", "%d/%m %H:%M", "%d/%m/%Y", "%d/%m/%y", "%d/%m"]
    for fmt in candidates:
        try:
            dt = datetime.strptime(raw.split()[0] + ((" " + time_s) if time_s and "%H" in fmt else ""), fmt)
            if dt.year == 1900:
                dt = dt.replace(year=now.year)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None

def is_future(date_s: Optional[str], time_s: Optional[str]) -> bool:
    dt = parse_fixture_datetime(date_s, time_s)
    if dt is None:
        return True
    return dt >= datetime.now(timezone.utc)

EXTRACT_MATCHES_JS = """
() => {
  const rows = Array.from(document.querySelectorAll(
    ".event__match, [class*='event__match'], [id^='g_']"
  ));
  return rows.map((el) => {
    const txt = (el.innerText || "").trim();
    const homeEl = el.querySelector(".event__participant--home, [class*='participant--home'], [class*='homeParticipant']");
    const awayEl = el.querySelector(".event__participant--away, [class*='participant--away'], [class*='awayParticipant']");
    const hsEl = el.querySelector(".event__score--home, [class*='score--home']");
    const asEl = el.querySelector(".event__score--away, [class*='score--away']");
    const timeEl = el.querySelector(".event__time, [class*='event__time'], [class*='time']");
    const status = (el.getAttribute("class") || "") + " " + txt.toLowerCase();
    return {
      text: txt,
      home: homeEl ? homeEl.innerText.trim() : "",
      away: awayEl ? awayEl.innerText.trim() : "",
      home_score: hsEl ? hsEl.innerText.trim() : "",
      away_score: asEl ? asEl.innerText.trim() : "",
      time: timeEl ? timeEl.innerText.trim() : "",
      scheduled: /scheduled|not started/.test(status) || (!hsEl && !asEl),
      finished: /event__match--static|finished|ft\\b/.test(status),
    };
  });
}
"""
