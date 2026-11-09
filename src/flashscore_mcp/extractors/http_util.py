"""Small HTTP GETs that do not need a rendered page (stdlib, no new deps)."""
from __future__ import annotations

import asyncio
import json
import urllib.request
from typing import Any, Optional

from loguru import logger

from ..config import settings


def _get(url: str, timeout: float) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": settings.user_agent,
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": settings.base_url.rstrip("/") + "/",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed hosts
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


async def get_text(url: str, timeout: float = 8.0, browser_fallback: bool = True) -> Optional[str]:
    try:
        return await asyncio.to_thread(_get, url, timeout)
    except Exception as exc:
        logger.debug("HTTP GET failed {}: {}", url, exc)
    if not browser_fallback:
        return None
    # Some hosts refuse non-browser clients; retry through the browser's
    # request context (same network path as the page loads).
    try:
        from ..browser import browser_manager

        async with browser_manager.new_page() as page:
            resp = await page.request.get(
                url,
                headers={"Referer": settings.base_url.rstrip("/") + "/"},
                timeout=timeout * 1000,
            )
            if resp.ok:
                return await resp.text()
            logger.debug("Browser GET {} -> {}", url, resp.status)
    except Exception as exc:
        logger.debug("Browser GET failed {}: {}", url, exc)
    return None


async def get_json(url: str, timeout: float = 8.0) -> Any:
    text = await get_text(url, timeout)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None
