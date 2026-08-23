from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
COMMIT = "a" * 40
TIMESTAMP = 1_700_000_000


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


manifest_packager = _load_module(
    "package_manifest_bundle", ROOT / "scripts/package_manifest_bundle.py"
)
packager = _load_module("_dicom_qa_packager", ROOT / "scripts/package_dicom_qa_bundle.py")
validator = _load_module("_dicom_qa_validator", ROOT / "scripts/validate_dicom_qa_output.py")


def _wheel(path: Path, distribution: str, module_files: dict[str, str] | None = None) -> None:
    dist_info = f"{distribution.replace('-', '_')}-0.1.0.dist-info"
    entries = {
        f"{distribution.replace('-', '_')}/__init__.py": "",
        **(module_files or {}),
        f"{dist_info}/METADATA": (
            "Metadata-Version: 2.1\n"
            f"Name: {distribution}\n"
            "Version: 0.1.0\n"
            "Requires-Python: >=3.11,<3.13\n\n"
        ),
        f"{dist_info}/WHEEL": (
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ),
        f"{dist_info}/RECORD": "",
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)


def _source_manifest_fixture(source: Path, manifest_schema: Path) -> tuple[Path, Path]:
    root = source / "source-manifest-bundle"
    dataset = root / "dataset"
    kernel = root / "kernel"
    dataset.mkdir(parents=True)
    kernel.mkdir()
    runner_payload = b"SOURCE_MANIFEST_FIXTURE = True\n"
    runner_sha256 = hashlib.sha256(runner_payload).hexdigest()
    source_commit = "2" * 40
    run_config = {
        "schema_version": 1,
        "code_commit": source_commit,
        "bundle_sha256": packager.RUN_CONFIG_BUNDLE_PLACEHOLDER,
        "provenance": {
            "manifest_version": "manifest-v2",
            "manifest_schema_sha256": hashlib.sha256(manifest_schema.read_bytes()).hexdigest(),
        },
        "output_policy": {
            "private_remote_only": [
                {
                    "path": "audit-output/private_manifest.sqlite3",
                    "max_bytes": 8 * 1024**3,
                },
                {
                    "path": "audit-output/private_duplicate_groups.csv",
                    "max_bytes": 256 * 1024**2,
                },
                {
                    "path": "audit-output/private_preliminary_group_keys.csv",
                    "max_bytes": 256 * 1024**2,
                },
                {
                    "path": "audit-output/private_qa_samples.csv",
                    "max_bytes": 64 * 1024**2,
                },
                {
                    "path": "audit-output/private_artifact_inventory.json",
                    "max_bytes": 1024 * 1024,
                },
                {
                    "path": "audit-output/audit_key.bin",
                    "max_bytes": 64,
                    "exact_bytes": 32,
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
        "kernel": {"code_file": "run.py", "sha256": runner_sha256},
        "files": [normalized_record],
    }
    bundle_sha256 = hashlib.sha256(packager._canonical_json_bytes(identity)).hexdigest()
    run_config["bundle_sha256"] = bundle_sha256
    run_config_payload = packager._canonical_json_bytes(run_config)
    run_config_sha256 = hashlib.sha256(run_config_payload).hexdigest()
    manifest = {
        **identity,
        "bundle_sha256": bundle_sha256,
        "files": [
            {
                **normalized_record,
                "bytes": len(run_config_payload),
                "sha256": run_config_sha256,
            }
        ],
    }
    dataset_ref = "test-owner/" + manifest_packager._derive_slug(
        "rsna-knee-manifest-bundle", source_commit, bundle_sha256
    )
    kernel_ref = "test-owner/" + manifest_packager._derive_slug(
        "rsna-knee-manifest-audit", source_commit, bundle_sha256
    )
    (dataset / "run-config.json").write_bytes(run_config_payload)
    (dataset / "bundle-manifest.json").write_bytes(packager._canonical_json_bytes(manifest))
    (dataset / "dataset-metadata.json").write_bytes(
        packager._canonical_json_bytes(
            {
                "title": dataset_ref.partition("/")[2],
                "id": dataset_ref,
                "licenses": [{"name": "other"}],
            }
        )
    )
    (kernel / "run.py").write_bytes(runner_payload)
    (kernel / "kernel-metadata.json").write_bytes(
        packager._canonical_json_bytes(
            {
                "id": kernel_ref,
                "title": kernel_ref.partition("/")[2],
                "code_file": "run.py",
                "language": "python",
                "kernel_type": "script",
                "is_private": True,
                "enable_gpu": False,
                "enable_tpu": False,
                "enable_internet": False,
                "machine_shape": "",
                "dataset_sources": [dataset_ref],
                "competition_sources": [packager.COMPETITION_SLUG],
                "kernel_sources": [],
                "model_sources": [],
            }
        )
    )
    registry = source / "source-manifest-registry.sqlite3"
    with sqlite3.connect(registry) as connection:
        connection.execute(
            "CREATE TABLE audit_runs (audit_id TEXT PRIMARY KEY, status TEXT, "
            "config_hash TEXT, manifest_version TEXT)"
        )
        connection.execute(
            "INSERT INTO audit_runs VALUES (?, ?, ?, ?)",
            (
                packager.SOURCE_MANIFEST_AUDIT_ID,
                "completed",
                run_config_sha256,
                "manifest-v2",
            ),
        )
    for directory in (root, dataset, kernel):
        os.chmod(directory, 0o700)
    for path in (*dataset.iterdir(), *kernel.iterdir(), registry):
        os.chmod(path, 0o600)
    return root, registry


def _bundle_inputs(tmp_path: Path) -> dict[str, Any]:
    source = tmp_path / "source"
    source.mkdir()
    project = source / "rsna_knee-0.1.0-py3-none-any.whl"
    _wheel(
        project,
        "rsna-knee",
        {name: "" for name in packager.REQUIRED_PROJECT_WHEEL_MEMBERS},
    )
    dependencies: list[Path] = []
    for distribution, version in packager.REQUIRED_RUNTIME_PACKAGES.items():
        path = source / f"{distribution.replace('-', '_')}-{version}-py3-none-any.whl"
        _wheel(path, distribution)
        dependencies.append(path)
    preprocessing = source / "preprocessing.json"
    preprocessing.write_bytes((ROOT / "configs/preprocessing.v1.json").read_bytes())
    schema = source / "preprocessing.schema.json"
    schema.write_bytes((ROOT / "configs/preprocessing.v1.schema.json").read_bytes())
    manifest_schema = source / "manifest_schema.yaml"
    manifest_schema.write_bytes((ROOT / "configs/manifest_schema.yaml").read_bytes())
    pointer = source / "competition.json"
    pointer.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "contract": "../docs/competition_contract/contract.yaml",
            }
        )
    )
    contract = source / "contract.json"
    contract.write_text(
        json.dumps(
            {
                "identity": {"slug": packager.COMPETITION_SLUG},
                "runtime": {"internet_enabled": False, "cpu_limit_seconds": 32_400},
            }
        )
    )
    lock = source / "uv.lock"
    lock.write_text("version = 1\n")
    requirements = source / "runtime-requirements.txt"
    requirements.write_text("pillow==12.3.0\n")
    synthetic_preflight = source / packager.SYNTHETIC_PREFLIGHT_BASENAME
    synthetic_preflight.write_bytes(
        packager._canonical_json_bytes(packager.SYNTHETIC_PREFLIGHT_REPORT)
    )
    source_manifest_root, source_manifest_registry = _source_manifest_fixture(
        source, manifest_schema
    )
    return {
        "owner": "test-owner",
        "git_commit": COMMIT,
        "git_commit_timestamp": TIMESTAMP,
        "wheel_path": project,
        "dependency_wheel_paths": tuple(dependencies),
        "runtime_requirements_path": requirements,
        "preprocessing_config_path": preprocessing,
        "preprocessing_schema_path": schema,
        "manifest_schema_path": manifest_schema,
        "competition_config_path": pointer,
        "competition_contract_path": contract,
        "uv_lock_path": lock,
        "kernel_runner_path": ROOT / "kaggle/dicom_qa/run.py",
        "performance_smoke_path": ROOT / "kaggle/dicom_qa/performance_smoke.py",
        "comparison_path": ROOT / "kaggle/dicom_qa/compare_runs.py",
        "review_finalizer_path": ROOT / "kaggle/dicom_qa/finalize_review.py",
        "review_ui_path": ROOT / "kaggle/dicom_qa/review_ui.py",
        "output_validator_path": ROOT / "scripts/validate_dicom_qa_output.py",
        "synthetic_preflight_path": synthetic_preflight,
        "source_manifest_bundle_root": source_manifest_root,
        "source_manifest_registry_path": source_manifest_registry,
        "source_manifest_audit_id": packager.SOURCE_MANIFEST_AUDIT_ID,
    }


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _assembled(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    output = tmp_path / "bundle"
    result = packager._assemble_bundle(output=output, **_bundle_inputs(tmp_path))
    return output, result


def _runner() -> Any:
    path = ROOT / "kaggle/dicom_qa/run.py"
    return validator._runner_module(hashlib.sha256(path.read_bytes()).hexdigest())


def test_bundle_with_core_reuse_stays_verifiable(tmp_path: Path) -> None:
    inputs = _bundle_inputs(tmp_path)
    core_reuse = {
        "core_lineage_id": "preprocess-0001-dicom-pipeline-r15",
        "core_certificate_payload_sha256": "c" * 64,
        "upstream_refs": {
            "performance_smoke": "owner/core-smoke",
            "run_a": "owner/core-a",
            "run_b": "owner/core-b",
            "comparison": "owner/core-cmp",
        },
    }
    bundle = tmp_path / "bundle"
    packager._assemble_bundle(output=bundle, **inputs, core_reuse=core_reuse)

    runner = _runner()
    manifest = json.loads((bundle / "dataset/bundle-manifest.json").read_text())
    records = runner._validated_records(bundle / "dataset", manifest)
    run_config, _, dependencies = runner._verify_run_config(bundle / "dataset", manifest, records)

    assert run_config["core_reuse"] == core_reuse
    assert dependencies


def _comparator() -> Any:
    path = ROOT / "kaggle/dicom_qa/compare_runs.py"
    return validator._comparison_module(hashlib.sha256(path.read_bytes()).hexdigest())


def _finalizer() -> Any:
    path = ROOT / "kaggle/dicom_qa/finalize_review.py"
    return validator._finalizer_module(hashlib.sha256(path.read_bytes()).hexdigest())


def test_bundle_is_deterministic_private_offline_and_identity_bound(tmp_path: Path) -> None:
    inputs = _bundle_inputs(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_result = packager._assemble_bundle(output=first, **inputs)
    second_result = packager._assemble_bundle(output=second, **inputs)

    assert first_result["bundle_sha256"] == second_result["bundle_sha256"]
    assert _file_hashes(first) == _file_hashes(second)
    metadata = json.loads((first / "kernel-a/kernel-metadata.json").read_text())
    assert metadata["is_private"] is True
    assert metadata["enable_internet"] is False
    assert metadata["enable_gpu"] is False
    assert metadata["enable_tpu"] is False
    assert metadata["competition_sources"] == [packager.COMPETITION_SLUG]
    assert metadata["kernel_sources"] == [first_result["source_manifest_kernel_ref"]]

    run_config = json.loads((first / "dataset/run-config.json").read_text())
    assert run_config["runtime"] == {
        "internet": False,
        "accelerator": "cpu",
        "self_deadline_seconds": 27_000,
        "outer_kill_seconds": 28_800,
    }
    assert run_config["output_policy"] == {
        "run_private_remote_only": list(packager.RUN_PRIVATE_OUTPUTS),
        "run_downloadable": list(packager.RUN_DOWNLOADABLE_OUTPUTS),
        "review_private_remote_only": list(packager.REVIEW_PRIVATE_OUTPUTS),
        "review_private_remote_patterns": list(packager.REVIEW_PRIVATE_PATTERN_OUTPUTS),
        "review_downloadable": list(packager.REVIEW_DOWNLOADABLE_OUTPUTS),
        "session_log": packager.SESSION_LOG_POLICY,
        "run_max_remote_bytes": 548 * 1024**2 + 384 * 1024,
        "run_max_download_bytes": 384 * 1024,
        "review_max_remote_bytes": 8 * 1024**3 + 66 * 1024**2 + 512 * 1024,
        "review_max_download_bytes": 512 * 1024,
    }
    competition_limit = json.loads((first / "dataset/competition-contract.json").read_text())[
        "runtime"
    ]["cpu_limit_seconds"]
    assert packager.OUTER_KILL_SECONDS - packager.SELF_DEADLINE_SECONDS >= 1_800
    assert competition_limit - 3_600 >= packager.OUTER_KILL_SECONDS
    assert run_config["selection"] == {
        "source": "full_run_terminal_records_plus_authenticated_manifest_v2",
        "minimum_studies": 100,
        "minimum_is_not_maximum": True,
        "represented_value_quota": 2,
        "stratum_registry_version": packager.QA_STRATUM_REGISTRY_VERSION,
        "stratum_registry_sha256": packager.QA_STRATUM_REGISTRY_SHA256,
        "cohort_selection_version": packager.QA_COHORT_SELECTION_VERSION,
        "dimensions": list(packager.REQUIRED_REVIEW_DIMENSIONS),
    }
    assert len(run_config["selection"]["dimensions"]) == 25
    assert run_config["review_policy"] == {
        "protocol_version": packager.REVIEW_PROTOCOL_VERSION,
        "instructions_version": packager.REVIEW_INSTRUCTIONS_VERSION,
        "cohort_selection_version": packager.QA_COHORT_SELECTION_VERSION,
        "stratum_registry_version": packager.QA_STRATUM_REGISTRY_VERSION,
        "stratum_registry_sha256": packager.QA_STRATUM_REGISTRY_SHA256,
        "kernel_version": 1,
        "checks": list(packager.REVIEW_CHECKS),
        "statuses": list(packager.REVIEW_STATUSES),
        "artifact_presence_separate": True,
        "minimum_reviewed_studies": 100,
    }
    preflight_path = first / "dataset/synthetic-preflight.json"
    assert json.loads(preflight_path.read_text()) == packager.SYNTHETIC_PREFLIGHT_REPORT
    manifest = json.loads((first / "dataset/bundle-manifest.json").read_text())
    smoke_source = (first / "dataset/performance_smoke.py").read_bytes()
    smoke_policy_path = first / "dataset/performance-smoke-policy.json"
    smoke_policy = json.loads(smoke_policy_path.read_text())
    smoke_source_sha256 = hashlib.sha256(smoke_source).hexdigest()
    smoke_policy_sha256 = hashlib.sha256(smoke_policy_path.read_bytes()).hexdigest()
    assert set(path.name for path in (first / "performance-smoke-kernel").iterdir()) == {
        "kernel-metadata.json",
        "performance_smoke.py",
    }
    smoke_metadata = json.loads(
        (first / "performance-smoke-kernel/kernel-metadata.json").read_text()
    )
    assert smoke_metadata["id"] == first_result["performance_smoke_ref"]
    assert smoke_metadata["code_file"] == "performance_smoke.py"
    assert smoke_metadata["is_private"] is True
    assert smoke_metadata["enable_internet"] is False
    assert smoke_metadata["enable_gpu"] is False
    assert smoke_metadata["enable_tpu"] is False
    assert smoke_metadata["dataset_sources"] == [first_result["dataset_ref"]]
    assert smoke_metadata["kernel_sources"] == [first_result["source_manifest_kernel_ref"]]
    assert smoke_metadata["competition_sources"] == [packager.COMPETITION_SLUG]
    assert smoke_metadata["model_sources"] == []
    assert (first / "performance-smoke-kernel/performance_smoke.py").read_bytes() == smoke_source
    assert smoke_policy == packager._performance_smoke_policy(smoke_source_sha256)
    assert manifest["performance_smoke"] == {
        "code_file": "performance_smoke.py",
        "sha256": smoke_source_sha256,
        "policy_file": "performance-smoke-policy.json",
        "policy_sha256": smoke_policy_sha256,
    }
    assert run_config["provenance"]["performance_smoke_sha256"] == smoke_source_sha256
    assert run_config["provenance"]["performance_smoke_policy_sha256"] == smoke_policy_sha256
    records_by_role = {
        record["role"]: record
        for record in manifest["files"]
        if record["role"] != "dependency_wheel"
    }
    assert records_by_role["performance_smoke_source"]["sha256"] == smoke_source_sha256
    assert records_by_role["performance_smoke_policy"]["sha256"] == smoke_policy_sha256
    preflight_records = [
        record for record in manifest["files"] if record["role"] == "synthetic_preflight"
    ]
    assert preflight_records == [
        {
            "path": "synthetic-preflight.json",
            "role": "synthetic_preflight",
            "source_path": "generated/synthetic-preflight.json",
            "bytes": preflight_path.stat().st_size,
            "sha256": hashlib.sha256(preflight_path.read_bytes()).hexdigest(),
        }
    ]
    assert run_config["provenance"]["synthetic_preflight_sha256"] == preflight_records[0]["sha256"]
    template_metadata = json.loads(
        (first / "review-ui-template-kernel/kernel-metadata.json").read_text()
    )
    assert template_metadata["is_private"] is True
    assert template_metadata["dataset_sources"] == [first_result["dataset_ref"]]
    assert template_metadata["kernel_sources"] == [
        first_result["run_a_ref"],
        first_result["run_b_ref"],
        first_result["comparison_ref"],
        first_result["review_plan_ref"],
    ]
    plan_metadata = json.loads((first / "review-plan-kernel/kernel-metadata.json").read_text())
    assert plan_metadata["kernel_sources"] == [
        first_result["performance_smoke_ref"],
        first_result["run_a_ref"],
        first_result["run_b_ref"],
        first_result["comparison_ref"],
    ]
    assert plan_metadata["competition_sources"] == [packager.COMPETITION_SLUG]
    finalizer_metadata = json.loads(
        (first / "review-finalizer-kernel/kernel-metadata.json").read_text()
    )
    assert finalizer_metadata["kernel_sources"] == [
        first_result["run_a_ref"],
        first_result["run_b_ref"],
        first_result["comparison_ref"],
        first_result["review_plan_ref"],
        first_result["review_session_ref"],
    ]
    verified, _, manifest = validator.load_verified_policy(
        first / "dataset/run-config.json",
        first / "dataset/bundle-manifest.json",
        expected_commit=COMMIT,
        expected_bundle=first_result["bundle_sha256"],
    )
    assert verified == run_config
    assert manifest["bundle_sha256"] == first_result["bundle_sha256"]


def test_built_project_wheel_passes_offline_synthetic_production_path(tmp_path: Path) -> None:
    wheel_root = tmp_path / "wheel"
    wheel_root.mkdir()
    project_wheel = packager._build_wheel(ROOT, TIMESTAMP, wheel_root)
    requirements = tmp_path / "requirements.txt"
    subprocess.run(
        [
            "uv",
            "export",
            "--frozen",
            "--no-dev",
            "--no-editable",
            "--no-emit-project",
            "--format",
            "requirements.txt",
            "--no-annotate",
            "--no-header",
            "--output-file",
            str(requirements),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        timeout=120,
    )
    site_root = tmp_path / "site"
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--offline",
            "--target",
            str(site_root),
            "--requirements",
            str(requirements),
            "--no-deps",
            "--no-progress",
            str(project_wheel),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        timeout=120,
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(ROOT / "scripts/run_dicom_qa_synthetic_preflight.py"),
            "--site-root",
            str(site_root),
            "--config",
            str(ROOT / "configs/preprocessing.v1.json"),
            "--code-commit",
            COMMIT,
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        timeout=120,
    )

    assert completed.returncode == 0
    assert completed.stderr == b""
    assert completed.stdout == packager._canonical_json_bytes(packager.SYNTHETIC_PREFLIGHT_REPORT)


def test_packaged_preflight_resolves_linux_targets_before_isolated_host_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project.whl"
    project.write_bytes(b"project")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("pillow==12.3.0\n")
    host = tmp_path / "host"
    linux = tmp_path / "linux"
    host.mkdir()
    linux.mkdir()
    host_wheel = host / "pillow-12.3.0-py3-none-any.whl"
    linux_wheel = linux / "pillow-12.3.0-py3-none-any.whl"
    host_wheel.write_bytes(b"host")
    linux_wheel.write_bytes(b"linux")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(command)
        if "-S" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=packager._canonical_json_bytes(packager.SYNTHETIC_PREFLIGHT_REPORT),
                stderr=b"",
            )
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(packager.subprocess, "run", fake_run)
    payload = packager._run_packaged_synthetic_preflight(
        project_wheel=project,
        host_dependency_wheels=(host_wheel,),
        linux_dependency_wheels=(linux_wheel,),
        runtime_requirements=requirements,
        preprocessing_config=ROOT / "configs/preprocessing.v1.json",
        code_commit=COMMIT,
        entrypoint=ROOT / "scripts/run_dicom_qa_synthetic_preflight.py",
    )

    assert payload == packager._canonical_json_bytes(packager.SYNTHETIC_PREFLIGHT_REPORT)
    assert len(calls) == 4
    assert [call[call.index("--python-version") + 1] for call in calls[:2]] == ["3.11", "3.12"]
    for call in calls[:2]:
        assert "--no-index" in call
        assert [
            call[index + 1] for index, argument in enumerate(call) if argument == "--platform"
        ] == list(packager.TARGET_PLATFORMS)
    assert "--no-index" in calls[2] and "--platform" not in calls[2]
    assert calls[3][1:3] == ["-I", "-S"]


def test_bundle_rejects_synthetic_preflight_mutation(tmp_path: Path) -> None:
    inputs = _bundle_inputs(tmp_path)
    report_path = inputs["synthetic_preflight_path"]
    report = json.loads(report_path.read_text())
    report["checks"]["no_horizontal_flip"] = False
    report_path.write_bytes(packager._canonical_json_bytes(report))

    with pytest.raises(packager.PackagingError, match="synthetic_preflight_invalid"):
        packager._assemble_bundle(output=tmp_path / "mutated", **inputs)


def test_bundle_requires_pillow_and_both_compressed_decoder_families(tmp_path: Path) -> None:
    inputs = _bundle_inputs(tmp_path)
    inputs["dependency_wheel_paths"] = tuple(
        path
        for path in inputs["dependency_wheel_paths"]
        if packager._wheel_distribution(path) != "pillow"
    )
    with pytest.raises(packager.PackagingError, match="required_runtime_wheel_missing"):
        packager._assemble_bundle(output=tmp_path / "missing", **inputs)


def test_registry_selection_is_deterministic_and_minimum_is_not_a_maximum() -> None:
    runner = _runner()
    studies = tuple(
        runner.CohortStudy(
            study_uid=f"1.2.840.1000.{index + 1}",
            stratum=("common",) * 11,
            dimensions=tuple(
                (
                    dimension,
                    (f"model_{index:03d}" if dimension == "scanner_model" else "common",),
                )
                for dimension in runner.REQUIRED_REVIEW_DIMENSIONS
            ),
            eligible_series_uids=(f"1.2.840.2000.{index + 1}",),
        )
        for index in range(101)
    )

    first = runner._select_after_full_pass(
        studies,
        source_manifest_available=True,
        target=100,
        minimum_eligible=100,
    )
    second = runner._select_after_full_pass(
        tuple(reversed(studies)),
        source_manifest_available=True,
        target=100,
        minimum_eligible=100,
    )

    assert first == second
    assert len(first.studies) == 101
    assert set(first.coverage) == {
        "rows",
        "total_required_strata",
        "total_satisfied",
        "unsatisfied_strata",
        "cohort_size",
        "all_required_represented_registry_values_satisfy_quotas",
        "registry_version",
        "selector_version",
        "manifest_version",
    }
    assert first.coverage["cohort_size"] == 101
    assert first.coverage["all_required_represented_registry_values_satisfy_quotas"] is True
    assert first.coverage["unsatisfied_strata"] == ()
    assert first.coverage["registry_version"] == runner.QA_STRATUM_REGISTRY_VERSION
    assert first.coverage["selector_version"] == runner.QA_COHORT_SELECTION_VERSION
    assert first.coverage["manifest_version"] == runner.SOURCE_MANIFEST_VERSION
    scanner_rows = [row for row in first.coverage["rows"] if row["dimension"] == "scanner_model"]
    assert len(scanner_rows) == 101
    assert all(
        row["population"] == row["required_quota"] == row["selected"] == 1
        and row["quota_met"] is True
        for row in scanner_rows
    )
    assert first.cohort_sha256 == second.cohort_sha256


def test_deadline_installs_handler_before_arm_and_disarms_before_restore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    events: list[tuple[object, ...]] = []
    previous_handler = object()

    def fake_getsignal(signal_number: int) -> object:
        events.append(("get", signal_number))
        return previous_handler

    monkeypatch.setattr(runner.signal, "getsignal", fake_getsignal)

    def fake_signal(signal_number: int, handler: object) -> None:
        events.append(("handler", signal_number, handler))

    timers = iter(((7.0, 0.0), (0.0, 0.0), (0.0, 0.0)))

    def fake_setitimer(timer: int, seconds: float, interval: float = 0.0) -> tuple[float, float]:
        events.append(("timer", timer, seconds, interval))
        return next(timers)

    monkeypatch.setattr(runner.signal, "signal", fake_signal)
    monkeypatch.setattr(runner.signal, "setitimer", fake_setitimer)

    with runner._enforce_self_deadline(11.0):
        events.append(("body",))

    assert events[1][0] == "handler"
    assert events[2] == ("timer", runner.signal.ITIMER_REAL, 11.0, 0.0)
    assert events[4] == ("timer", runner.signal.ITIMER_REAL, 0.0, 0.0)
    assert events[5] == ("handler", runner.signal.SIGALRM, previous_handler)
    assert events[6] == ("timer", runner.signal.ITIMER_REAL, 7.0, 0.0)


def test_unsafe_decode_states_are_fatal_and_other_failures_are_private_classifications() -> None:
    runner = _runner()
    for code in runner.FATAL_DECODE_ISSUE_CODES:
        error = SimpleNamespace(issue=SimpleNamespace(value=code))
        assert runner._fatal_decode_failure(error) is True

    explicit = SimpleNamespace(
        issue=SimpleNamespace(value="constant_slice"),
        stage="pixel_validation",
        root_cause="fixed_root_cause",
        exception_type="pydicom.errors.InvalidDicomError",
    )
    assert runner._fatal_decode_failure(explicit) is False
    assert runner._private_pipeline_failure(explicit) == {
        "issue": "constant_slice",
        "stage": "pixel_validation",
        "root_cause": "fixed_root_cause",
        "exception_type": "pydicom.errors.InvalidDicomError",
    }
    explicit.exception_type = "unsafe free-text detail"
    assert runner._private_pipeline_failure(explicit)["exception_type"] == "unspecified"


def test_private_reconstruction_ledger_is_complete_and_excludes_tensor_values() -> None:
    runner = _runner()

    @dataclass(frozen=True)
    class Geometry:
        positions: tuple[float, ...]
        affine_is_regular: bool

    @dataclass(frozen=True)
    class Ledger:
        ordered_input_checksums: tuple[str, ...]

    @dataclass(frozen=True)
    class Provenance:
        input_checksum: str
        output_checksum: str

    result = SimpleNamespace(
        tensor=SimpleNamespace(shape=(8, 2, 256, 256), dtype="float32"),
        channel_names=("base", "local_contrast"),
        sampled_ordered_indices=(0, 3, 7),
        sampled_projected_positions_mm=(0.0, 3.0, 7.0),
        geometry=Geometry((0.0, 1.0), True),
        clipping_values=(10.0, 900.0),
        normalization_statistics=(10.0, 890.0),
        output_pixel_spacing_row_column_mm=(0.5, 0.5),
        output_affine_lps_slice_row_column=((1.0, 0.0, 0.0, 0.0),),
        laterality="L",
        ledger=Ledger(("a" * 64, "b" * 64)),
        provenance=Provenance("c" * 64, "d" * 64),
    )
    record = runner._private_reconstruction_record(result)

    assert set(record) == {
        "source_slice_count",
        "output_tensor_shape",
        "output_tensor_dtype",
        "channel_names",
        "sampled_ordered_indices",
        "sampled_projected_positions_mm",
        "geometry",
        "clipping_values",
        "normalization_statistics",
        "output_pixel_spacing_row_column_mm",
        "output_affine_lps_slice_row_column",
        "laterality",
        "transformation_ledger",
        "provenance",
    }
    assert record["source_slice_count"] == 2
    assert record["output_tensor_shape"] == [8, 2, 256, 256]
    assert "tensor" not in record


def _remote_records(runner: Any) -> list[dict[str, object]]:
    records = [
        {"name": f"{runner.OUTPUT_DIRECTORY}/{name}", "size": 896}
        for name in (*runner.PRIVATE_OUTPUT_POLICY, *runner.DOWNLOADABLE_OUTPUT_POLICY)
    ]
    suffixes = (
        "contact.png",
        "orthogonal.png",
        "histogram.png",
        "animation.gif",
        "before_after.png",
        "review.json",
        "metadata.json",
    )
    for case in range(100):
        for suffix in suffixes:
            records.append(
                {
                    "name": (
                        f"{runner.OUTPUT_DIRECTORY}/{runner.PRIVATE_REVIEW_DIRECTORY}/"
                        f"case_{case:06d}_series_000_{suffix}"
                    ),
                    "size": 896,
                }
            )
    return records


def _remote_run_records(runner: Any) -> list[dict[str, object]]:
    return [
        {"name": f"{runner.OUTPUT_DIRECTORY}/{name}", "size": 896}
        for name in (*runner.RUN_PRIVATE_OUTPUT_POLICY, *runner.RUN_DOWNLOADABLE_OUTPUT_POLICY)
    ]


def test_full_run_listing_is_core_only_and_cohort_plan_bound() -> None:
    runner = _runner()
    progress = validator._expected_progress_events(runner)
    assert progress[0] == {"event": "dicom_qa_progress", "phase": "full_pass", "code": "start"}
    assert all(event["phase"] != "performance_smoke" for event in progress)
    assert set(runner.RUN_PRIVATE_OUTPUT_POLICY) == {
        "private_full_run_manifest.jsonl",
        "private_full_run_metrics.json",
        "private_cohort_plan.json",
    }
    assert set(runner.RUN_DOWNLOADABLE_OUTPUT_POLICY) == {
        "sanitized_summary.json",
        "sanitized_artifact_inventory.json",
    }
    records = _remote_run_records(runner)
    validator._validate_run_listing((json.dumps(records).encode(),), runner)

    for stale in (
        "private_case_index.json",
        "private_artifact_inventory.json",
        "private-review/case_000000_series_000_contact.png",
        "benchmark.md",
    ):
        altered = [*records, {"name": f"{runner.OUTPUT_DIRECTORY}/{stale}", "size": 896}]
        with pytest.raises(validator.OutputValidationError, match="remote_name_not_allowed"):
            validator._validate_run_listing((json.dumps(altered).encode(),), runner)


def test_paginated_remote_listing_checks_visible_private_review_without_download(
    tmp_path: Path,
) -> None:
    runner = _runner()
    records = _remote_records(runner)
    first = b"Next Page Token = page_two\n" + json.dumps(records[:300]).encode()
    second = json.dumps(records[300:]).encode()
    run_config = {"output_policy": {"max_remote_bytes": 8 * 1024**3 + 1024**2}}

    validator.validate_remote_listing((first, second), run_config, runner)

    records.append({"name": "dicom-qa-output/private-review/raw.dcm", "size": 896})
    second = json.dumps(records[300:]).encode()
    with pytest.raises(validator.OutputValidationError, match="remote_review_name_invalid"):
        validator.validate_remote_listing((first, second), run_config, runner)


def test_review_plan_listing_owns_qa_artifacts_and_bound_plan() -> None:
    runner = _runner()
    finalizer = _finalizer()
    assert (
        frozenset(
            {
                "contact.png",
                "histogram.png",
                "animation.gif",
                "before_after.png",
                "review.json",
                "metadata.json",
            }
        )
        == finalizer.REQUIRED_SUFFIXES
    )
    assert finalizer.REQUIRED_SUFFIXES | {"orthogonal.png"} == finalizer.ALLOWED_SUFFIXES
    records = [
        *_remote_records(runner),
        {
            "name": (f"{finalizer.TEMPLATE_OUTPUT_DIRECTORY}/{finalizer.REVIEW_PLAN_BASENAME}"),
            "size": 896,
        },
    ]
    validator._validate_review_output_listing(
        (json.dumps(records).encode(),), runner, finalizer=finalizer
    )

    missing_plan = records[:-1]
    with pytest.raises(validator.OutputValidationError, match="remote_required_output_missing"):
        validator._validate_review_output_listing(
            (json.dumps(missing_plan).encode(),), runner, finalizer=finalizer
        )

    without_optional_orthogonal = [
        record
        for record in records
        if not str(record["name"]).endswith("case_000000_series_000_orthogonal.png")
    ]
    validator._validate_review_output_listing(
        (json.dumps(without_optional_orthogonal).encode(),), runner, finalizer=finalizer
    )

    missing_required = [
        record
        for record in without_optional_orthogonal
        if not str(record["name"]).endswith("case_000000_series_000_contact.png")
    ]
    with pytest.raises(validator.OutputValidationError, match="remote_review_output_incomplete"):
        validator._validate_review_output_listing(
            (json.dumps(missing_required).encode(),), runner, finalizer=finalizer
        )

    duplicate = [*records, records[0]]
    with pytest.raises(validator.OutputValidationError, match="remote_duplicate_name"):
        validator._validate_review_output_listing(
            (json.dumps(duplicate).encode(),), runner, finalizer=finalizer
        )

    extra_cross_extension = [
        *records,
        {
            "name": (
                f"{runner.OUTPUT_DIRECTORY}/{runner.PRIVATE_REVIEW_DIRECTORY}/"
                "case_000000_series_000_contact.gif"
            ),
            "size": 896,
        },
    ]
    with pytest.raises(validator.OutputValidationError, match="remote_review_output_incomplete"):
        validator._validate_review_output_listing(
            (json.dumps(extra_cross_extension).encode(),), runner, finalizer=finalizer
        )


def _summary(run_config: dict[str, Any], runner: Any, runner_sha256: str) -> dict[str, Any]:
    benchmark = {
        "iterations": 3,
        "decode_time": {
            "minimum_seconds": 0.1,
            "median_seconds": 0.2,
            "maximum_seconds": 0.3,
        },
        "preprocessing_time": {
            "minimum_seconds": 0.2,
            "median_seconds": 0.3,
            "maximum_seconds": 0.4,
        },
        "representative_tensor_cache_mib_ceiling": 2,
        "process_peak_rss_mib_ceiling": 512,
        "peak_rss_increase_mib_ceiling": 64,
        "cpu_parallelism": [
            {
                "workers": 1,
                "tasks": 3,
                "wall_seconds": 1.0,
                "tasks_per_second": 3.0,
                "speedup_vs_one_worker": 1.0,
            }
        ],
        "kaggle_compatibility": {
            "python_version": "3.11.9",
            "platform_system": "Linux",
            "platform_machine": "x86_64",
            "cpu_count": 4,
            "numpy_version": "2.4.6",
            "pydicom_version": "3.0.2",
            "python_supported": True,
            "linux_runtime_observed": True,
            "offline_bundle_verified": True,
            "kaggle_runtime_verified": True,
            "accelerator": "cpu",
            "horizontal_flip": False,
            "through_plane_resampling": False,
        },
        "deterministic_replay": True,
    }
    performance = {
        "runtime_seconds": {
            "total_run_wall_seconds": 100.0,
            "full_dataset_pipeline_wall_seconds": 90.0,
        },
        "phase_seconds": {
            "decode_accumulated_seconds": 30.0,
            "preprocessing_accumulated_seconds": 40.0,
            "slot_assignment_seconds": 2.0,
            "qa_generation_seconds": 10.0,
            "cache_generation_seconds": 8.0,
        },
        "resources": {
            "process_peak_rss_mib_ceiling": 512,
            "logical_cache_power_of_two_mib_ceiling": 8,
            "peak_ephemeral_cache_power_of_two_mib_ceiling": 4,
            "peak_private_working_disk_power_of_two_mib_ceiling": 16,
        },
        "cpu": {"capacity_threads": 4, "average_utilization_percent": 50.0},
        "throughput": {
            "scope": "complete_private_run_including_post_pass_qa_and_representative_benchmark",
            "disclosure_policy": "fixed_order_of_magnitude_rate_buckets_v1",
            "decode_files_per_second_token": "one_to_below_ten_per_second",
            "preprocessing_series_per_second_token": "one_to_below_ten_per_second",
            "end_to_end_files_per_second_token": "one_to_below_ten_per_second",
            "end_to_end_series_per_second_token": "one_to_below_ten_per_second",
            "end_to_end_studies_per_second_token": "one_to_below_ten_per_second",
        },
        "representative_cpu_scaling": {
            "selection_method": "model_eligible_slice_count_rank_small_median_large_v1",
            "requested_workers": [1, 2, 4, 8],
            "available_workers": [1],
            "unavailable_workers": [2, 4, 8],
            "profiles": [
                {
                    "profile": profile,
                    "iterations": 3 if profile == "median" else 1,
                    "cpu_parallelism": benchmark["cpu_parallelism"],
                }
                for profile in ("small", "median", "large")
            ],
        },
        "inference_runtime_budget": {
            "limit_seconds": 32_400,
            "limit_source": "bundled_competition_contract",
            "measured_preprocessing_pipeline_wall_seconds": 90.0,
            "remaining_after_preprocessing_seconds": 32_310.0,
            "preprocessing_within_limit": True,
            "model_runtime_included": False,
            "model_viability_assessed": False,
            "scope": "measured_preprocessing_only",
        },
        "determinism_status": "pending_independent_run_comparison",
    }
    return {
        "schema_version": 1,
        "artifact_type": "dicom-qa-sanitized-aggregate",
        "status": "complete_pending_human_review",
        "provenance": {
            "git_commit": run_config["code_commit"],
            "bundle_sha256": run_config["bundle_sha256"],
            "runner_sha256": runner_sha256,
            "review_finalizer_sha256": run_config["provenance"]["review_finalizer_sha256"],
            "preprocessing_config_file_sha256": run_config["provenance"][
                "preprocessing_config_sha256"
            ],
            "preprocessing_configuration_hash": "b" * 64,
            "preprocessing_version": "dicom-model-v1",
            "source_manifest_version": "manifest-v2",
            "qa_cohort_selection_version": packager.QA_COHORT_SELECTION_VERSION,
            "dicom_library_versions": [
                {"package": name, "version": "1.0.0"}
                for name in (
                    "numpy",
                    "pydicom",
                    "pylibjpeg",
                    "pylibjpeg-libjpeg",
                    "pylibjpeg-openjpeg",
                )
            ],
        },
        "selection": {
            "source": "authenticated_run_a_cohort_plan_v1",
            "minimum_studies": 100,
            "minimum_is_not_maximum": True,
            "selected_studies": "at_least_100",
            "eligible_studies": "at_least_100",
            "stratified": True,
            "all_required_represented_registry_values_satisfy_quotas": True,
            "deterministic_constrained_greedy": True,
            "selected_after_full_pass": True,
            "source_manifest_authenticated": True,
            "represented_value_quota": 2,
            "cohort_selection_version": packager.QA_COHORT_SELECTION_VERSION,
            "stratum_registry_version": packager.QA_STRATUM_REGISTRY_VERSION,
            "stratum_registry_sha256": packager.QA_STRATUM_REGISTRY_SHA256,
        },
        "pipeline": {
            "full_training_dataset_processed": True,
            "all_series_terminal": True,
            "integrity_gate": "pass",
            "unresolved_blockers": "zero",
            "series_slot_system_exercised": True,
            "model_eligible_series": "at_least_100",
            "failure_reporting": "fixed_codes_with_case_details_private",
            "all_preprocessing_provenance_private": True,
        },
        "qa": {
            "rendered_series": "at_least_100",
            "all_model_eligible_series_rendered": True,
            "repeat_render_byte_identical": True,
            "full_cohort_replay_byte_identical": True,
            "review_files_present": True,
            "visual_review_status": "pending_private_human_review",
            "systematic_ordering_or_orientation_error": "not_evaluated_pending_human_review",
        },
        "anatomical_safety": run_config["anatomical_safety"],
        "privacy": {
            "downloaded_case_details": False,
            "downloaded_identifiers": False,
            "downloaded_paths": False,
            "downloaded_pixels": False,
            "private_review_artifacts_remote_only": True,
        },
        "performance": performance,
        "benchmark": benchmark,
    }


def _review_summary(
    run_config: dict[str, Any], manifest: dict[str, Any], finalizer: Any
) -> dict[str, Any]:
    static = finalizer._public_review_identity(run_config, manifest)
    return {
        "schema_version": 1,
        "artifact_type": "dicom-qa-human-review-sanitized-aggregate",
        "status": "complete",
        "completed_at_utc": "2026-08-09T01:02:03Z",
        "versions": {
            "preprocessing": static["preprocessing"]["version"],
            "source_manifest": static["source_manifest"]["version"],
            "source_manifest_audit": static["source_manifest"]["audit_id"],
            "cohort_selection": static["cohort_selection_version"],
            "review_protocol": finalizer.REVIEW_PROTOCOL_VERSION,
        },
        "review": {
            "reviewed_studies": "range_100_119",
            "eligible_series_reviewed": "range_100_119",
            "represented_strata": "all_required_represented_registry_values_satisfy_quotas",
            "all_eligible_series_complete": True,
            "all_nine_checks_terminal": True,
            "artifact_presence_verified": True,
            "review_identity_bound": True,
            "check_results": {check: "PASS" for check in validator.REVIEW_CHECKS},
            "block_decisions": "zero",
            "zero_blocks": True,
        },
        "privacy": {
            "case_rows_downloadable": False,
            "identifiers_downloadable": False,
            "cohort_hash_downloadable": False,
            "private_artifact_hashes_downloadable": False,
            "free_text_downloadable": False,
            "pixels_downloadable": False,
        },
    }


def test_review_summary_rejects_exact_numeric_and_non_k20_disclosures_without_240_cap(
    tmp_path: Path,
) -> None:
    bundle, result = _assembled(tmp_path)
    run_config, _, manifest = validator.load_verified_policy(
        bundle / "dataset/run-config.json",
        bundle / "dataset/bundle-manifest.json",
        expected_commit=COMMIT,
        expected_bundle=result["bundle_sha256"],
    )
    finalizer = _finalizer()
    assert [finalizer._count_token(count) for count in (220, 239, 240, 259)] == [
        "range_220_239",
        "range_220_239",
        "range_240_259",
        "range_240_259",
    ]
    assert finalizer._reviewed_study_bounds("range_240_259") == (240, 259)
    summary = _review_summary(run_config, manifest, finalizer)
    for key, value in (
        ("reviewed_studies", 100),
        ("eligible_series_reviewed", 100),
        ("block_decisions", 0),
        ("reviewed_studies", "range_101_120"),
        ("reviewed_studies", "range_241_260"),
        ("eligible_series_reviewed", "at_least_100"),
        ("eligible_series_reviewed", "at_or_above_threshold"),
    ):
        malformed = deepcopy(summary)
        malformed["review"][key] = value
        with pytest.raises(validator.OutputValidationError, match="review_summary_invalid"):
            validator._validate_review_summary_payload(
                packager._canonical_json_bytes(malformed), run_config, manifest, finalizer
            )

    expanded = deepcopy(summary)
    expanded["review"]["reviewed_studies"] = "range_240_259"
    expanded["review"]["eligible_series_reviewed"] = "range_240_259"
    validator._validate_review_summary_payload(
        packager._canonical_json_bytes(expanded), run_config, manifest, finalizer
    )

    old_schema = deepcopy(summary)
    old_schema["review"].pop("represented_strata")
    old_schema["review"]["represented_strata_count"] = 1
    old_schema["review"]["all_represented_strata_covered"] = True
    with pytest.raises(validator.OutputValidationError, match="review_summary_invalid"):
        validator._validate_review_summary_payload(
            packager._canonical_json_bytes(old_schema), run_config, manifest, finalizer
        )


def test_private_review_context_is_strict_and_bound_into_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finalizer = _finalizer()
    context = {
        "organizer_plane": "sagittal",
        "physical_plane": "coronal",
        "laterality": "unknown",
        "laterality_transform": "none",
        "horizontal_flip_applied": False,
        "assigned_slot": "additional_or_duplicate",
        "retention_reasons": ["conflicting_plane_metadata"],
        "missing_series_mask": [True, False, True, True, True, True],
        "sibling_series": [
            {
                "series_ordinal": 0,
                "slot": "additional_or_duplicate",
                "terminal_state": "model_eligible",
                "model_eligible": True,
                "retention_reasons": ["conflicting_plane_metadata"],
                "quality_blocked_reasons": [],
            },
            {
                "series_ordinal": 1,
                "slot": "sagittal_structural",
                "terminal_state": "quality_blocked",
                "model_eligible": False,
                "retention_reasons": ["blocked_quality"],
                "quality_blocked_reasons": ["duplicate_slices"],
            },
        ],
        "check_9_applicable": True,
        "check_9_reason_codes": [
            "missing_diagnostic_slot",
            "additional_or_duplicate_series",
            "non_model_eligible_sibling",
            "retention_reason",
            "quality_block_reason",
        ],
    }
    assert finalizer._validate_review_context(context, 0) == context
    monkeypatch.setattr(finalizer, "_review_case_ordinals", lambda _eligible: (0,))
    monkeypatch.setattr(
        finalizer,
        "_private_review_identity",
        lambda _static, _case_index: {"review_bundle_id": "c5qa-test"},
    )
    plan = finalizer._template(
        {},
        {},
        {0: (("stratum",), (0,))},
        {(0, 0): ({"name": "case_000000_series_000_review.json", "sha256": "a" * 64},)},
        {(0, 0): context},
    )
    assert plan["rows"][0]["review_context"] == context

    malformed_contexts = []
    extra = deepcopy(context)
    extra["study_uid"] = "1.2.3"
    malformed_contexts.append(extra)
    short_mask = deepcopy(context)
    short_mask["missing_series_mask"] = [True] * 5
    malformed_contexts.append(short_mask)
    wrong_slot = deepcopy(context)
    wrong_slot["assigned_slot"] = "sagittal_fluid_sensitive"
    malformed_contexts.append(wrong_slot)
    missing_assigned_slot = deepcopy(context)
    missing_assigned_slot["assigned_slot"] = "sagittal_fluid_sensitive"
    missing_assigned_slot["retention_reasons"] = []
    missing_assigned_slot["sibling_series"][0]["slot"] = "sagittal_fluid_sensitive"
    missing_assigned_slot["sibling_series"][0]["retention_reasons"] = []
    missing_assigned_slot["missing_series_mask"][0] = True
    malformed_contexts.append(missing_assigned_slot)
    skipped_ordinal = deepcopy(context)
    skipped_ordinal["sibling_series"][1]["series_ordinal"] = 2
    malformed_contexts.append(skipped_ordinal)
    free_text = deepcopy(context)
    free_text["sibling_series"][1]["quality_blocked_reasons"] = ["reviewer_note"]
    malformed_contexts.append(free_text)
    transformed_laterality = deepcopy(context)
    transformed_laterality["laterality_transform"] = "inferred_from_filename"
    malformed_contexts.append(transformed_laterality)
    for malformed in malformed_contexts:
        with pytest.raises(finalizer.ReviewFinalizationError, match="private_case_index_invalid"):
            finalizer._validate_review_context(malformed, 0)


def _comparison_summary() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "dicom-run-determinism-aggregate",
        "status": "pass",
        "independent_runs_compared": True,
        "exact_manifest_byte_equality": True,
        "deterministic_metrics_equal": True,
        "cohort_plan_byte_equality": True,
        "unresolved_mismatches": "zero",
        "private_case_details_downloaded": False,
    }


