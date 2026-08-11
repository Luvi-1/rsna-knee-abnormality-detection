from __future__ import annotations

import builtins
import copy
import hashlib
import importlib.util
import json
import sqlite3
import sys
import zipfile
from contextlib import contextmanager, nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REVIEW_DIMENSIONS = (
    "laterality",
    "organizer_plane",
    "physical_plane",
    "organizer_physical_plane_relation",
    "assigned_diagnostic_slot",
    "additional_diagnostic_series",
    "multiple_series_per_slot",
    "missing_diagnostic_slot",
    "retained_nonduplicate_abnormal_series",
    "duplicate_handling",
    "bit_depth_category",
    "photometric_interpretation",
    "transfer_syntax",
    "slice_thickness_stratum",
    "slice_spacing_stratum",
    "resolution_extreme",
    "slice_count_extreme",
    "scanner_manufacturer",
    "scanner_model",
    "field_strength",
    "site_domain_cluster",
    "source_manifest_quality_flag",
    "terminal_state",
    "pipeline_case",
    "dicom_edge_case_subtype",
)


def _load(name: str, path: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


sys.path.insert(0, str(ROOT / "scripts"))
try:
    packager = _load("_identity_packager", ROOT / "scripts/package_dicom_qa_bundle.py")
finally:
    sys.path.pop(0)
finalize_review = _load("_identity_finalizer", ROOT / "kaggle/dicom_qa/finalize_review.py")
review_ui = _load("_identity_review_ui", ROOT / "kaggle/dicom_qa/review_ui.py")


def _write_private(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(payload)
    path.chmod(0o600)


def _source_manifest_bundle(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "manifest-bundle"
    dataset = root / "dataset"
    kernel = root / "kernel"
    dataset.mkdir(parents=True, mode=0o700)
    kernel.mkdir(mode=0o700)
    root.chmod(0o700)
    runner = b"print('private manifest runner')\n"
    _write_private(kernel / "run.py", runner)
    schema_sha256 = hashlib.sha256((ROOT / "configs/manifest_schema.yaml").read_bytes()).hexdigest()
    source_commit = "2" * 40
    run_config = {
        "schema_version": 1,
        "code_commit": source_commit,
        "bundle_sha256": packager.RUN_CONFIG_BUNDLE_PLACEHOLDER,
        "provenance": {
            "manifest_version": packager.SOURCE_MANIFEST_VERSION,
            "manifest_schema_sha256": schema_sha256,
        },
        "output_policy": {
            "private_remote_only": [
                {
                    "path": "audit-output/private_manifest.sqlite3",
                    "max_bytes": 8 * 1024**3,
                },
                {"path": "audit-output/audit_key.bin", "max_bytes": 64, "exact_bytes": 32},
                {
                    "path": "audit-output/private_artifact_inventory.json",
                    "max_bytes": 1024**2,
                },
            ]
        },
    }
    normalized_payload = packager._canonical_json_bytes(run_config)
    normalized_record = {
        "path": "run-config.json",
        "role": "run_config",
        "source_path": "generated/run-config.json",
        "bytes": len(normalized_payload),
        "sha256": hashlib.sha256(normalized_payload).hexdigest(),
    }
    identity: dict[str, Any] = {
        "schema_version": 1,
        "bundle_format": "rsna-knee-manifest-audit-bundle-v1",
        "provenance": {
            "git_commit": source_commit,
            "git_commit_timestamp": 1_690_000_000,
        },
        "competition": {"slug": packager.COMPETITION_SLUG},
        "kernel": {
            "code_file": "run.py",
            "sha256": hashlib.sha256(runner).hexdigest(),
        },
        "files": [normalized_record],
    }
    bundle_sha256 = hashlib.sha256(packager._canonical_json_bytes(identity)).hexdigest()
    run_config["bundle_sha256"] = bundle_sha256
    run_payload = packager._canonical_json_bytes(run_config)
    _write_private(dataset / "run-config.json", run_payload)
    run_sha256 = hashlib.sha256(run_payload).hexdigest()
    manifest = {
        **identity,
        "bundle_sha256": bundle_sha256,
        "files": [{**normalized_record, "bytes": len(run_payload), "sha256": run_sha256}],
    }
    _write_private(dataset / "bundle-manifest.json", packager._canonical_json_bytes(manifest))
    dataset_ref = "test-owner/" + packager._derive_slug(
        "rsna-knee-manifest-bundle", source_commit, bundle_sha256
    )
    kernel_ref = "test-owner/" + packager._derive_slug(
        "rsna-knee-manifest-audit", source_commit, bundle_sha256
    )
    _write_private(
        dataset / "dataset-metadata.json",
        packager._canonical_json_bytes({"id": dataset_ref, "title": dataset_ref.partition("/")[2]}),
    )
    _write_private(
        kernel / "kernel-metadata.json",
        packager._canonical_json_bytes(
            {
                "id": kernel_ref,
                "code_file": "run.py",
                "is_private": True,
                "enable_internet": False,
                "dataset_sources": [dataset_ref],
                "competition_sources": [packager.COMPETITION_SLUG],
            }
        ),
    )

    registry = tmp_path / "registry.sqlite3"
    with sqlite3.connect(registry) as connection:
        connection.execute(
            "CREATE TABLE audit_runs("
            "audit_id TEXT,status TEXT,config_hash TEXT,manifest_version TEXT)"
        )
        connection.execute(
            "INSERT INTO audit_runs VALUES(?,?,?,?)",
            (
                packager.SOURCE_MANIFEST_AUDIT_ID,
                "completed",
                run_sha256,
                packager.SOURCE_MANIFEST_VERSION,
            ),
        )
    registry.chmod(0o600)
    return root, registry


def _project_wheel(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name in sorted(packager.REQUIRED_PROJECT_WHEEL_MEMBERS):
            archive.writestr(name, b"# fixture\n")


def _bundle_inputs(tmp_path: Path) -> dict[str, Any]:
    project_wheel = tmp_path / "rsna_knee-0.1.0-py3-none-any.whl"
    _project_wheel(project_wheel)
    dependencies = []
    for name in (
        "pillow-12.3.0-py3-none-any.whl",
        "pylibjpeg-2.1.0-py3-none-any.whl",
        "pylibjpeg_libjpeg-2.4.0-py3-none-any.whl",
        "pylibjpeg_openjpeg-2.5.0-py3-none-any.whl",
    ):
        path = tmp_path / name
        path.write_bytes(b"fixture\n")
        dependencies.append(path)
    requirements = tmp_path / "runtime-requirements.txt"
    requirements.write_text("pillow==12.3.0\n")
    synthetic_preflight = tmp_path / packager.SYNTHETIC_PREFLIGHT_BASENAME
    synthetic_preflight.write_bytes(
        packager._canonical_json_bytes(packager.SYNTHETIC_PREFLIGHT_REPORT)
    )
    source_root, registry = _source_manifest_bundle(tmp_path)
    return {
        "owner": "test-owner",
        "git_commit": "1" * 40,
        "git_commit_timestamp": 1_700_000_000,
        "wheel_path": project_wheel,
        "dependency_wheel_paths": dependencies,
        "runtime_requirements_path": requirements,
        "preprocessing_config_path": ROOT / "configs/preprocessing.v1.json",
        "preprocessing_schema_path": ROOT / "configs/preprocessing.v1.schema.json",
        "manifest_schema_path": ROOT / "configs/manifest_schema.yaml",
        "competition_config_path": ROOT / "configs/competition.yaml",
        "competition_contract_path": ROOT / "docs/competition_contract/contract.yaml",
        "uv_lock_path": ROOT / "uv.lock",
        "kernel_runner_path": ROOT / "kaggle/dicom_qa/run.py",
        "performance_smoke_path": ROOT / "kaggle/dicom_qa/performance_smoke.py",
        "comparison_path": ROOT / "kaggle/dicom_qa/compare_runs.py",
        "review_finalizer_path": ROOT / "kaggle/dicom_qa/finalize_review.py",
        "review_ui_path": ROOT / "kaggle/dicom_qa/review_ui.py",
        "output_validator_path": ROOT / "scripts/validate_dicom_qa_output.py",
        "synthetic_preflight_path": synthetic_preflight,
        "source_manifest_bundle_root": source_root,
        "source_manifest_registry_path": registry,
        "source_manifest_audit_id": packager.SOURCE_MANIFEST_AUDIT_ID,
    }


def test_bundle_has_distinct_immutable_a_b_review_chain(tmp_path: Path) -> None:
    inputs = _bundle_inputs(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    result = packager._assemble_bundle(output=first, **inputs)
    repeated = packager._assemble_bundle(output=second, **inputs)

    assert result == repeated
    assert result["run_a_ref"] != result["run_b_ref"]
    assert all(
        len(ref.partition("/")[2]) <= 50 for key, ref in result.items() if key.endswith("_ref")
    )
    assert [path.relative_to(first) for path in sorted(first.rglob("*"))] == [
        path.relative_to(second) for path in sorted(second.rglob("*"))
    ]
    for path in (item for item in first.rglob("*") if item.is_file()):
        assert path.read_bytes() == (second / path.relative_to(first)).read_bytes()

    run_a = json.loads((first / "kernel-a/kernel-metadata.json").read_text())
    run_b = json.loads((first / "kernel-b/kernel-metadata.json").read_text())
    performance_smoke = json.loads(
        (first / "performance-smoke-kernel/kernel-metadata.json").read_text()
    )
    comparison = json.loads((first / "comparison-kernel/kernel-metadata.json").read_text())
    finalizer = json.loads((first / "review-finalizer-kernel/kernel-metadata.json").read_text())
    assert (
        run_a["kernel_sources"] == run_b["kernel_sources"] == [result["source_manifest_kernel_ref"]]
    )
    assert performance_smoke["id"] == result["performance_smoke_ref"]
    assert performance_smoke["code_file"] == "performance_smoke.py"
    assert performance_smoke["kernel_sources"] == [result["source_manifest_kernel_ref"]]
    assert performance_smoke["is_private"] is True
    assert performance_smoke["enable_internet"] is False
    assert performance_smoke["enable_gpu"] is False
    assert performance_smoke["enable_tpu"] is False
    assert comparison["kernel_sources"] == [result["run_a_ref"], result["run_b_ref"]]
    assert finalizer["kernel_sources"] == [
        result["run_a_ref"],
        result["run_b_ref"],
        result["comparison_ref"],
        result["review_plan_ref"],
        result["review_session_ref"],
    ]
    manifest = json.loads((first / "dataset/bundle-manifest.json").read_text())
    roles = {record["role"] for record in manifest["files"]}
    assert {
        "source_manifest_schema",
        "performance_smoke_source",
        "performance_smoke_policy",
        "comparison_source",
        "review_ui_source",
        "review_notebook",
        "output_validator",
    } <= roles
    run_config = json.loads((first / "dataset/run-config.json").read_text())
    assert run_config["selection"]["minimum_studies"] == 100
    assert run_config["selection"]["minimum_is_not_maximum"] is True
    assert "maximum_studies" not in run_config["selection"]


def test_source_manifest_requires_successor_registry_binding(tmp_path: Path) -> None:
    source, registry = _source_manifest_bundle(tmp_path)
    identity = packager._source_manifest_identity(
        source,
        ROOT / "configs/manifest_schema.yaml",
        registry,
        packager.SOURCE_MANIFEST_AUDIT_ID,
    )
    assert identity["audit_id"] == "audit-0002-manifest-remediation"
    with pytest.raises(packager.PackagingError, match="source_manifest_audit_invalid"):
        packager._source_manifest_identity(
            source,
            ROOT / "configs/manifest_schema.yaml",
            registry,
            "audit-0001-manifest",
        )
    with sqlite3.connect(registry) as connection:
        connection.execute("UPDATE audit_runs SET config_hash=?", ("f" * 64,))
    with pytest.raises(packager.PackagingError, match="source_manifest_registry_invalid"):
        packager._source_manifest_identity(
            source,
            ROOT / "configs/manifest_schema.yaml",
            registry,
            packager.SOURCE_MANIFEST_AUDIT_ID,
        )


def test_project_wheel_rejects_symlink_member(tmp_path: Path) -> None:
    wheel = tmp_path / "unsafe.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name in packager.REQUIRED_PROJECT_WHEEL_MEMBERS:
            archive.writestr(name, b"fixture")
        link = zipfile.ZipInfo("rsna_knee/dicom/link.py")
        link.create_system = 3
        link.external_attr = (0o120777 << 16) | 0xA000
        archive.writestr(link, b"../../outside")
    with pytest.raises(packager.PackagingError, match="project_wheel_invalid"):
        packager._validate_project_wheel(wheel)


def _static_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    hashes = {
        "runner_sha256": "1" * 64,
        "performance_smoke_sha256": "2" * 64,
        "performance_smoke_policy_sha256": "3" * 64,
        "comparison_sha256": "4" * 64,
        "review_finalizer_sha256": "5" * 64,
        "review_ui_sha256": "6" * 64,
        "review_notebook_sha256": "7" * 64,
        "output_validator_sha256": "8" * 64,
    }
    source = {
        "version": "manifest-v2",
        "audit_id": "audit-0002-manifest-remediation",
        "kernel_ref": "test-owner/manifest-kernel",
        "kernel_version": 1,
        "kernel_code_file": "run.py",
        "kernel_code_sha256": "7" * 64,
        "bundle_dataset_ref": "test-owner/manifest-bundle",
        "bundle_dataset_version": 1,
        "bundle_sha256": "8" * 64,
        "bundle_dataset_files": [{"name": "bundle-manifest.json", "bytes": 1, "sha256": "0" * 64}],
        "private_output_policy": [
            {"path": "audit-output/private_manifest.sqlite3", "max_bytes": 1}
        ],
        "schema_sha256": "9" * 64,
        "artifact_inventory_filename": "private_artifact_inventory.json",
        "database_filename": "private_manifest.sqlite3",
        "audit_key_filename": "audit_key.bin",
    }
    run_config = {
        "code_commit": "a" * 40,
        "bundle_sha256": "b" * 64,
        "deployment": {"owner": "test-owner"},
        "provenance": {
            **hashes,
            "preprocessing_version": "dicom-model-v1",
            "preprocessing_config_sha256": "c" * 64,
        },
        "input_identity": {
            "official_competition": {
                "slug": packager.COMPETITION_SLUG,
                "contract_sha256": "d" * 64,
                "snapshot_identity_source": "chunk4_private_manifest",
            },
            "source_manifest": source,
        },
        "review_policy": {
            "protocol_version": finalize_review.REVIEW_PROTOCOL_VERSION,
            "instructions_version": finalize_review.REVIEW_INSTRUCTIONS_VERSION,
            "cohort_selection_version": finalize_review.QA_COHORT_SELECTION_VERSION,
            "stratum_registry_version": finalize_review.QA_STRATUM_REGISTRY_VERSION,
            "stratum_registry_sha256": finalize_review.QA_STRATUM_REGISTRY_SHA256,
            "kernel_version": 1,
            "checks": list(finalize_review.REVIEW_CHECKS),
            "statuses": ["PASS", "BLOCK", "NOT_APPLICABLE"],
            "artifact_presence_separate": True,
            "minimum_reviewed_studies": 100,
        },
    }
    manifest = {
        "kernel": {"code_file": "run.py", "sha256": hashes["runner_sha256"]},
        "performance_smoke": {
            "code_file": "performance_smoke.py",
            "sha256": hashes["performance_smoke_sha256"],
            "policy_file": "performance-smoke-policy.json",
            "policy_sha256": hashes["performance_smoke_policy_sha256"],
        },
        "comparison": {
            "code_file": "compare_runs.py",
            "sha256": hashes["comparison_sha256"],
        },
        "review_finalizer": {
            "code_file": "finalize_review.py",
            "sha256": hashes["review_finalizer_sha256"],
        },
        "review_ui": {
            "code_file": "review_ui.ipynb",
            "sha256": hashes["review_notebook_sha256"],
            "module_file": "review_ui.py",
            "module_sha256": hashes["review_ui_sha256"],
        },
        "output_validator": {
            "code_file": "validate_output.py",
            "sha256": hashes["output_validator_sha256"],
        },
    }
    return run_config, manifest


def _registry_memberships(*, laterality: str = "unknown") -> list[list[str]]:
    return sorted(
        [
            [
                dimension,
                laterality if dimension == "laterality" else f"represented_{dimension}",
            ]
            for dimension in EXPECTED_REVIEW_DIMENSIONS
        ]
    )


def _case_index() -> dict[str, Any]:
    studies: list[dict[str, Any]] = [
        {
            "case_ordinal": ordinal,
            "study_uid": f"1.2.840.{ordinal}",
            "selection_stratum": [f"s{index}" for index in range(11)],
            "registry_memberships": _registry_memberships(),
            "series": [
                {
                    "series_uid": f"1.2.840.{ordinal}.1",
                    "model_eligible": True,
                }
            ],
        }
        for ordinal in range(100)
    ]
    coverage_rows = [
        {
            "dimension": dimension,
            "value": "unknown" if dimension == "laterality" else f"represented_{dimension}",
            "represented": True,
            "population": 100,
            "required_quota": 2,
            "selected": 100,
            "quota_met": True,
            "reason": "mandatory_represented_categorical",
            "selector_version": finalize_review.QA_COHORT_SELECTION_VERSION,
        }
        for dimension in sorted(EXPECTED_REVIEW_DIMENSIONS)
    ]
    coverage_ledger = {
        "rows": coverage_rows,
        "total_required_strata": len(coverage_rows),
        "total_satisfied": len(coverage_rows),
        "unsatisfied_strata": [],
        "cohort_size": len(studies),
        "all_required_represented_registry_values_satisfy_quotas": True,
        "registry_version": finalize_review.QA_STRATUM_REGISTRY_VERSION,
        "selector_version": finalize_review.QA_COHORT_SELECTION_VERSION,
        "manifest_version": "manifest-v2",
    }
    selection = {
        "selection_version": finalize_review.QA_COHORT_SELECTION_VERSION,
        "stratum_registry_version": finalize_review.QA_STRATUM_REGISTRY_VERSION,
        "stratum_registry_sha256": finalize_review.QA_STRATUM_REGISTRY_SHA256,
        "selected_studies": len(studies),
        "eligible_series": len(studies),
        "cohort_sha256": finalize_review._cohort_sha256_from_studies(studies),
        "cohort_plan_sha256": "c" * 64,
        "source_manifest_gate": "pass",
        "coverage_ledger_sha256": hashlib.sha256(
            finalize_review._canonical_json_bytes(coverage_ledger)
        ).hexdigest(),
        "coverage_ledger": coverage_ledger,
    }
    capacity_certificate = {
        "schema_version": 1,
        "artifact_type": "private-dicom-qa-preparation-capacity-certificate",
        "status": "pass",
        "provenance": {
            "git_commit": "a" * 40,
            "bundle_sha256": "b" * 64,
            "review_plan_ref": "test-owner/rsna-knee-dqa-plan-aaaaaaa-bbbbbbbbbbbb",
            "review_plan_version": 1,
            "performance_smoke_summary_sha256": "9" * 64,
            "full_run_manifest_sha256": "0" * 64,
            "cohort_plan_sha256": "c" * 64,
            "comparison_sha256": "d" * 64,
            "qa_renderer_version": finalize_review.QA_RENDERER_VERSION,
            "qa_stratum_registry_version": finalize_review.QA_STRATUM_REGISTRY_VERSION,
            "qa_stratum_registry_sha256": finalize_review.QA_STRATUM_REGISTRY_SHA256,
        },
        "admission": {
            "eligible_series": len(studies),
            "projected_review_files": len(studies) * 7,
            "projected_review_bytes": len(studies) * 1024**2,
            "projected_replay_seconds": len(studies) * 60,
            "projected_benchmark_seconds": 60,
            "finalization_reserve_seconds": 600,
            "required_seconds": len(studies) * 60 + 660,
            "remaining_seconds_at_gate": len(studies) * 60 + 660,
            "available_working_disk_bytes_at_gate": 2 * 1024**3,
            "required_working_disk_bytes": 1024**3,
        },
    }
    return {
        "provenance": {
            "git_commit": "a" * 40,
            "bundle_sha256": "b" * 64,
            "runner_sha256": "1" * 64,
            "review_finalizer_sha256": "5" * 64,
            "full_run_manifest_sha256": "0" * 64,
            "cohort_plan_sha256": "c" * 64,
            "comparison_sha256": "d" * 64,
            "review_plan_ref": "test-owner/rsna-knee-dqa-plan-aaaaaaa-bbbbbbbbbbbb",
            "review_plan_version": 1,
            "qa_stratum_registry_version": finalize_review.QA_STRATUM_REGISTRY_VERSION,
            "qa_stratum_registry_sha256": finalize_review.QA_STRATUM_REGISTRY_SHA256,
            "qa_renderer_version": finalize_review.QA_RENDERER_VERSION,
        },
        "input_identity": {
            "audit_id": packager.SOURCE_MANIFEST_AUDIT_ID,
            "manifest_version": "manifest-v2",
            "source_manifest_artifact_sha256": "e" * 64,
            "official_input_snapshot_sha256": "f" * 64,
        },
        "qa_cohort_selection": selection,
        "capacity_certificate": capacity_certificate,
        "capacity_certificate_sha256": hashlib.sha256(
            finalize_review._canonical_json_bytes(capacity_certificate)
        ).hexdigest(),
        "studies": studies,
        "full_run": {
            "manifest_sha256": "0" * 64,
            "qa_cohort_selection": copy.deepcopy(selection),
            "qa_preparation_capacity_certificate": copy.deepcopy(capacity_certificate),
            "qa_preparation_capacity_certificate_sha256": hashlib.sha256(
                finalize_review._canonical_json_bytes(capacity_certificate)
            ).hexdigest(),
        },
    }


def _review_context(
    *, laterality: str = "unknown", check_9_applicable: bool = False
) -> dict[str, Any]:
    return {
        "organizer_plane": "sagittal",
        "physical_plane": "sagittal",
        "laterality": laterality,
        "laterality_transform": "none",
        "horizontal_flip_applied": False,
        "assigned_slot": "sagittal_fluid_sensitive",
        "retention_reasons": [],
        "missing_series_mask": (
            [False, True, True, True, True, True]
            if check_9_applicable
            else [False, False, False, False, False, False]
        ),
        "sibling_series": [
            {
                "series_ordinal": 0,
                "slot": "sagittal_fluid_sensitive",
                "terminal_state": "model_eligible",
                "model_eligible": True,
                "retention_reasons": [],
                "quality_blocked_reasons": [],
            }
        ],
        "check_9_applicable": check_9_applicable,
        "check_9_reason_codes": ["missing_diagnostic_slot"] if check_9_applicable else [],
    }


def _qa_materialization_identity(review_plan_ref: str) -> dict[str, Any]:
    return {
        "run_a_full_manifest_sha256": "1" * 64,
        "cohort_plan_sha256": "2" * 64,
        "comparison_proof_sha256": "3" * 64,
        "review_plan": {"ref": review_plan_ref, "version": 1},
        "stratum_registry": {
            "version": review_ui.QA_STRATUM_REGISTRY_VERSION,
            "sha256": review_ui.QA_STRATUM_REGISTRY_SHA256,
        },
        "renderer_version": review_ui.QA_RENDERER_VERSION,
        "capacity_certificate_sha256": "4" * 64,
    }


def _ui_review_identity(
    review_plan_ref: str, *, extra_kernels: dict[str, Any] | None = None
) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "preprocessing": {"version": "dicom-model-v1"},
        "qa_cohort": {"sha256": "a" * 64},
        "qa_materialization": _qa_materialization_identity(review_plan_ref),
        "kernels": {
            "review_plan": {"ref": review_plan_ref, "version": 1},
            **(extra_kernels or {}),
        },
    }
    identity["review_bundle_id"] = (
        "c5qa-"
        + hashlib.sha256(
            review_ui._canonical_json_bytes(
                {"domain": "rsna-knee-private-review-bundle-v2", "identity": identity}
            )
        ).hexdigest()[:20]
    )
    return identity


def _plan_and_ledger(
    static: dict[str, Any], case_index: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    identity = finalize_review._private_review_identity(static, case_index)
    rows = [
        {
            "case_ordinal": ordinal,
            "series_ordinal": 0,
            "review_context": _review_context(),
            "decisions": {check: "not_reviewed" for check in finalize_review.REVIEW_CHECKS},
            "artifacts": [
                {"name": f"case_{ordinal:06d}_series_000_review.json", "sha256": "1" * 64}
            ],
        }
        for ordinal in range(100)
    ]
    plan = {
        "schema_version": 2,
        "artifact_type": "private-dicom-qa-review-plan",
        "status": "pending_private_human_review",
        "review_identity": identity,
        "rows": rows,
    }
    ledger = {
        "schema_version": 2,
        "artifact_type": "private-dicom-qa-completed-review-ledger",
        "status": "complete",
        "review_identity": identity,
        "plan_sha256": hashlib.sha256(finalize_review._canonical_json_bytes(plan)).hexdigest(),
        "started_at_utc": "2025-01-01T01:02:02Z",
        "completed_at_utc": "2025-01-01T01:02:03Z",
        "human_attestation": {
            "schema_version": 1,
            "instructions_version": finalize_review.REVIEW_INSTRUCTIONS_VERSION,
            "statement": finalize_review.HUMAN_ATTESTATION_STATEMENT,
            "authorized_human_reviewer": True,
            "direct_visual_review": True,
            "no_llm_or_browser_automation_pixel_access": True,
            "attested_at_utc": "2025-01-01T01:02:03Z",
        },
        "rows": [
            {
                "case_ordinal": ordinal,
                "series_ordinal": 0,
                "artifact_hashes_verified": True,
                "decisions": {check: "PASS" for check in finalize_review.REVIEW_CHECKS},
            }
            for ordinal in range(100)
        ],
    }
    return plan, finalize_review._canonical_json_bytes(ledger)


def test_review_identity_uses_exact_registry_and_private_coverage_ledger() -> None:
    run_config, manifest = _static_inputs()
    case_index = _case_index()

    assert review_ui.QA_STRATUM_REGISTRY_SHA256 == finalize_review.QA_STRATUM_REGISTRY_SHA256
    assert len(EXPECTED_REVIEW_DIMENSIONS) == 25
    assert finalize_review.REQUIRED_REVIEW_DIMENSIONS == EXPECTED_REVIEW_DIMENSIONS
    assert packager.REQUIRED_REVIEW_DIMENSIONS == EXPECTED_REVIEW_DIMENSIONS
    assert (
        finalize_review.REPRESENTED_STRATA_SUMMARY_TOKEN
        == "all_required_represented_registry_values_satisfy_quotas"
    )
    assert case_index["qa_cohort_selection"] == case_index["full_run"]["qa_cohort_selection"]
    assert {
        row["dimension"] for row in case_index["qa_cohort_selection"]["coverage_ledger"]["rows"]
    } == set(EXPECTED_REVIEW_DIMENSIONS)
    assert all(
        {item[0] for item in study["registry_memberships"]} == set(EXPECTED_REVIEW_DIMENSIONS)
        for study in case_index["studies"]
    )
    assert case_index["qa_cohort_selection"]["cohort_sha256"] == (
        finalize_review._cohort_sha256_from_studies(case_index["studies"])
    )
    identity = finalize_review._private_review_identity(
        finalize_review._public_review_identity(run_config, manifest), case_index
    )
    assert (
        identity["qa_cohort"]["coverage_ledger"]
        == case_index["qa_cohort_selection"]["coverage_ledger"]
    )
    assert identity["qa_materialization"] == {
        "run_a_full_manifest_sha256": "0" * 64,
        "cohort_plan_sha256": "c" * 64,
        "comparison_proof_sha256": "d" * 64,
        "review_plan": {
            "ref": "test-owner/rsna-knee-dqa-plan-aaaaaaa-bbbbbbbbbbbb",
            "version": 1,
        },
        "stratum_registry": {
            "version": finalize_review.QA_STRATUM_REGISTRY_VERSION,
            "sha256": finalize_review.QA_STRATUM_REGISTRY_SHA256,
        },
        "renderer_version": finalize_review.QA_RENDERER_VERSION,
        "capacity_certificate_sha256": case_index["capacity_certificate_sha256"],
    }


def test_private_case_schema_uses_registry_coverage_without_legacy_joint_census() -> None:
    case_index = _case_index()
    reconstruction = {
        "laterality": None,
        "transformation_ledger": {
            "laterality_transform": "none",
            "horizontal_flip_applied": False,
        },
    }
    for study in case_index["studies"]:
        study.update(
            {
                "review_eligible": True,
                "missing_series_mask": [False] * 6,
                "series": [
                    {
                        "series_ordinal": 0,
                        "series_uid": study["series"][0]["series_uid"],
                        "organizer_plane": "sagittal",
                        "physical_plane": "sagittal",
                        "slot": "sagittal_fluid_sensitive",
                        "laterality": "unknown",
                        "laterality_transform": "none",
                        "horizontal_flip_applied": False,
                        "retention_reasons": [],
                        "quality": {"blocked_reasons": [], "components": {}},
                        "source_failure": None,
                        "decode_failures": [],
                        "ordering_failure": None,
                        "preprocessing_failure": None,
                        "terminal_state": "model_eligible",
                        "model_eligible": True,
                        "model_output_reconstruction": copy.deepcopy(reconstruction),
                        "qa_output_reconstruction": copy.deepcopy(reconstruction),
                    }
                ],
            }
        )
    case_index.update(
        {
            "schema_version": 1,
            "artifact_type": "private-dicom-qa-case-index",
            "status": "pending_private_human_review",
            "represented_review_strata": [[f"s{index}" for index in range(11)]],
            "benchmark": {},
        }
    )
    suffixes = (
        "contact.png",
        "orthogonal.png",
        "histogram.png",
        "animation.gif",
        "before_after.png",
        "review.json",
        "metadata.json",
    )
    inventory = {
        "schema_version": 1,
        "artifact_type": "private-dicom-qa-artifact-inventory",
        "status": "pending_private_human_review",
        "provenance": {},
        "artifacts": [
            {
                "name": f"case_{case:06d}_series_000_{suffix}",
                "bytes": 1,
                "sha256": "1" * 64,
            }
            for case in range(100)
            for suffix in suffixes
        ],
    }

    eligible, artifacts, contexts = finalize_review._case_series(case_index, inventory)
    assert len(eligible) == len(contexts) == 100
    assert all(len(value) == 7 for value in artifacts.values())
    assert "selection_census" not in case_index

    stale = copy.deepcopy(case_index)
    stale["selection_census"] = []
    with pytest.raises(finalize_review.ReviewFinalizationError, match="private_case_index_invalid"):
        finalize_review._case_series(stale, inventory)


def test_automatic_discovery_materializes_then_finalizes_review_plan_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_root = tmp_path / "input"
    working_root = tmp_path / "working"
    working_root.mkdir()
    run_config = {
        "code_commit": "a" * 40,
        "bundle_sha256": "b" * 64,
        "deployment": {"owner": "test-owner"},
    }
    refs = finalize_review._derived_refs(run_config)
    bundle_root = input_root / "bundle/data"
    _write_private(
        bundle_root / "run-config.json",
        finalize_review._canonical_json_bytes(run_config),
    )
    _write_private(
        bundle_root / "bundle-manifest.json",
        finalize_review._canonical_json_bytes({"fixture": True}),
    )
    _write_private(bundle_root / "qa_runner.py", b"# fixture\n")
    run_a_root = input_root / refs["run_a"].partition("/")[2] / "output"
    comparison_root = input_root / refs["comparison"].partition("/")[2] / "output"
    smoke_root = input_root / refs["performance_smoke"].partition("/")[2] / "output"
    for path in (
        run_a_root / "private_full_run_manifest.jsonl",
        run_a_root / "private_full_run_metrics.json",
        run_a_root / "private_cohort_plan.json",
        comparison_root / "private_run_comparison.json",
        smoke_root / "sanitized_performance_smoke.json",
    ):
        _write_private(path, b"fixture\n")
    monkeypatch.setenv("KAGGLE_INPUT_ROOT", str(input_root))
    monkeypatch.setenv("KAGGLE_WORKING_ROOT", str(working_root))

    materialize = finalize_review._automatic_args()
    assert materialize.automatic_materialization is True
    assert materialize.run_a_full_manifest == run_a_root / "private_full_run_manifest.jsonl"
    assert materialize.comparison_proof == comparison_root / "private_run_comparison.json"
    assert materialize.performance_smoke_summary == (
        smoke_root / "sanitized_performance_smoke.json"
    )

    review_plan_root = input_root / refs["review_plan"].partition("/")[2] / "output"
    review_session_root = input_root / refs["review_session"].partition("/")[2] / "output"
    for path in (
        review_plan_root / "private_case_index.json",
        review_plan_root / "private_artifact_inventory.json",
        review_plan_root / "sanitized_summary.json",
        review_session_root / finalize_review.REVIEW_LEDGER_BASENAME,
        comparison_root / "sanitized_determinism.json",
        run_a_root / "private_case_index.json",
        run_a_root / "private_artifact_inventory.json",
        run_a_root / "sanitized_summary.json",
    ):
        _write_private(path, b"fixture\n")
    (review_plan_root / "private-review").mkdir()

    complete = finalize_review._automatic_args()
    assert complete.automatic_materialization is False
    assert complete.private_case_index == review_plan_root / "private_case_index.json"
    assert complete.private_artifact_inventory == (
        review_plan_root / "private_artifact_inventory.json"
    )
    assert complete.private_review_root == review_plan_root / "private-review"
    assert complete.run_a_sanitized_summary == review_plan_root / "sanitized_summary.json"


def test_automatic_materializer_activates_offline_runtime_and_feeds_ui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    review_plan_ref = "test-owner/review-plan"
    artifact_name = "case_000000_series_000_review.json"
    artifact_payload = review_ui._canonical_json_bytes({"safe": True})
    plan = {
        "schema_version": 2,
        "artifact_type": "private-dicom-qa-review-plan",
        "status": "pending_private_human_review",
        "review_identity": _ui_review_identity(review_plan_ref),
        "rows": [
            {
                "case_ordinal": 0,
                "series_ordinal": 0,
                "review_context": _review_context(),
                "decisions": {check: "not_reviewed" for check in review_ui.REVIEW_CHECKS},
                "artifacts": [
                    {
                        "name": artifact_name,
                        "sha256": hashlib.sha256(artifact_payload).hexdigest(),
                    }
                ],
            }
        ],
    }
    input_root = tmp_path / "input"
    plan_target = input_root / "review-plan" / finalize_review.TEMPLATE_OUTPUT_DIRECTORY
    qa_target = input_root / "review-plan/dicom-qa-output"
    working_root = tmp_path / "working"
    working_root.mkdir()
    bundle_root = tmp_path / "bundle"
    bundle_root.mkdir()
    smoke = tmp_path / "smoke.json"
    _write_private(smoke, b"smoke\n")
    runtime_root = tmp_path / "runtime"
    calls: dict[str, Any] = {}

    class FakeSafeRunError(RuntimeError):
        code = "fake_safe_error"

    class FakeDeadlineExceeded(RuntimeError):
        pass

    @contextmanager
    def enforce_deadline(_remaining: float) -> Any:
        assert calls.get("deadline_active") is not True
        calls["deadline_active"] = True
        try:
            yield
        finally:
            calls["deadline_active"] = False

    def install_runtime(
        received_bundle: Path, project_wheel: Path, dependencies: tuple[Path, ...]
    ) -> Path:
        calls["install"] = (received_bundle, project_wheel, dependencies)
        runtime_root.mkdir()
        return runtime_root

    def prepare(**kwargs: Any) -> None:
        assert calls.get("deadline_active") is True
        calls["prepare"] = kwargs
        output_root = kwargs["output_root"]
        output_root.mkdir()
        _write_private(output_root / "private_case_index.json", b"case\n")
        _write_private(output_root / "private_artifact_inventory.json", b"inventory\n")
        _write_private(output_root / "private-review" / artifact_name, artifact_payload)

    runner = SimpleNamespace(
        OUTPUT_DIRECTORY="dicom-qa-output",
        SELF_DEADLINE_SECONDS=27_000,
        SafeRunError=FakeSafeRunError,
        _DeadlineExceeded=FakeDeadlineExceeded,
        prepare_private_review=prepare,
        _competition_cpu_limit_seconds=lambda _path: 32_400,
        _find_competition_root=lambda _root: tmp_path / "competition",
        _enforce_self_deadline=enforce_deadline,
        _silence_process_output=nullcontext,
        _install_offline_runtime=install_runtime,
    )
    run_config = {
        "code_commit": "a" * 40,
        "bundle_sha256": "b" * 64,
        "deployment": {"owner": "test-owner"},
    }
    paths = {
        "competition_contract": tmp_path / "contract.yaml",
        "preprocessing_config": tmp_path / "preprocessing.json",
        "project_wheel": tmp_path / "project.whl",
    }
    dependencies = (tmp_path / "dependency.whl",)
    monkeypatch.setattr(
        finalize_review,
        "_verified_bundle",
        lambda *_args, **_kwargs: (run_config, {}, {}, runner, paths, dependencies),
    )

    def create_template_inside_deadline(**_kwargs: Any) -> bytes:
        assert calls.get("deadline_active") is True
        calls["create_template_inside_deadline"] = True
        return cast(bytes, finalize_review._canonical_json_bytes(plan))

    original_publish = finalize_review._publish_review_plan_outputs

    def publish_inside_deadline(*publish_args: Path) -> None:
        assert calls.get("deadline_active") is True
        calls["publish_inside_deadline"] = True
        original_publish(*publish_args)

    monkeypatch.setattr(finalize_review, "create_template", create_template_inside_deadline)
    monkeypatch.setattr(finalize_review, "_publish_review_plan_outputs", publish_inside_deadline)
    args = SimpleNamespace(
        bundle_manifest=bundle_root / "bundle-manifest.json",
        run_config=bundle_root / "run-config.json",
        runner=bundle_root / "qa_runner.py",
        input_root=input_root,
        template_output=plan_target / review_ui.PLAN_BASENAME,
        run_a_full_manifest=tmp_path / "manifest.jsonl",
        run_a_metrics=tmp_path / "metrics.json",
        run_a_cohort_plan=tmp_path / "cohort.json",
        comparison_proof=tmp_path / "comparison.json",
        performance_smoke_summary=smoke,
    )

    finalize_review._materialize_automatic_template(
        args,
        run_config_payload=b"run\n",
        manifest_payload=b"manifest\n",
        finalizer_sha256="f" * 64,
    )

    assert calls["install"] == (bundle_root, paths["project_wheel"], dependencies)
    assert set(calls["prepare"]) == {
        "competition_root",
        "output_root",
        "staging_parent",
        "run_config",
        "preprocessing_config_path",
        "full_manifest_path",
        "full_metrics_path",
        "cohort_plan_path",
        "comparison_proof_path",
        "performance_smoke_summary_payload",
        "review_plan_ref",
        "review_plan_version",
        "inference_limit_seconds",
        "deadline_at",
    }
    assert calls["prepare"]["performance_smoke_summary_payload"] == b"smoke\n"
    assert calls["prepare"]["review_plan_ref"] == (
        "test-owner/rsna-knee-dqa-plan-aaaaaaa-bbbbbbbbbbbb"
    )
    assert calls["create_template_inside_deadline"] is True
    assert calls["publish_inside_deadline"] is True
    assert calls["deadline_active"] is False
    assert not runtime_root.exists()
    assert {path.name for path in plan_target.iterdir()} == {review_ui.PLAN_BASENAME}
    assert (qa_target / "private_case_index.json").is_file()
    assert (qa_target / "private_artifact_inventory.json").is_file()
    assert (qa_target / "private-review" / artifact_name).is_file()
    assert not (qa_target / review_ui.PLAN_BASENAME).exists()
    answers = iter(("START", "P" * 8 + "N", review_ui.HUMAN_ATTESTATION_STATEMENT))
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))
    monkeypatch.setattr(review_ui, "_show", lambda _context, _paths: None)
    assert review_ui.run_review(input_root=input_root, working_root=working_root) == (
        working_root / review_ui.LEDGER_BASENAME
    )


def test_two_sibling_publish_rolls_back_qa_when_plan_publish_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qa_staging = tmp_path / "staged-qa"
    plan_staging = tmp_path / "staged-plan"
    qa_staging.mkdir()
    plan_staging.mkdir()
    _write_private(qa_staging / "private_case_index.json", b"case\n")
    _write_private(plan_staging / review_ui.PLAN_BASENAME, b"plan\n")
    qa_target = tmp_path / "dicom-qa-output"
    plan_target = tmp_path / finalize_review.TEMPLATE_OUTPUT_DIRECTORY
    original_rename = Path.rename

    def fail_plan_publish(path: Path, target: Path) -> Path:
        if path == plan_staging:
            raise OSError("simulated publish failure")
        return original_rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_plan_publish)
    with pytest.raises(finalize_review.ReviewFinalizationError, match="output_write_failed"):
        finalize_review._publish_review_plan_outputs(
            qa_staging, plan_staging, qa_target, plan_target
        )
    assert not qa_target.exists()
    assert not plan_target.exists()
    assert (qa_staging / "private_case_index.json").is_file()
    assert (plan_staging / review_ui.PLAN_BASENAME).is_file()


@pytest.mark.parametrize("interrupted_publish", ["qa", "plan"])
def test_two_sibling_publish_rolls_back_renamed_target_on_late_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupted_publish: str
) -> None:
    qa_staging = tmp_path / "staged-qa"
    plan_staging = tmp_path / "staged-plan"
    qa_staging.mkdir()
    plan_staging.mkdir()
    _write_private(qa_staging / "private_case_index.json", b"case\n")
    _write_private(plan_staging / review_ui.PLAN_BASENAME, b"plan\n")
    qa_target = tmp_path / "dicom-qa-output"
    plan_target = tmp_path / finalize_review.TEMPLATE_OUTPUT_DIRECTORY
    original_rename = Path.rename

    class SimulatedDeadlineExceeded(RuntimeError):
        pass

    interrupted_staging = qa_staging if interrupted_publish == "qa" else plan_staging

    def exceed_after_successful_publish(path: Path, target: Path) -> Path:
        if path == interrupted_staging:
            original_rename(path, target)
            raise SimulatedDeadlineExceeded
        return original_rename(path, target)

    monkeypatch.setattr(Path, "rename", exceed_after_successful_publish)
    with pytest.raises(SimulatedDeadlineExceeded):
        finalize_review._publish_review_plan_outputs(
            qa_staging, plan_staging, qa_target, plan_target
        )
    assert not qa_target.exists()
    assert not plan_target.exists()
    assert (qa_staging / "private_case_index.json").is_file()
    assert (plan_staging / review_ui.PLAN_BASENAME).is_file()


@pytest.mark.parametrize(
    "mutation",
    [
        "cohort",
        "config",
        "bundle",
        "manifest",
        "input_version",
        "smoke",
        "coverage",
        "full_run_selection",
        "capacity",
        "comparison_binding",
        "review_plan_binding",
        "renderer_binding",
    ],
)
def test_ledger_replay_fails_for_every_identity_mutation(mutation: str) -> None:
    run_config, manifest = _static_inputs()
    case_index = _case_index()
    static = finalize_review._public_review_identity(run_config, manifest)
    plan, ledger = _plan_and_ledger(static, case_index)
    finalize_review._validated_ledger(ledger, plan)

    mutated_config = copy.deepcopy(run_config)
    mutated_case = copy.deepcopy(case_index)
    if mutation == "cohort":
        mutated_case["studies"][0]["study_uid"] = "1.2.840.changed"
    elif mutation == "config":
        mutated_config["provenance"]["preprocessing_config_sha256"] = "0" * 64
    elif mutation == "bundle":
        mutated_config["bundle_sha256"] = "0" * 64
    elif mutation == "manifest":
        mutated_case["input_identity"]["source_manifest_artifact_sha256"] = "0" * 64
    elif mutation == "input_version":
        mutated_config["input_identity"]["source_manifest"]["kernel_version"] = 2
    elif mutation == "smoke":
        manifest = copy.deepcopy(manifest)
        manifest["performance_smoke"]["sha256"] = "0" * 64
    elif mutation == "coverage":
        mutated_case["qa_cohort_selection"]["coverage_ledger"]["rows"][0]["selected"] = 99
        mutated_case["full_run"]["qa_cohort_selection"] = copy.deepcopy(
            mutated_case["qa_cohort_selection"]
        )
    elif mutation == "full_run_selection":
        mutated_case["full_run"]["qa_cohort_selection"]["selected_studies"] = 99
    elif mutation == "capacity":
        mutated_case["capacity_certificate"]["admission"]["required_seconds"] += 1
        mutated_case["capacity_certificate_sha256"] = hashlib.sha256(
            finalize_review._canonical_json_bytes(mutated_case["capacity_certificate"])
        ).hexdigest()
    elif mutation == "comparison_binding":
        mutated_case["provenance"]["comparison_sha256"] = "0" * 64
        mutated_case["capacity_certificate"]["provenance"]["comparison_sha256"] = "0" * 64
        mutated_case["capacity_certificate_sha256"] = hashlib.sha256(
            finalize_review._canonical_json_bytes(mutated_case["capacity_certificate"])
        ).hexdigest()
    elif mutation == "review_plan_binding":
        mutated_case["provenance"]["review_plan_ref"] = "test-owner/wrong-review-plan"
    else:
        mutated_case["provenance"]["qa_renderer_version"] = "private-qa-renderer-v2"

    with pytest.raises(finalize_review.ReviewFinalizationError):
        mutated_static = finalize_review._public_review_identity(mutated_config, manifest)
        mutated_identity = finalize_review._private_review_identity(mutated_static, mutated_case)
        mutated_plan = {**plan, "review_identity": mutated_identity}
        finalize_review._validated_ledger(ledger, mutated_plan)


def test_review_ledger_rejects_not_applicable_safety_bypass() -> None:
    run_config, manifest = _static_inputs()
    case_index = _case_index()
    static = finalize_review._public_review_identity(run_config, manifest)
    plan, ledger_payload = _plan_and_ledger(static, case_index)
    ledger = json.loads(ledger_payload)
    ledger["rows"][0]["decisions"] = {
        check: "NOT_APPLICABLE" for check in finalize_review.REVIEW_CHECKS
    }

    with pytest.raises(finalize_review.ReviewFinalizationError, match="review_ledger_invalid"):
        finalize_review._validated_ledger(finalize_review._canonical_json_bytes(ledger), plan)

    ledger["rows"][0]["decisions"] = {
        check: ("NOT_APPLICABLE" if check in finalize_review.NOT_APPLICABLE_CHECKS else "PASS")
        for check in finalize_review.REVIEW_CHECKS
    }
    finalize_review._validated_ledger(finalize_review._canonical_json_bytes(ledger), plan)

    applicable_plan = copy.deepcopy(plan)
    applicable_plan["rows"][0]["review_context"] = _review_context(check_9_applicable=True)
    applicable_ledger = copy.deepcopy(ledger)
    applicable_ledger["plan_sha256"] = hashlib.sha256(
        finalize_review._canonical_json_bytes(applicable_plan)
    ).hexdigest()
    with pytest.raises(finalize_review.ReviewFinalizationError, match="review_ledger_invalid"):
        finalize_review._validated_ledger(
            finalize_review._canonical_json_bytes(applicable_ledger), applicable_plan
        )


def test_review_ledger_rejects_stale_plan_and_identity() -> None:
    run_config, manifest = _static_inputs()
    case_index = _case_index()
    static = finalize_review._public_review_identity(run_config, manifest)
    plan, ledger = _plan_and_ledger(static, case_index)

    stale_plan = copy.deepcopy(plan)
    stale_plan["rows"][0]["artifacts"][0]["sha256"] = "2" * 64
    with pytest.raises(finalize_review.ReviewFinalizationError, match="review_ledger_invalid"):
        finalize_review._validated_ledger(ledger, stale_plan)

    stale_identity = copy.deepcopy(plan)
    stale_identity["review_identity"]["review_bundle_id"] = "c5qa-stale123456789012345"
    with pytest.raises(finalize_review.ReviewFinalizationError, match="review_ledger_invalid"):
        finalize_review._validated_ledger(ledger, stale_identity)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("started_at_utc", "not-a-timestamp"),
        ("started_at_utc", "2999-01-01T00:00:00Z"),
        ("started_at_utc", "2025-01-01T01:02:04Z"),
        ("completed_at_utc", "2999-01-01T00:00:00Z"),
    ],
)
def test_review_ledger_rejects_invalid_future_or_reversed_timestamps(
    field: str, value: str
) -> None:
    run_config, manifest = _static_inputs()
    static = finalize_review._public_review_identity(run_config, manifest)
    plan, ledger_payload = _plan_and_ledger(static, _case_index())
    ledger = json.loads(ledger_payload)
    ledger[field] = value
    if field == "completed_at_utc":
        ledger["human_attestation"]["attested_at_utc"] = value
    with pytest.raises(finalize_review.ReviewFinalizationError, match="review_ledger_invalid"):
        finalize_review._validated_ledger(finalize_review._canonical_json_bytes(ledger), plan)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("statement", "I did not inspect every artifact."),
        ("instructions_version", "private-dicom-qa-review-instructions-v1"),
        ("authorized_human_reviewer", False),
        ("direct_visual_review", False),
        ("no_llm_or_browser_automation_pixel_access", False),
        ("attested_at_utc", "2025-01-01T01:02:02Z"),
    ],
)
def test_review_ledger_rejects_wrong_attestation(field: str, value: object) -> None:
    run_config, manifest = _static_inputs()
    static = finalize_review._public_review_identity(run_config, manifest)
    plan, ledger_payload = _plan_and_ledger(static, _case_index())
    ledger = json.loads(ledger_payload)
    ledger["human_attestation"][field] = value
    with pytest.raises(finalize_review.ReviewFinalizationError, match="review_ledger_invalid"):
        finalize_review._validated_ledger(finalize_review._canonical_json_bytes(ledger), plan)


