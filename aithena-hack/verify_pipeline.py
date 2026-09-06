# AITHENA Pipeline Verification Script
# =====================================
# Run this AFTER implementing the Person B guide.
# It checks every seam between components, catches common mistakes,
# and confirms the pipeline works end-to-end.
#
# Usage:
#     cd aithena-hack
#     python verify_pipeline.py
#
# Set your OpenRouter key first:
#     $env:OPENROUTER_API_KEY = "your-key-here"

import asyncio
import os
import sys
import json
import traceback
import re
from datetime import datetime, timedelta

# ============================================================
# COLOR OUTPUT
# ============================================================
def ok(msg):   print(f"  [PASS] {msg}")
def fail(msg): print(f"  [FAIL] {msg}")
def warn(msg): print(f"  [WARN] {msg}")
def info(msg): print(f"  [INFO] {msg}")
def header(msg): print(f"\n{'='*60}\n  {msg}\n{'='*60}")

results = {"pass": 0, "fail": 0, "warn": 0}

def check(condition, pass_msg, fail_msg):
    if condition:
        ok(pass_msg)
        results["pass"] += 1
    else:
        fail(fail_msg)
        results["fail"] += 1

# ============================================================
# TEST 1: Imports - do all modules load without errors?
# ============================================================
def test_imports():
    header("TEST 1: Module Imports")

    modules = {
        "app.schemas": "Pydantic schemas",
        "app.db": "Database layer",
        "app.main": "FastAPI app",
        "app.ingest": "Ingestion pipeline (Person A)",
        "app.llm": "LLM client",
        "app.extract": "Extractors (Person B)",
        "app.verify": "Verification / span gate (Person B)",
        "app.calendar_utils": "Calendar date arithmetic (Person B)",
        "app.conflicts": "Conflict detection (Person B)",
        "app.handoff": "Escalation briefs (Person B)",
    }

    imported = {}
    for mod_name, desc in modules.items():
        try:
            mod = __import__(mod_name, fromlist=[""])
            imported[mod_name] = mod
            ok(f"{desc} ({mod_name})")
        except Exception as e:
            fail(f"{desc} ({mod_name}): {e}")
            imported[mod_name] = None

    return imported


# ============================================================
# TEST 2: Schema completeness - are the new types present?
# ============================================================
def test_schemas(modules):
    header("TEST 2: Schema Completeness")

    schemas = modules.get("app.schemas")
    if not schemas:
        fail("Cannot test - app.schemas did not import")
        return

    # Original types (should still exist)
    for name in ["Confidence", "ExtractedField", "ContractSummary", "Conflict", "HandoffBrief"]:
        check(
            hasattr(schemas, name),
            f"Original type '{name}' exists",
            f"Original type '{name}' MISSING - did you accidentally delete it?"
        )

    # New types from the guide
    for name in ["Provenance", "FieldStatus"]:
        check(
            hasattr(schemas, name),
            f"New type '{name}' exists",
            f"New type '{name}' MISSING - add it per Step 0 of the guide"
        )

    # Check Confidence enum values
    if hasattr(schemas, "Confidence"):
        conf = schemas.Confidence
        for val in ["VERIFIED", "INFERRED", "CONTESTED", "UNGROUNDED"]:
            check(
                hasattr(conf, val),
                f"Confidence.{val} exists",
                f"Confidence.{val} MISSING"
            )

    # Check Provenance enum values
    if hasattr(schemas, "Provenance"):
        prov = schemas.Provenance
        for val in ["DIRECT", "DERIVED", "INFERRED", "ABSENT", "UNKNOWN"]:
            check(
                hasattr(prov, val),
                f"Provenance.{val} exists",
                f"Provenance.{val} MISSING"
            )

    # Check FieldStatus - the CRITICAL three-state distinction
    if hasattr(schemas, "FieldStatus"):
        fs = schemas.FieldStatus
        for val in ["FOUND", "ABSENT", "CANNOT_ASSESS"]:
            check(
                hasattr(fs, val),
                f"FieldStatus.{val} exists",
                f"FieldStatus.{val} MISSING - this three-state distinction is load-bearing"
            )


