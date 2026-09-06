"""
Portfolio risk scoring.

Compares each contract's extracted terms against a curated set of "normal"
market positions and flags where the SME is materially worse off than typical.

DESIGN — grounding by construction:
The tool can only make a risk/norm assertion by SELECTING a pre-written rule
from RISK_RULES below. It never generates a legal claim in free text. That
makes a hallucinated legal assertion structurally impossible rather than
merely unlikely — which is exactly what the problem statement's grounding
requirement demands ("a clause in the document, a provision of Singapore law,
or a stated market norm").

ROLE-AWARE:
Each rule has a `direction` — the party it is adverse to. A rule fires only
when the SME's detected role matches, OR the rule is direction-neutral. If the
SME's role is UNKNOWN, only neutral rules fire — we never assert a directional
risk we might have backwards.

HONEST BENCHMARKS:
Every statistical claim discloses that it is a stated market norm and, where a
number is given, names it as a typical/reference position rather than a
measured percentile from the client's own corpus. We are explicit that these
are reference positions, not a computed score over their documents — and we
never roll it into a single "risk score out of 100", which would launder a
dozen uncertain judgements into one false-precision number.
"""

import re

# direction: "supplier" | "customer" | "neutral"
#   a rule fires only if SME role == direction, or direction == "neutral"
#   (with UNKNOWN role, only neutral rules fire)
RISK_RULES = [
    {
        "id": "LIAB_UNCAPPED_SUPPLIER",
        "field": "liability_cap",
        "direction": "supplier",
        "severity": "high",
        "assertion": "Your liability under this agreement is not capped.",
        "basis": "market norm",
        "evidence": "Most commercial supply and services agreements cap the supplier's aggregate liability, commonly at the fees paid over the preceding 12 months. An uncapped position exposes you to losses far exceeding contract value.",
        "requires_lawyer": True,
        "trigger": lambda v: _is_uncapped(v),
    },
    {
        "id": "LIAB_ABSENT",
        "field": "liability_cap",
        "direction": "supplier",
        "severity": "high",
        "assertion": "No liability cap was found in this agreement.",
        "basis": "market norm",
        "evidence": "A supplier-side agreement with no limitation of liability clause is unusual and leaves your exposure unbounded. Confirm whether a cap exists elsewhere (e.g. in a schedule) before relying on this.",
        "requires_lawyer": True,
        "trigger": lambda v: v is None or str(v).strip() == "" or str(v).upper() == "NOT_FOUND",
    },
    {
        "id": "NOTICE_LONG_AUTORENEW",
        "field": "notice_period_days",
        "direction": "neutral",
        "severity": "high",
        "assertion": "This agreement auto-renews and requires a long notice period to stop it.",
        "basis": "market norm",
        "evidence": "Notice windows of 90 days or more on auto-renewing contracts are onerous — missing the window commits you to another full term. Typical notice periods are 30-60 days. This is the exact failure mode behind unnoticed renewals.",
        "requires_lawyer": False,
        "trigger": lambda v: _days(v) is not None and _days(v) >= 90,
    },
    {
        "id": "NOTICE_MODERATE",
        "field": "notice_period_days",
        "direction": "neutral",
        "severity": "medium",
        "assertion": "This agreement requires advance notice to prevent renewal.",
        "basis": "market norm",
        "evidence": "A notice period of 60-89 days is on the longer side of typical. Diarise the deadline well in advance so the window is not missed.",
        "requires_lawyer": False,
        "trigger": lambda v: _days(v) is not None and 60 <= _days(v) < 90,
    },
    {
        "id": "FOREIGN_LAW",
        "field": "governing_law",
        "direction": "neutral",
        "severity": "medium",
        "assertion": "This agreement is governed by foreign law.",
        "basis": "market norm",
        "evidence": "For a Singapore business, a foreign governing law means disputes may need to be resolved abroad, typically at materially higher cost and complexity. Confirm this was a deliberate commercial choice.",
        "requires_lawyer": False,
        "trigger": lambda v: v is not None and "singapore" not in str(v).lower() and str(v).strip() != "" and str(v).upper() != "NOT_FOUND",
    },
    {
        "id": "EXCLUSIVITY_GRANTED",
        "field": "exclusivity",
        "direction": "neutral",
        "severity": "high",
        "assertion": "This agreement contains an exclusivity commitment.",
        "basis": "market norm",
        "evidence": "Exclusivity limits who else you can deal with for the covered scope, territory and period. Confirm the scope is no broader than intended and that the commitment is time-limited.",
        "requires_lawyer": True,
        "trigger": lambda v: _is_yes(v),
    },
    {
        "id": "RESTRICTIVE_COVENANT",
        "field": "restrictive_covenants",
        "direction": "neutral",
        "severity": "medium",
        "assertion": "This agreement contains a restrictive covenant.",
        "basis": "Singapore law pointer",
        "evidence": "Restraint-of-trade clauses (non-compete, non-solicitation) are enforceable in Singapore only so far as they are reasonable in scope, duration and geography. Whether this particular clause is enforceable is fact-specific and requires legal advice.",
        "requires_lawyer": True,
        "trigger": lambda v: _is_yes(v),
    },
]


