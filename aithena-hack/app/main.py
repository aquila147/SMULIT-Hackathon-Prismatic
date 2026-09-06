"""
AITHENA Contract Analyser — FastAPI Application
Updated to serve the integrated React frontend and all API endpoints.
"""

import os
import json
import asyncio
import logging
from pathlib import Path
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.db import get_db, init_db
from app.schemas import (
    Confidence, ExtractedField, ContractSummary, Conflict, HandoffBrief
)
from app.ingest import ingest_file, chunk_document

# Core pipeline modules. These are imported DIRECTLY (not wrapped in a
# swallowing try/except) so that any real syntax or import error surfaces
# loudly at startup instead of silently disabling a feature. If one of these
# fails to import, the app should refuse to start, not run half-broken.
from app.extract import extract_fields
from app.verify import verify_and_resolve
from app.agent_refuter import run_refuter
from app.calendar_utils import compute_calendar_events
from app.conflicts import detect_duplicate_coverage
from app.handoff import generate_handoff_brief
# CSV export is served directly from the database inside the export endpoints
# below (that is the live, correct data). The standalone app.export helpers
# (export_results_csv / export_coverage_csv) take a processed_contracts dict and
# are used by eval/calibrate.py, not by the API.


app = FastAPI(title="AITHENA Contract Analyser", version="1.0.0")


# ─── Database init ──────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    init_db()

    # Initialise the LLM client. Without this, every extractor's get_llm() call
    # raises RuntimeError, which the pipeline used to swallow — producing an app
    # that "runs" but extracts nothing. Fail LOUD instead of silent.
    import os
    from app.llm import init_llm

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. The extraction agents cannot run "
            "without it. Set it before starting the server, e.g.\n"
            '    PowerShell:  $env:OPENROUTER_API_KEY = "sk-or-..."\n'
            '    bash:        export OPENROUTER_API_KEY="sk-or-..."'
        )

    model = os.environ.get("LLM_MODEL", "").strip()
    if model:
        init_llm(api_key, model)
    else:
        init_llm(api_key)
    logging.getLogger("uvicorn").info("LLM client initialised.")


# ─── Health check ───────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}


# ─── Upload & process contracts ─────────────────────────────────────

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


