"""
Shared coercion helpers for values that come from an LLM's JSON output.

Why this file exists: an LLM asked for a "page number" or a "day count" will
occasionally hand back the right idea in the wrong Python type — "3" instead
of 3, 90 instead of "90", 3.0 instead of 3. Two crashes already happened from
this exact pattern (notice_period_days as an int where text was expected;
quote_page as a string where a number was expected) on two different fields
in two different agents. That is not a coincidence, it is a property of
asking a language model for "numbers" and "text" — it does not reliably
distinguish them at the JSON level, and nothing in our code should assume it
did.

Rule going forward: any field that we are about to compare, sort, or do
arithmetic on, and that ORIGINATED from an LLM response, goes through one of
these functions first. Fields we only ever display or interpolate into an
f-string (page numbers in log messages, for example) don't need this — Python
formats an int and a string identically. It is comparisons and arithmetic
that crash.
"""

import re


def coerce_page(value) -> int | None:
    """
    Normalise a "page number" to a real int, or None if it cannot be one.

    Handles: None, bool (rejected — True/False are technically ints in
    Python but are never a meaningful page number), int, float, and strings
    like "3", "page 3", "3.0".
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+", value)
        return int(match.group()) if match else None
    return None


def coerce_str(value) -> str:
    """
    Normalise anything to text. Same idea as verify.py's
    normalize_whitespace(), kept here too so files that don't already import
    from verify.py (agents, in particular) have a lightweight way to guard a
    value before calling a string method on it, without creating an import
    dependency on the verification module.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return str(value)
    return value


def coerce_int(value, default: int | None = None) -> int | None:
    """
    Normalise a count/quantity (days, years, etc.) to an int. Same shape of
    problem as coerce_page, kept separate because "no valid number found"
    should fall back to a caller-supplied default rather than always None —
    calendar math, for instance, wants 0 notice days as its sensible default,
    not a bare None it then has to guard again.
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+", value)
        return int(match.group()) if match else default
    return default
