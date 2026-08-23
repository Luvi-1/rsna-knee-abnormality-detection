"""Build the immutable private Kaggle bundle for Chunk 5 DICOM QA.

This command performs local packaging only.  Dataset creation and kernel execution remain
separate, approval-gated actions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Final

try:
    from scripts.package_manifest_bundle import (
        TARGET_PLATFORMS,
        TARGET_PYTHONS,
        PackagingError,
        _build_wheel,
        _canonical_json_bytes,
        _copy_payload,
        _derive_slug,
        _file_record,
        _git_output,
        _prepare_runtime_wheels,
        _read_bounded,
        _requirement_blocks,
        _scan_for_secrets,
        _sha256_bytes,
        _validate_contract_pair,
        _validate_linux_wheel,
        _wheel_distribution,
        _write_bytes,
    )
except ModuleNotFoundError:  # pragma: no cover - direct ``python scripts/...`` execution
    from package_manifest_bundle import (  # type: ignore[no-redef,import-not-found]
        TARGET_PLATFORMS,
        TARGET_PYTHONS,
        PackagingError,
        _build_wheel,
        _canonical_json_bytes,
        _copy_payload,
        _derive_slug,
        _file_record,
        _git_output,
        _prepare_runtime_wheels,
        _read_bounded,
        _requirement_blocks,
        _scan_for_secrets,
        _sha256_bytes,
        _validate_contract_pair,
        _validate_linux_wheel,
        _wheel_distribution,
        _write_bytes,
    )

BUNDLE_FORMAT: Final = "rsna-knee-dicom-qa-bundle-v1"
COMPETITION_SLUG: Final = "rsna-knee-abnormality-detection"
RUN_CONFIG_BUNDLE_PLACEHOLDER: Final = "0" * 64
MAX_BUNDLE_BYTES: Final = 128 * 1024 * 1024
OUTPUT_DIRECTORY: Final = "dicom-qa-output"
TARGET_STUDIES: Final = 100
MINIMUM_ELIGIBLE_STUDIES: Final = 100
REPRESENTED_VALUE_QUOTA: Final = 2
SELECTION_SEED: Final = 20260809
SELF_DEADLINE_SECONDS: Final = 27_000
OUTER_KILL_SECONDS: Final = 28_800
SOURCE_MANIFEST_VERSION: Final = "manifest-v2"
SOURCE_MANIFEST_AUDIT_ID: Final = "audit-0003-wheel-sanitization"
SOURCE_MANIFEST_KERNEL_VERSION: Final = 1
QA_KERNEL_VERSION: Final = 1
QA_COHORT_SELECTION_VERSION: Final = "qa-cohort-selection-v3"
QA_STRATUM_REGISTRY_VERSION: Final = "qa-stratum-registry-v1"
QA_STRATUM_REGISTRY_SHA256: Final = (
    "13829b49acec7ed2a3cb83cc862caaf3"  # pragma: allowlist secret
    "251ecbab9f1b11eca4061c0c9ae5acf3"  # pragma: allowlist secret
)
REQUIRED_REVIEW_DIMENSIONS: Final = (
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
REQUIRED_RUNTIME_PACKAGES: Final = {
    "pillow": "12.3.0",
    "pylibjpeg": "2.1.0",
    "pylibjpeg-libjpeg": "2.4.0",
    "pylibjpeg-openjpeg": "2.5.0",
}
RUN_PRIVATE_OUTPUTS: Final = (
    {
        "path": f"{OUTPUT_DIRECTORY}/private_full_run_manifest.jsonl",
        "kind": "private_remote_only",
        "max_bytes": 512 * 1024**2,
    },
    {
        "path": f"{OUTPUT_DIRECTORY}/private_full_run_metrics.json",
        "kind": "private_remote_only",
        "max_bytes": 2 * 1024**2,
    },
    {
        "path": f"{OUTPUT_DIRECTORY}/private_cohort_plan.json",
        "kind": "private_remote_only",
        "max_bytes": 32 * 1024**2,
    },
)
RUN_DOWNLOADABLE_OUTPUTS: Final = (
    {
        "path": f"{OUTPUT_DIRECTORY}/sanitized_summary.json",
        "kind": "aggregate_json",
        "max_bytes": 256 * 1024,
    },
    {
        "path": f"{OUTPUT_DIRECTORY}/sanitized_artifact_inventory.json",
        "kind": "aggregate_json",
        "max_bytes": 128 * 1024,
    },
)
REVIEW_PRIVATE_OUTPUTS: Final = (
    {
        "path": f"{OUTPUT_DIRECTORY}/private_case_index.json",
        "kind": "private_remote_only",
        "max_bytes": 32 * 1024**2,
    },
    {
        "path": f"{OUTPUT_DIRECTORY}/private_artifact_inventory.json",
        "kind": "private_remote_only",
        "max_bytes": 32 * 1024**2,
    },
)
REVIEW_PRIVATE_PATTERN_OUTPUTS: Final = (
    {
        "prefix": f"{OUTPUT_DIRECTORY}/private-review/",
        "basename_pattern": (
            r"case_[0-9]{6}_series_[0-9]{3}_"
            r"(?:contact|orthogonal|histogram|animation|before_after|review|metadata)"
            r"\.(?:png|gif|json)"
        ),
        "kind": "private_remote_only",
        "max_file_bytes": 32 * 1024**2,
        "max_files": 20_000,
        "max_total_bytes": 8 * 1024**3,
    },
)
REVIEW_DOWNLOADABLE_OUTPUTS: Final = (
    {
        "path": f"{OUTPUT_DIRECTORY}/sanitized_summary.json",
        "kind": "aggregate_json",
        "max_bytes": 256 * 1024,
    },
    {
        "path": f"{OUTPUT_DIRECTORY}/benchmark.md",
        "kind": "aggregate_documentation",
        "max_bytes": 128 * 1024,
    },
    {
        "path": f"{OUTPUT_DIRECTORY}/sanitized_artifact_inventory.json",
        "kind": "aggregate_json",
        "max_bytes": 128 * 1024,
    },
)
SESSION_LOG_POLICY: Final = {
    "basename_pattern": r"[a-z0-9][a-z0-9_-]{0,99}\.log",
    "kind": "log",
    "max_bytes": 2 * 1024 * 1024,
    "max_files": 1,
}
HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
SAFE_SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,49}\Z")
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
REVIEW_CHECKS: Final = (
    "slice_order",
    "anatomical_orientation",
    "laterality_preservation",
    "no_unintended_mirroring",
    "intensity_polarity",
    "anatomy_not_clipped",
    "sequence_slot_assignment",
    "preprocessing_appearance",
    "duplicate_missing_abnormal_handling",
)
REVIEW_STATUSES: Final = ("PASS", "BLOCK", "NOT_APPLICABLE")
REVIEW_PROTOCOL_VERSION: Final = "private-dicom-qa-human-review-v2"
REVIEW_INSTRUCTIONS_VERSION: Final = "private-dicom-qa-review-instructions-v2"
REQUIRED_PROJECT_WHEEL_MEMBERS: Final = frozenset(
    {
        "rsna_knee/data/series_slots.py",
        "rsna_knee/data/qa_strata.py",
        "rsna_knee/dicom/audit.py",
        "rsna_knee/dicom/benchmark.py",
        "rsna_knee/dicom/pipeline.py",
        "rsna_knee/qa/preprocessing.py",
    }
)
REVIEW_NOTEBOOK_BASENAME: Final = "review_ui.ipynb"
PERFORMANCE_SMOKE_POLICY_BASENAME: Final = "performance-smoke-policy.json"
PERFORMANCE_SMOKE_SELF_DEADLINE_SECONDS: Final = 3_600
PERFORMANCE_SMOKE_SUMMARY_MAX_BYTES: Final = 16 * 1024
SYNTHETIC_PREFLIGHT_BASENAME: Final = "synthetic-preflight.json"
MAX_SYNTHETIC_PREFLIGHT_BYTES: Final = 16 * 1024
SYNTHETIC_PREFLIGHT_REPORT: Final = {
    "schema_version": 1,
    "artifact_type": "dicom-qa-packaged-synthetic-preflight",
    "status": "pass",
    "preprocessing_version": "dicom-model-v1",
    "source_manifest_version": "synthetic-preflight-v1",
    "validation_scope": {
        "host_native_locked_dependencies": True,
        "kaggle_runtime_execution": "pending_run_a",
        "linux_cp311_cp312_wheelhouse_resolved": True,
        "production_project_wheel_executed": True,
        "target_linux_binaries_executed_locally": False,
    },
    "checks": {
        "deterministic_replay": True,
        "laterality_preserved": True,
        "native_in_plane_preserved": True,
        "no_horizontal_flip": True,
        "host_offline_execution": True,
        "physical_ordering": True,
        "provenance_complete": True,
        "rescale_and_monochrome1": True,
        "reversed_instance_numbers_ignored": True,
        "through_plane_not_resampled": True,
    },
}


def _performance_smoke_policy(entrypoint_sha256: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "artifact_type": "dicom-qa-performance-smoke-policy",
        "entrypoint": {"code_file": "performance_smoke.py", "sha256": entrypoint_sha256},
        "kernel": {
            "is_private": True,
            "enable_internet": False,
            "enable_gpu": False,
            "enable_tpu": False,
            "self_deadline_seconds": PERFORMANCE_SMOKE_SELF_DEADLINE_SECONDS,
            "full_run_allowed": False,
        },
        "output": {
            "directory": "dicom-qa-performance-smoke",
            "filename": "sanitized_performance_smoke.json",
            "kind": "sanitized_aggregate",
            "max_bytes": PERFORMANCE_SMOKE_SUMMARY_MAX_BYTES,
        },
    }


def _validate_preprocessing_config(path: Path) -> dict[str, Any]:
    payload = _read_bounded(path, 128 * 1024)
    _scan_for_secrets(payload)
    try:
        config = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackagingError("preprocessing_config_invalid") from error
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise PackagingError("preprocessing_config_invalid")
    if config.get("preprocessing_version") != "dicom-model-v1":
        raise PackagingError("preprocessing_config_invalid")
    if config.get("horizontal_flip") is not False:
        raise PackagingError("anatomical_policy_invalid")
    if config.get("through_plane_resampling") is not False:
        raise PackagingError("anatomical_policy_invalid")
    if config.get("allow_instance_fallback_for_qa") is not False:
        raise PackagingError("anatomical_policy_invalid")
    return config


def _validate_preprocessing_schema(path: Path) -> None:
    payload = _read_bounded(path, 256 * 1024)
    _scan_for_secrets(payload)
    try:
        schema = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackagingError("preprocessing_schema_invalid") from error
    if (
        not isinstance(schema, dict)
        or schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
    ):
        raise PackagingError("preprocessing_schema_invalid")


def _validate_synthetic_preflight(path: Path) -> bytes:
    payload = _read_bounded(path, MAX_SYNTHETIC_PREFLIGHT_BYTES)
    _scan_for_secrets(payload)
    try:
        report = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackagingError("synthetic_preflight_invalid") from error
    if report != SYNTHETIC_PREFLIGHT_REPORT or payload != _canonical_json_bytes(report):
        raise PackagingError("synthetic_preflight_invalid")
    return payload


def _runtime_pins(path: Path) -> dict[str, str]:
    try:
        text = _read_bounded(path, 2 * 1024 * 1024).decode("utf-8")
        blocks = _requirement_blocks(text)
    except (UnicodeDecodeError, PackagingError) as error:
        raise PackagingError("synthetic_preflight_dependencies_invalid") from error
    pins: dict[str, str] = {}
    for distribution, block in blocks.items():
        match = re.match(r"[A-Za-z0-9_.-]+==([^\s\\]+)", block)
        if match is None:
            raise PackagingError("synthetic_preflight_dependencies_invalid")
        pins[distribution] = match.group(1)
    return pins


def _prepare_host_preflight_wheels(
    *,
    runtime_requirements: Path,
    linux_dependency_wheels: Sequence[Path],
    destination: Path,
    timestamp: int,
    repo_root: Path,
) -> tuple[Path, ...]:
    """Prepare an ephemeral host-native mirror of the exact locked dependency versions."""

    pins = _runtime_pins(runtime_requirements)
    destination.mkdir()
    pure_distributions: set[str] = set()
    for wheel in linux_dependency_wheels:
        if "-none-any.whl" not in wheel.name.lower():
            continue
        distribution = _wheel_distribution(wheel)
        if distribution in pure_distributions:
            raise PackagingError("synthetic_preflight_dependencies_invalid")
        pure_distributions.add(distribution)
        _copy_payload(
            source=wheel,
            target=destination / wheel.name,
            maximum_bytes=MAX_BUNDLE_BYTES,
            timestamp=timestamp,
            scan_secrets=False,
        )
    try:
        blocks = _requirement_blocks(
            _read_bounded(runtime_requirements, 2 * 1024 * 1024).decode("utf-8")
        )
    except (UnicodeDecodeError, PackagingError) as error:
        raise PackagingError("synthetic_preflight_dependencies_invalid") from error
    native_requirements = destination.parent / "host-native-requirements.txt"
    native_payload = "".join(
        block for distribution, block in blocks.items() if distribution not in pure_distributions
    ).encode()
    if native_payload:
        _write_bytes(native_requirements, native_payload, timestamp)
        environment = os.environ.copy()
        environment.update(
            {
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PIP_NO_INPUT": "1",
                "PIP_KEYRING_PROVIDER": "disabled",
            }
        )
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "download",
                    "--isolated",
                    "--index-url",
                    "https://pypi.org/simple",
                    "--require-hashes",
                    "--no-deps",
                    "--only-binary=:all:",
                    "--dest",
                    str(destination),
                    "--requirement",
                    str(native_requirements),
                ],
                cwd=repo_root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=600,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise PackagingError("synthetic_preflight_dependency_prepare_failed") from error
    wheels = tuple(sorted(destination.glob("*.whl")))
    distributions = {_wheel_distribution(wheel) for wheel in wheels}
    if distributions != set(pins) or any(
        f"-{pins[_wheel_distribution(wheel)]}-" not in wheel.name.lower() for wheel in wheels
    ):
        raise PackagingError("synthetic_preflight_dependencies_invalid")
    return wheels


def _run_packaged_synthetic_preflight(
    *,
    project_wheel: Path,
    host_dependency_wheels: Sequence[Path],
    linux_dependency_wheels: Sequence[Path],
    runtime_requirements: Path,
    preprocessing_config: Path,
    code_commit: str,
    entrypoint: Path,
) -> bytes:
    """Execute host-native locked code and separately resolve the Kaggle Linux wheelhouse."""

    if not HEX_40.fullmatch(code_commit):
        raise PackagingError("synthetic_preflight_invalid")
    pins = _runtime_pins(runtime_requirements)
    host_distributions = {_wheel_distribution(path) for path in host_dependency_wheels}
    linux_distributions = {_wheel_distribution(path) for path in linux_dependency_wheels}
    if (
        host_distributions != set(pins)
        or linux_distributions != set(pins)
        or len({path.parent for path in host_dependency_wheels}) != 1
        or len({path.parent for path in linux_dependency_wheels}) != 1
        or any(
            f"-{pins[_wheel_distribution(path)]}-" not in path.name.lower()
            for path in (*host_dependency_wheels, *linux_dependency_wheels)
        )
    ):
        raise PackagingError("synthetic_preflight_dependencies_invalid")
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.upper().endswith("_PROXY"):
            environment.pop(name, None)
    environment.update(
        {
            "NO_PROXY": "*",
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INDEX": "1",
            "PIP_NO_INPUT": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONSAFEPATH": "1",
        }
    )
    try:
        with tempfile.TemporaryDirectory(prefix="rsna-knee-dicom-preflight-install-") as name:
            root = Path(name)
            root.chmod(0o700)
            pins_path = root / "runtime-pins.txt"
            pins_path.write_text(
                "".join(
                    f"{distribution}=={version}\n" for distribution, version in sorted(pins.items())
                )
            )
            pins_path.chmod(0o600)
            linux_wheelhouse = linux_dependency_wheels[0].parent
            platform_arguments = [
                argument for platform in TARGET_PLATFORMS for argument in ("--platform", platform)
            ]
            for python_version in TARGET_PYTHONS:
                abi = f"cp{python_version.replace('.', '')}"
                target = root / f"linux-{abi}"
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--isolated",
                        "--no-index",
                        "--find-links",
                        str(linux_wheelhouse),
                        "--no-deps",
                        "--only-binary=:all:",
                        *platform_arguments,
                        "--python-version",
                        python_version,
                        "--implementation",
                        "cp",
                        "--abi",
                        abi,
                        "--ignore-installed",
                        "--no-compile",
                        "--no-cache-dir",
                        "--disable-pip-version-check",
                        "--no-input",
                        "--target",
                        str(target),
                        "--requirement",
                        str(pins_path),
                        str(project_wheel),
                    ],
                    cwd=root,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                    timeout=300,
                )
            site_root = root / "site"
            host_wheelhouse = host_dependency_wheels[0].parent
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--isolated",
                    "--no-index",
                    "--find-links",
                    str(host_wheelhouse),
                    "--no-deps",
                    "--only-binary=:all:",
                    "--ignore-installed",
                    "--no-compile",
                    "--no-cache-dir",
                    "--disable-pip-version-check",
                    "--no-input",
                    "--target",
                    str(site_root),
                    "--requirement",
                    str(pins_path),
                    str(project_wheel),
                ],
                cwd=root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=300,
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    str(entrypoint),
                    "--site-root",
                    str(site_root),
                    "--config",
                    str(preprocessing_config),
                    "--code-commit",
                    code_commit,
                ],
                cwd=root,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=120,
            )
    except (OSError, subprocess.SubprocessError) as error:
        raise PackagingError("synthetic_preflight_failed") from error
    if (
        completed.returncode != 0
        or completed.stderr
        or not completed.stdout
        or len(completed.stdout) > MAX_SYNTHETIC_PREFLIGHT_BYTES
    ):
        raise PackagingError("synthetic_preflight_failed")
    try:
        report = json.loads(completed.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackagingError("synthetic_preflight_failed") from error
    if report != SYNTHETIC_PREFLIGHT_REPORT or completed.stdout != _canonical_json_bytes(report):
        raise PackagingError("synthetic_preflight_failed")
    return completed.stdout


def _canonical_json_object(path: Path, maximum: int, code: str) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    payload = _read_bounded(path, maximum)
    try:
        value = json.loads(payload, object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise PackagingError(code) from error
    if not isinstance(value, dict) or payload != _canonical_json_bytes(value):
        raise PackagingError(code)
    return value


def _source_manifest_identity(
    root: Path,
    manifest_schema_path: Path,
    registry_path: Path,
    audit_id: str,
) -> dict[str, object]:
    """Validate and bind the ignored, successful Chunk 4 private bundle."""

    if audit_id != SOURCE_MANIFEST_AUDIT_ID:
        raise PackagingError("source_manifest_audit_invalid")
    try:
        supplied = root.resolve(strict=True)
        resolved = supplied.parent if supplied.name == "dataset" else supplied
        if root.is_symlink() or not supplied.is_dir() or supplied.stat().st_mode & 0o077:
            raise PackagingError("source_manifest_bundle_invalid")
        dataset = supplied if supplied.name == "dataset" else resolved / "dataset"
        kernel = resolved / "kernel"
        expected_paths = {
            "manifest": dataset / "bundle-manifest.json",
            "run_config": dataset / "run-config.json",
            "dataset_metadata": dataset / "dataset-metadata.json",
            "kernel_metadata": kernel / "kernel-metadata.json",
            "runner": kernel / "run.py",
        }
        if any(
            path.is_symlink()
            or not path.is_file()
            or path.resolve(strict=True).parent not in {dataset.resolve(), kernel.resolve()}
            or path.stat().st_mode & 0o077
            for path in expected_paths.values()
        ):
            raise PackagingError("source_manifest_bundle_invalid")
    except (OSError, RuntimeError) as error:
        raise PackagingError("source_manifest_bundle_invalid") from error

    manifest = _canonical_json_object(
        expected_paths["manifest"], 2 * 1024**2, "source_manifest_bundle_invalid"
    )
    run_config = _canonical_json_object(
        expected_paths["run_config"], 2 * 1024**2, "source_manifest_bundle_invalid"
    )
    dataset_metadata = _canonical_json_object(
        expected_paths["dataset_metadata"], 256 * 1024, "source_manifest_bundle_invalid"
    )
    kernel_metadata = _canonical_json_object(
        expected_paths["kernel_metadata"], 256 * 1024, "source_manifest_bundle_invalid"
    )
    runner_payload = _read_bounded(expected_paths["runner"], 1024 * 1024)
    runner_sha256 = _sha256_bytes(runner_payload)
    bundle_sha256 = manifest.get("bundle_sha256")
    provenance = run_config.get("provenance")
    files = manifest.get("files")
    kernel_record = manifest.get("kernel")
    output_policy = run_config.get("output_policy")
    private_outputs = (
        output_policy.get("private_remote_only") if isinstance(output_policy, dict) else None
    )
    run_config_records = (
        [
            record
            for record in files
            if isinstance(record, dict) and record.get("role") == "run_config"
        ]
        if isinstance(files, list)
        else []
    )
    if (
        manifest.get("schema_version") != 1
        or not isinstance(bundle_sha256, str)
        or HEX_64.fullmatch(bundle_sha256) is None
        or run_config.get("bundle_sha256") != bundle_sha256
        or not isinstance(provenance, dict)
        or provenance.get("manifest_version") != SOURCE_MANIFEST_VERSION
        or provenance.get("manifest_schema_sha256")
        != _sha256_bytes(_read_bounded(manifest_schema_path, 2 * 1024**2))
        or not isinstance(kernel_record, dict)
        or kernel_record != {"code_file": "run.py", "sha256": runner_sha256}
        or not isinstance(files, list)
        or not files
        or not isinstance(private_outputs, list)
        or not private_outputs
        or len(run_config_records) != 1
    ):
        raise PackagingError("source_manifest_bundle_invalid")
    try:
        registry = registry_path.resolve(strict=True)
        if (
            registry_path.is_symlink()
            or not registry.is_file()
            or registry.stat().st_mode & 0o077
            or re.fullmatch(r"audit-[a-z0-9][a-z0-9_-]{0,63}", audit_id) is None
        ):
            raise PackagingError("source_manifest_registry_invalid")
        with sqlite3.connect(f"file:{registry}?mode=ro&immutable=1", uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            row = connection.execute(
                "SELECT status,config_hash,manifest_version FROM audit_runs WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
    except (OSError, sqlite3.Error) as error:
        raise PackagingError("source_manifest_registry_invalid") from error
    if (
        row is None
        or row[0] != "completed"
        or row[2] != SOURCE_MANIFEST_VERSION
        or row[1] != run_config_records[0].get("sha256")
    ):
        raise PackagingError("source_manifest_registry_invalid")
    kernel_ref = kernel_metadata.get("id")
    dataset_ref = dataset_metadata.get("id")
    if (
        not isinstance(kernel_ref, str)
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}/[a-z0-9][a-z0-9_-]{0,99}", kernel_ref) is None
        or not isinstance(dataset_ref, str)
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}/[a-z0-9][a-z0-9_-]{0,99}", dataset_ref) is None
        or kernel_metadata.get("code_file") != "run.py"
        or kernel_metadata.get("is_private") is not True
        or kernel_metadata.get("enable_internet") is not False
        or kernel_metadata.get("dataset_sources") != [dataset_ref]
        or kernel_metadata.get("competition_sources") != [COMPETITION_SLUG]
        or dataset_metadata.get("title") != dataset_ref.partition("/")[2]
    ):
        raise PackagingError("source_manifest_bundle_invalid")

    expected_dataset_files: list[dict[str, object]] = []
    observed_names: set[str] = set()
    for record in files:
        if not isinstance(record, dict):
            raise PackagingError("source_manifest_bundle_invalid")
        name = record.get("path")
        size = record.get("bytes")
        digest = record.get("sha256")
        if (
            not isinstance(name, str)
            or PurePosixPath(name).name != name
            or name in observed_names
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
            or not isinstance(digest, str)
            or HEX_64.fullmatch(digest) is None
        ):
            raise PackagingError("source_manifest_bundle_invalid")
        observed_names.add(name)
        local = dataset / name
        try:
            if (
                local.is_symlink()
                or not local.is_file()
                or local.stat().st_size != size
                or _sha256_bytes(_read_bounded(local, MAX_BUNDLE_BYTES)) != digest
            ):
                raise PackagingError("source_manifest_bundle_invalid")
        except OSError as error:
            raise PackagingError("source_manifest_bundle_invalid") from error
        expected_dataset_files.append({"name": name, "bytes": size, "sha256": digest})
    try:
        if {path.name for path in dataset.iterdir()} != {
            *observed_names,
            "bundle-manifest.json",
            "dataset-metadata.json",
        }:
            raise PackagingError("source_manifest_bundle_invalid")
    except OSError as error:
        raise PackagingError("source_manifest_bundle_invalid") from error
    normalized_config = dict(run_config)
    normalized_config["bundle_sha256"] = RUN_CONFIG_BUNDLE_PLACEHOLDER
    normalized_payload = _canonical_json_bytes(normalized_config)
    normalized_record = {
        **dict(run_config_records[0]),
        "bytes": len(normalized_payload),
        "sha256": _sha256_bytes(normalized_payload),
    }
    identity_records = [
        normalized_record if record.get("role") == "run_config" else record for record in files
    ]
    identity = {
        key: value for key, value in manifest.items() if key not in {"bundle_sha256", "files"}
    }
    identity["files"] = sorted(identity_records, key=lambda item: str(item["path"]))
    if _sha256_bytes(_canonical_json_bytes(identity)) != bundle_sha256:
        raise PackagingError("source_manifest_bundle_invalid")
    source_commit = (
        manifest.get("provenance", {}).get("git_commit")
        if isinstance(manifest.get("provenance"), dict)
        else None
    )
    owner = kernel_ref.partition("/")[0]
    if (
        not isinstance(source_commit, str)
        or HEX_40.fullmatch(source_commit) is None
        or dataset_ref
        != f"{owner}/{_derive_slug('rsna-knee-manifest-bundle', source_commit, bundle_sha256)}"
        or kernel_ref
        != f"{owner}/{_derive_slug('rsna-knee-manifest-audit', source_commit, bundle_sha256)}"
    ):
        raise PackagingError("source_manifest_bundle_invalid")
    expected_dataset_files.append(
        {
            "name": "bundle-manifest.json",
            "bytes": expected_paths["manifest"].stat().st_size,
            "sha256": _sha256_bytes(_read_bounded(expected_paths["manifest"], 2 * 1024**2)),
        }
    )
    return {
        "version": SOURCE_MANIFEST_VERSION,
        "audit_id": audit_id,
        "kernel_ref": kernel_ref,
        "kernel_version": SOURCE_MANIFEST_KERNEL_VERSION,
        "kernel_code_file": "run.py",
        "kernel_code_sha256": runner_sha256,
        "bundle_dataset_ref": dataset_ref,
        "bundle_dataset_version": 1,
        "bundle_sha256": bundle_sha256,
        "bundle_dataset_files": sorted(expected_dataset_files, key=lambda item: str(item["name"])),
        "private_output_policy": private_outputs,
        "schema_sha256": provenance["manifest_schema_sha256"],
        "artifact_inventory_filename": "private_artifact_inventory.json",
        "database_filename": "private_manifest.sqlite3",
        "audit_key_filename": "audit_key.bin",
    }


def _validate_project_wheel(path: Path) -> None:
    """Reject unsafe archives and require the production Chunk 5 modules."""

    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names: set[str] = set()
            total = 0
            for info in infos:
                member = PurePosixPath(info.filename)
                mode = info.external_attr >> 16
                if (
                    member.is_absolute()
                    or any(part in {"", ".", ".."} for part in member.parts)
                    or "\\" in info.filename
                    or info.filename in names
                    or stat.S_IFMT(mode) == stat.S_IFLNK
                    or info.file_size < 0
                ):
                    raise PackagingError("project_wheel_invalid")
                names.add(info.filename)
                total += info.file_size
            if (
                len(infos) > 10_000
                or total > MAX_BUNDLE_BYTES
                or not REQUIRED_PROJECT_WHEEL_MEMBERS.issubset(names)
            ):
                raise PackagingError("project_wheel_invalid")
    except (OSError, zipfile.BadZipFile) as error:
        raise PackagingError("project_wheel_invalid") from error


def _review_notebook_payload() -> bytes:
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# Private Chunk 5 DICOM integrity review\n",
                    "Run only in a private Chrome Kaggle session. Do not download outputs.\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "from pathlib import Path\n",
                    "root = Path('/kaggle/input')\n",
                    "matches = [p for pattern in ('*/review_ui.py', '*/*/review_ui.py')\n",
                    "           for p in root.glob(pattern)\n",
                    "           if p.is_file() and not p.is_symlink()]\n",
                    "if len(matches) != 1: raise RuntimeError('review_ui_source_invalid')\n",
                    "namespace = {'__name__': '_private_review_ui', '__file__': str(matches[0])}\n",
                    "exec(compile(matches[0].read_bytes(), str(matches[0]), 'exec'), namespace)\n",
                    "namespace['run_review']()\n",
                ],
            },
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return _canonical_json_bytes(notebook)


def _derived_refs(owner: str, commit: str, bundle: str) -> dict[str, str]:
    prefixes = {
        "performance_smoke": "rsna-knee-dqa-smoke",
        "run_a": "rsna-knee-dqa-a",
        "run_b": "rsna-knee-dqa-b",
        "comparison": "rsna-knee-dqa-cmp",
        "review_plan": "rsna-knee-dqa-plan",
        "review_ui_template": "rsna-knee-dqa-ui",
        "review_session": "rsna-knee-dqa-review",
        "review_finalizer": "rsna-knee-dqa-final",
    }
    return {
        role: f"{owner}/{_derive_slug(prefix, commit, bundle)}" for role, prefix in prefixes.items()
    }


def _require_runtime_wheels(paths: Sequence[Path]) -> None:
    if not paths:
        raise PackagingError("dependency_wheelhouse_empty")
    names: set[str] = set()
    for path in paths:
        _validate_linux_wheel(path)
        if path.name in names:
            raise PackagingError("dependency_wheel_name_duplicate")
        names.add(path.name)
    for distribution, version in REQUIRED_RUNTIME_PACKAGES.items():
        if not any(
            _wheel_distribution(path) == distribution and f"-{version}-" in path.name.lower()
            for path in paths
        ):
            raise PackagingError("required_runtime_wheel_missing")
    distributions = {_wheel_distribution(path) for path in paths}
    for distribution in distributions:
        names_for_distribution = [
            path.name.lower() for path in paths if _wheel_distribution(path) == distribution
        ]
        if not any("-none-any.whl" in name for name in names_for_distribution) and not (
            any("cp311" in name for name in names_for_distribution)
            and any("cp312" in name for name in names_for_distribution)
        ):
            raise PackagingError("dependency_python_coverage_invalid")


def _normalized_run_record(run_config: Mapping[str, object]) -> dict[str, object]:
    normalized = dict(run_config)
    normalized["bundle_sha256"] = RUN_CONFIG_BUNDLE_PLACEHOLDER
    payload = _canonical_json_bytes(normalized)
    return {
        "path": "run-config.json",
        "role": "run_config",
        "source_path": "generated/run-config.json",
        "bytes": len(payload),
        "sha256": _sha256_bytes(payload),
    }


def _bundle_identity(
    *,
    owner: str,
    git_commit: str,
    git_commit_timestamp: int,
    kernel_sha256: str,
    performance_smoke_sha256: str,
    performance_smoke_policy_sha256: str,
    comparison_sha256: str,
    review_finalizer_sha256: str,
    review_ui_sha256: str,
    review_notebook_sha256: str,
    output_validator_sha256: str,
    records: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "bundle_format": BUNDLE_FORMAT,
        "provenance": {
            "git_commit": git_commit,
            "git_commit_timestamp": git_commit_timestamp,
        },
        "deployment": {"owner": owner},
        "competition": {"slug": COMPETITION_SLUG},
        "kernel": {"code_file": "run.py", "sha256": kernel_sha256},
        "performance_smoke": {
            "code_file": "performance_smoke.py",
            "sha256": performance_smoke_sha256,
            "policy_file": PERFORMANCE_SMOKE_POLICY_BASENAME,
            "policy_sha256": performance_smoke_policy_sha256,
        },
        "comparison": {"code_file": "compare_runs.py", "sha256": comparison_sha256},
        "review_finalizer": {
            "code_file": "finalize_review.py",
            "sha256": review_finalizer_sha256,
        },
        "review_ui": {
            "code_file": REVIEW_NOTEBOOK_BASENAME,
            "sha256": review_notebook_sha256,
            "module_file": "review_ui.py",
            "module_sha256": review_ui_sha256,
        },
        "output_validator": {
            "code_file": "validate_output.py",
            "sha256": output_validator_sha256,
        },
        "files": sorted((dict(record) for record in records), key=lambda item: str(item["path"])),
    }


def _run_config(
    *,
    owner: str,
    commit: str,
    runner_sha256: str,
    performance_smoke_sha256: str,
    performance_smoke_policy_sha256: str,
    comparison_sha256: str,
    review_finalizer_sha256: str,
    review_ui_sha256: str,
    review_notebook_sha256: str,
    output_validator_sha256: str,
    source_manifest_identity: Mapping[str, object],
    preprocessing_version: str,
    records: Sequence[Mapping[str, object]],
    dependency_records: Sequence[Mapping[str, object]],
    workers: int,
) -> dict[str, object]:
    if not 1 <= workers <= 16:
        raise PackagingError("worker_count_invalid")
    by_role = {str(record["role"]): record for record in records}
    dependency_identity = [
        {"path": record["path"], "bytes": record["bytes"], "sha256": record["sha256"]}
        for record in sorted(dependency_records, key=lambda item: str(item["path"]))
    ]
    privacy_canary = (
        "RSNA_PRIVATE_CANARY_" + hashlib.sha256(f"{commit}:dicom-qa-v1".encode()).hexdigest()[:32]
    )
    return {
        "schema_version": 1,
        "run_id": f"dicom-qa-{commit[:12]}",
        "code_commit": commit,
        "bundle_sha256": RUN_CONFIG_BUNDLE_PLACEHOLDER,
        "deployment": {"owner": owner},
        "competition": {"slug": COMPETITION_SLUG, "source": "official_competition_input"},
        "provenance": {
            "git_commit": commit,
            "preprocessing_config_sha256": by_role["preprocessing_config"]["sha256"],
            "preprocessing_schema_sha256": by_role["preprocessing_schema"]["sha256"],
            "competition_config_sha256": by_role["competition_pointer"]["sha256"],
            "competition_contract_sha256": by_role["competition_contract"]["sha256"],
            "uv_lock_sha256": by_role["dependency_lock"]["sha256"],
            "preprocessing_version": preprocessing_version,
            "source_manifest_version": SOURCE_MANIFEST_VERSION,
            "renderer_version": "private-qa-renderer-v1",
            "required_runtime_packages": dict(REQUIRED_RUNTIME_PACKAGES),
            "runner_sha256": runner_sha256,
            "performance_smoke_sha256": performance_smoke_sha256,
            "performance_smoke_policy_sha256": performance_smoke_policy_sha256,
            "comparison_sha256": comparison_sha256,
            "review_finalizer_sha256": review_finalizer_sha256,
            "review_ui_sha256": review_ui_sha256,
            "review_notebook_sha256": review_notebook_sha256,
            "output_validator_sha256": output_validator_sha256,
            "synthetic_preflight_sha256": by_role["synthetic_preflight"]["sha256"],
        },
        "input_identity": {
            "official_competition": {
                "slug": COMPETITION_SLUG,
                "contract_sha256": by_role["competition_contract"]["sha256"],
                "snapshot_identity_source": "chunk4_private_manifest",
            },
            "source_manifest": dict(source_manifest_identity),
        },
        "review_policy": {
            "protocol_version": REVIEW_PROTOCOL_VERSION,
            "instructions_version": REVIEW_INSTRUCTIONS_VERSION,
            "cohort_selection_version": QA_COHORT_SELECTION_VERSION,
            "stratum_registry_version": QA_STRATUM_REGISTRY_VERSION,
            "stratum_registry_sha256": QA_STRATUM_REGISTRY_SHA256,
            "kernel_version": QA_KERNEL_VERSION,
            "checks": list(REVIEW_CHECKS),
            "statuses": list(REVIEW_STATUSES),
            "artifact_presence_separate": True,
            "minimum_reviewed_studies": MINIMUM_ELIGIBLE_STUDIES,
        },
        "runtime_dependencies": {
            "target_platforms": list(TARGET_PLATFORMS),
            "python_versions": list(TARGET_PYTHONS),
            "install_mode": "pip-no-index-find-links",
            "wheel_count": len(dependency_identity),
            "wheel_set_sha256": _sha256_bytes(_canonical_json_bytes(dependency_identity)),
        },
        "selection": {
            "source": "full_run_terminal_records_plus_authenticated_manifest_v2",
            "minimum_studies": MINIMUM_ELIGIBLE_STUDIES,
            "minimum_is_not_maximum": True,
            "represented_value_quota": REPRESENTED_VALUE_QUOTA,
            "stratum_registry_version": QA_STRATUM_REGISTRY_VERSION,
            "stratum_registry_sha256": QA_STRATUM_REGISTRY_SHA256,
            "cohort_selection_version": QA_COHORT_SELECTION_VERSION,
            "dimensions": list(REQUIRED_REVIEW_DIMENSIONS),
        },
        "workers": workers,
        "privacy": {
            "canary": privacy_canary,
            "raw_identifiers_downloadable": False,
            "raw_paths_downloadable": False,
            "raw_reports_downloadable": False,
            "patient_metadata_downloadable": False,
            "pixel_data_downloadable": False,
            "case_details_downloadable": False,
            "private_visuals_remote_only": True,
        },
        "anatomical_safety": {
            "physical_order_required": True,
            "horizontal_flip": False,
            "through_plane_resampling": False,
            "laterality_transform": "none",
        },
        "runtime": {
            "internet": False,
            "accelerator": "cpu",
            "self_deadline_seconds": SELF_DEADLINE_SECONDS,
            "outer_kill_seconds": OUTER_KILL_SECONDS,
        },
        "output_policy": {
            "run_private_remote_only": list(RUN_PRIVATE_OUTPUTS),
            "run_downloadable": list(RUN_DOWNLOADABLE_OUTPUTS),
            "review_private_remote_only": list(REVIEW_PRIVATE_OUTPUTS),
            "review_private_remote_patterns": list(REVIEW_PRIVATE_PATTERN_OUTPUTS),
            "review_downloadable": list(REVIEW_DOWNLOADABLE_OUTPUTS),
            "session_log": SESSION_LOG_POLICY,
            "run_max_remote_bytes": 548 * 1024**2 + 384 * 1024,
            "run_max_download_bytes": 384 * 1024,
            "review_max_remote_bytes": 8 * 1024**3 + 66 * 1024**2 + 512 * 1024,
            "review_max_download_bytes": 512 * 1024,
        },
    }


def _assemble_bundle(
    *,
    output: Path,
    owner: str,
    git_commit: str,
    git_commit_timestamp: int,
    wheel_path: Path,
    dependency_wheel_paths: Sequence[Path],
    runtime_requirements_path: Path,
    preprocessing_config_path: Path,
    preprocessing_schema_path: Path,
    manifest_schema_path: Path,
    competition_config_path: Path,
    competition_contract_path: Path,
    uv_lock_path: Path,
    kernel_runner_path: Path,
    performance_smoke_path: Path,
    comparison_path: Path,
    review_finalizer_path: Path,
    review_ui_path: Path,
    output_validator_path: Path,
    synthetic_preflight_path: Path,
    source_manifest_bundle_root: Path,
    source_manifest_registry_path: Path,
    source_manifest_audit_id: str,
    workers: int = 4,
    core_reuse: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Assemble deterministic dataset/kernel directories from immutable inputs."""

    if output.exists():
        raise PackagingError("output_exists")
    if not SAFE_SLUG.fullmatch(owner):
        raise PackagingError("owner_invalid")
    if not HEX_40.fullmatch(git_commit) or git_commit_timestamp < 1:
        raise PackagingError("git_provenance_invalid")
    if wheel_path.suffix != ".whl":
        raise PackagingError("wheel_name_invalid")
    _validate_project_wheel(wheel_path)
    _require_runtime_wheels(dependency_wheel_paths)
    if (
        _validate_contract_pair(competition_config_path, competition_contract_path)
        != COMPETITION_SLUG
    ):
        raise PackagingError("competition_identity_invalid")
    preprocessing_config = _validate_preprocessing_config(preprocessing_config_path)
    _validate_preprocessing_schema(preprocessing_schema_path)
    source_manifest_identity = _source_manifest_identity(
        source_manifest_bundle_root,
        manifest_schema_path,
        source_manifest_registry_path,
        source_manifest_audit_id,
    )
    runner_payload = _read_bounded(kernel_runner_path, 1024 * 1024)
    _scan_for_secrets(runner_payload)
    runner_sha256 = _sha256_bytes(runner_payload)
    performance_smoke_payload = _read_bounded(performance_smoke_path, 1024 * 1024)
    _scan_for_secrets(performance_smoke_payload)
    performance_smoke_sha256 = _sha256_bytes(performance_smoke_payload)
    performance_smoke_policy_payload = _canonical_json_bytes(
        _performance_smoke_policy(performance_smoke_sha256)
    )
    performance_smoke_policy_sha256 = _sha256_bytes(performance_smoke_policy_payload)
    comparison_payload = _read_bounded(comparison_path, 1024 * 1024)
    _scan_for_secrets(comparison_payload)
    comparison_sha256 = _sha256_bytes(comparison_payload)
    review_finalizer_payload = _read_bounded(review_finalizer_path, 1024 * 1024)
    _scan_for_secrets(review_finalizer_payload)
    review_ui_payload = _read_bounded(review_ui_path, 1024 * 1024)
    _scan_for_secrets(review_ui_payload)
    review_ui_sha256 = _sha256_bytes(review_ui_payload)
    review_notebook_payload = _review_notebook_payload()
    review_notebook_sha256 = _sha256_bytes(review_notebook_payload)
    output_validator_payload = _read_bounded(output_validator_path, 2 * 1024 * 1024)
    _scan_for_secrets(output_validator_payload)
    output_validator_sha256 = _sha256_bytes(output_validator_payload)
    _validate_synthetic_preflight(synthetic_preflight_path)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    try:
        dataset_dir = temporary_root / "dataset"
        performance_smoke_dir = temporary_root / "performance-smoke-kernel"
        run_a_dir = temporary_root / "kernel-a"
        run_b_dir = temporary_root / "kernel-b"
        comparison_dir = temporary_root / "comparison-kernel"
        review_plan_dir = temporary_root / "review-plan-kernel"
        review_ui_dir = temporary_root / "review-ui-template-kernel"
        review_finalizer_dir = temporary_root / "review-finalizer-kernel"
        dataset_dir.mkdir()
        for directory in (
            performance_smoke_dir,
            run_a_dir,
            run_b_dir,
            comparison_dir,
            review_plan_dir,
            review_ui_dir,
            review_finalizer_dir,
        ):
            directory.mkdir()
        payload_specs = (
            (wheel_path, dataset_dir / wheel_path.name, "project_wheel", "dist/project.whl", False),
            (
                preprocessing_config_path,
                dataset_dir / "preprocessing.json",
                "preprocessing_config",
                "configs/preprocessing.v1.json",
                True,
            ),
            (
                preprocessing_schema_path,
                dataset_dir / "preprocessing.schema.json",
                "preprocessing_schema",
                "configs/preprocessing.v1.schema.json",
                True,
            ),
            (
                manifest_schema_path,
                dataset_dir / "manifest_schema.yaml",
                "source_manifest_schema",
                "configs/manifest_schema.yaml",
                True,
            ),
            (
                competition_config_path,
                dataset_dir / "competition.json",
                "competition_pointer",
                "configs/competition.yaml",
                True,
            ),
            (
                competition_contract_path,
                dataset_dir / "competition-contract.json",
                "competition_contract",
                "docs/competition_contract/contract.yaml",
                True,
            ),
            (uv_lock_path, dataset_dir / "uv.lock", "dependency_lock", "uv.lock", True),
            (
                runtime_requirements_path,
                dataset_dir / "runtime-requirements.txt",
                "runtime_requirements",
                "generated/runtime-requirements.txt",
                True,
            ),
            (
                review_finalizer_path,
                dataset_dir / "finalize_review.py",
                "review_finalizer",
                "kaggle/dicom_qa/finalize_review.py",
                True,
            ),
            (
                comparison_path,
                dataset_dir / "compare_runs.py",
                "comparison_source",
                "kaggle/dicom_qa/compare_runs.py",
                True,
            ),
            (
                review_ui_path,
                dataset_dir / "review_ui.py",
                "review_ui_source",
                "kaggle/dicom_qa/review_ui.py",
                True,
            ),
            (
                output_validator_path,
                dataset_dir / "validate_output.py",
                "output_validator",
                "scripts/validate_dicom_qa_output.py",
                True,
            ),
            (
                kernel_runner_path,
                dataset_dir / "qa_runner.py",
                "runner_source",
                "kaggle/dicom_qa/run.py",
                True,
            ),
            (
                performance_smoke_path,
                dataset_dir / "performance_smoke.py",
                "performance_smoke_source",
                "kaggle/dicom_qa/performance_smoke.py",
                True,
            ),
            (
                synthetic_preflight_path,
                dataset_dir / SYNTHETIC_PREFLIGHT_BASENAME,
                "synthetic_preflight",
                "generated/synthetic-preflight.json",
                True,
            ),
        )
        _write_bytes(
            dataset_dir / REVIEW_NOTEBOOK_BASENAME,
            review_notebook_payload,
            git_commit_timestamp,
        )
        _write_bytes(
            dataset_dir / PERFORMANCE_SMOKE_POLICY_BASENAME,
            performance_smoke_policy_payload,
            git_commit_timestamp,
        )
        for source, target, _role, _source_path, scan in payload_specs:
            _copy_payload(
                source=source,
                target=target,
                maximum_bytes=MAX_BUNDLE_BYTES,
                timestamp=git_commit_timestamp,
                scan_secrets=scan,
            )
        records = [
            _file_record(target, role, source_path)
            for _source, target, role, source_path, _scan in payload_specs
        ]
        records.append(
            _file_record(
                dataset_dir / REVIEW_NOTEBOOK_BASENAME,
                "review_notebook",
                "generated/review_ui.ipynb",
            )
        )
        records.append(
            _file_record(
                dataset_dir / PERFORMANCE_SMOKE_POLICY_BASENAME,
                "performance_smoke_policy",
                f"generated/{PERFORMANCE_SMOKE_POLICY_BASENAME}",
            )
        )
        dependency_records: list[dict[str, object]] = []
        for dependency in sorted(dependency_wheel_paths, key=lambda path: path.name):
            target = dataset_dir / dependency.name
            _copy_payload(
                source=dependency,
                target=target,
                maximum_bytes=MAX_BUNDLE_BYTES,
                timestamp=git_commit_timestamp,
                scan_secrets=False,
            )
            record = _file_record(target, "dependency_wheel", f"wheelhouse/{dependency.name}")
            records.append(record)
            dependency_records.append(record)

        run_config = _run_config(
            owner=owner,
            commit=git_commit,
            runner_sha256=runner_sha256,
            performance_smoke_sha256=performance_smoke_sha256,
            performance_smoke_policy_sha256=performance_smoke_policy_sha256,
            comparison_sha256=comparison_sha256,
            review_finalizer_sha256="",
            review_ui_sha256=review_ui_sha256,
            review_notebook_sha256=review_notebook_sha256,
            output_validator_sha256=output_validator_sha256,
            source_manifest_identity=source_manifest_identity,
            preprocessing_version=str(preprocessing_config["preprocessing_version"]),
            records=records,
            dependency_records=dependency_records,
            workers=workers,
        )
        # ponytail: finalizer hash is finalized after packaging-time policy injection.
        run_config["provenance"]["review_finalizer_sha256"] = ""
        if core_reuse is not None and set(core_reuse) != {
            "core_lineage_id",
            "core_certificate_payload_sha256",
            "upstream_refs",
        }:
            raise PackagingError("core_reuse_invalid")
        finalizer_text = _read_bounded(review_finalizer_path, 1024 * 1024).decode("ascii")
        marker = "CORE_REUSE_POLICY: Final = "
        prefix, marker_present, suffix = finalizer_text.partition(marker)
        if not marker_present or "\n" not in suffix:
            raise PackagingError("review_finalizer_binding_invalid")
        suffix = suffix.split("\n", 1)[1]
        reuse_payload = None if core_reuse is None else _canonical_json_bytes(core_reuse)
        reuse_literal = "None" if reuse_payload is None else reuse_payload.decode("ascii").strip()
        finalizer_text = f"{prefix}{marker}{reuse_literal}\n{suffix}"
        review_finalizer_payload = finalizer_text.encode("ascii")
        review_finalizer_sha256 = _sha256_bytes(review_finalizer_payload)
        run_config["provenance"]["review_finalizer_sha256"] = review_finalizer_sha256
        finalizer_record = next(item for item in records if item["path"] == "finalize_review.py")
        with open(dataset_dir / "finalize_review.py", "r+b") as handle:
            handle.write(review_finalizer_payload)
            handle.truncate()
        finalizer_record["bytes"] = len(review_finalizer_payload)
        finalizer_record["sha256"] = review_finalizer_sha256
        normalized_record = _normalized_run_record(run_config)
        upstream_refs = core_reuse["upstream_refs"] if core_reuse is not None else {}
        identity = _bundle_identity(
            owner=owner,
            git_commit=git_commit,
            git_commit_timestamp=git_commit_timestamp,
            kernel_sha256=runner_sha256,
            performance_smoke_sha256=performance_smoke_sha256,
            performance_smoke_policy_sha256=performance_smoke_policy_sha256,
            comparison_sha256=comparison_sha256,
            review_finalizer_sha256=review_finalizer_sha256,
            review_ui_sha256=review_ui_sha256,
            review_notebook_sha256=review_notebook_sha256,
            output_validator_sha256=output_validator_sha256,
            records=[*records, normalized_record],
        )
        bundle_sha256 = _sha256_bytes(_canonical_json_bytes(identity))
        run_config["bundle_sha256"] = bundle_sha256
        run_config_path = dataset_dir / "run-config.json"
        _write_bytes(run_config_path, _canonical_json_bytes(run_config), git_commit_timestamp)
        records.append(_file_record(run_config_path, "run_config", "generated/run-config.json"))
        manifest = {
            **identity,
            "bundle_sha256": bundle_sha256,
            "files": sorted(records, key=lambda item: str(item["path"])),
        }
        _write_bytes(
            dataset_dir / "bundle-manifest.json",
            _canonical_json_bytes(manifest),
            git_commit_timestamp,
        )
        if sum(path.stat().st_size for path in dataset_dir.iterdir()) > MAX_BUNDLE_BYTES:
            raise PackagingError("bundle_too_large")

        dataset_slug = _derive_slug("rsna-knee-dicom-qa-bundle", git_commit, bundle_sha256)
        dataset_ref = f"{owner}/{dataset_slug}"
        refs = _derived_refs(owner, git_commit, bundle_sha256)
        dataset_metadata = {
            "title": dataset_slug,
            "id": dataset_ref,
            "licenses": [{"name": "other"}],
            "description": (
                "PRIVATE TEAM-ONLY immutable offline code/configuration/Linux-wheel bundle. "
                "Contains no competition data, pixels, reports, identifiers, credentials, "
                "checkpoints, or predictions. Do not publish or share."
            ),
        }
        _write_bytes(
            dataset_dir / "dataset-metadata.json",
            _canonical_json_bytes(dataset_metadata),
            git_commit_timestamp,
        )
        if sum(path.stat().st_size for path in dataset_dir.iterdir()) > MAX_BUNDLE_BYTES:
            raise PackagingError("bundle_too_large")
        source_manifest_ref = str(source_manifest_identity["kernel_ref"])

        def write_kernel(
            directory: Path,
            *,
            ref: str,
            code_file: str,
            payload: bytes,
            kernel_sources: Sequence[str],
            competition_sources: Sequence[str] = (),
            kernel_type: str = "script",
        ) -> None:
            _write_bytes(directory / code_file, payload, git_commit_timestamp)
            metadata = {
                "id": ref,
                "title": ref.partition("/")[2],
                "code_file": code_file,
                "language": "python",
                "kernel_type": kernel_type,
                "is_private": True,
                "enable_gpu": False,
                "enable_tpu": False,
                "enable_internet": False,
                "machine_shape": "",
                "dataset_sources": [dataset_ref],
                "competition_sources": list(competition_sources),
                "kernel_sources": list(kernel_sources),
                "model_sources": [],
            }
            _write_bytes(
                directory / "kernel-metadata.json",
                _canonical_json_bytes(metadata),
                git_commit_timestamp,
            )

        write_kernel(
            performance_smoke_dir,
            ref=refs["performance_smoke"],
            code_file="performance_smoke.py",
            payload=performance_smoke_payload,
            kernel_sources=[source_manifest_ref],
            competition_sources=[COMPETITION_SLUG],
        )
        for directory, role in ((run_a_dir, "run_a"), (run_b_dir, "run_b")):
            write_kernel(
                directory,
                ref=refs[role],
                code_file="run.py",
                payload=runner_payload,
                kernel_sources=[source_manifest_ref],
                competition_sources=[COMPETITION_SLUG],
            )
        write_kernel(
            comparison_dir,
            ref=refs["comparison"],
            code_file="compare_runs.py",
            payload=comparison_payload,
            kernel_sources=[
                upstream_refs.get("run_a", refs["run_a"]),
                upstream_refs.get("run_b", refs["run_b"]),
            ],
        )
        write_kernel(
            review_plan_dir,
            ref=refs["review_plan"],
            code_file="finalize_review.py",
            payload=review_finalizer_payload,
            kernel_sources=[
                upstream_refs.get("performance_smoke", refs["performance_smoke"]),
                upstream_refs.get("run_a", refs["run_a"]),
                upstream_refs.get("run_b", refs["run_b"]),
                upstream_refs.get("comparison", refs["comparison"]),
            ],
            competition_sources=[COMPETITION_SLUG],
        )
        review_sources = [
            upstream_refs.get("run_a", refs["run_a"]),
            upstream_refs.get("run_b", refs["run_b"]),
            upstream_refs.get("comparison", refs["comparison"]),
            refs["review_plan"],
        ]
        write_kernel(
            review_ui_dir,
            ref=refs["review_ui_template"],
            code_file=REVIEW_NOTEBOOK_BASENAME,
            payload=review_notebook_payload,
            kernel_sources=review_sources,
            kernel_type="notebook",
        )
        write_kernel(
            review_finalizer_dir,
            ref=refs["review_finalizer"],
            code_file="finalize_review.py",
            payload=review_finalizer_payload,
            kernel_sources=[
                upstream_refs.get("run_a", refs["run_a"]),
                upstream_refs.get("run_b", refs["run_b"]),
                upstream_refs.get("comparison", refs["comparison"]),
                refs["review_plan"],
                refs["review_session"],
            ],
        )
        directories = [
            dataset_dir,
            performance_smoke_dir,
            run_a_dir,
            run_b_dir,
            comparison_dir,
            review_plan_dir,
            review_ui_dir,
            review_finalizer_dir,
        ]
        for directory in (*directories, temporary_root):
            # Directory mtimes are part of deterministic local bundle comparisons.
            os.utime(directory, (git_commit_timestamp, git_commit_timestamp))
        temporary_root.rename(output)
    except BaseException:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise
    result = {
        "bundle_sha256": bundle_sha256,
        "dataset_ref": dataset_ref,
        "source_manifest_kernel_ref": str(source_manifest_identity["kernel_ref"]),
        **{f"{role}_ref": ref for role, ref in refs.items()},
    }
    # Legacy aliases remain read-only conveniences while callers migrate to explicit A/B roles.
    result["kernel_ref"] = refs["run_a"]
    result["review_kernel_ref"] = refs["review_finalizer"]
    return result


