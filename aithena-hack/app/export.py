# app/export.py
# CSV export for judges. One row per contract per field.
# The judges score field by field — if they must read our dashboard to score us,
# we lose on friction alone.

import csv
import io
import os
from datetime import datetime


def export_results_csv(processed_contracts: dict, output_path: str = "results.csv") -> str:
    """
    Export one row per contract per field.
    Columns match what judges need to score extraction accuracy + honesty.
    """
    fieldnames = [
        "contract_id",
        "field",
        "value_display",
        "status",
        "provenance",
        "confidence_band",
        "page",
        "quote",
        "quote_match_score",
        "extractor_a_raw",
        "extractor_b_raw",
        "adversary_note",
    ]

    rows = []
    for filename, contract in processed_contracts.items():
        fields = contract.get("fields", [])
        for f in fields:
            rows.append({
                "contract_id": filename,
                "field": f.get("field_name", ""),
                "value_display": f.get("value", ""),
                "status": "FOUND" if f.get("value") and f.get("value") != "NOT_FOUND" else (
                    "ABSENT" if f.get("value") == "NOT_FOUND" else "UNKNOWN"
                ),
                "provenance": f.get("provenance", "UNKNOWN"),
                "confidence_band": f.get("confidence", "UNGROUNDED"),
                "page": f.get("page", ""),
                "quote": f.get("verbatim_quote", ""),
                "quote_match_score": f.get("quote_match_score", ""),
                "extractor_a_raw": f.get("extractor_a_raw", ""),
                "extractor_b_raw": f.get("extractor_b_raw", ""),
                "adversary_note": f.get("adversary_note", ""),
            })

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return output_path


def export_coverage_csv(processed_contracts: dict, output_path: str = "coverage.csv") -> str:
    """
    One row per document: page count, scanned status, fields by confidence band.
    """
    fieldnames = [
        "contract_id",
        "pages",
        "is_scanned",
        "fields_verified",
        "fields_inferred",
        "fields_contested",
        "fields_ungrounded",
        "error",
    ]

    rows = []
    for filename, contract in processed_contracts.items():
        fields = contract.get("fields", [])
        tier_counts = {}
        for f in fields:
            tier = f.get("confidence", "UNGROUNDED")
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        rows.append({
            "contract_id": filename,
            "pages": len(contract.get("pages", [])),
            "is_scanned": contract.get("is_scanned", False),
            "fields_verified": tier_counts.get("VERIFIED", 0),
            "fields_inferred": tier_counts.get("INFERRED", 0),
            "fields_contested": tier_counts.get("CONTESTED", 0),
            "fields_ungrounded": tier_counts.get("UNGROUNDED", 0),
            "error": contract.get("error", ""),
        })

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return output_path
