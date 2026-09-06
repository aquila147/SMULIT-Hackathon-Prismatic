
from datetime import datetime


def generate_handoff_brief(
    title: str,
    trigger: str,
    issue_summary: str,
    contracts: list[dict],
    resolved_fields: list[dict],
    negative_findings: list[str] | None = None,
) -> dict:
    """
    Generate a structured handoff brief that a lawyer can act on in < 1 minute.
    This is AITHENA's monetisation step — self-serve to lawyer conversion.
    """
    # Collect relevant clauses with citations
    relevant_clauses = []
    contested_or_ungrounded = []

    for f in resolved_fields:
        if f.get("verbatim_quote"):
            relevant_clauses.append({
                "filename": contracts[0].get("filename", "") if contracts else "",
                "field_name": f["field_name"],
                "quote": f["verbatim_quote"],
                "page": f.get("page"),
            })
        if f.get("confidence") in ("CONTESTED", "UNGROUNDED"):
            contested_or_ungrounded.append({
                "field_name": f["field_name"],
                "value": f.get("value"),
                "confidence": f.get("confidence"),
                "extractor_a_raw": f.get("extractor_a_raw"),
                "extractor_b_raw": f.get("extractor_b_raw"),
            })

    brief = {
        "title": title,
        "trigger": trigger,
        "issue_summary": issue_summary,
        "generated_at": datetime.now().isoformat(),
        "relevant_documents": [c.get("filename", "") for c in contracts],
        "relevant_clauses": relevant_clauses,
        "what_the_tool_established": _summarize_established(resolved_fields),
        "negative_findings": negative_findings or [
            "No superseding amendment was found in the document corpus."
        ],
        "specific_question_for_lawyer": _generate_question(trigger, issue_summary),
        "contested_or_ungrounded_fields": contested_or_ungrounded,
    }

    return brief


def brief_to_markdown(brief: dict) -> str:
    """Export as one-page Markdown for printing."""
    lines = [
        f"# Escalation Brief: {brief['title']}",
        f"*Generated: {brief['generated_at']}*",
        f"*Trigger: {brief['trigger']}*",
        "",
        "## Issue",
        brief["issue_summary"],
        "",
        "## Documents involved",
    ]
    for doc in brief["relevant_documents"]:
        lines.append(f"- {doc}")

    lines.extend(["", "## What we established"])
    lines.append(brief["what_the_tool_established"])

    if brief.get("relevant_clauses"):
        lines.extend(["", "## Supporting clauses"])
        for clause in brief["relevant_clauses"]:
            lines.append(
                f"- **{clause['field_name']}** (p.{clause.get('page', '?')}): "
                f'"{clause["quote"]}"'
            )

    if brief.get("negative_findings"):
        lines.extend(["", "## What we checked and ruled out"])
        for nf in brief["negative_findings"]:
            lines.append(f"- {nf}")

    if brief.get("contested_or_ungrounded_fields"):
        lines.extend(["", "## Fields requiring human review"])
        for f in brief["contested_or_ungrounded_fields"]:
            lines.append(
                f"- **{f['field_name']}**: value={f.get('value', 'unknown')}, "
                f"confidence={f.get('confidence')}"
            )
            if f.get("extractor_a_raw") and f.get("extractor_b_raw"):
                lines.append(
                    f"  - Extractor A said: {f['extractor_a_raw']}"
                )
                lines.append(
                    f"  - Extractor B said: {f['extractor_b_raw']}"
                )

    lines.extend([
        "",
        "## Question for counsel",
        brief["specific_question_for_lawyer"],
    ])

    return "\n".join(lines)


def _summarize_established(fields: list[dict]) -> str:
    """
    A readable paragraph (or two) a lawyer can skim in seconds — not a
    semicolon-joined field dump. Describes what the tool is confident about,
    what it couldn't confirm, and how it reached those conclusions, in prose.
    """
    verified = [f for f in fields if f.get("confidence") == "VERIFIED"]
    inferred = [f for f in fields if f.get("confidence") == "INFERRED"]
    contested = [f for f in fields if f.get("confidence") == "CONTESTED"]
    ungrounded = [f for f in fields if f.get("confidence") == "UNGROUNDED"]

    def _readable(name: str) -> str:
        return name.replace("_", " ")

    def _list(fs: list[dict]) -> str:
        parts = []
        for f in fs[:8]:
            val = f.get("value")
            if val and str(val).upper() != "NOT_FOUND":
                parts.append(f"{_readable(f['field_name'])} ({val})")
            else:
                parts.append(_readable(f["field_name"]))
        return ", ".join(parts)

    sentences = []

    # Opening: method + what's solid.
    if verified:
        sentences.append(
            f"This analysis was produced by a multi-agent extraction pipeline in "
            f"which several independent methods read the contract and their "
            f"agreement was checked against the source text (a citation must "
            f"match the document verbatim to count). "
            f"{len(verified)} field(s) reached the highest confidence tier, with "
            f"multiple methods agreeing and citations verified against the "
            f"contract: {_list(verified)}."
        )
    else:
        sentences.append(
            "This analysis was produced by a multi-agent extraction pipeline, "
            "but no field reached the highest confidence tier for this document "
            "— every extracted value below should be independently confirmed "
            "against the source."
        )

    # Middle: the softer findings.
    if inferred:
        sentences.append(
            f"A further {len(inferred)} field(s) were found by a single method "
            f"or with a partial citation match and should be treated as "
            f"probable but unconfirmed: {_list(inferred)}."
        )

    # The part the lawyer is actually being paid for.
    problem_bits = []
    if contested:
        problem_bits.append(
            f"{len(contested)} field(s) where the methods disagreed on the value "
            f"({_list(contested)})"
        )
    if ungrounded:
        problem_bits.append(
            f"{len(ungrounded)} field(s) that could not be grounded to any "
            f"verifiable clause ({_list(ungrounded)})"
        )
    if problem_bits:
        sentences.append(
            "The following require human judgement: " + "; and ".join(problem_bits) +
            ". These are where a lawyer's review adds the most value."
        )

    return " ".join(sentences)


def _generate_question(trigger: str, summary: str) -> str:
    templates = {
        "urgent_unverified_deadline": (
            "An action deadline falls within 30 days but the underlying fields "
            "could not be fully verified. Please confirm the dates and advise on "
            "whether action is required."
        ),
        "cross_contract_conflict": (
            "A potential conflict has been identified between two agreements. "
            "Please review both clauses and advise whether there is an actual breach."
        ),
        "refutation_quoted": (
            "A contradicting clause was found for an extracted value. "
            "Please determine which clause is operative."
        ),
    }
    return templates.get(trigger, f"Please review the following issue: {summary}")