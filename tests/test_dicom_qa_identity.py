from __future__ import annotations

import builtins
import copy
import hashlib
import importlib.util
import json
import sqlite3
import sys
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


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
    identity = {
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
    comparison = json.loads((first / "comparison-kernel/kernel-metadata.json").read_text())
    finalizer = json.loads((first / "review-finalizer-kernel/kernel-metadata.json").read_text())
    assert (
        run_a["kernel_sources"] == run_b["kernel_sources"] == [result["source_manifest_kernel_ref"]]
    )
    assert comparison["kernel_sources"] == [result["run_a_ref"], result["run_b_ref"]]
    assert finalizer["kernel_sources"] == [
        result["run_a_ref"],
        result["run_b_ref"],
        result["comparison_ref"],
        result["review_session_ref"],
    ]
    manifest = json.loads((first / "dataset/bundle-manifest.json").read_text())
    roles = {record["role"] for record in manifest["files"]}
    assert {
        "source_manifest_schema",
        "comparison_source",
        "review_ui_source",
        "review_notebook",
        "output_validator",
    } <= roles


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
        "comparison_sha256": "2" * 64,
        "review_finalizer_sha256": "3" * 64,
        "review_ui_sha256": "4" * 64,
        "review_notebook_sha256": "5" * 64,
        "output_validator_sha256": "6" * 64,
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
            "cohort_selection_version": finalize_review.QA_COHORT_SELECTION_VERSION,
            "kernel_version": 1,
            "checks": list(finalize_review.REVIEW_CHECKS),
            "statuses": ["PASS", "BLOCK", "NOT_APPLICABLE"],
            "artifact_presence_separate": True,
            "minimum_reviewed_studies": 100,
        },
    }
    manifest = {
        "kernel": {"code_file": "run.py", "sha256": hashes["runner_sha256"]},
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


def _case_index() -> dict[str, Any]:
    studies: list[dict[str, Any]] = [
        {
            "case_ordinal": ordinal,
            "study_uid": f"1.2.840.{ordinal}",
            "selection_stratum": [f"s{index}" for index in range(11)],
            "series": [
                {
                    "series_uid": f"1.2.840.{ordinal}.1",
                    "model_eligible": True,
                }
            ],
        }
        for ordinal in range(100)
    ]
    cohort = {
        "domain": "rsna-knee-dicom-qa-cohort-v2",
        "selection_version": finalize_review.QA_COHORT_SELECTION_VERSION,
        "studies": [
            {
                "study_uid": study["study_uid"],
                "selection_stratum": study["selection_stratum"],
                "eligible_series_uids": [study["series"][0]["series_uid"]],
            }
            for study in studies
        ],
    }
    coverage = [
        {
            "dimension": f"dimension_{index:02d}",
            "value": "represented",
            "population_studies": 100,
            "selected_studies": 100,
            "disposition": "covered",
            "source": "manifest-v2" if index < 4 else "full_run_terminal_records",
        }
        for index in range(19)
    ]
    return {
        "input_identity": {
            "source_manifest": {
                "audit_id": packager.SOURCE_MANIFEST_AUDIT_ID,
                "version": "manifest-v2",
                "source_manifest_artifact_sha256": "e" * 64,
            },
            "official_competition": {
                "slug": packager.COMPETITION_SLUG,
                "official_input_snapshot_sha256": "f" * 64,
            },
        },
        "qa_cohort_selection": {
            "selection_version": finalize_review.QA_COHORT_SELECTION_VERSION,
            "selected_studies": 100,
            "eligible_series": 100,
            "cohort_sha256": hashlib.sha256(
                finalize_review._canonical_json_bytes(cohort)
            ).hexdigest(),
            "source_manifest_gate": "pass",
            "coverage": coverage,
        },
        "studies": studies,
    }


def _review_context() -> dict[str, Any]:
    return {
        "organizer_plane": "sagittal",
        "physical_plane": "sagittal",
        "assigned_slot": "sagittal_fluid_sensitive",
        "retention_reasons": [],
        "missing_series_mask": [False, True, True, True, True, True],
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
    }


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
        "schema_version": 1,
        "artifact_type": "private-dicom-qa-review-plan",
        "status": "pending_private_human_review",
        "review_identity": identity,
        "rows": rows,
    }
    ledger = {
        "schema_version": 1,
        "artifact_type": "private-dicom-qa-completed-review-ledger",
        "status": "complete",
        "review_identity": identity,
        "plan_sha256": hashlib.sha256(finalize_review._canonical_json_bytes(plan)).hexdigest(),
        "completed_at_utc": "2026-08-09T01:02:03Z",
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


@pytest.mark.parametrize("mutation", ["cohort", "config", "bundle", "manifest", "input_version"])
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
        mutated_case["input_identity"]["source_manifest"]["source_manifest_artifact_sha256"] = (
            "0" * 64
        )
    else:
        mutated_config["input_identity"]["source_manifest"]["kernel_version"] = 2

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


def test_finalizer_validates_source_and_preprocessing_block_evidence() -> None:
    base = {
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


def test_reviewed_study_count_token_avoids_exact_public_cap_range() -> None:
    assert {finalize_review._count_token(count, public_cap=240) for count in (220, 239, 240)} == {
        "at_or_above_threshold"
    }
    assert finalize_review._reviewed_study_bounds("at_or_above_threshold") == (220, 240)
    assert finalize_review._reviewed_study_bounds("range_240_259") is None
    assert finalize_review._k20_range_bounds("at_or_above_threshold") is None


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
    run_a_ref = "test-owner/run-a"
    run_b_ref = "test-owner/run-b"
    artifact = input_root / "run-a/output/private-review/case_000000_series_000_review.json"
    artifact_payload = review_ui._canonical_json_bytes({"safe": True})
    _write_private(artifact, artifact_payload)
    _write_private(
        input_root / "run-b/output/private-review" / artifact.name,
        review_ui._canonical_json_bytes({"safe": False}),
    )
    plan = {
        "schema_version": 1,
        "artifact_type": "private-dicom-qa-review-plan",
        "status": "pending_private_human_review",
        "review_identity": {
            "review_bundle_id": "c5qa-12345678901234567890",
            "preprocessing": {"version": "dicom-model-v1"},
            "qa_cohort": {"sha256": "a" * 64},
            "kernels": {
                "run_a": {"ref": run_a_ref, "version": 1},
                "run_b": {"ref": run_b_ref, "version": 1},
            },
        },
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
    answers = iter(("START", "N" * 9, "P" * 8 + "N"))
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))
    shown: list[dict[str, Any]] = []
    monkeypatch.setattr(review_ui, "_show", lambda context, _paths: shown.append(context))

    assert review_ui.run_review(input_root=input_root, working_root=working_root) == (
        working_root / review_ui.LEDGER_BASENAME
    )
    assert {path.name for path in working_root.iterdir()} == {review_ui.LEDGER_BASENAME}
    ledger = json.loads((working_root / review_ui.LEDGER_BASENAME).read_text())
    assert ledger["status"] == "complete"
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _review_context()
    identity = {
        "review_bundle_id": "c5qa-12345678901234567890",
        "preprocessing": {"version": "dicom-model-v1"},
        "qa_cohort": {"sha256": "a" * 64},
        "kernels": {"run_a": {"ref": "test-owner/run-a", "version": 1}},
    }
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
        {(0, 0): ({"name": "case_000000_series_000_review.json", "sha256": "b" * 64},)},
        {(0, 0): context},
    )

    rows, run_a_ref = review_ui._validate_plan(plan)
    assert rows[0]["review_context"] == context
    assert run_a_ref == "test-owner/run-a"

    tampered = copy.deepcopy(plan)
    tampered["rows"][0]["review_context"]["missing_series_mask"][0] = True
    with pytest.raises(review_ui.ReviewUIError, match="plan_invalid"):
        review_ui._validate_plan(tampered)


