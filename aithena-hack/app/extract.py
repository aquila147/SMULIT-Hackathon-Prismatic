import asyncio
import logging
from app.llm import get_llm
from app.schemas import FieldStatus
from app.safe_types import coerce_page

logger = logging.getLogger(__name__)

# No local concurrency cap here anymore. Every call to llm.complete() now
# queues against ONE global semaphore inside app/llm.py, shared across every
# agent and every document. Firing all of a document's chunks at once with
# asyncio.gather is safe regardless of how many there are — the global gate
# is what decides how many are ever actually in flight, not this file.

# The 12+ field types to extract
FIELD_NAMES = [
    "parties", "contract_type", "start_date", "end_date",
    "renewal_type", "notice_period_days", "termination_rights",
    "payment_obligations", "liability_cap", "exclusivity",
    "restrictive_covenants", "governing_law",
]

EXTRACTOR_A_SYSTEM = """You are a contract clause extractor (Agent A).
You read one section of a contract at a time and extract specific fields.

For EACH field you find, you MUST return:
- field_name: one of the standard field names
- value: the extracted value
- verbatim_quote: the EXACT text from the contract that supports this value
  (copy-paste, do not paraphrase)
- page: which page (0-indexed) the quote appears on (if known)
- status: "FOUND" if you found it, "ABSENT" if you looked and it's definitely
  not in this section, "CANNOT_ASSESS" if this section doesn't contain relevant info

Return JSON: {"fields": [{"field_name": "...", "value": "...",
"verbatim_quote": "...", "page": 0, "status": "FOUND"}, ...]}

CRITICAL RULES:
- The verbatim_quote must be EXACTLY copied from the text. Do not rephrase.
- If you cannot find a verbatim quote, set status to "CANNOT_ASSESS", not "FOUND".
- "ninety (90) days" and "90 days" are both fine — quote what the text says.
- Do NOT make up quotes. If the text doesn't say it, don't claim it does.
"""

EXTRACTOR_B_SYSTEM = """You are a contract field extractor (Agent B).
You read the FULL contract text and extract all key commercial fields.

For EACH field, return:
- field_name: one of the standard field names
- value: the extracted value (normalize dates to YYYY-MM-DD where possible)
- verbatim_quote: the EXACT text from the contract supporting this
- page: page number (0-indexed) where the quote appears
- status: "FOUND", "ABSENT" (definitely not in the contract), or
  "CANNOT_ASSESS" (cannot determine from the text)

Return JSON: {"fields": [...]}

You see the whole document, so look for:
- Definitions that are referenced in clauses elsewhere
- Schedules or annexes that override main body clauses
- Amendment language that changes earlier terms
- Cross-references between clauses

CRITICAL: Every "FOUND" field MUST have a verbatim_quote copied exactly
from the contract text. No quote = CANNOT_ASSESS, not FOUND.
"""


async def run_extractor_a(chunks: list[dict], pages: list[dict]) -> list[dict]:
    """
    Agent 2 (a2_clause / agent_id="extractor_a"). Clause-focused extractor:
    reads one chunk at a time. Runs on each chunk independently.
    Returns a list of AgentClaim-shaped dicts.

    Chunks are read concurrently — reading chunk 2 does not need to wait for
    chunk 1's reply, since each chunk is asked about in isolation anyway. How
    many are ever ACTUALLY in flight at once is decided by the global
    semaphore in app/llm.py, not here.
    """
    llm = get_llm()

    async def _read_chunk(chunk: dict) -> list[dict]:
        try:
            result = await llm.complete(
                system_prompt=EXTRACTOR_A_SYSTEM,
                user_prompt=(
                    f"Contract section (pages {chunk.get('pages', '?')}):\n\n"
                    f"{chunk['text']}\n\n"
                    f"Extract these fields if present: {', '.join(FIELD_NAMES)}"
                ),
                # Can return up to 12 fields with full quotes in one
                # response — 4096 (the old default) was cutting this off
                # mid-answer (finish_reason=length).
                max_tokens=8192,
                label=f"a2_clause p.{chunk.get('pages', '?')}",
            )
        except Exception as e:
            logger.warning(f"Extractor A (a2_clause) failed on a chunk: {e}")
            # Fail soft — this chunk contributes nothing, the rest of the
            # document is unaffected. (Was `break`, which abandoned the
            # whole document after one bad chunk.)
            return []

        return [
            {
                "agent_id": "extractor_a",
                "field_name": field.get("field_name", ""),
                "status": field.get("status", "CANNOT_ASSESS"),
                "value": field.get("value"),
                "verbatim_quote": field.get("verbatim_quote"),
                # coerce_page: the LLM sometimes returns "3" instead of 3.
                # Fix at the source, not just where it's later compared —
                # span_gate() also coerces defensively, but a claim should
                # never carry a bad type in the first place.
                "quote_page": coerce_page(field.get("page")),
            }
            for field in result.get("fields", [])
        ]

    results = await asyncio.gather(*[_read_chunk(c) for c in chunks])
    return [claim for chunk_claims in results for claim in chunk_claims]