# ============================================================
# TEST 3: LLM client - does it initialize and have the right shape?
# ============================================================
def test_llm(modules):
    header("TEST 3: LLM Client")

    llm_mod = modules.get("app.llm")
    if not llm_mod:
        fail("Cannot test - app.llm did not import")
        return

    # Check required functions exist
    for fn_name in ["init_llm", "get_llm"]:
        check(
            hasattr(llm_mod, fn_name) and callable(getattr(llm_mod, fn_name)),
            f"Function '{fn_name}()' exists",
            f"Function '{fn_name}()' MISSING"
        )

    # Check that get_llm raises before init
    try:
        llm_mod.get_llm()
        warn("get_llm() did not raise before init - should require init_llm() first")
        results["warn"] += 1
    except RuntimeError:
        ok("get_llm() correctly raises before init_llm() is called")
        results["pass"] += 1
    except Exception as e:
        warn(f"get_llm() raised unexpected error: {e}")
        results["warn"] += 1

    # Check LLMClient class
    if hasattr(llm_mod, "LLMClient"):
        client_cls = llm_mod.LLMClient
        check(
            hasattr(client_cls, "complete"),
            "LLMClient has 'complete' method",
            "LLMClient MISSING 'complete' method"
        )

    # Initialize if key is available
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if api_key:
        try:
            llm_mod.init_llm(api_key)
            client = llm_mod.get_llm()
            ok(f"LLM initialized with key (model: {getattr(client, 'model', '?')})")
        except Exception as e:
            fail(f"LLM init failed: {e}")
    else:
        warn("OPENROUTER_API_KEY not set - skipping live LLM test")
        results["warn"] += 1


# ============================================================
# TEST 4: Extract - do the extractors have the right interface?
# ============================================================
def test_extract(modules):
    header("TEST 4: Extractors")

    extract_mod = modules.get("app.extract")
    if not extract_mod:
        fail("Cannot test - app.extract did not import")
        return

    # Check main entry point
    check(
        hasattr(extract_mod, "extract_fields") and callable(extract_mod.extract_fields),
        "extract_fields() entry point exists",
        "extract_fields() MISSING - this is the main function Person B exposes"
    )

    # Check both extractors exist
    for fn in ["run_extractor_a", "run_extractor_b"]:
        check(
            hasattr(extract_mod, fn) and callable(getattr(extract_mod, fn)),
            f"{fn}() exists",
            f"{fn}() MISSING"
        )

    # Check FIELD_NAMES list
    if hasattr(extract_mod, "FIELD_NAMES"):
        fn_list = extract_mod.FIELD_NAMES
        check(
            len(fn_list) >= 10,
            f"FIELD_NAMES has {len(fn_list)} fields (>= 10 required)",
            f"FIELD_NAMES only has {len(fn_list)} fields - need at least 10"
        )
        # Check critical fields are present
        for critical in ["parties", "start_date", "end_date", "renewal_type",
                         "notice_period_days", "liability_cap", "governing_law"]:
            check(
                critical in fn_list,
                f"  Field '{critical}' in FIELD_NAMES",
                f"  Field '{critical}' MISSING from FIELD_NAMES - this is a judged field"
            )
    else:
        fail("FIELD_NAMES list MISSING")

    # Check system prompts exist and mention verbatim quotes
    for prompt_name in ["EXTRACTOR_A_SYSTEM", "EXTRACTOR_B_SYSTEM"]:
        if hasattr(extract_mod, prompt_name):
            prompt = getattr(extract_mod, prompt_name)
            check(
                "verbatim" in prompt.lower() or "exact" in prompt.lower(),
                f"{prompt_name} mentions verbatim/exact quotes",
                f"{prompt_name} does not mention verbatim quotes - agents MUST return exact quotes"
            )
        else:
            warn(f"{prompt_name} not found as module-level variable (may be inline)")
            results["warn"] += 1