def test_review_ui_rejects_run_a_ambiguity_and_tamper(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    run_a_ref = "test-owner/run-a"
    name = "case_000000_series_000_review.json"
    expected = review_ui._canonical_json_bytes({"run": "a"})
    run_a = input_root / "run-a/output/private-review"
    run_b = input_root / "run-b/output/private-review"
    _write_private(run_a / name, expected)
    _write_private(run_b / name, expected)

    artifact_root = review_ui._run_a_artifact_root(input_root, run_a_ref)
    assert artifact_root == run_a
    assert review_ui._artifact(artifact_root, name, hashlib.sha256(expected).hexdigest()) == (
        run_a / name
    )

    _write_private(run_a / name, b"tampered\n")
    with pytest.raises(review_ui.ReviewUIError, match="artifact_invalid"):
        review_ui._artifact(artifact_root, name, hashlib.sha256(expected).hexdigest())

    (run_a / name).unlink()
    with pytest.raises(review_ui.ReviewUIError, match="artifact_invalid"):
        review_ui._artifact(artifact_root, name, hashlib.sha256(expected).hexdigest())
    (run_a / name).symlink_to(run_b / name)
    with pytest.raises(review_ui.ReviewUIError, match="artifact_invalid"):
        review_ui._artifact(artifact_root, name, hashlib.sha256(expected).hexdigest())

    wrong_owner = input_root / "other-owner/run-a/private-review"
    _write_private(wrong_owner / name, expected)
    run_a.rename(tmp_path / "detached-run-a")
    with pytest.raises(review_ui.ReviewUIError, match="artifact_invalid"):
        review_ui._run_a_artifact_root(input_root, run_a_ref)

    run_a.parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "detached-run-a").rename(run_a)
    duplicate = input_root / "run-a/duplicate/private-review"
    _write_private(duplicate / name, expected)
    with pytest.raises(review_ui.ReviewUIError, match="artifact_invalid"):
        review_ui._run_a_artifact_root(input_root, run_a_ref)
