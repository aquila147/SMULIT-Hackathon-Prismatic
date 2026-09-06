import logging
from rapidfuzz import fuzz
from app.schemas import Confidence

logger = logging.getLogger(__name__)


def normalize_party(name: str) -> str:
    """Normalize party name for comparison."""
    if not name:
        return ""
    name = name.upper().strip()
    # Strip common suffixes
    for suffix in ["PTE LTD", "PTE. LTD.", "PTY LTD", "LIMITED", "LTD",
                   "INC", "INC.", "LLC", "CORP", "CORPORATION"]:
        name = name.replace(suffix, "").strip()
    # Collapse whitespace
    import re
    name = re.sub(r"\s+", " ", name).strip()
    return name


def detect_duplicate_coverage(contracts: list[dict]) -> list[dict]:
    """
    Detect contracts with the same counterparty, same/similar type, both live.
    This is the easy conflict class — build first.
    """
    conflicts = []

    for i, ca in enumerate(contracts):
        for j, cb in enumerate(contracts):
            if j <= i:
                continue

            # Check if same counterparty (fuzzy match on party names)
            parties_a = ca.get("parties", "")
            parties_b = cb.get("parties", "")
            
            # Simple approach: check if they share a non-SME party
            party_similarity = fuzz.token_set_ratio(
                normalize_party(parties_a),
                normalize_party(parties_b)
            )

            if party_similarity < 70:
                continue

            # Check if same contract type
            type_a = (ca.get("contract_type") or "").lower()
            type_b = (cb.get("contract_type") or "").lower()

            if type_a and type_b and type_a == type_b:
                # Both currently live? (end_date in the future or no end_date)
                # For now, flag all matches — calendar_utils handles date logic

                # Confidence = min of contributing fields
                conf_a = ca.get("field_summary", {}).get("worst", Confidence.UNGROUNDED.value)
                conf_b = cb.get("field_summary", {}).get("worst", Confidence.UNGROUNDED.value)

                conflicts.append({
                    "contract_a_filename": ca.get("filename", ""),
                    "contract_b_filename": cb.get("filename", ""),
                    "kind": "duplicate_coverage",
                    "description": (
                        f"Two active agreements with similar counterparties "
                        f"({parties_a} / {parties_b}) covering {type_a}. "
                        f"You may be paying twice."
                    ),
                    "severity": "medium",
                    "field_a": parties_a,
                    "field_b": parties_b,
                    "confidence": min(conf_a, conf_b) if conf_a and conf_b else Confidence.INFERRED.value,
                    "caveat": (
                        "Potential conflict identified from extracted terms. "
                        "Whether this is a breach is a legal question. "
                        "Both clauses are shown for review."
                    ),
                })

    logger.info(f"Conflict detection: {len(conflicts)} potential duplicate coverage conflicts")
    return conflicts