def test_finalizer_validates_source_and_preprocessing_block_evidence() -> None:
    base: dict[str, Any] = {
        "source_failure": None,
        "decode_failures": [],
        "ordering_failure": None,
        "preprocessing_failure": None,
        "model_eligible": False,
        "model_output_reconstruction": None,
        "qa_output_reconstruction": None,
    }
    source = {
        **base,
        "terminal_state": "source_access_blocked",
        "source_failure": "series_file_invalid",
    }
    preprocessing = {
        **base,
        "terminal_state": "preprocessing_blocked",
        "preprocessing_failure": {
            "issue": "normalization_collapsed",
            "stage": "normalization",
            "root_cause": "constant_image",
            "exception_type": "PipelineError",
        },
    }

    assert finalize_review._validate_series_terminal_evidence(source) is False
    assert finalize_review._validate_series_terminal_evidence(preprocessing) is False

    malformed = {**preprocessing, "preprocessing_failure": None}
    with pytest.raises(finalize_review.ReviewFinalizationError, match="private_case_index_invalid"):
        finalize_review._validate_series_terminal_evidence(malformed)


def test_finalizer_preserves_unknown_laterality_without_inventing_side() -> None:
    reconstruction = {
        "laterality": None,
        "transformation_ledger": {
            "laterality_transform": "none",
            "horizontal_flip_applied": False,
        },
    }
    series = {
        "source_failure": None,
        "preprocessing_failure": None,
        "terminal_state": "model_eligible",
        "model_eligible": True,
        "laterality": "unknown",
        "model_output_reconstruction": copy.deepcopy(reconstruction),
        "qa_output_reconstruction": copy.deepcopy(reconstruction),
    }

    assert finalize_review._validate_series_terminal_evidence(series) is True
    invented = copy.deepcopy(series)
    invented["laterality"] = "left"
    with pytest.raises(finalize_review.ReviewFinalizationError, match="private_case_index_invalid"):
        finalize_review._validate_series_terminal_evidence(invented)


