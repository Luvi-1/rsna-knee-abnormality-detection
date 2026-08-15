"""Build an immutable, private Kaggle dataset and thin script bundle.

The command intentionally stops at local packaging. Dataset creation and kernel
pushes remain separate, approval-gated operations.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Final

BUNDLE_FORMAT: Final = "rsna-knee-manifest-audit-bundle-v1"
COMPETITION_SLUG: Final = "rsna-knee-abnormality-detection"
DEFAULT_RUNNER_MODULE: Final = "rsna_knee.data.manifest"
DEFAULT_RUNNER_CALLABLE: Final = "run_manifest_audit"
MAX_BUNDLE_BYTES: Final = 64 * 1024 * 1024
RUN_CONFIG_BUNDLE_PLACEHOLDER: Final = "0" * 64
TARGET_PLATFORMS: Final = (
    "manylinux_2_27_x86_64",
    "manylinux_2_28_x86_64",
    "manylinux2014_x86_64",
)
TARGET_PYTHONS: Final = ("3.11", "3.12")
PYDICOM_TEST_TREE: Final = ("pydicom", "data", "test_files")
MEDICAL_WHEEL_SUFFIXES: Final = frozenset({".dcm", ".dicom"})
OUTPUT_DIRECTORY: Final = "audit-output"
AUDIT_KEY_FILENAME: Final = "audit-key.bin"
REQUIRED_DECODER_PACKAGES: Final = {
    "pylibjpeg": "2.1.0",
    "pylibjpeg-libjpeg": "2.4.0",
    "pylibjpeg-openjpeg": "2.5.0",
}

PRIVATE_OUTPUTS: Final = (
    {"path": f"{OUTPUT_DIRECTORY}/private_manifest.sqlite3", "max_bytes": 8 * 1024**3},
    {
        "path": f"{OUTPUT_DIRECTORY}/private_duplicate_groups.csv",
        "max_bytes": 256 * 1024**2,
    },
    {
        "path": f"{OUTPUT_DIRECTORY}/private_preliminary_group_keys.csv",
        "max_bytes": 256 * 1024**2,
    },
    {"path": f"{OUTPUT_DIRECTORY}/private_qa_samples.csv", "max_bytes": 64 * 1024**2},
    {"path": f"{OUTPUT_DIRECTORY}/private_artifact_inventory.json", "max_bytes": 1024 * 1024},
    {"path": f"{OUTPUT_DIRECTORY}/audit_key.bin", "max_bytes": 64, "exact_bytes": 32},
)
DOWNLOADABLE_OUTPUTS: Final = (
    {
        "path": f"{OUTPUT_DIRECTORY}/sanitized_summary.json",
        "kind": "aggregate_json",
        "max_bytes": 1024**2,
    },
    {
        "path": f"{OUTPUT_DIRECTORY}/data_audit.md",
        "kind": "documentation",
        "max_bytes": 512 * 1024,
    },
    {
        "path": f"{OUTPUT_DIRECTORY}/leakage_audit.md",
        "kind": "documentation",
        "max_bytes": 512 * 1024,
    },
    {
        "path": f"{OUTPUT_DIRECTORY}/domain_shift_audit.md",
        "kind": "documentation",
        "max_bytes": 512 * 1024,
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
SECRET_PATTERNS: Final = (
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"KAGGLE_API_TOKEN\s*[:=]\s*[^\s\"']+", re.IGNORECASE),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
)
SAFE_SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,49}\Z")
SAFE_IMPORT = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,199}\Z")
HEX_40 = re.compile(r"[0-9a-f]{40}\Z")


class PackagingError(RuntimeError):
    """A stable packaging failure that never carries source contents."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _canonical_json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise PackagingError("unsafe_relative_path")
    if any(not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", part) for part in path.parts):
        raise PackagingError("unsafe_relative_path")
    return path.as_posix()


def _read_bounded(path: Path, maximum_bytes: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise PackagingError("source_not_regular_file")
    size = path.stat().st_size
    if size <= 0 or size > maximum_bytes:
        raise PackagingError("source_size_invalid")
    with path.open("rb") as stream:
        payload = stream.read(maximum_bytes + 1)
    if len(payload) != size:
        raise PackagingError("source_changed_during_read")
    return payload


def _scan_for_secrets(payload: bytes) -> None:
    if any(pattern.search(payload) for pattern in SECRET_PATTERNS):
        raise PackagingError("secret_pattern_detected")


def _write_bytes(path: Path, payload: bytes, timestamp: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.utime(path, (timestamp, timestamp), follow_symlinks=False)


def _file_record(path: Path, role: str, source_path: str) -> dict[str, object]:
    return {
        "path": path.name,
        "role": role,
        "source_path": _safe_relative_path(source_path),
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _normalized_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _wheel_distribution(path: Path) -> str:
    if path.suffix != ".whl":
        raise PackagingError("dependency_wheel_name_invalid")
    distribution = path.name.split("-", 1)[0]
    if not distribution:
        raise PackagingError("dependency_wheel_name_invalid")
    return _normalized_distribution(distribution)


def _medical_wheel_member(member: PurePosixPath, header: bytes) -> bool:
    return (
        member.parts[:3] == PYDICOM_TEST_TREE
        or member.suffix.casefold() in MEDICAL_WHEEL_SUFFIXES
        or header[128:132] == b"DICM"
    )


def _validate_linux_wheel(path: Path) -> None:
    name = path.name.lower()
    if (
        not re.fullmatch(r"[a-z0-9][a-z0-9._+-]{0,199}\.whl", name)
        or "macosx" in name
        or "win32" in name
        or "win_amd64" in name
        or "arm64" in name
        or "aarch64" in name
        or "musllinux" in name
    ):
        raise PackagingError("dependency_wheel_platform_invalid")
    if "-none-any.whl" not in name and not (
        "manylinux" in name
        and ("x86_64" in name or "amd64" in name)
        and ("cp311" in name or "cp312" in name)
    ):
        raise PackagingError("dependency_wheel_platform_invalid")
    try:
        with zipfile.ZipFile(path) as archive:
            names: set[str] = set()
            for info in archive.infolist():
                member = PurePosixPath(info.filename)
                mode = info.external_attr >> 16
                if (
                    member.is_absolute()
                    or any(part in {"", ".", ".."} for part in member.parts)
                    or "\\" in info.filename
                    or info.filename in names
                    or stat.S_ISLNK(mode)
                    or info.file_size < 0
                ):
                    raise PackagingError("dependency_wheel_archive_invalid")
                names.add(info.filename)
                if info.is_dir():
                    continue
                with archive.open(info) as stream:
                    header = stream.read(132)
                if _medical_wheel_member(member, header):
                    raise PackagingError("dependency_wheel_medical_payload_detected")
    except (OSError, zipfile.BadZipFile) as error:
        raise PackagingError("dependency_wheel_archive_invalid") from error
    if _wheel_distribution(path) == "pydicom":
        _validate_pydicom_record(path)


def _normalized_run_config_record(
    run_config: Mapping[str, object], source_path: str = "generated/run-config.json"
) -> dict[str, object]:
    normalized = dict(run_config)
    normalized["bundle_sha256"] = RUN_CONFIG_BUNDLE_PLACEHOLDER
    payload = _canonical_json_bytes(normalized)
    return {
        "path": "run-config.json",
        "role": "run_config",
        "source_path": source_path,
        "bytes": len(payload),
        "sha256": _sha256_bytes(payload),
    }


def _bundle_identity(
    *,
    git_commit: str,
    git_commit_timestamp: int,
    competition_slug: str,
    kernel_sha256: str,
    records: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "bundle_format": BUNDLE_FORMAT,
        "provenance": {
            "git_commit": git_commit,
            "git_commit_timestamp": git_commit_timestamp,
        },
        "competition": {"slug": competition_slug},
        "kernel": {"code_file": "run.py", "sha256": kernel_sha256},
        "files": sorted((dict(record) for record in records), key=lambda item: str(item["path"])),
    }


def _derive_slug(prefix: str, commit: str, bundle_sha256: str) -> str:
    slug = f"{prefix}-{commit[:7]}-{bundle_sha256[:12]}"
    if not SAFE_SLUG.fullmatch(slug):
        raise PackagingError("derived_slug_invalid")
    return slug


def _load_json_object(path: Path, maximum_bytes: int) -> dict[str, Any]:
    payload = _read_bounded(path, maximum_bytes)
    _scan_for_secrets(payload)
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackagingError("json_source_invalid") from error
    if not isinstance(decoded, dict):
        raise PackagingError("json_source_invalid")
    return decoded


def _validate_contract_pair(config_path: Path, contract_path: Path) -> str:
    pointer = _load_json_object(config_path, 64 * 1024)
    contract = _load_json_object(contract_path, 2 * 1024 * 1024)
    if pointer.get("schema_version") != 1 or pointer.get("contract") != (
        "../docs/competition_contract/contract.yaml"
    ):
        raise PackagingError("competition_pointer_invalid")
    identity = contract.get("identity")
    runtime = contract.get("runtime")
    if not isinstance(identity, dict) or identity.get("slug") != COMPETITION_SLUG:
        raise PackagingError("competition_identity_invalid")
    if not isinstance(runtime, dict) or runtime.get("internet_enabled") is not False:
        raise PackagingError("competition_runtime_invalid")
    return COMPETITION_SLUG


def _validate_manifest_schema(path: Path) -> dict[str, Any]:
    schema = _load_json_object(path, 2 * 1024 * 1024)
    privacy = schema.get("privacy")
    if schema.get("schema_version") != 2 or not isinstance(privacy, dict):
        raise PackagingError("manifest_schema_invalid")
    if privacy.get("minimum_export_cell") != 20:
        raise PackagingError("manifest_privacy_invalid")
    for field in ("raw_text_persisted", "pixel_arrays_persisted", "private_tables_leave_kaggle"):
        if privacy.get(field) is not False:
            raise PackagingError("manifest_privacy_invalid")
    return schema


def _run_config(
    *,
    commit: str,
    schema: Mapping[str, Any],
    schema_sha256: str,
    competition_config_sha256: str,
    competition_contract_sha256: str,
    uv_lock_sha256: str,
    dependency_wheel_records: Sequence[Mapping[str, object]],
    runner_module: str,
    runner_callable: str,
    workers: int,
    max_files: int | None,
    progress_every: int,
) -> dict[str, object]:
    if not SAFE_IMPORT.fullmatch(runner_module) or not SAFE_IMPORT.fullmatch(runner_callable):
        raise PackagingError("runner_import_invalid")
    if workers < 1 or workers > 16:
        raise PackagingError("worker_count_invalid")
    if max_files is not None and max_files < 1:
        raise PackagingError("max_files_invalid")
    if progress_every < 100 or progress_every > 1_000_000:
        raise PackagingError("progress_interval_invalid")
    canary_seed = f"{commit}:{schema_sha256}:privacy-canary-v1".encode()
    privacy_canary = f"RSNA_PRIVATE_CANARY_{_sha256_bytes(canary_seed)[:32]}"
    dependency_identity = [
        {"path": record["path"], "bytes": record["bytes"], "sha256": record["sha256"]}
        for record in sorted(dependency_wheel_records, key=lambda item: str(item["path"]))
    ]
    return {
        "schema_version": 1,
        "audit_id": f"manifest-audit-{commit[:12]}",
        "code_commit": commit,
        "bundle_sha256": RUN_CONFIG_BUNDLE_PLACEHOLDER,
        "workers": workers,
        "max_files": max_files,
        "progress_every": progress_every,
        "qa_per_stratum": 5,
        "minimum_export_cell": 20,
        "source_context": "train-plus-example-test",
        "seed": 20260808,
        "runner": {
            "module": runner_module,
            "callable": runner_callable,
            "arguments": {
                "input_root": "competition_input",
                "output_root": "working_output",
                "manifest_schema_path": "bundle_manifest_schema",
                "competition_config_path": "bundle_competition_config",
                "competition_contract_path": "bundle_competition_contract",
                "run_config_path": "bundle_run_config",
            },
        },
        "competition": {"slug": COMPETITION_SLUG},
        "provenance": {
            "git_commit": commit,
            "manifest_schema_sha256": schema_sha256,
            "competition_config_sha256": competition_config_sha256,
            "competition_contract_sha256": competition_contract_sha256,
            "uv_lock_sha256": uv_lock_sha256,
            "manifest_version": schema.get("manifest_version"),
            "group_version": schema.get("group_version"),
            "label_version": schema.get("label_version"),
            "preprocessing_version": schema.get("preprocessing_version"),
            "decoder_packages": dict(REQUIRED_DECODER_PACKAGES),
        },
        "runtime_dependencies": {
            "target_platforms": list(TARGET_PLATFORMS),
            "python_versions": list(TARGET_PYTHONS),
            "install_mode": "pip-no-index-find-links",
            "wheel_count": len(dependency_identity),
            "wheel_set_sha256": _sha256_bytes(_canonical_json_bytes(dependency_identity)),
        },
        "privacy": {
            "canary": privacy_canary,
            "minimum_export_cell": 20,
            "raw_identifiers": False,
            "raw_reports": False,
            "patient_metadata": False,
            "pixel_data": False,
            "private_tables": False,
        },
        "runtime": {
            "internet": False,
            "accelerator": "cpu",
            "max_seconds": 21_600,
            "kill_before_seconds": 23_400,
        },
        "output_policy": {
            "private_remote_only": list(PRIVATE_OUTPUTS),
            "downloadable": list(DOWNLOADABLE_OUTPUTS),
            "session_log": SESSION_LOG_POLICY,
            "max_remote_bytes": 9 * 1024**3,
            "max_download_bytes": 4 * 1024**2,
        },
    }


def _copy_payload(
    *,
    source: Path,
    target: Path,
    maximum_bytes: int,
    timestamp: int,
    scan_secrets: bool,
) -> None:
    payload = _read_bounded(source, maximum_bytes)
    if scan_secrets:
        _scan_for_secrets(payload)
    _write_bytes(target, payload, timestamp)


def _assemble_bundle(
    *,
    output: Path,
    owner: str,
    git_commit: str,
    git_commit_timestamp: int,
    audit_key: bytes,
    wheel_path: Path,
    dependency_wheel_paths: Sequence[Path],
    runtime_requirements_path: Path,
    manifest_schema_path: Path,
    competition_config_path: Path,
    competition_contract_path: Path,
    uv_lock_path: Path,
    kernel_runner_path: Path,
    runner_module: str = DEFAULT_RUNNER_MODULE,
    runner_callable: str = DEFAULT_RUNNER_CALLABLE,
    workers: int = 4,
    max_files: int | None = None,
    progress_every: int = 10_000,
) -> dict[str, str]:
    """Assemble a deterministic bundle from already resolved immutable inputs."""

    if output.exists():
        raise PackagingError("output_exists")
    if not SAFE_SLUG.fullmatch(owner):
        raise PackagingError("owner_invalid")
    if not HEX_40.fullmatch(git_commit):
        raise PackagingError("git_commit_invalid")
    if git_commit_timestamp < 1:
        raise PackagingError("git_timestamp_invalid")
    if len(audit_key) != 32:
        raise PackagingError("audit_key_invalid")
    if wheel_path.suffix != ".whl" or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._+-]{0,199}\.whl", wheel_path.name
    ):
        raise PackagingError("wheel_name_invalid")
    _validate_linux_wheel(wheel_path)
    if not dependency_wheel_paths:
        raise PackagingError("dependency_wheelhouse_empty")
    dependency_names: set[str] = set()
    for dependency_wheel in dependency_wheel_paths:
        _validate_linux_wheel(dependency_wheel)
        if dependency_wheel.name == wheel_path.name or dependency_wheel.name in dependency_names:
            raise PackagingError("dependency_wheel_name_duplicate")
        dependency_names.add(dependency_wheel.name)
    for distribution, version in REQUIRED_DECODER_PACKAGES.items():
        matching = [
            path
            for path in dependency_wheel_paths
            if _wheel_distribution(path) == distribution and f"-{version}-" in path.name.lower()
        ]
        if not matching:
            raise PackagingError("required_decoder_wheel_missing")

    competition_slug = _validate_contract_pair(competition_config_path, competition_contract_path)
    schema = _validate_manifest_schema(manifest_schema_path)
    kernel_payload = _read_bounded(kernel_runner_path, 512 * 1024)
    _scan_for_secrets(kernel_payload)
    kernel_sha256 = _sha256_bytes(kernel_payload)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    try:
        dataset_dir = temporary_root / "dataset"
        kernel_dir = temporary_root / "kernel"
        dataset_dir.mkdir()
        kernel_dir.mkdir()

        payload_specs = (
            (wheel_path, dataset_dir / wheel_path.name, "project_wheel", "dist/project.whl", False),
            (
                manifest_schema_path,
                dataset_dir / "manifest_schema.yaml",
                "manifest_schema",
                "configs/manifest_schema.yaml",
                True,
            ),
            (
                competition_config_path,
                dataset_dir / "competition.yaml",
                "competition_pointer",
                "configs/competition.yaml",
                True,
            ),
            (
                competition_contract_path,
                dataset_dir / "competition_contract.yaml",
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
        )
        for source, target, _role, _source_path, scan_secrets in payload_specs:
            _copy_payload(
                source=source,
                target=target,
                maximum_bytes=MAX_BUNDLE_BYTES,
                timestamp=git_commit_timestamp,
                scan_secrets=scan_secrets,
            )

        records = [
            _file_record(target, role, source_path)
            for _source, target, role, source_path, _scan in payload_specs
        ]
        audit_key_path = dataset_dir / AUDIT_KEY_FILENAME
        _write_bytes(audit_key_path, audit_key, git_commit_timestamp)
        records.append(_file_record(audit_key_path, "audit_key", f"generated/{AUDIT_KEY_FILENAME}"))
        dependency_records: list[dict[str, object]] = []
        for dependency_wheel in sorted(dependency_wheel_paths, key=lambda item: item.name):
            target = dataset_dir / dependency_wheel.name
            _copy_payload(
                source=dependency_wheel,
                target=target,
                maximum_bytes=MAX_BUNDLE_BYTES,
                timestamp=git_commit_timestamp,
                scan_secrets=False,
            )
            dependency_record = _file_record(
                target,
                "dependency_wheel",
                f"wheelhouse/{dependency_wheel.name}",
            )
            dependency_records.append(dependency_record)
            records.append(dependency_record)
        record_by_role = {str(record["role"]): record for record in records}
        run_config = _run_config(
            commit=git_commit,
            schema=schema,
            schema_sha256=str(record_by_role["manifest_schema"]["sha256"]),
            competition_config_sha256=str(record_by_role["competition_pointer"]["sha256"]),
            competition_contract_sha256=str(record_by_role["competition_contract"]["sha256"]),
            uv_lock_sha256=str(record_by_role["dependency_lock"]["sha256"]),
            dependency_wheel_records=dependency_records,
            runner_module=runner_module,
            runner_callable=runner_callable,
            workers=workers,
            max_files=max_files,
            progress_every=progress_every,
        )
        normalized_run_record = _normalized_run_config_record(run_config)
        identity = _bundle_identity(
            git_commit=git_commit,
            git_commit_timestamp=git_commit_timestamp,
            competition_slug=competition_slug,
            kernel_sha256=kernel_sha256,
            records=[*records, normalized_run_record],
        )
        bundle_sha256 = _sha256_bytes(_canonical_json_bytes(identity))
        run_config["bundle_sha256"] = bundle_sha256
        run_config_path = dataset_dir / "run-config.json"
        _write_bytes(
            run_config_path,
            _canonical_json_bytes(run_config),
            git_commit_timestamp,
        )
        records.append(_file_record(run_config_path, "run_config", "generated/run-config.json"))

        bundle_manifest = {
            **identity,
            "bundle_sha256": bundle_sha256,
            "files": sorted(records, key=lambda item: str(item["path"])),
        }
        manifest_path = dataset_dir / "bundle-manifest.json"
        _write_bytes(
            manifest_path,
            _canonical_json_bytes(bundle_manifest),
            git_commit_timestamp,
        )

        total_bundle_bytes = sum(path.stat().st_size for path in dataset_dir.iterdir())
        if total_bundle_bytes > MAX_BUNDLE_BYTES:
            raise PackagingError("bundle_too_large")

        dataset_slug = _derive_slug("rsna-knee-manifest-bundle", git_commit, bundle_sha256)
        kernel_slug = _derive_slug("rsna-knee-manifest-audit", git_commit, bundle_sha256)
        dataset_ref = f"{owner}/{dataset_slug}"
        kernel_ref = f"{owner}/{kernel_slug}"
        dataset_metadata = {
            "title": dataset_slug,
            "id": dataset_ref,
            "licenses": [{"name": "other"}],
            "description": (
                "PRIVATE TEAM-ONLY offline code/configuration/Linux-wheel bundle. All rights "
                "reserved. "
                "Contains no competition data, DICOM pixels, reports, patient metadata, "
                "credentials, checkpoints, or predictions. Do not publish or share."
            ),
        }
        _write_bytes(
            dataset_dir / "dataset-metadata.json",
            _canonical_json_bytes(dataset_metadata),
            git_commit_timestamp,
        )

        if sum(path.stat().st_size for path in dataset_dir.iterdir()) > MAX_BUNDLE_BYTES:
            raise PackagingError("bundle_too_large")

        _write_bytes(kernel_dir / "run.py", kernel_payload, git_commit_timestamp)
        kernel_metadata = {
            "id": kernel_ref,
            "title": kernel_slug,
            "code_file": "run.py",
            "language": "python",
            "kernel_type": "script",
            "is_private": True,
            "enable_gpu": False,
            "enable_tpu": False,
            "enable_internet": False,
            "machine_shape": "",
            "dataset_sources": [dataset_ref],
            "competition_sources": [competition_slug],
            "kernel_sources": [],
            "model_sources": [],
        }
        _write_bytes(
            kernel_dir / "kernel-metadata.json",
            _canonical_json_bytes(kernel_metadata),
            git_commit_timestamp,
        )
        for directory in (dataset_dir, kernel_dir, temporary_root):
            os.utime(directory, (git_commit_timestamp, git_commit_timestamp))
        temporary_root.rename(output)
    except BaseException:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise

    return {
        "bundle_sha256": bundle_sha256,
        "dataset_ref": dataset_ref,
        "kernel_ref": kernel_ref,
    }


def _git_output(repo_root: Path, arguments: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise PackagingError("git_query_failed") from error
    return result.stdout.strip()


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
    required = (
        "configs/manifest_schema.yaml",
        "configs/competition.yaml",
        "docs/competition_contract/contract.yaml",
        "uv.lock",
        "kaggle/manifest_audit/run.py",
    )
    for relative in required:
        _git_output(repo_root, ["ls-files", "--error-unmatch", relative])
    return commit, timestamp


def _build_wheel(repo_root: Path, commit_timestamp: int, destination: Path) -> Path:
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONHASHSEED": "0",
            "SOURCE_DATE_EPOCH": str(commit_timestamp),
            "UV_NO_EDITABLE": "1",
        }
    )
    try:
        subprocess.run(
            ["uv", "build", "--offline", "--wheel", "--out-dir", str(destination)],
            cwd=repo_root,
            env=environment,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=300,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise PackagingError("offline_wheel_build_failed") from error
    wheels = sorted(destination.glob("*.whl"))
    if len(wheels) != 1:
        raise PackagingError("wheel_count_invalid")
    return wheels[0]


def _requirement_blocks(payload: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    current: list[str] = []
    for raw_line in payload.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        current.append(line)
        if line.endswith("\\"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==[^\s\\]+(?:\s+\\)?", current[0])
        if match is None:
            raise PackagingError("runtime_requirements_invalid")
        name = _normalized_distribution(match.group(1))
        if name in blocks:
            raise PackagingError("runtime_requirements_duplicate")
        blocks[name] = "\n".join(current) + "\n"
        current = []
    if current or not blocks:
        raise PackagingError("runtime_requirements_invalid")
    return blocks


def _run_sanitized(command: Sequence[str], *, cwd: Path, environment: Mapping[str, str]) -> None:
    try:
        subprocess.run(
            list(command),
            cwd=cwd,
            env=dict(environment),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=600,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise PackagingError("dependency_wheelhouse_build_failed") from error


def _wheel_record(payload: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode()
    return f"sha256={digest},{len(payload)}"


def _validate_pydicom_record(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            payloads = {
                info.filename: archive.read(info)
                for info in archive.infolist()
                if not info.is_dir()
            }
        records = [name for name in payloads if name.endswith(".dist-info/RECORD")]
        if len(records) != 1 or any(
            name.endswith((".dist-info/RECORD.jws", ".dist-info/RECORD.p7s")) for name in payloads
        ):
            raise PackagingError("dependency_wheel_record_invalid")
        record_name = records[0]
        rows = list(csv.reader(payloads[record_name].decode("utf-8").splitlines()))
        if len(rows) != len(payloads) or any(len(row) != 3 for row in rows):
            raise PackagingError("dependency_wheel_record_invalid")
        observed = {row[0]: (row[1], row[2]) for row in rows}
        if len(observed) != len(rows) or set(observed) != set(payloads):
            raise PackagingError("dependency_wheel_record_invalid")
        for name, payload in payloads.items():
            expected_hash, expected_size = (
                ("", "") if name == record_name else _wheel_record(payload).split(",", 1)
            )
            if observed[name] != (expected_hash, expected_size):
                raise PackagingError("dependency_wheel_record_invalid")
        if (
            "pydicom/__init__.py" not in payloads
            or not any(name.endswith(".dist-info/METADATA") for name in payloads)
            or not any(name.endswith(".dist-info/WHEEL") for name in payloads)
            or not any(".dist-info/licenses/" in name.casefold() for name in payloads)
        ):
            raise PackagingError("dependency_wheel_record_invalid")
    except (OSError, UnicodeDecodeError, csv.Error, zipfile.BadZipFile) as error:
        raise PackagingError("dependency_wheel_record_invalid") from error


def _strip_pydicom_medical_payloads(path: Path, timestamp: int) -> None:
    if _wheel_distribution(path) != "pydicom":
        return
    files: dict[str, bytes] = {}
    record_name: str | None = None
    removed = False
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > 10_000 or sum(info.file_size for info in infos) > MAX_BUNDLE_BYTES:
                raise PackagingError("pydicom_wheel_sanitization_failed")
            names: set[str] = set()
            for info in infos:
                member = PurePosixPath(info.filename)
                mode = info.external_attr >> 16
                if (
                    member.is_absolute()
                    or any(part in {"", ".", ".."} for part in member.parts)
                    or "\\" in info.filename
                    or info.filename in names
                    or stat.S_ISLNK(mode)
                    or info.file_size < 0
                ):
                    raise PackagingError("pydicom_wheel_sanitization_failed")
                names.add(info.filename)
                if info.is_dir():
                    continue
                payload = archive.read(info)
                if len(payload) != info.file_size:
                    raise PackagingError("pydicom_wheel_sanitization_failed")
                if _medical_wheel_member(member, payload[:132]):
                    removed = True
                    continue
                name = _safe_relative_path(info.filename)
                if name.endswith(".dist-info/RECORD"):
                    if record_name is not None:
                        raise PackagingError("pydicom_wheel_sanitization_failed")
                    record_name = name
                    continue
                if name.endswith((".dist-info/RECORD.jws", ".dist-info/RECORD.p7s")):
                    raise PackagingError("pydicom_wheel_sanitization_failed")
                files[name] = payload
    except (OSError, zipfile.BadZipFile) as error:
        raise PackagingError("pydicom_wheel_sanitization_failed") from error
    if not removed:
        return
    if (
        record_name is None
        or "pydicom/__init__.py" not in files
        or not any(name.endswith(".dist-info/METADATA") for name in files)
        or not any(name.endswith(".dist-info/WHEEL") for name in files)
        or not any(".dist-info/licenses/" in name.casefold() for name in files)
    ):
        raise PackagingError("pydicom_wheel_sanitization_failed")
    record_lines = [f"{name},{_wheel_record(payload)}" for name, payload in sorted(files.items())]
    record_lines.append(f"{record_name},,")
    files[record_name] = ("\n".join(record_lines) + "\n").encode()
    temporary = path.with_name(f".{path.name}.sanitized")
    date_time = time.gmtime(max(timestamp, 315532800))[:6]
    try:
        with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, payload)
        os.replace(temporary, path)
        os.utime(path, (timestamp, timestamp), follow_symlinks=False)
    except (OSError, zipfile.BadZipFile) as error:
        temporary.unlink(missing_ok=True)
        raise PackagingError("pydicom_wheel_sanitization_failed") from error


def _build_langdetect_wheel(source: Path, destination: Path, timestamp: int) -> Path:
    """Build the locked pure-Python dependency without an unpinned build backend."""

    files: dict[str, bytes] = {}
    try:
        with tarfile.open(source, "r:*") as archive:
            for member in archive.getmembers():
                parts = PurePosixPath(member.name).parts
                if parts == ("langdetect-1.0.9",) and member.isdir():
                    continue
                if (
                    len(parts) < 2
                    or parts[0] != "langdetect-1.0.9"
                    or any(part in {"", ".", ".."} for part in parts)
                ):
                    raise PackagingError("langdetect_source_invalid")
                relative = PurePosixPath(*parts[1:]).as_posix()
                if member.issym() or member.islnk():
                    raise PackagingError("langdetect_source_invalid")
                if not member.isfile():
                    continue
                if relative.startswith("langdetect/") or relative in {"LICENSE", "NOTICE"}:
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        raise PackagingError("langdetect_source_invalid")
                    payload = extracted.read(4 * 1024 * 1024 + 1)
                    if len(payload) != member.size or len(payload) > 4 * 1024 * 1024:
                        raise PackagingError("langdetect_source_invalid")
                    target = relative
                    if relative in {"LICENSE", "NOTICE"}:
                        target = f"langdetect-1.0.9.dist-info/licenses/{relative}"
                    files[target] = payload
    except (OSError, tarfile.TarError) as error:
        raise PackagingError("langdetect_source_invalid") from error
    if not {"langdetect/__init__.py", "langdetect/profiles/en"} <= set(files):
        raise PackagingError("langdetect_source_invalid")
    metadata = (
        b"Metadata-Version: 2.1\n"
        b"Name: langdetect\n"
        b"Version: 1.0.9\n"
        b"Summary: Language detection library ported from Google's language-detection.\n"
        b"License: MIT\n"
        b"Requires-Dist: six\n\n"
    )
    wheel_metadata = (
        b"Wheel-Version: 1.0\n"
        b"Generator: rsna-knee-stdlib-wheel-v1\n"
        b"Root-Is-Purelib: true\n"
        b"Tag: py3-none-any\n"
    )
    files["langdetect-1.0.9.dist-info/METADATA"] = metadata
    files["langdetect-1.0.9.dist-info/WHEEL"] = wheel_metadata
    files["langdetect-1.0.9.dist-info/top_level.txt"] = b"langdetect\n"
    record_name = "langdetect-1.0.9.dist-info/RECORD"
    record_lines = [f"{name},{_wheel_record(payload)}" for name, payload in sorted(files.items())]
    record_lines.append(f"{record_name},,")
    files[record_name] = ("\n".join(record_lines) + "\n").encode()

    wheel_path = destination / "langdetect-1.0.9-py3-none-any.whl"
    date_time = time.gmtime(max(timestamp, 315532800))[:6]
    try:
        with zipfile.ZipFile(wheel_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, payload)
    except (OSError, zipfile.BadZipFile) as error:
        raise PackagingError("langdetect_wheel_build_failed") from error
    os.utime(wheel_path, (timestamp, timestamp), follow_symlinks=False)
    return wheel_path


def _prepare_runtime_wheels(
    repo_root: Path,
    commit_timestamp: int,
    destination: Path,
) -> tuple[tuple[Path, ...], Path]:
    try:
        exported = subprocess.run(
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
            ],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        ).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise PackagingError("dependency_export_failed") from error
    blocks = _requirement_blocks(exported)
    if "langdetect" not in blocks:
        raise PackagingError("runtime_requirements_invalid")
    for distribution, version in REQUIRED_DECODER_PACKAGES.items():
        block = blocks.get(distribution)
        if block is None or not block.startswith(f"{distribution}=={version}"):
            raise PackagingError("required_decoder_requirement_invalid")

    destination.mkdir()
    requirements_path = destination.parent / "runtime-requirements.txt"
    _write_bytes(requirements_path, exported.encode(), commit_timestamp)
    binary_requirements = destination.parent / "binary-requirements.txt"
    source_requirements = destination.parent / "source-requirements.txt"
    _write_bytes(
        binary_requirements,
        "".join(block for name, block in blocks.items() if name != "langdetect").encode(),
        commit_timestamp,
    )
    _write_bytes(source_requirements, blocks["langdetect"].encode(), commit_timestamp)

    environment = os.environ.copy()
    environment.update(
        {
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
            "PIP_KEYRING_PROVIDER": "disabled",
            "PYTHONHASHSEED": "0",
            "SOURCE_DATE_EPOCH": str(commit_timestamp),
        }
    )
    pip = [sys.executable, "-m", "pip"]
    common_index = ["--isolated", "--index-url", "https://pypi.org/simple"]
    platform_arguments = [
        argument for platform in TARGET_PLATFORMS for argument in ("--platform", platform)
    ]
    for python_version in TARGET_PYTHONS:
        abi = f"cp{python_version.replace('.', '')}"
        _run_sanitized(
            [
                *pip,
                "download",
                *common_index,
                "--require-hashes",
                "--no-deps",
                "--only-binary=:all:",
                *platform_arguments,
                "--python-version",
                python_version,
                "--implementation",
                "cp",
                "--abi",
                abi,
                "--dest",
                str(destination),
                "--requirement",
                str(binary_requirements),
            ],
            cwd=repo_root,
            environment=environment,
        )
    source_dir = destination.parent / "source"
    source_dir.mkdir()
    _run_sanitized(
        [
            *pip,
            "download",
            *common_index,
            "--require-hashes",
            "--no-deps",
            "--no-binary=:all:",
            "--dest",
            str(source_dir),
            "--requirement",
            str(source_requirements),
        ],
        cwd=repo_root,
        environment=environment,
    )
    source_archives = sorted(source_dir.iterdir())
    if len(source_archives) != 1 or not source_archives[0].is_file():
        raise PackagingError("source_distribution_count_invalid")
    _build_langdetect_wheel(source_archives[0], destination, commit_timestamp)
    wheels = tuple(sorted(destination.glob("*.whl")))
    found_distributions = {_wheel_distribution(path) for path in wheels}
    if found_distributions != set(blocks):
        raise PackagingError("dependency_wheelhouse_incomplete")
    for distribution in found_distributions:
        distribution_wheels = [path for path in wheels if _wheel_distribution(path) == distribution]
        lowered = [path.name.lower() for path in distribution_wheels]
        if not any("-none-any.whl" in name for name in lowered) and not (
            any("cp311" in name for name in lowered) and any("cp312" in name for name in lowered)
        ):
            raise PackagingError("dependency_python_coverage_invalid")
    for wheel in wheels:
        _strip_pydicom_medical_payloads(wheel, commit_timestamp)
        _validate_linux_wheel(wheel)
        os.utime(wheel, (commit_timestamp, commit_timestamp), follow_symlinks=False)
    return wheels, requirements_path


def package_from_clean_repo(args: argparse.Namespace) -> dict[str, str]:
    repo_root = args.repo_root.resolve()
    output = args.output.resolve()
    audit_key_path = args.audit_key_path.resolve()
    audit_key = _read_bounded(audit_key_path, 32)
    try:
        if len(audit_key) != 32 or audit_key_path.stat().st_mode & 0o077:
            raise PackagingError("audit_key_invalid")
    except OSError as error:
        raise PackagingError("audit_key_invalid") from error
    try:
        relative_key = audit_key_path.relative_to(repo_root)
    except ValueError:
        relative_key = None
    if relative_key is not None:
        ignored = subprocess.run(
            ["git", "-C", str(repo_root), "check-ignore", "--quiet", "--", str(relative_key)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
        )
        if ignored.returncode != 0:
            raise PackagingError("audit_key_not_ignored")
    commit, timestamp = _clean_git_provenance(repo_root)
    with tempfile.TemporaryDirectory(prefix="rsna-knee-wheel-") as build_directory:
        build_root = Path(build_directory)
        project_wheel_dir = build_root / "project"
        project_wheel_dir.mkdir()
        wheel = _build_wheel(repo_root, timestamp, project_wheel_dir)
        dependency_wheels, runtime_requirements = _prepare_runtime_wheels(
            repo_root,
            timestamp,
            build_root / "wheelhouse",
        )
        return _assemble_bundle(
            output=output,
            owner=args.owner,
            git_commit=commit,
            git_commit_timestamp=timestamp,
            audit_key=audit_key,
            wheel_path=wheel,
            dependency_wheel_paths=dependency_wheels,
            runtime_requirements_path=runtime_requirements,
            manifest_schema_path=repo_root / "configs/manifest_schema.yaml",
            competition_config_path=repo_root / "configs/competition.yaml",
            competition_contract_path=repo_root / "docs/competition_contract/contract.yaml",
            uv_lock_path=repo_root / "uv.lock",
            kernel_runner_path=repo_root / "kaggle/manifest_audit/run.py",
            runner_module=args.runner_module,
            runner_callable=args.runner_callable,
            workers=args.workers,
            max_files=args.max_files,
            progress_every=args.progress_every,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--audit-key-path", type=Path, required=True)
    parser.add_argument("--runner-module", default=DEFAULT_RUNNER_MODULE)
    parser.add_argument("--runner-callable", default=DEFAULT_RUNNER_CALLABLE)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--progress-every", type=int, default=10_000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = package_from_clean_repo(args)
    except PackagingError as error:
        print(f"manifest_bundle=FAIL code={error.code}")
        return 2
    except Exception:
        print("manifest_bundle=FAIL code=internal_error")
        return 2
    print(f"manifest_bundle=PASS bundle_sha256={result['bundle_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
