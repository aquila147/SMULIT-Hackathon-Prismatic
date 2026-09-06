# app/adversary.py — only build if ahead of schedule
async def adversarial_check(field: dict, full_text: str) -> dict | None:
    """
    Hunt for contradicting clauses. Only fires on non-VERIFIED fields.
    Sees the document and the claim. NEVER sees any agent's reasoning.
    Returns an adversary_note if a contradiction is found.
    """
    if field.get("confidence") == "VERIFIED":
        return None  # Don't waste tokens on verified fields

    llm = get_llm()
    result = await llm.complete(
        system_prompt=(
            "You are a contract adversarial verifier. You are given a claimed "
            "value from a contract and the full contract text. Your job is to "
            "find CONTRADICTING evidence — a clause that says something different.\n\n"
            "Return JSON: {\"contradiction_found\": true/false, "
            "\"contradicting_quote\": \"...\", \"page\": N, \"explanation\": \"...\"}\n\n"
            "Only report genuine contradictions, not restatements."
        ),
        user_prompt=(
            f"Claimed field: {field['field_name']}\n"
            f"Claimed value: {field.get('value', 'unknown')}\n\n"
            f"Contract text:\n{full_text[:20000]}"
        ),
    )
    if result.get("contradiction_found"):
        return result
    return None