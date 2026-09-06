"""
Semantic value normalization, used ONLY for grouping claims by agreement in
verify.py's resolve_field(). This is a different job from normalize_whitespace():

  normalize_whitespace() cleans up TEXT artifacts (extra spaces, soft
  hyphens) so the SAME string compares equal despite noisy extraction.

  normalize_value() (this file) converts DIFFERENT-LOOKING but SAME-MEANING
  values to one canonical form, so "90 days", "ninety (90) days", and "3
  months" all group together instead of registering as three agents in
  disagreement when they actually agree.

Why this matters: resolve_field() counts `disagreement = len(votes) -
agreement_count`, and VERIFIED requires disagreement == 0. Four agents that
all correctly find a 90-day notice period, but phrase it four different
ways, were being treated as four-way disagreement — capping confidence at
INFERRED or worse even though every agent agreed in substance. This is the
single most likely reason a lot of fields were landing at medium confidence
rather than high: not because the agents disagreed, but because nothing was
telling the code that they didn't.

Each function returns a canonical string for ONE value. Two values that mean
the same thing must return the identical string; two that mean different
things must not. Falls back to normalize_whitespace()'s cleanup for any field
with no specific normalizer — that field's grouping behaviour is completely
unchanged from before this file existed.
"""

import re
from datetime import datetime


_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "forty-five": 45,
    "sixty": 60, "ninety": 90, "one hundred eighty": 180,
    "three hundred sixty-five": 365,
}

_DURATION_UNIT_DAYS = {
    "day": 1, "days": 1,
    "week": 7, "weeks": 7,
    "month": 30, "months": 30,
    "year": 365, "years": 365,
}

_CURRENCY_ALIASES = {
    "s$": "SGD", "sgd": "SGD", "singapore dollars": "SGD", "singapore dollar": "SGD",
    "us$": "USD", "usd": "USD", "us dollars": "USD", "$": "USD",
    "£": "GBP", "gbp": "GBP",
    "€": "EUR", "eur": "EUR",
    "rm": "MYR", "myr": "MYR", "ringgit": "MYR",
}

_LEGAL_SUFFIXES = re.compile(
    r"\b(pte\.?|ltd\.?|limited|llc|l\.l\.c\.|inc\.?|incorporated|corp\.?|"
    r"corporation|plc|gmbh|sdn\.?|bhd\.?|co\.?|company|llp|lp)\b",
    re.IGNORECASE,
)


def _word_to_number(token: str) -> int | None:
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return _WORD_NUMBERS.get(token)


def normalize_duration_days(raw: str) -> str | None:
    """
    'ninety (90) days', '90 days', '3 months' -> a canonical day-count key
    like 'DAYS:90'. Returns None if no duration could be parsed (caller
    should fall back to normalize_whitespace() in that case, not treat None
    as a value).

    Prefers a parenthesised numeral when present — "ninety (90) days" — since
    that is the unambiguous, author-disambiguated form contracts use
    specifically to avoid this kind of confusion.
    """
    if not raw:
        return None
    text = raw.lower()

    paren = re.search(r"\((\d{1,4})\)\s*(day|week|month|year)s?", text)
    if paren:
        n, unit = int(paren.group(1)), paren.group(2)
        return f"DAYS:{n * _DURATION_UNIT_DAYS[unit + 's']}"

    word_pattern = "|".join(re.escape(w) for w in _WORD_NUMBERS)
    match = re.search(
        rf"\b(\d{{1,4}}|{word_pattern})\b[\s-]*\(?\d*\)?\s*(day|week|month|year)s?\b",
        text,
    )
    if match:
        n = _word_to_number(match.group(1))
        if n is not None:
            unit = match.group(2) + "s"
            return f"DAYS:{n * _DURATION_UNIT_DAYS[unit]}"

    # No unit word found at all — this happens routinely from Agent 1
    # (rules), whose regex captures just the digits for this field ("90",
    # not "90 days"). The field itself is named notice_period_DAYS, so a
    # bare number here already means days; treat it as such rather than
    # falling through to whitespace-only comparison, which would otherwise
    # leave this one agent's vote out of a group the other three correctly
    # joined.
    bare = text.strip()
    if bare.isdigit():
        return f"DAYS:{int(bare)}"
    bare_word = _word_to_number(bare)
    if bare_word is not None:
        return f"DAYS:{bare_word}"

    return None