# ============================================================
# TEST 5: Verify - the span gate and resolution logic
# ============================================================
def test_verify(modules):
    header("TEST 5: Span Gate and Verification")

    verify_mod = modules.get("app.verify")
    if not verify_mod:
        fail("Cannot test - app.verify did not import")
        return

    # Check required functions
    for fn in ["normalize_whitespace", "span_gate", "resolve_field", "verify_and_resolve"]:
        check(
            hasattr(verify_mod, fn) and callable(getattr(verify_mod, fn)),
            f"{fn}() exists",
            f"{fn}() MISSING"
        )

    # Test normalize_whitespace
    if hasattr(verify_mod, "normalize_whitespace"):
        nw = verify_mod.normalize_whitespace
        check(
            nw("hello   world") == "hello world",
            "normalize_whitespace collapses spaces",
            "normalize_whitespace does not collapse spaces"
        )
        check(
            nw("soft\u00adhyphen") == "softhyphen",
            "normalize_whitespace strips soft hyphens",
            "normalize_whitespace does not strip soft hyphens - will break fuzzy matching"
        )
        check(
            nw("line\nbreak\ttab") == "line break tab",
            "normalize_whitespace handles newlines and tabs",
            "normalize_whitespace does not handle newlines/tabs"
        )

    # Test span gate with a KNOWN good match
    if hasattr(verify_mod, "span_gate"):
        test_claim = {
            "agent_id": "test",
            "field_name": "test_field",
            "status": "FOUND",
            "value": "90 days",
            "verbatim_quote": "ninety (90) days prior written notice",
            "quote_page": 0,
        }
        test_pages = [
            {"text": "The Supplier shall provide ninety (90) days prior written notice of termination."}
        ]
        result = verify_mod.span_gate(test_claim, test_pages)
        check(
            result.get("span_score", 0) >= 85,
            f"Span gate: good quote scores {result.get('span_score', 0):.0f} (>= 85)",
            f"Span gate: good quote only scored {result.get('span_score', 0):.0f} - threshold too high?"
        )
        check(
            not result.get("discarded", True),
            "Span gate: good quote NOT discarded",
            "Span gate: good quote was DISCARDED - this will kill valid extractions"
        )

    # Test span gate with a FABRICATED quote
    if hasattr(verify_mod, "span_gate"):
        fake_claim = {
            "agent_id": "test",
            "field_name": "test_field",
            "status": "FOUND",
            "value": "30 days",
            "verbatim_quote": "thirty (30) days written notice shall be provided by either party",
            "quote_page": 0,
        }
        test_pages = [
            {"text": "The term of this agreement shall be twenty-four months from the effective date."}
        ]
        result = verify_mod.span_gate(fake_claim, test_pages)
        check(
            result.get("discarded", False),
            f"Span gate: fabricated quote DISCARDED (score {result.get('span_score', 0):.0f})",
            f"Span gate: fabricated quote NOT discarded (score {result.get('span_score', 0):.0f}) - gate is too loose!"
        )

    # Test resolve_field: two extractors agree
    if hasattr(verify_mod, "resolve_field"):
        agreeing_claims = [
            {"agent_id": "extractor_a", "field_name": "notice_period_days",
             "status": "FOUND", "value": "90 days",
             "verbatim_quote": "ninety (90) days", "span_score": 95,
             "discarded": False, "quote_page": 3},
            {"agent_id": "extractor_b", "field_name": "notice_period_days",
             "status": "FOUND", "value": "90 days",
             "verbatim_quote": "ninety (90) days prior written notice", "span_score": 92,
             "discarded": False, "quote_page": 3},
        ]
        resolved = verify_mod.resolve_field("notice_period_days", agreeing_claims)
        check(
            resolved.get("confidence") == "VERIFIED",
            f"Two agreeing extractors -> VERIFIED (got {resolved.get('confidence')})",
            f"Two agreeing extractors -> should be VERIFIED, got {resolved.get('confidence')}"
        )

    # Test resolve_field: extractors DISAGREE
    if hasattr(verify_mod, "resolve_field"):
        disagreeing_claims = [
            {"agent_id": "extractor_a", "field_name": "notice_period_days",
             "status": "FOUND", "value": "90 days",
             "verbatim_quote": "ninety (90) days", "span_score": 95,
             "discarded": False, "quote_page": 3},
            {"agent_id": "extractor_b", "field_name": "notice_period_days",
             "status": "FOUND", "value": "30 days",
             "verbatim_quote": "thirty (30) days notice", "span_score": 90,
             "discarded": False, "quote_page": 7},
        ]
        resolved = verify_mod.resolve_field("notice_period_days", disagreeing_claims)
        check(
            resolved.get("confidence") == "CONTESTED",
            f"Disagreeing extractors -> CONTESTED (got {resolved.get('confidence')})",
            f"Disagreeing extractors -> should be CONTESTED, got {resolved.get('confidence')}"
        )
        check(
            resolved.get("value_alt") is not None,
            "Disagreement records the alternative value in value_alt",
            "value_alt is None - disagreements should preserve both values"
        )

    # Test: ABSENT != CANNOT_ASSESS (the most common architecture failure)
    if hasattr(verify_mod, "resolve_field"):
        mixed_claims = [
            {"agent_id": "extractor_a", "field_name": "liability_cap",
             "status": "ABSENT", "value": None,
             "verbatim_quote": None, "span_score": 0,
             "discarded": False, "quote_page": None},
            {"agent_id": "extractor_b", "field_name": "liability_cap",
             "status": "CANNOT_ASSESS", "value": None,
             "verbatim_quote": None, "span_score": 0,
             "discarded": False, "quote_page": None},
        ]
        resolved = verify_mod.resolve_field("liability_cap", mixed_claims)
        check(
            resolved.get("confidence") != "CONTESTED",
            f"ABSENT + CANNOT_ASSESS -> NOT contested (got {resolved.get('confidence')})",
            "ABSENT + CANNOT_ASSESS -> wrongly marked CONTESTED - "
            "CANNOT_ASSESS is an abstention, not a disagreement!"
        )


