import re
import logging
from rapidfuzz import fuzz
from app.schemas import Confidence, Provenance, FieldStatus
from app.safe_types import coerce_page
from app.value_normalize import normalize_value

logger = logging.getLogger(__name__)

# Thresholds (from your Master Reference, tune during calibration)
SPAN_GATE_THRESHOLD = 85       # rapidfuzz score to pass the span gate
VERIFIED_THRESHOLD = 85         # agreement + span pass = VERIFIED
INFERRED_THRESHOLD = 65         # partial match = INFERRED


def normalize_whitespace(text) -> str:
    """
    Collapse whitespace, strip soft hyphens and zero-width chars.
    This is the fix for the 'whitespace trap' — PDF extraction produces
    messy output that breaks strict matching.

    Also coerces non-string input to text. An LLM asked for a numeric-sounding
    field (e.g. notice_period_days) will sometimes return a bare JSON number
    (90) instead of a string ("90"). Both mean the same thing to a person, but
    an int has no .replace()/.strip() methods, so without this coercion a
    single mistyped field from ANY agent crashes verification for the WHOLE
    document, not just that field.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return ""
    # Remove soft hyphens, zero-width chars
    text = text.replace("\u00ad", "").replace("\u200b", "").replace("\u200c", "")
    # Collapse all whitespace to single space
    text = re.sub(r"\s+", " ", text).strip()
    return text

def span_gate(claim: dict, pages: list[dict]) -> dict:
    """
    Check if the claimed verbatim_quote actually exists in the page text.
    Returns the claim dict with span_score added, and discarded=True if it fails.
    
    THIS IS THE KEY MECHANISM: an agent that can't quote can't be verified.
    A fabricated citation is DISCARDED entirely, not downweighted.
    """
    quote = claim.get("verbatim_quote")
    if not quote or claim.get("status") != "FOUND":
        # No quote to check — can't verify, but don't discard. Still coerce
        # quote_page here for consistency, even though this branch does not
        # itself compare it to anything.
        claim["span_score"] = 0.0
        claim["discarded"] = False
        claim["quote_page"] = coerce_page(claim.get("quote_page"))
        return claim

    quote_norm = normalize_whitespace(quote)
    best_score = 0.0
    # An LLM occasionally returns the page as a string ("3") or float (3.0)
    # instead of an int. The comparison two lines below (0 <= best_page < ...)
    # crashes on a string with TypeError — this is what took down
    # "Bright Cove retainer + side letter.docx". coerce_page() normalises it
    # to a real int, or None if it genuinely cannot be read as one.
    best_page = coerce_page(claim.get("quote_page"))

    # Search the claimed page first, then all pages
    page_order = []
    if best_page is not None and 0 <= best_page < len(pages):
        page_order.append(best_page)
    page_order.extend(i for i in range(len(pages)) if i not in page_order)

    for page_idx in page_order:
        page_text = pages[page_idx].get("text", "")
        page_text_norm = normalize_whitespace(page_text)
        if not page_text_norm:
            continue

        score = fuzz.partial_ratio(quote_norm, page_text_norm)
        if score > best_score:
            best_score = score
            best_page = page_idx

    claim["span_score"] = best_score
    claim["quote_page"] = best_page

    if best_score < SPAN_GATE_THRESHOLD:
        # DISCARD — this quote doesn't exist in the document
        claim["discarded"] = True
        claim["discard_reason"] = (
            f"span gate failed: best match {best_score:.1f} < {SPAN_GATE_THRESHOLD} threshold"
        )
        logger.warning(
            f"FABRICATION DETECTED: {claim['agent_id']}/{claim['field_name']} "
            f"— quote not found (score {best_score:.1f})"
        )
    else:
        claim["discarded"] = False

    return claim

def resolve_field(field_name: str, claims: list[dict]) -> dict:
    """
    Take all claims for one field from all agents, apply span gate results,
    vote, and produce a single resolved field matching your ExtractedField schema.
    
    Core rule: confidence is decided by CODE (agreement + span score),
    never by model self-assessment.
    """
    # Separate into usable vs discarded
    live_claims = [c for c in claims if not c.get("discarded", False)]
    discarded_claims = [c for c in claims if c.get("discarded", False)]

    # Among live claims, separate votes from abstentions
    # CRITICAL: CANNOT_ASSESS is an abstention, NOT a vote against
    votes = [c for c in live_claims if c.get("status") == "FOUND"]
    absent_votes = [c for c in live_claims if c.get("status") == "ABSENT"]
    abstentions = [c for c in live_claims if c.get("status") == "CANNOT_ASSESS"]

    # No votes at all?
    if not votes and not absent_votes:
        return {
            "field_name": field_name,
            "value": None,
            "value_alt": None,
            "verbatim_quote": None,
            "quote_match_score": 0.0,
            "page": None,
            "bbox": None,
            "confidence": Confidence.UNGROUNDED.value,
            "provenance": Provenance.UNKNOWN.value,
            "extractor_a_raw": _get_raw(claims, "extractor_a"),
            "extractor_b_raw": _get_raw(claims, "extractor_b"),
            "adversary_note": None,
        }

    # All voters said ABSENT?
    if not votes and absent_votes:
        return {
            "field_name": field_name,
            "value": "NOT_FOUND",
            "value_alt": None,
            "verbatim_quote": None,
            "quote_match_score": 0.0,
            "page": None,
            "bbox": None,
            "confidence": Confidence.VERIFIED.value if len(absent_votes) >= 2 else Confidence.INFERRED.value,
            "provenance": Provenance.ABSENT.value,
            "extractor_a_raw": _get_raw(claims, "extractor_a"),
            "extractor_b_raw": _get_raw(claims, "extractor_b"),
            "adversary_note": None,
        }

    # We have positive votes — find agreement
    #
    # THE FIX: group by SEMANTICALLY normalized value, not just
    # whitespace-cleaned text. "90 days", "ninety (90) days", and "3 months"
    # all mean the same thing, but only differed by MORE than whitespace, so
    # they were three separate groups before this — registering as
    # disagreement between agents that actually agreed. normalize_value()
    # converts field-appropriate types (dates, money, durations, party
    # names) to one canonical form first; any field without a specific
    # normalizer falls back to exactly the old whitespace-only behaviour.
    values = [normalize_value(field_name, v.get("value", ""), normalize_whitespace)
              for v in votes if v.get("value")]

    # Group by normalized value
    value_groups = {}
    for v in votes:
        val = normalize_value(field_name, v.get("value", "") or "", normalize_whitespace)
        if val not in value_groups:
            value_groups[val] = []
        value_groups[val].append(v)

    if not value_groups:
        return _ungrounded_field(field_name, claims)

    # Pick the majority value. winner_value/runner_up_value here are the
    # CANONICAL keys used for grouping (e.g. "DAYS:90"), not display text —
    # see best_display_value below for what actually gets shown to the user.
    sorted_groups = sorted(value_groups.items(), key=lambda x: len(x[1]), reverse=True)
    winner_value, winner_claims = sorted_groups[0]
    runner_up_value = sorted_groups[1][0] if len(sorted_groups) > 1 else None

    # Best supporting claim (highest span score)
    best_claim = max(winner_claims, key=lambda c: c.get("span_score", 0))
    best_span_score = best_claim.get("span_score", 0)

    # The value actually shown to the user: the original, human-readable text
    # from the best-scoring claim in the winning group — e.g. "ninety (90)
    # days", not the internal grouping key "DAYS:90". Every claim in
    # winner_claims agreed in substance (that is why they grouped together),
    # so any of their original values is a faithful, readable answer; we
    # just pick the one with the strongest citation.
    display_value = best_claim.get("value", winner_value)
    runner_up_claim = sorted_groups[1][1][0] if len(sorted_groups) > 1 else None
    display_value_alt = runner_up_claim.get("value") if runner_up_claim else None

    # Determine confidence tier — BY CODE, not by model
    agreement_count = len(winner_claims)
    total_voters = len(votes) + len(absent_votes)  # abstentions don't count
    disagreement = len(votes) - agreement_count

    if agreement_count >= 2 and best_span_score >= VERIFIED_THRESHOLD and disagreement == 0:
        confidence = Confidence.VERIFIED
    elif agreement_count >= 1 and best_span_score >= INFERRED_THRESHOLD:
        if disagreement > 0:
            confidence = Confidence.CONTESTED
        else:
            confidence = Confidence.INFERRED
    else:
        confidence = Confidence.UNGROUNDED

    # Determine provenance. Checks the DISPLAY value against the quote, not
    # the canonical key — "DAYS:90" will never literally appear in a
    # document's text, but "ninety (90) days" will.
    if best_span_score >= 90 and _value_in_quote(display_value, best_claim.get("verbatim_quote", "")):
        provenance = Provenance.DIRECT
    elif best_span_score >= INFERRED_THRESHOLD:
        provenance = Provenance.INFERRED
    else:
        provenance = Provenance.UNKNOWN

    return {
        "field_name": field_name,
        "value": display_value,
        "value_alt": display_value_alt,
        "verbatim_quote": best_claim.get("verbatim_quote"),
        "quote_match_score": best_span_score,
        "page": best_claim.get("quote_page"),
        "bbox": best_claim.get("quote_bbox"),
        "confidence": confidence.value,
        "provenance": provenance.value,
        "extractor_a_raw": _get_raw(claims, "extractor_a"),
        "extractor_b_raw": _get_raw(claims, "extractor_b"),
        "adversary_note": _format_discarded(discarded_claims),
    }


def _value_in_quote(value, quote) -> bool:
    """Check if the extracted value actually appears in its own citation."""
    if not value or not quote:
        return False
    # Normalize FIRST (which now also coerces to string), THEN lowercase.
    # The old order called .lower() on the raw value before normalizing —
    # if value was a number, .lower() itself would crash.
    return normalize_whitespace(value).lower() in normalize_whitespace(quote).lower()


def _get_raw(claims: list[dict], agent_id: str) -> str | None:
    """Get raw output from a specific agent for the extractor_a/b_raw fields."""
    for c in claims:
        if c.get("agent_id") == agent_id and c.get("value"):
            return c.get("value")
    return None


def _format_discarded(discarded: list[dict]) -> str | None:
    """Format discarded claims into an adversary note."""
    if not discarded:
        return None
    notes = []
    for d in discarded:
        notes.append(
            f"{d['agent_id']}: quote discarded (span score {d.get('span_score', 0):.0f})"
        )
    return "; ".join(notes)


def _ungrounded_field(field_name: str, claims: list) -> dict:
    return {
        "field_name": field_name,
        "value": None,
        "value_alt": None,
        "verbatim_quote": None,
        "quote_match_score": 0.0,
        "page": None,
        "bbox": None,
        "confidence": Confidence.UNGROUNDED.value,
        "provenance": Provenance.UNKNOWN.value,
        "extractor_a_raw": _get_raw(claims, "extractor_a"),
        "extractor_b_raw": _get_raw(claims, "extractor_b"),
        "adversary_note": None,
    }


def verify_and_resolve(all_claims: list[dict], pages: list[dict]) -> list[dict]:
    """
    Main entry point. Takes raw claims from extract.py, runs span gate
    on each, then resolves into one ExtractedField per field_name.
    """
    # Step 1: Run span gate on every claim
    gated_claims = [span_gate(c, pages) for c in all_claims]

    # Step 2: Group by field_name
    from collections import defaultdict
    by_field = defaultdict(list)
    for c in gated_claims:
        fn = c.get("field_name", "")
        if fn:
            by_field[fn].append(c)

    # Step 3: Resolve each field
    resolved = []
    for field_name, field_claims in by_field.items():
        resolved_field = resolve_field(field_name, field_claims)
        resolved.append(resolved_field)

    logger.info(
        f"Verification complete: {len(resolved)} fields resolved, "
        f"{sum(1 for c in gated_claims if c.get('discarded'))} claims discarded by span gate"
    )

    return resolved