async def _process_one_upload(upload_file) -> dict:
    """
    Everything that used to happen inline, per file, inside a single shared
    `for upload_file in files:` loop — now its own function so multiple files
    can run this concurrently via asyncio.gather instead of one after another.

    IMPORTANT — the database connection is not opened until AFTER every slow
    step (ingest, extraction, verify, refute) is finished. Everything that
    touches the database happens in one short, uninterrupted burst at the end,
    then commits and closes immediately.

    Why this matters: the FIRST version of this function opened its
    connection early, wrote the contract row, and then sat there through the
    entire multi-second extraction pipeline with that write transaction still
    open before finally committing. SQLite allows only ONE writer at a time
    even in WAL mode — WAL only helps readers not block writers, not writer
    vs writer. With several documents running concurrently, each holding an
    open write transaction for 10-30+ seconds, they queued for the lock and
    any that waited past the timeout failed with "database is locked". Moving
    every write to a single fast burst at the end shrinks that window from
    "the whole pipeline" to a few milliseconds of plain INSERT statements —
    small enough that even several documents finishing at the same moment
    should never collide for long enough to matter. `get_conn()`'s raised
    timeout (30s, was the 5s default) is a safety margin on top of this, not
    the fix itself.

    Actual API-call concurrency across ALL of this — however many documents,
    however many chunks each — is bounded by the ONE global semaphore in
    app/llm.py, not by anything in here.
    """
    filepath = UPLOAD_DIR / upload_file.filename
    content = await upload_file.read()
    filepath.write_bytes(content)

    try:
        # ---- SLOW PHASE: no database connection open during any of this ----
        doc_data = ingest_file(str(filepath))
        chunks = chunk_document(doc_data)

        fields = []
        if extract_fields:
            try:
                raw_fields = await extract_fields(doc_data)
                if verify_and_resolve and raw_fields:
                    fields = await asyncio.to_thread(
                        verify_and_resolve, raw_fields, doc_data.get("pages", [])
                    )
                    if run_refuter and fields:
                        fields = await run_refuter(
                            fields, doc_data.get("full_text", "")
                        )
                elif raw_fields:
                    fields = raw_fields
            except Exception as e:
                print(f"Extraction error for {upload_file.filename}: {e}")
                import traceback
                traceback.print_exc()

        # ---- FAST PHASE: open the connection now, write everything, commit
        # and close immediately. Nothing below this line awaits anything. ----
        db = get_db()
        try:
            cursor = db.execute(
                """INSERT OR REPLACE INTO contracts
                   (filename, is_scanned, clauses_total, clauses_covered, raw_text)
                   VALUES (?, ?, ?, 0, ?)""",
                (upload_file.filename, doc_data.get("is_scanned", False),
                 doc_data.get("clauses_total", 0), doc_data.get("full_text", "")[:50000])
            )
            contract_id = cursor.lastrowid

            for page in doc_data.get("pages", []):
                db.execute(
                    """INSERT INTO pages
                       (contract_id, page_number, text_content, has_text, image_path)
                       VALUES (?, ?, ?, ?, ?)""",
                    (contract_id, page["page_number"], page.get("text", ""),
                     page.get("has_text", True), page.get("image_path"))
                )

            parties = None
            contract_type = None
            start_date = None
            end_date = None
            renewal_type = None
            notice_period_days = None
            notice_deadline = None
            governing_law = None
            clauses_covered = 0

            for field in fields:
                f = field if isinstance(field, dict) else field.dict() if hasattr(field, 'dict') else field.model_dump()
                db.execute(
                    """INSERT INTO fields
                       (contract_id, field_name, value, value_alt, confidence,
                        verbatim_quote, quote_match_score, page, bbox,
                        extractor_a_raw, extractor_b_raw, adversary_note)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (contract_id, f.get("field_name"), f.get("value"),
                     f.get("value_alt"), f.get("confidence", "UNGROUNDED"),
                     f.get("verbatim_quote"), f.get("quote_match_score"),
                     f.get("page"), f.get("bbox"),
                     f.get("extractor_a_raw"), f.get("extractor_b_raw"),
                     f.get("adversary_note"))
                )
                if f.get("verbatim_quote"):
                    clauses_covered += 1

                fn = f.get("field_name", "")
                val = f.get("value")
                if fn == "parties" and val:
                    parties = val
                elif fn == "contract_type" and val:
                    contract_type = val
                elif fn == "start_date" and val:
                    start_date = val
                elif fn == "end_date" and val:
                    end_date = val
                elif fn == "renewal_type" and val:
                    renewal_type = val
                elif fn == "notice_period_days" and val:
                    try:
                        notice_period_days = int(val)
                    except (ValueError, TypeError):
                        pass
                elif fn == "notice_deadline" and val:
                    notice_deadline = val
                elif fn == "governing_law" and val:
                    governing_law = val

            db.execute(
                """UPDATE contracts SET
                   parties=?, contract_type=?, start_date=?, end_date=?,
                   renewal_type=?, notice_period_days=?, notice_deadline=?,
                   governing_law=?, clauses_covered=?
                   WHERE id=?""",
                (parties, contract_type, start_date, end_date, renewal_type,
                 notice_period_days, notice_deadline, governing_law,
                 clauses_covered, contract_id)
            )
            db.commit()

            return _contract_to_dict(db, contract_id)
        finally:
            db.close()

    except ValueError as e:
        return {"error": str(e), "filename": upload_file.filename}
    except Exception as e:
        print(f"Error processing {upload_file.filename}: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "filename": upload_file.filename}


@app.post("/api/upload")
async def upload_contracts(files: List[UploadFile] = File(...)):
    # All files are processed CONCURRENTLY now, not one after another. This
    # used to be the single biggest reason a 12-document batch took as long
    # as it did: the whole system, however fast internally, still queued
    # documents up one at a time. Each document gets its own DB connection
    # (see _process_one_upload), and total LLM request concurrency across
    # every document combined is bounded by the global semaphore in
    # app/llm.py — so this is faster without being less safe.
    results = await asyncio.gather(
        *[_process_one_upload(f) for f in files]
    )
    results = list(results)

    # Step 6: Detect conflicts — needs every contract to already be in the DB,
    # so this still runs after all uploads have finished, on a fresh connection.
    db = get_db()
    if detect_duplicate_coverage:
        try:
            all_contracts = _get_all_contracts(db)
            # Build filename→id lookup so we can store FKs
            fname_to_id = {c["filename"]: c["id"] for c in all_contracts}
            conflicts = detect_duplicate_coverage(all_contracts)
            for c in conflicts:
                cd = c if isinstance(c, dict) else c.dict() if hasattr(c, 'dict') else c.model_dump()
                # detect_duplicate_coverage returns filenames, not IDs — resolve them
                a_id = cd.get("contract_a_id") or fname_to_id.get(cd.get("contract_a_filename"))
                b_id = cd.get("contract_b_id") or fname_to_id.get(cd.get("contract_b_filename"))
                db.execute(
                    """INSERT INTO conflicts
                       (contract_a_id, contract_b_id, kind, description, severity)
                       VALUES (?, ?, ?, ?, ?)""",
                    (a_id, b_id,
                     cd.get("kind", "exclusivity_overlap"),
                     cd.get("description", ""), cd.get("severity", "medium"))
                )
            db.commit()
        except Exception as e:
            print(f"Conflict detection error: {e}")
            import traceback
            traceback.print_exc()

    # Step 7: Corpus-level analysis — party roles, portfolio risk, gaps.
    # All run after every contract is in the DB, on the same connection.
    try:
        _run_corpus_analysis(db)
    except Exception as e:
        print(f"Corpus analysis error: {e}")
        import traceback
        traceback.print_exc()

    return JSONResponse(content=results)


def _run_corpus_analysis(db):
    """
    Runs after all uploads: identifies the SME and its role per contract,
    scores portfolio risk (role-aware), and detects dangling-reference gaps.
    Each step is isolated so one failing doesn't sink the others.
    """
    from app.party_role import identify_sme, detect_role
    from app.risk import score_contract
    from app.gaps import detect_gaps

    all_contracts = _get_all_contracts(db)
    if not all_contracts:
        return

    # --- Party roles ---
    try:
        sme_name, sme_conf = identify_sme(all_contracts)
        for c in all_contracts:
            role_info = detect_role(c, sme_name, c.get("raw_text", ""))
            db.execute(
                """UPDATE contracts SET sme_party=?, counterparty=?,
                   sme_role=?, role_confidence=? WHERE id=?""",
                (role_info["sme_party"], role_info["counterparty"],
                 role_info["role"], str(role_info["confidence"]), c["id"])
            )
            c["sme_role"] = role_info["role"]  # keep in-memory copy for risk step
        db.commit()
    except Exception as e:
        print(f"Party-role detection error: {e}")

    # --- Portfolio risk (needs fields + role) ---
    try:
        db.execute("DELETE FROM risk_findings")  # recompute cleanly each upload
        for c in all_contracts:
            contract_dict = _contract_to_dict(db, c["id"])
            role = c.get("sme_role", "unknown")
            findings = score_contract(contract_dict, role)
            for f in findings:
                db.execute(
                    """INSERT INTO risk_findings
                       (contract_id, field_name, assertion, severity, basis,
                        evidence, benchmark_note, requires_lawyer)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (c["id"], f["field_name"], f["assertion"], f["severity"],
                     f["basis"], f["evidence"], None,
                     1 if f["requires_lawyer"] else 0)
                )
        db.commit()
    except Exception as e:
        print(f"Risk scoring error: {e}")

    # --- Gaps / dangling references ---
    try:
        db.execute("DELETE FROM gaps")  # recompute cleanly each upload
        gaps = detect_gaps(all_contracts)
        import json as _json
        for g in gaps:
            db.execute(
                """INSERT INTO gaps
                   (source_contract_id, source_filename, kind, reference_text,
                    page, resolution, candidates, language_note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (g.get("source_contract_id"), g.get("source_filename"),
                 g.get("kind"), g.get("reference_text"), g.get("page"),
                 g.get("resolution"), _json.dumps(g.get("candidates", [])),
                 g.get("language_note"))
            )
        db.commit()
    except Exception as e:
        print(f"Gap detection error: {e}")


# ─── Contract endpoints ────────────────────────────────────────────

@app.get("/api/contracts")
def list_contracts():
    db = get_db()
    rows = db.execute("SELECT id FROM contracts ORDER BY id").fetchall()
    return [_contract_to_dict(db, row["id"]) for row in rows]


@app.get("/api/contracts/{contract_id}")
def get_contract(contract_id: int):
    db = get_db()
    row = db.execute("SELECT id FROM contracts WHERE id=?", (contract_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contract not found")
    return _contract_to_dict(db, contract_id)


# ─── Calendar events ───────────────────────────────────────────────

@app.get("/api/calendar")
def get_calendar():
    db = get_db()
    contracts = _get_all_contracts(db)

    if compute_calendar_events:
        try:
            # compute_calendar_events is per-contract: (contract_id, fields) -> list[dict]
            result = []
            for c in contracts:
                c_id = c["id"]
                c_fields = [dict(f) for f in db.execute(
                    "SELECT * FROM fields WHERE contract_id=?", (c_id,)
                ).fetchall()]
                if not c_fields:
                    continue
                contract_events = compute_calendar_events(
                    contract_id=str(c_id),
                    fields=c_fields,
                )
                for e in contract_events:
                    ed = e if isinstance(e, dict) else e.dict() if hasattr(e, 'dict') else e.model_dump()
                    # Map the internal event shape (event / event_date /
                    # days_remaining) to the exact field names the frontend's
                    # mapCalendarEvent() expects (event_type / date /
                    # days_away / priority). This mismatch was crashing the
                    # dashboard on mapEventType(undefined).toLowerCase() and
                    # leaving the calendar empty.
                    days_away = ed.get("days_remaining", 999)
                    result.append({
                        "contract_id": ed.get("contract_id"),
                        "contract_filename": c.get("filename", ""),
                        "event_type": "renewal" if ed.get("event") == "auto_renews" else "expiry",
                        "date": ed.get("event_date"),
                        "action_by": ed.get("action_by"),
                        "days_away": days_away,
                        "priority": (
                            "urgent" if days_away <= 14
                            else "upcoming" if days_away <= 30
                            else "clear"
                        ),
                        "confidence": ed.get("confidence"),
                        "provenance": ed.get("provenance"),
                        "derived_from": ed.get("derived_from", []),
                    })
            return result
        except Exception as e:
            print(f"Calendar computation error: {e}")
            import traceback
            traceback.print_exc()

    # Fallback: generate events from contract dates
    from datetime import datetime, date
    events = []
    today = date.today()

    for c in contracts:
        cid = c["id"]
        fname = c["filename"]

        if c.get("end_date"):
            try:
                end = datetime.strptime(c["end_date"], "%Y-%m-%d").date()
                days = (end - today).days
                if 0 <= days <= 90:
                    events.append({
                        "contract_id": cid,
                        "contract_filename": fname,
                        "event_type": "renewal" if c.get("renewal_type") == "auto" else "expiry",
                        "date": c["end_date"],
                        "days_away": days,
                        "priority": "urgent" if days <= 14 else "upcoming" if days <= 30 else "clear",
                    })
            except (ValueError, TypeError):
                pass

        if c.get("notice_deadline"):
            try:
                nd = datetime.strptime(c["notice_deadline"], "%Y-%m-%d").date()
                days = (nd - today).days
                if 0 <= days <= 90:
                    events.append({
                        "contract_id": cid,
                        "contract_filename": fname,
                        "event_type": "notice_deadline",
                        "date": c["notice_deadline"],
                        "days_away": days,
                        "priority": "urgent" if days <= 14 else "upcoming" if days <= 30 else "clear",
                    })
            except (ValueError, TypeError):
                pass

    events.sort(key=lambda e: e["days_away"])
    return events


# ─── Conflicts ──────────────────────────────────────────────────────

@app.get("/api/conflicts")
def get_conflicts():
    db = get_db()
    rows = db.execute(
        """SELECT c.*, ca.filename as contract_a_filename, cb.filename as contract_b_filename
           FROM conflicts c
           LEFT JOIN contracts ca ON c.contract_a_id = ca.id
           LEFT JOIN contracts cb ON c.contract_b_id = cb.id"""
    ).fetchall()
    return [dict(row) for row in rows]


# ─── Handoff brief ──────────────────────────────────────────────────

@app.get("/api/contracts/{contract_id}/handoff")
def get_handoff(contract_id: int):
    db = get_db()
    row = db.execute("SELECT id FROM contracts WHERE id=?", (contract_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contract not found")

    contract_data = _contract_to_dict(db, contract_id)
    fields = contract_data.get("fields", [])

    contested = [f for f in fields
                 if f.get("confidence") in ("CONTESTED", "UNGROUNDED")]

    if not contested:
        return None

    # generate_handoff_brief(title, trigger, issue_summary, contracts, resolved_fields, negative_findings)
    if generate_handoff_brief:
        try:
            negative = [f.get("field_name", "") for f in fields
                        if f.get("confidence") == "UNGROUNDED"]
            brief = generate_handoff_brief(
                title=f"Review needed: {contract_data.get('filename', 'Unknown')}",
                trigger="contested_or_ungrounded_fields",
                issue_summary=f"{len(contested)} field(s) did not reach VERIFIED confidence",
                contracts=[contract_data],
                resolved_fields=fields,
                negative_findings=negative or None,
            )
            return brief
        except Exception as e:
            print(f"Handoff generation error: {e}")
            import traceback
            traceback.print_exc()

    # Fallback
    return {
        "title": f"Review needed: {contract_data.get('filename', 'Unknown')}",
        "issue_summary": f"{len(contested)} field(s) require human verification",
        "relevant_documents": [contract_data.get("filename", "")],
        "relevant_clauses": [
            {"filename": contract_data.get("filename", ""),
             "field_name": f.get("field_name", ""),
             "quote": f.get("verbatim_quote", ""),
             "page": f.get("page", 0)}
            for f in contested if f.get("verbatim_quote")
        ],
        "what_the_tool_established": "AITHENA extracted and verified contract terms using dual-extractor analysis with span matching. The fields listed below did not reach the VERIFIED confidence tier.",
        "specific_question_for_lawyer": "Please verify the contested/ungrounded findings and advise on any legal implications.",
        "contested_or_ungrounded_fields": contested,
    }


# ─── Risk & Gaps endpoints ─────────────────────────────────────────

@app.get("/api/risk")
def get_portfolio_risk():
    """Portfolio-wide risk findings, grouped — never a single score."""
    from app.risk import portfolio_risk_summary
    db = get_db()
    contracts = _get_all_contracts(db)

    contracts_with_findings = []
    for c in contracts:
        rows = db.execute(
            "SELECT * FROM risk_findings WHERE contract_id=?", (c["id"],)
        ).fetchall()
        c_copy = dict(c)
        c_copy["risk_findings"] = [dict(r) for r in rows]
        contracts_with_findings.append(c_copy)

    summary = portfolio_risk_summary(contracts_with_findings)
    return {
        "summary": summary,
        "contracts": [
            {
                "contract_id": c["id"],
                "filename": c["filename"],
                "sme_role": c.get("sme_role", "unknown"),
                "findings": c["risk_findings"],
            }
            for c in contracts_with_findings if c["risk_findings"]
        ],
    }


@app.get("/api/contracts/{contract_id}/risk")
def get_contract_risk(contract_id: int):
    """Risk findings for a single contract."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM risk_findings WHERE contract_id=?", (contract_id,)
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/gaps")
def get_gaps():
    """Unresolved/ambiguous references — 'what might be missing'."""
    import json as _json
    db = get_db()
    rows = db.execute("SELECT * FROM gaps ORDER BY resolution").fetchall()
    gaps = []
    for r in rows:
        g = dict(r)
        try:
            g["candidates"] = _json.loads(g.get("candidates") or "[]")
        except Exception:
            g["candidates"] = []
        gaps.append(g)
    return {
        "gaps": gaps,
        "total": len(gaps),
        "note": (
            "These are references we could not resolve to a document in the "
            "uploaded folder. This does not prove anything is missing — the "
            "referenced document may be filed elsewhere or superseded."
        ),
    }


# ─── Portfolio query (Ask page) ────────────────────────────────────

class QueryRequest(BaseModel):
    question: str

@app.post("/api/query")
async def query_portfolio(req: QueryRequest):
    from app.query import answer_question
    if not req.question.strip():
        return {"answer": "Sorry, I can't reply to this question.", "error": True}
    result = await answer_question(req.question.strip())
    return result


# ─── Portfolio stats ────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats():
    db = get_db()

    total = db.execute("SELECT COUNT(*) as n FROM contracts").fetchone()["n"]

    # Actions Required = contracts with a renewal/expiry deadline actually
    # falling inside the next 90 days. The old query counted a
    # 'notice_deadline' field the extractors don't reliably emit, so it was
    # always 0. Compute it from the real calendar instead.
    actions = 0
    renewals = 0
    try:
        from app.calendar_utils import compute_calendar_events
        for c in _get_all_contracts(db):
            c_fields = [dict(f) for f in db.execute(
                "SELECT * FROM fields WHERE contract_id=?", (c["id"],)
            ).fetchall()]
            if not c_fields:
                continue
            for e in compute_calendar_events(contract_id=str(c["id"]), fields=c_fields):
                # Anything needing a decision inside the window is an action.
                if e.get("days_remaining", 999) <= 90:
                    actions += 1
                if e.get("event") == "auto_renews":
                    renewals += 1
    except Exception as e:
        print(f"Stats calendar computation error: {e}")

    conflicts = db.execute("SELECT COUNT(*) as n FROM conflicts").fetchone()["n"]

    legal = db.execute(
        """SELECT COUNT(DISTINCT contract_id) as n FROM fields
           WHERE confidence IN ('INFERRED', 'CONTESTED', 'UNGROUNDED')"""
    ).fetchone()["n"]

    return {
        "total_contracts": total,
        "actions_required": actions,
        "renewals_90_days": renewals,
        "potential_conflicts": conflicts,
        "legal_review_needed": legal,
    }


# ─── Page images (for scanned documents) ───────────────────────────

@app.get("/api/pages/{contract_id}/{page_num}/image")
def get_page_image(contract_id: int, page_num: int):
    db = get_db()
    row = db.execute(
        "SELECT image_path FROM pages WHERE contract_id=? AND page_number=?",
        (contract_id, page_num)
    ).fetchone()

    if not row or not row["image_path"]:
        raise HTTPException(status_code=404, detail="No image for this page")

    path = Path(row["image_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file not found")

    return FileResponse(path, media_type="image/png")


# ─── CSV export ─────────────────────────────────────────────────────

@app.get("/api/export/results")
def export_results():
    db = get_db()
    import csv
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["contract", "field", "value", "confidence", "quote", "page"])
    rows = db.execute(
        """SELECT c.filename, f.field_name, f.value, f.confidence,
                  f.verbatim_quote, f.page
           FROM fields f JOIN contracts c ON f.contract_id = c.id
           ORDER BY c.filename, f.field_name"""
    ).fetchall()
    for r in rows:
        writer.writerow([r["filename"], r["field_name"], r["value"],
                        r["confidence"], r["verbatim_quote"], r["page"]])
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=aithena_results.csv"}
    )