def test_reviewed_study_count_token_has_minimum_not_legacy_240_maximum() -> None:
    assert finalize_review._count_token(100) == "range_100_119"
    assert finalize_review._count_token(240) == "range_240_259"
    assert finalize_review._count_token(241) == "range_240_259"
    assert finalize_review._reviewed_study_bounds("range_240_259") == (240, 259)
    assert finalize_review._reviewed_study_bounds("at_or_above_threshold") is None


def test_review_ui_batch_eof_touches_no_private_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(builtins, "input", lambda _prompt: (_ for _ in ()).throw(EOFError()))
    monkeypatch.setattr(
        review_ui,
        "_discover_one",
        lambda *_args: (_ for _ in ()).throw(AssertionError("private input opened")),
    )
    assert (
        review_ui.run_review(input_root=tmp_path / "input", working_root=tmp_path / "work") is None
    )
    assert not (tmp_path / "work").exists()


def test_review_ui_writes_only_exact_completed_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_root = tmp_path / "input"
    working_root = tmp_path / "working"
    working_root.mkdir()
    review_plan_ref = "test-owner/review-plan"
    run_b_ref = "test-owner/run-b"
    artifact = input_root / "review-plan/output/private-review/case_000000_series_000_review.json"
    artifact_payload = review_ui._canonical_json_bytes({"safe": True})
    _write_private(artifact, artifact_payload)
    _write_private(
        input_root / "run-b/output/private-review" / artifact.name,
        review_ui._canonical_json_bytes({"safe": False}),
    )
    plan = {
        "schema_version": 2,
        "artifact_type": "private-dicom-qa-review-plan",
        "status": "pending_private_human_review",
        "review_identity": _ui_review_identity(
            review_plan_ref,
            extra_kernels={"run_b": {"ref": run_b_ref, "version": 1}},
        ),
        "rows": [
            {
                "case_ordinal": 0,
                "series_ordinal": 0,
                "review_context": _review_context(),
                "decisions": {check: "not_reviewed" for check in review_ui.REVIEW_CHECKS},
                "artifacts": [
                    {
                        "name": artifact.name,
                        "sha256": hashlib.sha256(artifact_payload).hexdigest(),
                    }
                ],
            }
        ],
    }
    _write_private(
        input_root / "plan/output/private_review_plan.json",
        review_ui._canonical_json_bytes(plan),
    )
    answers = iter(
        (
            "START",
            "N" * 9,
            "P" * 8 + "N",
            review_ui.HUMAN_ATTESTATION_STATEMENT,
        )
    )
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))
    shown: list[dict[str, Any]] = []
    monkeypatch.setattr(review_ui, "_show", lambda context, _paths: shown.append(context))

    assert review_ui.run_review(input_root=input_root, working_root=working_root) == (
        working_root / review_ui.LEDGER_BASENAME
    )
    assert {path.name for path in working_root.iterdir()} == {review_ui.LEDGER_BASENAME}
    ledger = json.loads((working_root / review_ui.LEDGER_BASENAME).read_text())
    assert ledger["schema_version"] == 2
    assert ledger["status"] == "complete"
    assert ledger["human_attestation"] == {
        "schema_version": 1,
        "instructions_version": review_ui.REVIEW_INSTRUCTIONS_VERSION,
        "statement": review_ui.HUMAN_ATTESTATION_STATEMENT,
        "authorized_human_reviewer": True,
        "direct_visual_review": True,
        "no_llm_or_browser_automation_pixel_access": True,
        "attested_at_utc": ledger["completed_at_utc"],
    }
    assert set(ledger["rows"][0]["decisions"].values()) == {"PASS", "NOT_APPLICABLE"}
    assert ledger["rows"][0]["artifact_hashes_verified"] is True
    assert shown == [_review_context()]
    completed = (working_root / review_ui.LEDGER_BASENAME).read_bytes()
    monkeypatch.setattr(builtins, "input", lambda _prompt: "START")
    assert review_ui.run_review(input_root=input_root, working_root=working_root) == (
        working_root / review_ui.LEDGER_BASENAME
    )
    assert (working_root / review_ui.LEDGER_BASENAME).read_bytes() == completed

    ledger["status"] = "fabricated"
    with pytest.raises(review_ui.ReviewUIError, match="resume_invalid"):
        review_ui._validate_resume(
            ledger,
            plan,
            hashlib.sha256(review_ui._canonical_json_bytes(plan)).hexdigest(),
        )