def _final_performance_report(
    run_config: dict[str, Any], manifest: dict[str, Any], runner: Any, finalizer: Any
) -> dict[str, Any]:
    return json.loads(
        finalizer._final_performance_report(
            run_a_payload=packager._canonical_json_bytes(
                _summary(run_config, runner, manifest["kernel"]["sha256"])
            ),
            comparison_payload=packager._canonical_json_bytes(_comparison_summary()),
            review_payload=packager._canonical_json_bytes(
                _review_summary(run_config, manifest, finalizer)
            ),
            run_config=run_config,
            manifest=manifest,
            runner=runner,
        )
    )


def test_local_validator_accepts_only_three_sanitized_files(tmp_path: Path) -> None:
    bundle, result = _assembled(tmp_path)
    run_config = json.loads((bundle / "dataset/run-config.json").read_text())
    manifest = json.loads((bundle / "dataset/bundle-manifest.json").read_text())
    runner = _runner()
    runner_sha256 = manifest["kernel"]["sha256"]
    summary = _summary(run_config, runner, runner_sha256)
    summary_payload = runner._canonical_json_bytes(summary)
    benchmark_payload = runner._render_benchmark(summary)
    inventory_payload = runner._canonical_json_bytes(
        {
            "schema_version": 1,
            "artifact_type": "dicom-qa-sanitized-artifact-inventory",
            "provenance": {
                "git_commit": run_config["code_commit"],
                "bundle_sha256": result["bundle_sha256"],
            },
            "artifacts": [
                {
                    "name": "benchmark.md",
                    "kind": "aggregate_documentation",
                    "bytes": len(benchmark_payload),
                    "sha256": hashlib.sha256(benchmark_payload).hexdigest(),
                },
                {
                    "name": "sanitized_summary.json",
                    "kind": "aggregate_json",
                    "bytes": len(summary_payload),
                    "sha256": hashlib.sha256(summary_payload).hexdigest(),
                },
            ],
        }
    )
    output = tmp_path / "download"
    output.mkdir()
    (output / "sanitized_summary.json").write_bytes(summary_payload)
    (output / "benchmark.md").write_bytes(benchmark_payload)
    (output / "sanitized_artifact_inventory.json").write_bytes(inventory_payload)

    validator.validate_local_output(output, run_config, runner, manifest)

    session_log = output / "session.log"
    plan_events = [
        {"event": "dicom_qa_review_started"},
        *validator._expected_progress_events(
            runner,
            sequence_attribute="PLAN_PROGRESS_EVENT_SEQUENCE",
            event_name="dicom_qa_plan_progress",
        ),
        {"event": "dicom_qa_review_template_complete"},
    ]
    session_log.write_text(
        json.dumps(
            [
                {"stream_name": "stderr", "time": 1, "data": "platform warning\n"},
                {
                    "stream_name": "stdout",
                    "time": 2,
                    "data": b"".join(
                        packager._canonical_json_bytes(event) for event in plan_events
                    ).decode("ascii"),
                },
            ]
        )
    )
    validator.validate_local_output(output, run_config, runner, manifest)
    session_log.write_bytes(
        b"".join(
            packager._canonical_json_bytes(event)
            for event in [
                {"event": "dicom_qa_started"},
                {"event": "dicom_qa_complete"},
            ]
        )
    )
    with pytest.raises(validator.OutputValidationError, match="log_completion_invalid"):
        validator.validate_local_output(output, run_config, runner, manifest)
    session_log.unlink()

    (output / "private_case_index.json").write_text("{}")
    with pytest.raises(validator.OutputValidationError, match="local_output_allowlist_invalid"):
        validator.validate_local_output(output, run_config, runner, manifest)


