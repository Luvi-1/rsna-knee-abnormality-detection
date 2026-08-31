from __future__ import annotations

import json
import pickle
import zipfile
from pathlib import Path

import pytest

from rsna_knee.public_repro import (
    AssetRecord,
    CandidateRecord,
    ClaimBoundary,
    ContractError,
    InferenceClassification,
    LicenseClassification,
    ScoreType,
    load_registry,
    select_highest_eligible,
)
from rsna_knee.public_repro.checkpoint_security import inspect_checkpoint_archive


GOOD_SHA = "a" * 64


def asset(**overrides: object) -> AssetRecord:
    values: dict[str, object] = {
        "resource": "owner/dataset:file.pt",
        "version": "1",
        "sha256": GOOD_SHA,
        "public": True,
        "available": True,
        "license_classification": LicenseClassification.PERMITS_COMPETITION_INFERENCE,
        "inference_required": True,
        "safe_load": True,
        "exact_binding": True,
        "notes": "",
    }
    values.update(overrides)
    return AssetRecord(**values)  # type: ignore[arg-type]


def candidate(**overrides: object) -> CandidateRecord:
    values: dict[str, object] = {
        "candidate_id": "candidate",
        "owner_slug": "owner/notebook",
        "version": 1,
        "script_version_id": 123,
        "source_score": 0.92,
        "score_type": ScoreType.SOURCE_REPORTED_PUBLIC_LB,
        "runtime_seconds": 100.0,
        "source_sha256": GOOD_SHA,
        "output_sha256": "b" * 64,
        "saved_version": True,
        "public_access": True,
        "exact_output_available": True,
        "dynamic_test_discovery": True,
        "accesses_test_reports": False,
        "calls_submission_api": False,
        "training_lineage_complete": False,
        "source_url": "https://www.kaggle.com/code/owner/notebook",
        "captured_at": "2026-08-31T00:00:00Z",
        "assets": (asset(),),
        "notes": "",
    }
    values.update(overrides)
    result = CandidateRecord(**values)  # type: ignore[arg-type]
    result.validate()
    return result


def test_training_opaque_can_be_inference_reproducible() -> None:
    item = candidate()
    assert (
        item.classification()
        is InferenceClassification.INFERENCE_REPRODUCIBLE_TRAINING_OPAQUE
    )
    assert item.eligible_for_private_reproduction()


def test_complete_training_lineage_gets_stronger_class() -> None:
    item = candidate(training_lineage_complete=True)
    assert (
        item.classification()
        is InferenceClassification.INFERENCE_AND_TRAINING_REPRODUCIBLE
    )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("public_access", False, InferenceClassification.SOURCE_UNAVAILABLE),
        ("saved_version", False, InferenceClassification.INFERENCE_BLOCKED),
        ("script_version_id", None, InferenceClassification.INFERENCE_BLOCKED),
        ("source_sha256", None, InferenceClassification.INFERENCE_BLOCKED),
        ("dynamic_test_discovery", False, InferenceClassification.INFERENCE_BLOCKED),
        ("accesses_test_reports", True, InferenceClassification.INFERENCE_BLOCKED),
        ("calls_submission_api", True, InferenceClassification.INFERENCE_BLOCKED),
    ],
)
def test_candidate_blockers(
    field: str, value: object, expected: InferenceClassification
) -> None:
    item = candidate(**{field: value})
    assert item.classification() is expected


@pytest.mark.parametrize(
    "broken_asset",
    [
        asset(public=False),
        asset(available=False),
        asset(version=None),
        asset(sha256=None),
        asset(exact_binding=False),
        asset(safe_load=False),
        asset(license_classification=LicenseClassification.NO_ACTIONABLE_LICENSE),
    ],
)
def test_indispensable_asset_blocks_inference(broken_asset: AssetRecord) -> None:
    item = candidate(assets=(broken_asset,))
    assert item.classification() is InferenceClassification.INFERENCE_BLOCKED


def test_training_only_asset_does_not_block_inference() -> None:
    opaque_training_label = asset(
        resource="owner/labels:oof.npz",
        inference_required=False,
        public=False,
        available=False,
        version=None,
        sha256=None,
        safe_load=False,
        exact_binding=False,
        license_classification=LicenseClassification.NO_ACTIONABLE_LICENSE,
    )
    item = candidate(assets=(asset(), opaque_training_label))
    assert item.classification() is InferenceClassification.INFERENCE_REPRODUCIBLE_TRAINING_OPAQUE


