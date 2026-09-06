"""
Agent 1 — deterministic rule-based extractor. NO LLM. Cannot hallucinate.

This is the independent anchor of the ensemble. Its errors have nothing in
common with the LLM extractors, so when Agent 1 agrees with an LLM agent, that
is the strongest corroboration the system can produce.

Low recall (finds maybe 40% of fields), very high precision. It emits the same
AgentClaim dict shape as the LLM extractors so verify.py treats it identically.

Critical rule: when a pattern does not match, it emits CANNOT_ASSESS, never
ABSENT. A regex miss is not evidence the term is absent — it is evidence this
method could not assess it.
"""

import re
import logging

logger = logging.getLogger(__name__)

AGENT_ID = "a1_rules"

# Field names must match extract.py FIELD_NAMES exactly.
NUM = r"(?:\d{1,4}|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|forty|forty-five|sixty|ninety)"

PATTERNS = {
    "start_date": [
        re.compile(r"[Ee]ffective\s+(?:as\s+of\s+)?(?:[Dd]ate[:\s]+)?((?:\w+\s+\d{1,2},?\s+\d{4})|(?:\d{1,2}\s+\w+\s+\d{4})|(?:\d{4}-\d{2}-\d{2}))"),
        re.compile(r"dated\s+(?:as\s+of\s+)?((?:\w+\s+\d{1,2},?\s+\d{4})|(?:\d{1,2}\s+\w+\s+\d{4}))"),
        re.compile(r"commenc\w+\s+on\s+((?:\w+\s+\d{1,2},?\s+\d{4})|(?:\d{1,2}\s+\w+\s+\d{4}))", re.I),
    ],
    "end_date": [
        re.compile(r"(?:expir\w+|terminat\w+|end)s?\s+on\s+((?:\w+\s+\d{1,2},?\s+\d{4})|(?:\d{1,2}\s+\w+\s+\d{4}))", re.I),
        re.compile(r"until\s+((?:\w+\s+\d{1,2},?\s+\d{4})|(?:\d{1,2}\s+\w+\s+\d{4}))", re.I),
    ],
    "notice_period_days": [
        re.compile(rf"({NUM})\s*(?:\(\d+\)\s*)?days'?\s+(?:prior\s+)?written\s+notice", re.I),
        re.compile(rf"(?:at\s+least\s+|not\s+less\s+than\s+)?({NUM})\s*(?:\(\d+\)\s*)?days'?\s+notice", re.I),
        re.compile(rf"written\s+notice\s+of\s+(?:at\s+least\s+)?({NUM})\s*(?:\(\d+\)\s*)?days", re.I),
    ],
    "liability_cap": [
        re.compile(r"(?:shall\s+not\s+exceed|limited\s+to|capped\s+at|maximum\s+(?:aggregate\s+)?liability\s+(?:shall\s+be\s+|of\s+)?)\s*((?:S\$|US\$|SGD|USD|RM|MYR|\$|£|€)\s?[\d,]+(?:\.\d{2})?)", re.I),
    ],
    "payment_obligations": [
        re.compile(r"(?:pay|fee\s+of|amount\s+of|sum\s+of|price\s+of|total\s+(?:of|consideration))\s+((?:S\$|US\$|SGD|USD|RM|MYR|\$|£|€)\s?[\d,]+(?:\.\d{2})?)", re.I),
    ],
    "governing_law": [
        re.compile(r"governed\s+by\s+(?:and\s+construed\s+in\s+accordance\s+with\s+)?the\s+laws?\s+of\s+(?:the\s+)?([A-Z][A-Za-z\s]{2,40}?)(?:[,\.]|\s+and\b|\s+without\b)"),
        re.compile(r"laws?\s+of\s+(?:the\s+)?(Republic\s+of\s+Singapore|Singapore|Malaysia|England(?:\s+and\s+Wales)?|New\s+York|Hong\s+Kong)", re.I),
    ],
    "renewal_type": [
        re.compile(r"(automatically\s+renew\w*)", re.I),
        re.compile(r"(auto-?renew\w*)", re.I),
        re.compile(r"(shall\s+(?:not\s+)?(?:be\s+)?renew\w+\s+for\s+successive)", re.I),
    ],
    "exclusivity": [
        re.compile(r"(exclusive\s+(?:right|distributor|licen[cs]e|supplier|agent))", re.I),
        re.compile(r"(sole\s+and\s+exclusive)", re.I),
    ],
    "restrictive_covenants": [
        re.compile(r"(shall\s+not\s+(?:directly\s+or\s+indirectly\s+)?compete)", re.I),
        re.compile(r"(non-?compet\w+)", re.I),
        re.compile(r"(non-?solicit\w+)", re.I),
    ],
    "contract_type": [
        re.compile(r"\b(Master\s+Services\s+Agreement|Non-?Disclosure\s+Agreement|Distribution\s+Agreement|Supply\s+(?:and\s+Maintenance\s+)?Agreement|Sublease|Lease\s+Agreement|Subscription\s+Agreement|Retainer|Order\s+Form|SAFE)\b", re.I),
    ],
}

CONTEXT = 100  # chars of quote context around a match


def _find_page_for_offset(pages: list[dict], full_text: str, offset: int) -> int:
    """Map a character offset in full_text back to a page number."""
    char_count = 0
    for page in pages:
        page_len = len(page.get("text", "")) + 2  # +2 for the join separator
        if char_count <= offset < char_count + page_len:
            return page.get("page_number", 0)
        char_count += page_len
    return pages[0].get("page_number", 0) if pages else 0


def run_rules_agent(doc_data: dict) -> list[dict]:
    """
    Scan the document with regex. Returns AgentClaim-shaped dicts.
    Same output contract as run_extractor_a / run_extractor_b.
    """
    full_text = doc_data.get("full_text", "")
    pages = doc_data.get("pages", [])
    claims = []

    if not full_text:
        return claims

    for field_name, patterns in PATTERNS.items():
        hit = None
        for pattern in patterns:
            match = pattern.search(full_text)
            if match and match.group(1):
                hit = match
                break

        if not hit:
            # CANNOT_ASSESS, never ABSENT — a regex miss is not evidence of absence.
            claims.append({
                "agent_id": AGENT_ID,
                "field_name": field_name,
                "status": "CANNOT_ASSESS",
                "value": None,
                "verbatim_quote": None,
                "quote_page": None,
                "quote_bbox": None,
            })
            continue

        value = hit.group(1).strip()

        # notice_period_days: normalise word-numbers to digits for the value
        if field_name == "notice_period_days":
            value = _word_to_digit(value)

        start = max(0, hit.start() - CONTEXT)
        end = min(len(full_text), hit.end() + CONTEXT)
        quote = full_text[start:end].strip()
        page = _find_page_for_offset(pages, full_text, hit.start())

        claims.append({
            "agent_id": AGENT_ID,
            "field_name": field_name,
            "status": "FOUND",
            "value": value,
            "verbatim_quote": quote,
            "quote_page": page,
            "quote_bbox": None,
        })
        logger.info(f"{AGENT_ID}: found {field_name} = {value!r} on page {page}")

    return claims


_WORD_NUM = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "fifteen": "15", "twenty": "20", "thirty": "30", "forty": "40",
    "forty-five": "45", "sixty": "60", "ninety": "90",
}


def _word_to_digit(value: str) -> str:
    low = value.lower().strip()
    return _WORD_NUM.get(low, value)
