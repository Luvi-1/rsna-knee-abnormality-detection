#!/usr/bin/env python3
"""Freeze gate for weak-labels-v1: provenance + precision checks on reviewed queue.

Reads the privacy-scanned weak_labels_v1_summary.json and the completed local
review worksheet (hashed keys only), then emits a freeze record only when both
gates pass. Never reads report text.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

VALID_DECISIONS = {"POSITIVE", "EXPLICIT_NEGATIVE", "UNCERTAIN", "NOT_MENTIONED"}
RULE_TO_EXPECTED = {
    "positive": "POSITIVE",
    "negative": "EXPLICIT_NEGATIVE",
    "uncertain": "UNCERTAIN",
}
MIN_QUEUE_ROWS = 80
MIN_PRECISION = 0.80


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_provenance(summary: dict) -> tuple[bool, list[str]]:
    problems: list[str] = []
    if summary.get("gate") != "weak-labels-v1":
        problems.append("gate_identity_invalid")
    if not summary.get("artifact_inventory_digest_sha256"):
        problems.append("inventory_digest_missing")
    queue = summary.get("human_review_queue", {}).get("rows", [])
    if len(queue) < MIN_QUEUE_ROWS:
        problems.append("queue_rows_insufficient")
    for row_number, row in enumerate(queue, start=1):
        key = row.get("study_key_sha256", "")
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            problems.append(f"row_{row_number}_key_invalid")
        if row.get("confidence") is None or not 0.0 <= float(row["confidence"]) <= 1.0:
            problems.append(f"row_{row_number}_confidence_invalid")
        if not row.get("target") or not row.get("language"):
            problems.append(f"row_{row_number}_fields_missing")
    if summary.get("empty_reports") != 0:
        problems.append("empty_reports_nonzero")
    return (not problems, problems)


def check_precision(summary: dict, worksheet_path: Path) -> tuple[bool, dict]:
    queue = summary.get("human_review_queue", {}).get("rows", [])
    with worksheet_path.open(newline="") as handle:
        reviewed = {int(r["row_id"]): r for r in csv.DictReader(handle)}
    matched = correct = 0
    per_target: dict[str, dict[str, int]] = {}
    undecided: list[int] = []
    for row_number, row in enumerate(queue, start=1):
        entry = reviewed.get(row_number)
        decision = (entry or {}).get("reviewer_decision", "").strip().upper()
        if not decision:
            undecided.append(row_number)
            continue
        if decision not in VALID_DECISIONS:
            raise SystemExit(f"invalid_decision_row_{row_number}")
        expected = RULE_TO_EXPECTED.get(row["state_before_mask"])
        stats = per_target.setdefault(row["target"], {"n": 0, "correct": 0})
        stats["n"] += 1
        matched += 1
        if decision == expected:
            correct += 1
            stats["correct"] += 1
    precision = round(correct / matched, 4) if matched else 0.0
    result = {
        "rows_total": len(queue),
        "rows_decided": matched,
        "undecided_rows": undecided[:10],
        "precision_pooled": precision,
        "per_target": per_target,
    }
    passed = matched == len(queue) and precision >= MIN_PRECISION
    return passed, result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--worksheet", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text())
    provenance_ok, provenance_problems = check_provenance(summary)
    precision_ok, precision_result = check_precision(summary, args.worksheet)
    freeze_record = {
        "schema_version": 1,
        "frozen": bool(provenance_ok and precision_ok),
        "supervision_version": "weak-labels-v1",
        "summary_sha256": _sha256_file(args.summary),
        "worksheet_sha256": _sha256_file(args.worksheet),
        "provenance_pass": provenance_ok,
        "provenance_problems": provenance_problems[:20],
        "precision": precision_result,
        "min_precision": MIN_PRECISION,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(freeze_record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"frozen": freeze_record["frozen"], "provenance_pass": provenance_ok,
                      "precision_pass": precision_ok}))
    return 0 if freeze_record["frozen"] else 2


if __name__ == "__main__":
    sys.exit(main())
