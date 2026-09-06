"""
Agent 3 — retrieval-based extractor. Different evidence pathway from A and B.

Instead of reading clause-by-clause (Agent A / extractor_a) or the whole
document at once (Agent B / extractor_b), this agent RETRIEVES the passages most
relevant to each field by meaning-ish similarity, then asks the LLM to read only
those passages. Its failure mode — retrieval misses the right passage — is
different from a clause-window miss or a whole-document hallucination, which is
exactly why its agreement carries independent information.

Implemented with pure-stdlib TF-IDF cosine similarity over a query bank. No
numpy, no sentence-transformers, no torch — nothing to install on the demo
machine. If you later add embeddings, swap `_score_passages` for a vector
similarity and keep everything else.

BATCHED: retrieval itself (scoring passages against the query bank) is cheap
local computation and runs per field, unchanged. What changed is that the
LLM is only called ONCE per document, with every field's retrieved excerpts
combined into one labelled prompt — not once per field. This used to be up
to 12 separate network round trips per document; it is now 1.
"""

import re
import math
import logging
from collections import Counter

from app.llm import get_llm
from app.safe_types import coerce_page

logger = logging.getLogger(__name__)

AGENT_ID = "a3_retrieval"

# Multiple paraphrases per field — contracts say the same thing many ways, and a
# single query phrase misses most of them.
QUERY_BANK = {
    "parties": [
        "this agreement is entered into between the parties",
        "by and between the following parties",
    ],
    "contract_type": [
        "this master services agreement distribution agreement lease nda",
        "the title and nature of this agreement",
    ],
    "start_date": [
        "this agreement is effective as of the commencement date",
        "the effective date of this agreement is",
    ],
    "end_date": [
        "this agreement expires on the expiration date",
        "the initial term ends on termination date",
    ],
    "renewal_type": [
        "this agreement automatically renews for successive periods",
        "the agreement shall be extended or renewed unless notice",
    ],
    "notice_period_days": [
        "written notice must be given days prior to non-renewal",
        "either party may give prior written notice of termination days",
    ],
    "termination_rights": [
        "either party may terminate this agreement for convenience or cause",
        "termination rights and conditions",
    ],
    "payment_obligations": [
        "the customer shall pay fees in the amount of",
        "payment terms invoice fees consideration due",
    ],
    "liability_cap": [
        "the aggregate liability shall not exceed the cap",
        "limitation of liability maximum amount capped at",
    ],
    "exclusivity": [
        "grants an exclusive right to distribute in the territory",
        "sole and exclusive supplier appointment",
    ],
    "restrictive_covenants": [
        "shall not compete non-solicitation restrictive covenant",
        "non-compete obligations during and after the term",
    ],
    "governing_law": [
        "this agreement is governed by the laws of",
        "governing law jurisdiction and venue for disputes",
    ],
}

TOP_K = 3
# Deliberately low. TF-IDF against short contract passages almost always finds
# some lexical overlap, so this gate only rejects the truly irrelevant. The real
# protection against a bad retrieval is twofold and downstream: (1) the LLM is
# instructed to return CANNOT_ASSESS when the passages don't settle the field,
# and (2) the span gate in verify.py discards any fabricated quote outright. A
# permissive gate here is safe because nothing unverified reaches the vote.
MIN_SCORE = 0.02

RETRIEVAL_SYSTEM_BATCHED = """You are a contract field extractor (Agent C, retrieval-based).
You are shown several SEPARATE excerpt sets, each labelled with the field it
is meant to answer. Each excerpt set was retrieved independently for that one
field — passages under one field's label may not be relevant to any other
field, so answer each field ONLY from its own labelled excerpts.

Return JSON: {"fields": [
  {"field_name": "...", "value": "...", "verbatim_quote": "...",
   "page": 0, "status": "FOUND"|"ABSENT"|"CANNOT_ASSESS"},
  ...
]}
Return exactly one object per field you were given, using the same
field_name labels you were shown.

Rules:
- verbatim_quote MUST be copied EXACTLY from that field's own excerpts. Do
  not paraphrase, and do not borrow a quote from a different field's excerpts.
- If a field's excerpts do not settle the question, status = "CANNOT_ASSESS".
- Only use "ABSENT" if that field's excerpts clearly show the term is absent.
- No quote = CANNOT_ASSESS, never FOUND.
"""

_WORD = re.compile(r"[a-z0-9$]+")


