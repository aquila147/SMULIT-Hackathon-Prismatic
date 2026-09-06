"""
Shared schemas — agreed in hour 0, never changed without all three people present.
Every extracted field carries its own evidence chain.
"""
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class Confidence(str, Enum):
    VERIFIED = "VERIFIED"
    INFERRED = "INFERRED"
    CONTESTED = "CONTESTED"
    UNGROUNDED = "UNGROUNDED"


class ExtractedField(BaseModel):
    field_name: str
    value: Optional[str] = None
    value_alt: Optional[str] = None
    verbatim_quote: Optional[str] = None
    quote_match_score: Optional[float] = None
    page: Optional[int] = None
    bbox: Optional[str] = None
    confidence: Confidence = Confidence.UNGROUNDED
    extractor_a_raw: Optional[str] = None
    extractor_b_raw: Optional[str] = None
    adversary_note: Optional[str] = None


class ContractSummary(BaseModel):
    filename: str
    parties: Optional[str] = None
    contract_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    renewal_type: Optional[str] = None
    notice_period_days: Optional[int] = None
    notice_deadline: Optional[str] = None
    governing_law: Optional[str] = None
    is_scanned: bool = False
    clauses_total: Optional[int] = None
    clauses_covered: Optional[int] = None
    fields: list[ExtractedField] = []


class Conflict(BaseModel):
    contract_a_filename: str
    contract_b_filename: str
    kind: str
    description: str
    severity: str
    field_a: Optional[ExtractedField] = None
    field_b: Optional[ExtractedField] = None


class HandoffBrief(BaseModel):
    title: str
    issue_summary: str
    relevant_documents: list[str]
    relevant_clauses: list[dict]
    what_the_tool_established: str
    specific_question_for_lawyer: str
    contested_or_ungrounded_fields: list[ExtractedField] = []

# NEW — Provenance (how we know, separate from confidence)
class Provenance(str, Enum):
    DIRECT = "DIRECT"        # quoted verbatim, value in quote, span-verified
    DERIVED = "DERIVED"      # computed in Python (all calendar dates)
    INFERRED = "INFERRED"    # model concluded without verbatim value
    ABSENT = "ABSENT"        # methods concluded term is not in contract
    UNKNOWN = "UNKNOWN"      # no method could assess

# NEW — Three-state status for each agent's output
class FieldStatus(str, Enum):
    FOUND = "FOUND"
    ABSENT = "ABSENT"              # "I looked, it's not there" — this IS a vote
    CANNOT_ASSESS = "CANNOT_ASSESS" # "this method can't answer" — this is NOT a vote

# NEW — Individual agent claim (append-only, never overwritten)
class AgentClaim(BaseModel):
    agent_id: str              # "a1_rules", "a2_clause", etc.
    field_name: str
    status: FieldStatus
    value: str | None = None
    verbatim_quote: str | None = None
    quote_page: int | None = None
    quote_bbox: str | None = None  # "x0,y0,x1,y1"
    span_score: float | None = None  # rapidfuzz score against page text
    discarded: bool = False    # True if span gate killed this claim
    discard_reason: str | None = None

# NEW — Escalation trigger types
class EscalationTrigger(str, Enum):
    REFUTATION_QUOTED = "refutation_quoted"
    CONSTRAINT_VIOLATION = "constraint_violation"
    CROSS_CONTRACT_CONFLICT = "cross_contract_conflict"
    URGENT_UNVERIFIED_DEADLINE = "urgent_unverified_deadline"
    UNRESOLVED_REFERENCE = "unresolved_reference"
    INGESTION_FAILURE = "ingestion_failure"
    SUBSTANTIAL_DISSENT = "substantial_dissent"
    NORM_REQUIRES_LAWYER = "norm_requires_lawyer"

# NEW — Gap types
class Gap(BaseModel):
    kind: str                  # "unresolved_parent", "missing_schedule", "ingestion_failed"
    source_contract: str
    reference_text: str | None = None
    page: int | None = None
    resolution: str            # "resolved", "ambiguous", "unresolved"
    candidates: list = []
    language_note: str = "We found a reference we could not resolve. This does not prove the document is missing."