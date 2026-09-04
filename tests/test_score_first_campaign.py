from __future__ import annotations

import json
from pathlib import Path

import pytest

from rsna_knee.public_repro.score_first import (
    ScoreFirstError,
    collect_pull_evidence,
    load_campaign,
    parse_kaggle_kernel_csv,
    prioritized_campaign,
    scan_notebook_source,
    sha256_file,
    shortlist_listings,
)


def test_parse_kaggle_csv_and_shortlist() -> None:
    text = (
        "ref,title,score,runtimeSeconds,version\n"
        "owner/high,High,0.936,165,36\n"
        "owner/low,Low,0.924,53,1\n"
    )
    rows = parse_kaggle_kernel_csv(text)
    assert len(rows) == 2
    assert rows[0].owner_slug == "owner/high"
    assert rows[0].score == pytest.approx(0.936)
    assert rows[0].runtime_seconds == pytest.approx(165.0)
    assert rows[0].version == 36
    selected = shortlist_listings(rows, minimum_score=0.93)
    assert [item.ref for item in selected] == ["owner/high"]


def test_parse_csv_tolerates_missing_optional_fields() -> None:
    rows = parse_kaggle_kernel_csv("ref,title\nowner/notebook,Notebook\n")
    assert rows[0].score is None
    assert rows[0].runtime_seconds is None
    assert rows[0].version is None


def test_parse_csv_requires_ref() -> None:
    with pytest.raises(ScoreFirstError, match="missing a ref"):
        parse_kaggle_kernel_csv("title,score\nNo ref,0.936\n")


def test_shortlist_validates_threshold() -> None:
    with pytest.raises(ScoreFirstError, match="within"):
        shortlist_listings((), minimum_score=1.1)


def test_source_audit_detects_blockers() -> None:
    source = """
# [Private Dataset]
client.competitions.submit(file_name='submission.csv')
model = torch.load('weights.pt', weights_only=False)
test = pd.read_csv('/input/test.csv')
reports = test_df['Report']
for row in test[:3]:
    pass
StudyInstanceUID = test['StudyInstanceUID']
"""
    audit = scan_notebook_source(source)
    assert audit.private_input_markers >= 1
    assert audit.submission_api_calls >= 1
    assert audit.test_report_accesses >= 1
    assert audit.unsafe_torch_loads == 1
    assert audit.hardcoded_three_markers >= 1
    assert "private_input_marker" in audit.blocking_reasons
    assert "unsafe_torch_load" in audit.blocking_reasons


def test_source_audit_accepts_safe_load_and_dynamic_test() -> None:
    source = """
model = torch.load('weights.pt', weights_only=True)
test = pd.read_csv('/input/test.csv')
ids = test['StudyInstanceUID']
"""
    audit = scan_notebook_source(source)
    assert audit.safe_torch_loads == 1
    assert audit.unsafe_torch_loads == 0
    assert audit.dynamic_test_evidence
    assert not audit.blocking_reasons


def test_campaign_load_and_priority(tmp_path: Path) -> None:
    payload = {
        "candidates": [
            {
                "candidate_id": "second",
                "owner_slug": "owner/second",
                "required_version": 1,
                "script_version_id": None,
                "source_reported_public_score": 0.936,
                "priority": 2,
                "status": "PIN_REQUIRED",
                "reason": "test",
            },
            {
                "candidate_id": "first",
                "owner_slug": "owner/first",
                "required_version": 1,
                "script_version_id": 10,
                "source_reported_public_score": 0.933,
                "priority": 1,
                "status": "PIN_REQUIRED",
                "reason": "test",
            },
        ]
    }
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    candidates = load_campaign(path)
    ordered = prioritized_campaign(candidates)
    assert [item.candidate_id for item in ordered] == ["first", "second"]


def test_campaign_rejects_duplicate_ids(tmp_path: Path) -> None:
    row = {
        "candidate_id": "same",
        "owner_slug": "owner/notebook",
        "required_version": 1,
        "script_version_id": None,
        "source_reported_public_score": 0.936,
        "priority": 1,
        "status": "PIN_REQUIRED",
        "reason": "test",
    }
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps({"candidates": [row, row]}), encoding="utf-8")
    with pytest.raises(ScoreFirstError, match="unique"):
        load_campaign(path)


def test_campaign_rejects_bad_slug(tmp_path: Path) -> None:
    row = {
        "candidate_id": "bad",
        "owner_slug": "missing-owner-separator",
        "required_version": 1,
        "script_version_id": None,
        "source_reported_public_score": 0.936,
        "priority": 1,
        "status": "PIN_REQUIRED",
        "reason": "test",
    }
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps({"candidates": [row]}), encoding="utf-8")
    with pytest.raises(ScoreFirstError, match="owner/slug"):
        load_campaign(path)


def test_collect_pull_evidence_is_path_relative(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    output.mkdir()
    (source / "notebook.py").write_text(
        "test = pd.read_csv('test.csv')\nids = test['StudyInstanceUID']\n",
        encoding="utf-8",
    )
    (output / "predictions.csv").write_text("StudyInstanceUID,ACL\na,0.5\n")
    evidence = collect_pull_evidence("owner/notebook", source, output)
    payload = evidence.to_json()
    assert payload["source_root"] == "source"
    assert payload["source_files"][0]["path"] == "notebook.py"
    assert payload["output_files"][0]["path"] == "predictions.csv"
    assert str(tmp_path) not in json.dumps(payload)


def test_sha256_file_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "value.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"  # pragma: allowlist secret
    )