@app.get("/api/export/coverage")
def export_coverage():
    db = get_db()
    import csv
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["contract", "clauses_total", "clauses_covered",
                     "verified", "inferred", "contested", "ungrounded"])
    rows = db.execute("SELECT * FROM contracts ORDER BY filename").fetchall()
    for r in rows:
        fields = db.execute(
            "SELECT confidence FROM fields WHERE contract_id=?", (r["id"],)
        ).fetchall()
        counts = {"VERIFIED": 0, "INFERRED": 0, "CONTESTED": 0, "UNGROUNDED": 0}
        for f in fields:
            conf = f["confidence"]
            if conf in counts:
                counts[conf] += 1
        writer.writerow([r["filename"], r["clauses_total"], r["clauses_covered"],
                        counts["VERIFIED"], counts["INFERRED"],
                        counts["CONTESTED"], counts["UNGROUNDED"]])
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=aithena_coverage.csv"}
    )


# ─── Serve original PDF for "View Original" ────────────────────────

@app.get("/api/contracts/{contract_id}/pdf")
def get_contract_pdf(contract_id: int):
    db = get_db()
    row = db.execute("SELECT filename FROM contracts WHERE id=?", (contract_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contract not found")
    path = UPLOAD_DIR / row["filename"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(path, media_type="application/pdf", filename=row["filename"])


# ─── Helpers ────────────────────────────────────────────────────────

def _contract_to_dict(db, contract_id: int) -> dict:
    """Build a full contract dict with nested fields from the DB."""
    row = db.execute("SELECT * FROM contracts WHERE id=?", (contract_id,)).fetchone()
    if not row:
        return {}

    fields = db.execute(
        "SELECT * FROM fields WHERE contract_id=? ORDER BY field_name",
        (contract_id,)
    ).fetchall()

    return {
        "id": row["id"],
        "filename": row["filename"],
        "parties": row["parties"],
        "contract_type": row["contract_type"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "renewal_type": row["renewal_type"],
        "notice_period_days": row["notice_period_days"],
        "notice_deadline": row["notice_deadline"],
        "governing_law": row["governing_law"],
        "is_scanned": bool(row["is_scanned"]),
        "clauses_total": row["clauses_total"] or 0,
        "clauses_covered": row["clauses_covered"] or 0,
        "fields": [
            {
                "field_name": f["field_name"],
                "value": f["value"],
                "value_alt": f["value_alt"],
                "verbatim_quote": f["verbatim_quote"],
                "quote_match_score": f["quote_match_score"],
                "page": f["page"],
                "bbox": f["bbox"],
                "confidence": f["confidence"],
                "extractor_a_raw": f["extractor_a_raw"],
                "extractor_b_raw": f["extractor_b_raw"],
                "adversary_note": f["adversary_note"],
            }
            for f in fields
        ],
    }


def _get_all_contracts(db) -> list:
    """Get all contracts as dicts (without fields, for conflict detection)."""
    rows = db.execute("SELECT * FROM contracts ORDER BY id").fetchall()
    return [dict(r) for r in rows]


# ─── Serve React SPA (production) ──────────────────────────────────

DIST_DIR = Path(__file__).parent.parent / "web" / "dist"
if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        file_path = DIST_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(DIST_DIR / "index.html")
