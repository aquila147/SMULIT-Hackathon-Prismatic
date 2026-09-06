import re
from datetime import datetime, timedelta
from app.schemas import Confidence, Provenance
from app.safe_types import coerce_int


def parse_date(value: str) -> datetime | None:
    """Try multiple date formats."""
    if not value:
        return None
    value = str(value).strip()
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d %B %Y", "%B %d, %Y",
                "%B %d %Y", "%d-%m-%Y", "%d %b %Y", "%b %d, %Y", "%d.%m.%Y"]:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    # Last resort: pull "14 March 2023" out of a longer string.
    m = re.search(
        r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+(\d{4})", value, re.I,
    )
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y")
        except ValueError:
            pass
    return None


def _term_to_days(value) -> int | None:
    """Convert a term-length value ('2 years', '18 months', '90 days') to days,
    so an end date can be derived from start + term when no explicit end date
    was extracted."""
    if not value:
        return None
    text = str(value).lower()
    m = re.search(r"(\d+)\s*(day|week|month|year)", text)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    return n * {"day": 1, "week": 7, "month": 30, "year": 365}[unit]


def compute_calendar_events(
    contract_id: str,
    fields: list[dict],
    today: datetime | None = None,
    horizon_days: int = 90,
) -> list[dict]:
    """
    Compute forward calendar events from resolved fields.
    Every date here is DERIVED — computed in Python, never read from the contract.
    A deadline inherits the WEAKEST confidence of its inputs.
    """
    if today is None:
        today = datetime.now()

    horizon = today + timedelta(days=horizon_days)

    # Extract the fields we need
    field_map = {f["field_name"]: f for f in fields}

    start_f = field_map.get("start_date")
    end_f = field_map.get("end_date")
    renewal_f = field_map.get("renewal_type")
    notice_f = field_map.get("notice_period_days")
    term_f = field_map.get("term_length") or field_map.get("term")

    events = []

    # Try to parse end date directly.
    end_date = parse_date(end_f["value"]) if end_f and end_f.get("value") else None

    # If there's no explicit end date, derive one from start date + term length.
    # Many contracts state "2 year term" with only a start date and no end date,
    # so requiring a literal end_date was silently dropping most calendar events.
    if not end_date and start_f and start_f.get("value"):
        start_date = parse_date(start_f["value"])
        term_days = _term_to_days(term_f.get("value") if term_f else None)
        if start_date and term_days:
            end_date = start_date + timedelta(days=term_days)

    if not end_date:
        return events  # genuinely cannot place this contract on the calendar

    # Determine if auto-renewing. Robust substring check — extractors return
    # free-form text like "automatically renew" or "auto-renew", not the exact
    # token "auto", so an equality check against a fixed set silently missed
    # every real auto-renewal.
    renewal_text = str(renewal_f.get("value", "")).lower() if renewal_f else ""
    is_auto = any(
        kw in renewal_text
        for kw in ("auto", "renew", "evergreen", "successive", "automatic")
    )

    # Parse notice period using the same shared coercion the rest of the
    # codebase now uses, rather than a local ad-hoc str()+regex.
    notice_days = coerce_int(notice_f.get("value") if notice_f else None, default=0) or 0

    # Compute action-by date
    action_by = end_date - timedelta(days=notice_days) if notice_days > 0 else end_date

    # Only include events within the horizon
    if end_date <= horizon:
        # Confidence = min of all contributing fields
        contributing = [f for f in [end_f, renewal_f, notice_f, start_f] if f]
        confidence_order = [
            Confidence.UNGROUNDED, Confidence.CONTESTED,
            Confidence.INFERRED, Confidence.VERIFIED
        ]
        worst_confidence = Confidence.VERIFIED
        for f in contributing:
            fc = f.get("confidence", Confidence.UNGROUNDED.value)
            try:
                fc_enum = Confidence(fc)
            except ValueError:
                fc_enum = Confidence.UNGROUNDED
            if confidence_order.index(fc_enum) < confidence_order.index(worst_confidence):
                worst_confidence = fc_enum

        days_remaining = (action_by - today).days if action_by > today else 0

        event = {
            "contract_id": contract_id,
            "event": "auto_renews" if is_auto else "expires",
            "event_date": end_date.strftime("%Y-%m-%d"),
            "action_by": action_by.strftime("%Y-%m-%d"),
            "days_remaining": days_remaining,
            "provenance": Provenance.DERIVED.value,  # ALWAYS derived
            "confidence": worst_confidence.value,
            "derived_from": [
                {"field": f["field_name"], "value": f.get("value"), "confidence": f.get("confidence")}
                for f in contributing
            ],
            # Flag the S$40k scenario
            "urgent_unverified": (
                days_remaining <= 30
                and worst_confidence.value != Confidence.VERIFIED.value
            ),
        }
        events.append(event)

    return events
