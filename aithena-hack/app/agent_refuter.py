"""
Agent 5 — adversarial refuter. Attacks resolved values; never sees agent reasoning.

Its output is ASYMMETRIC and must be treated that way:
  - "I found a contradicting/superseding clause" -> strong evidence, downgrade
  - "I found nothing" -> weak; this is the default output and must NEVER be
    counted as corroboration.

It runs AFTER verify_and_resolve, on the resolved fields, seeing only the bare
claimed values plus the document text — never any extractor's reasoning, never
the vote counts. An agent asked to break a claim behaves differently from one
asked to grade an argument, and it cannot be persuaded by prose it never reads.

When it quotes a genuine contradiction, the field's confidence is capped: a
refuted field cannot remain VERIFIED no matter how many agents agreed.
Unanimity about the wrong clause is still wrong.

BATCHED, not one call per field: this used to fire one LLM call per
attackable field (often 6-10 per document). All attackable fields are
independent questions asked of the SAME document text, so they are now asked
in a single combined call — fewer total requests, faster, and less likely to
collide with a backend rate/concurrency limit.
"""

import logging
from app.llm import get_llm
from app.schemas import Confidence

logger = logging.getLogger(__name__)

AGENT_ID = "a5_refuter"

REFUTER_SYSTEM = (
    "You are a contract adversarial verifier. You are given SEVERAL claimed "
    "values from a contract, each labelled with its field name, and the "
    "contract text. For EACH claimed value independently, look for evidence "
    "that specific claim is WRONG:\n"
    "  - a later clause, schedule or amendment that supersedes it\n"
    "  - another clause stating a different value for the same thing\n"
    "  - a defined term that changes what it means\n"
    "  - a carve-out or exception that limits when it applies\n\n"
    'Return JSON: {"results": [\n'
    '  {"field_name": "...", "contradiction_found": true|false, '
    '"contradicting_quote": "<exact text copied from the contract, or empty>", '
    '"page": <int or null>, "explanation": "<one sentence, or empty>"},\n'
    "  ...\n"
    "]}\n"
    "Return exactly one result per claimed field you were given, using the "
    "same field_name labels you were shown.\n\n"
    "Only report a contradiction if you can copy the exact text that does the "
    "overriding. A restatement is not a contradiction. Speculation is not a "
    "contradiction. If you find nothing solid for a field, return "
    "contradiction_found=false for that field — do not force a result."
)

# Confidence tiers Agent 5 is allowed to touch. It never fires on already-weak
# fields (no point) — only on things the ensemble thought were solid.
_ATTACKABLE = {Confidence.VERIFIED.value, Confidence.INFERRED.value}


async def run_refuter(resolved_fields: list[dict], full_text: str) -> list[dict]:
    """
    Attack every sufficiently-confident resolved field in ONE combined call.
    Mutates fields in place: on a genuine refutation, caps confidence and
    appends to adversary_note. Returns the same list.
    """
    if not full_text:
        return resolved_fields

    attackable = [
        f for f in resolved_fields
        if f.get("confidence") in _ATTACKABLE
        and f.get("value") not in (None, "NOT_FOUND")
    ]
    if not attackable:
        return resolved_fields

    by_name = {f.get("field_name"): f for f in attackable}
    claims_block = "\n".join(
        f"- field_name: {f.get('field_name')} | claimed value: {f.get('value')}"
        for f in attackable
    )

    llm = get_llm()
    try:
        result = await llm.complete(
            system_prompt=REFUTER_SYSTEM,
            user_prompt=(
                f"Claimed values to check:\n{claims_block}\n\n"
                f"Contract text:\n{full_text[:20000]}"
            ),
            # Several fields' worth of possible contradiction text in one
            # response — same reasoning as the other multi-field agents.
            max_tokens=8192,
            label=f"a5_refuter:batched({len(attackable)} fields)",
        )
    except Exception as e:
        logger.warning(f"{AGENT_ID} batched call failed: {e}")
        return resolved_fields  # fail soft — no refutations applied, not a crash

    results = result.get("results", []) if isinstance(result, dict) else []

    for item in results:
        if not isinstance(item, dict) or not item.get("contradiction_found"):
            continue

        field = by_name.get(item.get("field_name"))
        if field is None:
            continue  # model referenced a field we didn't ask about — ignore

        quote = (item.get("contradicting_quote") or "").strip()
        if not quote:
            continue  # no quote = not a real refutation

        # Cap confidence. A refuted field cannot stay VERIFIED.
        field["confidence"] = Confidence.CONTESTED.value
        note = (
            f"REFUTED by {AGENT_ID}: {item.get('explanation', 'contradicting clause found')} "
            f"(p.{item.get('page', '?')}: \"{quote[:140]}\")"
        )
        existing = field.get("adversary_note")
        field["adversary_note"] = f"{existing}; {note}" if existing else note
        logger.info(f"{AGENT_ID}: refuted {field.get('field_name')} — {item.get('explanation','')}")

    return resolved_fields