# ============================================================
# TEST 6: Calendar - date arithmetic in Python, never the LLM
# ============================================================
def test_calendar(modules):
    header("TEST 6: Calendar Date Arithmetic")

    cal_mod = modules.get("app.calendar_utils")
    if not cal_mod:
        fail("Cannot test - app.calendar_utils did not import")
        return

    check(
        hasattr(cal_mod, "compute_calendar_events"),
        "compute_calendar_events() exists",
        "compute_calendar_events() MISSING"
    )

    if not hasattr(cal_mod, "compute_calendar_events"):
        return

    # Test with known fields
    test_fields = [
        {"field_name": "start_date", "value": "2023-01-01", "confidence": "VERIFIED"},
        {"field_name": "end_date", "value": "2027-01-01", "confidence": "VERIFIED"},
        {"field_name": "renewal_type", "value": "auto", "confidence": "VERIFIED"},
        {"field_name": "notice_period_days", "value": "90", "confidence": "INFERRED"},
    ]

    # Use a fixed "today" for deterministic testing
    test_today = datetime(2026, 9, 5)

    events = cal_mod.compute_calendar_events(
        "test_contract", test_fields, today=test_today, horizon_days=365
    )

    check(
        len(events) >= 1,
        f"Calendar produced {len(events)} event(s)",
        "Calendar produced 0 events - check date parsing and horizon logic"
    )

    if events:
        ev = events[0]
        check(
            ev.get("provenance") == "DERIVED",
            "Calendar event provenance = DERIVED",
            f"Calendar event provenance = {ev.get('provenance')} - MUST be DERIVED, "
            "no contract states its own renewal date"
        )
        check(
            "derived_from" in ev and len(ev["derived_from"]) >= 2,
            f"Calendar event carries derived_from chain ({len(ev.get('derived_from', []))} fields)",
            "Calendar event missing derived_from - mandatory for the demo"
        )
        # Confidence should inherit the WEAKEST input
        check(
            ev.get("confidence") != "VERIFIED",
            f"Calendar confidence = {ev.get('confidence')} (inherited weakest input)",
            "Calendar confidence = VERIFIED but notice_period is INFERRED - "
            "must inherit the weakest confidence"
        )