def test_review_plan_log_contract_matches_automatic_producer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    runner = _runner()
    finalizer = _finalizer()
    run_config = tmp_path / "run-config.json"
    manifest = tmp_path / "bundle-manifest.json"
    run_config.write_text("{}")
    manifest.write_text("{}")
    args = SimpleNamespace(
        automatic_materialization=True,
        run_config=run_config,
        bundle_manifest=manifest,
    )
    calls: list[tuple[object, bytes, bytes, str]] = []

    def materialize(
        received: object,
        *,
        run_config_payload: bytes,
        manifest_payload: bytes,
        finalizer_sha256: str,
    ) -> None:
        calls.append((received, run_config_payload, manifest_payload, finalizer_sha256))
        for phase, code in runner.PLAN_PROGRESS_EVENT_SEQUENCE:
            runner._safe_event("dicom_qa_plan_progress", phase=phase, code=code)

    monkeypatch.setattr(finalizer, "_automatic_args", lambda: args)
    monkeypatch.setattr(finalizer, "_materialize_automatic_template", materialize)
    monkeypatch.setattr(finalizer, "_self_hash", lambda: "f" * 64)
    monkeypatch.setattr(sys, "argv", ["finalize_review.py"])

    assert finalizer.main() == 0
    assert calls == [(args, b"{}", b"{}", "f" * 64)]
    assert [json.loads(line) for line in capfd.readouterr().out.splitlines()] == [
        {"event": "dicom_qa_review_started"},
        *validator._expected_progress_events(
            runner,
            sequence_attribute="PLAN_PROGRESS_EVENT_SEQUENCE",
            event_name="dicom_qa_plan_progress",
        ),
        {"event": "dicom_qa_review_template_complete"},
    ]