async def run_extractor_b(full_text: str, pages: list[dict]) -> list[dict]:
    """
    Agent 4 (a4_holistic / agent_id="extractor_b"). Holistic extractor:
    sees the full document in one pass. Best at cross-references and schedules.
    Returns a list of AgentClaim-shaped dicts.
    """
    llm = get_llm()

    # Truncate if too long for context window
    max_chars = 30_000
    text_input = full_text[:max_chars]
    if len(full_text) > max_chars:
        text_input += f"\n\n[...truncated, {len(full_text) - max_chars} chars omitted...]"

    try:
        result = await llm.complete(
            system_prompt=EXTRACTOR_B_SYSTEM,
            user_prompt=(
                f"Full contract text:\n\n{text_input}\n\n"
                f"Extract ALL of these fields: {', '.join(FIELD_NAMES)}\n"
                f"For every field, report FOUND, ABSENT, or CANNOT_ASSESS."
            ),
            # This is the heaviest single call in the whole pipeline: ALL 12
            # fields, each with a quote, from up to 30k chars of context, in
            # one response. Give it the most room of any agent.
            max_tokens=12000,
            label="a4_holistic",
        )
        claims = []
        for field in result.get("fields", []):
            claims.append({
                "agent_id": "extractor_b",
                "field_name": field.get("field_name", ""),
                "status": field.get("status", "CANNOT_ASSESS"),
                "value": field.get("value"),
                "verbatim_quote": field.get("verbatim_quote"),
                "quote_page": coerce_page(field.get("page")),
            })
        return claims

    except Exception as e:
        logger.warning(f"Extractor B failed: {e}")
        return [
            {
                "agent_id": "extractor_b",
                "field_name": fn,
                "status": "CANNOT_ASSESS",
                "value": None,
                "verbatim_quote": None,
                "quote_page": None,
            }
            for fn in FIELD_NAMES
        ]


async def extract_fields(doc_data: dict) -> list[dict]:
    """
    Run the full five-agent ensemble and return all claims (unverified).
    doc_data comes from ingest.py — has 'full_text', 'pages', 'chunks'.

    The five agents by evidence pathway:
      a1_rules      — deterministic regex, NO LLM, cannot hallucinate
      a2_clause     — LLM reading one clause chunk at a time  (extractor_a)
      a3_retrieval  — LLM reading only retrieved passages
      a4_holistic   — LLM reading the whole document          (extractor_b)
      a5_refuter    — runs later in the pipeline, in verify/adversary step

    Diversity is the whole point: these fail differently, so agreement between
    them carries real information. Two LLMs reading text (a2 + a4) agreeing is
    weak; a1_rules agreeing with any LLM agent is strong.
    """
    chunks = doc_data.get("chunks", [])
    pages = doc_data.get("pages", [])
    full_text = doc_data.get("full_text", "")

    all_claims = []

    # Agent 1 (rules) is synchronous and cannot fail on the network — run it
    # first and unconditionally. It is the independent anchor.
    try:
        from app.agent_rules import run_rules_agent
        rules_claims = run_rules_agent(doc_data)
        all_claims.extend(rules_claims)
        logger.info(f"a1_rules: {sum(1 for c in rules_claims if c['status']=='FOUND')} fields found")
    except Exception as e:
        logger.error(f"a1_rules failed: {e}")

    # Agents 2, 3, 4 all call the LLM — run them concurrently.
    async def _safe(coro, label):
        try:
            return await coro
        except Exception as e:
            logger.error(f"{label} failed: {e}")
            return []

    try:
        from app.agent_retrieval import run_retrieval_agent
        retrieval_coro = _safe(run_retrieval_agent(doc_data), "a3_retrieval")
    except Exception as e:
        logger.error(f"a3_retrieval import failed: {e}")
        async def _empty():
            return []
        retrieval_coro = _empty()

    results = await asyncio.gather(
        _safe(run_extractor_a(chunks, pages), "a2_clause"),
        retrieval_coro,
        _safe(run_extractor_b(full_text, pages), "a4_holistic"),
    )
    for r in results:
        all_claims.extend(r)

    n_agents = len({c["agent_id"] for c in all_claims})
    logger.info(f"Extraction complete: {len(all_claims)} raw claims from {n_agents} agents")
    return all_claims