# ============================================================
# TEST 7: Conflicts - duplicate coverage detection
# ============================================================
def test_conflicts(modules):
    header("TEST 7: Conflict Detection")

    conflicts_mod = modules.get("app.conflicts")
    if not conflicts_mod:
        fail("Cannot test - app.conflicts did not import")
        return

    check(
        hasattr(conflicts_mod, "detect_duplicate_coverage"),
        "detect_duplicate_coverage() exists",
        "detect_duplicate_coverage() MISSING"
    )

    if not hasattr(conflicts_mod, "detect_duplicate_coverage"):
        return

    # Test with two contracts that should conflict
    test_contracts = [
        {
            "filename": "services_bravo_2023.pdf",
            "parties": "Acme Pte Ltd and Bravo Systems Pte Ltd",
            "contract_type": "services",
        },
        {
            "filename": "services_bravo_2024.pdf",
            "parties": "Acme Pte Ltd and Bravo Systems",
            "contract_type": "services",
        },
        {
            "filename": "nda_charlie_2024.pdf",
            "parties": "Acme Pte Ltd and Charlie Corp",
            "contract_type": "nda",
        },
    ]

    conflicts = conflicts_mod.detect_duplicate_coverage(test_contracts)

    check(
        len(conflicts) >= 1,
        f"Found {len(conflicts)} duplicate coverage conflict(s) (expected: Bravo pair)",
        "Found 0 conflicts - the Bravo pair should match even with 'Pte Ltd' vs no suffix"
    )

    if conflicts:
        c = conflicts[0]
        check(
            "breach" not in c.get("description", "").lower(),
            "Conflict description does NOT say 'breach'",
            "Conflict description says 'breach' - NEVER assert breach, say 'potential conflict'"
        )
        check(
            c.get("caveat") is not None,
            "Conflict carries a caveat",
            "Conflict missing caveat - must say 'whether this is a breach is a legal question'"
        )


# ============================================================
# TEST 8: Handoff - escalation brief generation
# ============================================================
def test_handoff(modules):
    header("TEST 8: Escalation Briefs")

    handoff_mod = modules.get("app.handoff")
    if not handoff_mod:
        fail("Cannot test - app.handoff did not import")
        return

    for fn in ["generate_handoff_brief", "brief_to_markdown"]:
        check(
            hasattr(handoff_mod, fn) and callable(getattr(handoff_mod, fn)),
            f"{fn}() exists",
            f"{fn}() MISSING"
        )

    if not hasattr(handoff_mod, "generate_handoff_brief"):
        return

    # Generate a test brief
    test_fields = [
        {"field_name": "notice_period_days", "value": "90", "confidence": "CONTESTED",
         "verbatim_quote": "ninety (90) days", "page": 3,
         "extractor_a_raw": "90 days", "extractor_b_raw": "30 days"},
    ]

    brief = handoff_mod.generate_handoff_brief(
        title="Test Escalation",
        trigger="substantial_dissent",
        issue_summary="Extractors disagree on notice period",
        contracts=[{"filename": "test.pdf"}],
        resolved_fields=test_fields,
        negative_findings=["No superseding amendment was found."],
    )

    check(
        brief.get("title") == "Test Escalation",
        "Brief has correct title",
        "Brief title mismatch"
    )
    check(
        len(brief.get("contested_or_ungrounded_fields", [])) >= 1,
        "Brief includes contested fields",
        "Brief missing contested fields - these are what the lawyer needs to review"
    )
    check(
        len(brief.get("negative_findings", [])) >= 1,
        "Brief includes negative findings",
        "Brief missing negative findings - 'what we checked and ruled out' saves lawyers time"
    )

    # Test markdown export
    if hasattr(handoff_mod, "brief_to_markdown"):
        md = handoff_mod.brief_to_markdown(brief)
        check(
            len(md) > 100,
            f"Markdown brief is {len(md)} chars",
            "Markdown brief is suspiciously short"
        )
        check(
            "ruled out" in md.lower() or "checked" in md.lower(),
            "Markdown brief mentions negative findings",
            "Markdown brief does not mention negative findings"
        )


