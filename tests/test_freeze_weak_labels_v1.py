from __future__ import annotations

import csv
import json
import subprocess
import sys

import pytest

from scripts.freeze_weak_labels_v1 import check_precision, check_provenance


def _queue_row(n: int) -> dict:
    key = f"{n:064x}"
    return {
        "study_key_sha256": key,
        "confidence": 1.0,
        "target": "Fracture",
        "language": "en",
        "state_before_mask": "positive",
    }


def _summary() -> dict:
    return {
        "gate": "weak-labels-v1",
        "artifact_inventory_digest_sha256": "a" * 64,
        "empty_reports": 0,
        "human_review_queue": {"rows": [_queue_row(i) for i in range(1, 81)]},
    }


def _worksheet(tmp_path, decisions):
    path = tmp_path / "ws.csv"
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["row_id", "reviewer_decision"])
        writer.writeheader()
        for i, d in enumerate(decisions, start=1):
            writer.writerow({"row_id": i, "reviewer_decision": d})
    return path


def test_full_pass(tmp_path):
    summary = _summary()
    ok, problems = check_provenance(summary)
    assert ok and not problems
    ws = _worksheet(tmp_path, ["POSITIVE"] * 80)
    passed, result = check_precision(summary, ws)
    assert passed
    assert result["precision_pooled"] == 1.0


def test_undecided_row_fails(tmp_path):
    summary = _summary()
    decisions = ["POSITIVE"] * 79 + [""]
    passed, result = check_precision(summary, _worksheet(tmp_path, decisions))
    assert not passed
    assert result["undecided_rows"] == [80]


def test_low_precision_fails(tmp_path):
    summary = _summary()
    decisions = ["POSITIVE"] * 63 + ["NOT_MENTIONED"] * 17
    passed, result = check_precision(summary, _worksheet(tmp_path, decisions))
    assert not passed
    assert result["precision_pooled"] < 0.80


def test_provenance_rejects_bad_identity():
    summary = _summary()
    summary["gate"] = "wrong"
    summary["empty_reports"] = 3
    summary["artifact_inventory_digest_sha256"] = ""
    ok, problems = check_provenance(summary)
    assert not ok
    assert set(problems) >= {
        "gate_identity_invalid", "inventory_digest_missing", "empty_reports_nonzero"}


def test_cli_end_to_end(tmp_path):
    summary_path = tmp_path / "s.json"
    summary_path.write_text(json.dumps(_summary()))
    ws = _worksheet(tmp_path, ["POSITIVE"] * 80)
    out = tmp_path / "freeze.json"
    proc = subprocess.run(
        [sys.executable, "scripts/freeze_weak_labels_v1.py", "--summary", str(summary_path),
         "--worksheet", str(ws), "--out", str(out)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    record = json.loads(out.read_text())
    assert record["frozen"] is True


if __name__ == "__main__":
    pytest.main([__file__])