def test_local_core_run_validator_accepts_only_two_safe_files_and_exact_gate(
    tmp_path: Path,
) -> None:
    runner_sha256 = "a" * 64
    summary = {
        "status": "complete_pending_comparison",
        "provenance": {"runner_sha256": runner_sha256},
        "pipeline": {
            "full_training_dataset_processed": True,
            "all_series_terminal": True,
            "integrity_gate": "pass",
            "unresolved_blockers": "zero",
        },
        "selection": {
            "cohort_plan_status": "complete",
            "all_required_represented_registry_values_satisfy_quotas": True,
        },
    }
    summary_payload = b'{"safe":"summary"}\n'
    inventory_payload = b'{"safe":"inventory"}\n'
    calls: list[tuple[str, bytes]] = []

    def validate_summary(payload: bytes, received_config: object) -> dict[str, Any]:
        assert received_config == {"privacy": {"canary": "safe-canary"}}
        calls.append(("summary", payload))
        return summary

    def validate_inventory(payload: bytes, *, run_config: object, summary_payload: bytes) -> None:
        assert run_config == {"privacy": {"canary": "safe-canary"}}
        assert summary_payload == b'{"safe":"summary"}\n'
        calls.append(("inventory", payload))

    runner = SimpleNamespace(
        OUTPUT_DIRECTORY="dicom-qa-output",
        SESSION_LOG_PATTERN=r"[a-z0-9][a-z0-9_-]{0,99}\.log",
        RUN_DOWNLOADABLE_OUTPUT_POLICY={
            "sanitized_summary.json": ("aggregate_json", 1024),
            "sanitized_artifact_inventory.json": ("aggregate_json", 1024),
        },
        _validate_run_summary=validate_summary,
        _validate_run_inventory=validate_inventory,
    )
    run_config = {"privacy": {"canary": "safe-canary"}}
    output = tmp_path / "core"
    output.mkdir()
    (output / "sanitized_summary.json").write_bytes(summary_payload)
    (output / "sanitized_artifact_inventory.json").write_bytes(inventory_payload)

    validated = validator.validate_local_run_output(
        output, run_config, runner, {"kernel": {"sha256": runner_sha256}}
    )
    validator._validate_run_exit_gate(validated)
    assert calls == [
        ("summary", summary_payload),
        ("inventory", inventory_payload),
    ]

    for forbidden in ("benchmark.md", "private_case_index.json"):
        forbidden_path = output / forbidden
        forbidden_path.write_text("forbidden")
        with pytest.raises(validator.OutputValidationError, match="local_output_allowlist_invalid"):
            validator.validate_local_run_output(
                output, run_config, runner, {"kernel": {"sha256": runner_sha256}}
            )
        forbidden_path.unlink()

    for altered in (
        {**summary, "status": "complete_pending_human_review"},
        {
            **summary,
            "pipeline": {**summary["pipeline"], "unresolved_blockers": "present"},
        },
        {
            **summary,
            "selection": {**summary["selection"], "cohort_plan_status": "pending"},
        },
        {
            **summary,
            "selection": {
                **summary["selection"],
                "all_required_represented_registry_values_satisfy_quotas": False,
            },
        },
    ):
        with pytest.raises(
            validator.OutputValidationError, match="dicom_integrity_exit_gate_failed"
        ):
            validator._validate_run_exit_gate(altered)


@pytest.mark.parametrize(
    "private_digest",
    [
        "source_manifest_artifact_sha256",
        "official_input_snapshot_sha256",
        "qa_cohort_sha256",
    ],
)
def test_sanitized_summary_rejects_private_identity_digests(
    tmp_path: Path, private_digest: str
) -> None:
    bundle, _result = _assembled(tmp_path)
    run_config = json.loads((bundle / "dataset/run-config.json").read_text())
    manifest = json.loads((bundle / "dataset/bundle-manifest.json").read_text())
    runner = _runner()
    summary = _summary(run_config, runner, manifest["kernel"]["sha256"])
    summary["provenance"][private_digest] = "f" * 64

    with pytest.raises(runner.SafeRunError, match="sanitized_summary_invalid"):
        runner._validate_summary(packager._canonical_json_bytes(summary), run_config)


def test_fd_level_suppression_and_sensitive_download_rejection(
    capfd: pytest.CaptureFixture[str],
) -> None:
    runner = _runner()
    runner._decoder_preflight()
    with runner._silence_process_output():
        runner._safe_event("dicom_qa_progress", phase="full_pass", code="q1")
        print("private-marker")
        os.write(1, b"native-private-marker")
        os.write(2, b"native-private-marker")
    stdout, stderr = capfd.readouterr()
    assert stdout == '{"code":"q1","event":"dicom_qa_progress","phase":"full_pass"}\n'
    assert stderr == ""

    with pytest.raises(runner.SafeRunError, match="downloadable_privacy_invalid"):
        runner._scan_downloadable(b"1.2.840.10008.1.2.4.90", "unused-canary")


def test_progress_log_requires_an_exact_safe_prefix(tmp_path: Path) -> None:
    runner = _runner()
    run_config = {"privacy": {"canary": "RSNA_PRIVATE_CANARY_TEST"}}
    expected = validator._expected_progress_events(runner)
    root = tmp_path / "failure"
    root.mkdir()
    log = root / "session.log"

    def write(events: list[dict[str, str]]) -> None:
        log.write_bytes(b"".join(packager._canonical_json_bytes(event) for event in events))

    final = {
        "event": "dicom_qa_failed",
        "phase": "processing",
        "code": "self_deadline_exceeded",
    }
    write([{"event": "dicom_qa_started"}, *expected[:4], final])
    assert validator.validate_failure_log(root, run_config, runner) == (
        "processing",
        "self_deadline_exceeded",
    )

    stdout = b"".join(
        packager._canonical_json_bytes(event)
        for event in [{"event": "dicom_qa_started"}, *expected[:4], final]
    ).decode("ascii")
    wrapper = [
        {"stream_name": "stderr", "time": 1, "data": "platform warning\n"},
        {"stream_name": "stdout", "time": 2, "data": stdout},
    ]
    log.write_text(json.dumps(wrapper))
    assert validator.validate_failure_log(root, run_config, runner) == (
        "processing",
        "self_deadline_exceeded",
    )
    wrapper[0]["data"] = run_config["privacy"]["canary"]
    log.write_text(json.dumps(wrapper))
    with pytest.raises(validator.OutputValidationError, match="log_privacy_invalid"):
        validator.validate_failure_log(root, run_config, runner)

    invalid_progress = (
        expected[1:4],
        [expected[1], expected[0]],
        [*expected, expected[-1]],
    )
    for events in invalid_progress:
        write([{"event": "dicom_qa_started"}, *events, final])
        with pytest.raises(validator.OutputValidationError, match="failure_log_completion_invalid"):
            validator.validate_failure_log(root, run_config, runner)


