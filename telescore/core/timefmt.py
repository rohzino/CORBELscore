"""
Time formatting and parsing for TeleScore clocks.

All clock values are integer milliseconds. Formatting is a pure function so the
same rules apply to the operator panel, text files, XML and the browser source.

Format tokens (case-insensitive):
    h / hh   hours
    m / mm   minutes (total minutes when the format has no hour token)
    s / ss   seconds (total seconds when the format has no minute token)
    t        tenths of a second   (``z`` is accepted as the legacy spelling)
    tt       hundredths of a second
Anything else is copied literally, so ``m:ss.t`` renders ``4:07.3``.
"""

from __future__ import annotations

import math
import re

__all__ = ["format_ms", "parse_time", "ordinal", "LEGACY_FORMATS", "TimeParseError"]

# Formats offered by TeleScore 1.x, kept so old projects open unchanged.
LEGACY_FORMATS = ["mm:ss", "hh:mm:ss", "m:ss", "mm", "ss", "hh",
                  "mm:ss.z", "hh:mm:ss.z", "ss.z"]

_TOKEN = re.compile(r"(h+|m+|s+|t+|z+)", re.IGNORECASE)


class TimeParseError(ValueError):
    """Raised when a typed time cannot be understood."""


def _round_ms(ms: int, unit: int, countdown: bool) -> int:
    """Quantise ``ms`` to ``unit``.

    Whole-second countdowns round up, so 0.4 s left shows 0:01 and never 0:00
    while the clock still runs. Tenths and hundredths truncate, as arena
    clocks do, so the hand-off at a one-minute threshold reads 1:00 -> 59.9."""
    if ms <= 0:
        return 0
    if countdown and unit >= 1000:
        return int(math.ceil(ms / unit)) * unit
    return (ms // unit) * unit


def format_ms(ms: int, fmt: str = "m:ss", countdown: bool = True) -> str:
    """Render ``ms`` milliseconds with ``fmt``.

    The smallest unit in the format decides the rounding: a countdown at
    4 999 ms in ``m:ss`` shows ``0:05``; with ``s.t`` it shows ``5.0``.
    Negative values are clamped to zero.
    """
    ms = max(0, int(ms))
    tokens = [t.lower() for t in _TOKEN.findall(fmt)]
    has_h = any(t[0] == "h" for t in tokens)
    has_m = any(t[0] == "m" for t in tokens)
    has_s = any(t[0] == "s" for t in tokens)
    frac_tokens = [t for t in tokens if t[0] in "tz"]
    if any(len(t) >= 2 for t in frac_tokens):
        unit = 10
    elif frac_tokens:
        unit = 100
    elif has_s:
        unit = 1000
    elif has_m:
        unit = 60_000
    elif has_h:
        unit = 3_600_000
    else:
        unit = 1000
    q = _round_ms(ms, unit, countdown)

    hours = q // 3_600_000
    minutes = q // 60_000 if not has_h else (q // 60_000) % 60
    seconds = q // 1000 if not (has_h or has_m) else (q // 1000) % 60
    tenths = (q // 100) % 10
    hundredths = (q // 10) % 100

    def repl(match: re.Match) -> str:
        tok = match.group(0).lower()
        kind, width = tok[0], len(tok)
        if kind == "h":
            return f"{hours:0{width}d}"
        if kind == "m":
            return f"{minutes:0{width}d}"
        if kind == "s":
            return f"{seconds:0{width}d}"
        # tenths / hundredths ('z' is the legacy tenths token)
        return f"{hundredths:02d}" if width >= 2 else f"{tenths:d}"

    return _TOKEN.sub(repl, fmt)


_PARSE = re.compile(
    r"^\s*(?:(?P<a>\d+)\s*:\s*)?(?:(?P<b>\d+)\s*:\s*)?(?P<c>\d+)?(?:[.,](?P<frac>\d{1,3}))?\s*$"
)


def parse_time(text: str) -> int:
    """Parse operator input into milliseconds.

    Accepted: ``12:00``, ``1:02:03``, ``45`` (seconds), ``4:07.3``, ``.5``,
    ``8:`` (minutes), ``90`` (90 seconds). Raises :class:`TimeParseError`.
    """
    raw = (text or "").strip()
    if not raw:
        raise TimeParseError("Type a time such as 12:00 or 45.")
    if raw.endswith(":"):
        raw = raw + "00"
    m = _PARSE.match(raw)
    if not m or (m.group("c") is None and m.group("frac") is None and m.group("a") is None):
        raise TimeParseError(f"{text!r} is not a time. Use m:ss, h:mm:ss or seconds.")
    a, b, c = m.group("a"), m.group("b"), m.group("c")
    parts = [int(p) for p in (a, b, c) if p is not None]
    if len(parts) == 3:
        h, mi, s = parts
    elif len(parts) == 2:
        h, (mi, s) = 0, parts
    elif len(parts) == 1:
        h, mi, s = 0, 0, parts[0]
    else:
        h = mi = s = 0
    if len(parts) >= 2 and s >= 60:
        raise TimeParseError(f"{text!r}: seconds must be under 60 when minutes are given.")
    if len(parts) == 3 and mi >= 60:
        raise TimeParseError(f"{text!r}: minutes must be under 60 when hours are given.")
    frac = m.group("frac") or ""
    frac_ms = int((frac + "00")[:3]) if frac else 0
    return ((h * 60 + mi) * 60 + s) * 1000 + frac_ms


def ordinal(n: int) -> str:
    """1 -> 1st, 2 -> 2nd, 11 -> 11th, 112 -> 112th, 21 -> 21st."""
    n = int(n)
    if 10 <= abs(n) % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(abs(n) % 10, "th")
    return f"{n}{suffix}"
