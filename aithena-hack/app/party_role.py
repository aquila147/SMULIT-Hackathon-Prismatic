"""
Party-role detection.

Two jobs:
  1. Identify which party IS the SME (the client using this tool), across the
     whole corpus — it's the name that appears in nearly every contract, while
     counterparties appear once or twice.
  2. For each contract, decide whether the SME is the supplier, the customer,
     both (middleman), or a symmetric counterparty (NDAs).

Why this matters: risk direction inverts entirely depending on role. An
uncapped liability cap is catastrophic if the SME is the supplier (they bear
unlimited exposure) and near-irrelevant if they're the customer. So risk
scoring (see risk.py) cannot fire directional findings without knowing which
side the SME is on.

Critical honesty rule: when role confidence is low, we return UNKNOWN rather
than guessing. Downstream, an UNKNOWN role means only direction-neutral risk
findings fire — never a directional one that could be backwards.
"""

import re
from collections import Counter

# Role labels contracts commonly attach to a party, and which role each implies
# for the party that carries it.
_ROLE_LABELS = {
    "supplier": "supplier", "vendor": "supplier", "seller": "supplier",
    "provider": "supplier", "licensor": "supplier", "contractor": "supplier",
    "consultant": "supplier", "distributor": "supplier", "landlord": "supplier",
    "lessor": "supplier",
    "customer": "customer", "client": "customer", "buyer": "customer",
    "purchaser": "customer", "licensee": "customer", "tenant": "customer",
    "lessee": "customer", "recipient": "customer",
}

_LEGAL_SUFFIX = re.compile(
    r"\b(pte\.?\s*ltd\.?|ltd\.?|limited|llc|inc\.?|incorporated|corp\.?|"
    r"corporation|plc|gmbh|sdn\.?\s*bhd\.?|llp|lp)\b",
    re.IGNORECASE,
)


def _norm_party(name: str) -> str:
    """Normalize a party name for cross-contract counting/matching."""
    if not name:
        return ""
    n = _LEGAL_SUFFIX.sub("", name.lower())
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _split_parties(parties_value: str) -> list[str]:
    """A contract's `parties` field is often 'A and B' or 'A; B' — split it."""
    if not parties_value:
        return []
    parts = re.split(r"\s+and\s+|\s*;\s*|\s*&\s*|\s*/\s*|\s+vs\.?\s+", parties_value, flags=re.I)
    return [p.strip() for p in parts if p.strip()]


def identify_sme(all_contracts: list[dict]) -> tuple[str | None, float]:
    """
    The SME is the party appearing across the most contracts. Returns
    (normalized_sme_name, confidence 0-1). Confidence reflects how dominant
    that party is over the runner-up — a clear repeat party is high
    confidence; a near-tie is not.
    """
    counter = Counter()
    display = {}  # normalized -> a readable original form
    for c in all_contracts:
        seen = set()
        for raw in _split_parties(c.get("parties") or ""):
            norm = _norm_party(raw)
            if norm and norm not in seen:
                counter[norm] += 1
                seen.add(norm)
                display.setdefault(norm, raw.strip())

    if not counter:
        return None, 0.0

    ranked = counter.most_common()
    top_norm, top_count = ranked[0]
    runner_count = ranked[1][1] if len(ranked) > 1 else 0

    # Confidence: how much more often the top party appears than the next.
    # Appears in most contracts and clearly ahead of #2 -> high.
    total = len(all_contracts)
    dominance = top_count / total if total else 0
    margin = (top_count - runner_count) / top_count if top_count else 0
    confidence = round(min(1.0, 0.5 * dominance + 0.5 * margin + (0.2 if top_count >= 3 else 0)), 2)

    return display.get(top_norm, top_norm), confidence


def detect_role(contract: dict, sme_name: str | None, raw_text: str) -> dict:
    """
    Determine the SME's role in ONE contract. Returns:
      {sme_party, counterparty, role, confidence}
    role in {"supplier","customer","both","counterparty","unknown"}.

    Confidence-gated: weak signals -> role="unknown", which downstream keeps
    risk direction neutral rather than guessing a direction that could be
    exactly backwards.
    """
    result = {"sme_party": sme_name, "counterparty": None,
              "role": "unknown", "confidence": 0.0}

    parties = _split_parties(contract.get("parties") or "")
    if parties:
        if sme_name:
            sme_norm = _norm_party(sme_name)
            others = [p for p in parties if _norm_party(p) != sme_norm]
            result["counterparty"] = others[0] if others else None
        else:
            result["counterparty"] = parties[1] if len(parties) > 1 else None

    text = (raw_text or "").lower()
    sme_norm = _norm_party(sme_name) if sme_name else ""

    # Signal 1 (strongest): a defined-term label attached to the SME's name,
    # e.g. 'Acme Pte Ltd ("the Supplier")'.
    label_role = None
    if sme_norm:
        # Look for the SME name followed within ~60 chars by a quoted role label
        for label, role in _ROLE_LABELS.items():
            # e.g.  acme ... ("the supplier")   or   acme ... (the "supplier")
            pattern = re.escape(sme_norm.split()[0]) + r".{0,80}?[\"'\(]\s*(?:the\s+)?" + label
            if re.search(pattern, text):
                label_role = role
                break

    # Signal 2: payment direction. "customer shall pay the supplier" tells us
    # the roles even without knowing which the SME is by name — combine with
    # any label we found.
    pay_customer = bool(re.search(r"(customer|client|buyer|purchaser|licensee|tenant)\s+shall\s+pay", text))
    pay_supplier_receives = bool(re.search(r"pay(?:able)?\s+to\s+the\s+(supplier|vendor|provider|licensor|contractor|consultant)", text))

    contract_type = (contract.get("contract_type") or "").lower()

    # NDAs / mutual agreements are symmetric — no supplier/customer direction.
    if "nda" in contract_type or "non-disclosure" in contract_type or "mutual" in contract_type:
        result["role"] = "counterparty"
        result["confidence"] = 0.7
        return result

    if label_role:
        result["role"] = label_role
        # A direct defined-term label is strong evidence.
        result["confidence"] = 0.85
        return result

    # Fall back to type-based inference, weaker.
    if "distribution" in contract_type:
        # SME granted distribution rights -> usually the distributor (supplier side)
        result["role"] = "supplier"
        result["confidence"] = 0.45
    elif "services" in contract_type or "msa" in contract_type or "retainer" in contract_type:
        # Ambiguous without a label — leave unknown unless payment direction helps
        if pay_customer or pay_supplier_receives:
            result["role"] = "supplier"
            result["confidence"] = 0.5
        else:
            result["role"] = "unknown"
            result["confidence"] = 0.3
    else:
        result["role"] = "unknown"
        result["confidence"] = 0.3

    return result