def test_performance_smoke_failure_log_uses_its_bound_event_protocol(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _runner()
    run_config = {"privacy": {"canary": "RSNA_PRIVATE_CANARY_TEST"}}
    root = tmp_path / "failure"
    root.mkdir()
    log = root / "session.log"
    started = {"event": "dicom_qa_performance_smoke_started"}
    progress = [
        {
            "event": "dicom_qa_performance_smoke_progress",
            "phase": "performance_smoke",
            "code": code,
        }
        for code in ("start", "complete")
    ]
    failed = {
        "event": "dicom_qa_performance_smoke_failed",
        "phase": "performance_smoke",
        "code": "self_deadline_exceeded",
    }

    def write(events: list[dict[str, str]]) -> None:
        log.write_bytes(b"".join(packager._canonical_json_bytes(event) for event in events))

    for length in range(3):
        write([started, *progress[:length], failed])
        assert validator.validate_failure_log(root, run_config, runner) == (
            "performance_smoke",
            "self_deadline_exceeded",
        )
    for phase, length in (("bundle", 0), ("authentication", 0), ("output", 2)):
        write([started, *progress[:length], {**failed, "phase": phase}])
        assert validator.validate_failure_log(root, run_config, runner) == (
            phase,
            "self_deadline_exceeded",
        )

    write([started, progress[0], failed])
    monkeypatch.setattr(
        validator,
        "load_verified_policy",
        lambda *_args, **_kwargs: (run_config, runner, {}),
    )
    result = validator.main(
        [
            "--run-config",
            str(tmp_path / "run-config.json"),
            "--expected-commit",
            COMMIT,
            "--expected-bundle",
            "b" * 64,
            "--failure-log-dir",
            str(root),
        ]
    )
    assert result == 0
    assert capsys.readouterr().out == (
        "dicom_qa_output_validation=PASS mode=failure "
        "phase=performance_smoke code=self_deadline_exceeded\n"
    )
    invalid = (
        [started, progress[1], failed],
        [started, *progress, progress[-1], failed],
        [started, progress[0], {**failed, "event": "dicom_qa_failed"}],
        [started, progress[0], {**failed, "phase": "processing"}],
        *(
            [started, *progress[:length], {**failed, "phase": phase}]
            for phase, length in (
                ("bundle", 1),
                ("bundle", 2),
                ("authentication", 1),
                ("authentication", 2),
                ("output", 0),
                ("output", 1),
            )
        ),
    )
    for events in invalid:
        write(events)
        with pytest.raises(validator.OutputValidationError, match="failure_log_completion_invalid"):
            validator.validate_failure_log(root, run_config, runner)


def test_review_failure_log_uses_its_bound_event_protocol(tmp_path: Path) -> None:
    runner = _runner()
    run_config = {"privacy": {"canary": "RSNA_PRIVATE_CANARY_TEST"}}
    root = tmp_path / "failure"
    root.mkdir()
    log = root / "session.log"
    started = {"event": "dicom_qa_review_started"}
    progress = validator._expected_progress_events(
        runner,
        sequence_attribute="PLAN_PROGRESS_EVENT_SEQUENCE",
        event_name="dicom_qa_plan_progress",
    )
    failed = {"event": "dicom_qa_review_failed", "code": "input_discovery_invalid"}

    def write(events: list[dict[str, str]]) -> None:
        log.write_bytes(b"".join(packager._canonical_json_bytes(event) for event in events))

    for length in range(len(progress) + 1):
        write([started, *progress[:length], failed])
        assert validator.validate_failure_log(root, run_config, runner) == (
            "review",
            "input_discovery_invalid",
        )

    invalid = (
        [started, progress[1], failed],
        [started, *progress, progress[-1], failed],
        [started, {**failed, "event": "dicom_qa_failed"}],
        [started, {**failed, "phase": "review"}],
    )
    for events in invalid:
        write(events)
        with pytest.raises(validator.OutputValidationError, match="failure_log_completion_invalid"):
            validator.validate_failure_log(root, run_config, runner)


def test_duplicate_json_keys_and_noncanonical_policy_are_rejected() -> None:
    runner = _runner()
    with pytest.raises(runner.SafeRunError, match="sanitized_summary_invalid"):
        runner._json_object(
            b'{"status":"complete","status":"private text"}\n',
            "sanitized_summary_invalid",
        )
    with pytest.raises(validator.OutputValidationError, match="remote_listing_invalid"):
        validator._listing_page(b'[{"name":"safe.json","name":"private.dcm","size":1}]')


@pytest.mark.parametrize(
    "record",
    [
        {},
        {"size": None},
        {"size": -1},
        {"size": 0},
        {"size": "896"},
        {"size": "8x96"},
        {"size": "896 XB"},
        {"size": "1 KB"},
        {"size": 896.0},
        {"size": float("nan")},
        {"size": float("inf")},
        {"size": True},
        {"size": 896, "unit": "KB"},
        {"size": 896, "sizeUnit": "KiB"},
        {"bytes": 896},
        {"totalBytes": 896},
        {"size": 896, "bytes": 32},
    ],
)
def test_kernel_listing_size_rejects_ambiguous_or_non_integer_values(
    record: dict[str, object],
) -> None:
    record = {"name": "safe.json", **record}
    with pytest.raises(validator.OutputValidationError, match="remote_size"):
        validator._kernel_listing_records((json.dumps([record]).encode(),))


def test_kernel_listing_rejects_mixed_size_schemas() -> None:
    records = [
        {"name": "first.json", "size": 896},
        {"name": "second.json", "bytes": 32},
    ]
    with pytest.raises(validator.OutputValidationError, match="remote_size"):
        validator._kernel_listing_records((json.dumps(records).encode(),))


@pytest.mark.parametrize("value", (1 << 63, 10**100))
def test_kernel_listing_rejects_wrong_or_overflow_numeric_size(value: int) -> None:
    record = {"name": "safe.json", "size": value}
    with pytest.raises(validator.OutputValidationError, match="remote_size_invalid"):
        validator._kernel_listing_records((json.dumps([record]).encode(),))


def test_authenticated_listing_handles_real_cli_pagination_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = b'Next Page Token = token_2\n[{"name":"first.json","size":1}]\n'
    second = b'[{"name":"second.json","size":2}]\n'
    calls: list[tuple[str, ...]] = []

    def fake_cli(arguments: tuple[str, ...], **_kwargs: object) -> bytes:
        calls.append(arguments)
        return first if len(calls) == 1 else second

    monkeypatch.setattr(validator, "_run_kaggle_cli", fake_cli)
    pages = validator._authenticated_listing("owner/kernel", 1)

    assert pages == (first, second)
    assert calls[0][:4] == ("kernels", "files", "owner/kernel/1", "--page-size")
    assert calls[1][-2:] == ("--page-token", "token_2")
    assert [record["name"] for record in validator._listing_records(pages)] == [
        "first.json",
        "second.json",
    ]


def _install_fake_dataset_cli(
    monkeypatch: pytest.MonkeyPatch,
    *,
    ref: str,
    files: dict[str, int],
    status: str = "ready",
    version: object = 1,
    private: bool = True,
    metadata_envelope: bool = True,
) -> list[tuple[str, ...]]:
    calls: list[tuple[str, ...]] = []

    def fake_cli(arguments: tuple[str, ...], **_kwargs: object) -> bytes:
        calls.append(arguments)
        if arguments[:2] == ("datasets", "status"):
            assert arguments == ("datasets", "status", ref, "--format", "json")
            return json.dumps({"status": status, "current_version_number": version}).encode()
        if arguments[:2] == ("datasets", "metadata"):
            assert arguments[:3] == ("datasets", "metadata", ref)
            path = Path(arguments[arguments.index("--path") + 1])
            slug = ref.split("/", 1)[1]
            info = {
                "datasetId": 1729,
                "datasetSlug": slug,
                "title": slug,
                "isPrivate": private,
            }
            (path / "dataset-metadata.json").write_text(
                json.dumps({"info": info} if metadata_envelope else info)
            )
            return b"metadata_saved\n"
        if arguments[:2] == ("datasets", "files"):
            assert arguments[:3] == ("datasets", "files", f"{ref}/1")
            return json.dumps(
                [{"name": name, "totalBytes": size} for name, size in files.items()]
            ).encode()
        raise AssertionError("unexpected CLI command")

    monkeypatch.setattr(validator, "_run_kaggle_cli", fake_cli)
    return calls


def test_authenticated_dataset_snapshot_is_private_ready_v1_and_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ref = "test-owner/private-bundle"
    expected = {"bundle-manifest.json": 101, "run-config.json": 202}
    calls = _install_fake_dataset_cli(
        monkeypatch,
        ref=ref,
        files=expected,
    )

    snapshot = validator._authenticated_dataset_snapshot(ref, expected)

    assert snapshot == {
        "dataset_id": 1729,
        "dataset_slug": "private-bundle",
        "is_private": True,
        "status": "ready",
        "version": 1,
        "files": tuple(sorted(expected.items())),
    }
    assert [call[:2] for call in calls] == [
        ("datasets", "status"),
        ("datasets", "metadata"),
        ("datasets", "files"),
    ]

    with pytest.raises(validator.OutputValidationError, match="dataset_identity_invalid"):
        validator._authenticated_dataset_snapshot(f"test-owner/{'a' * 51}", {"only.bin": 4})


def test_authenticated_dataset_snapshot_rejects_flat_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ref = "test-owner/private-bundle"
    _install_fake_dataset_cli(
        monkeypatch,
        ref=ref,
        files={"only.bin": 4},
        metadata_envelope=False,
    )

    with pytest.raises(validator.OutputValidationError, match="dataset_metadata_invalid"):
        validator._authenticated_dataset_snapshot(ref, {"only.bin": 4})


@pytest.mark.parametrize(
    ("status", "version", "private", "files", "error"),
    [
        ("creating", 1, True, {"only.bin": 4}, "dataset_status_invalid"),
        ("ready", 2, True, {"only.bin": 4}, "dataset_status_invalid"),
        ("ready", 1.0, True, {"only.bin": 4}, "dataset_status_invalid"),
        ("ready", 1, False, {"only.bin": 4}, "dataset_metadata_invalid"),
        (
            "ready",
            1,
            True,
            {"only.bin": 4, "unexpected.bin": 1},
            "dataset_file_set_invalid",
        ),
        ("ready", 1, True, {}, "dataset_file_set_invalid"),
    ],
)
def test_authenticated_dataset_snapshot_rejects_unready_public_version_or_file_drift(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    version: object,
    private: bool,
    files: dict[str, int],
    error: str,
) -> None:
    ref = "test-owner/private-bundle"
    _install_fake_dataset_cli(
        monkeypatch,
        ref=ref,
        files=files,
        status=status,
        version=version,
        private=private,
    )

    with pytest.raises(validator.OutputValidationError, match=error):
        validator._authenticated_dataset_snapshot(ref, {"only.bin": 4})


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("config", "bundle_verification_failed"),
        ("expected_bundle", "expected_bundle_mismatch"),
        ("manifest", "bundle_verification_failed"),
    ],
)
def test_verified_policy_rejects_config_bundle_or_manifest_identity_mismatch(
    tmp_path: Path, mutation: str, error: str
) -> None:
    bundle, result = _assembled(tmp_path)
    run_config_path = bundle / "dataset/run-config.json"
    manifest_path = bundle / "dataset/bundle-manifest.json"
    expected_bundle = result["bundle_sha256"]
    if mutation == "config":
        run_config = json.loads(run_config_path.read_text())
        run_config["workers"] += 1
        run_config_path.write_bytes(packager._canonical_json_bytes(run_config))
    elif mutation == "manifest":
        manifest = json.loads(manifest_path.read_text())
        manifest["provenance"]["git_commit"] = "c" * 40
        manifest_path.write_bytes(packager._canonical_json_bytes(manifest))
    else:
        expected_bundle = "f" * 64

    with pytest.raises(validator.OutputValidationError, match=error):
        validator.load_verified_policy(
            run_config_path,
            manifest_path,
            expected_commit=COMMIT,
            expected_bundle=expected_bundle,
        )


def test_template_kernel_metadata_is_exact_private_offline_and_source_bound(
    tmp_path: Path,
) -> None:
    bundle, result = _assembled(tmp_path)
    run_config = json.loads((bundle / "dataset/run-config.json").read_text())
    metadata = json.loads((bundle / "review-ui-template-kernel/kernel-metadata.json").read_text())
    metadata.update({"id_no": 1729, "keywords": [], "docker_image": ""})
    ref = validator._derived_stage_kernel_ref(run_config, "review_ui")
    assert ref == result["review_ui_template_ref"]
    expected_sources = [
        result["run_a_ref"],
        result["run_b_ref"],
        result["comparison_ref"],
        result["review_plan_ref"],
    ]
    validated = validator._validate_exact_kernel_metadata(
        metadata,
        ref=ref,
        expected_code_file="review_ui.ipynb",
        expected_kernel_type="notebook",
        expected_dataset_sources=[result["dataset_ref"]],
        expected_kernel_sources=expected_sources,
        expected_competition_sources=[],
    )
    assert validated["dataset_sources"] == [result["dataset_ref"]]
    assert validated["kernel_sources"] == expected_sources
    assert validated["competition_sources"] == []
    assert validated["model_sources"] == []
    assert validated["is_private"] is True
    assert validated["enable_internet"] is False

    mutations: tuple[dict[str, object], ...] = (
        {"is_private": False},
        {"enable_internet": True},
        {"dataset_sources": [result["dataset_ref"], "test-owner/unexpected"]},
        {"kernel_sources": []},
        {"competition_sources": [packager.COMPETITION_SLUG]},
        {"model_sources": ["test-owner/unexpected"]},
        {"unexpected_field": "unexpected"},
    )
    for mutation in mutations:
        altered = {**metadata, **mutation}
        with pytest.raises(validator.OutputValidationError, match="kernel_metadata_invalid"):
            validator._validate_exact_kernel_metadata(
                altered,
                ref=ref,
                expected_code_file="review_ui.ipynb",
                expected_kernel_type="notebook",
                expected_dataset_sources=[result["dataset_ref"]],
                expected_kernel_sources=expected_sources,
                expected_competition_sources=[],
            )


def test_review_plan_and_finalizer_metadata_bind_the_split_qa_stage(tmp_path: Path) -> None:
    bundle, result = _assembled(tmp_path)
    plan = json.loads((bundle / "review-plan-kernel/kernel-metadata.json").read_text())
    plan.update({"id_no": 1729, "keywords": [], "docker_image": ""})
    plan_sources = [
        result["performance_smoke_ref"],
        result["run_a_ref"],
        result["run_b_ref"],
        result["comparison_ref"],
    ]
    validator._validate_exact_kernel_metadata(
        plan,
        ref=result["review_plan_ref"],
        expected_code_file="finalize_review.py",
        expected_kernel_type="script",
        expected_dataset_sources=[result["dataset_ref"]],
        expected_kernel_sources=plan_sources,
        expected_competition_sources=[packager.COMPETITION_SLUG],
    )
    for mutation in (
        {"competition_sources": []},
        {"kernel_sources": [*plan_sources, result["source_manifest_kernel_ref"]]},
    ):
        with pytest.raises(validator.OutputValidationError, match="kernel_metadata_invalid"):
            validator._validate_exact_kernel_metadata(
                {**plan, **mutation},
                ref=result["review_plan_ref"],
                expected_code_file="finalize_review.py",
                expected_kernel_type="script",
                expected_dataset_sources=[result["dataset_ref"]],
                expected_kernel_sources=plan_sources,
                expected_competition_sources=[packager.COMPETITION_SLUG],
            )

    finalizer = json.loads((bundle / "review-finalizer-kernel/kernel-metadata.json").read_text())
    finalizer.update({"id_no": 1730, "keywords": [], "docker_image": ""})
    finalizer_sources = [
        result["run_a_ref"],
        result["run_b_ref"],
        result["comparison_ref"],
        result["review_plan_ref"],
        result["review_session_ref"],
    ]
    validator._validate_exact_kernel_metadata(
        finalizer,
        ref=result["review_finalizer_ref"],
        expected_code_file="finalize_review.py",
        expected_kernel_type="script",
        expected_dataset_sources=[result["dataset_ref"]],
        expected_kernel_sources=finalizer_sources,
        expected_competition_sources=[],
    )
    with pytest.raises(validator.OutputValidationError, match="kernel_metadata_invalid"):
        validator._validate_exact_kernel_metadata(
            {
                **finalizer,
                "kernel_sources": [
                    source for source in finalizer_sources if source != result["review_plan_ref"]
                ],
            },
            ref=result["review_finalizer_ref"],
            expected_code_file="finalize_review.py",
            expected_kernel_type="script",
            expected_dataset_sources=[result["dataset_ref"]],
            expected_kernel_sources=finalizer_sources,
            expected_competition_sources=[],
        )


def test_full_private_workflow_kernel_refs_are_exact_and_content_addressed(
    tmp_path: Path,
) -> None:
    bundle, result = _assembled(tmp_path)
    run_config = json.loads((bundle / "dataset/run-config.json").read_text())
    suffix = f"{COMMIT[:7]}-{result['bundle_sha256'][:12]}"
    expected_prefixes = {
        "performance_smoke": "rsna-knee-dqa-smoke",
        "run_a": "rsna-knee-dqa-a",
        "run_b": "rsna-knee-dqa-b",
        "comparator": "rsna-knee-dqa-cmp",
        "plan": "rsna-knee-dqa-plan",
        "review_ui": "rsna-knee-dqa-ui",
        "review_session": "rsna-knee-dqa-review",
        "finalizer": "rsna-knee-dqa-final",
    }
    assert {
        stage: validator._derived_stage_kernel_ref(run_config, stage) for stage in expected_prefixes
    } == {stage: f"test-owner/{prefix}-{suffix}" for stage, prefix in expected_prefixes.items()}
    with pytest.raises(validator.OutputValidationError, match="kernel_identity_invalid"):
        validator._derived_stage_kernel_ref(run_config, "unknown")


def _kernel_api_payload(ref: str) -> dict[str, object]:
    slug = ref.partition("/")[2]
    return {
        "current_version_number": 1,
        "enable_internet": False,
        "is_private": True,
        "ref": ref,
        "slug": slug,
        "title": slug,
    }


def test_kernel_api_metadata_requires_exact_private_offline_v1_identity() -> None:
    ref = "test-owner/private-kernel"
    assert validator._validate_kernel_api_metadata(
        _kernel_api_payload(ref), ref=ref, expected_version=1
    ) == _kernel_api_payload(ref)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_version",
        "wrong_version_type",
        "wrong_version",
        "wrong_slug_identity",
        "wrong_owner",
        "public",
        "internet_enabled",
        "malformed",
    ],
)
def test_kernel_api_metadata_rejects_ambiguous_identity_version_or_policy(
    mutation: str,
) -> None:
    ref = "test-owner/private-kernel"
    payload = _kernel_api_payload(ref)
    if mutation == "missing_version":
        payload.pop("current_version_number")
    elif mutation == "wrong_version_type":
        payload["current_version_number"] = "1"
    elif mutation == "wrong_version":
        payload["current_version_number"] = 2
    elif mutation == "wrong_slug_identity":
        payload["ref"] = "test-owner/other-kernel"
    elif mutation == "wrong_owner":
        payload["ref"] = "other-owner/private-kernel"
    elif mutation == "public":
        payload["is_private"] = False
    elif mutation == "internet_enabled":
        payload["enable_internet"] = True
    else:
        payload = {"error": "metadata"}

    with pytest.raises(validator.OutputValidationError, match="kernel_api_metadata_invalid"):
        validator._validate_kernel_api_metadata(payload, ref=ref, expected_version=1)


def test_kernel_api_probe_uses_stdin_and_fails_closed_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ref = "test-owner/private-kernel"
    calls: list[tuple[list[str], bytes]] = []

    def fake_run(arguments: list[str], **kwargs: object) -> SimpleNamespace:
        request = kwargs.get("input")
        assert isinstance(request, bytes)
        calls.append((arguments, request))
        return SimpleNamespace(
            returncode=0,
            stdout=validator._canonical_json_bytes(_kernel_api_payload(ref)),
            stderr=b"",
        )

    monkeypatch.setattr(
        validator, "_supported_kaggle_cli_interpreter", lambda: Path(sys.executable)
    )
    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    assert validator._authenticate_kernel_api_version(ref, 1) == _kernel_api_payload(ref)
    assert len(calls) == 1
    arguments, request = calls[0]
    assert all(ref not in argument for argument in arguments)
    assert json.loads(request) == {"owner": "test-owner", "slug": "private-kernel"}

    monkeypatch.setattr(
        validator.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=2, stdout=b"", stderr=b""),
    )
    with pytest.raises(validator.OutputValidationError, match="kernel_api_metadata_invalid"):
        validator._authenticate_kernel_api_version(ref, 1)