# ============================================================
# TEST 9: FastAPI endpoints - do the routes exist?
# ============================================================
def test_api_routes(modules):
    header("TEST 9: API Endpoints")

    main_mod = modules.get("app.main")
    if not main_mod:
        fail("Cannot test - app.main did not import")
        return

    app = getattr(main_mod, "app", None)
    if not app:
        fail("No 'app' object found in app.main")
        return

    # Get all registered routes
    routes = {r.path for r in app.routes if hasattr(r, "path")}

    expected = [
        "/api/health",
        "/api/ingest",
        "/api/contracts",
        "/api/calendar",
        "/api/conflicts",
    ]

    for route in expected:
        found = route in routes or any(
            route.rstrip("/") in r or r.startswith(route.split("{")[0])
            for r in routes
        )
        check(found, f"Route {route} registered", f"Route {route} MISSING")

    # Check for contract detail route (parameterized)
    has_detail = any("/api/contracts/" in r for r in routes) or "/api/contracts/{filename}" in routes
    check(
        has_detail,
        "Contract detail route exists",
        "Contract detail route MISSING - judges need to drill into individual contracts"
    )


# ============================================================
# TEST 10: End-to-end pipeline (with LLM, if key available)
# ============================================================
async def test_e2e(modules):
    header("TEST 10: End-to-End Pipeline")

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        warn("Skipping E2E test - OPENROUTER_API_KEY not set")
        results["warn"] += 1
        return

    # Check for test corpus
    corpus_file = None
    for path in ["corpus/test_contract.pdf", "test_contract.pdf"]:
        if os.path.exists(path):
            corpus_file = path
            break

    if not corpus_file:
        warn("Skipping E2E test - no test PDF found in corpus/")
        results["warn"] += 1
        return

    info(f"Running full pipeline on {corpus_file}...")

    try:
        # Step 1: Ingest
        from app.ingest import ingest_file
        doc_data = ingest_file(corpus_file)
        check(
            doc_data.get("full_text") and len(doc_data["full_text"]) > 100,
            f"Ingest: {len(doc_data.get('full_text', ''))} chars extracted",
            "Ingest: no text extracted"
        )

        # Step 2: Extract
        from app.extract import extract_fields
        raw_claims = await extract_fields(doc_data)
        check(
            len(raw_claims) >= 5,
            f"Extract: {len(raw_claims)} raw claims from extractors",
            f"Extract: only {len(raw_claims)} claims - expected at least 5"
        )

        # Check claims have required fields
        if raw_claims:
            c = raw_claims[0]
            for key in ["agent_id", "field_name", "status"]:
                check(
                    key in c,
                    f"Claims have '{key}' field",
                    f"Claims MISSING '{key}' field - verify.py needs this"
                )

        # Step 3: Verify
        from app.verify import verify_and_resolve
        resolved = verify_and_resolve(raw_claims, doc_data["pages"])
        check(
            len(resolved) >= 5,
            f"Verify: {len(resolved)} resolved fields",
            f"Verify: only {len(resolved)} resolved fields"
        )

        # Check resolved fields have both confidence AND provenance
        for f in resolved:
            if f.get("confidence") and f.get("value"):
                check(
                    "provenance" in f,
                    f"Field '{f['field_name']}' has provenance alongside confidence",
                    f"Field '{f['field_name']}' MISSING provenance - must ship both signals"
                )
                break

        # Check span gate actually ran
        discarded = sum(1 for c in raw_claims if c.get("discarded"))
        info(f"Span gate discarded {discarded} of {len(raw_claims)} claims")

        # Count by confidence tier
        tier_counts = {}
        for f in resolved:
            tier = f.get("confidence", "UNKNOWN")
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        info(f"Confidence distribution: {tier_counts}")

        # Check that at least one field has a verbatim quote
        quoted = [f for f in resolved if f.get("verbatim_quote")]
        check(
            len(quoted) >= 1,
            f"{len(quoted)} fields have verbatim quotes",
            "No fields have verbatim quotes - extraction prompts may not be returning them"
        )

        # Step 4: Calendar
        from app.calendar_utils import compute_calendar_events
        events = compute_calendar_events("test", resolved)
        info(f"Calendar: {len(events)} event(s) computed")

        ok("End-to-end pipeline completed successfully")

    except Exception as e:
        fail(f"End-to-end pipeline crashed: {e}")
        traceback.print_exc()


