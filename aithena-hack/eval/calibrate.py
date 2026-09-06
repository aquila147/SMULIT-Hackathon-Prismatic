# eval/calibrate.py
# Fully synchronous - no asyncio, avoids Python 3.14 cancellation bugs.
#
# Usage:
#   $env:OPENROUTER_API_KEY = "your-key"
#   python -m eval.calibrate --corpus corpus/

import argparse
import os
import sys
import json
import logging
import httpx
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ingest import ingest_file
from app.verify import verify_and_resolve
from app.export import export_results_csv, export_coverage_csv

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def llm_call(api_key: str, model: str, system_prompt: str, user_prompt: str) -> dict:
    """Direct synchronous LLM call. No asyncio involved."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(3):
        try:
            resp = httpx.post(OPENROUTER_URL, json=body, headers=headers, timeout=300.0)
            resp.raise_for_status()
            data = resp.json()
            tokens = data.get("usage", {}).get("total_tokens", "?")
            logger.info(f"  LLM: {tokens} tokens")

            content = data["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                content = content.rsplit("```", 1)[0]
            return json.loads(content)
        except Exception as e:
            logger.warning(f"  LLM attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise


# Import the prompts and field names from extract.py
from app.extract import EXTRACTOR_A_SYSTEM, EXTRACTOR_B_SYSTEM, FIELD_NAMES


def run_extractor_a_sync(api_key: str, model: str, chunks: list, pages: list) -> list:
    """Synchronous extractor A - chunk by chunk."""
    all_claims = []
    for i, chunk in enumerate(chunks):
        try:
            logger.info(f"  Extractor A: chunk {i+1}/{len(chunks)}")
            result = llm_call(
                api_key, model,
                EXTRACTOR_A_SYSTEM,
                f"Contract section (pages {chunk.get('pages', '?')}):\n\n"
                f"{chunk['text']}\n\n"
                f"Extract these fields if present: {', '.join(FIELD_NAMES)}"
            )
            for field in result.get("fields", []):
                all_claims.append({
                    "agent_id": "extractor_a",
                    "field_name": field.get("field_name", ""),
                    "status": field.get("status", "CANNOT_ASSESS"),
                    "value": field.get("value"),
                    "verbatim_quote": field.get("verbatim_quote"),
                    "quote_page": field.get("page"),
                })
        except Exception as e:
            logger.warning(f"  Extractor A chunk {i+1} failed: {e}")
    return all_claims


def run_extractor_b_sync(api_key: str, model: str, full_text: str, pages: list) -> list:
    """Synchronous extractor B - full document."""
    max_chars = 30000
    text_input = full_text[:max_chars]
    if len(full_text) > max_chars:
        text_input += f"\n\n[...truncated, {len(full_text) - max_chars} chars omitted...]"

    try:
        logger.info(f"  Extractor B: full document ({len(text_input)} chars)")
        result = llm_call(
            api_key, model,
            EXTRACTOR_B_SYSTEM,
            f"Full contract text:\n\n{text_input}\n\n"
            f"Extract ALL of these fields: {', '.join(FIELD_NAMES)}\n"
            f"For every field, report FOUND, ABSENT, or CANNOT_ASSESS."
        )
        claims = []
        for field in result.get("fields", []):
            claims.append({
                "agent_id": "extractor_b",
                "field_name": field.get("field_name", ""),
                "status": field.get("status", "CANNOT_ASSESS"),
                "value": field.get("value"),
                "verbatim_quote": field.get("verbatim_quote"),
                "quote_page": field.get("page"),
            })
        return claims
    except Exception as e:
        logger.warning(f"  Extractor B failed: {e}")
        return [{
            "agent_id": "extractor_b",
            "field_name": fn,
            "status": "CANNOT_ASSESS",
            "value": None, "verbatim_quote": None, "quote_page": None,
        } for fn in FIELD_NAMES]


def run_pipeline_on_file(filepath: str, api_key: str, model: str) -> dict:
    """Run full pipeline on a single file. Fully synchronous."""
    filename = os.path.basename(filepath)
    logger.info(f"Processing: {filename}")

    try:
        doc_data = ingest_file(filepath)
        logger.info(f"  Ingested: {len(doc_data.get('pages', []))} pages, {len(doc_data.get('full_text', ''))} chars")

        claims_a = run_extractor_a_sync(api_key, model, doc_data.get("chunks", []), doc_data.get("pages", []))
        claims_b = run_extractor_b_sync(api_key, model, doc_data.get("full_text", ""), doc_data.get("pages", []))
        raw_claims = claims_a + claims_b
        logger.info(f"  Extracted: {len(raw_claims)} raw claims")

        resolved_fields = verify_and_resolve(raw_claims, doc_data["pages"])
        logger.info(f"  Resolved: {len(resolved_fields)} fields")

        tiers = {}
        for f in resolved_fields:
            t = f.get("confidence", "UNGROUNDED")
            tiers[t] = tiers.get(t, 0) + 1
        logger.info(f"  Tiers: {tiers}")

        return {
            "filename": filename, "status": "ok",
            "fields": resolved_fields,
            "pages": doc_data.get("pages", []),
            "is_scanned": doc_data.get("is_scanned", False),
            "tiers": tiers,
        }
    except Exception as e:
        logger.error(f"  FAILED: {e}")
        return {
            "filename": filename, "status": "error",
            "error": str(e), "fields": [], "pages": [], "tiers": {},
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default="corpus/")
    parser.add_argument("--output", default=".")
    parser.add_argument("--model", default="deepseek/deepseek-v4-flash-0731")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("ERROR: Set $env:OPENROUTER_API_KEY first")
        sys.exit(1)

    corpus_path = Path(args.corpus)
    pdf_files = sorted(
        [str(p) for p in corpus_path.glob("*.pdf")]
        + [str(p) for p in corpus_path.glob("*.docx")]
        + [str(p) for p in corpus_path.glob("*.pptx")]
    )

    if not pdf_files:
        print(f"ERROR: No files found in {corpus_path}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  AITHENA Calibration Run")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Corpus: {len(pdf_files)} files in {corpus_path}")
    print(f"  Model: {args.model}")
    print(f"{'='*60}\n")

    processed = {}
    total_tiers = {"VERIFIED": 0, "INFERRED": 0, "CONTESTED": 0, "UNGROUNDED": 0}
    ok_count = 0
    fail_count = 0

    for filepath in pdf_files:
        result = run_pipeline_on_file(filepath, api_key, args.model)
        processed[result["filename"]] = result
        if result["status"] == "ok":
            ok_count += 1
            for tier, count in result.get("tiers", {}).items():
                total_tiers[tier] = total_tiers.get(tier, 0) + count
        else:
            fail_count += 1

    results_path = os.path.join(args.output, "results.csv")
    coverage_path = os.path.join(args.output, "coverage.csv")
    export_results_csv(processed, results_path)
    export_coverage_csv(processed, coverage_path)

    total_fields = sum(total_tiers.values())

    print(f"\n{'='*60}")
    print(f"  CALIBRATION RESULTS")
    print(f"{'='*60}")
    print(f"  Documents processed: {ok_count}")
    print(f"  Documents failed:    {fail_count}")
    print(f"  Total fields:        {total_fields}")
    print()
    print("  Confidence Distribution:")
    print("  " + "-" * 40)
    for tier in ["VERIFIED", "INFERRED", "CONTESTED", "UNGROUNDED"]:
        count = total_tiers.get(tier, 0)
        pct = (count / total_fields * 100) if total_fields > 0 else 0
        bar = "#" * int(pct / 2)
        print(f"  {tier:12s}  {count:4d}  ({pct:5.1f}%)  {bar}")

    print()
    verified = total_tiers.get("VERIFIED", 0)
    if verified > 0:
        print(f"  >>> VERIFIED-tier fields: {verified}")
        print(f"  >>> For the pitch: 'High-confidence fields account for")
        print(f"      {verified} of {total_fields} extracted values across {ok_count} contracts.'")
    else:
        print("  >>> WARNING: No VERIFIED fields. Check extraction quality.")

    print(f"\n  Exported: {results_path}")
    print(f"  Exported: {coverage_path}")
    print()


if __name__ == "__main__":
    main()