def test_kaggle_cli_interpreter_preserves_tool_environment_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_interpreter = tmp_path / "python-real"
    real_interpreter.write_bytes(b"python")
    real_interpreter.chmod(0o700)
    interpreter = tmp_path / "tool-env" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(real_interpreter)
    executable = tmp_path / "kaggle"
    executable.write_text(f"#!{interpreter}\n", encoding="utf-8")
    executable.chmod(0o700)
    monkeypatch.setattr(validator.shutil, "which", lambda _name: str(executable))
    monkeypatch.setattr(
        validator.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=(validator.KAGGLE_CLI_VERSION + "\n").encode(),
            stderr=b"",
        ),
    )

    assert validator._supported_kaggle_cli_interpreter() == interpreter


@pytest.mark.parametrize(
    "status",
    ["complete", "COMPLETE", "KernelWorkerStatus.COMPLETE"],
)
def test_kernel_status_normalizes_only_approved_complete_tokens(status: str) -> None:
    assert validator._normalize_kernel_status(status) == "complete"


@pytest.mark.parametrize(
    "status",
    [
        "KernelWorkerStatus.ERROR",
        "KernelWorkerStatus.FAILED",
        "KernelWorkerStatus.CANCELLED",
        "KernelWorkerStatus.RUNNING",
        "KernelWorkerStatus.QUEUED",
        "INCOMPLETE",
        "NOT_COMPLETE",
        "COMPLETE_WITH_ERROR",
        "KernelWorkerStatus.UNKNOWN",
        "",
        None,
    ],
)
def test_kernel_status_rejects_nonterminal_unknown_or_empty_tokens(status: object) -> None:
    with pytest.raises(validator.OutputValidationError, match="kernel_status_invalid"):
        validator._normalize_kernel_status(status)


def test_kernel_status_accepts_observed_cli_enum_and_rejects_malformed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ref = "test-owner/private-kernel"
    monkeypatch.setattr(
        validator,
        "_run_kaggle_cli",
        lambda _arguments, **_kwargs: f'{ref} has status "KernelWorkerStatus.COMPLETE"\n'.encode(),
    )
    validator._kernel_status_complete(ref)

    monkeypatch.setattr(
        validator,
        "_run_kaggle_cli",
        lambda _arguments, **_kwargs: b"private-kernel status COMPLETE\n",
    )
    with pytest.raises(validator.OutputValidationError, match="kernel_status_invalid"):
        validator._kernel_status_complete(ref)


def test_kernel_source_pull_authenticates_exact_file_and_rejects_unexpected_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, result = _assembled(tmp_path)
    run_config = json.loads((bundle / "dataset/run-config.json").read_text())
    metadata_path = bundle / "review-ui-template-kernel/kernel-metadata.json"
    source_path = bundle / "review-ui-template-kernel/review_ui.ipynb"
    ref = validator._derived_stage_kernel_ref(run_config, "review_ui")
    expected_sources = [
        result["run_a_ref"],
        result["run_b_ref"],
        result["comparison_ref"],
        result["review_plan_ref"],
    ]
    include_extra = True

    def fake_cli(arguments: tuple[str, ...], **_kwargs: object) -> bytes:
        assert arguments[:2] == ("kernels", "pull")
        assert arguments[2] == ref
        target = Path(arguments[arguments.index("--path") + 1])
        assert target.name == "review_ui.ipynb"
        root = target.parent
        metadata = json.loads(metadata_path.read_text())
        metadata.update({"id_no": 1729, "keywords": [], "docker_image": ""})
        (root / "kernel-metadata.json").write_text(json.dumps(metadata))
        target.write_bytes(source_path.read_bytes())
        if include_extra:
            (root / "pydicom.py").write_text("raise RuntimeError('shadowed import')\n")
        return b"source_pulled\n"

    monkeypatch.setattr(validator, "_run_kaggle_cli", fake_cli)
    with pytest.raises(validator.OutputValidationError, match="kernel_source_invalid"):
        validator._pull_and_verify_exact_kernel(
            ref,
            1,
            "review_ui.ipynb",
            hashlib.sha256(source_path.read_bytes()).hexdigest(),
            expected_kernel_type="notebook",
            expected_dataset_sources=[result["dataset_ref"]],
            expected_kernel_sources=expected_sources,
            expected_competition_sources=[],
        )

    include_extra = False
    verified = validator._pull_and_verify_exact_kernel(
        ref,
        1,
        "review_ui.ipynb",
        hashlib.sha256(source_path.read_bytes()).hexdigest(),
        expected_kernel_type="notebook",
        expected_dataset_sources=[result["dataset_ref"]],
        expected_kernel_sources=expected_sources,
        expected_competition_sources=[],
    )
    assert verified["id_no"] == 1729
    assert verified["dataset_sources"] == [result["dataset_ref"]]


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("missing", "kernel_source_invalid"),
        ("stale_hash", "kernel_source_hash_mismatch"),
        ("identity_conflict", "kernel_source_invalid"),
    ],
)
def test_unversioned_kernel_source_rejects_missing_stale_or_conflicting_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    error: str,
) -> None:
    bundle, result = _assembled(tmp_path)
    run_config = json.loads((bundle / "dataset/run-config.json").read_text())
    metadata = json.loads((bundle / "kernel-a/kernel-metadata.json").read_text())
    source = (bundle / "kernel-a/run.py").read_bytes()
    ref = validator._derived_stage_kernel_ref(run_config, "run_a")
    metadata.update({"id_no": 1729, "keywords": [], "docker_image": ""})

    def fake_cli(arguments: tuple[str, ...], **_kwargs: object) -> bytes:
        assert arguments[:3] == ("kernels", "pull", ref)
        target = Path(arguments[arguments.index("--path") + 1])
        if mutation == "missing":
            target.unlink()
        else:
            target.write_bytes(source + (b"\n" if mutation == "stale_hash" else b""))
        if mutation == "identity_conflict":
            metadata["id"] = "other-owner/other-kernel"
        (target.parent / "kernel-metadata.json").write_text(json.dumps(metadata))
        return b"source_pulled\n"

    monkeypatch.setattr(validator, "_run_kaggle_cli", fake_cli)
    with pytest.raises(validator.OutputValidationError, match=error):
        validator._pull_and_verify_exact_kernel(
            ref,
            1,
            "run.py",
            hashlib.sha256(source).hexdigest(),
            expected_kernel_type="script",
            expected_dataset_sources=[result["dataset_ref"]],
            expected_kernel_sources=[result["source_manifest_kernel_ref"]],
            expected_competition_sources=[packager.COMPETITION_SLUG],
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "valid",
        "wrong_source_hash",
        "wrong_version",
        "wrong_identity",
        "public",
        "internet_enabled",
        "incomplete_status",
    ),
)
def test_real_size_listing_never_compensates_for_wrong_authentication_factor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    bundle, result = _assembled(tmp_path)
    run_config = json.loads((bundle / "dataset/run-config.json").read_text())
    manifest = json.loads((bundle / "dataset/bundle-manifest.json").read_text())
    metadata = json.loads((bundle / "kernel-a/kernel-metadata.json").read_text())
    source = (bundle / "kernel-a/run.py").read_bytes()
    ref = result["run_a_ref"]
    metadata.update({"id_no": 1729, "keywords": [], "docker_image": ""})
    api_payload = _kernel_api_payload(ref)
    pulled_source = source
    status = "KernelWorkerStatus.COMPLETE"
    if mutation == "wrong_source_hash":
        pulled_source += b"\n"
    elif mutation == "wrong_version":
        api_payload["current_version_number"] = 2
    elif mutation == "wrong_identity":
        api_payload["ref"] = "test-owner/other-kernel"
    elif mutation == "public":
        api_payload["is_private"] = False
    elif mutation == "internet_enabled":
        api_payload["enable_internet"] = True
    elif mutation == "incomplete_status":
        status = "KernelWorkerStatus.RUNNING"
    api_calls: list[list[str]] = []
    cli_calls: list[tuple[str, ...]] = []

    def fake_run(arguments: list[str], **_kwargs: object) -> SimpleNamespace:
        api_calls.append(arguments)
        return SimpleNamespace(
            returncode=0,
            stdout=validator._canonical_json_bytes(api_payload),
            stderr=b"",
        )

    def fake_cli(arguments: tuple[str, ...], **_kwargs: object) -> bytes:
        cli_calls.append(arguments)
        if arguments[:2] == ("kernels", "status"):
            assert arguments[2] == ref
            return f'{ref} has status "{status}"\n'.encode()
        if arguments[:2] == ("kernels", "pull"):
            assert arguments[2] == ref
            target = Path(arguments[arguments.index("--path") + 1])
            target.write_bytes(pulled_source)
            (target.parent / "kernel-metadata.json").write_text(json.dumps(metadata))
            return b"source_pulled\n"
        raise AssertionError("unexpected CLI command")

    monkeypatch.setattr(
        validator, "_supported_kaggle_cli_interpreter", lambda: Path(sys.executable)
    )
    monkeypatch.setattr(validator.subprocess, "run", fake_run)
    monkeypatch.setattr(validator, "_run_kaggle_cli", fake_cli)
    monkeypatch.setattr(
        validator,
        "_authenticated_listing",
        lambda *_args: (json.dumps(_remote_run_records(_runner())).encode(),),
    )
    monkeypatch.setattr(validator, "_retrieve_safe_run_output", lambda *_args: None)

    arguments = {
        "ref": ref,
        "dataset_ref": result["dataset_ref"],
        "source_manifest_ref": result["source_manifest_kernel_ref"],
        "competition_slug": packager.COMPETITION_SLUG,
        "run_config": run_config,
        "runner": _runner(),
        "manifest": manifest,
    }
    if mutation == "valid":
        validator._authenticate_qa_run(**arguments)
    else:
        with pytest.raises(validator.OutputValidationError):
            validator._authenticate_qa_run(**arguments)
        return

    assert len(api_calls) == 2
    assert all(all(ref not in argument for argument in call) for call in api_calls)
    assert sum(call[:2] == ("kernels", "status") for call in cli_calls) == 2
    assert sum(call[:3] == ("kernels", "pull", ref) for call in cli_calls) == 2


@pytest.mark.parametrize(
    "records",
    [
        [],
        [{"name": "unexpected.json", "size": 896}],
        [
            {"name": "private_review_plan.json", "size": 896},
            {"name": "unexpected.json", "size": 896},
        ],
    ],
)
def test_template_listing_rejects_missing_or_extra_outputs(
    records: list[dict[str, object]],
) -> None:
    runner = _runner()
    finalizer_path = ROOT / "kaggle/dicom_qa/finalize_review.py"
    finalizer = validator._finalizer_module(hashlib.sha256(finalizer_path.read_bytes()).hexdigest())
    pages = (json.dumps(records).encode(),)

    with pytest.raises(validator.OutputValidationError):
        validator._validate_template_listing(pages, runner, finalizer)


def test_comparator_listing_and_sanitized_summary_are_exact() -> None:
    runner = _runner()
    comparator = _comparator()
    records = [
        {
            "name": f"{comparator.OUTPUT_DIRECTORY}/{comparator.PRIVATE_OUTPUT}",
            "size": 896,
        },
        {
            "name": f"{comparator.OUTPUT_DIRECTORY}/{comparator.SANITIZED_OUTPUT}",
            "size": 896,
        },
        {"name": "rsna-knee-dqa-cmp.log", "size": 896},
    ]
    validator._validate_comparison_listing((json.dumps(records).encode(),), runner, comparator)
    summary = packager._canonical_json_bytes(
        {
            "schema_version": 1,
            "artifact_type": "dicom-run-determinism-aggregate",
            "status": "pass",
            "independent_runs_compared": True,
            "exact_manifest_byte_equality": True,
            "deterministic_metrics_equal": True,
            "cohort_plan_byte_equality": True,
            "unresolved_mismatches": "zero",
            "private_case_details_downloaded": False,
        }
    )
    validator._validate_comparison_summary(summary)

    records.append({"name": "unexpected.json", "size": 896})
    with pytest.raises(validator.OutputValidationError, match="remote_name_not_allowed"):
        validator._validate_comparison_listing((json.dumps(records).encode(),), runner, comparator)
    for field in (
        "exact_manifest_byte_equality",
        "deterministic_metrics_equal",
        "cohort_plan_byte_equality",
    ):
        altered = json.loads(summary)
        altered[field] = False
        with pytest.raises(validator.OutputValidationError, match="comparison_summary_invalid"):
            validator._validate_comparison_summary(packager._canonical_json_bytes(altered))


@pytest.mark.parametrize("nested", (False, True))
def test_comparison_retrieval_accepts_exact_summary_and_safe_root_log(
    monkeypatch: pytest.MonkeyPatch, nested: bool
) -> None:
    runner = _runner()
    comparator = _comparator()
    run_config = {"privacy": {"canary": "RSNA_PRIVATE_CANARY_TEST"}}

    def fake_cli(arguments: tuple[str, ...], **_kwargs: object) -> bytes:
        root = Path(arguments[arguments.index("--path") + 1])
        output = root / comparator.OUTPUT_DIRECTORY if nested else root
        output.mkdir(exist_ok=True)
        (output / comparator.SANITIZED_OUTPUT).write_bytes(
            packager._canonical_json_bytes(_comparison_summary())
        )
        (root / "rsna-knee-dqa-cmp.log").write_bytes(b"dicom_qa_comparison_complete\n")
        return b""

    monkeypatch.setattr(validator, "_run_kaggle_cli", fake_cli)
    validator._retrieve_comparison_summary(
        "test-owner/comparison/1",
        run_config=run_config,
        runner=runner,
        comparator=comparator,
    )