# ============================================================
# TEST 11: Design rule violations - catch common mistakes
# ============================================================
def test_design_rules(modules):
    header("TEST 11: Design Rule Compliance")

    # Rule: Temperature must be 0
    llm_mod = modules.get("app.llm")
    if llm_mod:
        import inspect
        source = inspect.getsource(llm_mod)
        check(
            '"temperature": 0' in source or "'temperature': 0" in source or "temperature=0" in source,
            "LLM client sets temperature to 0 (deterministic)",
            "LLM client may not set temperature=0 - output must be deterministic"
        )

    # Rule: Fail soft - check for try/except in extract.py
    extract_mod = modules.get("app.extract")
    if extract_mod:
        import inspect
        source = inspect.getsource(extract_mod)
        check(
            "except" in source,
            "extract.py has error handling (fail-soft)",
            "extract.py has no try/except - a single LLM failure will crash the batch"
        )

    # Rule: CANNOT_ASSESS is distinct from ABSENT in extraction
    if extract_mod:
        import inspect
        source = inspect.getsource(extract_mod)
        check(
            "CANNOT_ASSESS" in source,
            "extract.py uses CANNOT_ASSESS status",
            "extract.py never mentions CANNOT_ASSESS - agents that fail should abstain, not vote against"
        )


# ============================================================
# MAIN
# ============================================================
def main():
    print()
    print("=" * 60)
    print("  AITHENA Pipeline Verification")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    modules = test_imports()
    test_schemas(modules)
    test_llm(modules)
    test_extract(modules)
    test_verify(modules)
    test_calendar(modules)
    test_conflicts(modules)
    test_handoff(modules)
    test_api_routes(modules)
    test_design_rules(modules)

    # Run async E2E test
    asyncio.run(test_e2e(modules))

    # Summary
    header("SUMMARY")
    total = results["pass"] + results["fail"] + results["warn"]
    print(f"  PASS: {results['pass']}")
    print(f"  FAIL: {results['fail']}")
    print(f"  WARN: {results['warn']}")
    print(f"  Total checks: {total}")

    if results["fail"] == 0:
        print("\n  All critical checks passed.")
    else:
        print(f"\n  {results['fail']} FAILURES - fix these before integration.")

    if results["warn"] > 0:
        print(f"  {results['warn']} warnings - review but not blocking.")

    print()
    return 0 if results["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