def test_selects_highest_score_then_fastest() -> None:
    lower = candidate(candidate_id="lower", source_score=0.91, runtime_seconds=50.0)
    high_slow = candidate(candidate_id="high-slow", source_score=0.93, runtime_seconds=150.0)
    high_fast = candidate(candidate_id="high-fast", source_score=0.93, runtime_seconds=90.0)
    selected = select_highest_eligible([lower, high_slow, high_fast])
    assert selected is not None
    assert selected.candidate_id == "high-fast"


def test_blocked_high_score_does_not_beat_safe_lower_score() -> None:
    blocked = candidate(
        candidate_id="blocked",
        source_score=0.936,
        assets=(asset(license_classification=LicenseClassification.UNVERIFIED),),
    )
    safe = candidate(candidate_id="safe", source_score=0.920)
    selected = select_highest_eligible([blocked, safe])
    assert selected is not None
    assert selected.candidate_id == "safe"


def test_source_score_claim_boundary() -> None:
    claim = ClaimBoundary(
        owner_slug="owner/notebook",
        source_score=0.936,
        source_score_type=ScoreType.SOURCE_REPORTED_PUBLIC_LB,
        project_submission_performed=False,
    )
    text = claim.summary()
    assert "source-reported" in text
    assert "has not independently submitted or achieved" in text


def test_project_score_without_submission_is_rejected() -> None:
    claim = ClaimBoundary(
        owner_slug="owner/notebook",
        source_score=0.936,
        source_score_type=ScoreType.SOURCE_REPORTED_PUBLIC_LB,
        project_submission_performed=False,
        project_public_score=0.93,
    )
    with pytest.raises(ContractError):
        claim.validate()


def test_registry_rejects_duplicate_ids(tmp_path: Path) -> None:
    raw_candidate = {
        "candidate_id": "same",
        "owner_slug": "owner/notebook",
        "version": 1,
        "script_version_id": 1,
        "source_score": 0.92,
        "score_type": "SOURCE_REPORTED_PUBLIC_LB",
        "runtime_seconds": 1.0,
        "source_sha256": GOOD_SHA,
        "output_sha256": "b" * 64,
        "saved_version": True,
        "public_access": True,
        "exact_output_available": True,
        "dynamic_test_discovery": True,
        "accesses_test_reports": False,
        "calls_submission_api": False,
        "training_lineage_complete": False,
        "source_url": "https://www.kaggle.com/code/owner/notebook",
        "captured_at": "2026-08-31T00:00:00Z",
        "assets": [
            {
                "resource": "owner/data:file.pt",
                "version": "1",
                "sha256": GOOD_SHA,
                "public": True,
                "available": True,
                "license_classification": "PERMITS_COMPETITION_INFERENCE",
                "inference_required": True,
                "safe_load": True,
                "exact_binding": True,
            }
        ],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"candidates": [raw_candidate, raw_candidate]}))
    with pytest.raises(ContractError, match="unique"):
        load_registry(path)


def test_non_zip_checkpoint_requires_sandbox(tmp_path: Path) -> None:
    path = tmp_path / "weights.pt"
    path.write_bytes(b"not a zip checkpoint")
    result = inspect_checkpoint_archive(path)
    assert not result.is_zip
    assert result.requires_sandbox


def test_zip_path_traversal_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "weights.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../escape.bin", b"x")
    result = inspect_checkpoint_archive(path)
    assert result.path_traversal_members == ("../escape.bin",)
    assert result.requires_sandbox


def test_pickle_checkpoint_requires_sandbox(tmp_path: Path) -> None:
    path = tmp_path / "weights.zip"
    payload = pickle.dumps({"value": set([1, 2, 3])})
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("archive/data.pkl", payload)
    result = inspect_checkpoint_archive(path)
    assert result.pickle_members == ("archive/data.pkl",)
    assert result.requires_sandbox


def test_tensor_only_zip_without_pickle_can_pass_static_archive_checks(tmp_path: Path) -> None:
    path = tmp_path / "weights.safetensors.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("model.safetensors", b"synthetic")
    result = inspect_checkpoint_archive(path)
    assert result.is_zip
    assert not result.path_traversal_members
    assert not result.pickle_members
    assert not result.requires_sandbox
