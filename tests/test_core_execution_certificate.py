from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


certifier = _load("_core_certifier", ROOT / "scripts/certify_dicom_qa_core.py")

CHAIN_AUDIT_ID = "preprocess-0001-dicom-pipeline-r15"
FREEZE_COMMIT = "d3771e7ffb7f8674c5162749f0aba8b7a7f95cdf"
BUNDLE_SHA256 = "61963849d8ec6c5977f423a0dc161855a1aa158322961a5eaaa380fb7a4ddab0"
EXPECTED_REFS = {
    "performance_smoke": ("lavicheema/rsna-knee-dqa-smoke-d3771e7-61963849d8ec"),
    "run_a": "lavicheema/rsna-knee-dqa-a-d3771e7-61963849d8ec",
    "run_b": "lavicheema/rsna-knee-dqa-b-d3771e7-61963849d8ec",
    "comparison": "lavicheema/rsna-knee-dqa-cmp-d3771e7-61963849d8ec",
}
NOW = "2026-08-22T20:00:00Z"


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _run_summary() -> bytes:
    return _canonical(
        {
            "schema_version": 1,
            "artifact_type": "dicom-qa-sanitized-core-aggregate",
            "status": "complete_pending_comparison",
            "provenance": {
                "git_commit": FREEZE_COMMIT,
                "bundle_sha256": BUNDLE_SHA256,
                "runner_sha256": "5b71cbc3e36f862c41edfe93e55186bc46ed541b418de0c7325238b315b8bf4a",
            },
            "pipeline": {
                "all_series_terminal": True,
                "full_training_dataset_processed": True,
                "integrity_gate": "pass",
                "unresolved_blockers": "zero",
            },
            "privacy": {
                "downloaded_case_details": False,
                "downloaded_identifiers": False,
                "downloaded_paths": False,
                "downloaded_pixels": False,
                "private_cohort_plan_remote_only": True,
            },
        }
    )


def _comparison_proof() -> bytes:
    # The comparison producer emits its canonical JSON with one trailing newline.
    return (
        _canonical(
            {
                "artifact_type": "dicom-run-determinism-aggregate",
                "cohort_plan_byte_equality": True,
                "deterministic_metrics_equal": True,
                "exact_manifest_byte_equality": True,
                "independent_runs_compared": True,
                "private_case_details_downloaded": False,
                "schema_version": 1,
                "status": "pass",
                "unresolved_mismatches": "zero",
            }
        )
        + b"\n"
    )


def _fake_fetch(reference: str, pattern: str, maximum: int) -> bytes:
    del maximum
    if EXPECTED_REFS["run_a"] == reference or reference.endswith("/dicom-qa-output"):
        pass
    if EXPECTED_REFS["run_a"] in reference:
        return _run_summary()
    if EXPECTED_REFS["run_b"] in reference:
        return _run_summary()
    if EXPECTED_REFS["comparison"] in reference:
        return _comparison_proof()
    raise AssertionError(f"unexpected reference {reference} pattern {pattern}")


@pytest.fixture()
def certificate(tmp_path: Path) -> Iterator[SimpleNamespace]:
    seen_refs: list[str] = []

    def authenticate(chain_audit_id: str) -> None:
        assert chain_audit_id == CHAIN_AUDIT_ID
        seen_refs.append(chain_audit_id)

    payload = certifier.build_certificate(
        repo_root=ROOT,
        chain_audit_id=CHAIN_AUDIT_ID,
        fetch=_fake_fetch,
        live_authenticate=authenticate,
        now=NOW,
    )
    yield SimpleNamespace(value=payload, seen_refs=seen_refs, tmp_path=tmp_path)


def _registry_fixture(tmp_path: Path, *, mutate: Any = None) -> Path:
    source = sqlite3.connect(f"file:{ROOT / 'artifacts/experiments.sqlite3'}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        row = dict(
            source.execute(
                "SELECT * FROM audit_runs WHERE audit_id = ?", (CHAIN_AUDIT_ID,)
            ).fetchone()
        )
        ddl_row = source.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='audit_runs'"
        ).fetchone()
    finally:
        source.close()
    if mutate is not None:
        mutate(row)
    target_path = tmp_path / "experiments.sqlite3"
    target = sqlite3.connect(target_path)
    try:
        target.execute(str(ddl_row[0]))
        target.execute(
            "INSERT INTO audit_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(
                row[column]
                for column in (
                    "audit_id",
                    "audit_kind",
                    "status",
                    "scope_json",
                    "code_version",
                    "config_hash",
                    "input_version",
                    "manifest_version",
                    "result_json",
                    "created_utc",
                    "completed_utc",
                )
            ),
        )
        target.commit()
    finally:
        target.close()
    return target_path