@pytest.mark.parametrize(
    "payload",
    (b"RSNA_PRIVATE_CANARY_TEST\n", b"PatientID\n"),
)
def test_comparison_retrieval_rejects_sensitive_root_log(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    runner = _runner()
    comparator = _comparator()
    run_config = {"privacy": {"canary": "RSNA_PRIVATE_CANARY_TEST"}}

    def fake_cli(arguments: tuple[str, ...], **_kwargs: object) -> bytes:
        root = Path(arguments[arguments.index("--path") + 1])
        (root / comparator.SANITIZED_OUTPUT).write_bytes(
            packager._canonical_json_bytes(_comparison_summary())
        )
        (root / "rsna-knee-dqa-cmp.log").write_bytes(payload)
        return b""

    monkeypatch.setattr(validator, "_run_kaggle_cli", fake_cli)
    with pytest.raises(validator.OutputValidationError, match=r"\Acomparison_log_invalid\Z"):
        validator._retrieve_comparison_summary(
            "test-owner/comparison/1",
            run_config=run_config,
            runner=runner,
            comparator=comparator,
        )


@pytest.mark.parametrize("payload", (b"", b"x" * (2 * 1024 * 1024 + 1)))
def test_comparison_retrieval_bounds_root_log(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    runner = _runner()
    comparator = _comparator()

    def fake_cli(arguments: tuple[str, ...], **_kwargs: object) -> bytes:
        root = Path(arguments[arguments.index("--path") + 1])
        (root / comparator.SANITIZED_OUTPUT).write_bytes(
            packager._canonical_json_bytes(_comparison_summary())
        )
        (root / "rsna-knee-dqa-cmp.log").write_bytes(payload)
        return b""

    monkeypatch.setattr(validator, "_run_kaggle_cli", fake_cli)
    with pytest.raises(validator.OutputValidationError, match=r"\Acomparison_log_invalid\Z"):
        validator._retrieve_comparison_summary(
            "test-owner/comparison/1",
            run_config={"privacy": {"canary": "RSNA_PRIVATE_CANARY_TEST"}},
            runner=runner,
            comparator=comparator,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "arbitrary_nested",
        "extra_file",
        "extra_directory",
        "missing",
        "multiple_summaries",
        "multiple_logs",
        "misplaced_log",
        "symlink",
        "special",
    ),
)
def test_comparison_retrieval_rejects_nonexact_layout(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    runner = _runner()
    comparator = _comparator()
    summary_payload = packager._canonical_json_bytes(_comparison_summary())

    def fake_cli(arguments: tuple[str, ...], **_kwargs: object) -> bytes:
        root = Path(arguments[arguments.index("--path") + 1])
        summary = root / comparator.SANITIZED_OUTPUT
        if mutation == "arbitrary_nested":
            summary = root / "arbitrary" / comparator.SANITIZED_OUTPUT
            summary.parent.mkdir()
        elif mutation != "missing":
            summary.write_bytes(summary_payload)
        if mutation == "extra_file":
            (root / "unexpected.txt").write_text("unexpected")
        elif mutation == "extra_directory":
            (root / "unexpected").mkdir()
        elif mutation == "multiple_summaries":
            nested = root / comparator.OUTPUT_DIRECTORY
            nested.mkdir()
            (nested / comparator.SANITIZED_OUTPUT).write_bytes(summary_payload)
        elif mutation == "multiple_logs":
            (root / "first.log").write_text("safe")
            (root / "second.log").write_text("safe")
        elif mutation == "misplaced_log":
            nested = root / comparator.OUTPUT_DIRECTORY
            nested.mkdir()
            (nested / "session.log").write_text("safe")
        elif mutation == "symlink":
            (root / "unexpected-link").symlink_to(summary)
        elif mutation == "special":
            os.mkfifo(root / "unexpected.pipe")
        if mutation == "arbitrary_nested":
            summary.write_bytes(summary_payload)
        return b""

    monkeypatch.setattr(validator, "_run_kaggle_cli", fake_cli)
    with pytest.raises(
        validator.OutputValidationError, match=r"\Acomparison_output_layout_invalid\Z"
    ):
        validator._retrieve_comparison_summary(
            "test-owner/comparison/1",
            run_config={"privacy": {"canary": "RSNA_PRIVATE_CANARY_TEST"}},
            runner=runner,
            comparator=comparator,
        )


@pytest.mark.parametrize(
    ("stage", "expected_calls"),
    [
        ("inputs", ["source_manifest_kernel"]),
        (
            "performance-smoke",
            ["source_manifest_kernel", "performance_smoke_kernel"],
        ),
        (
            "run-a",
            ["source_manifest_kernel", "performance_smoke_kernel", "qa_run"],
        ),
        (
            "run-b",
            [
                "source_manifest_kernel",
                "performance_smoke_kernel",
                "qa_run",
                "qa_run",
            ],
        ),
        (
            "comparison",
            [
                "source_manifest_kernel",
                "performance_smoke_kernel",
                "qa_run",
                "qa_run",
                "comparison_kernel",
            ],
        ),
        (
            "plan",
            [
                "source_manifest_kernel",
                "performance_smoke_kernel",
                "qa_run",
                "qa_run",
                "comparison_kernel",
                "review_plan_kernel",
            ],
        ),
        (
            "ui",
            [
                "source_manifest_kernel",
                "performance_smoke_kernel",
                "qa_run",
                "qa_run",
                "comparison_kernel",
                "review_plan_kernel",
                "review_ui_template_kernel",
            ],
        ),
        (
            "review",
            [
                "source_manifest_kernel",
                "performance_smoke_kernel",
                "qa_run",
                "qa_run",
                "comparison_kernel",
                "review_plan_kernel",
                "review_ui_template_kernel",
                "review_session_kernel",
            ],
        ),
        (
            "final",
            [
                "source_manifest_kernel",
                "performance_smoke_kernel",
                "qa_run",
                "qa_run",
                "comparison_kernel",
                "review_plan_kernel",
                "review_ui_template_kernel",
                "review_session_kernel",
                "review_finalizer_kernel",
            ],
        ),
    ],
)
def test_authenticated_workflow_routes_every_immutable_v1_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    expected_calls: list[str],
) -> None:
    bundle, result = _assembled(tmp_path)
    run_config, runner, manifest = validator.load_verified_policy(
        bundle / "dataset/run-config.json",
        bundle / "dataset/bundle-manifest.json",
        expected_commit=COMMIT,
        expected_bundle=result["bundle_sha256"],
    )
    calls: list[tuple[str, dict[str, object]]] = []
    dataset_calls: list[tuple[str, dict[str, int]]] = []
    kernel_version_calls: list[tuple[str, int]] = []
    kernel_status_calls: list[str] = []

    monkeypatch.setattr(
        validator,
        "_supported_kaggle_cli_interpreter",
        lambda: Path(sys.executable),
    )

    def fake_dataset(ref: str, files: dict[str, int]) -> dict[str, object]:
        dataset_calls.append((ref, files))
        return {"dataset_id": 1729, "version": 1, "files": tuple(sorted(files.items()))}

    monkeypatch.setattr(validator, "_authenticated_dataset_snapshot", fake_dataset)

    def recorder(name: str) -> Any:
        def record(**kwargs: object) -> dict[str, object] | None:
            calls.append((name, kwargs))
            if name == "source_manifest_kernel":
                source = kwargs["source"]
                assert isinstance(source, dict)
                return {
                    "dataset_id": 1729,
                    "version": 1,
                    "files": tuple(
                        sorted(validator._source_manifest_dataset_files(source).items())
                    ),
                }
            return None

        return record

    for name in (
        "source_manifest_kernel",
        "performance_smoke_kernel",
        "qa_run",
        "comparison_kernel",
        "review_plan_kernel",
        "review_ui_template_kernel",
        "review_session_kernel",
        "review_finalizer_kernel",
    ):
        monkeypatch.setattr(validator, f"_authenticate_{name}", recorder(name))
    monkeypatch.setattr(
        validator,
        "_authenticate_kernel_api_version",
        lambda ref, version: kernel_version_calls.append((ref, version)) or {},
    )
    monkeypatch.setattr(
        validator,
        "_kernel_status_complete",
        lambda ref: kernel_status_calls.append(ref),
    )

    validator.validate_authenticated_workflow(
        expected_version=1,
        stage=stage,
        run_config=run_config,
        runner=runner,
        manifest=manifest,
    )

    assert [name for name, _kwargs in calls] == expected_calls
    expected_run_refs = [result["run_a_ref"], result["run_b_ref"]][: expected_calls.count("qa_run")]
    assert [kwargs["ref"] for name, kwargs in calls if name == "qa_run"] == expected_run_refs
    if "performance_smoke_kernel" in expected_calls:
        smoke = next(kwargs for name, kwargs in calls if name == "performance_smoke_kernel")
        assert smoke["ref"] == result["performance_smoke_ref"]
        assert smoke["dataset_ref"] == result["dataset_ref"]
        assert smoke["source_manifest_ref"] == result["source_manifest_kernel_ref"]
        assert smoke["competition_slug"] == packager.COMPETITION_SLUG
    if "comparison_kernel" in expected_calls:
        comparison = next(kwargs for name, kwargs in calls if name == "comparison_kernel")
        assert comparison["run_config"] is run_config
    if "review_session_kernel" in expected_calls:
        session = next(kwargs for name, kwargs in calls if name == "review_session_kernel")
        assert session["ref"] == result["review_session_ref"]
        assert session["parent_ref"] == result["review_ui_template_ref"]
    if "review_plan_kernel" in expected_calls:
        plan = next(kwargs for name, kwargs in calls if name == "review_plan_kernel")
        assert plan["kernel_sources"] == [
            result["performance_smoke_ref"],
            result["run_a_ref"],
            result["run_b_ref"],
            result["comparison_ref"],
        ]
        assert plan["competition_slug"] == packager.COMPETITION_SLUG
    if "review_finalizer_kernel" in expected_calls:
        finalizer = next(kwargs for name, kwargs in calls if name == "review_finalizer_kernel")
        assert finalizer["kernel_sources"] == [
            result["run_a_ref"],
            result["run_b_ref"],
            result["comparison_ref"],
            result["review_plan_ref"],
            result["review_session_ref"],
        ]
    source_identity = run_config["input_identity"]["source_manifest"]
    source_dataset_ref = source_identity["bundle_dataset_ref"]
    assert [ref for ref, _files in dataset_calls] == [
        result["dataset_ref"],
        source_dataset_ref,
        result["dataset_ref"],
    ]
    expected_kernel_refs: list[str] = []
    for name, kwargs in calls:
        if name == "source_manifest_kernel":
            source = kwargs["source"]
            assert isinstance(source, dict)
            expected_kernel_refs.append(source["kernel_ref"])
        else:
            expected_kernel_refs.append(kwargs["ref"])
    assert kernel_status_calls == expected_kernel_refs
    assert kernel_version_calls == [(ref, 1) for ref in expected_kernel_refs]


@pytest.mark.parametrize(
    ("race", "expected_error"),
    [
        ("source_dataset", "dataset_version_race"),
        ("upstream_kernel", "kernel_api_metadata_invalid"),
    ],
)
def test_authenticated_workflow_rejects_end_of_chain_version_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    race: str,
    expected_error: str,
) -> None:
    bundle, result = _assembled(tmp_path)
    run_config, runner, manifest = validator.load_verified_policy(
        bundle / "dataset/run-config.json",
        bundle / "dataset/bundle-manifest.json",
        expected_commit=COMMIT,
        expected_bundle=result["bundle_sha256"],
    )
    source = run_config["input_identity"]["source_manifest"]
    source_dataset_ref = source["bundle_dataset_ref"]
    source_snapshot = {
        "dataset_id": 1729,
        "version": 1,
        "files": tuple(sorted(validator._source_manifest_dataset_files(source).items())),
    }
    advanced = False

    monkeypatch.setattr(
        validator,
        "_supported_kaggle_cli_interpreter",
        lambda: Path(sys.executable),
    )

    def fake_dataset(ref: str, files: dict[str, int]) -> dict[str, object]:
        if ref == source_dataset_ref:
            if race == "source_dataset" and advanced:
                return {**source_snapshot, "version": 2}
            return source_snapshot
        return {"dataset_id": 2718, "version": 1, "files": tuple(sorted(files.items()))}

    def advance_during_comparison(**_kwargs: object) -> None:
        nonlocal advanced
        advanced = True

    def final_kernel_version(ref: str, _version: int) -> dict[str, object]:
        if race == "upstream_kernel" and advanced and ref == result["run_a_ref"]:
            raise validator.OutputValidationError("kernel_api_metadata_invalid")
        return {"ref": ref, "current_version_number": 1}

    monkeypatch.setattr(validator, "_authenticated_dataset_snapshot", fake_dataset)
    monkeypatch.setattr(
        validator,
        "_authenticate_source_manifest_kernel",
        lambda **_kwargs: source_snapshot,
    )
    monkeypatch.setattr(validator, "_authenticate_performance_smoke_kernel", lambda **_kwargs: None)
    monkeypatch.setattr(validator, "_authenticate_qa_run", lambda **_kwargs: None)
    monkeypatch.setattr(
        validator,
        "_authenticate_comparison_kernel",
        advance_during_comparison,
    )
    monkeypatch.setattr(validator, "_kernel_status_complete", lambda _ref: None)
    monkeypatch.setattr(validator, "_authenticate_kernel_api_version", final_kernel_version)

    with pytest.raises(validator.OutputValidationError, match=rf"\A{expected_error}\Z"):
        validator.validate_authenticated_workflow(
            expected_version=1,
            stage="comparison",
            run_config=run_config,
            runner=runner,
            manifest=manifest,
        )


def test_workflow_stage_is_required_only_with_remote_workflow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = [
        "--run-config",
        str(tmp_path / "missing.json"),
        "--expected-commit",
        COMMIT,
        "--expected-bundle",
        "b" * 64,
    ]
    assert validator.main([*base, "--workflow-kernel-version", "1"]) == 2
    assert capsys.readouterr().out == (
        "dicom_qa_output_validation=FAIL code=workflow_stage_invalid\n"
    )
    assert validator.main([*base, "--local-dir", str(tmp_path), "--workflow-stage", "inputs"]) == 2
    assert capsys.readouterr().out == (
        "dicom_qa_output_validation=FAIL code=workflow_stage_invalid\n"
    )

    with pytest.raises(SystemExit):
        validator._parser().parse_args(
            [
                *base,
                "--workflow-kernel-version",
                "1",
                "--workflow-stage",
                "unknown",
            ]
        )


@pytest.mark.parametrize(
    ("stage", "expected_output"),
    [
        (
            "inputs",
            "dicom_qa_output_validation=PASS mode=workflow stage=inputs\n",
        ),
        (
            "final",
            "dicom_qa_output_validation=PASS mode=workflow stage=final "
            "determinism=pass human_review=pass\n",
        ),
    ],
)
def test_workflow_pass_token_names_authenticated_stage_and_final_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stage: str,
    expected_output: str,
) -> None:
    sentinel_runner = SimpleNamespace()
    monkeypatch.setattr(
        validator,
        "load_verified_policy",
        lambda *_args, **_kwargs: ({}, sentinel_runner, {}),
    )
    observed: list[dict[str, object]] = []
    monkeypatch.setattr(
        validator,
        "validate_authenticated_workflow",
        lambda **kwargs: observed.append(kwargs),
    )

    result = validator.main(
        [
            "--run-config",
            str(tmp_path / "run-config.json"),
            "--expected-commit",
            COMMIT,
            "--expected-bundle",
            "b" * 64,
            "--workflow-kernel-version",
            "1",
            "--workflow-stage",
            stage,
        ]
    )

    assert result == 0
    assert capsys.readouterr().out == expected_output
    assert len(observed) == 1
    assert observed[0]["stage"] == stage
    assert observed[0]["expected_version"] == 1


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("audit_id", "audit-0001-initial"),
        ("manifest_version", "manifest-v1"),
        ("dataset_version", 2),
        ("cohort_version", "qa-cohort-selection-v1"),
        ("checks", ["slice_order"]),
        ("contract_hash", "f" * 64),
    ],
)
def test_workflow_identity_rejects_manifest_cohort_or_contract_drift(
    tmp_path: Path, mutation: str, value: object
) -> None:
    bundle, result = _assembled(tmp_path)
    run_config, _runner_module, manifest = validator.load_verified_policy(
        bundle / "dataset/run-config.json",
        bundle / "dataset/bundle-manifest.json",
        expected_commit=COMMIT,
        expected_bundle=result["bundle_sha256"],
    )
    altered = deepcopy(run_config)
    if mutation == "audit_id":
        altered["input_identity"]["source_manifest"]["audit_id"] = value
    elif mutation == "manifest_version":
        altered["input_identity"]["source_manifest"]["version"] = value
    elif mutation == "dataset_version":
        altered["input_identity"]["source_manifest"]["bundle_dataset_version"] = value
    elif mutation == "cohort_version":
        altered["review_policy"]["cohort_selection_version"] = value
    elif mutation == "checks":
        altered["review_policy"]["checks"] = value
    else:
        altered["input_identity"]["official_competition"]["contract_sha256"] = value
    finalizer_path = ROOT / "kaggle/dicom_qa/finalize_review.py"
    finalizer = validator._finalizer_module(hashlib.sha256(finalizer_path.read_bytes()).hexdigest())

    with pytest.raises(validator.OutputValidationError, match="review_identity_invalid"):
        validator._validated_workflow_identity(altered, manifest, finalizer)


def test_kernel_listing_size_is_strictly_parsed_as_an_opaque_metric(tmp_path: Path) -> None:
    bundle, result = _assembled(tmp_path)
    run_config = json.loads((bundle / "dataset/run-config.json").read_text())
    source = run_config["input_identity"]["source_manifest"]
    private = {
        record["path"]: record.get("exact_bytes", 100) for record in source["private_output_policy"]
    }
    # The observed CLI 2.2.4 value is an opaque kernel-listing metric: a
    # contractually 32-byte key reports 896, so it must not be compared as bytes.
    records = [{"name": name, "size": 896} for name in private] + [
        {"name": name, "size": 896} for name in validator.SOURCE_MANIFEST_DOWNLOADABLE_OUTPUTS
    ]
    parsed = validator._kernel_listing_records((json.dumps(records).encode(),))
    assert [size for _record, size in parsed] == [896] * len(records)
    validator._validate_source_manifest_listing((json.dumps(records).encode(),), source)

    records.append({"name": "audit-output/unexpected.json", "size": 896})
    with pytest.raises(validator.OutputValidationError, match="remote_name_not_allowed"):
        validator._validate_source_manifest_listing((json.dumps(records).encode(),), source)

    session_records = [
        {"name": validator.REVIEW_SESSION_LEDGER, "size": 896},
        {"name": "rsna-knee-dqa-review.log", "size": 896},
    ]
    validator._validate_review_session_listing((json.dumps(session_records).encode(),))
    with pytest.raises(validator.OutputValidationError, match="remote_required_output_missing"):
        validator._validate_review_session_listing((b"[]",))
    session_records.append({"name": "private_review_plan.json", "size": 896})
    with pytest.raises(validator.OutputValidationError, match="remote_name_not_allowed"):
        validator._validate_review_session_listing((json.dumps(session_records).encode(),))

    assert result["review_session_ref"] != result["review_ui_template_ref"]