def test_generated_review_plan_context_is_accepted_and_tamper_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _review_context()
    identity = _ui_review_identity("test-owner/review-plan")
    artifact_name = "case_000000_series_000_review.json"
    artifact_payload = review_ui._canonical_json_bytes({"safe": True})
    monkeypatch.setattr(finalize_review, "_review_case_ordinals", lambda _eligible: (0,))
    monkeypatch.setattr(
        finalize_review,
        "_private_review_identity",
        lambda _static, _case_index: identity,
    )
    plan = finalize_review._template(
        {},
        {},
        {0: (("stratum",), (0,))},
        {
            (0, 0): (
                {
                    "name": artifact_name,
                    "sha256": hashlib.sha256(artifact_payload).hexdigest(),
                },
            )
        },
        {(0, 0): context},
    )

    assert plan["schema_version"] == 2
    rows, review_plan_ref = review_ui._validate_plan(plan)
    assert rows[0]["review_context"] == context
    assert review_plan_ref == "test-owner/review-plan"

    tampered = copy.deepcopy(plan)
    tampered["rows"][0]["review_context"]["missing_series_mask"][0] = True
    with pytest.raises(review_ui.ReviewUIError, match="plan_invalid"):
        review_ui._validate_plan(tampered)

    tampered_identity = copy.deepcopy(plan)
    tampered_identity["review_identity"]["qa_materialization"]["cohort_plan_sha256"] = "0" * 64
    with pytest.raises(review_ui.ReviewUIError, match="plan_invalid"):
        review_ui._validate_plan(tampered_identity)

    input_root = tmp_path / "input"
    working_root = tmp_path / "working"
    working_root.mkdir()
    _write_private(
        input_root / "plan/output" / review_ui.PLAN_BASENAME,
        review_ui._canonical_json_bytes(plan),
    )
    _write_private(
        input_root / "review-plan/output/private-review" / artifact_name,
        artifact_payload,
    )
    answers = iter(
        (
            "START",
            "P" * 8 + "N",
            review_ui.HUMAN_ATTESTATION_STATEMENT,
        )
    )
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))
    monkeypatch.setattr(review_ui, "_show", lambda _context, _paths: None)
    ledger_path = review_ui.run_review(input_root=input_root, working_root=working_root)
    assert ledger_path == working_root / review_ui.LEDGER_BASENAME
    assert json.loads(ledger_path.read_text())["status"] == "complete"