def normalize_money(raw: str) -> str | None:
    """
    'S$50,000', 'SGD 50,000.00', 'S$ 50000' -> 'SGD:50000.00'.
    'unlimited' / 'uncapped' / 'no cap' -> 'UNCAPPED'.
    Returns None if no monetary value could be parsed.
    """
    if not raw:
        return None
    text = raw.strip()

    if re.search(r"\b(unlimited|uncapped|no\s+cap|not\s+limited|shall\s+not\s+be\s+limited)\b", text, re.I):
        return "UNCAPPED"

    match = re.search(
        r"(S\$|US\$|SGD|USD|GBP|EUR|RM|MYR|[$£€])\s*([\d][\d,]*(?:\.\d{1,2})?)",
        text, re.I,
    )
    if not match:
        digits_only = re.search(r"([\d][\d,]*(?:\.\d{1,2})?)", text)
        if not digits_only:
            return None
        amount = float(digits_only.group(1).replace(",", ""))
        return f"UNK:{amount:.2f}"

    currency = _CURRENCY_ALIASES.get(match.group(1).lower(), match.group(1).upper())
    amount = float(match.group(2).replace(",", ""))
    return f"{currency}:{amount:.2f}"


def normalize_date(raw: str) -> str | None:
    """
    '14 March 2023', 'March 14, 2023', '2023-03-14' -> '2023-03-14'.
    Returns None if the text could not be parsed as a date at all — this is
    intentionally conservative rather than guessing.
    """
    if not raw:
        return None
    text = raw.strip()

    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        try:
            return datetime(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))).date().isoformat()
        except ValueError:
            pass

    for fmt in ("%d %B %Y", "%B %d, %Y", "%B %d %Y", "%d/%m/%Y", "%m/%d/%Y",
                "%d-%m-%Y", "%d %b %Y", "%b %d, %Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue

    match = re.search(
        r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+(\d{4})",
        text, re.I,
    )
    if match:
        try:
            return datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %B %Y").date().isoformat()
        except ValueError:
            pass

    return None


def normalize_party_name(raw: str) -> str | None:
    """
    'Acme Pte. Ltd.' and 'ACME PTE LTD' -> 'acme' — strips common legal
    entity suffixes and case/punctuation so the same company named two
    different ways by two different agents groups together.
    """
    if not raw:
        return None
    text = _LEGAL_SUFFIXES.sub("", raw.lower())
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def normalize_boolean_ish(raw: str) -> str | None:
    """
    For fields whose answer is essentially yes/no dressed up as prose —
    'exclusivity', 'restrictive_covenants' — map common phrasings to one of
    two canonical tokens so "Yes, exclusive rights are granted" and
    "Exclusive" group together instead of being treated as different values.
    """
    if not raw:
        return None
    text = raw.strip().lower()
    if re.search(r"\b(yes|exclusive|granted|present|applies|included)\b", text):
        return "YES"
    if re.search(r"\b(no|non-exclusive|not\s+granted|absent|none|not\s+applicable|n/?a)\b", text):
        return "NO"
    return None


# Dispatch table: field_name -> normalizer function. Any field not listed
# here falls back to normalize_whitespace()'s existing text cleanup in
# verify.py — completely unchanged behaviour for those fields.
_NORMALIZERS = {
    "start_date": normalize_date,
    "end_date": normalize_date,
    "notice_period_days": normalize_duration_days,
    "liability_cap": normalize_money,
    "payment_obligations": normalize_money,
    "parties": normalize_party_name,
    "exclusivity": normalize_boolean_ish,
}


def normalize_value(field_name: str, raw: str, whitespace_fallback) -> str:
    """
    The single entry point resolve_field() calls when grouping claims.

    Tries the field-specific semantic normalizer first. If it exists AND
    successfully parses the value, use its canonical form. Otherwise (no
    normalizer for this field, or the value didn't match any known pattern)
    fall back to whitespace_fallback (normalize_whitespace from verify.py),
    exactly as before — this function can only make grouping MORE accurate,
    never less; a value it can't confidently canonicalize is left exactly as
    it was being compared before this existed.
    """
    normalizer = _NORMALIZERS.get(field_name)
    if normalizer:
        canonical = normalizer(raw)
        if canonical is not None:
            return canonical
    return whitespace_fallback(raw)
