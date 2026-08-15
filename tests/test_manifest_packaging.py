from __future__ import annotations

import ctypes
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from concurrent.futures.process import BrokenProcessPool
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

ROOT = Path(__file__).parents[1]
COMMIT = "a" * 40
TIMESTAMP = 1_700_000_000


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


packager = _load_module("_manifest_packager", ROOT / "scripts" / "package_manifest_bundle.py")
validator = _load_module("_manifest_validator", ROOT / "scripts" / "validate_manifest_output.py")
sys.path.insert(0, str(ROOT))
try:
    deployment = _load_module(
        "_manifest_deployment", ROOT / "scripts" / "authenticate_manifest_deployment.py"
    )
finally:
    sys.path.pop(0)


FAKE_RUNNER = r"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def _render(title, headings, values, keys):
    lines = [title, "", *headings, ""]
    for key in sorted(keys):
        value = values[key]
        if value is None:
            value = "not_evaluable"
        elif isinstance(value, bool):
            value = str(value).lower()
        lines.append(f"- {key}: {value}")
    return "\n".join(lines) + "\n"


def run_manifest_audit(*, input_root, output_root, manifest_schema_path,
                       competition_config_path, competition_contract_path, run_config_path):
    del input_root, manifest_schema_path, competition_config_path, competition_contract_path
    config = json.loads(Path(run_config_path).read_text())
    provenance = config["provenance"]
    privacy = {key: value for key, value in config["privacy"].items() if key != "canary"}
    aggregates = {
        "scope": {
            "mode": "full",
            "source_context": config["source_context"],
            "example_test_only": True,
            "hidden_test_evaluable": False,
        },
        "coverage": {
            "studies_total": 40, "train_studies": 20, "test_studies": 20,
            "series_total": 40, "train_series": 20, "test_series": 20,
            "files_total": 40, "files_terminal": 40, "files_decoded": 40,
            "files_quarantined": 0, "complete": True,
        },
        "quality": {
            "series_geometry_pass": 40, "series_fallback": 0, "series_quarantined": 0,
            "files_unreadable": 0, "files_decode_failure": 0, "path_header_mismatch": 0,
            "patient_group_missing": 0, "unexplained_dicom_issues": 0,
        },
        "labels": {
            "official_only": True, "non_official_sources": 0,
            "official_cells": 40, "positive_cells": 20,
            "negative_cells": 20, "unknown_cells": 0, "conflict_cells": 0,
        },
        "duplicates": {
            "exact_file_groups": 0, "exact_pixel_groups": 0, "exact_series_groups": 0,
            "exact_study_groups": 0, "exact_report_raw_pairs": 20,
            "exact_report_normalized_pairs": 20, "exact_report_overlap_pairs": 20,
            "exact_report_union_pairs": 20, "near_slice_groups": 0, "near_slice_edges": 0,
            "near_slice_edges_suppressed": 0, "near_slice_unresolved_study_pairs": 0,
            "near_slice_study_pair_space_overflow": False,
            "near_slice_study_pair_count_lower_bound": 0,
            "near_slice_overflow_study_edges": 0,
            "raw_container_variation_groups": 0, "altered_metadata_groups": 0,
            "near_series_edges": 0, "near_series_candidate_space_overflow": False,
            "near_series_candidate_pair_count_lower_bound": 0,
            "near_series_overflow_study_edges": 0, "near_report_edges": 0,
            "near_report_candidate_space_overflow": False,
            "near_report_candidate_pair_count_lower_bound": 0,
            "near_report_overflow_study_edges": 0, "candidate_edges": 0,
            "label_copy_candidates": 0, "protected_components": 20,
            "cross_split_components": 0, "future_fold_crossings": 0,
        },
        "shift": {
            "evaluation_scope": config["source_context"],
            "patient_sex": "suppressed_low_test_support",
            "scanner_manufacturer": "suppressed_low_test_support",
            "scanner_model": "suppressed_low_test_support",
            "protocol_cluster": "suppressed_low_test_support",
            "plane_availability": "suppressed_low_test_support",
            "sequence_composition": "suppressed_low_test_support",
            "report_language": "not_evaluable_test_reports_unavailable",
            "site_domain_cluster": "suppressed_low_test_support",
            "series_description_vocabulary": "suppressed_low_test_support",
            "patient_age_years": "suppressed_low_test_support",
            "field_strength_t": "suppressed_low_test_support",
            "study_complexity_series_count": "suppressed_low_test_support",
            "study_complexity_slice_count": "suppressed_low_test_support",
            "in_plane_resolution_area_mm2": "suppressed_low_test_support",
            "slice_thickness_mm": "suppressed_low_test_support",
            "overall_missingness": "suppressed_low_test_support",
        },
        "qa": {"selected_studies": 20},
        "integrity": {
            "foreign_keys": True, "all_files_terminal": True, "all_series_terminal": True,
            "protected_graph_closed": True, "private_artifacts_complete": True,
            "five_levels_reconciled": True, "dicom_issue_dispositions_complete": True,
        },
        "versions": {
            "manifest_version": provenance["manifest_version"],
            "group_version": provenance["group_version"],
            "label_version": provenance["label_version"],
            "preprocessing_version": provenance["preprocessing_version"],
        },
        "runtime": {"elapsed_seconds": 1},
    }
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=False)
    private_payloads = {
        "private_manifest.sqlite3": b"private sqlite fixture\n",
        "private_duplicate_groups.csv": b"kind,count\n",
        "private_preliminary_group_keys.csv": b"kind,count\n",
        "private_qa_samples.csv": b"kind,count\n",
        "private_artifact_inventory.json": b"{}\n",
        "audit_key.bin": Path(run_config_path).with_name("audit-key.bin").read_bytes(),
    }
    for name, payload in private_payloads.items():
        (output / name).write_bytes(payload)
    merged = {key: value for section in aggregates.values() for key, value in section.items()}
    merged.update({"folds_assigned": False, "fold_feasibility": "not_assessed"})
    data_keys = set().union(
        aggregates["scope"], aggregates["coverage"], aggregates["quality"],
        aggregates["labels"], aggregates["integrity"], aggregates["versions"],
        aggregates["runtime"],
    )
    leakage_keys = (
        set(aggregates["duplicates"])
        | set(aggregates["integrity"])
        | {"folds_assigned", "fold_feasibility"}
    )
    shift_keys = set(aggregates["scope"]) | set(aggregates["shift"]) | set(aggregates["integrity"])
    documents = {
        "data_audit.md": _render(
            "# Data audit",
            ["## Scope", "## Coverage", "## Quality", "## Labels", "## Integrity",
             "## Versions", "## Runtime"], merged, data_keys,
        ),
        "leakage_audit.md": _render(
            "# Leakage audit",
            [
                "## Duplicates",
                "## Protected components",
                "## Structural grouping checks",
                "## Integrity",
            ],
            merged, leakage_keys,
        ),
        "domain_shift_audit.md": _render(
            "# Domain shift audit",
            ["## Scope", "## Shift", "## Limitations", "## Integrity"], merged, shift_keys,
        ),
    }
    for name, text in documents.items():
        (output / name).write_text(text)
    artifacts = []
    for name, text in sorted(documents.items()):
        payload = text.encode()
        artifacts.append({
            "name": name, "kind": "documentation", "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
    inventory = {
        "schema_version": 1,
        "artifact_type": "sanitized-artifact-inventory",
        "provenance": provenance,
        "privacy": privacy,
        "artifacts": artifacts,
    }
    (output / "sanitized_artifact_inventory.json").write_text(
        json.dumps(inventory, sort_keys=True, separators=(",", ":")) + "\n"
    )
    print(config["privacy"]["canary"])
    os.write(1, config["privacy"]["canary"].encode())
    os.write(2, config["privacy"]["canary"].encode())
    return {
        "schema_version": 1,
        "artifact_type": "manifest-audit-aggregate",
        "status": "complete",
        "provenance": provenance,
        "privacy": privacy,
        "aggregates": aggregates,
    }
"""


def _wheel(path: Path, distribution: str, module_files: dict[str, str | bytes]) -> None:
    dist_info = f"{distribution.replace('-', '_')}-0.1.0.dist-info"
    metadata = (
        "Metadata-Version: 2.1\n"
        f"Name: {distribution}\n"
        "Version: 0.1.0\n"
        "Requires-Python: >=3.11,<3.13\n\n"
    )
    wheel = "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    entries = {
        **module_files,
        f"{dist_info}/METADATA": metadata,
        f"{dist_info}/WHEEL": wheel,
        f"{dist_info}/RECORD": "",
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)


def test_pydicom_wheel_strips_medical_payloads_and_rebuilds_record(tmp_path: Path) -> None:
    dicm_payload = b"\0" * 128 + b"DICM" + b"payload"
    module_files: dict[str, str | bytes] = {
        "pydicom/__init__.py": "__version__ = '0.1.0'\n",
        "pydicom/data/runtime.json": b"{}",
        "pydicom/data/charset_files/README.txt": b"safe charset resource\n",
        "pydicom/data/palettes/README.md": b"safe palette resource\n",
        "pydicom/data/test_files/support.json": b"{}",
        "pydicom/data/charset_files/sample.dcm": b"suffix-only payload",
        "pydicom/data/palettes/sample.bin": dicm_payload,
        "pydicom-0.1.0.dist-info/licenses/LICENSE": b"test license\n",
    }
    first = tmp_path / "pydicom-0.1.0-py3-none-any.whl"
    second_root = tmp_path / "second"
    second_root.mkdir()
    second = second_root / first.name
    _wheel(first, "pydicom", module_files)
    _wheel(second, "pydicom", module_files)

    packager._strip_pydicom_medical_payloads(first, TIMESTAMP)
    packager._strip_pydicom_medical_payloads(second, TIMESTAMP)

    assert first.read_bytes() == second.read_bytes()
    packager._validate_linux_wheel(first)
    with zipfile.ZipFile(first) as archive:
        payloads = {
            info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()
        }
    record_names = [name for name in payloads if name.endswith(".dist-info/RECORD")]
    assert record_names == ["pydicom-0.1.0.dist-info/RECORD"]
    record_name = record_names[0]
    record_payload = payloads.pop(record_name)
    assert (
        record_payload
        == (
            "\n".join(
                [
                    f"{name},{packager._wheel_record(payload)}"
                    for name, payload in sorted(payloads.items())
                ]
                + [f"{record_name},,"]
            )
            + "\n"
        ).encode()
    )
    assert payloads["pydicom/__init__.py"] == b"__version__ = '0.1.0'\n"
    assert payloads["pydicom/data/runtime.json"] == b"{}"
    assert payloads["pydicom/data/charset_files/README.txt"] == b"safe charset resource\n"
    assert payloads["pydicom/data/palettes/README.md"] == b"safe palette resource\n"
    assert payloads["pydicom-0.1.0.dist-info/licenses/LICENSE"] == b"test license\n"
    assert all(
        not packager._medical_wheel_member(Path(name), payload[:132])
        for name, payload in payloads.items()
    )

    unexpected = tmp_path / "dummy_dep-0.1.0-py3-none-any.whl"
    _wheel(unexpected, "dummy-dep", {"dummy_dep/__init__.py": "", "dummy_dep/sample": dicm_payload})
    with pytest.raises(packager.PackagingError, match="dependency_wheel_medical_payload_detected"):
        packager._validate_linux_wheel(unexpected)

    invalid_record_root = tmp_path / "invalid-record"
    invalid_record_root.mkdir()
    invalid_record = invalid_record_root / first.name
    _wheel(
        invalid_record,
        "pydicom",
        {
            "pydicom/__init__.py": "",
            "pydicom/data/runtime.json": b"{}",
            "pydicom-0.1.0.dist-info/licenses/LICENSE": b"test license\n",
        },
    )
    with pytest.raises(packager.PackagingError, match="dependency_wheel_record_invalid"):
        packager._validate_linux_wheel(invalid_record)

    project_root = tmp_path / "project"
    project_root.mkdir()
    inputs = _bundle_inputs(project_root)
    with zipfile.ZipFile(inputs["wheel_path"], "a") as archive:
        archive.writestr("rsna_knee/medical_fixture", dicm_payload)
    with pytest.raises(packager.PackagingError, match="dependency_wheel_medical_payload_detected"):
        packager._assemble_bundle(output=tmp_path / "rejected-bundle", **inputs)


def _bundle_inputs(tmp_path: Path) -> dict[str, Any]:
    sources = tmp_path / "sources"
    sources.mkdir()
    project_wheel = sources / "rsna_knee-0.1.0-py3-none-any.whl"
    _wheel(
        project_wheel,
        "rsna-knee",
        {
            "rsna_knee/__init__.py": "",
            "rsna_knee/data/__init__.py": "",
            "rsna_knee/data/manifest.py": FAKE_RUNNER,
        },
    )
    dependency_wheel = sources / "dummy_dep-0.1.0-py3-none-any.whl"
    _wheel(dependency_wheel, "dummy-dep", {"dummy_dep/__init__.py": ""})
    decoder_wheels = []
    for distribution, version in packager.REQUIRED_DECODER_PACKAGES.items():
        wheel_name = f"{distribution.replace('-', '_')}-{version}-py3-none-any.whl"
        decoder_wheel = sources / wheel_name
        module = distribution.replace("-", "_")
        _wheel(decoder_wheel, distribution, {f"{module}/__init__.py": ""})
        decoder_wheels.append(decoder_wheel)
    schema = sources / "manifest_schema.yaml"
    schema.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "manifest_version": "manifest-v2",
                "group_version": "protected-groups-v2",
                "label_version": "official-labels-v1",
                "preprocessing_version": "unassigned",
                "privacy": {
                    "minimum_export_cell": 20,
                    "raw_text_persisted": False,
                    "pixel_arrays_persisted": False,
                    "private_tables_leave_kaggle": False,
                },
            }
        )
    )
    pointer = sources / "competition.yaml"
    pointer.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "contract": "../docs/competition_contract/contract.yaml",
            }
        )
    )
    contract = sources / "contract.yaml"
    contract.write_text(
        json.dumps(
            {
                "identity": {"slug": packager.COMPETITION_SLUG},
                "runtime": {"internet_enabled": False},
            }
        )
    )
    lock = sources / "uv.lock"
    lock.write_text("version = 1\n")
    requirements = sources / "runtime-requirements.txt"
    requirements.write_text("dummy-dep==0.1.0\n")
    return {
        "owner": "test-owner",
        "git_commit": COMMIT,
        "git_commit_timestamp": TIMESTAMP,
        "audit_key": b"k" * 32,
        "wheel_path": project_wheel,
        "dependency_wheel_paths": (dependency_wheel, *decoder_wheels),
        "runtime_requirements_path": requirements,
        "manifest_schema_path": schema,
        "competition_config_path": pointer,
        "competition_contract_path": contract,
        "uv_lock_path": lock,
        "kernel_runner_path": ROOT / "kaggle" / "manifest_audit" / "run.py",
    }


def test_tracked_manifest_schema_matches_packager_contract() -> None:
    schema = packager._validate_manifest_schema(ROOT / "configs" / "manifest_schema.yaml")

    assert schema["schema_version"] == 2
    assert schema["manifest_version"] == "manifest-v2"
    assert schema["group_version"] == "protected-groups-v2"


def _assemble(tmp_path: Path, name: str = "bundle") -> Path:
    inputs = _bundle_inputs(tmp_path)
    output = tmp_path / name
    packager._assemble_bundle(output=output, **inputs)
    return output


def _runner() -> ModuleType:
    runner_path = ROOT / "kaggle" / "manifest_audit" / "run.py"
    digest = hashlib.sha256(runner_path.read_bytes()).hexdigest()
    return cast(ModuleType, validator._runner_module(digest))


def _fake_private_summary(
    tmp_path: Path,
) -> tuple[ModuleType, dict[str, Any], dict[str, Any]]:
    bundle = _assemble(tmp_path)
    run_config = json.loads((bundle / "dataset" / "run-config.json").read_text())
    namespace: dict[str, Any] = {}
    exec(FAKE_RUNNER, namespace)
    summary = namespace["run_manifest_audit"](
        input_root=tmp_path,
        output_root=tmp_path / "fake-private-output",
        manifest_schema_path=tmp_path,
        competition_config_path=tmp_path,
        competition_contract_path=tmp_path,
        run_config_path=bundle / "dataset" / "run-config.json",
    )
    return _runner(), run_config, cast(dict[str, Any], summary)


def _competition_mount(input_root: Path) -> Path:
    root = input_root / cast(str, packager.COMPETITION_SLUG)
    root.mkdir()
    for name in (
        "train.csv",
        "test.csv",
        "train_series.csv",
        "test_series.csv",
        "sample_submission.csv",
    ):
        (root / name).write_text("synthetic")
    (root / "train_series").mkdir()
    (root / "test_series").mkdir()
    return root


def _verified_failure_module() -> tuple[ModuleType, type[BaseException]]:
    module = ModuleType("rsna_knee.data.failure_fixture")
    error_type = type(
        "ManifestAuditError",
        (RuntimeError,),
        {"__module__": module.__name__},
    )
    cast(Any, module).ManifestAuditError = error_type
    return module, error_type


def test_runner_failure_code_propagates_only_verified_manifest_codes() -> None:
    runner = _runner()
    module, error_type = _verified_failure_module()

    assert (
        runner._runner_failure_code(error_type("five_level_reconciliation_failed"), module)
        == "five_level_reconciliation_failed"
    )
    maximum_code = "a" + "b" * 63
    assert runner._runner_failure_code(error_type(maximum_code), module) == maximum_code

    manifest_audit_subclass = type(
        "ManifestAuditSubclass",
        (error_type,),
        {"__module__": module.__name__},
    )

    invalid_failures = (
        error_type(),
        error_type("valid_code", "extra"),
        error_type(7),
        error_type("invalid-code"),
        error_type("a" * 65),
        manifest_audit_subclass("valid_code"),
    )
    assert all(
        runner._runner_failure_code(failure, module) == "runner_failed"
        for failure in invalid_failures
    )

    imposter_type = type(
        "ManifestAuditError",
        (RuntimeError,),
        {"__module__": "rsna_knee.data.imposter"},
    )
    assert runner._runner_failure_code(imposter_type("valid_code"), module) == "runner_failed"


def test_runner_failure_code_maps_fixed_runtime_failures_without_text() -> None:
    runner = _runner()
    private_marker = "private runner exception detail"
    cases = (
        (MemoryError(private_marker), "runner_memory_exhausted"),
        (BrokenProcessPool(private_marker), "runner_worker_pool_broken"),
        (sqlite3.OperationalError(private_marker), "runner_database_failed"),
        (runner.SafeRunError(private_marker), "runner_failed"),
        (RuntimeError(private_marker), "runner_failed"),
    )

    for failure, expected in cases:
        code = runner._runner_failure_code(failure, None)
        assert code == expected
        assert private_marker not in code


def test_run_audit_wraps_verified_manifest_error_without_cause_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner()
    module, error_type = _verified_failure_module()
    private_marker = "private manifest row detail"

    def fail(**_kwargs: object) -> None:
        error = error_type("five_level_reconciliation_failed")
        error.add_note(private_marker)
        raise error

    cast(Any, module).run_manifest_audit = fail
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setattr(runner, "_find_competition_root", lambda _root: tmp_path)
    monkeypatch.setattr(
        runner,
        "_install_offline_runtime",
        lambda _bundle, _wheel, _dependencies: runtime_root,
    )
    monkeypatch.setattr(runner.importlib, "import_module", lambda _name: module)
    arguments = {
        "input_root": "competition_input",
        "output_root": "working_output",
        "manifest_schema_path": "bundle_manifest_schema",
        "competition_config_path": "bundle_competition_config",
        "competition_contract_path": "bundle_competition_contract",
        "run_config_path": "bundle_run_config",
    }
    paths = {
        "project_wheel": tmp_path / "project.whl",
        "manifest_schema": tmp_path / "manifest_schema.yaml",
        "competition_pointer": tmp_path / "competition.yaml",
        "competition_contract": tmp_path / "competition_contract.yaml",
        "run_config": tmp_path / "run-config.json",
    }

    def invoke() -> Any:
        return runner._run_audit(
            input_root=tmp_path,
            output_root=tmp_path / "output",
            run_config={
                "runner": {
                    "module": module.__name__,
                    "callable": "run_manifest_audit",
                    "arguments": arguments,
                },
                "competition": {"slug": packager.COMPETITION_SLUG},
            },
            paths=paths,
            dependency_paths=(),
            deadline_seconds=5,
        )

    with pytest.raises(runner.SafeRunError) as captured:
        invoke()

    assert captured.value.code == "five_level_reconciliation_failed"
    assert str(captured.value) == "five_level_reconciliation_failed"
    assert captured.value.__cause__ is None
    assert private_marker not in str(captured.value)

    def unsafe_fail(**_kwargs: object) -> None:
        raise runner.SafeRunError(private_marker)

    cast(Any, module).run_manifest_audit = unsafe_fail
    with pytest.raises(runner.SafeRunError) as unsafe_captured:
        invoke()
    assert unsafe_captured.value.code == "runner_failed"
    assert private_marker not in str(unsafe_captured.value)

    def deadline_fail(**_kwargs: object) -> None:
        raise runner.SafeRunError("self_deadline_exceeded")

    cast(Any, module).run_manifest_audit = deadline_fail
    with pytest.raises(runner.SafeRunError) as deadline_captured:
        invoke()
    assert deadline_captured.value.code == "self_deadline_exceeded"


def test_bundle_is_deterministic_and_metadata_is_fail_closed(tmp_path: Path) -> None:
    inputs = _bundle_inputs(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_result = packager._assemble_bundle(output=first, **inputs)
    second_result = packager._assemble_bundle(output=second, **inputs)
    first_files = {
        path.relative_to(first).as_posix(): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second).as_posix(): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_result["bundle_sha256"] == second_result["bundle_sha256"]
    assert first_files == second_files

    dataset_metadata = json.loads((first / "dataset" / "dataset-metadata.json").read_text())
    kernel_metadata = json.loads((first / "kernel" / "kernel-metadata.json").read_text())
    assert dataset_metadata["licenses"] == [{"name": "other"}]
    assert "PRIVATE TEAM-ONLY" in dataset_metadata["description"]
    assert kernel_metadata["is_private"] is True
    assert kernel_metadata["enable_internet"] is False
    assert kernel_metadata["enable_gpu"] is False
    assert kernel_metadata["enable_tpu"] is False
    assert kernel_metadata["competition_sources"] == [packager.COMPETITION_SLUG]
    assert kernel_metadata["dataset_sources"] == [first_result["dataset_ref"]]
    manifest = json.loads((first / "dataset" / "bundle-manifest.json").read_text())
    dependency_records = [
        record for record in manifest["files"] if record["role"] == "dependency_wheel"
    ]
    assert len(dependency_records) == len(inputs["dependency_wheel_paths"])
    assert {record["sha256"] for record in dependency_records} == {
        hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs["dependency_wheel_paths"]
    }
    audit_key_record = next(record for record in manifest["files"] if record["role"] == "audit_key")
    assert audit_key_record["path"] == packager.AUDIT_KEY_FILENAME
    assert (first / "dataset" / packager.AUDIT_KEY_FILENAME).read_bytes() == inputs["audit_key"]
    run_config = json.loads((first / "dataset" / "run-config.json").read_text())
    assert run_config["provenance"]["decoder_packages"] == packager.REQUIRED_DECODER_PACKAGES
    assert inputs["audit_key"].hex() not in json.dumps(run_config)


def test_manifest_deployment_auth_reuses_exact_v1_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _assemble(tmp_path)
    run_config = json.loads((bundle / "dataset" / "run-config.json").read_text())
    manifest = json.loads((bundle / "dataset" / "bundle-manifest.json").read_text())
    calls: list[str] = []
    snapshot = {"version": 1, "is_private": True}
    kernel_identity = {"version": 1, "is_private": True, "enable_internet": False}
    monkeypatch.setattr(
        deployment.remote, "_supported_kaggle_cli_interpreter", lambda: Path("/usr/bin/python3")
    )
    monkeypatch.setattr(
        deployment.remote,
        "_authenticated_dataset_snapshot",
        lambda _ref, _files: calls.append("dataset") or snapshot,
    )
    monkeypatch.setattr(
        deployment.remote,
        "_authenticate_dataset_content",
        lambda _ref, _content, **_kwargs: calls.append("content"),
    )
    monkeypatch.setattr(
        deployment.remote,
        "_authenticate_kernel_api_version",
        lambda _ref, _version: calls.append("api") or kernel_identity,
    )
    monkeypatch.setattr(
        deployment.remote,
        "_pull_and_verify_exact_kernel",
        lambda *_args, **_kwargs: calls.append("pull") or kernel_identity,
    )
    monkeypatch.setattr(
        deployment.remote, "_kernel_status_complete", lambda _ref: calls.append("status")
    )
    monkeypatch.setattr(
        deployment.remote,
        "_authenticated_listing",
        lambda _ref, _version: calls.append("listing") or (b"[]",),
    )
    monkeypatch.setattr(
        deployment.remote,
        "_validate_source_manifest_listing",
        lambda _pages, _identity: calls.append("validate-listing"),
    )

    deployment.authenticate_manifest_deployment(
        run_config=run_config,
        manifest=manifest,
        bundle_manifest_path=bundle / "dataset" / "bundle-manifest.json",
        dataset_metadata_path=bundle / "dataset" / "dataset-metadata.json",
        kernel_metadata_path=bundle / "kernel" / "kernel-metadata.json",
        stage="local",
    )
    kernel_ref = json.loads((bundle / "kernel" / "kernel-metadata.json").read_text())["id"]
    monkeypatch.setattr(
        deployment.remote,
        "_run_kaggle_cli",
        lambda _arguments, **_kwargs: (
            f'{kernel_ref} has status "KernelWorkerStatus.RUNNING"\n'.encode()
        ),
    )
    assert (
        deployment.authenticate_manifest_deployment(
            run_config=run_config,
            manifest=manifest,
            bundle_manifest_path=bundle / "dataset" / "bundle-manifest.json",
            dataset_metadata_path=bundle / "dataset" / "dataset-metadata.json",
            kernel_metadata_path=bundle / "kernel" / "kernel-metadata.json",
            stage="status",
        )
        == "RUNNING"
    )
    deployment.authenticate_manifest_deployment(
        run_config=run_config,
        manifest=manifest,
        bundle_manifest_path=bundle / "dataset" / "bundle-manifest.json",
        dataset_metadata_path=bundle / "dataset" / "dataset-metadata.json",
        kernel_metadata_path=bundle / "kernel" / "kernel-metadata.json",
        stage="complete",
    )

    assert calls == [
        "api",
        "api",
        "dataset",
        "content",
        "api",
        "status",
        "pull",
        "listing",
        "validate-listing",
        "status",
        "api",
        "pull",
        "dataset",
    ]
    other_root = tmp_path / "other"
    other_root.mkdir()
    other_bundle = _assemble(other_root)
    remote_calls = len(calls)
    with pytest.raises(
        deployment.DeploymentAuthenticationError, match="deployment_identity_invalid"
    ):
        deployment.authenticate_manifest_deployment(
            run_config=run_config,
            manifest=manifest,
            bundle_manifest_path=bundle / "dataset" / "bundle-manifest.json",
            dataset_metadata_path=other_bundle / "dataset" / "dataset-metadata.json",
            kernel_metadata_path=bundle / "kernel" / "kernel-metadata.json",
            stage="inputs",
        )
    assert len(calls) == remote_calls

    kernel_path = bundle / "kernel" / "kernel-metadata.json"
    altered = json.loads(kernel_path.read_text())
    altered["enable_internet"] = True
    kernel_path.write_text(json.dumps(altered))
    with pytest.raises(
        deployment.DeploymentAuthenticationError, match="deployment_identity_invalid"
    ):
        deployment.authenticate_manifest_deployment(
            run_config=run_config,
            manifest=manifest,
            bundle_manifest_path=bundle / "dataset" / "bundle-manifest.json",
            dataset_metadata_path=bundle / "dataset" / "dataset-metadata.json",
            kernel_metadata_path=kernel_path,
            stage="inputs",
        )

    altered["enable_internet"] = False
    kernel_path.write_text(json.dumps(altered))
    run_path = bundle / "kernel" / "run.py"
    run_payload = run_path.read_bytes()
    run_path.write_bytes(run_payload + b"\n")
    with pytest.raises(
        deployment.DeploymentAuthenticationError, match="deployment_identity_invalid"
    ):
        deployment.authenticate_manifest_deployment(
            run_config=run_config,
            manifest=manifest,
            bundle_manifest_path=bundle / "dataset" / "bundle-manifest.json",
            dataset_metadata_path=bundle / "dataset" / "dataset-metadata.json",
            kernel_metadata_path=kernel_path,
            stage="local",
        )
    run_path.write_bytes(run_payload)
    extra_path = bundle / "kernel" / "extra.py"
    extra_path.write_text("pass\n")
    with pytest.raises(
        deployment.DeploymentAuthenticationError, match="deployment_identity_invalid"
    ):
        deployment.authenticate_manifest_deployment(
            run_config=run_config,
            manifest=manifest,
            bundle_manifest_path=bundle / "dataset" / "bundle-manifest.json",
            dataset_metadata_path=bundle / "dataset" / "dataset-metadata.json",
            kernel_metadata_path=kernel_path,
            stage="local",
        )
    extra_path.unlink()

    project_wheel = next((bundle / "dataset").glob("rsna_knee-*.whl"))
    with zipfile.ZipFile(project_wheel, "a") as archive:
        archive.writestr("rsna_knee/payload.bin", b"\0" * 128 + b"DICM")
    remote_calls = len(calls)
    with pytest.raises(
        deployment.packager.PackagingError, match="dependency_wheel_medical_payload_detected"
    ):
        deployment.authenticate_manifest_deployment(
            run_config=run_config,
            manifest=manifest,
            bundle_manifest_path=bundle / "dataset" / "bundle-manifest.json",
            dataset_metadata_path=bundle / "dataset" / "dataset-metadata.json",
            kernel_metadata_path=kernel_path,
            stage="inputs",
        )
    assert len(calls) == remote_calls


@pytest.mark.parametrize(
    ("provider_status", "expected"),
    [
        ("KernelWorkerStatus.PENDING", "PENDING"),
        ("RUNNING", "RUNNING"),
        ("complete", "COMPLETE"),
        ("KernelWorkerStatus.ERROR", "ERROR"),
        ("COMPLETE_WITH_ERROR", None),
    ],
)
def test_manifest_deployment_status_is_fixed_and_fail_closed(
    provider_status: str,
    expected: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ref = "test-owner/private-manifest-kernel"
    monkeypatch.setattr(
        deployment.remote,
        "_run_kaggle_cli",
        lambda _arguments, **_kwargs: f'{ref} has status "{provider_status}"\n'.encode(),
    )
    if expected is None:
        with pytest.raises(deployment.DeploymentAuthenticationError, match="kernel_status_invalid"):
            deployment._kernel_status(ref)
    else:
        assert deployment._kernel_status(ref) == expected


def test_manifest_deployment_status_cli_emits_only_fixed_state(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        deployment.output, "load_verified_policy", lambda *_args, **_kwargs: ({}, None)
    )
    monkeypatch.setattr(deployment.output, "_json_object", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(deployment, "authenticate_manifest_deployment", lambda **_kwargs: "RUNNING")

    assert (
        deployment.main(
            [
                "--run-config",
                "run-config.json",
                "--bundle-manifest",
                "bundle-manifest.json",
                "--dataset-metadata",
                "dataset-metadata.json",
                "--kernel-metadata",
                "kernel-metadata.json",
                "--expected-commit",
                COMMIT,
                "--expected-bundle",
                "b" * 64,
                "--stage",
                "status",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == "manifest_deployment_status=RUNNING\n"


def test_top_level_packaging_reuses_explicit_private_key_deterministically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _bundle_inputs(tmp_path)
    repository = tmp_path / "repo"
    for directory in (
        repository / "configs",
        repository / "docs" / "competition_contract",
        repository / "kaggle" / "manifest_audit",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(inputs["manifest_schema_path"], repository / "configs" / "manifest_schema.yaml")
    shutil.copy2(inputs["competition_config_path"], repository / "configs" / "competition.yaml")
    shutil.copy2(
        inputs["competition_contract_path"],
        repository / "docs" / "competition_contract" / "contract.yaml",
    )
    shutil.copy2(inputs["uv_lock_path"], repository / "uv.lock")
    shutil.copy2(inputs["kernel_runner_path"], repository / "kaggle" / "manifest_audit" / "run.py")
    audit_key_path = tmp_path / "private-audit-key.bin"
    audit_key_path.write_bytes(inputs["audit_key"])
    audit_key_path.chmod(0o600)
    monkeypatch.setattr(
        packager,
        "_clean_git_provenance",
        lambda _repo: (inputs["git_commit"], inputs["git_commit_timestamp"]),
    )
    monkeypatch.setattr(
        packager,
        "_build_wheel",
        lambda _repo, _timestamp, _destination: inputs["wheel_path"],
    )
    monkeypatch.setattr(
        packager,
        "_prepare_runtime_wheels",
        lambda _repo, _timestamp, _destination: (
            inputs["dependency_wheel_paths"],
            inputs["runtime_requirements_path"],
        ),
    )

    def package(output: Path) -> dict[str, str]:
        return cast(
            dict[str, str],
            packager.package_from_clean_repo(
                SimpleNamespace(
                    repo_root=repository,
                    output=output,
                    owner=inputs["owner"],
                    audit_key_path=audit_key_path,
                    runner_module=packager.DEFAULT_RUNNER_MODULE,
                    runner_callable=packager.DEFAULT_RUNNER_CALLABLE,
                    workers=4,
                    max_files=None,
                    progress_every=10_000,
                )
            ),
        )

    first = tmp_path / "top-level-first"
    second = tmp_path / "top-level-second"
    assert package(first) == package(second)
    assert {
        path.relative_to(first).as_posix(): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    } == {
        path.relative_to(second).as_posix(): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }


def test_dirty_repo_is_rejected_without_echoing_content(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=repository, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repository, check=True)
    tracked = repository / "tracked.txt"
    tracked.write_text("safe\n")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repository, check=True)
    tracked.write_text("private marker must not echo\n")
    with pytest.raises(packager.PackagingError) as captured:
        packager._clean_git_provenance(repository)
    assert captured.value.code == "git_worktree_dirty"
    assert "private marker" not in str(captured.value)


def test_runner_verifies_bundle_suppresses_output_and_validates_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    bundle = _assemble(tmp_path)
    input_root = tmp_path / "input"
    input_root.mkdir()
    shutil.copytree(bundle / "dataset", input_root / "bundle-input")
    _competition_mount(input_root)
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.setenv("KAGGLE_INPUT_ROOT", str(input_root))
    monkeypatch.setenv("KAGGLE_WORKING_ROOT", str(working))
    runner = _runner()
    assert runner.main() == 0
    captured_output = capfd.readouterr()
    captured = captured_output.out
    assert "manifest_audit_started" in captured
    assert "manifest_audit_complete" in captured
    assert "RSNA_PRIVATE_CANARY" not in captured
    assert "RSNA_PRIVATE_CANARY" not in captured_output.err
    shift_document = (working / runner.OUTPUT_DIRECTORY / "domain_shift_audit.md").read_text()
    assert all(f"- {feature}:" in shift_document for feature in runner.SHIFT_FEATURES)
    leakage_document = (working / runner.OUTPUT_DIRECTORY / "leakage_audit.md").read_text()
    assert "## Structural grouping checks" in leakage_document
    assert "## Fold feasibility" not in leakage_document
    assert "- folds_assigned: false" in leakage_document
    assert "- fold_feasibility: not_assessed" in leakage_document

    dataset = bundle / "dataset"
    run_config, trusted_runner = validator.load_verified_policy(
        dataset / "run-config.json", dataset / "bundle-manifest.json"
    )
    local = tmp_path / "downloaded"
    safe_dir = local / trusted_runner.OUTPUT_DIRECTORY
    safe_dir.mkdir(parents=True)
    for name in trusted_runner.DOWNLOADABLE_OUTPUT_POLICY:
        shutil.copy2(working / trusted_runner.OUTPUT_DIRECTORY / name, safe_dir / name)
    (local / "kernel.log").write_text(captured)
    validator.validate_local_output(local, run_config, trusted_runner)

    leakage_path = safe_dir / "leakage_audit.md"
    original_leakage = leakage_path.read_text()
    leakage_path.write_text(
        original_leakage.replace("- folds_assigned: false", "- folds_assigned: true")
    )
    with pytest.raises(validator.OutputValidationError) as status_error:
        validator.validate_local_output(local, run_config, trusted_runner)
    assert status_error.value.code == "documentation_validation_failed"
    leakage_path.write_text(original_leakage)

    data_path = safe_dir / "data_audit.md"
    original_data = data_path.read_text()
    reordered = original_data.replace(
        "- files_terminal: range_40_59\n- files_total: range_40_59",
        "- files_total: range_40_59\n- files_terminal: range_40_59",
    )
    assert reordered != original_data
    data_path.write_text(reordered)
    with pytest.raises(validator.OutputValidationError) as cross_file_error:
        validator.validate_local_output(local, run_config, trusted_runner)
    assert cross_file_error.value.code == "documentation_cross_file_mismatch"
    data_path.write_text(original_data)

    flat = tmp_path / "flat-downloaded"
    flat.mkdir()
    for name in trusted_runner.DOWNLOADABLE_OUTPUT_POLICY:
        shutil.copy2(working / trusted_runner.OUTPUT_DIRECTORY / name, flat / name)
    wrapped_log = [
        {"stream_name": "stderr", "time": 1, "data": "platform warning\n"},
        *[
            {"stream_name": "stdout", "time": index + 2, "data": f"{line}\n"}
            for index, line in enumerate(captured.splitlines())
        ],
    ]
    (flat / "kernel.log").write_text(json.dumps(wrapped_log))
    validator.validate_local_output(flat, run_config, trusted_runner)

    failure = tmp_path / "failure-log"
    failure.mkdir()
    failed_log = [
        {
            "stream_name": "stdout",
            "time": 1,
            "data": json.dumps({"event": "manifest_audit_started"}) + "\n",
        },
        {
            "stream_name": "stdout",
            "time": 2,
            "data": json.dumps(
                {
                    "event": "manifest_audit_failed",
                    "phase": "audit",
                    "code": "candidate_space_unbounded",
                }
            )
            + "\n",
        },
    ]
    (failure / "kernel.log").write_text(json.dumps(failed_log))
    assert validator.validate_failure_log(failure, run_config, trusted_runner) == (
        "audit",
        "candidate_space_unbounded",
    )

    failed_log[1]["data"] = json.dumps(
        {"event": "manifest_audit_failed", "phase": "audit", "code": "unsafe-code"}
    )
    (failure / "kernel.log").write_text(json.dumps(failed_log))
    with pytest.raises(validator.OutputValidationError):
        validator.validate_failure_log(failure, run_config, trusted_runner)

    failed_log[1]["data"] = json.dumps(
        {"event": "manifest_audit_failed", "phase": "unknown", "code": "runner_failed"}
    )
    (failure / "kernel.log").write_text(json.dumps(failed_log))
    with pytest.raises(validator.OutputValidationError):
        validator.validate_failure_log(failure, run_config, trusted_runner)

    remote_files = []
    for name in trusted_runner.PRIVATE_OUTPUT_POLICY | trusted_runner.DOWNLOADABLE_OUTPUT_POLICY:
        remote_path = f"{trusted_runner.OUTPUT_DIRECTORY}/{name}"
        remote_files.append(
            {"name": remote_path, "totalBytes": (working / remote_path).stat().st_size}
        )
    listing = tmp_path / "remote.json"
    listing.write_text(json.dumps({"files": remote_files, "nextPageToken": ""}))
    validator.validate_remote_listing(listing, run_config, trusted_runner)

    flat_listing = tmp_path / "flat-remote.json"
    flat_listing.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "name": Path(str(record["name"])).name,
                        "size": index + 1,
                    }
                    for index, record in enumerate(remote_files)
                ],
                "nextPageToken": "",
            }
        )
    )
    validator.validate_remote_listing(flat_listing, run_config, trusted_runner)

    shutil.copy2(
        working / trusted_runner.OUTPUT_DIRECTORY / "private_manifest.sqlite3",
        safe_dir / "private_manifest.sqlite3",
    )
    with pytest.raises(validator.OutputValidationError) as captured_error:
        validator.validate_local_output(local, run_config, trusted_runner)
    assert captured_error.value.code == "private_artifact_downloaded"


@pytest.mark.parametrize(
    "leak",
    [
        "1.2.840.113619.2.55.3.604688123.1",
        "Findings: normal acl tear without effusion",
        "private_outputs/study.csv",
        "scanner category: rare_vendor_model",
        '"pixels": [1,2,3]',
        "https://www.kaggle.com/private/resource",
        "550e8400-e29b-41d4-a716-446655440000",
        "a" * 40,
        "b" * 64,
        "ghp_abcdefghijklmnopqrstuvwxyz1234567890",  # pragma: allowlist secret
        "Bearer abcdefghijklmnopqrstuvwxyz",
    ],
)
def test_privacy_scanner_rejects_adversarial_text(leak: str) -> None:
    runner = _runner()
    with pytest.raises(Exception) as captured:
        runner._scan_unstructured(leak.encode(), "RSNA_PRIVATE_CANARY_fixture")
    assert leak not in str(captured.value)


def test_valid_summary_regression_and_small_counts_fail(tmp_path: Path) -> None:
    bundle = _assemble(tmp_path)
    run_config = json.loads((bundle / "dataset" / "run-config.json").read_text())
    runner = _runner()
    namespace: dict[str, Any] = {}
    exec(FAKE_RUNNER, namespace)
    fake_output = tmp_path / "fake-output"
    summary = namespace["run_manifest_audit"](
        input_root=tmp_path,
        output_root=fake_output,
        manifest_schema_path=tmp_path,
        competition_config_path=tmp_path,
        competition_contract_path=tmp_path,
        run_config_path=bundle / "dataset" / "run-config.json",
    )
    runner._validate_private_summary(summary, run_config)
    with pytest.raises(runner.SafeRunError):
        runner._validated_summary(summary, run_config)
    disclosed = runner._apply_disclosure_control(summary, run_config)
    assert runner._validated_summary(disclosed, run_config)
    assert set(summary["aggregates"]["shift"]) == {
        "evaluation_scope",
        *runner.SHIFT_FEATURES,
    }
    assert (
        summary["aggregates"]["shift"]["report_language"]
        == "not_evaluable_test_reports_unavailable"
    )
    assert set(summary["aggregates"]["duplicates"]) == {
        "exact_file_groups",
        "exact_pixel_groups",
        "exact_series_groups",
        "exact_study_groups",
        "exact_report_raw_pairs",
        "exact_report_normalized_pairs",
        "exact_report_overlap_pairs",
        "exact_report_union_pairs",
        "near_slice_groups",
        "near_slice_edges",
        "near_slice_edges_suppressed",
        "near_slice_unresolved_study_pairs",
        "near_slice_study_pair_space_overflow",
        "near_slice_study_pair_count_lower_bound",
        "near_slice_overflow_study_edges",
        "raw_container_variation_groups",
        "altered_metadata_groups",
        "near_series_edges",
        "near_series_candidate_space_overflow",
        "near_series_candidate_pair_count_lower_bound",
        "near_series_overflow_study_edges",
        "near_report_edges",
        "near_report_candidate_space_overflow",
        "near_report_candidate_pair_count_lower_bound",
        "near_report_overflow_study_edges",
        "candidate_edges",
        "label_copy_candidates",
        "protected_components",
        "cross_split_components",
        "future_fold_crossings",
    }
    overflow = deepcopy(summary)
    overflow_duplicates = overflow["aggregates"]["duplicates"]
    overflow_duplicates["near_slice_study_pair_space_overflow"] = True
    overflow_duplicates["near_slice_study_pair_count_lower_bound"] = 250_001
    overflow_duplicates["near_slice_overflow_study_edges"] = 20
    overflow_duplicates["near_series_candidate_space_overflow"] = True
    overflow_duplicates["near_series_candidate_pair_count_lower_bound"] = 1_000_001
    overflow_duplicates["near_series_overflow_study_edges"] = 20
    overflow_duplicates["candidate_edges"] = 40
    runner._validate_private_summary(overflow, run_config)
    overflow_duplicates["candidate_edges"] = "suppressed"
    with pytest.raises(runner.SafeRunError):
        runner._validate_private_summary(overflow, run_config)
    overflow_duplicates["candidate_edges"] = 40
    overflow_duplicates["near_slice_study_pair_count_lower_bound"] = 0
    with pytest.raises(runner.SafeRunError):
        runner._validate_private_summary(overflow, run_config)
    summary["aggregates"]["coverage"]["train_studies"] = 7
    with pytest.raises(runner.SafeRunError):
        runner._validate_private_summary(summary, run_config)


def test_disclosure_control_blocks_addition_subtraction_and_nested_totals(
    tmp_path: Path,
) -> None:
    runner, run_config, private = _fake_private_summary(tmp_path)
    coverage = private["aggregates"]["coverage"]
    coverage.update(
        {
            "studies_total": 105,
            "train_studies": 102,
            "test_studies": "suppressed",
            "series_total": 215,
            "train_series": 200,
            "test_series": "suppressed",
            "files_total": 1_003,
            "files_terminal": 1_003,
            "files_decoded": 1_001,
            "files_quarantined": "suppressed",
        }
    )
    private["aggregates"]["quality"].update(
        {
            "series_geometry_pass": 213,
            "series_quarantined": "suppressed",
            "files_decode_failure": "suppressed",
        }
    )
    private["aggregates"]["labels"].update(
        {
            "official_cells": 81,
            "positive_cells": 20,
            "negative_cells": 20,
            "unknown_cells": 40,
            "conflict_cells": "suppressed",
        }
    )

    disclosed = runner._apply_disclosure_control(private, run_config)
    released = disclosed["aggregates"]
    assert released["coverage"]["test_studies"] == runner.DISCLOSED_LOW
    assert released["coverage"]["files_quarantined"] == runner.DISCLOSED_LOW
    assert released["quality"]["files_decode_failure"] == runner.DISCLOSED_LOW
    assert released["labels"]["conflict_cells"] == runner.DISCLOSED_LOW
    assert released["coverage"]["studies_total"] == runner.DISCLOSED_HIGH
    assert released["coverage"]["train_studies"] == runner.DISCLOSED_HIGH
    assert released["coverage"]["files_total"] == runner.DISCLOSED_HIGH
    assert released["coverage"]["files_decoded"] == runner.DISCLOSED_HIGH
    assert released["labels"]["official_cells"] == runner.DISCLOSED_HIGH

    studies_total = runner._disclosed_count_interval(released["coverage"]["studies_total"])
    train_studies = runner._disclosed_count_interval(released["coverage"]["train_studies"])
    possible_test = (
        max(1, studies_total[0] - train_studies[1]),
        min(19, studies_total[1] - train_studies[0]),
    )
    assert possible_test == (1, 19)

    files_total = runner._disclosed_count_interval(released["coverage"]["files_total"])
    files_decoded = runner._disclosed_count_interval(released["coverage"]["files_decoded"])
    possible_decode_failures = (
        max(1, files_total[0] - files_decoded[1]),
        min(19, files_total[1] - files_decoded[0]),
    )
    assert possible_decode_failures == (1, 19)

    official = runner._disclosed_count_interval(released["labels"]["official_cells"])
    known_parts = [
        runner._disclosed_count_interval(released["labels"][key])
        for key in ("positive_cells", "negative_cells", "unknown_cells")
    ]
    parts_interval = runner._sum_interval(known_parts)
    possible_conflicts = (
        max(1, official[0] - parts_interval[1]),
        min(19, official[1] - parts_interval[0]),
    )
    assert possible_conflicts == (1, 19)


def test_disclosure_control_rejects_percentages_and_exact_count_releases(
    tmp_path: Path,
) -> None:
    runner, run_config, private = _fake_private_summary(tmp_path)
    disclosed = runner._apply_disclosure_control(private, run_config)
    for unsafe_value in ("5%", 5, 40, 0.05):
        unsafe = deepcopy(disclosed)
        unsafe["aggregates"]["coverage"]["files_quarantined"] = unsafe_value
        with pytest.raises(runner.SafeRunError):
            runner._validated_summary(unsafe, run_config)


def test_disclosure_control_prevents_prior_current_snapshot_differencing(
    tmp_path: Path,
) -> None:
    runner, run_config, private = _fake_private_summary(tmp_path)
    prior = deepcopy(private)
    current = deepcopy(private)
    for summary, total, decoded in ((prior, 59, 57), (current, 60, 58)):
        summary["aggregates"]["coverage"].update(
            {
                "files_total": total,
                "files_terminal": total,
                "files_decoded": decoded,
                "files_quarantined": "suppressed",
            }
        )
        summary["aggregates"]["quality"]["files_decode_failure"] = "suppressed"
    prior["aggregates"]["qa"]["selected_studies"] = 59
    current["aggregates"]["qa"]["selected_studies"] = 60
    prior_release = runner._apply_disclosure_control(prior, run_config)
    current_release = runner._apply_disclosure_control(current, run_config)
    assert prior_release["aggregates"]["coverage"]["files_total"] == runner.DISCLOSED_HIGH
    assert current_release["aggregates"]["coverage"]["files_total"] == runner.DISCLOSED_HIGH
    prior_interval = runner._disclosed_count_interval(
        prior_release["aggregates"]["qa"]["selected_studies"]
    )
    current_interval = runner._disclosed_count_interval(
        current_release["aggregates"]["qa"]["selected_studies"]
    )
    possible_delta = (
        current_interval[0] - prior_interval[1],
        current_interval[1] - prior_interval[0],
    )
    assert possible_delta[0] <= 1 < possible_delta[1]


def test_legacy_exact_snapshot_demonstrates_history_rewrite_gate(
    tmp_path: Path,
) -> None:
    runner, run_config, private = _fake_private_summary(tmp_path)
    private["aggregates"]["coverage"].update(
        {
            "files_total": 1_003,
            "files_terminal": 1_003,
            "files_decoded": 1_001,
            "files_quarantined": "suppressed",
        }
    )
    private["aggregates"]["quality"]["files_decode_failure"] = "suppressed"
    # A committed v1 pair already reconstructs a below-threshold value; HEAD cannot unpublish it.
    assert 1_003 - 1_001 == 2
    assert 0 < 2 < runner.DISCLOSURE_POLICY["minimum_export_cell"]

    released = runner._apply_disclosure_control(private, run_config)
    total_interval = runner._disclosed_count_interval(
        released["aggregates"]["coverage"]["files_total"]
    )
    decoded_interval = runner._disclosed_count_interval(
        released["aggregates"]["coverage"]["files_decoded"]
    )
    v2_possibilities = (
        max(1, total_interval[0] - decoded_interval[1]),
        min(19, total_interval[1] - decoded_interval[0]),
    )
    assert v2_possibilities == (1, 19)


def test_disclosure_control_coarsens_every_count_field(tmp_path: Path) -> None:
    runner, run_config, private = _fake_private_summary(tmp_path)
    disclosed = runner._apply_disclosure_control(private, run_config)
    for section, fields in runner.COUNT_FIELDS.items():
        for key in fields:
            value = disclosed["aggregates"][section][key]
            assert isinstance(value, str)
            runner._disclosed_count_interval(value)


def test_disclosure_schema_and_documented_policy_match_runner() -> None:
    runner = _runner()
    schema = json.loads((ROOT / "configs" / "sanitized_manifest_output.schema.json").read_text())
    disclosure = schema["$defs"]["disclosure"]["properties"]
    for key, value in runner.DISCLOSURE_POLICY.items():
        assert disclosure[key]["const"] == value
    assert schema["x-count-fields"] == {
        section: sorted(fields) for section, fields in runner.COUNT_FIELDS.items()
    }
    assert schema["x-document-fixed-states"]["leakage_audit.md"] == {
        "heading": "Structural grouping checks",
        **runner.STRUCTURAL_GROUPING_STATUS,
    }
    policy_document = (ROOT / "docs" / "manifest_disclosure_policy.md").read_text()
    assert runner.DISCLOSURE_POLICY["policy"] in policy_document
    assert "--force-with-lease" in policy_document
    assert "fold feasibility remains not assessed" in policy_document


def test_runtime_policy_and_elapsed_budget_fail_closed(tmp_path: Path) -> None:
    bundle = _assemble(tmp_path)
    run_config = json.loads((bundle / "dataset" / "run-config.json").read_text())
    runner = _runner()
    runner._validate_runtime_policy(run_config["runtime"])
    with pytest.raises(runner.SafeRunError):
        runner._validate_runtime_policy(
            {**run_config["runtime"], "kill_before_seconds": run_config["runtime"]["max_seconds"]}
        )
    with pytest.raises(runner.SafeRunError), runner._enforce_self_deadline(0):
        pass

    namespace: dict[str, Any] = {}
    exec(FAKE_RUNNER, namespace)
    summary = namespace["run_manifest_audit"](
        input_root=tmp_path,
        output_root=tmp_path / "fake-output",
        manifest_schema_path=tmp_path,
        competition_config_path=tmp_path,
        competition_contract_path=tmp_path,
        run_config_path=bundle / "dataset" / "run-config.json",
    )
    summary["aggregates"]["runtime"]["elapsed_seconds"] = run_config["runtime"]["max_seconds"] + 1
    with pytest.raises(runner.SafeRunError):
        runner._validate_private_summary(summary, run_config)


def test_fd_silencing_flushes_buffered_native_output(
    capfd: pytest.CaptureFixture[str],
) -> None:
    runner = _runner()
    canary = b"buffered_native_private_canary"
    library = ctypes.CDLL(None)
    printf = library.printf
    printf.argtypes = [ctypes.c_char_p]
    printf.restype = ctypes.c_int
    with runner._silence_process_output():
        assert printf(canary) >= 0
        os.write(1, canary)
        os.write(2, canary)
    runner._flush_native_stdio()
    captured = capfd.readouterr()
    assert canary.decode() not in captured.out
    assert canary.decode() not in captured.err


@pytest.mark.parametrize(
    "unsafe_status",
    [0.42, "large", "eo", "suppressed", {"primary_effect": 0.42}],
)
def test_shift_feature_status_is_fixed_and_non_numeric(
    tmp_path: Path, unsafe_status: object
) -> None:
    bundle = _assemble(tmp_path)
    run_config = json.loads((bundle / "dataset" / "run-config.json").read_text())
    runner = _runner()
    namespace: dict[str, Any] = {}
    exec(FAKE_RUNNER, namespace)
    summary = namespace["run_manifest_audit"](
        input_root=tmp_path,
        output_root=tmp_path / "fake-output",
        manifest_schema_path=tmp_path,
        competition_config_path=tmp_path,
        competition_contract_path=tmp_path,
        run_config_path=bundle / "dataset" / "run-config.json",
    )
    unsafe = deepcopy(summary)
    unsafe["aggregates"]["shift"]["patient_sex"] = unsafe_status
    with pytest.raises(runner.SafeRunError):
        runner._validate_private_summary(unsafe, run_config)


@pytest.mark.parametrize(
    ("section", "key", "unsafe_value"),
    [
        ("duplicates", "exact_report_union_pairs", 40),
        ("duplicates", "near_slice_unresolved_study_pairs", 20),
        ("duplicates", "future_fold_crossings", 20),
        ("duplicates", "altered_metadata_groups", 7),
        ("labels", "non_official_sources", 20),
        ("integrity", "five_levels_reconciled", False),
        ("integrity", "dicom_issue_dispositions_complete", False),
        ("quality", "unexplained_dicom_issues", 20),
    ],
)
def test_hardening_aggregate_invariants_fail_closed(
    tmp_path: Path, section: str, key: str, unsafe_value: object
) -> None:
    bundle = _assemble(tmp_path)
    run_config = json.loads((bundle / "dataset" / "run-config.json").read_text())
    runner = _runner()
    namespace: dict[str, Any] = {}
    exec(FAKE_RUNNER, namespace)
    summary = namespace["run_manifest_audit"](
        input_root=tmp_path,
        output_root=tmp_path / "fake-output",
        manifest_schema_path=tmp_path,
        competition_config_path=tmp_path,
        competition_contract_path=tmp_path,
        run_config_path=bundle / "dataset" / "run-config.json",
    )
    unsafe = deepcopy(summary)
    unsafe["aggregates"][section][key] = unsafe_value
    with pytest.raises(runner.SafeRunError):
        runner._validate_private_summary(unsafe, run_config)


def test_hardening_aggregate_key_is_required(tmp_path: Path) -> None:
    bundle = _assemble(tmp_path)
    run_config = json.loads((bundle / "dataset" / "run-config.json").read_text())
    runner = _runner()
    namespace: dict[str, Any] = {}
    exec(FAKE_RUNNER, namespace)
    summary = namespace["run_manifest_audit"](
        input_root=tmp_path,
        output_root=tmp_path / "fake-output",
        manifest_schema_path=tmp_path,
        competition_config_path=tmp_path,
        competition_contract_path=tmp_path,
        run_config_path=bundle / "dataset" / "run-config.json",
    )
    del summary["aggregates"]["duplicates"]["label_copy_candidates"]
    with pytest.raises(runner.SafeRunError):
        runner._validate_private_summary(summary, run_config)


def test_tampered_bundle_fails_without_traceback_or_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = _assemble(tmp_path)
    input_root = tmp_path / "input"
    input_root.mkdir()
    shutil.copytree(bundle / "dataset", input_root / "bundle-input")
    _competition_mount(input_root)
    project_wheel = next((input_root / "bundle-input").glob("rsna_knee-*.whl"))
    project_wheel.write_bytes(project_wheel.read_bytes() + b"private exception marker")
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.setenv("KAGGLE_INPUT_ROOT", str(input_root))
    monkeypatch.setenv("KAGGLE_WORKING_ROOT", str(working))
    runner = _runner()
    assert runner.main() == 2
    output = capsys.readouterr().out
    assert "bundle_file_invalid" in output
    assert "private exception marker" not in output
    assert "Traceback" not in output


def test_unmanifested_wheel_is_rejected_before_offline_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    bundle = _assemble(tmp_path)
    input_root = tmp_path / "input"
    input_root.mkdir()
    mounted_bundle = input_root / "bundle-input"
    shutil.copytree(bundle / "dataset", mounted_bundle)
    (mounted_bundle / "unmanifested-9.9.9-py3-none-any.whl").write_bytes(b"untrusted")
    _competition_mount(input_root)
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.setenv("KAGGLE_INPUT_ROOT", str(input_root))
    monkeypatch.setenv("KAGGLE_WORKING_ROOT", str(working))
    runner = _runner()
    assert runner.main() == 2
    captured = capfd.readouterr()
    assert "bundle_root_allowlist_invalid" in captured.out
    assert "untrusted" not in captured.out + captured.err


def test_retrieval_policy_rejects_runner_hash_drift_before_import(tmp_path: Path) -> None:
    runner_path = ROOT / "kaggle" / "manifest_audit" / "run.py"
    trusted_payload = runner_path.read_bytes()
    trusted_digest = hashlib.sha256(trusted_payload).hexdigest()
    changed_runner = tmp_path / "changed-run.py"
    weakened_payload = trusted_payload.replace(
        b'if _sha256_file(current_runner) != kernel.get("sha256"):',
        b"if False:",
    )
    assert weakened_payload != trusted_payload
    changed_runner.write_bytes(weakened_payload)
    with pytest.raises(validator.OutputValidationError) as captured:
        validator._runner_module(trusted_digest, changed_runner)
    assert captured.value.code == "trusted_validator_hash_mismatch"


def test_bundle_discovery_accepts_fully_qualified_kaggle_mount(tmp_path: Path) -> None:
    runner = _runner()
    input_root = tmp_path / "input"
    bundle_root = input_root / "datasets" / "owner" / "bundle"
    bundle_root.mkdir(parents=True)
    payload = {"schema_version": 1}
    (bundle_root / "bundle-manifest.json").write_text(json.dumps(payload))
    (input_root / "competition" / "train_series").mkdir(parents=True)

    discovered_root, discovered_payload = runner._find_bundle(input_root)

    assert discovered_root == bundle_root
    assert discovered_payload == payload


def test_bundle_discovery_accepts_and_deduplicates_mount_symlinks(tmp_path: Path) -> None:
    runner = _runner()
    input_root = tmp_path / "input"
    bundle_root = tmp_path / "mounted-bundle"
    input_root.mkdir()
    bundle_root.mkdir()
    payload = {"schema_version": 1}
    (bundle_root / "bundle-manifest.json").write_text(json.dumps(payload))
    (input_root / "bundle-alias-a").symlink_to(bundle_root, target_is_directory=True)
    (input_root / "bundle-alias-b").symlink_to(bundle_root, target_is_directory=True)

    discovered_root, discovered_payload = runner._find_bundle(input_root)

    assert discovered_root.resolve() == bundle_root
    assert discovered_payload == payload


def test_bundle_discovery_accepts_symlinked_manifest_file(tmp_path: Path) -> None:
    runner = _runner()
    input_root = tmp_path / "input"
    bundle_root = input_root / "bundle"
    backing_root = tmp_path / "backing"
    bundle_root.mkdir(parents=True)
    backing_root.mkdir()
    payload = {"schema_version": 1}
    backing_manifest = backing_root / "bundle-manifest.json"
    backing_manifest.write_text(json.dumps(payload))
    (bundle_root / "bundle-manifest.json").symlink_to(backing_manifest)

    discovered_root, discovered_payload = runner._find_bundle(input_root)

    assert discovered_root == bundle_root
    assert discovered_payload == payload


def test_symlinked_kaggle_bundle_files_still_require_full_verification(tmp_path: Path) -> None:
    bundle = _assemble(tmp_path)
    runner = _runner()
    input_root = tmp_path / "input"
    mounted_root = input_root / "bundle"
    mounted_root.mkdir(parents=True)
    for source in (bundle / "dataset").iterdir():
        (mounted_root / source.name).symlink_to(source)

    discovered_root, manifest = runner._find_bundle(input_root)
    records = runner._validated_records(discovered_root, manifest)
    run_config, _, dependencies = runner._verify_run_config(discovered_root, manifest, records)

    assert run_config["bundle_sha256"] == manifest["bundle_sha256"]
    assert dependencies


def test_competition_mount_symlink_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner()
    input_root = tmp_path / "input"
    competition_backing = tmp_path / "competition-backing"
    input_root.mkdir()
    competition_backing.mkdir()
    for name in (
        "train.csv",
        "test.csv",
        "train_series.csv",
        "test_series.csv",
        "sample_submission.csv",
    ):
        (competition_backing / name).write_text("synthetic")
    (competition_backing / "train_series").mkdir()
    (competition_backing / "test_series").mkdir()
    competition_mount = input_root / packager.COMPETITION_SLUG
    competition_mount.symlink_to(competition_backing, target_is_directory=True)
    monkeypatch.setattr(
        runner,
        "_install_offline_runtime",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            runner.SafeRunError("after_competition_gate")
        ),
    )

    with pytest.raises(runner.SafeRunError) as captured:
        runner._run_audit(
            input_root=input_root,
            output_root=tmp_path / "output",
            run_config={
                "runner": {
                    "module": "rsna_knee.data.manifest",
                    "callable": "run_manifest_audit",
                    "arguments": {
                        "input_root": "competition_input",
                        "output_root": "working_output",
                        "manifest_schema_path": "bundle_manifest_schema",
                        "competition_config_path": "bundle_competition_config",
                        "competition_contract_path": "bundle_competition_contract",
                        "run_config_path": "bundle_run_config",
                    },
                },
                "competition": {"slug": packager.COMPETITION_SLUG},
            },
            paths={"project_wheel": tmp_path / "project.whl"},
            dependency_paths=(),
            deadline_seconds=1,
        )
    assert captured.value.code == "after_competition_gate"