def _clean_git_provenance(repo_root: Path) -> tuple[str, int]:
    commit = _git_output(repo_root, ["rev-parse", "--verify", "HEAD"])
    if not HEX_40.fullmatch(commit):
        raise PackagingError("git_commit_invalid")
    if _git_output(repo_root, ["status", "--porcelain=v1", "--untracked-files=all"]):
        raise PackagingError("git_worktree_dirty")
    timestamp_text = _git_output(repo_root, ["show", "-s", "--format=%ct", "HEAD"])
    try:
        timestamp = int(timestamp_text)
    except ValueError as error:
        raise PackagingError("git_timestamp_invalid") from error
    for relative in (
        "configs/preprocessing.v1.json",
        "configs/preprocessing.v1.schema.json",
        "configs/manifest_schema.yaml",
        "configs/competition.yaml",
        "docs/competition_contract/contract.yaml",
        "uv.lock",
        "kaggle/dicom_qa/run.py",
        "kaggle/dicom_qa/performance_smoke.py",
        "kaggle/dicom_qa/compare_runs.py",
        "kaggle/dicom_qa/finalize_review.py",
        "kaggle/dicom_qa/review_ui.py",
        "scripts/run_dicom_qa_synthetic_preflight.py",
        "scripts/validate_dicom_qa_output.py",
    ):
        _git_output(repo_root, ["ls-files", "--error-unmatch", relative])
    return commit, timestamp


