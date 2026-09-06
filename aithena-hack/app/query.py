"""
app/query.py — Portfolio query endpoint.

Takes a natural-language question, gathers extracted contract data from
SQLite, sends it to the LLM, and returns a grounded answer.

The LLM sees ONLY the structured data already in the database (fields,
confidence tiers, contract metadata). It never sees raw contract text.
Every answer inherits the confidence of the underlying verified fields.
"""

import json
import logging
from app.db import get_db
from app.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are AITHENA, an AI contract analysis assistant. You answer questions about a portfolio of contracts based ONLY on the structured data provided below.

RULES:
1. Only answer based on the data provided. If the data does not contain enough information to answer, say exactly: "Sorry, I can't reply to this question."
2. When citing a finding, mention its confidence level (VERIFIED, INFERRED, CONTESTED, or UNGROUNDED).
3. UNGROUNDED fields mean the tool could NOT verify the information — warn the user.
4. CONTESTED fields mean the extractors disagreed — warn the user.
5. Be concise and direct. Use bullet points for lists.
6. If the question is unrelated to contracts or legal analysis, say exactly: "Sorry, I can't reply to this question."
7. Always mention which contract(s) you are referring to by filename.
"""


def _gather_portfolio_data() -> str:
    """Pull all contract + field data from SQLite into a text summary for the LLM."""
    db = get_db()
    contracts = db.execute("SELECT * FROM contracts ORDER BY id").fetchall()

    if not contracts:
        return "NO CONTRACTS UPLOADED. The portfolio is empty."

    lines = []
    for c in contracts:
        cid = c["id"]
        lines.append(f"\n=== CONTRACT: {c['filename']} (ID {cid}) ===")
        lines.append(f"  Parties: {c['parties'] or 'Unknown'}")
        lines.append(f"  Type: {c['contract_type'] or 'Unknown'}")
        lines.append(f"  Start: {c['start_date'] or 'Unknown'}  End: {c['end_date'] or 'Unknown'}")
        lines.append(f"  Renewal: {c['renewal_type'] or 'Unknown'}  Notice period: {c['notice_period_days'] or 'Unknown'} days")
        lines.append(f"  Notice deadline: {c['notice_deadline'] or 'N/A'}")
        lines.append(f"  Governing law: {c['governing_law'] or 'Unknown'}")
        lines.append(f"  Scanned: {bool(c['is_scanned'])}")
        lines.append(f"  Clauses: {c['clauses_covered'] or 0} of {c['clauses_total'] or 0} covered")

        fields = db.execute(
            "SELECT * FROM fields WHERE contract_id=? ORDER BY field_name",
            (cid,)
        ).fetchall()

        if fields:
            lines.append("  EXTRACTED FIELDS:")
            for f in fields:
                val = f["value"] or "Not identified"
                conf = f["confidence"] or "UNGROUNDED"
                quote_snippet = ""
                if f["verbatim_quote"]:
                    q = f["verbatim_quote"][:120]
                    quote_snippet = f'  Quote: "{q}..."' if len(f["verbatim_quote"]) > 120 else f'  Quote: "{q}"'
                lines.append(f"    - {f['field_name']}: {val} [{conf}]{quote_snippet}")
        else:
            lines.append("  NO EXTRACTED FIELDS (extraction may have failed)")

    # Add conflict data
    conflicts = db.execute(
        """SELECT c.*, ca.filename as contract_a_filename, cb.filename as contract_b_filename
           FROM conflicts c
           LEFT JOIN contracts ca ON c.contract_a_id = ca.id
           LEFT JOIN contracts cb ON c.contract_b_id = cb.id"""
    ).fetchall()

    if conflicts:
        lines.append("\n=== DETECTED CONFLICTS ===")
        for cf in conflicts:
            lines.append(f"  - {cf['kind']}: {cf['description']} (severity: {cf['severity']})")
            lines.append(f"    Between: {cf['contract_a_filename']} and {cf['contract_b_filename']}")

    return "\n".join(lines)


async def answer_question(question: str) -> dict:
    """
    Answer a natural-language question about the contract portfolio.

    Returns:
        {"answer": str, "error": bool}
    """
    try:
        portfolio_data = _gather_portfolio_data()

        if "NO CONTRACTS UPLOADED" in portfolio_data:
            return {
                "answer": "No contracts have been uploaded yet. Please upload your contracts from the home page first, then come back to ask questions.",
                "error": False,
            }

        llm = get_llm()
        user_prompt = f"""Here is the current contract portfolio data:

{portfolio_data}

USER QUESTION: {question}

Answer the question based ONLY on the data above. If you cannot answer from this data, respond with exactly: "Sorry, I can't reply to this question."
"""

        result = await llm.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            json_mode=False,
            max_retries=2,
            max_tokens=2048,
            label="query",
        )

        if isinstance(result, str):
            return {"answer": result.strip(), "error": False}
        else:
            return {"answer": "Sorry, I can't reply to this question.", "error": True}

    except Exception as e:
        logger.error(f"Query error: {e}")
        return {"answer": "Sorry, I can't reply to this question.", "error": True}