def test_review_session_metadata_probe_never_places_private_refs_in_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, result = _assembled(tmp_path)
    captured: dict[str, object] = {}

    def fake_run(arguments: list[str], **kwargs: object) -> SimpleNamespace:
        captured["arguments"] = arguments
        captured["input"] = kwargs.get("input")
        return SimpleNamespace(
            returncode=0,
            stdout=b"review_session_metadata=PASS\n",
            stderr=b"",
        )

    monkeypatch.setattr(validator.subprocess, "run", fake_run)
    validator._verify_review_session_metadata(
        interpreter=Path(sys.executable),
        ref=result["review_session_ref"],
        parent_ref=result["review_ui_template_ref"],
        dataset_sources=[result["dataset_ref"]],
        kernel_sources=[
            result["run_a_ref"],
            result["run_b_ref"],
            result["comparison_ref"],
            result["review_plan_ref"],
        ],
        competition_sources=[],
    )

    arguments = captured["arguments"]
    assert isinstance(arguments, list)
    assert all(result["review_session_ref"] not in argument for argument in arguments)
    request_payload = captured["input"]
    assert isinstance(request_payload, bytes)
    request = json.loads(request_payload)
    assert request["ref"] == result["review_session_ref"]


def test_review_session_authentication_pulls_source_only_before_and_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    def forbidden_version_probe(_ref: str, _version: int) -> None:
        pytest.fail("review session version checks must use its dedicated metadata probe")

    def status(_ref: str) -> None:
        events.append("status")

    def metadata(**_kwargs: object) -> None:
        events.append("metadata")

    def listing(_ref: str, _version: int) -> tuple[bytes, ...]:
        events.append("listing")
        return (json.dumps([{"name": validator.REVIEW_SESSION_LEDGER, "size": 896}]).encode(),)

    def source_pull(*_args: object, **_kwargs: object) -> dict[str, object]:
        events.append("pull")
        return {"source_sha256": "a" * 64, "version": 1}

    monkeypatch.setattr(validator, "_authenticate_kernel_api_version", forbidden_version_probe)
    monkeypatch.setattr(validator, "_kernel_status_complete", status)
    monkeypatch.setattr(validator, "_verify_review_session_metadata", metadata)
    monkeypatch.setattr(validator, "_authenticated_listing", listing)
    monkeypatch.setattr(validator, "_pull_and_verify_exact_kernel", source_pull)

    validator._authenticate_review_session_kernel(
        interpreter=Path(sys.executable),
        ref="test-owner/rsna-knee-dqa-review-aaaaaaa-bbbbbbbbbbbb",
        parent_ref="test-owner/rsna-knee-dqa-ui-aaaaaaa-bbbbbbbbbbbb",
        dataset_ref="test-owner/rsna-knee-dqa-bundle-aaaaaaa-bbbbbbbbbbbb",
        kernel_sources=["test-owner/source"],
        manifest={"review_ui": {"sha256": "a" * 64}},
    )

    assert events == [
        "status",
        "pull",
        "metadata",
        "listing",
        "status",
        "listing",
        "metadata",
        "pull",
    ]


def test_review_session_authentication_rejects_edited_source_without_output_retrieval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, result = _assembled(tmp_path)
    manifest = json.loads((bundle / "dataset/bundle-manifest.json").read_text())
    source = (bundle / "review-ui-template-kernel/review_ui.ipynb").read_bytes()
    kernel_sources = [
        result["run_a_ref"],
        result["run_b_ref"],
        result["comparison_ref"],
        result["review_plan_ref"],
    ]
    calls: list[tuple[str, ...]] = []

    def fake_cli(arguments: tuple[str, ...], **_kwargs: object) -> bytes:
        calls.append(arguments)
        assert arguments[:2] == ("kernels", "pull")
        target = Path(arguments[arguments.index("--path") + 1])
        target.write_bytes(source + b"\n")
        (target.parent / "kernel-metadata.json").write_text(
            json.dumps(
                {
                    "id": result["review_session_ref"],
                    "id_no": 1729,
                    "title": result["review_session_ref"].partition("/")[2],
                    "code_file": "review_ui.ipynb",
                    "language": "python",
                    "kernel_type": "notebook",
                    "is_private": True,
                    "enable_gpu": False,
                    "enable_tpu": False,
                    "enable_internet": False,
                    "keywords": [],
                    "dataset_sources": [result["dataset_ref"]],
                    "kernel_sources": kernel_sources,
                    "competition_sources": [],
                    "model_sources": [],
                    "docker_image": "",
                    "machine_shape": "",
                }
            )
        )
        return b"source_pulled\n"

    monkeypatch.setattr(validator, "_run_kaggle_cli", fake_cli)
    monkeypatch.setattr(validator, "_kernel_status_complete", lambda _ref: None)

    with pytest.raises(validator.OutputValidationError, match="kernel_source_hash_mismatch"):
        validator._authenticate_review_session_kernel(
            interpreter=Path(sys.executable),
            ref=result["review_session_ref"],
            parent_ref=result["review_ui_template_ref"],
            dataset_ref=result["dataset_ref"],
            kernel_sources=kernel_sources,
            manifest=manifest,
        )

    assert calls
    assert all(call[:2] == ("kernels", "pull") for call in calls)
    assert all("output" not in call for call in calls)


def test_remote_qa_exit_gate_rejects_blocked_or_unresolved_runs(tmp_path: Path) -> None:
    bundle, _result = _assembled(tmp_path)
    run_config = json.loads((bundle / "dataset/run-config.json").read_text())
    manifest = json.loads((bundle / "dataset/bundle-manifest.json").read_text())
    runner = _runner()
    summary = _summary(run_config, runner, manifest["kernel"]["sha256"])

    validator._validate_qa_exit_gate(summary)
    for mutation in (
        {"status": "blocked_unresolved_integrity"},
        {"pipeline": {**summary["pipeline"], "integrity_gate": "blocked"}},
        {"pipeline": {**summary["pipeline"], "unresolved_blockers": "present"}},
    ):
        altered = {**summary, **mutation}
        with pytest.raises(
            validator.OutputValidationError, match="dicom_integrity_exit_gate_failed"
        ):
            validator._validate_qa_exit_gate(altered)


def test_review_summary_binds_completion_time_and_requires_zero_blocks(tmp_path: Path) -> None:
    bundle, result = _assembled(tmp_path)
    run_config, _runner_module, manifest = validator.load_verified_policy(
        bundle / "dataset/run-config.json",
        bundle / "dataset/bundle-manifest.json",
        expected_commit=COMMIT,
        expected_bundle=result["bundle_sha256"],
    )
    finalizer = _finalizer()
    summary = _review_summary(run_config, manifest, finalizer)
    payload = packager._canonical_json_bytes(summary)

    validated = validator._validate_review_summary_payload(payload, run_config, manifest, finalizer)
    assert validated["completed_at_utc"] == "2026-08-09T01:02:03Z"

    bad_timestamp = {**summary, "completed_at_utc": "2026-08-09 01:02:03Z"}
    with pytest.raises(validator.OutputValidationError, match="review_summary_invalid"):
        validator._validate_review_summary_payload(
            packager._canonical_json_bytes(bad_timestamp), run_config, manifest, finalizer
        )

    blocked = deepcopy(summary)
    blocked["status"] = "blocked"
    blocked["review"]["block_decisions"] = "below_threshold_nonzero"
    blocked["review"]["zero_blocks"] = False
    blocked["review"]["check_results"]["slice_order"] = "BLOCK"
    with pytest.raises(validator.OutputValidationError, match="human_review_exit_gate_failed"):
        validator._validate_review_summary_payload(
            packager._canonical_json_bytes(blocked), run_config, manifest, finalizer
        )


def test_final_performance_report_is_bound_complete_and_disclosure_safe(tmp_path: Path) -> None:
    bundle, result = _assembled(tmp_path)
    run_config, runner, manifest = validator.load_verified_policy(
        bundle / "dataset/run-config.json",
        bundle / "dataset/bundle-manifest.json",
        expected_commit=COMMIT,
        expected_bundle=result["bundle_sha256"],
    )
    finalizer = _finalizer()
    human_review = _review_summary(run_config, manifest, finalizer)
    report = _final_performance_report(run_config, manifest, runner, finalizer)
    payload = packager._canonical_json_bytes(report)

    validated = validator._validate_performance_report_payload(
        payload, run_config, manifest, runner, finalizer, human_review
    )
    assert validated["provenance"]["pipeline_version"] == "dicom-model-v1"
    assert validated["performance"]["throughput"]["decode_files_per_second_token"] == (
        "one_to_below_ten_per_second"
    )
    assert validated["performance"]["inference_runtime_budget"] == {
        "limit_seconds": 32_400,
        "limit_source": "bundled_competition_contract",
        "measured_preprocessing_pipeline_wall_seconds": 90.0,
        "remaining_after_preprocessing_seconds": 32_310.0,
        "preprocessing_within_limit": True,
        "model_runtime_included": False,
        "model_viability_assessed": False,
        "scope": "measured_preprocessing_only",
    }
    assert validated["exit_gate"] == {
        "unresolved_blockers": "zero",
        "disclosure_policy": "joint-complementary-k20-v1",
    }


def test_final_performance_keeps_run_a_blockers_separate_from_review_blocks(
    tmp_path: Path,
) -> None:
    bundle, result = _assembled(tmp_path)
    run_config, runner, manifest = validator.load_verified_policy(
        bundle / "dataset/run-config.json",
        bundle / "dataset/bundle-manifest.json",
        expected_commit=COMMIT,
        expected_bundle=result["bundle_sha256"],
    )
    finalizer = _finalizer()
    human_review = _review_summary(run_config, manifest, finalizer)
    human_review["status"] = "blocked"
    human_review["review"]["check_results"]["slice_order"] = "BLOCK"
    human_review["review"]["block_decisions"] = "below_threshold_nonzero"
    human_review["review"]["zero_blocks"] = False
    payload = finalizer._final_performance_report(
        run_a_payload=packager._canonical_json_bytes(
            _summary(run_config, runner, manifest["kernel"]["sha256"])
        ),
        comparison_payload=packager._canonical_json_bytes(_comparison_summary()),
        review_payload=packager._canonical_json_bytes(human_review),
        run_config=run_config,
        manifest=manifest,
        runner=runner,
    )
    report = json.loads(payload)

    assert report["status"] == "blocked"
    assert report["human_review"]["block_decisions"] == "below_threshold_nonzero"
    assert report["exit_gate"]["unresolved_blockers"] == "zero"
    with pytest.raises(validator.OutputValidationError, match="performance_exit_gate_failed"):
        validator._validate_performance_report_payload(
            payload, run_config, manifest, runner, finalizer, human_review
        )


@pytest.mark.parametrize(
    "mutation",
    ["pending_determinism", "mismatched_review_count", "mismatched_bundle"],
)
def test_final_performance_report_rejects_pending_or_mismatched_evidence(
    tmp_path: Path, mutation: str
) -> None:
    bundle, result = _assembled(tmp_path)
    run_config, runner, manifest = validator.load_verified_policy(
        bundle / "dataset/run-config.json",
        bundle / "dataset/bundle-manifest.json",
        expected_commit=COMMIT,
        expected_bundle=result["bundle_sha256"],
    )
    finalizer = _finalizer()
    human_review = _review_summary(run_config, manifest, finalizer)
    report = _final_performance_report(run_config, manifest, runner, finalizer)
    if mutation == "pending_determinism":
        report["performance"]["determinism_status"] = "pending_independent_run_comparison"
    elif mutation == "mismatched_review_count":
        report["human_review"]["reviewed_studies"] = "range_120_139"
    else:
        report["provenance"]["project_bundle_sha256"] = "0" * 64

    with pytest.raises(validator.OutputValidationError, match="performance_report_invalid"):
        validator._validate_performance_report_payload(
            packager._canonical_json_bytes(report),
            run_config,
            manifest,
            runner,
            finalizer,
            human_review,
        )


def test_finalizer_listing_requires_final_performance_artifact() -> None:
    finalizer = _finalizer()
    records = [
        {
            "name": f"{finalizer.OUTPUT_DIRECTORY}/{finalizer.SANITIZED_SUMMARY}",
            "size": 896,
        },
        {
            "name": f"{finalizer.OUTPUT_DIRECTORY}/{finalizer.PRIVATE_COMPLETION}",
            "size": 896,
        },
    ]
    with pytest.raises(validator.OutputValidationError, match="remote_required_output_missing"):
        validator._validate_review_listing((json.dumps(records).encode(),), finalizer)

    records.append(
        {
            "name": f"{finalizer.OUTPUT_DIRECTORY}/{finalizer.SANITIZED_PERFORMANCE}",
            "size": 896,
        }
    )
    validator._validate_review_listing((json.dumps(records).encode(),), finalizer)


def test_review_ledger_check9_na_and_attestation_binding() -> None:
    finalizer = _finalizer()
    clean_context = {
        "organizer_plane": "sagittal",
        "physical_plane": "sagittal",
        "laterality": "unknown",
        "laterality_transform": "none",
        "horizontal_flip_applied": False,
        "assigned_slot": "sagittal_fluid_sensitive",
        "retention_reasons": [],
        "missing_series_mask": [False] * 6,
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
        "check_9_applicable": False,
        "check_9_reason_codes": [],
    }
    plan = {
        "schema_version": 2,
        "artifact_type": "private-dicom-qa-review-plan",
        "status": "pending_private_human_review",
        "review_identity": {"review_bundle_id": "c5qa-test"},
        "rows": [
            {
                "case_ordinal": 0,
                "series_ordinal": 0,
                "review_context": clean_context,
                "decisions": {check: "not_reviewed" for check in finalizer.REVIEW_CHECKS},
                "artifacts": [],
            },
        ],
    }
    ledger = {
        "schema_version": 2,
        "artifact_type": "private-dicom-qa-completed-review-ledger",
        "status": "complete",
        "review_identity": plan["review_identity"],
        "plan_sha256": hashlib.sha256(finalizer._canonical_json_bytes(plan)).hexdigest(),
        "started_at_utc": "2026-08-09T01:00:00Z",
        "completed_at_utc": "2026-08-09T01:02:03Z",
        "human_attestation": {
            "schema_version": 1,
            "instructions_version": finalizer.REVIEW_INSTRUCTIONS_VERSION,
            "statement": finalizer.HUMAN_ATTESTATION_STATEMENT,
            "authorized_human_reviewer": True,
            "direct_visual_review": True,
            "no_llm_or_browser_automation_pixel_access": True,
            "attested_at_utc": "2026-08-09T01:02:03Z",
        },
        "rows": [
            {
                "case_ordinal": 0,
                "series_ordinal": 0,
                "artifact_hashes_verified": True,
                "decisions": {
                    check: (
                        "NOT_APPLICABLE"
                        if check == "duplicate_missing_abnormal_handling"
                        else "PASS"
                    )
                    for check in finalizer.REVIEW_CHECKS
                },
            }
        ],
    }
    finalizer._validated_ledger(finalizer._canonical_json_bytes(ledger), plan)

    applicable_plan = deepcopy(plan)
    applicable_context = applicable_plan["rows"][0]["review_context"]
    applicable_context["missing_series_mask"][1] = True
    applicable_context["check_9_applicable"] = True
    applicable_context["check_9_reason_codes"] = ["missing_diagnostic_slot"]
    applicable_ledger = deepcopy(ledger)
    applicable_ledger["plan_sha256"] = hashlib.sha256(
        finalizer._canonical_json_bytes(applicable_plan)
    ).hexdigest()
    with pytest.raises(finalizer.ReviewFinalizationError, match="review_ledger_invalid"):
        finalizer._validated_ledger(
            finalizer._canonical_json_bytes(applicable_ledger), applicable_plan
        )

    stale = deepcopy(ledger)
    stale["human_attestation"]["attested_at_utc"] = "2026-08-09T01:01:59Z"
    with pytest.raises(finalizer.ReviewFinalizationError, match="review_ledger_invalid"):
        finalizer._validated_ledger(finalizer._canonical_json_bytes(stale), plan)