def _require_ignored_private_input(repo_root: Path, path: Path) -> None:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(repo_root):
        return
    try:
        completed = subprocess.run(
            ["git", "check-ignore", "--quiet", "--", str(resolved)],
            cwd=repo_root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise PackagingError("private_input_ignore_check_failed") from error
    if completed.returncode != 0:
        raise PackagingError("private_input_not_ignored")


def package_from_clean_repo(args: argparse.Namespace) -> dict[str, str]:
    repo_root = args.repo_root.resolve()
    commit, timestamp = _clean_git_provenance(repo_root)
    _require_ignored_private_input(repo_root, args.source_manifest_bundle_root)
    _require_ignored_private_input(repo_root, args.source_manifest_registry)
    with tempfile.TemporaryDirectory(prefix="rsna-knee-dicom-qa-wheel-") as temporary:
        build_root = Path(temporary)
        project_dir = build_root / "project"
        project_dir.mkdir()
        project_wheel = _build_wheel(repo_root, timestamp, project_dir)
        dependencies, requirements = _prepare_runtime_wheels(
            repo_root, timestamp, build_root / "wheelhouse"
        )
        host_dependencies = _prepare_host_preflight_wheels(
            runtime_requirements=requirements,
            linux_dependency_wheels=dependencies,
            destination=build_root / "host-wheelhouse",
            timestamp=timestamp,
            repo_root=repo_root,
        )
        synthetic_preflight = build_root / SYNTHETIC_PREFLIGHT_BASENAME
        _write_bytes(
            synthetic_preflight,
            _run_packaged_synthetic_preflight(
                project_wheel=project_wheel,
                host_dependency_wheels=host_dependencies,
                linux_dependency_wheels=dependencies,
                runtime_requirements=requirements,
                preprocessing_config=repo_root / "configs/preprocessing.v1.json",
                code_commit=commit,
                entrypoint=repo_root / "scripts/run_dicom_qa_synthetic_preflight.py",
            ),
            timestamp,
        )
        return _assemble_bundle(
            output=args.output.resolve(),
            owner=args.owner,
            git_commit=commit,
            git_commit_timestamp=timestamp,
            wheel_path=project_wheel,
            dependency_wheel_paths=dependencies,
            runtime_requirements_path=requirements,
            preprocessing_config_path=repo_root / "configs/preprocessing.v1.json",
            preprocessing_schema_path=repo_root / "configs/preprocessing.v1.schema.json",
            manifest_schema_path=repo_root / "configs/manifest_schema.yaml",
            competition_config_path=repo_root / "configs/competition.yaml",
            competition_contract_path=repo_root / "docs/competition_contract/contract.yaml",
            uv_lock_path=repo_root / "uv.lock",
            kernel_runner_path=repo_root / "kaggle/dicom_qa/run.py",
            performance_smoke_path=repo_root / "kaggle/dicom_qa/performance_smoke.py",
            comparison_path=repo_root / "kaggle/dicom_qa/compare_runs.py",
            review_finalizer_path=repo_root / "kaggle/dicom_qa/finalize_review.py",
            review_ui_path=repo_root / "kaggle/dicom_qa/review_ui.py",
            output_validator_path=repo_root / "scripts/validate_dicom_qa_output.py",
            synthetic_preflight_path=synthetic_preflight,
            source_manifest_bundle_root=args.source_manifest_bundle_root,
            source_manifest_registry_path=args.source_manifest_registry,
            source_manifest_audit_id=args.source_manifest_audit_id,
            workers=args.workers,
            core_reuse=args.core_reuse,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--source-manifest-bundle-root",
        type=Path,
        required=True,
        help="Ignored mode-600 root of the successful immutable Chunk 4 private bundle.",
    )
    parser.add_argument(
        "--source-manifest-registry",
        type=Path,
        required=True,
        help="Ignored mode-600 registry containing the completed source-manifest audit row.",
    )
    parser.add_argument(
        "--source-manifest-audit-id",
        required=True,
        help="Completed manifest-v2 audit ID; audit-0001 is superseded and invalid.",
    )
    parser.add_argument(
        "--core-reuse",
        type=str,
        default=None,
        help=(
            "Optional JSON object with core_lineage_id, "
            "core_certificate_payload_sha256, and upstream_refs for stage-aware reuse."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if getattr(args, "core_reuse", None) is not None:
            try:
                args.core_reuse = json.loads(args.core_reuse)
            except json.JSONDecodeError:
                print("dicom_qa_bundle=FAIL code=core_reuse_json_invalid")
                return 2
            if not isinstance(args.core_reuse, dict):
                print("dicom_qa_bundle=FAIL code=core_reuse_not_object")
                return 2
        else:
            args.core_reuse = None
        result = package_from_clean_repo(args)
    except PackagingError as error:
        print(f"dicom_qa_bundle=FAIL code={error.code}")
        return 2
    except Exception:
        print("dicom_qa_bundle=FAIL code=internal_error")
        return 2
    print(f"dicom_qa_bundle=PASS bundle_sha256={result['bundle_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