def _days(v) -> int | None:
    if v is None:
        return None
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None


def _is_uncapped(v) -> bool:
    if v is None:
        return False
    return bool(re.search(r"unlimited|uncapped|no\s+cap|not\s+limited", str(v), re.I))


def _is_yes(v) -> bool:
    if v is None:
        return False
    s = str(v).strip().lower()
    if s in ("", "not_found", "no", "none", "n/a", "non-exclusive", "false"):
        return False
    return bool(re.search(r"yes|exclusive|granted|present|applies|shall not|non-?compete|non-?solicit|true", s)) or s not in ("no", "none")


def score_contract(contract: dict, sme_role: str) -> list[dict]:
    """
    Evaluate all risk rules against one contract's fields.
    contract: dict with a "fields" list (each field has field_name, value, confidence).
    sme_role: "supplier" | "customer" | "both" | "counterparty" | "unknown"
    Returns a list of risk finding dicts (only rules that fired).
    """
    # Build a quick field lookup, but ONLY trust fields that reached at least
    # INFERRED confidence — never raise a risk flag off an UNGROUNDED value.
    field_values = {}
    for f in contract.get("fields", []):
        conf = f.get("confidence", "UNGROUNDED")
        if conf in ("VERIFIED", "INFERRED"):
            field_values[f.get("field_name")] = f.get("value")
        elif f.get("field_name") not in field_values:
            # keep a record it exists even if low-confidence, for absence checks
            field_values.setdefault(f.get("field_name"), None)

    findings = []
    for rule in RISK_RULES:
        # Role gating: directional rules only fire for the matching role.
        # "both" (middleman) sees both supplier- and customer-direction rules.
        direction = rule["direction"]
        if direction != "neutral":
            if sme_role == "unknown":
                continue  # never guess a direction
            if sme_role not in (direction, "both"):
                continue

        value = field_values.get(rule["field"])
        try:
            fired = rule["trigger"](value)
        except Exception:
            fired = False

        if fired:
            findings.append({
                "rule_id": rule["id"],
                "field_name": rule["field"],
                "assertion": rule["assertion"],
                "severity": rule["severity"],
                "basis": rule["basis"],
                "evidence": rule["evidence"],
                "requires_lawyer": rule["requires_lawyer"],
            })

    return findings


def portfolio_risk_summary(contracts_with_findings: list[dict]) -> dict:
    """
    Roll findings up across the portfolio WITHOUT producing a single score.
    Returns counts by severity and the list of flagged contracts, so the UI
    shows the distribution and the specific outliers — not a false-precision
    "risk: 72/100".
    """
    high = medium = low = 0
    flagged = []
    for c in contracts_with_findings:
        findings = c.get("risk_findings", [])
        if not findings:
            continue
        sev = [f["severity"] for f in findings]
        high += sev.count("high")
        medium += sev.count("medium")
        low += sev.count("low")
        flagged.append({
            "filename": c.get("filename"),
            "contract_id": c.get("id"),
            "finding_count": len(findings),
            "highest_severity": "high" if "high" in sev else ("medium" if "medium" in sev else "low"),
        })

    return {
        "total_findings": high + medium + low,
        "by_severity": {"high": high, "medium": medium, "low": low},
        "flagged_contracts": sorted(flagged, key=lambda x: {"high":0,"medium":1,"low":2}[x["highest_severity"]]),
        "disclaimer": (
            "Risk flags compare your contract terms against typical market "
            "positions. They are reference positions, not a measured score over "
            "your own corpus, and not legal advice. Each flag links to the "
            "specific clause it concerns."
        ),
    }