def test_certificate_roundtrip_binds_expected_identity(certificate: SimpleNamespace) -> None:
    payload = certificate.value
    certifier.verify_certificate(copy.deepcopy(payload))
    assert payload["certificate_type"] == "rsna-knee-core-execution-certificate-v1"
    assert payload["core_status"] == "passed"
    assert payload["qa_adapter_status"] == "not_passed"
    assert payload["human_review_status"] == "not_started"
    assert payload["freeze_commit_sha256"] == FREEZE_COMMIT
    assert payload["bundle_sha256"] == BUNDLE_SHA256
    assert payload["bundle_dataset_ref"] == (
        "lavicheema/rsna-knee-dicom-qa-bundle-d3771e7-61963849d8ec"
    )
    stages = payload["stages"]
    for role in ("performance_smoke", "run_a", "run_b", "comparison"):
        assert stages[role]["kernel_ref"] == EXPECTED_REFS[role]
        assert stages[role]["kernel_version"] == 1
        assert stages[role]["status"] == "passed"
    assert stages["run_a"]["output_sha256"] == hashlib.sha256(_run_summary()).hexdigest()
    assert stages["run_b"]["output_sha256"] == hashlib.sha256(_run_summary()).hexdigest()
    assert stages["comparison"]["result_sha256"] == hashlib.sha256(_comparison_proof()).hexdigest()
    assert stages["inputs"]["input_identity_sha256"] == (
        "6abe1773fa757e8650e66e425122932ed35e113e2253b33a6c78e9fe677a1c12"
    )
    assert payload["source_input_snapshot"]["manifest_bundle_sha256"] == (
        "64a7ae0408879a2d3705664f9190f7a0ba97d28df5784858b6d0d530bf3a7eeb"
    )
    assert payload["preprocessing"]["version"] == "dicom-model-v1"
    assert certificate.seen_refs == [CHAIN_AUDIT_ID]


def _bound_paths() -> list[tuple[Any, ...]]:
    paths: list[tuple[Any, ...]] = [("core_lineage_id",), ("freeze_commit_sha256",)]
    for name in ("inputs", "performance_smoke", "run_a", "run_b", "comparison"):
        paths.append(("stages", name))
    paths += [
        ("stages", "run_a", "kernel_version"),
        ("stages", "run_a", "output_sha256"),
        ("stages", "comparison", "result_sha256"),
        ("stages", "inputs", "input_identity_sha256"),
        ("source_input_snapshot",),
        ("preprocessing",),
        ("qa_registry_membership",),
    ]
    return paths


def test_certificate_rejects_any_bound_field_change(certificate: SimpleNamespace) -> None:
    for path in _bound_paths():
        tampered = copy.deepcopy(certificate.value)
        target: Any = tampered
        for key in path[:-1]:
            target = target[key]
        original = target[path[-1]]
        if path[-1] == "freeze_commit_sha256":
            target[path[-1]] = "f" * 40  # valid shape, different identity
        else:
            target[path[-1]] = 999 if isinstance(original, int) else {"tampered": True}
        with pytest.raises(
            certifier.CertificateError,
            match=r"certificate_(digest_mismatch|field_invalid|stage_not_passed)",
        ):
            certifier.verify_certificate(tampered)


def test_certificate_verify_detects_status_flip(certificate: SimpleNamespace) -> None:
    tampered = copy.deepcopy(certificate.value)
    tampered["certificate_payload_sha256"] = hashlib.sha256(b"other").hexdigest()
    with pytest.raises(certifier.CertificateError, match="certificate_digest_mismatch"):
        certifier.verify_certificate(tampered)
    flipped = copy.deepcopy(certificate.value)
    flipped["human_review_status"] = "passed"
    with pytest.raises(certifier.CertificateError, match="certificate_status_invalid"):
        certifier.verify_certificate(flipped)


def test_missing_registry_row_fails_closed(tmp_path: Path) -> None:
    registry_path = _registry_fixture(tmp_path)
    with pytest.raises(certifier.CertificateError, match="registry_row_missing"):
        certifier.build_certificate(
            repo_root=ROOT,
            chain_audit_id="preprocess-0001-dicom-pipeline-r99",
            registry_path=registry_path,
            fetch=_fake_fetch,
            live_authenticate=lambda chain: None,
            now=NOW,
        )


def test_non_reusable_failure_shape_is_rejected(tmp_path: Path) -> None:
    def mutate(row: dict[str, Any]) -> None:
        result = json.loads(str(row["result_json"]))
        result["comparison"] = "failed"
        row["result_json"] = json.dumps(result)

    registry_path = _registry_fixture(tmp_path, mutate=mutate)
    with pytest.raises(certifier.CertificateError, match="registry_stage_not_passed_comparison"):
        certifier.build_certificate(
            repo_root=ROOT,
            chain_audit_id=CHAIN_AUDIT_ID,
            registry_path=registry_path,
            fetch=_fake_fetch,
            live_authenticate=lambda chain: None,
            now=NOW,
        )


def test_tampered_run_summary_is_rejected(certificate: SimpleNamespace) -> None:
    def fetch(reference: str, pattern: str, maximum: int) -> bytes:
        payload = _fake_fetch(reference, pattern, maximum)
        if EXPECTED_REFS["run_a"] in reference:
            summary = json.loads(payload)
            summary["pipeline"]["unresolved_blockers"] = "one"
            return _canonical(summary)
        return payload

    with pytest.raises(certifier.CertificateError, match="run_summary_pipeline_invalid"):
        certifier.build_certificate(
            repo_root=ROOT,
            chain_audit_id=CHAIN_AUDIT_ID,
            fetch=fetch,
            live_authenticate=lambda chain: None,
            now=NOW,
        )


def test_tampered_comparison_proof_is_rejected(certificate: SimpleNamespace) -> None:
    def fetch(reference: str, pattern: str, maximum: int) -> bytes:
        payload = _fake_fetch(reference, pattern, maximum)
        if EXPECTED_REFS["comparison"] in reference:
            proof = json.loads(payload)
            proof["cohort_plan_byte_equality"] = False
            return _canonical(proof)
        return payload

    with pytest.raises(certifier.CertificateError, match="comparison_proof_invalid"):
        certifier.build_certificate(
            repo_root=ROOT,
            chain_audit_id=CHAIN_AUDIT_ID,
            fetch=fetch,
            live_authenticate=lambda chain: None,
            now=NOW,
        )
