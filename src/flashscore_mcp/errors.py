"""Errors shared by the browser layer and the extractors."""
from __future__ import annotations


class LoadFailed(RuntimeError):
    """The page did not load or could not be parsed; this is not an empty result."""

    def __init__(self, message: str, reason: str = "parse-failed"):
        super().__init__(message)
        self.reason = reason


class BusyError(LoadFailed):
    """Every browser slot stayed in use for the whole queue-wait cap."""

    def __init__(self, message: str):
        super().__init__(message, reason="busy")


# Reason text for a section that was requested but not loaded before the
# budget ran out. It starts with "timeout" so callers can tell it apart from
# a genuinely empty section (which is returned as an empty list, no error).
SECTION_TIMEOUT = "timeout: section not loaded within budget"
