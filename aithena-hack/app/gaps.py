"""
Missing-contract detection via dangling-reference analysis.

The strongest version of "what are we missing?" needs no external data at all:
contracts constantly reference OTHER documents — a parent agreement an
amendment modifies, a schedule, an annex. If the referenced document isn't in
the folder, that's a gap the client should see.

THREE OUTCOMES, not two — this is the honesty core:
  resolved   — we found a strong match for the reference in the corpus
  ambiguous  — we found partial matches but can't be sure (shown with reasons)
  unresolved — nothing plausible in the corpus

Critical language rule, enforced in every output: we NEVER say "you are
missing a contract." We say "we found a reference we could not resolve." An
unresolved reference does not prove the document is absent — it may be present
under a name we couldn't match, or superseded, or our own party extraction may
have failed. The evidence is always a verbatim quote from a document we hold,
so the finding itself is fully grounded either way.
"""

import re
from difflib import SequenceMatcher

LANGUAGE_NOTE = (
    "We found a reference we could not resolve to a document in this folder. "
    "This does not prove the document is missing — it may be filed under a "
    "different name, or superseded. The quoted text is from a document you have."
)

# Patterns that indicate a reference TO another document.
_REFERENCE_PATTERNS = [
    # "Amendment ... to the Master Services Agreement dated 3 March 2022"
    (r"amendment\s+(?:no\.?\s*\d+\s+)?to\s+(?:the\s+)?([A-Z][A-Za-z \-]{5,60}?(?:Agreement|Contract|Deed|MSA|Lease))\b(?:\s+dated\s+([\w \d,]+?\d{4}))?",
     "unresolved_parent"),
    # "the Master Services Agreement dated ... between"
    (r"(?:under|pursuant to|governed by)\s+(?:the\s+)?([A-Z][A-Za-z \-]{5,60}?(?:Agreement|Contract|Deed|MSA))\b(?:\s+dated\s+([\w \d,]+?\d{4}))?",
     "unresolved_reference"),
    # "as set out in Schedule C" / "Annex 2" / "Exhibit B" / "Appendix 1"
    (r"(?:set out in|attached as|in accordance with|pursuant to)\s+(Schedule\s+[A-Z0-9]+|Annex\s+[A-Z0-9]+|Exhibit\s+[A-Z0-9]+|Appendix\s+[A-Z0-9]+)\b",
     "missing_schedule"),
]

_STOPWORDS = {"the", "a", "an", "of", "and", "to", "agreement", "contract", "deed"}


def _tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in _STOPWORDS}


def _title_similarity(ref: str, candidate_filename: str, candidate_type: str) -> float:
    """How well does a reference match a candidate document in the corpus?"""
    ref_t = _tokens(ref)
    cand_t = _tokens(candidate_filename) | _tokens(candidate_type)
    if not ref_t or not cand_t:
        return 0.0
    overlap = len(ref_t & cand_t) / len(ref_t)
    seq = SequenceMatcher(None, ref.lower(), (candidate_filename or "").lower()).ratio()
    return round(0.7 * overlap + 0.3 * seq, 3)


def _extract_references(raw_text: str) -> list[dict]:
    """Find all outbound document references in one contract's text."""
    refs = []
    seen = set()
    for pattern, kind in _REFERENCE_PATTERNS:
        for m in re.finditer(pattern, raw_text or "", re.IGNORECASE):
            ref_name = m.group(1).strip()
            ref_date = m.group(2).strip() if m.lastindex and m.lastindex >= 2 and m.group(2) else None
            key = (kind, ref_name.lower())
            if key in seen:
                continue
            seen.add(key)
            # Grab a verbatim quote around the match for grounding.
            start = max(0, m.start() - 20)
            end = min(len(raw_text), m.end() + 40)
            refs.append({
                "kind": kind,
                "ref_name": ref_name,
                "ref_date": ref_date,
                "quote": raw_text[start:end].strip(),
            })
    return refs


def detect_gaps(all_contracts: list[dict]) -> list[dict]:
    """
    For every contract, find outbound references and try to resolve each
    against the rest of the corpus. Returns a list of gap dicts for anything
    that did not cleanly resolve (ambiguous or unresolved).

    all_contracts: list of dicts with keys: id, filename, contract_type,
                   raw_text, start_date (whatever _get_all_contracts provides).
    """
    gaps = []

    for contract in all_contracts:
        raw_text = contract.get("raw_text") or ""
        source_name = contract.get("filename", "")
        refs = _extract_references(raw_text)

        for ref in refs:
            # Schedules/annexes are internal to their own document — resolve
            # against THIS contract's text, not the corpus.
            if ref["kind"] == "missing_schedule":
                # Does the schedule name appear again elsewhere in the doc
                # (i.e. it's actually attached), beyond the reference itself?
                occurrences = len(re.findall(re.escape(ref["ref_name"]), raw_text, re.I))
                if occurrences <= 1:
                    gaps.append({
                        "source_contract_id": contract.get("id"),
                        "source_filename": source_name,
                        "kind": "missing_schedule",
                        "reference_text": ref["quote"],
                        "resolution": "unresolved",
                        "candidates": [],
                        "language_note": (
                            f"This document refers to {ref['ref_name']}, but that "
                            f"schedule does not appear elsewhere in the file we have."
                        ),
                    })
                continue

            # Parent/other-agreement references: resolve against the corpus.
            candidates = []
            for other in all_contracts:
                if other.get("id") == contract.get("id"):
                    continue
                score = _title_similarity(
                    ref["ref_name"],
                    other.get("filename", ""),
                    other.get("contract_type", ""),
                )
                if score >= 0.3:
                    reject = None
                    # Date cross-check: if the reference names a date and the
                    # candidate has a different start date, note the mismatch.
                    if ref.get("ref_date") and other.get("start_date"):
                        ref_year = re.search(r"\d{4}", ref["ref_date"])
                        cand_year = re.search(r"\d{4}", str(other.get("start_date")))
                        if ref_year and cand_year and ref_year.group() != cand_year.group():
                            reject = (f"date mismatch: reference says {ref['ref_date']}, "
                                      f"candidate dated {other.get('start_date')}")
                    candidates.append({
                        "filename": other.get("filename"),
                        "score": score,
                        "rejected_because": reject,
                    })

            candidates.sort(key=lambda c: c["score"], reverse=True)
            strong = [c for c in candidates if c["score"] >= 0.6 and not c["rejected_because"]]

            if strong:
                continue  # resolved — a strong, un-rejected match exists

            if candidates:
                gaps.append({
                    "source_contract_id": contract.get("id"),
                    "source_filename": source_name,
                    "kind": ref["kind"],
                    "reference_text": ref["quote"],
                    "resolution": "ambiguous",
                    "candidates": candidates[:3],
                    "language_note": LANGUAGE_NOTE,
                })
            else:
                gaps.append({
                    "source_contract_id": contract.get("id"),
                    "source_filename": source_name,
                    "kind": ref["kind"],
                    "reference_text": ref["quote"],
                    "resolution": "unresolved",
                    "candidates": [],
                    "language_note": LANGUAGE_NOTE,
                })

    return gaps