def _tokenize(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _passages(doc_data: dict) -> list[dict]:
    """Use the chunks the ingester already produced; fall back to pages."""
    chunks = doc_data.get("chunks") or []
    if chunks:
        return [{"text": c["text"], "page": (c.get("pages") or [0])[0]} for c in chunks]
    return [{"text": p.get("text", ""), "page": p.get("page_number", 0)}
            for p in doc_data.get("pages", [])]


def _score_passages(query_tokens: list[str], passages: list[dict], idf: dict) -> list[tuple]:
    """TF-IDF cosine similarity, pure stdlib. Returns (score, passage) sorted."""
    q_counts = Counter(query_tokens)
    q_vec = {t: (q_counts[t] / len(query_tokens)) * idf.get(t, 0.0) for t in q_counts}
    q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

    scored = []
    for p in passages:
        toks = _tokenize(p["text"])
        if not toks:
            scored.append((0.0, p))
            continue
        counts = Counter(toks)
        vec = {t: (counts[t] / len(toks)) * idf.get(t, 0.0) for t in counts}
        dot = sum(q_vec.get(t, 0.0) * vec.get(t, 0.0) for t in q_vec)
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        scored.append((dot / (q_norm * norm), p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def _build_idf(passages: list[dict]) -> dict:
    n = len(passages) or 1
    df = Counter()
    for p in passages:
        for t in set(_tokenize(p["text"])):
            df[t] += 1
    return {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}


async def run_retrieval_agent(doc_data: dict) -> list[dict]:
    """
    Retrieve per field (cheap, local, unchanged), then ask about ALL fields
    in ONE combined LLM call instead of one call per field.

    This used to fire up to 12 separate network round trips per document —
    the single biggest contributor to total pipeline time, and to the
    finish_reason="error" failures under concurrent load, since more calls
    means more chances to collide with whatever rate limit the backend
    enforces. Batching keeps the retrieval step (which is genuinely per-field
    and cheap, since it's pure local math) exactly as it was, and only
    changes how the RESULTS are asked about: together, in one request, instead
    of one request each.
    """
    passages = _passages(doc_data)
    claims = []

    if not passages:
        return claims

    idf = _build_idf(passages)
    llm = get_llm()

    # Step 1 — score locally per field, decide who gets asked. Unchanged:
    # this is pure computation, no network calls, and is not the bottleneck.
    to_ask = {}
    for field_name, queries in QUERY_BANK.items():
        best = {}
        best_score = 0.0
        for q in queries:
            for score, p in _score_passages(_tokenize(q), passages, idf):
                key = id(p)
                if key not in best or score > best[key][0]:
                    best[key] = (score, p)
                best_score = max(best_score, score)

        if best_score < MIN_SCORE:
            claims.append(_abstain(field_name, "retrieval score too low"))
            continue

        to_ask[field_name] = sorted(best.values(), key=lambda x: x[0], reverse=True)[:TOP_K]

    if not to_ask:
        return claims

    # Step 2 — ONE combined call for every field that passed the local gate,
    # each field's excerpts clearly labelled so the model doesn't cross-wire
    # an answer from one field's passages into another's.
    sections = []
    for field_name, top in to_ask.items():
        excerpt = "\n\n---\n\n".join(f"[page {p['page']}] {p['text'][:1200]}" for _, p in top)
        sections.append(f"### FIELD: {field_name}\n{excerpt}")
    combined_prompt = "\n\n====\n\n".join(sections)

    try:
        result = await llm.complete(
            system_prompt=RETRIEVAL_SYSTEM_BATCHED,
            user_prompt=combined_prompt,
            # Multiple fields' worth of quotes in one response — same
            # reasoning as Agent 2/4's bumped budget.
            # Can now return up to 12 fields with quotes in ONE response,
            # since batching combined every field's excerpts into one call.
            # Same shape of problem as Agent 4 (also asks for up to 12 fields
            # at once), so matching its budget rather than the smaller one
            # this had before batching.
            max_tokens=12000,
            label=f"a3_retrieval:batched({len(to_ask)} fields)",
        )
    except Exception as e:
        logger.warning(f"{AGENT_ID} batched call failed: {e}")
        # Fail soft: every field we HAD passages for but never got an answer
        # for becomes CANNOT_ASSESS, not silently missing.
        for field_name in to_ask:
            claims.append(_abstain(field_name, f"batched call error: {e}"))
        return claims

    returned = result.get("fields", []) if isinstance(result, dict) else []
    by_name = {f.get("field_name"): f for f in returned if isinstance(f, dict)}

    for field_name, top in to_ask.items():
        field = by_name.get(field_name)
        if not field:
            claims.append(_abstain(field_name, "model did not return this field"))
            continue
        claims.append({
            "agent_id": AGENT_ID,
            "field_name": field_name,
            "status": field.get("status", "CANNOT_ASSESS"),
            "value": field.get("value"),
            "verbatim_quote": field.get("verbatim_quote"),
            "quote_page": coerce_page(field.get("page")) or top[0][1]["page"],
            "quote_bbox": None,
        })

    return claims


def _abstain(field_name: str, reason: str) -> dict:
    return {
        "agent_id": AGENT_ID,
        "field_name": field_name,
        "status": "CANNOT_ASSESS",
        "value": None,
        "verbatim_quote": None,
        "quote_page": None,
        "quote_bbox": None,
    }