def test_review_ui_rejects_review_plan_ambiguity_and_tamper(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    review_plan_ref = "test-owner/review-plan"
    name = "case_000000_series_000_review.json"
    expected = review_ui._canonical_json_bytes({"stage": "review-plan"})
    review_plan = input_root / "review-plan/output/private-review"
    run_a = input_root / "run-a/output/private-review"
    run_b = input_root / "run-b/output/private-review"
    _write_private(review_plan / name, expected)
    _write_private(run_a / name, expected)
    _write_private(run_b / name, expected)

    artifact_root = review_ui._review_plan_artifact_root(input_root, review_plan_ref)
    assert artifact_root == review_plan
    assert review_ui._artifact(artifact_root, name, hashlib.sha256(expected).hexdigest()) == (
        review_plan / name
    )

    _write_private(review_plan / name, b"tampered\n")
    with pytest.raises(review_ui.ReviewUIError, match="artifact_invalid"):
        review_ui._artifact(artifact_root, name, hashlib.sha256(expected).hexdigest())

    (review_plan / name).unlink()
    with pytest.raises(review_ui.ReviewUIError, match="artifact_invalid"):
        review_ui._artifact(artifact_root, name, hashlib.sha256(expected).hexdigest())
    (review_plan / name).symlink_to(run_b / name)
    with pytest.raises(review_ui.ReviewUIError, match="artifact_invalid"):
        review_ui._artifact(artifact_root, name, hashlib.sha256(expected).hexdigest())

    wrong_owner = input_root / "other-owner/review-plan/private-review"
    _write_private(wrong_owner / name, expected)
    review_plan.rename(tmp_path / "detached-review-plan")
    with pytest.raises(review_ui.ReviewUIError, match="artifact_invalid"):
        review_ui._review_plan_artifact_root(input_root, review_plan_ref)

    review_plan.parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "detached-review-plan").rename(review_plan)
    duplicate = input_root / "review-plan/duplicate/private-review"
    _write_private(duplicate / name, expected)
    with pytest.raises(review_ui.ReviewUIError, match="artifact_invalid"):
        review_ui._review_plan_artifact_root(input_root, review_plan_ref)
