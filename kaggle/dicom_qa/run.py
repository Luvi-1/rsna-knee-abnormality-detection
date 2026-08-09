"""Verified offline Kaggle entry point for private Chunk 5 DICOM QA.

Only fixed events and sanitized aggregate files may leave the protected execution body.  The
ordinal-only review images and case index remain visible solely in the private Kaggle output.
"""

from __future__ import annotations

import contextlib
import csv
import ctypes
import hashlib
import hmac
import io
import json
import math
import os
import re
import resource
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from heapq import nsmallest
from itertools import islice
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, Final, cast

BUNDLE_FORMAT: Final = "rsna-knee-dicom-qa-bundle-v1"
BUNDLE_PLACEHOLDER: Final = "0" * 64
COMPETITION_SLUG: Final = "rsna-knee-abnormality-detection"
OUTPUT_DIRECTORY: Final = "dicom-qa-output"
PRIVATE_REVIEW_DIRECTORY: Final = "private-review"
MAX_BUNDLE_BYTES: Final = 128 * 1024 * 1024
MAX_POLICY_BYTES: Final = 2 * 1024 * 1024
MAX_MOUNT_SEARCH_DEPTH: Final = 4
MAX_MOUNT_DIRECTORY_ENTRIES: Final = 128
MAX_SERIES_ROWS: Final = 50_000
MAX_STUDIES: Final = 10_000
MAX_FILES_PER_SERIES: Final = 1_024
EXPECTED_SERIES_HEADER: Final = (
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "Fluid_Sensitive",
    "Fat_Suppression",
    "Anatomical_Plane",
)
EXPECTED_SINGLETON_ROLES: Final = {
    "project_wheel",
    "preprocessing_config",
    "preprocessing_schema",
    "source_manifest_schema",
    "competition_pointer",
    "competition_contract",
    "dependency_lock",
    "runtime_requirements",
    "run_config",
    "comparison_source",
    "review_finalizer",
    "review_ui_source",
    "review_notebook",
    "output_validator",
    "runner_source",
    "synthetic_preflight",
}
DEPENDENCY_ROLE: Final = "dependency_wheel"
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
REQUIRED_RUNTIME_PACKAGES: Final = {
    "pillow": "12.3.0",
    "pylibjpeg": "2.1.0",
    "pylibjpeg-libjpeg": "2.4.0",
    "pylibjpeg-openjpeg": "2.5.0",
}
PRIVATE_OUTPUT_POLICY: Final = {
    "private_case_index.json": 32 * 1024**2,
    "private_artifact_inventory.json": 32 * 1024**2,
    "private_full_run_manifest.jsonl": 512 * 1024**2,
    "private_full_run_metrics.json": 2 * 1024**2,
}
PRIVATE_REVIEW_PATTERN: Final = (
    r"case_[0-9]{6}_series_[0-9]{3}_"
    r"(?:contact|orthogonal|histogram|animation|before_after|review|metadata)"
    r"\.(?:png|gif|json)"
)
PRIVATE_REVIEW_MAX_FILE_BYTES: Final = 32 * 1024**2
PRIVATE_REVIEW_MAX_FILES: Final = 20_000
PRIVATE_REVIEW_MAX_TOTAL_BYTES: Final = 8 * 1024**3
DOWNLOADABLE_OUTPUT_POLICY: Final = {
    "sanitized_summary.json": ("aggregate_json", 256 * 1024),
    "benchmark.md": ("aggregate_documentation", 128 * 1024),
    "sanitized_artifact_inventory.json": ("aggregate_json", 128 * 1024),
}
SESSION_LOG_PATTERN: Final = r"[a-z0-9][a-z0-9_-]{0,99}\.log"
SELF_DEADLINE_SECONDS: Final = 21_600
OUTER_KILL_SECONDS: Final = 23_400
TARGET_STUDIES: Final = 120
MAX_TARGET_STUDIES: Final = 240
MINIMUM_ELIGIBLE_STUDIES: Final = 100
MATERIAL_STRATUM_MIN_STUDIES: Final = 2
MATERIAL_STRATUM_SAMPLE_QUOTA: Final = 2
SELECTION_SEED: Final = 20260809
SOURCE_MANIFEST_VERSION: Final = "manifest-v2"
SOURCE_MANIFEST_AUDIT_ID: Final = "audit-0002-manifest-remediation"
QA_COHORT_SELECTION_VERSION: Final = "qa-cohort-selection-v2"
REVIEW_PROTOCOL_VERSION: Final = "private-dicom-qa-human-review-v1"
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
SOURCE_MANIFEST_TABLES: Final = frozenset(
    {
        "manifest_run",
        "study_manifest",
        "series_manifest",
        "slice_file_manifest",
        "report_manifest",
        "label_source_manifest",
        "duplicate_edge",
        "duplicate_group_mapping",
        "protected_component",
        "candidate_component",
        "duplicate_component_summary",
        "duplicate_component_edge",
        "manifest_issue",
        "shift_result",
        "qa_sample",
    }
)
SOURCE_MANIFEST_REQUIRED_COLUMNS: Final = {
    "manifest_run": ("key", "value"),
    "study_manifest": (
        "study_key",
        "split",
        "domain_cluster_key",
        "scanner_manufacturer",
        "scanner_model",
        "field_strength_t",
        "data_quality_flags",
        "terminal_state",
    ),
    "series_manifest": (
        "series_key",
        "study_key",
        "source_row_count",
        "plane",
        "fluid_sensitive",
        "fat_suppression",
    ),
    "slice_file_manifest": (
        "file_key",
        "study_key",
        "series_key",
        "file_size_bytes",
        "raw_file_exact_key",
    ),
    "protected_component": ("component_kind", "component_key", "study_key", "evidence_state"),
    "candidate_component": (
        "component_key",
        "study_key",
        "hard_component_key",
        "evidence_state",
    ),
    "manifest_issue": (
        "entity_level",
        "entity_key",
        "issue_code",
        "resolution_status",
    ),
    "qa_sample": (
        "stratum_kind",
        "stratum_key",
        "study_key",
        "selection_reason",
        "priority",
    ),
}
SOURCE_MANIFEST_PRIVATE_ARTIFACTS: Final = {
    "private_manifest.sqlite3": (8 * 1024**3, None),
    "private_duplicate_groups.csv": (256 * 1024**2, None),
    "private_preliminary_group_keys.csv": (256 * 1024**2, None),
    "private_qa_samples.csv": (64 * 1024**2, None),
    "audit_key.bin": (64, 32),
}
SOURCE_MANIFEST_DIMENSIONS: Final = frozenset(
    {
        "scanner_manufacturer",
        "scanner_model",
        "field_strength",
        "site_domain_cluster",
        "protected_duplicate_group",
        "candidate_duplicate_group",
        "remediated_decode_case",
    }
)
REQUIRED_REVIEW_DIMENSIONS: Final = (
    "plane",
    "sequence",
    "fat_suppression",
    "scanner_manufacturer",
    "scanner_model",
    "field_strength",
    "site_domain_cluster",
    "resolution",
    "slice_count",
    "slice_spacing",
    "orientation",
    "multiple_series_per_slot",
    "missing_slot",
    "quality",
    "duplicate_integrity",
    "protected_duplicate_group",
    "candidate_duplicate_group",
    "dicom_edge_case",
    "remediated_decode_case",
)
REVIEW_DIMENSION_EXPECTED_VALUES: Final = {
    "plane": ("sagittal", "coronal", "axial"),
    "sequence": ("fluid_sensitive", "structural"),
    "fat_suppression": ("present", "absent"),
    "multiple_series_per_slot": ("present",),
    "missing_slot": ("present", "absent"),
    "quality": ("high", "low", "blocked"),
    "duplicate_integrity": ("present",),
    "dicom_edge_case": ("present",),
    "protected_duplicate_group": ("present",),
    "candidate_duplicate_group": ("present",),
    "remediated_decode_case": ("present",),
}
FATAL_DECODE_ISSUE_CODES: Final = frozenset(
    {
        "decoder_unavailable",
        "transfer_syntax_unsupported",
        "pixel_decode",
        "pydicom_warning",
    }
)
TARGET_PLATFORMS: Final = (
    "manylinux_2_27_x86_64",
    "manylinux_2_28_x86_64",
    "manylinux2014_x86_64",
)
TARGET_PYTHONS: Final = ("3.11", "3.12")
REPRESENTATIVE_WORKER_COUNTS: Final = (1, 2, 4, 8)
THROUGHPUT_BUCKETS: Final = (
    ("below_one_per_second", 0.0, 1.0),
    ("one_to_below_ten_per_second", 1.0, 10.0),
    ("ten_to_below_one_hundred_per_second", 10.0, 100.0),
    ("one_hundred_to_below_one_thousand_per_second", 100.0, 1_000.0),
    ("one_thousand_or_more_per_second", 1_000.0, math.inf),
)
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,199}\Z")
SAFE_SOURCE_PART = re.compile(r"[A-Za-z0-9._-]{1,100}\Z")
SAFE_EVENT_VALUE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
UID = re.compile(r"[0-9]+(?:\.[0-9]+)+\Z")
SENSITIVE_DOWNLOAD_BYTES: Final = (
    re.compile(
        rb"StudyInstanceUID|SeriesInstanceUID|SOPInstanceUID|Patient(?:Name|ID)|"
        rb"AccessionNumber|(?:raw[_ -]?report|report[_ -]?text)",
        re.IGNORECASE,
    ),
    re.compile(rb"(?<![0-9])(?:[0-9]{1,12}\.){3,}[0-9]{1,12}(?![0-9])"),
    re.compile(rb"(?:^|[\"'\s])/kaggle/input/", re.MULTILINE),
    re.compile(rb"\.dcm\b", re.IGNORECASE),
    re.compile(rb"https?://|(?:www\.)?kaggle\.com/", re.IGNORECASE),
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"KAGGLE_API_TOKEN\s*[:=]|gh[pousr]_[A-Za-z0-9]{20,}", re.IGNORECASE),
)


class SafeRunError(RuntimeError):
    """One fixed failure code; source values and exception text are never retained."""

    def __init__(self, code: str) -> None:
        self.code = code if SAFE_EVENT_VALUE.fullmatch(code) else "internal_error"
        super().__init__(self.code)


class _SeriesFileDiscoveryError(SafeRunError):
    """A fixed source failure retaining only bounded regular-file paths in process."""

    def __init__(self, code: str, files: tuple[Path, ...]) -> None:
        super().__init__(code)
        self.files = files


class _DeadlineExceeded(BaseException):
    """Deadline sentinel that broad library ``except Exception`` blocks cannot swallow."""


class _Discard(io.TextIOBase):
    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        return len(text)


@dataclass(frozen=True, slots=True)
class SeriesRow:
    study_uid: str
    series_uid: str
    fluid_sensitive: str
    fat_suppression: str
    plane: str


@dataclass(frozen=True, slots=True)
class SelectedStudy:
    study_uid: str
    stratum: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StratumCensus:
    stratum: tuple[str, ...]
    population_studies: int
    selected_studies: int
    material: bool


@dataclass(frozen=True, slots=True)
class DimensionCoverage:
    dimension: str
    value: str
    population_studies: int
    selected_studies: int
    disposition: str
    source: str


@dataclass(frozen=True, slots=True)
class CohortStudy:
    study_uid: str
    stratum: tuple[str, ...]
    dimensions: tuple[tuple[str, tuple[str, ...]], ...]
    eligible_series_uids: tuple[str, ...]

    @property
    def eligible_series(self) -> int:
        return len(self.eligible_series_uids)


@dataclass(frozen=True, slots=True)
class SelectionPlan:
    studies: tuple[SelectedStudy, ...]
    census: tuple[StratumCensus, ...]
    coverage: tuple[DimensionCoverage, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceManifestBinding:
    database_path: Path
    audit_key_path: Path
    database_sha256: str
    audit_key_sha256: str
    schema_sha256: str
    source_manifest_artifact_sha256: str


@dataclass(frozen=True, slots=True)
class SourceManifestReconciliation:
    """Authenticated private snapshot state used only during the full input pass."""

    connection: sqlite3.Connection = field(repr=False)
    secret: bytes = field(repr=False)
    expected_series_count: int
    expected_file_count: int


@dataclass(frozen=True, slots=True)
class RepresentativeSeriesInput:
    profile: str
    slice_count: int
    paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class SeriesPass:
    decoded: tuple[Any, ...]
    decode_failures: tuple[dict[str, str | None], ...]
    file_decode_records: tuple[dict[str, object], ...]
    file_raw_checksums: tuple[str | None, ...]
    ordered: Any | None
    order_failure: dict[str, str | None] | None
    decode_seconds: float
    ordering_seconds: float


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_bounded(
    path: Path,
    maximum: int,
    code: str,
    *,
    allow_symlink: bool = False,
) -> bytes:
    try:
        if (path.is_symlink() and not allow_symlink) or not path.is_file():
            raise SafeRunError(code)
        size = path.stat().st_size
        if size <= 0 or size > maximum:
            raise SafeRunError(code)
        with path.open("rb") as stream:
            payload = stream.read(maximum + 1)
    except SafeRunError:
        raise
    except OSError as error:
        raise SafeRunError(code) from error
    if len(payload) != size:
        raise SafeRunError(code)
    return payload


def _json_object(payload: bytes, code: str) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    try:
        value = json.loads(payload, object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise SafeRunError(code) from error
    if not isinstance(value, dict):
        raise SafeRunError(code)
    return value


def _competition_cpu_limit_seconds(path: Path) -> int:
    contract = _json_object(
        _read_bounded(path, MAX_POLICY_BYTES, "competition_contract_invalid", allow_symlink=True),
        "competition_contract_invalid",
    )
    runtime = contract.get("runtime")
    limit = runtime.get("cpu_limit_seconds") if isinstance(runtime, dict) else None
    if (
        contract.get("schema_version") != 1
        or isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 86_400
    ):
        raise SafeRunError("competition_contract_invalid")
    return limit


def _safe_event(event: str, *, phase: str | None = None, code: str | None = None) -> None:
    payload = {"event": event}
    if phase is not None:
        payload["phase"] = phase
    if code is not None:
        payload["code"] = code
    if any(not SAFE_EVENT_VALUE.fullmatch(value) for value in payload.values()):
        payload = {"event": "dicom_qa_failed", "phase": "output", "code": "internal_error"}
    print(_canonical_json_bytes(payload).decode("ascii").rstrip(), flush=True)


def _flush_native_stdio() -> None:
    try:
        library = ctypes.CDLL(None)
        flush = library.fflush
        flush.argtypes = [ctypes.c_void_p]
        flush.restype = ctypes.c_int
        flush(None)
    except Exception:
        pass


@contextlib.contextmanager
def _silence_process_output() -> Iterator[None]:
    """Suppress Python and native writes to stdout/stderr at the descriptor boundary."""

    _flush_native_stdio()
    saved = (os.dup(1), os.dup(2))
    null = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(null, 1)
        os.dup2(null, 2)
        with contextlib.redirect_stdout(_Discard()), contextlib.redirect_stderr(_Discard()):
            yield
    finally:
        _flush_native_stdio()
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        os.close(saved[0])
        os.close(saved[1])
        os.close(null)


@contextlib.contextmanager
def _enforce_self_deadline(seconds: float) -> Iterator[None]:
    if seconds <= 0:
        raise _DeadlineExceeded
    if not hasattr(signal, "setitimer") or not hasattr(signal, "SIGALRM"):
        yield
        return

    def timeout_handler(_signum: int, _frame: object) -> None:
        raise _DeadlineExceeded

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, timeout_handler)
    try:
        previous_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    except BaseException:
        signal.signal(signal.SIGALRM, previous_handler)
        raise
    try:
        yield
    finally:
        # Disarm our timer while our handler is still installed.  Only then restore the
        # previous handler and timer, so no pending alarm can reach an unrelated handler.
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer != (0.0, 0.0):
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)


def _safe_manifest_path(value: object) -> str:
    if not isinstance(value, str) or not SAFE_NAME.fullmatch(value):
        raise SafeRunError("bundle_manifest_invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or len(path.parts) != 1:
        raise SafeRunError("bundle_manifest_invalid")
    return value


def _safe_source_path(value: object) -> str:
    if not isinstance(value, str):
        raise SafeRunError("bundle_manifest_invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise SafeRunError("bundle_manifest_invalid")
    if any(not SAFE_SOURCE_PART.fullmatch(part) for part in path.parts):
        raise SafeRunError("bundle_manifest_invalid")
    return path.as_posix()


def _bounded_mount_directories(input_root: Path) -> tuple[Path, ...]:
    discovered: list[Path] = []
    seen: set[Path] = set()
    frontier = [input_root]
    for depth in range(MAX_MOUNT_SEARCH_DEPTH + 1):
        next_frontier: list[Path] = []
        for directory in frontier:
            try:
                resolved = directory.resolve(strict=True)
            except OSError as error:
                raise SafeRunError("input_root_unreadable") from error
            if resolved in seen:
                continue
            seen.add(resolved)
            discovered.append(directory)
            if depth == MAX_MOUNT_SEARCH_DEPTH:
                continue
            try:
                entries = list(islice(directory.iterdir(), MAX_MOUNT_DIRECTORY_ENTRIES + 1))
            except OSError as error:
                raise SafeRunError("input_root_unreadable") from error
            if len(entries) <= MAX_MOUNT_DIRECTORY_ENTRIES:
                next_frontier.extend(
                    entry for entry in sorted(entries, key=lambda path: path.name) if entry.is_dir()
                )
        frontier = next_frontier
    return tuple(discovered)


def _find_bundle(input_root: Path) -> tuple[Path, dict[str, Any]]:
    candidates: dict[Path, Path] = {}
    for directory in _bounded_mount_directories(input_root):
        candidate = directory / "bundle-manifest.json"
        if not candidate.is_file():
            continue
        try:
            candidates.setdefault(candidate.resolve(strict=True), candidate)
        except OSError as error:
            raise SafeRunError("bundle_unreadable") from error
    if len(candidates) != 1:
        raise SafeRunError("bundle_missing" if not candidates else "bundle_ambiguous")
    manifest_path = next(iter(candidates.values()))
    manifest = _json_object(
        _read_bounded(
            manifest_path, MAX_POLICY_BYTES, "bundle_manifest_invalid", allow_symlink=True
        ),
        "bundle_manifest_invalid",
    )
    return manifest_path.parent, manifest


def _find_competition_root(input_root: Path) -> Path:
    required_files = (
        "train.csv",
        "test.csv",
        "train_series.csv",
        "test_series.csv",
        "sample_submission.csv",
    )
    required_directories = ("train_series", "test_series")
    candidates: dict[Path, Path] = {}
    for directory in _bounded_mount_directories(input_root):
        if all((directory / name).is_file() for name in required_files) and all(
            (directory / name).is_dir() for name in required_directories
        ):
            try:
                candidates.setdefault(directory.resolve(strict=True), directory)
            except OSError as error:
                raise SafeRunError("competition_input_missing") from error
    if len(candidates) != 1:
        raise SafeRunError("competition_input_missing")
    return next(iter(candidates.values()))


def _validated_records(
    bundle_root: Path, manifest: Mapping[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    records = manifest.get("files")
    if not isinstance(records, list) or not (
        len(EXPECTED_SINGLETON_ROLES) + 1 <= len(records) <= 96
    ):
        raise SafeRunError("bundle_manifest_invalid")
    by_role: dict[str, list[dict[str, Any]]] = {}
    names: set[str] = set()
    total = 0
    for raw in records:
        if not isinstance(raw, dict):
            raise SafeRunError("bundle_manifest_invalid")
        name = _safe_manifest_path(raw.get("path"))
        role = raw.get("role")
        digest = raw.get("sha256")
        size = raw.get("bytes")
        _safe_source_path(raw.get("source_path"))
        if (
            not isinstance(role, str)
            or role not in EXPECTED_SINGLETON_ROLES | {DEPENDENCY_ROLE}
            or name in names
            or not isinstance(digest, str)
            or not HEX_64.fullmatch(digest)
            or isinstance(size, bool)
            or not isinstance(size, int)
            or not 0 < size <= MAX_BUNDLE_BYTES
        ):
            raise SafeRunError("bundle_manifest_invalid")
        candidate = bundle_root / name
        try:
            if not candidate.is_file() or candidate.stat().st_size != size:
                raise SafeRunError("bundle_file_invalid")
        except OSError as error:
            raise SafeRunError("bundle_file_invalid") from error
        if _sha256_file(candidate) != digest:
            raise SafeRunError("bundle_hash_mismatch")
        by_role.setdefault(role, []).append(raw)
        names.add(name)
        total += size
    if (
        set(by_role) != EXPECTED_SINGLETON_ROLES | {DEPENDENCY_ROLE}
        or any(len(by_role[role]) != 1 for role in EXPECTED_SINGLETON_ROLES)
        or not by_role[DEPENDENCY_ROLE]
        or total > MAX_BUNDLE_BYTES
    ):
        raise SafeRunError("bundle_manifest_invalid")
    try:
        entries = tuple(bundle_root.iterdir())
    except OSError as error:
        raise SafeRunError("bundle_root_allowlist_invalid") from error
    if any(not entry.is_file() for entry in entries):
        raise SafeRunError("bundle_root_allowlist_invalid")
    observed = {entry.name for entry in entries}
    expected = names | {"bundle-manifest.json"}
    extras = observed - expected
    if not expected.issubset(observed) or extras not in (set(), {"dataset-metadata.json"}):
        raise SafeRunError("bundle_root_allowlist_invalid")
    return by_role


def _identity_payload(
    manifest: Mapping[str, Any],
    records: Mapping[str, Sequence[Mapping[str, Any]]],
    run_config: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_config = dict(run_config)
    normalized_config["bundle_sha256"] = BUNDLE_PLACEHOLDER
    payload = _canonical_json_bytes(normalized_config)
    normalized_record = dict(records["run_config"][0])
    normalized_record["bytes"] = len(payload)
    normalized_record["sha256"] = _sha256_bytes(payload)
    identity_records: list[dict[str, Any]] = []
    for role, role_records in records.items():
        identity_records.extend(
            [normalized_record] if role == "run_config" else map(dict, role_records)
        )
    return {
        "schema_version": manifest.get("schema_version"),
        "bundle_format": manifest.get("bundle_format"),
        "provenance": manifest.get("provenance"),
        "deployment": manifest.get("deployment"),
        "competition": manifest.get("competition"),
        "kernel": manifest.get("kernel"),
        "comparison": manifest.get("comparison"),
        "review_finalizer": manifest.get("review_finalizer"),
        "review_ui": manifest.get("review_ui"),
        "output_validator": manifest.get("output_validator"),
        "files": sorted(identity_records, key=lambda item: str(item.get("path"))),
    }


def _validate_output_policy(value: object) -> None:
    expected = {
        "private_remote_only": [
            {
                "path": f"{OUTPUT_DIRECTORY}/{name}",
                "kind": "private_remote_only",
                "max_bytes": maximum,
            }
            for name, maximum in PRIVATE_OUTPUT_POLICY.items()
        ],
        "private_remote_patterns": [
            {
                "prefix": f"{OUTPUT_DIRECTORY}/{PRIVATE_REVIEW_DIRECTORY}/",
                "basename_pattern": PRIVATE_REVIEW_PATTERN,
                "kind": "private_remote_only",
                "max_file_bytes": PRIVATE_REVIEW_MAX_FILE_BYTES,
                "max_files": PRIVATE_REVIEW_MAX_FILES,
                "max_total_bytes": PRIVATE_REVIEW_MAX_TOTAL_BYTES,
            }
        ],
        "downloadable": [
            {
                "path": f"{OUTPUT_DIRECTORY}/{name}",
                "kind": kind,
                "max_bytes": maximum,
            }
            for name, (kind, maximum) in DOWNLOADABLE_OUTPUT_POLICY.items()
        ],
        "session_log": {
            "basename_pattern": SESSION_LOG_PATTERN,
            "kind": "log",
            "max_bytes": 2 * 1024 * 1024,
            "max_files": 1,
        },
        "max_remote_bytes": 8 * 1024**3 + 581 * 1024**2,
        "max_download_bytes": 512 * 1024,
    }
    if value != expected:
        raise SafeRunError("output_policy_invalid")


def _wheel_distribution(path: Path) -> str:
    return re.sub(r"[-_.]+", "-", path.name.split("-", 1)[0]).lower()


def _verify_run_config(
    bundle_root: Path,
    manifest: Mapping[str, Any],
    records: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[dict[str, Any], dict[str, Path], tuple[Path, ...]]:
    if (
        set(manifest)
        != {
            "schema_version",
            "bundle_format",
            "provenance",
            "deployment",
            "competition",
            "kernel",
            "comparison",
            "review_finalizer",
            "review_ui",
            "output_validator",
            "files",
            "bundle_sha256",
        }
        or manifest.get("schema_version") != 1
        or manifest.get("bundle_format") != BUNDLE_FORMAT
    ):
        raise SafeRunError("bundle_manifest_invalid")
    bundle_sha256 = manifest.get("bundle_sha256")
    if not isinstance(bundle_sha256, str) or not HEX_64.fullmatch(bundle_sha256):
        raise SafeRunError("bundle_manifest_invalid")
    paths = {
        role: bundle_root / str(role_records[0]["path"])
        for role, role_records in records.items()
        if role in EXPECTED_SINGLETON_ROLES
    }
    dependencies = tuple(
        bundle_root / str(record["path"])
        for record in sorted(records[DEPENDENCY_ROLE], key=lambda item: str(item["path"]))
    )
    run_config = _json_object(
        _read_bounded(
            paths["run_config"],
            MAX_POLICY_BYTES,
            "run_config_invalid",
            allow_symlink=True,
        ),
        "run_config_invalid",
    )
    if (
        set(run_config)
        != {
            "schema_version",
            "run_id",
            "code_commit",
            "bundle_sha256",
            "deployment",
            "competition",
            "provenance",
            "input_identity",
            "review_policy",
            "runtime_dependencies",
            "selection",
            "workers",
            "privacy",
            "anatomical_safety",
            "runtime",
            "output_policy",
        }
        or run_config.get("run_id")
        != f"dicom-qa-{cast(str, run_config.get('code_commit', ''))[:12]}"
        or run_config.get("schema_version") != 1
        or run_config.get("bundle_sha256") != bundle_sha256
        or _sha256_bytes(_canonical_json_bytes(_identity_payload(manifest, records, run_config)))
        != bundle_sha256
    ):
        raise SafeRunError("bundle_identity_mismatch")
    provenance = manifest.get("provenance")
    deployment = manifest.get("deployment")
    config_provenance = run_config.get("provenance")
    commit = provenance.get("git_commit") if isinstance(provenance, dict) else None
    if (
        not isinstance(provenance, dict)
        or not isinstance(commit, str)
        or not HEX_40.fullmatch(commit)
        or set(provenance) != {"git_commit", "git_commit_timestamp"}
        or isinstance(provenance.get("git_commit_timestamp"), bool)
        or not isinstance(provenance.get("git_commit_timestamp"), int)
        or provenance["git_commit_timestamp"] < 1
        or run_config.get("code_commit") != commit
        or not isinstance(config_provenance, dict)
        or config_provenance.get("git_commit") != commit
    ):
        raise SafeRunError("provenance_invalid")
    if (
        not isinstance(deployment, dict)
        or set(deployment) != {"owner"}
        or not isinstance(deployment.get("owner"), str)
        or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}", str(deployment["owner"]))
        or run_config.get("deployment") != deployment
    ):
        raise SafeRunError("deployment_identity_invalid")
    if manifest.get("competition") != {"slug": COMPETITION_SLUG} or run_config.get(
        "competition"
    ) != {"slug": COMPETITION_SLUG, "source": "official_competition_input"}:
        raise SafeRunError("competition_source_invalid")
    if set(config_provenance) != {
        "git_commit",
        "preprocessing_config_sha256",
        "preprocessing_schema_sha256",
        "competition_config_sha256",
        "competition_contract_sha256",
        "uv_lock_sha256",
        "preprocessing_version",
        "source_manifest_version",
        "renderer_version",
        "required_runtime_packages",
        "runner_sha256",
        "comparison_sha256",
        "review_finalizer_sha256",
        "review_ui_sha256",
        "review_notebook_sha256",
        "output_validator_sha256",
        "synthetic_preflight_sha256",
    }:
        raise SafeRunError("provenance_invalid")
    expected_hashes = {
        "preprocessing_config_sha256": records["preprocessing_config"][0]["sha256"],
        "preprocessing_schema_sha256": records["preprocessing_schema"][0]["sha256"],
        "competition_config_sha256": records["competition_pointer"][0]["sha256"],
        "competition_contract_sha256": records["competition_contract"][0]["sha256"],
        "uv_lock_sha256": records["dependency_lock"][0]["sha256"],
        "review_finalizer_sha256": records["review_finalizer"][0]["sha256"],
        "synthetic_preflight_sha256": records["synthetic_preflight"][0]["sha256"],
    }
    if any(config_provenance.get(key) != value for key, value in expected_hashes.items()):
        raise SafeRunError("provenance_invalid")
    synthetic_preflight_payload = _read_bounded(
        paths["synthetic_preflight"],
        16 * 1024,
        "synthetic_preflight_invalid",
        allow_symlink=True,
    )
    synthetic_preflight = _json_object(synthetic_preflight_payload, "synthetic_preflight_invalid")
    if (
        synthetic_preflight != SYNTHETIC_PREFLIGHT_REPORT
        or synthetic_preflight_payload != _canonical_json_bytes(synthetic_preflight)
    ):
        raise SafeRunError("synthetic_preflight_invalid")
    if config_provenance.get("required_runtime_packages") != REQUIRED_RUNTIME_PACKAGES:
        raise SafeRunError("runtime_dependency_policy_invalid")
    kernel = manifest.get("kernel")
    comparison = manifest.get("comparison")
    finalizer = manifest.get("review_finalizer")
    review_ui = manifest.get("review_ui")
    output_validator = manifest.get("output_validator")
    if (
        not isinstance(kernel, dict)
        or set(kernel) != {"code_file", "sha256"}
        or kernel.get("code_file") != "run.py"
        or config_provenance.get("runner_sha256") != kernel.get("sha256")
        or records["runner_source"][0].get("sha256") != kernel.get("sha256")
        or not isinstance(comparison, dict)
        or comparison
        != {
            "code_file": "compare_runs.py",
            "sha256": config_provenance.get("comparison_sha256"),
        }
        or records["comparison_source"][0].get("sha256") != comparison.get("sha256")
        or not isinstance(finalizer, dict)
        or set(finalizer) != {"code_file", "sha256"}
        or finalizer.get("code_file") != "finalize_review.py"
        or config_provenance.get("review_finalizer_sha256") != finalizer.get("sha256")
        or not isinstance(review_ui, dict)
        or review_ui
        != {
            "code_file": "review_ui.ipynb",
            "sha256": config_provenance.get("review_notebook_sha256"),
            "module_file": "review_ui.py",
            "module_sha256": config_provenance.get("review_ui_sha256"),
        }
        or records["review_ui_source"][0].get("sha256") != review_ui.get("module_sha256")
        or records["review_notebook"][0].get("sha256") != review_ui.get("sha256")
        or not isinstance(output_validator, dict)
        or output_validator
        != {
            "code_file": "validate_output.py",
            "sha256": config_provenance.get("output_validator_sha256"),
        }
        or records["output_validator"][0].get("sha256") != output_validator.get("sha256")
    ):
        raise SafeRunError("provenance_invalid")
    if (
        config_provenance.get("preprocessing_version") != "dicom-model-v1"
        or config_provenance.get("source_manifest_version") != SOURCE_MANIFEST_VERSION
        or config_provenance.get("renderer_version") != "private-qa-renderer-v1"
    ):
        raise SafeRunError("provenance_invalid")
    input_identity = run_config.get("input_identity")
    if (
        not isinstance(input_identity, dict)
        or set(input_identity) != {"official_competition", "source_manifest"}
        or input_identity.get("official_competition")
        != {
            "slug": COMPETITION_SLUG,
            "contract_sha256": records["competition_contract"][0]["sha256"],
            "snapshot_identity_source": "chunk4_private_manifest",
        }
        or not isinstance(input_identity.get("source_manifest"), dict)
        or cast(Mapping[str, object], input_identity["source_manifest"]).get("audit_id")
        != SOURCE_MANIFEST_AUDIT_ID
        or cast(Mapping[str, object], input_identity["source_manifest"]).get("version")
        != SOURCE_MANIFEST_VERSION
        or cast(Mapping[str, object], input_identity["source_manifest"]).get("schema_sha256")
        != records["source_manifest_schema"][0]["sha256"]
    ):
        raise SafeRunError("input_identity_invalid")
    review_policy = run_config.get("review_policy")
    if review_policy != {
        "protocol_version": REVIEW_PROTOCOL_VERSION,
        "cohort_selection_version": QA_COHORT_SELECTION_VERSION,
        "kernel_version": 1,
        "checks": list(REVIEW_CHECKS),
        "statuses": list(REVIEW_STATUSES),
        "artifact_presence_separate": True,
        "minimum_reviewed_studies": MINIMUM_ELIGIBLE_STUDIES,
    }:
        raise SafeRunError("review_policy_invalid")
    selection = run_config.get("selection")
    if (
        not isinstance(selection, dict)
        or set(selection)
        != {
            "source",
            "seed",
            "target_studies",
            "maximum_studies",
            "minimum_eligible_studies",
            "material_stratum_minimum_studies",
            "material_stratum_sample_quota",
            "strata",
        }
        or selection.get("source") != "train_series.csv"
        or selection.get("seed") != SELECTION_SEED
        or selection.get("target_studies") != TARGET_STUDIES
        or selection.get("maximum_studies") != MAX_TARGET_STUDIES
        or selection.get("minimum_eligible_studies") != MINIMUM_ELIGIBLE_STUDIES
        or selection.get("material_stratum_minimum_studies") != MATERIAL_STRATUM_MIN_STUDIES
        or selection.get("material_stratum_sample_quota") != MATERIAL_STRATUM_SAMPLE_QUOTA
        or selection.get("strata")
        != [
            "plane_profile",
            "fluid_profile",
            "series_count_bucket",
            "slice_count_profile",
            "bit_depth_profile",
            "photometric_profile",
            "transfer_syntax_profile",
            "resolution_profile",
            "thickness_profile",
            "slice_spacing_profile",
            "orientation_obliquity_profile",
        ]
    ):
        raise SafeRunError("selection_policy_invalid")
    runtime = run_config.get("runtime")
    if runtime != {
        "internet": False,
        "accelerator": "cpu",
        "self_deadline_seconds": SELF_DEADLINE_SECONDS,
        "outer_kill_seconds": OUTER_KILL_SECONDS,
    }:
        raise SafeRunError("runtime_policy_invalid")
    safety = run_config.get("anatomical_safety")
    if safety != {
        "physical_order_required": True,
        "horizontal_flip": False,
        "through_plane_resampling": False,
        "laterality_transform": "none",
    }:
        raise SafeRunError("anatomical_policy_invalid")
    privacy = run_config.get("privacy")
    if (
        not isinstance(privacy, dict)
        or set(privacy)
        != {
            "canary",
            "raw_identifiers_downloadable",
            "raw_paths_downloadable",
            "raw_reports_downloadable",
            "patient_metadata_downloadable",
            "pixel_data_downloadable",
            "case_details_downloadable",
            "private_visuals_remote_only",
        }
        or not isinstance(privacy.get("canary"), str)
        or not str(privacy["canary"]).startswith("RSNA_PRIVATE_CANARY_")
        or any(
            privacy.get(key) is not False
            for key in (
                "raw_identifiers_downloadable",
                "raw_paths_downloadable",
                "raw_reports_downloadable",
                "patient_metadata_downloadable",
                "pixel_data_downloadable",
                "case_details_downloadable",
            )
        )
        or privacy.get("private_visuals_remote_only") is not True
    ):
        raise SafeRunError("privacy_policy_invalid")
    _validate_output_policy(run_config.get("output_policy"))
    dependency_identity = [
        {"path": record["path"], "bytes": record["bytes"], "sha256": record["sha256"]}
        for record in sorted(records[DEPENDENCY_ROLE], key=lambda item: str(item["path"]))
    ]
    runtime_dependencies = run_config.get("runtime_dependencies")
    if (
        not isinstance(runtime_dependencies, dict)
        or set(runtime_dependencies)
        != {
            "target_platforms",
            "python_versions",
            "install_mode",
            "wheel_count",
            "wheel_set_sha256",
        }
        or runtime_dependencies.get("target_platforms") != list(TARGET_PLATFORMS)
        or runtime_dependencies.get("python_versions") != list(TARGET_PYTHONS)
        or runtime_dependencies.get("install_mode") != "pip-no-index-find-links"
        or runtime_dependencies.get("wheel_count") != len(dependency_identity)
        or runtime_dependencies.get("wheel_set_sha256")
        != _sha256_bytes(_canonical_json_bytes(dependency_identity))
    ):
        raise SafeRunError("runtime_dependency_policy_invalid")
    workers = run_config.get("workers")
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 16:
        raise SafeRunError("worker_count_invalid")
    for distribution, version in REQUIRED_RUNTIME_PACKAGES.items():
        if not any(
            _wheel_distribution(path) == distribution and f"-{version}-" in path.name.lower()
            for path in dependencies
        ):
            raise SafeRunError("runtime_dependency_policy_invalid")
    kernel = manifest.get("kernel")
    if (
        not isinstance(kernel, dict)
        or set(kernel) != {"code_file", "sha256"}
        or kernel.get("code_file") != "run.py"
        or not isinstance(kernel.get("sha256"), str)
        or not HEX_64.fullmatch(str(kernel["sha256"]))
    ):
        raise SafeRunError("kernel_provenance_invalid")
    try:
        current_runner = Path(__file__).resolve(strict=True)
    except OSError as error:
        raise SafeRunError("kernel_provenance_invalid") from error
    if _sha256_file(current_runner) != kernel["sha256"]:
        raise SafeRunError("kernel_provenance_invalid")
    return run_config, paths, dependencies


def _validate_runtime_wheel_names(paths: Sequence[Path]) -> None:
    names: set[str] = set()
    for path in paths:
        name = path.name.lower()
        if (
            name in names
            or not re.fullmatch(r"[a-z0-9][a-z0-9._+-]{0,199}\.whl", name)
            or any(
                token in name
                for token in (
                    "macosx",
                    "win32",
                    "win_amd64",
                    "arm64",
                    "aarch64",
                    "musllinux",
                )
            )
        ):
            raise SafeRunError("runtime_wheel_platform_invalid")
        names.add(name)
        if "-none-any.whl" not in name and not (
            "manylinux" in name
            and ("x86_64" in name or "amd64" in name)
            and ("cp311" in name or "cp312" in name)
        ):
            raise SafeRunError("runtime_wheel_platform_invalid")


def _install_offline_runtime(
    bundle_root: Path, project_wheel: Path, dependency_wheels: Sequence[Path]
) -> Path:
    if sys.version_info[:2] not in {(3, 11), (3, 12)}:
        raise SafeRunError("python_version_unsupported")
    _validate_runtime_wheel_names(dependency_wheels)
    runtime_root = Path(tempfile.mkdtemp(prefix="rsna-knee-dicom-qa-runtime-"))
    environment = os.environ.copy()
    environment.update(
        {
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INDEX": "1",
            "PIP_NO_INPUT": "1",
            "PIP_KEYRING_PROVIDER": "disabled",
            "PYTHONNOUSERSITE": "1",
        }
    )
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--isolated",
                "--no-index",
                "--find-links",
                str(bundle_root),
                "--only-binary=:all:",
                "--ignore-installed",
                "--no-compile",
                "--no-cache-dir",
                "--disable-pip-version-check",
                "--no-input",
                "--no-warn-script-location",
                "--target",
                str(runtime_root),
                str(project_wheel),
            ],
            env=environment,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=300,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        shutil.rmtree(runtime_root, ignore_errors=True)
        raise SafeRunError("offline_dependency_install_failed") from error
    return runtime_root


def _validated_uid(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64 or not UID.fullmatch(value):
        raise SafeRunError("series_csv_invalid")
    return value


def _csv_flag(value: object) -> str:
    if not isinstance(value, str):
        return "missing"
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes"}:
        return "present"
    if normalized in {"0", "false", "no"}:
        return "absent"
    return "missing"


def _csv_plane(value: object) -> str:
    if not isinstance(value, str):
        return "missing"
    normalized = value.strip().casefold()
    return normalized if normalized in {"sagittal", "coronal", "axial"} else "missing"


def _read_series_rows(path: Path) -> tuple[SeriesRow, ...]:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024**2:
            raise SafeRunError("series_csv_invalid")
        rows: list[SeriesRow] = []
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != EXPECTED_SERIES_HEADER:
                raise SafeRunError("series_csv_invalid")
            seen: set[tuple[str, str]] = set()
            for raw in reader:
                if len(rows) >= MAX_SERIES_ROWS:
                    raise SafeRunError("series_csv_too_large")
                study_uid = _validated_uid(raw.get("StudyInstanceUID"))
                series_uid = _validated_uid(raw.get("SeriesInstanceUID"))
                key = (study_uid, series_uid)
                if key in seen:
                    raise SafeRunError("series_csv_duplicate")
                seen.add(key)
                rows.append(
                    SeriesRow(
                        study_uid=study_uid,
                        series_uid=series_uid,
                        fluid_sensitive=_csv_flag(raw.get("Fluid_Sensitive")),
                        fat_suppression=_csv_flag(raw.get("Fat_Suppression")),
                        plane=_csv_plane(raw.get("Anatomical_Plane")),
                    )
                )
    except SafeRunError:
        raise
    except (OSError, csv.Error, UnicodeError) as error:
        raise SafeRunError("series_csv_invalid") from error
    if not rows:
        raise SafeRunError("series_csv_empty")
    studies = {row.study_uid for row in rows}
    if len(studies) > MAX_STUDIES:
        raise SafeRunError("study_count_invalid")
    return tuple(rows)


def _series_files(competition_root: Path, row: SeriesRow) -> tuple[Path, ...]:
    train_root = competition_root / "train_series"
    directory = train_root / row.study_uid / row.series_uid
    try:
        resolved_root = train_root.resolve(strict=True)
        resolved_directory = directory.resolve(strict=True)
        if resolved_directory.parent.parent != resolved_root or directory.is_symlink():
            raise SafeRunError("series_directory_invalid")
        entries = nsmallest(
            MAX_FILES_PER_SERIES + 1, directory.iterdir(), key=lambda path: path.name
        )
    except SafeRunError:
        raise
    except OSError as error:
        raise SafeRunError("series_directory_invalid") from error
    if not entries:
        raise _SeriesFileDiscoveryError("series_file_count_invalid", ())
    files: list[Path] = []
    invalid_entry = False
    for entry in entries:
        try:
            if entry.is_symlink() or not entry.is_file():
                invalid_entry = True
                continue
            files.append(entry)
            if not 0 < entry.stat().st_size <= 512 * 1024**2:
                invalid_entry = True
        except OSError:
            invalid_entry = True
    bounded_files = tuple(files)
    if len(entries) > MAX_FILES_PER_SERIES:
        raise _SeriesFileDiscoveryError("series_file_count_invalid", bounded_files)
    if invalid_entry:
        raise _SeriesFileDiscoveryError("series_file_invalid", bounded_files)
    return bounded_files


def _bucket_number(value: object, boundaries: tuple[float, ...], labels: tuple[str, ...]) -> str:
    try:
        number = float(cast(Any, value))
    except (TypeError, ValueError, OverflowError):
        return "missing"
    if not math.isfinite(number) or number <= 0:
        return "missing"
    for boundary, label in zip(boundaries, labels, strict=True):
        if number <= boundary:
            return label
    return labels[-1].replace("le_", "gt_")


def _source_manifest_opaque_key(secret: bytes, domain: str, value: str) -> str:
    if len(secret) != 32 or not domain or not value:
        raise SafeRunError("source_manifest_input_invalid")
    return hmac.new(secret, f"{domain}\0{value}".encode(), hashlib.sha256).hexdigest()


def _source_manifest_study_key(secret: bytes, study_uid: str) -> str:
    if UID.fullmatch(study_uid) is None:
        raise SafeRunError("source_manifest_input_invalid")
    return _source_manifest_opaque_key(secret, "study", f"train\0{study_uid}")


def _source_manifest_series_key(secret: bytes, series_uid: str) -> str:
    if UID.fullmatch(series_uid) is None:
        raise SafeRunError("source_manifest_input_invalid")
    return _source_manifest_opaque_key(secret, "series", f"train\0{series_uid}")


def _discover_source_manifest_binding(
    input_root: Path,
    source_config: Mapping[str, object],
) -> SourceManifestBinding:
    expected_keys = {
        "audit_id",
        "version",
        "kernel_ref",
        "kernel_version",
        "kernel_code_file",
        "kernel_code_sha256",
        "bundle_dataset_ref",
        "bundle_dataset_version",
        "bundle_sha256",
        "bundle_dataset_files",
        "private_output_policy",
        "schema_sha256",
        "artifact_inventory_filename",
        "database_filename",
        "audit_key_filename",
    }
    schema_sha256 = source_config.get("schema_sha256")
    if (
        set(source_config) != expected_keys
        or source_config.get("audit_id") != SOURCE_MANIFEST_AUDIT_ID
        or source_config.get("version") != SOURCE_MANIFEST_VERSION
        or not isinstance(source_config.get("kernel_ref"), str)
        or re.fullmatch(
            r"[a-z0-9][a-z0-9_-]{0,49}/[a-z0-9][a-z0-9_-]{0,99}",
            str(source_config["kernel_ref"]),
        )
        is None
        or source_config.get("kernel_version") != 1
        or source_config.get("kernel_code_file") != "run.py"
        or not isinstance(source_config.get("kernel_code_sha256"), str)
        or HEX_64.fullmatch(str(source_config["kernel_code_sha256"])) is None
        or not isinstance(source_config.get("bundle_dataset_ref"), str)
        or re.fullmatch(
            r"[a-z0-9][a-z0-9_-]{0,49}/[a-z0-9][a-z0-9_-]{0,99}",
            str(source_config["bundle_dataset_ref"]),
        )
        is None
        or source_config.get("bundle_dataset_version") != 1
        or not isinstance(source_config.get("bundle_sha256"), str)
        or HEX_64.fullmatch(str(source_config["bundle_sha256"])) is None
        or not isinstance(schema_sha256, str)
        or HEX_64.fullmatch(schema_sha256) is None
        or source_config.get("artifact_inventory_filename") != "private_artifact_inventory.json"
        or source_config.get("database_filename") != "private_manifest.sqlite3"
        or source_config.get("audit_key_filename") != "audit_key.bin"
    ):
        raise SafeRunError("source_manifest_identity_invalid")
    bundle_files = source_config.get("bundle_dataset_files")
    private_policy = source_config.get("private_output_policy")
    if (
        not isinstance(bundle_files, list)
        or not bundle_files
        or not isinstance(private_policy, list)
        or not private_policy
    ):
        raise SafeRunError("source_manifest_identity_invalid")
    bundle_names: set[str] = set()
    for item in bundle_files:
        if (
            not isinstance(item, dict)
            or set(item) != {"name", "bytes", "sha256"}
            or not isinstance(item.get("name"), str)
            or PurePosixPath(str(item["name"])).name != item["name"]
            or item["name"] in bundle_names
            or isinstance(item.get("bytes"), bool)
            or not isinstance(item.get("bytes"), int)
            or cast(int, item["bytes"]) < 1
            or not isinstance(item.get("sha256"), str)
            or HEX_64.fullmatch(str(item["sha256"])) is None
        ):
            raise SafeRunError("source_manifest_identity_invalid")
        bundle_names.add(str(item["name"]))
    if "bundle-manifest.json" not in bundle_names:
        raise SafeRunError("source_manifest_identity_invalid")

    candidates: dict[Path, Path] = {}
    for directory in _bounded_mount_directories(input_root):
        inventory_candidate = directory / "private_artifact_inventory.json"
        if not inventory_candidate.is_file() or not all(
            (directory / name).is_file() for name in SOURCE_MANIFEST_PRIVATE_ARTIFACTS
        ):
            continue
        try:
            candidates.setdefault(inventory_candidate.resolve(strict=True), inventory_candidate)
        except OSError as error:
            raise SafeRunError("source_manifest_input_invalid") from error
    if len(candidates) != 1:
        raise SafeRunError(
            "source_manifest_input_missing" if not candidates else "source_manifest_input_ambiguous"
        )
    inventory_path = next(iter(candidates.values()))
    inventory_payload = _read_bounded(inventory_path, 1024**2, "source_manifest_inventory_invalid")
    inventory_document = _json_object(inventory_payload, "source_manifest_inventory_invalid")
    if inventory_payload != _canonical_json_bytes(inventory_document) or set(
        inventory_document
    ) != {
        "schema_version",
        "artifact_type",
        "provenance",
        "artifacts",
    }:
        raise SafeRunError("source_manifest_inventory_invalid")
    provenance = inventory_document.get("provenance")
    artifacts = inventory_document.get("artifacts")
    if (
        inventory_document.get("schema_version") != 1
        or inventory_document.get("artifact_type") != "private-artifact-inventory"
        or not isinstance(provenance, dict)
        or provenance.get("manifest_schema_sha256") != schema_sha256
        or provenance.get("manifest_version") != SOURCE_MANIFEST_VERSION
        or not isinstance(artifacts, list)
        or len(artifacts) != len(SOURCE_MANIFEST_PRIVATE_ARTIFACTS)
    ):
        raise SafeRunError("source_manifest_inventory_invalid")
    records: dict[str, tuple[int, str]] = {}
    root = inventory_path.parent
    for raw in artifacts:
        if not isinstance(raw, dict) or set(raw) != {
            "name",
            "sha256",
            "size_bytes",
            "privacy",
        }:
            raise SafeRunError("source_manifest_inventory_invalid")
        name = raw.get("name")
        size = raw.get("size_bytes")
        digest = raw.get("sha256")
        if (
            not isinstance(name, str)
            or name not in SOURCE_MANIFEST_PRIVATE_ARTIFACTS
            or name in records
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 1
            or not isinstance(digest, str)
            or HEX_64.fullmatch(digest) is None
            or raw.get("privacy") != "private"
        ):
            raise SafeRunError("source_manifest_inventory_invalid")
        maximum, exact = SOURCE_MANIFEST_PRIVATE_ARTIFACTS[name]
        path = root / name
        try:
            if (
                path.is_symlink()
                or not path.is_file()
                or path.stat().st_size != size
                or size > maximum
                or (exact is not None and size != exact)
                or (
                    name not in {"private_manifest.sqlite3", "audit_key.bin"}
                    and _sha256_file(path) != digest
                )
            ):
                raise SafeRunError("source_manifest_artifact_invalid")
        except OSError as error:
            raise SafeRunError("source_manifest_artifact_invalid") from error
        records[name] = (size, digest)
    if set(records) != set(SOURCE_MANIFEST_PRIVATE_ARTIFACTS):
        raise SafeRunError("source_manifest_inventory_invalid")
    source_artifact_sha256 = _sha256_bytes(inventory_payload + schema_sha256.encode("ascii"))
    return SourceManifestBinding(
        database_path=root / "private_manifest.sqlite3",
        audit_key_path=root / "audit_key.bin",
        database_sha256=records["private_manifest.sqlite3"][1],
        audit_key_sha256=records["audit_key.bin"][1],
        schema_sha256=schema_sha256,
        source_manifest_artifact_sha256=source_artifact_sha256,
    )


def _source_manifest_columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    try:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.Error as error:
        raise SafeRunError("source_manifest_schema_invalid") from error
    return tuple(str(row[1]) for row in rows)


def _validate_source_manifest_series_population(
    connection: sqlite3.Connection,
    secret: bytes,
    rows: Sequence[SeriesRow],
) -> int:
    observed: dict[str, tuple[str, str, str, str]] = {}
    for row in rows:
        series_key = _source_manifest_series_key(secret, row.series_uid)
        study_key = _source_manifest_study_key(secret, row.study_uid)
        if series_key in observed:
            raise SafeRunError("source_manifest_population_mismatch")
        observed[series_key] = (
            study_key,
            row.plane,
            row.fluid_sensitive,
            row.fat_suppression,
        )
    try:
        expected_rows = connection.execute(
            """SELECT series_manifest.series_key,series_manifest.study_key,
                    series_manifest.source_row_count,series_manifest.plane,
                    series_manifest.fluid_sensitive,series_manifest.fat_suppression
                FROM series_manifest JOIN study_manifest
                    ON series_manifest.study_key=study_manifest.study_key
                WHERE study_manifest.split='train'"""
        ).fetchall()
    except sqlite3.Error as error:
        raise SafeRunError("source_manifest_schema_invalid") from error
    expected: dict[str, tuple[str, str, str, str]] = {}
    for (
        raw_series_key,
        raw_study_key,
        source_row_count,
        plane,
        fluid_sensitive,
        fat_suppression,
    ) in expected_rows:
        series_key = str(raw_series_key)
        study_key = str(raw_study_key)
        if (
            HEX_64.fullmatch(series_key) is None
            or HEX_64.fullmatch(study_key) is None
            or source_row_count != 1
            or series_key in expected
        ):
            raise SafeRunError("source_manifest_schema_invalid")
        expected[series_key] = (
            study_key,
            _csv_plane(plane),
            _csv_flag(fluid_sensitive),
            _csv_flag(fat_suppression),
        )
    if expected != observed:
        raise SafeRunError("source_manifest_population_mismatch")
    return len(observed)


def _source_manifest_expected_file_count(connection: sqlite3.Connection) -> int:
    try:
        raw_count = connection.execute(
            """SELECT COUNT(*) FROM slice_file_manifest JOIN series_manifest
                    ON slice_file_manifest.series_key=series_manifest.series_key
                JOIN study_manifest ON series_manifest.study_key=study_manifest.study_key
                WHERE study_manifest.split='train'"""
        ).fetchone()
    except sqlite3.Error as error:
        raise SafeRunError("source_manifest_schema_invalid") from error
    if (
        raw_count is None
        or isinstance(raw_count[0], bool)
        or not isinstance(raw_count[0], int)
        or not 0 <= raw_count[0] <= MAX_SERIES_ROWS * (MAX_FILES_PER_SERIES + 1)
    ):
        raise SafeRunError("source_manifest_population_mismatch")
    return raw_count[0]


def _reconcile_source_manifest_series_files(
    reconciliation: SourceManifestReconciliation,
    *,
    competition_root: Path,
    row: SeriesRow,
    paths: Sequence[Path],
    raw_checksums: Sequence[str | None],
    deadline_at: float | None,
) -> int:
    """Match one current series to the authenticated file snapshot with bounded memory."""

    if len(paths) != len(raw_checksums) or len(paths) > MAX_FILES_PER_SERIES + 1:
        raise SafeRunError("source_manifest_population_mismatch")
    series_key = _source_manifest_series_key(reconciliation.secret, row.series_uid)
    study_key = _source_manifest_study_key(reconciliation.secret, row.study_uid)
    try:
        cursor = reconciliation.connection.execute(
            """SELECT file_key,study_key,file_size_bytes,raw_file_exact_key
                FROM slice_file_manifest WHERE series_key=? ORDER BY file_key""",
            (series_key,),
        )
        expected_rows = cursor.fetchmany(MAX_FILES_PER_SERIES + 2)
    except sqlite3.Error as error:
        raise SafeRunError("source_manifest_schema_invalid") from error
    if len(expected_rows) > MAX_FILES_PER_SERIES + 1:
        raise SafeRunError("source_manifest_population_mismatch")
    expected: dict[str, tuple[str, int, str]] = {}
    for raw_file_key, raw_study_key, raw_size, raw_digest_key in expected_rows:
        file_key = str(raw_file_key)
        expected_study_key = str(raw_study_key)
        digest_key = str(raw_digest_key)
        if (
            HEX_64.fullmatch(file_key) is None
            or expected_study_key != study_key
            or isinstance(raw_size, bool)
            or not isinstance(raw_size, int)
            or not 0 <= raw_size <= 512 * 1024**2
            or HEX_64.fullmatch(digest_key) is None
            or file_key in expected
        ):
            raise SafeRunError("source_manifest_population_mismatch")
        expected[file_key] = (expected_study_key, raw_size, digest_key)

    observed: dict[str, tuple[str, int, str]] = {}
    for path, decoded_raw_checksum in zip(paths, raw_checksums, strict=True):
        _check_deadline(deadline_at)
        try:
            relative = path.relative_to(competition_root).as_posix()
            if path.is_symlink() or not path.is_file():
                raise OSError
            size = path.stat().st_size
            if not 0 <= size <= 512 * 1024**2:
                raise OSError
            raw_checksum = (
                _sha256_file(path) if decoded_raw_checksum is None else decoded_raw_checksum
            )
        except (OSError, ValueError):
            raise SafeRunError("source_manifest_population_mismatch") from None
        if HEX_64.fullmatch(raw_checksum) is None:
            raise SafeRunError("source_manifest_population_mismatch")
        file_key = _source_manifest_opaque_key(reconciliation.secret, "file", relative)
        raw_digest_key = _source_manifest_opaque_key(
            reconciliation.secret, "raw-file-digest", raw_checksum
        )
        if file_key in observed:
            raise SafeRunError("source_manifest_population_mismatch")
        observed[file_key] = (study_key, size, raw_digest_key)
    if observed != expected:
        raise SafeRunError("source_manifest_population_mismatch")
    return len(observed)


def _load_source_manifest_facts(
    binding: SourceManifestBinding,
    rows: Sequence[SeriesRow],
) -> tuple[
    dict[str, dict[str, tuple[str, ...]]],
    dict[str, str],
    SourceManifestReconciliation,
]:
    """Authenticate and read only fixed private Chunk 4 fields without copying the database."""

    database = binding.database_path
    key_path = binding.audit_key_path
    if (
        HEX_64.fullmatch(binding.database_sha256) is None
        or HEX_64.fullmatch(binding.audit_key_sha256) is None
        or database.is_symlink()
        or key_path.is_symlink()
        or not database.is_file()
        or not key_path.is_file()
        or not 0 < database.stat().st_size <= 8 * 1024**3
        or key_path.stat().st_size != 32
        or _sha256_file(database) != binding.database_sha256
        or _sha256_file(key_path) != binding.audit_key_sha256
    ):
        raise SafeRunError("source_manifest_input_invalid")
    try:
        secret = key_path.read_bytes()
    except OSError as error:
        raise SafeRunError("source_manifest_input_invalid") from error
    if len(secret) != 32:
        raise SafeRunError("source_manifest_input_invalid")

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            f"{database.resolve(strict=True).as_uri()}?mode=ro&immutable=1", uri=True
        )
        connection.execute("PRAGMA query_only=ON")
        integrity = connection.execute("PRAGMA integrity_check").fetchall()
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        tables = {
            str(item[0])
            for item in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        if integrity != [("ok",)] or foreign_keys or tables != SOURCE_MANIFEST_TABLES:
            raise SafeRunError("source_manifest_schema_invalid")
        for table, required in SOURCE_MANIFEST_REQUIRED_COLUMNS.items():
            columns = _source_manifest_columns(connection, table)
            if any(column not in columns for column in required):
                raise SafeRunError("source_manifest_schema_invalid")
        run_metadata = dict(connection.execute("SELECT key,value FROM manifest_run").fetchall())
        table_hashes = {
            key.removeprefix("table_sha256:"): value
            for key, value in run_metadata.items()
            if key.startswith("table_sha256:")
        }
        reconciliation = {
            key.removeprefix("reconciliation:"): value
            for key, value in run_metadata.items()
            if key.startswith("reconciliation:")
        }
        if (
            run_metadata.get("manifest_version") != SOURCE_MANIFEST_VERSION
            or run_metadata.get("audit_id") != SOURCE_MANIFEST_AUDIT_ID
            or run_metadata.get("schema_sha256") != binding.schema_sha256
            or set(table_hashes) != SOURCE_MANIFEST_TABLES - {"manifest_run"}
            or any(HEX_64.fullmatch(value) is None for value in table_hashes.values())
            or reconciliation
            != {
                "studies": "pass",
                "series": "pass",
                "files": "pass",
                "reports": "pass",
                "official_label_cells": "pass",
            }
            or run_metadata.get("five_levels_reconciled") != "true"
        ):
            raise SafeRunError("source_manifest_version_mismatch")
        official_input_snapshot_sha256 = _sha256_bytes(
            _canonical_json_bytes(
                {
                    "domain": "rsna-knee-official-input-snapshot-v1",
                    "manifest_version": SOURCE_MANIFEST_VERSION,
                    "schema_sha256": binding.schema_sha256,
                    "table_hashes": dict(sorted(table_hashes.items())),
                    "reconciliation": dict(sorted(reconciliation.items())),
                }
            )
        )

        requested_uids = {row.study_uid for row in rows}
        requested_keys = {_source_manifest_study_key(secret, uid): uid for uid in requested_uids}
        study_rows = connection.execute(
            """SELECT study_key,scanner_manufacturer,scanner_model,field_strength_t,
                domain_cluster_key,data_quality_flags,terminal_state
                FROM study_manifest WHERE split='train'"""
        ).fetchall()
        if {str(item[0]) for item in study_rows} != set(requested_keys):
            raise SafeRunError("source_manifest_population_mismatch")
        expected_series_count = _validate_source_manifest_series_population(
            connection, secret, rows
        )
        expected_file_count = _source_manifest_expected_file_count(connection)

        protected = {
            str(item[0])
            for item in connection.execute("SELECT DISTINCT study_key FROM protected_component")
        }
        candidates = {
            str(item[0])
            for item in connection.execute("SELECT DISTINCT study_key FROM candidate_component")
        }
        issue_rows = connection.execute(
            """SELECT study_key,issue_code,resolution_status FROM manifest_issue
                WHERE entity_level='study'
                UNION ALL
                SELECT series_manifest.study_key,manifest_issue.issue_code,
                    manifest_issue.resolution_status
                FROM manifest_issue JOIN series_manifest
                    ON manifest_issue.entity_level='series'
                    AND manifest_issue.entity_key=series_manifest.series_key
                UNION ALL
                SELECT slice_file_manifest.study_key,manifest_issue.issue_code,
                    manifest_issue.resolution_status
                FROM manifest_issue JOIN slice_file_manifest
                    ON manifest_issue.entity_level='file'
                    AND manifest_issue.entity_key=slice_file_manifest.file_key"""
        ).fetchall()
        issues: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for study_key, issue_code, resolution in issue_rows:
            issues[str(study_key)].append((str(issue_code), str(resolution)))
    except SafeRunError:
        if connection is not None:
            connection.close()
        raise
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        if connection is not None:
            connection.close()
        raise SafeRunError("source_manifest_input_invalid") from error
    try:
        facts: dict[str, dict[str, tuple[str, ...]]] = {}
        for item in study_rows:
            study_key = str(item[0])
            uid = requested_keys[study_key]
            manufacturer = str(item[1]) if item[1] is not None else None
            model = str(item[2]) if item[2] is not None else None
            field_strength = _bucket_number(item[3], (1.0, 1.5, 3.0), ("le_1", "le_1_5", "le_3"))
            domain = str(item[4]) if item[4] is not None else None
            try:
                flags_raw = json.loads(str(item[5]))
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                raise SafeRunError("source_manifest_schema_invalid") from error
            if not isinstance(flags_raw, list) or any(
                not isinstance(value, str) or SAFE_EVENT_VALUE.fullmatch(value) is None
                for value in flags_raw
            ):
                raise SafeRunError("source_manifest_schema_invalid")
            study_issues = tuple(issues.get(study_key, ()))
            remediated = any(
                "decode" in code and resolution != "unresolved_blocker"
                for code, resolution in study_issues
            )
            facts[uid] = {
                "scanner_manufacturer": (() if manufacturer is None else (manufacturer,)),
                "scanner_model": (() if model is None else (model,)),
                "field_strength": (() if field_strength == "missing" else (field_strength,)),
                "site_domain_cluster": (() if domain is None else (domain,)),
                "protected_duplicate_group": (("present",) if study_key in protected else ()),
                "candidate_duplicate_group": (("present",) if study_key in candidates else ()),
                "remediated_decode_case": (("present",) if remediated else ()),
                "source_manifest_quality_flag": tuple(sorted(set(cast(list[str], flags_raw)))),
                "source_manifest_terminal_state": (str(item[6]),),
            }
    except BaseException:
        connection.close()
        raise
    return (
        facts,
        {
            "audit_id": SOURCE_MANIFEST_AUDIT_ID,
            "manifest_version": SOURCE_MANIFEST_VERSION,
            "source_manifest_artifact_sha256": binding.source_manifest_artifact_sha256,
            "official_input_snapshot_sha256": official_input_snapshot_sha256,
        },
        SourceManifestReconciliation(
            connection=connection,
            secret=secret,
            expected_series_count=expected_series_count,
            expected_file_count=expected_file_count,
        ),
    )


def _orientation_bucket(value: object) -> str:
    try:
        values = tuple(float(item) for item in cast(Any, value))
    except (TypeError, ValueError, OverflowError):
        return "missing"
    if len(values) != 6 or any(not math.isfinite(item) for item in values):
        return "missing"
    row, column = values[:3], values[3:]
    row_norm = math.sqrt(sum(item * item for item in row))
    column_norm = math.sqrt(sum(item * item for item in column))
    dot = sum(left * right for left, right in zip(row, column, strict=True))
    if abs(row_norm - 1.0) > 0.01 or abs(column_norm - 1.0) > 0.01 or abs(dot) > 0.01:
        return "malformed"
    normal = (
        row[1] * column[2] - row[2] * column[1],
        row[2] * column[0] - row[0] * column[2],
        row[0] * column[1] - row[1] * column[0],
    )
    magnitudes = tuple(abs(item) for item in normal)
    ordered = sorted(range(3), key=lambda index: (-magnitudes[index], index))
    axis = ("sagittal", "coronal", "axial")[ordered[0]]
    if magnitudes[ordered[0]] - magnitudes[ordered[1]] < 0.05:
        return "oblique_indeterminate"
    return f"orthogonal_{axis}" if magnitudes[ordered[0]] >= 0.95 else f"oblique_{axis}"


def _transfer_syntax_bucket(value: object) -> str:
    raw = str(value) if value is not None else ""
    if raw in {"1.2.840.10008.1.2", "1.2.840.10008.1.2.1"}:
        return "uncompressed_little_endian"
    if raw in {"1.2.840.10008.1.2.4.57", "1.2.840.10008.1.2.4.70"}:
        return "jpeg_lossless"
    if raw in {"1.2.840.10008.1.2.4.90", "1.2.840.10008.1.2.4.91"}:
        return "jpeg2000"
    return "missing" if not raw else "other"


def _header_buckets(path: Path, pydicom_module: Any) -> tuple[str, ...]:
    missing = ("missing",) * 7
    try:
        dataset = pydicom_module.dcmread(
            path,
            force=False,
            stop_before_pixels=True,
            specific_tags=(
                "BitsAllocated",
                "BitsStored",
                "PhotometricInterpretation",
                "Rows",
                "Columns",
                "SliceThickness",
                "SpacingBetweenSlices",
                "ImageOrientationPatient",
            ),
        )
        bits_raw = getattr(dataset, "BitsStored", getattr(dataset, "BitsAllocated", None))
        try:
            bits = int(cast(Any, bits_raw))
        except (TypeError, ValueError, OverflowError):
            bits_bucket = "missing"
        else:
            bits_bucket = (
                "missing"
                if bits < 1
                else "le_8"
                if bits <= 8
                else "le_12"
                if bits <= 12
                else "le_16"
                if bits <= 16
                else "other"
            )
        photometric_raw = str(getattr(dataset, "PhotometricInterpretation", "")).strip().upper()
        photometric = (
            "monochrome1"
            if photometric_raw == "MONOCHROME1"
            else "monochrome2"
            if photometric_raw == "MONOCHROME2"
            else "missing"
            if not photometric_raw
            else "other"
        )
        transfer = _transfer_syntax_bucket(
            getattr(getattr(dataset, "file_meta", None), "TransferSyntaxUID", None)
        )
        try:
            rows, columns = int(dataset.Rows), int(dataset.Columns)
        except (AttributeError, TypeError, ValueError, OverflowError):
            resolution = "missing"
        else:
            maximum = max(rows, columns)
            resolution = "le_256" if maximum <= 256 else "le_512" if maximum <= 512 else "gt_512"
        thickness = _bucket_number(
            getattr(dataset, "SliceThickness", None),
            (1.5, 3.0, 5.0),
            ("le_1_5", "le_3", "le_5"),
        )
        spacing = _bucket_number(
            getattr(dataset, "SpacingBetweenSlices", None),
            (1.5, 3.0, 5.0),
            ("le_1_5", "le_3", "le_5"),
        )
        orientation = _orientation_bucket(getattr(dataset, "ImageOrientationPatient", None))
        return (bits_bucket, photometric, transfer, resolution, thickness, spacing, orientation)
    except MemoryError:
        raise
    except Exception:
        return missing


def _profile(values: Sequence[str]) -> str:
    return "+".join(sorted(set(values))) if values else "missing"


def _series_count_bucket(count: int) -> str:
    return "one_to_three" if count <= 3 else "four_to_six" if count <= 6 else "seven_plus"


def _slice_count_bucket(count: int) -> str:
    if count <= 1:
        return "one"
    if count <= 16:
        return "two_to_sixteen"
    if count <= 32:
        return "seventeen_to_thirty_two"
    if count <= 64:
        return "thirty_three_to_sixty_four"
    return "sixty_five_plus"


def _deterministic_header_sample(files: Sequence[Path], seed: int) -> Path:
    return min(
        files,
        key=lambda path: hashlib.sha256(f"{seed}:{path.name}".encode()).digest(),
    )


def _select_studies(
    competition_root: Path,
    rows: Sequence[SeriesRow],
    pydicom_module: Any,
    *,
    target: int = TARGET_STUDIES,
    maximum: int = MAX_TARGET_STUDIES,
    seed: int = SELECTION_SEED,
    deadline_at: float | None = None,
) -> SelectionPlan:
    """Select a bounded cohort covering every material header-only stratum."""

    if target < 1 or maximum < target:
        raise SafeRunError("selection_target_invalid")
    by_study: dict[str, list[tuple[SeriesRow, tuple[str, ...], str]]] = defaultdict(list)
    for row in rows:
        _check_deadline(deadline_at)
        files = _series_files(competition_root, row)
        sample = _deterministic_header_sample(files, seed)
        by_study[row.study_uid].append(
            (row, _header_buckets(sample, pydicom_module), _slice_count_bucket(len(files)))
        )
    if len(by_study) < target:
        raise SafeRunError("selection_population_too_small")

    strata: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for study_uid, values in by_study.items():
        _check_deadline(deadline_at)
        study_rows = [item[0] for item in values]
        headers = [item[1] for item in values]
        slice_counts = [item[2] for item in values]
        plane_profile = _profile([row.plane for row in study_rows])
        fluid_values = {row.fluid_sensitive for row in study_rows}
        fluid_profile = (
            "mixed"
            if {"present", "absent"}.issubset(fluid_values)
            else "fluid_only"
            if fluid_values == {"present"}
            else "structural_only"
            if fluid_values == {"absent"}
            else "missing_or_partial"
        )
        stratum = (
            plane_profile,
            fluid_profile,
            _series_count_bucket(len(study_rows)),
            _profile(slice_counts),
            *(_profile([header[index] for header in headers]) for index in range(7)),
        )
        strata[stratum].append(study_uid)
    for stratum, studies in strata.items():
        studies.sort(
            key=lambda uid: hashlib.sha256(f"{seed}:{'|'.join(stratum)}:{uid}".encode()).digest()
        )
    ordered_strata = sorted(
        strata,
        key=lambda stratum: hashlib.sha256(f"{seed}:{'|'.join(stratum)}".encode()).digest(),
    )
    material = {
        stratum
        for stratum, studies in strata.items()
        if len(studies) >= MATERIAL_STRATUM_MIN_STUDIES
    }
    material_quota = sum(
        min(MATERIAL_STRATUM_SAMPLE_QUOTA, len(strata[stratum])) for stratum in material
    )
    required_target = max(target, material_quota)
    if required_target > maximum:
        raise SafeRunError("material_strata_coverage_impossible")
    offsets = {stratum: 0 for stratum in ordered_strata}
    selected: list[SelectedStudy] = []
    for stratum in ordered_strata:
        if stratum not in material:
            continue
        quota = min(MATERIAL_STRATUM_SAMPLE_QUOTA, len(strata[stratum]))
        for study_uid in strata[stratum][:quota]:
            selected.append(SelectedStudy(study_uid, stratum))
        offsets[stratum] = quota
    while len(selected) < required_target:
        progressed = False
        for stratum in ordered_strata:
            offset = offsets[stratum]
            studies = strata[stratum]
            if offset >= len(studies):
                continue
            selected.append(SelectedStudy(studies[offset], stratum))
            offsets[stratum] += 1
            progressed = True
            if len(selected) == required_target:
                break
        if not progressed:
            raise SafeRunError("selection_population_too_small")
    selected_counts: dict[tuple[str, ...], int] = defaultdict(int)
    for item in selected:
        selected_counts[item.stratum] += 1
    if any(selected_counts[stratum] < 1 for stratum in material):
        raise SafeRunError("material_strata_coverage_failed")
    census = tuple(
        StratumCensus(
            stratum=stratum,
            population_studies=len(strata[stratum]),
            selected_studies=selected_counts[stratum],
            material=stratum in material,
        )
        for stratum in sorted(strata)
    )
    return SelectionPlan(tuple(selected), census)


def _check_deadline(deadline_at: float | None) -> None:
    if deadline_at is not None and time.monotonic() >= deadline_at:
        raise _DeadlineExceeded


def _fixed_failure_component(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", text) else "unspecified"


def _private_pipeline_failure(error: Any) -> dict[str, str | None]:
    """Retain only bounded pipeline classifications, never exception messages."""

    return {
        "issue": _fixed_failure_component(error.issue.value) or "unspecified",
        "stage": _fixed_failure_component(error.stage) or "unspecified",
        "root_cause": _fixed_failure_component(error.root_cause),
        "exception_type": _fixed_failure_component(error.exception_type),
    }


def _fatal_decode_failure(error: Any) -> bool:
    return str(error.issue.value) in FATAL_DECODE_ISSUE_CODES


def _decode_order_pass(
    paths: Sequence[Path], pipeline_module: Any, *, deadline_at: float | None
) -> SeriesPass:
    decode_started = time.perf_counter()
    decoded: list[Any] = []
    failures: list[dict[str, str | None]] = []
    file_decode_records: list[dict[str, object]] = []
    file_raw_checksums: list[str | None] = []
    for file_ordinal, path in enumerate(paths):
        _check_deadline(deadline_at)
        try:
            decoded_slice = pipeline_module.decode_dicom(path)
            decoded.append(decoded_slice)
        except MemoryError:
            raise
        except pipeline_module.PipelineError as error:
            failure = _private_pipeline_failure(error)
            failures.append(failure)
            file_decode_records.append(
                {
                    "file_ordinal": file_ordinal,
                    "decode_state": "failed",
                    "failure": failure,
                }
            )
            file_raw_checksums.append(None)
        except Exception:
            raise SafeRunError("unsafe_decode_state") from None
        else:
            file_decode_records.append({"file_ordinal": file_ordinal, "decode_state": "pass"})
            file_raw_checksums.append(str(decoded_slice.raw_checksum))
    decode_seconds = time.perf_counter() - decode_started
    ordering_started = time.perf_counter()
    ordered = None
    order_failure: dict[str, str | None] | None = None
    if decoded:
        try:
            ordered = pipeline_module.order_series(tuple(decoded))
        except pipeline_module.PipelineError as error:
            order_failure = _private_pipeline_failure(error)
        except Exception:
            raise SafeRunError("unsafe_ordering_state") from None
    return SeriesPass(
        tuple(decoded),
        tuple(failures),
        tuple(file_decode_records),
        tuple(file_raw_checksums),
        ordered,
        order_failure,
        decode_seconds,
        time.perf_counter() - ordering_started,
    )


def _failure_resolution(failures: Sequence[Mapping[str, object]]) -> str:
    unresolved_roots = {
        "decoder_unavailable",
        "unsupported_transfer_syntax",
        "unexpected_unexplained",
        "dicom_parse_io_error",
        "file_read_io_error",
    }
    if any(
        str(item.get("issue")) in FATAL_DECODE_ISSUE_CODES
        or str(item.get("root_cause")) in unresolved_roots
        for item in failures
    ):
        return "unresolved_blocker"
    return "excluded_unusable_source"


def _series_pass_record(result: SeriesPass) -> dict[str, object]:
    decoded = [
        {
            "metadata": asdict(item.metadata),
            "raw_checksum": item.raw_checksum,
            "decoded_checksum": item.decoded_checksum,
            "model_pixel_checksum": item.model_pixel_checksum,
            "transfer_syntax": item.transfer_syntax,
            "laterality": item.laterality,
        }
        for item in result.decoded
    ]
    ordered = result.ordered
    ordered_record = (
        None
        if ordered is None
        else {
            "ordered_raw_checksums": [item.raw_checksum for item in ordered.slices],
            "ordered_decoded_checksums": [item.decoded_checksum for item in ordered.slices],
            "ordered_model_pixel_checksums": [item.model_pixel_checksum for item in ordered.slices],
            "geometry": asdict(ordered.geometry),
            "transformation_ledger": asdict(ordered.ledger),
            "laterality": ordered.laterality,
            "slice_lateralities": list(ordered.slice_lateralities),
            "input_checksum": ordered.input_checksum,
            "model_eligible": ordered.model_eligible,
        }
    )
    return {
        "decoded": decoded,
        "decode_failures": list(result.decode_failures),
        "file_decode_records": list(result.file_decode_records),
        "ordered": ordered_record,
        "ordering_failure": result.order_failure,
    }


def _file_terminal_records(
    result: SeriesPass, terminal_state: str, resolution_state: str
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for decode_record in result.file_decode_records:
        failed = decode_record["decode_state"] == "failed"
        failure = cast(Mapping[str, object] | None, decode_record.get("failure"))
        records.append(
            {
                **decode_record,
                "terminal_state": "decode_blocked" if failed else terminal_state,
                "resolution_state": (
                    _failure_resolution((failure,)) if failure is not None else resolution_state
                ),
                "disposition": (
                    "file_quarantine"
                    if failed
                    else "included_in_model_series"
                    if terminal_state == "model_eligible"
                    else "series_quarantine"
                ),
            }
        )
    return records


def _decoder_preflight() -> None:
    try:
        from pydicom.pixels import get_decoder  # type: ignore[attr-defined]

        decoders = tuple(
            get_decoder(uid) for uid in ("1.2.840.10008.1.2.4.70", "1.2.840.10008.1.2.4.90")
        )
    except Exception as error:
        raise SafeRunError("required_decoder_unavailable") from error
    if any(decoder.is_available is not True for decoder in decoders):
        raise SafeRunError("required_decoder_unavailable")


def _preprocessing_config(path: Path, pipeline_module: Any) -> Any:
    payload = _json_object(
        _read_bounded(path, 128 * 1024, "preprocessing_config_invalid", allow_symlink=True),
        "preprocessing_config_invalid",
    )
    expected = {
        "schema_version",
        "preprocessing_version",
        "lower_percentile",
        "upper_percentile",
        "normalization",
        "sample_count",
        "local_contrast_channel",
        "local_contrast_window",
        "adjacent_slice_channels",
        "difference_channel",
        "resize_rows_columns",
        "allow_instance_fallback_for_qa",
        "horizontal_flip",
        "through_plane_resampling",
    }
    if (
        set(payload) != expected
        or payload.get("schema_version") != 1
        or payload.get("preprocessing_version") != pipeline_module.PREPROCESSING_VERSION
        or payload.get("horizontal_flip") is not False
        or payload.get("through_plane_resampling") is not False
        or payload.get("allow_instance_fallback_for_qa") is not False
    ):
        raise SafeRunError("preprocessing_config_invalid")
    if (
        any(
            isinstance(payload[key], bool) or not isinstance(payload[key], (int, float))
            for key in ("lower_percentile", "upper_percentile")
        )
        or not isinstance(payload["normalization"], str)
        or (
            payload["sample_count"] is not None
            and (
                isinstance(payload["sample_count"], bool)
                or not isinstance(payload["sample_count"], int)
            )
        )
        or any(
            not isinstance(payload[key], bool)
            for key in (
                "local_contrast_channel",
                "adjacent_slice_channels",
                "difference_channel",
            )
        )
        or isinstance(payload["local_contrast_window"], bool)
        or not isinstance(payload["local_contrast_window"], int)
    ):
        raise SafeRunError("preprocessing_config_invalid")
    resize = payload["resize_rows_columns"]
    if resize is not None:
        if (
            not isinstance(resize, list)
            or len(resize) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) for value in resize)
        ):
            raise SafeRunError("preprocessing_config_invalid")
        resize = (resize[0], resize[1])
    try:
        return pipeline_module.PreprocessingConfig(
            lower_percentile=payload["lower_percentile"],
            upper_percentile=payload["upper_percentile"],
            normalization=pipeline_module.NormalizationMode(payload["normalization"]),
            sample_count=payload["sample_count"],
            local_contrast_channel=payload["local_contrast_channel"],
            local_contrast_window=payload["local_contrast_window"],
            adjacent_slice_channels=payload["adjacent_slice_channels"],
            difference_channel=payload["difference_channel"],
            resize_rows_columns=resize,
            allow_instance_fallback_for_qa=False,
        )
    except (TypeError, ValueError, KeyError) as error:
        raise SafeRunError("preprocessing_config_invalid") from error


def _spacing_cv(spacings: Sequence[float]) -> float | None:
    if not spacings:
        return None
    mean = sum(spacings) / len(spacings)
    if mean <= 0:
        return None
    variance = sum((value - mean) ** 2 for value in spacings) / len(spacings)
    return math.sqrt(variance) / mean


def _quality(
    *,
    total: int,
    decoded: int,
    ordered: Any | None,
    slots_module: Any,
) -> Any:
    duplicate_slices = 0
    geometry_valid = False
    spacing_regular = False
    median_spacing: float | None = None
    spacing_cv: float | None = None
    pixel_spacing: tuple[float, float] | None = None
    physical_coverage: float | None = None
    if ordered is not None:
        geometry = ordered.geometry
        duplicate_slices = sum(len(group) - 1 for group in geometry.duplicate_pixel_groups)
        geometry_valid = bool(ordered.model_eligible)
        spacing_regular = not geometry.spacing_is_uneven
        median_spacing = geometry.median_slice_spacing_mm
        spacing_cv = _spacing_cv(geometry.slice_spacings_mm)
        pixel_spacing = geometry.pixel_spacing_row_column_mm
        if len(geometry.projected_positions_mm) > 1:
            physical_coverage = (
                geometry.projected_positions_mm[-1] - geometry.projected_positions_mm[0]
            )
        elif len(geometry.projected_positions_mm) == 1:
            physical_coverage = 0.0
    return slots_module.SeriesQuality(
        total_slices=total,
        decoded_slices=decoded,
        decode_failure_count=total - decoded,
        duplicate_slices=duplicate_slices,
        geometry_valid=geometry_valid,
        spacing_regular=spacing_regular,
        median_slice_spacing_mm=median_spacing,
        spacing_coefficient_of_variation=spacing_cv,
        pixel_spacing_mm=pixel_spacing,
        physical_coverage_mm=physical_coverage,
    )


def _physical_plane_value(orientation: object, slots_module: Any) -> str:
    derived = slots_module.plane_from_image_orientation(orientation)
    if derived is slots_module.AnatomicalPlane.SAGITTAL:
        return "sagittal"
    if derived is slots_module.AnatomicalPlane.CORONAL:
        return "coronal"
    if derived is slots_module.AnatomicalPlane.AXIAL:
        return "axial"
    return "oblique" if _orientation_bucket(orientation) == "oblique_indeterminate" else "unknown"


def _review_plane_context(row: SeriesRow, orientation: object, slots_module: Any) -> dict[str, str]:
    return {
        "organizer_plane": row.plane,
        "physical_plane": _physical_plane_value(orientation, slots_module),
    }


def _qa_plane(row: SeriesRow, ordered: Any, qa_module: Any, slots_module: Any) -> Any:
    physical = _physical_plane_value(ordered.slices[0].metadata.image_orientation, slots_module)
    if physical == "sagittal":
        return qa_module.QaPlane.SAGITTAL
    if physical == "coronal":
        return qa_module.QaPlane.CORONAL
    if physical == "axial":
        return qa_module.QaPlane.AXIAL
    if physical == "oblique":
        return qa_module.QaPlane.OBLIQUE
    if row.plane == "sagittal":
        return qa_module.QaPlane.SAGITTAL
    if row.plane == "coronal":
        return qa_module.QaPlane.CORONAL
    if row.plane == "axial":
        return qa_module.QaPlane.AXIAL
    return qa_module.QaPlane.UNKNOWN


def _qa_laterality(value: str | None, qa_module: Any) -> Any:
    return {
        "L": qa_module.QaLaterality.LEFT,
        "R": qa_module.QaLaterality.RIGHT,
        "B": qa_module.QaLaterality.BILATERAL,
    }.get(value or "", qa_module.QaLaterality.UNKNOWN)


def _qa_metadata(
    *,
    case_ordinal: int,
    series_ordinal: int,
    row: SeriesRow,
    ordered: Any,
    qa_result: Any,
    qa_module: Any,
    slots_module: Any,
) -> Any:
    geometry = ordered.geometry
    orientation = ordered.slices[0].metadata.image_orientation
    normal = geometry.canonical_slice_normal_lps
    if orientation is None or normal is None:
        raise SafeRunError("qa_geometry_invalid")
    photometric = ordered.slices[0].metadata.photometric_interpretation
    return qa_module.QaSafeMetadata(
        case_ordinal=case_ordinal,
        series_ordinal=series_ordinal,
        plane=_qa_plane(row, ordered, qa_module, slots_module),
        sequence=(
            qa_module.QaSequence.FLUID_SENSITIVE
            if row.fluid_sensitive == "present"
            else qa_module.QaSequence.NON_FLUID_SENSITIVE
            if row.fluid_sensitive == "absent"
            else qa_module.QaSequence.UNKNOWN
        ),
        fat_suppression=(
            qa_module.QaPresence.PRESENT
            if row.fat_suppression == "present"
            else qa_module.QaPresence.ABSENT
            if row.fat_suppression == "absent"
            else qa_module.QaPresence.UNKNOWN
        ),
        photometric=(
            qa_module.QaPhotometric.MONOCHROME1
            if photometric == "MONOCHROME1"
            else qa_module.QaPhotometric.MONOCHROME2
        ),
        laterality=_qa_laterality(ordered.laterality, qa_module),
        ordering=qa_module.QaOrdering.PHYSICAL_GEOMETRY,
        geometry=qa_module.QaGeometry(
            row_spacing_mm=geometry.pixel_spacing_row_column_mm[0],
            column_spacing_mm=geometry.pixel_spacing_row_column_mm[1],
            slice_spacing_mm=geometry.median_slice_spacing_mm,
            orientation_consistent=True,
            spacing_consistent=not geometry.spacing_is_uneven,
            positions_monotonic=all(
                left < right
                for left, right in zip(
                    geometry.projected_positions_mm,
                    geometry.projected_positions_mm[1:],
                    strict=False,
                )
            ),
            processed_row_spacing_mm=qa_result.output_pixel_spacing_row_column_mm[0],
            processed_column_spacing_mm=qa_result.output_pixel_spacing_row_column_mm[1],
            display_right_direction=qa_module.qa_direction_from_lps(orientation[:3]),
            display_down_direction=qa_module.qa_direction_from_lps(orientation[3:]),
            slice_advance_direction=qa_module.qa_direction_from_lps(normal),
            relative_slice_positions_mm=geometry.projected_positions_mm,
        ),
    )


def _private_reconstruction_record(result: Any) -> dict[str, object]:
    """Return the full private transformation account without retaining tensor values."""

    return {
        "source_slice_count": len(result.ledger.ordered_input_checksums),
        "output_tensor_shape": list(result.tensor.shape),
        "output_tensor_dtype": str(result.tensor.dtype),
        "channel_names": list(result.channel_names),
        "sampled_ordered_indices": list(result.sampled_ordered_indices),
        "sampled_projected_positions_mm": list(result.sampled_projected_positions_mm),
        "geometry": asdict(result.geometry),
        "clipping_values": list(result.clipping_values),
        "normalization_statistics": list(result.normalization_statistics),
        "output_pixel_spacing_row_column_mm": list(result.output_pixel_spacing_row_column_mm),
        "output_affine_lps_slice_row_column": result.output_affine_lps_slice_row_column,
        "laterality": result.laterality,
        "transformation_ledger": asdict(result.ledger),
        "provenance": asdict(result.provenance),
    }


def _series_selection_features(
    row: SeriesRow,
    series_pass: SeriesPass,
    quality: Any,
    terminal_state: str,
) -> dict[str, tuple[str, ...]]:
    metadata = [item.metadata for item in series_pass.decoded]
    bits = _profile(
        [
            "le_8"
            if item.bits_stored <= 8
            else "le_12"
            if item.bits_stored <= 12
            else "le_16"
            if item.bits_stored <= 16
            else "other"
            for item in metadata
        ]
    )
    photometric = _profile(
        [str(item.photometric_interpretation).strip().casefold() for item in metadata]
    )
    transfer = _profile(
        [_transfer_syntax_bucket(item.transfer_syntax) for item in series_pass.decoded]
    )
    resolution = _profile(
        [
            "le_256"
            if max(item.rows, item.columns) <= 256
            else "le_512"
            if max(item.rows, item.columns) <= 512
            else "gt_512"
            for item in metadata
        ]
    )
    thickness = _profile(
        [
            _bucket_number(
                item.slice_thickness,
                (1.5, 3.0, 5.0),
                ("le_1_5", "le_3", "le_5"),
            )
            for item in metadata
        ]
    )
    slice_spacing = (
        _bucket_number(
            quality.median_slice_spacing_mm,
            (1.5, 3.0, 5.0),
            ("le_1_5", "le_3", "le_5"),
        )
        if quality.median_slice_spacing_mm is not None
        else _profile(
            [
                _bucket_number(
                    item.spacing_between_slices,
                    (1.5, 3.0, 5.0),
                    ("le_1_5", "le_3", "le_5"),
                )
                for item in metadata
            ]
        )
    )
    orientation = _profile([_orientation_bucket(item.image_orientation) for item in metadata])
    eligible = terminal_state == "model_eligible"
    spacing_cv = quality.spacing_coefficient_of_variation
    quality_band = (
        "blocked"
        if not eligible
        else "high"
        if quality.decode_failure_count == 0
        and quality.duplicate_slices == 0
        and (spacing_cv is None or spacing_cv <= 0.01)
        else "low"
    )
    edge_case = any(
        (
            "oblique" in orientation,
            "monochrome1" in photometric,
            "jpeg" in transfer,
            terminal_state != "model_eligible",
        )
    )
    return {
        "plane": (row.plane,),
        "sequence": (
            "fluid_sensitive"
            if row.fluid_sensitive == "present"
            else "structural"
            if row.fluid_sensitive == "absent"
            else "missing",
        ),
        "fat_suppression": (row.fat_suppression,),
        "slice_count": (_slice_count_bucket(quality.total_slices),),
        "bit_depth": (bits,),
        "photometric": (photometric,),
        "transfer_syntax": (transfer,),
        "resolution": (resolution,),
        "slice_thickness": (thickness,),
        "slice_spacing": (slice_spacing,),
        "orientation": (orientation,),
        "quality": (quality_band,),
        "duplicate_integrity": (("present",) if quality.duplicate_slices else ()),
        "dicom_edge_case": (("present",) if edge_case else ()),
        "terminal_state": (terminal_state,),
    }


def _cache_tensor(
    result: Any,
    *,
    cache_root: Path,
) -> tuple[Path, int, str, float]:
    """Write and hash one real NPY cache artifact; the bounded study owner removes it."""

    import numpy as np

    started = time.perf_counter()
    descriptor, name = tempfile.mkstemp(prefix="series-cache-", suffix=".npy", dir=cache_root)
    path = Path(name)
    try:
        with os.fdopen(descriptor, "w+b") as temporary:
            np.save(temporary, result.tensor, allow_pickle=False)
            temporary.flush()
            os.fsync(temporary.fileno())
            size = temporary.tell()
            temporary.seek(0)
            digest = hashlib.sha256()
            for chunk in iter(lambda: temporary.read(1024 * 1024), b""):
                digest.update(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path, size, digest.hexdigest(), time.perf_counter() - started


def _full_series_state(
    *,
    competition_root: Path,
    row: SeriesRow,
    pipeline_module: Any,
    slots_module: Any,
    config: Any,
    versions: Any,
    cache_root: Path,
    deadline_at: float | None,
) -> dict[str, Any]:
    """Process one series completely and return only bounded private evidence."""

    _check_deadline(deadline_at)
    try:
        paths = _series_files(competition_root, row)
    except SafeRunError as error:
        paths = error.files if isinstance(error, _SeriesFileDiscoveryError) else ()
        quality = _quality(total=len(paths), decoded=0, ordered=None, slots_module=slots_module)
        candidate = slots_module.SeriesCandidate(
            series_key=row.series_uid,
            tie_break_key=hashlib.sha256(row.series_uid.encode("ascii")).hexdigest(),
            organizer_plane=None if row.plane == "missing" else row.plane,
            organizer_fluid_sensitive=(
                True
                if row.fluid_sensitive == "present"
                else False
                if row.fluid_sensitive == "absent"
                else None
            ),
            image_orientation_patient=None,
            quality=quality,
        )
        empty_pass = SeriesPass((), (), (), (), None, None, 0.0, 0.0)
        return {
            "row": row,
            "candidate": candidate,
            "paths": paths,
            "file_raw_checksums": tuple(None for _ in paths),
            "provenance": None,
            "quality": quality,
            "selection_features": _series_selection_features(
                row, empty_pass, quality, "source_access_blocked"
            ),
            "cache_path": None,
            "timings": {
                "decode_seconds": 0.0,
                "ordering_seconds": 0.0,
                "preprocessing_seconds": 0.0,
                "cache_generation_seconds": 0.0,
            },
            "record": {
                "series_uid": row.series_uid,
                "source": {
                    "plane": row.plane,
                    "fluid_sensitive": row.fluid_sensitive,
                    "fat_suppression": row.fat_suppression,
                },
                "files": len(paths),
                "slot": None,
                "retention_reasons": [],
                "quality": {
                    "blocked_reasons": [reason.value for reason in quality.blocked_reasons],
                    "components": asdict(quality.components),
                },
                "source_failure": error.code,
                "decode_failures": [],
                "file_records": [
                    {
                        "file_ordinal": file_ordinal,
                        "decode_state": "not_attempted",
                        "terminal_state": "source_access_blocked",
                        "resolution_state": "unresolved_blocker",
                        "disposition": "series_quarantine",
                    }
                    for file_ordinal in range(len(paths))
                ],
                "ordering_failure": None,
                "preprocessing_failure": None,
                "terminal_state": "source_access_blocked",
                "resolution_state": "unresolved_blocker",
                "disposition": "series_quarantine",
                "model_eligible": False,
                "model_output_reconstruction": None,
                "cache": None,
            },
        }
    series_pass = _decode_order_pass(paths, pipeline_module, deadline_at=deadline_at)
    ordered = series_pass.ordered
    quality = _quality(
        total=len(paths),
        decoded=len(series_pass.decoded),
        ordered=ordered,
        slots_module=slots_module,
    )
    orientation = (
        ordered.slices[0].metadata.image_orientation
        if ordered is not None
        else series_pass.decoded[0].metadata.image_orientation
        if series_pass.decoded
        else None
    )
    candidate = slots_module.SeriesCandidate(
        series_key=row.series_uid,
        tie_break_key=hashlib.sha256(row.series_uid.encode("ascii")).hexdigest(),
        organizer_plane=None if row.plane == "missing" else row.plane,
        organizer_fluid_sensitive=(
            True
            if row.fluid_sensitive == "present"
            else False
            if row.fluid_sensitive == "absent"
            else None
        ),
        image_orientation_patient=orientation,
        quality=quality,
    )
    preprocessing_seconds = 0.0
    cache_seconds = 0.0
    cache_bytes = 0
    cache_sha256: str | None = None
    cache_path: Path | None = None
    reconstruction: dict[str, object] | None = None
    provenance: Any | None = None
    preprocessing_failure: dict[str, str | None] | None = None
    terminal_state = (
        "decode_blocked"
        if series_pass.decode_failures or not series_pass.decoded
        else "ordering_blocked"
        if series_pass.order_failure is not None or ordered is None
        else "quality_blocked"
        if quality.blocked or not ordered.model_eligible
        else "model_eligible"
    )
    if terminal_state == "model_eligible":
        started = time.perf_counter()
        try:
            result = pipeline_module.preprocess_series(ordered, config, versions)
        except MemoryError:
            raise
        except pipeline_module.PipelineError as error:
            preprocessing_seconds = time.perf_counter() - started
            preprocessing_failure = _private_pipeline_failure(error)
            terminal_state = "preprocessing_blocked"
        except Exception:
            raise SafeRunError("unsafe_preprocessing_state") from None
        else:
            preprocessing_seconds = time.perf_counter() - started
            cache_path, cache_bytes, cache_sha256, cache_seconds = _cache_tensor(
                result, cache_root=cache_root
            )
            reconstruction = _private_reconstruction_record(result)
            provenance = result.provenance
    failures: list[Mapping[str, object]] = [*series_pass.decode_failures]
    if series_pass.order_failure is not None:
        failures.append(series_pass.order_failure)
    if preprocessing_failure is not None:
        failures.append(preprocessing_failure)
    resolution_state = (
        "pass"
        if terminal_state == "model_eligible"
        else _failure_resolution(failures)
        if failures
        else "excluded_unusable_source"
    )
    return {
        "row": row,
        "candidate": candidate,
        "paths": paths,
        "file_raw_checksums": series_pass.file_raw_checksums,
        "provenance": provenance,
        "quality": quality,
        "selection_features": _series_selection_features(row, series_pass, quality, terminal_state),
        "cache_path": cache_path,
        "timings": {
            "decode_seconds": series_pass.decode_seconds,
            "ordering_seconds": series_pass.ordering_seconds,
            "preprocessing_seconds": preprocessing_seconds,
            "cache_generation_seconds": cache_seconds,
        },
        "record": {
            "series_uid": row.series_uid,
            "source": {
                "plane": row.plane,
                "fluid_sensitive": row.fluid_sensitive,
                "fat_suppression": row.fat_suppression,
            },
            "files": len(paths),
            "slot": None,
            "retention_reasons": [],
            "quality": {
                "blocked_reasons": [reason.value for reason in quality.blocked_reasons],
                "components": asdict(quality.components),
            },
            "decode_failures": list(series_pass.decode_failures),
            "file_records": _file_terminal_records(series_pass, terminal_state, resolution_state),
            "ordering_failure": series_pass.order_failure,
            "source_failure": None,
            "preprocessing_failure": preprocessing_failure,
            "terminal_state": terminal_state,
            "resolution_state": resolution_state,
            "disposition": (
                "model_eligible" if terminal_state == "model_eligible" else "series_quarantine"
            ),
            "model_eligible": terminal_state == "model_eligible",
            "model_output_reconstruction": reconstruction,
            "cache": (
                None
                if cache_sha256 is None
                else {"format": "npy-v1", "bytes": cache_bytes, "sha256": cache_sha256}
            ),
        },
    }


def _cohort_study(
    study_uid: str,
    states: Sequence[Mapping[str, Any]],
    missing_mask: Sequence[bool],
    source_manifest_facts: Mapping[str, tuple[str, ...]] | None,
) -> CohortStudy:
    dimensions: dict[str, set[str]] = defaultdict(set)
    duplicate_slot = False
    for state in states:
        features = cast(Mapping[str, Sequence[str]], state["selection_features"])
        for dimension, values in features.items():
            dimensions[dimension].update(str(value) for value in values if value)
        record = cast(Mapping[str, Any], state["record"])
        duplicate_slot = duplicate_slot or "duplicate_slot" in cast(
            Sequence[str], record["retention_reasons"]
        )
    dimensions["multiple_series_per_slot"].add("present" if duplicate_slot else "absent")
    dimensions["missing_slot"].add("present" if any(missing_mask) else "absent")
    if duplicate_slot:
        dimensions["duplicate_integrity"].add("present")
    if source_manifest_facts is not None:
        for dimension, values in source_manifest_facts.items():
            dimensions[dimension].update(values)

    def profile(name: str) -> str:
        return _profile(sorted(dimensions.get(name, ())))

    stratum = (
        profile("plane"),
        profile("sequence"),
        _series_count_bucket(len(states)),
        profile("slice_count"),
        profile("bit_depth"),
        profile("photometric"),
        profile("transfer_syntax"),
        profile("resolution"),
        profile("slice_thickness"),
        profile("slice_spacing"),
        profile("orientation"),
    )
    eligible_series_uids = tuple(
        sorted(
            str(cast(Mapping[str, object], state["record"])["series_uid"])
            for state in states
            if cast(Mapping[str, object], state["record"]).get("terminal_state") == "model_eligible"
        )
    )
    return CohortStudy(
        study_uid=study_uid,
        stratum=stratum,
        dimensions=tuple(
            (dimension, tuple(sorted(values))) for dimension, values in sorted(dimensions.items())
        ),
        eligible_series_uids=eligible_series_uids,
    )


def _select_after_full_pass(
    studies: Sequence[CohortStudy],
    *,
    source_manifest_available: bool,
    target: int = TARGET_STUDIES,
    maximum: int = MAX_TARGET_STUDIES,
    minimum_eligible: int = MINIMUM_ELIGIBLE_STUDIES,
    seed: int = SELECTION_SEED,
) -> SelectionPlan:
    """Select reviewable studies only after every series has a terminal full-run record."""

    if target < 1 or minimum_eligible < 1 or maximum < max(target, minimum_eligible):
        raise SafeRunError("selection_target_invalid")
    eligible = tuple(
        sorted(
            (item for item in studies if item.eligible_series),
            key=lambda item: item.study_uid,
        )
    )
    required_target = max(target, minimum_eligible)
    if len(eligible) < required_target:
        raise SafeRunError("eligible_study_gate_failed")

    by_uid = {item.study_uid: item for item in eligible}
    token_members: dict[tuple[str, str], set[str]] = defaultdict(set)
    joint_members: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for item in eligible:
        for dimension, values in item.dimensions:
            if dimension not in REQUIRED_REVIEW_DIMENSIONS:
                continue
            for value in values:
                token_members[(dimension, value)].add(item.study_uid)
        joint_members[item.stratum].add(item.study_uid)

    requirements: dict[tuple[str, str], int] = {
        token: min(MATERIAL_STRATUM_SAMPLE_QUOTA, len(members))
        for token, members in token_members.items()
    }
    study_tokens = {
        item.study_uid: {
            (dimension, value)
            for dimension, values in item.dimensions
            if dimension in REQUIRED_REVIEW_DIMENSIONS
            for value in values
        }
        for item in eligible
    }
    joint_requirements = {
        stratum: min(MATERIAL_STRATUM_SAMPLE_QUOTA, len(members))
        for stratum, members in joint_members.items()
        if len(members) >= MATERIAL_STRATUM_MIN_STUDIES
    }
    selected: set[str] = set()
    token_counts: dict[tuple[str, str], int] = defaultdict(int)
    joint_counts: dict[tuple[str, ...], int] = defaultdict(int)

    def needs(uid: str) -> int:
        item = by_uid[uid]
        score = sum(
            token_counts[token] < requirements[token]
            for token in study_tokens[uid]
            if token in requirements
        )
        return score + int(
            item.stratum in joint_requirements
            and joint_counts[item.stratum] < joint_requirements[item.stratum]
        )

    while any(token_counts[token] < count for token, count in requirements.items()) or any(
        joint_counts[stratum] < count for stratum, count in joint_requirements.items()
    ):
        candidates = [uid for uid in by_uid if uid not in selected and needs(uid)]
        if not candidates or len(selected) >= maximum:
            raise SafeRunError("material_strata_coverage_impossible")
        chosen = min(
            candidates,
            key=lambda uid: (
                -needs(uid),
                hashlib.sha256(f"{seed}:material:{uid}".encode()).digest(),
            ),
        )
        selected.add(chosen)
        item = by_uid[chosen]
        for dimension, values in item.dimensions:
            for value in values:
                token_counts[(dimension, value)] += 1
        joint_counts[item.stratum] += 1

    remaining = sorted(
        (uid for uid in by_uid if uid not in selected),
        key=lambda uid: hashlib.sha256(f"{seed}:fill:{uid}".encode()).digest(),
    )
    selected.update(remaining[: max(0, required_target - len(selected))])
    if not required_target <= len(selected) <= maximum:
        raise SafeRunError("selection_population_too_small")
    selected_order = sorted(
        selected, key=lambda uid: hashlib.sha256(f"{seed}:order:{uid}".encode()).digest()
    )

    selected_token_counts: dict[tuple[str, str], int] = defaultdict(int)
    selected_joint_counts: dict[tuple[str, ...], int] = defaultdict(int)
    for uid in selected_order:
        item = by_uid[uid]
        selected_joint_counts[item.stratum] += 1
        for dimension, values in item.dimensions:
            for value in values:
                selected_token_counts[(dimension, value)] += 1
    if any(
        selected_token_counts[token] < required for token, required in requirements.items()
    ) or any(
        selected_joint_counts[stratum] < required
        for stratum, required in joint_requirements.items()
    ):
        raise SafeRunError("material_strata_coverage_failed")

    coverage: list[DimensionCoverage] = []
    for dimension in REQUIRED_REVIEW_DIMENSIONS:
        source = (
            SOURCE_MANIFEST_VERSION
            if dimension in SOURCE_MANIFEST_DIMENSIONS and source_manifest_available
            else "full_run_terminal_records"
        )
        if dimension in SOURCE_MANIFEST_DIMENSIONS and not source_manifest_available:
            coverage.append(
                DimensionCoverage(
                    dimension,
                    "unavailable_source_manifest",
                    0,
                    0,
                    "unavailable_source_manifest",
                    "source_manifest_not_attached",
                )
            )
            continue
        observed = sorted(value for key, value in token_members if key == dimension)
        coverage_values = sorted(
            set(observed) | set(REVIEW_DIMENSION_EXPECTED_VALUES.get(dimension, ()))
        )
        if not coverage_values:
            coverage.append(
                DimensionCoverage(
                    dimension,
                    "not_represented",
                    0,
                    0,
                    "not_represented",
                    source,
                )
            )
            continue
        for value in coverage_values:
            population = len(token_members.get((dimension, value), ()))
            selected_count = selected_token_counts.get((dimension, value), 0)
            disposition = (
                "not_represented"
                if population == 0
                else "covered"
                if population >= MATERIAL_STRATUM_MIN_STUDIES
                else "represented_nonmaterial"
            )
            coverage.append(
                DimensionCoverage(
                    dimension,
                    value,
                    population,
                    selected_count,
                    disposition,
                    source,
                )
            )

    census = tuple(
        StratumCensus(
            stratum=stratum,
            population_studies=len(members),
            selected_studies=selected_joint_counts[stratum],
            material=len(members) >= MATERIAL_STRATUM_MIN_STUDIES,
        )
        for stratum, members in sorted(joint_members.items())
    )
    return SelectionPlan(
        studies=tuple(SelectedStudy(uid, by_uid[uid].stratum) for uid in selected_order),
        census=census,
        coverage=tuple(coverage),
    )


def _case_index_cohort_sha256(studies: Sequence[Mapping[str, object]]) -> str:
    ordered = sorted(studies, key=lambda item: cast(int, item["case_ordinal"]))
    payload = {
        "domain": "rsna-knee-dicom-qa-cohort-v2",
        "selection_version": QA_COHORT_SELECTION_VERSION,
        "studies": [
            {
                "study_uid": study["study_uid"],
                "selection_stratum": study["selection_stratum"],
                "eligible_series_uids": sorted(
                    str(series["series_uid"])
                    for series in cast(Sequence[Mapping[str, object]], study["series"])
                    if series.get("model_eligible") is True
                ),
            }
            for study in ordered
        ],
    }
    return _sha256_bytes(_canonical_json_bytes(payload))


def _selected_replay_terminal(
    base_terminal: str, evidence: Mapping[str, object]
) -> tuple[str, dict[str, str | None] | None]:
    if set(evidence) != {
        "terminal_state",
        "preprocessing_failure",
        "source_failure",
        "quality",
    }:
        raise SafeRunError("full_cohort_replay_mismatch")
    terminal = evidence.get("terminal_state")
    failure = evidence.get("preprocessing_failure")
    if base_terminal == "preprocessing_candidate":
        if terminal not in {"model_eligible", "preprocessing_blocked"}:
            raise SafeRunError("full_cohort_replay_mismatch")
    elif terminal != base_terminal:
        raise SafeRunError("full_cohort_replay_mismatch")
    if terminal == "preprocessing_blocked":
        if not isinstance(failure, dict) or set(failure) != {
            "issue",
            "stage",
            "root_cause",
            "exception_type",
        }:
            raise SafeRunError("full_cohort_replay_mismatch")
        return terminal, cast(dict[str, str | None], failure)
    if failure is not None or not isinstance(terminal, str):
        raise SafeRunError("full_cohort_replay_mismatch")
    return terminal, None


def _cpu_seconds() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return float(usage.ru_utime + usage.ru_stime)


def _peak_rss_bytes() -> int:
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return peak if sys.platform == "darwin" else peak * 1024


def _run_full_dataset_pass(
    *,
    competition_root: Path,
    rows: Sequence[SeriesRow],
    private_manifest_path: Path,
    run_config: Mapping[str, Any],
    config: Any,
    versions: Any,
    pipeline_module: Any,
    slots_module: Any,
    workers: int,
    deadline_at: float | None,
    source_manifest_facts: Mapping[str, Mapping[str, tuple[str, ...]]] | None = None,
    source_manifest_identity: Mapping[str, str] | None = None,
    source_manifest_reconciliation: SourceManifestReconciliation | None = None,
    selection_target: int = TARGET_STUDIES,
    selection_maximum: int = MAX_TARGET_STUDIES,
    selection_minimum_eligible: int = MINIMUM_ELIGIBLE_STUDIES,
) -> tuple[
    dict[str, object],
    tuple[RepresentativeSeriesInput, ...],
    Any,
    SelectionPlan,
    dict[tuple[str, str], dict[str, object]],
]:
    """Process every training series once and persist a deterministic private manifest."""

    grouped: dict[str, list[SeriesRow]] = defaultdict(list)
    for row in rows:
        grouped[row.study_uid].append(row)
    if not grouped:
        raise SafeRunError("full_run_population_empty")
    source_parts = (
        source_manifest_facts,
        source_manifest_identity,
        source_manifest_reconciliation,
    )
    if (
        any(part is None for part in source_parts) != all(part is None for part in source_parts)
        or (source_manifest_facts is not None and set(source_manifest_facts) != set(grouped))
        or (
            source_manifest_reconciliation is not None
            and source_manifest_reconciliation.expected_series_count != len(rows)
        )
    ):
        raise SafeRunError("source_manifest_population_mismatch")
    private_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if private_manifest_path.exists() or private_manifest_path.is_symlink():
        raise SafeRunError("private_full_run_manifest_exists")
    descriptor = os.open(private_manifest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    stream = os.fdopen(descriptor, "wb")
    digest = hashlib.sha256()
    files_total = 0
    source_files_observed = 0
    series_terminal = 0
    model_eligible_series = 0
    logical_cache_bytes = 0
    peak_cache_bytes = 0
    peak_disk_bytes = 0
    timings = {
        "decode_seconds": 0.0,
        "ordering_seconds": 0.0,
        "slot_assignment_seconds": 0.0,
        "preprocessing_seconds": 0.0,
        "cache_generation_seconds": 0.0,
        "qa_generation_seconds": 0.0,
    }
    terminal_counts: dict[str, int] = defaultdict(int)
    resolution_counts: dict[str, int] = defaultdict(int)
    file_terminal_counts: dict[str, int] = defaultdict(int)
    file_resolution_counts: dict[str, int] = defaultdict(int)
    file_disposition_counts: dict[str, int] = defaultdict(int)
    unresolved_stage_counts: dict[str, int] = defaultdict(int)
    unresolved_issue_counts: dict[str, int] = defaultdict(int)
    cohort_studies: list[CohortStudy] = []
    replay_evidence: dict[tuple[str, str], dict[str, object]] = {}
    eligible_profile_rows: list[tuple[int, str, SeriesRow]] = []
    first_provenance: Any | None = None
    started = time.perf_counter()
    cpu_started = _cpu_seconds()
    peak_rss_started = _peak_rss_bytes()
    cache_root = Path(tempfile.mkdtemp(prefix=".full-run-cache-", dir=private_manifest_path.parent))

    def write_record(value: object) -> None:
        payload = _canonical_json_bytes(value)
        stream.write(payload)
        digest.update(payload)
        if stream.tell() > PRIVATE_OUTPUT_POLICY["private_full_run_manifest.jsonl"]:
            raise SafeRunError("private_full_run_manifest_too_large")

    try:
        write_record(
            {
                "schema_version": 1,
                "artifact_type": "private-dicom-full-run-manifest",
                "record_type": "header",
                "output_policy": {
                    "classification": "private_remote_only",
                    "filename": "private_full_run_manifest.jsonl",
                    "format": "canonical-json-lines-v1",
                    "maximum_bytes": PRIVATE_OUTPUT_POLICY["private_full_run_manifest.jsonl"],
                    "case_data": "permitted_private_only",
                    "dynamic_measurements": "excluded",
                },
                "provenance": {
                    "git_commit": run_config["code_commit"],
                    "bundle_sha256": run_config["bundle_sha256"],
                    "source_manifest_version": versions.source_manifest_version,
                    "preprocessing_version": versions.preprocessing_version,
                    "preprocessing_configuration_hash": pipeline_module.preprocessing_config_hash(
                        config
                    ),
                    "source_manifest_identity": (
                        dict(sorted(source_manifest_identity.items()))
                        if source_manifest_identity is not None
                        else {"status": "unavailable_source_manifest"}
                    ),
                },
            }
        )
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="dicom-series") as executor:
            for study_ordinal, study_uid in enumerate(sorted(grouped)):
                _check_deadline(deadline_at)
                study_rows = sorted(grouped[study_uid], key=lambda item: item.series_uid)
                futures = [
                    executor.submit(
                        _full_series_state,
                        competition_root=competition_root,
                        row=row,
                        pipeline_module=pipeline_module,
                        slots_module=slots_module,
                        config=config,
                        versions=versions,
                        cache_root=cache_root,
                        deadline_at=deadline_at,
                    )
                    for row in study_rows
                ]
                states = [future.result() for future in futures]
                study_cache_bytes = 0
                for state in states:
                    state_record = cast(Mapping[str, Any], state["record"])
                    state_cache = state_record.get("cache")
                    if isinstance(state_cache, Mapping):
                        study_cache_bytes += int(cast(Any, state_cache["bytes"]))
                peak_cache_bytes = max(peak_cache_bytes, study_cache_bytes)
                slot_started = time.perf_counter()
                assignment = slots_module.assign_series_slots(
                    tuple(state["candidate"] for state in states)
                )
                timings["slot_assignment_seconds"] += time.perf_counter() - slot_started
                primary_slots = {
                    selection.primary.candidate.series_key: selection.slot.value
                    for selection in assignment.primary_slots
                    if selection.primary is not None
                }
                additional = {
                    item.candidate.series_key: tuple(reason.value for reason in item.reasons)
                    for item in assignment.additional_or_duplicate
                }
                records: list[dict[str, object]] = []
                for state in states:
                    if source_manifest_reconciliation is not None:
                        raw_checksums = state.get("file_raw_checksums")
                        if not isinstance(raw_checksums, tuple) or any(
                            value is not None and not isinstance(value, str)
                            for value in raw_checksums
                        ):
                            raise SafeRunError("source_manifest_population_mismatch")
                        source_files_observed += _reconcile_source_manifest_series_files(
                            source_manifest_reconciliation,
                            competition_root=competition_root,
                            row=cast(SeriesRow, state["row"]),
                            paths=cast(Sequence[Path], state["paths"]),
                            raw_checksums=cast(Sequence[str | None], raw_checksums),
                            deadline_at=deadline_at,
                        )
                    record = cast(dict[str, object], state["record"])
                    candidate = state["candidate"]
                    record["slot"] = primary_slots.get(
                        candidate.series_key, "additional_or_duplicate"
                    )
                    record["retention_reasons"] = list(additional.get(candidate.series_key, ()))
                    records.append(record)
                    series_files = int(cast(Any, record["files"]))
                    file_records = record.get("file_records")
                    if not isinstance(file_records, list) or len(file_records) != series_files:
                        raise SafeRunError("full_run_file_reconciliation_failed")
                    for file_ordinal, file_record in enumerate(file_records):
                        if (
                            not isinstance(file_record, Mapping)
                            or type(file_record.get("file_ordinal")) is not int
                            or file_record["file_ordinal"] != file_ordinal
                            or file_record.get("decode_state")
                            not in {"pass", "failed", "not_attempted"}
                            or not isinstance(file_record.get("terminal_state"), str)
                            or not isinstance(file_record.get("resolution_state"), str)
                            or not isinstance(file_record.get("disposition"), str)
                        ):
                            raise SafeRunError("full_run_file_reconciliation_failed")
                        file_terminal_counts[str(file_record["terminal_state"])] += 1
                        file_resolution_counts[str(file_record["resolution_state"])] += 1
                        file_disposition_counts[str(file_record["disposition"])] += 1
                    files_total += series_files
                    series_terminal += 1
                    terminal = str(record["terminal_state"])
                    terminal_counts[terminal] += 1
                    resolution = str(record["resolution_state"])
                    resolution_counts[resolution] += 1
                    replay_key = (study_uid, cast(SeriesRow, state["row"]).series_uid)
                    preprocessing_failure = record.get("preprocessing_failure")
                    source_failure = record.get("source_failure")
                    if (
                        replay_key in replay_evidence
                        or (terminal == "preprocessing_blocked")
                        != isinstance(preprocessing_failure, Mapping)
                        or (terminal == "source_access_blocked") != isinstance(source_failure, str)
                    ):
                        raise SafeRunError("full_run_replay_evidence_invalid")
                    replay_evidence[replay_key] = {
                        "terminal_state": terminal,
                        "preprocessing_failure": preprocessing_failure,
                        "source_failure": source_failure,
                        "quality": state["quality"],
                    }
                    if resolution == "unresolved_blocker":
                        unresolved_stage_counts[terminal] += 1
                        failures = [
                            record.get("source_failure"),
                            *cast(Sequence[Mapping[str, object]], record["decode_failures"]),
                            record.get("ordering_failure"),
                            record.get("preprocessing_failure"),
                        ]
                        for failure in failures:
                            if isinstance(failure, str):
                                unresolved_issue_counts[failure] += 1
                            elif isinstance(failure, Mapping):
                                unresolved_issue_counts[
                                    str(failure.get("issue", "unspecified"))
                                ] += 1
                    cache = record["cache"]
                    if isinstance(cache, dict):
                        size = int(cache["bytes"])
                        logical_cache_bytes += size
                        model_eligible_series += 1
                        profile_row = cast(SeriesRow, state["row"])
                        eligible_profile_rows.append(
                            (
                                int(cast(Any, record["files"])),
                                hashlib.sha256(profile_row.series_uid.encode("ascii")).hexdigest(),
                                profile_row,
                            )
                        )
                        if first_provenance is None:
                            first_provenance = state["provenance"]
                    for key in timings:
                        if key not in {"slot_assignment_seconds", "qa_generation_seconds"}:
                            state_timings = cast(Mapping[str, Any], state["timings"])
                            timings[key] += float(state_timings[key])
                cohort_studies.append(
                    _cohort_study(
                        study_uid,
                        states,
                        assignment.missing_mask,
                        (
                            source_manifest_facts.get(study_uid)
                            if source_manifest_facts is not None
                            else None
                        ),
                    )
                )
                write_record(
                    {
                        "record_type": "study",
                        "study_ordinal": study_ordinal,
                        "study_uid": study_uid,
                        "missing_series_mask": list(assignment.missing_mask),
                        "series": records,
                    }
                )
                peak_disk_bytes = max(peak_disk_bytes, stream.tell() + study_cache_bytes)
                for state in states:
                    cache_path = state.get("cache_path")
                    if isinstance(cache_path, Path):
                        cache_path.unlink(missing_ok=True)
        if series_terminal != len(rows):
            raise SafeRunError("full_run_series_reconciliation_failed")
        if (
            source_manifest_reconciliation is not None
            and source_files_observed != source_manifest_reconciliation.expected_file_count
        ):
            raise SafeRunError("source_manifest_population_mismatch")
        if len(replay_evidence) != series_terminal:
            raise SafeRunError("full_run_replay_evidence_invalid")
        if (
            sum(terminal_counts.values()) != series_terminal
            or sum(resolution_counts.values()) != series_terminal
        ):
            raise SafeRunError("full_run_terminal_reconciliation_failed")
        if (
            sum(file_terminal_counts.values()) != files_total
            or sum(file_resolution_counts.values()) != files_total
            or sum(file_disposition_counts.values()) != files_total
        ):
            raise SafeRunError("full_run_file_terminal_reconciliation_failed")
        write_record(
            {
                "record_type": "footer",
                "studies": len(grouped),
                "series": series_terminal,
                "files": files_total,
                "terminal_counts": dict(sorted(terminal_counts.items())),
                "resolution_counts": dict(sorted(resolution_counts.items())),
                "file_terminal_counts": dict(sorted(file_terminal_counts.items())),
                "file_resolution_counts": dict(sorted(file_resolution_counts.items())),
                "file_disposition_counts": dict(sorted(file_disposition_counts.items())),
                "unresolved_blockers": resolution_counts.get("unresolved_blocker", 0),
                "logical_cache_bytes": logical_cache_bytes,
            }
        )
        stream.flush()
        os.fsync(stream.fileno())
    except BaseException:
        stream.close()
        private_manifest_path.unlink(missing_ok=True)
        raise
    finally:
        if not stream.closed:
            stream.close()
        shutil.rmtree(cache_root, ignore_errors=True)
    wall_seconds = time.perf_counter() - started
    cpu_seconds = max(0.0, _cpu_seconds() - cpu_started)
    peak_rss_finished = _peak_rss_bytes()
    timings["total_seconds"] = wall_seconds
    if _sha256_file(private_manifest_path) != digest.hexdigest():
        raise SafeRunError("private_full_run_manifest_hash_mismatch")
    if not eligible_profile_rows or first_provenance is None:
        raise SafeRunError("full_run_has_no_model_eligible_series")
    ordered_profiles = sorted(eligible_profile_rows, key=lambda item: (item[0], item[1]))
    requested_profiles = (
        ("small", 0),
        ("median", (len(ordered_profiles) - 1) // 2),
        ("large", len(ordered_profiles) - 1),
    )
    representatives: list[RepresentativeSeriesInput] = []
    represented_rows: set[tuple[str, str]] = set()
    for profile, index in requested_profiles:
        slice_count, _, profile_row = ordered_profiles[index]
        identity = (profile_row.study_uid, profile_row.series_uid)
        if identity in represented_rows:
            continue
        represented_rows.add(identity)
        profile_paths = _series_files(competition_root, profile_row)
        if len(profile_paths) != slice_count:
            raise SafeRunError("representative_profile_source_changed")
        representatives.append(
            RepresentativeSeriesInput(
                profile=profile,
                slice_count=slice_count,
                paths=profile_paths,
            )
        )
    selection_plan = _select_after_full_pass(
        cohort_studies,
        source_manifest_available=source_manifest_facts is not None,
        target=selection_target,
        maximum=selection_maximum,
        minimum_eligible=selection_minimum_eligible,
    )
    cohort_by_uid = {study.study_uid: study for study in cohort_studies}
    cohort_payload = _canonical_json_bytes(
        {
            "domain": "rsna-knee-dicom-qa-cohort-v2",
            "selection_version": QA_COHORT_SELECTION_VERSION,
            "studies": [
                {
                    "study_uid": item.study_uid,
                    "selection_stratum": list(item.stratum),
                    "eligible_series_uids": list(
                        cohort_by_uid[item.study_uid].eligible_series_uids
                    ),
                }
                for item in selection_plan.studies
            ],
        }
    )
    cpu_capacity = max(1, min(workers, os.cpu_count() or workers))
    metrics: dict[str, object] = {
        "schema_version": 1,
        "artifact_type": "private-dicom-full-run-metrics",
        "output_policy": {
            "private_full_run_manifest.jsonl": {
                "classification": "private_remote_only",
                "format": "canonical-json-lines-v1",
                "maximum_bytes": PRIVATE_OUTPUT_POLICY["private_full_run_manifest.jsonl"],
                "case_data": "permitted_private_only",
                "timings": "excluded",
            },
            "private_full_run_metrics.json": {
                "classification": "private_remote_only",
                "format": "canonical-json-v1",
                "maximum_bytes": PRIVATE_OUTPUT_POLICY["private_full_run_metrics.json"],
                "case_data": "excluded",
                "timings": "aggregate_only",
            },
        },
        "input_identity": (
            dict(sorted(source_manifest_identity.items()))
            if source_manifest_identity is not None
            else {"status": "unavailable_source_manifest"}
        ),
        "studies_processed": len(grouped),
        "series_processed": series_terminal,
        "files_processed": files_total,
        "terminal_counts": dict(sorted(terminal_counts.items())),
        "resolution_counts": dict(sorted(resolution_counts.items())),
        "integrity_gate": {
            "terminal_reconciled": True,
            "unresolved_blocker_count": resolution_counts.get("unresolved_blocker", 0),
            "unresolved_stage_counts": dict(sorted(unresolved_stage_counts.items())),
            "unresolved_issue_counts": dict(sorted(unresolved_issue_counts.items())),
            "status": ("pass" if resolution_counts.get("unresolved_blocker", 0) == 0 else "block"),
        },
        "model_eligible_series": model_eligible_series,
        "timings_seconds": timings,
        "total_wall_seconds": wall_seconds,
        "process_cpu_seconds": cpu_seconds,
        "cpu_capacity_threads": cpu_capacity,
        "cpu_utilization_percent": min(
            100.0, 100.0 * cpu_seconds / max(wall_seconds * cpu_capacity, 1e-12)
        ),
        "process_peak_rss_bytes": peak_rss_finished,
        "process_peak_rss_increase_bytes": max(0, peak_rss_finished - peak_rss_started),
        "process_peak_rss_observation": {
            "method": "getrusage_process_lifetime_high_water_mark",
            "scope": "process_lifetime_not_interval_attribution",
            "platform_unit_normalized_to_bytes": True,
        },
        "logical_cache_bytes": logical_cache_bytes,
        "peak_ephemeral_cache_bytes": peak_cache_bytes,
        "manifest_bytes": private_manifest_path.stat().st_size,
        "manifest_sha256": digest.hexdigest(),
        "peak_private_working_disk_bytes": max(
            peak_disk_bytes, private_manifest_path.stat().st_size
        ),
        "peak_private_working_disk_observation": (
            "manifest_bytes_written_plus_concurrent_study_cache_files_before_deletion"
        ),
        "throughput": {
            "files_per_second": files_total / max(wall_seconds, 1e-12),
            "series_per_second": series_terminal / max(wall_seconds, 1e-12),
            "studies_per_second": len(grouped) / max(wall_seconds, 1e-12),
        },
        "throughput_scope": "single_full_dataset_pass_excludes_post_pass_qa_replay",
        "qa_cohort_selection": {
            "selection_version": QA_COHORT_SELECTION_VERSION,
            "selected_studies": len(selection_plan.studies),
            "eligible_series": sum(
                cohort_by_uid[item.study_uid].eligible_series for item in selection_plan.studies
            ),
            "cohort_sha256": _sha256_bytes(cohort_payload),
            "source_manifest_gate": (
                "pass" if source_manifest_facts is not None else "unavailable_source_manifest"
            ),
            "coverage": [asdict(item) for item in selection_plan.coverage],
        },
    }
    return metrics, tuple(representatives), first_provenance, selection_plan, replay_evidence


def _directory_records(root: Path) -> tuple[dict[str, object], ...]:
    try:
        files = sorted(path for path in root.iterdir() if path.is_file() and not path.is_symlink())
        if len(files) > PRIVATE_REVIEW_MAX_FILES or any(path.is_dir() for path in root.iterdir()):
            raise SafeRunError("private_artifact_inventory_invalid")
    except OSError as error:
        raise SafeRunError("private_artifact_inventory_invalid") from error
    records: list[dict[str, object]] = []
    total = 0
    for path in files:
        size = path.stat().st_size
        if not re.fullmatch(PRIVATE_REVIEW_PATTERN, path.name) or not (
            0 < size <= PRIVATE_REVIEW_MAX_FILE_BYTES
        ):
            raise SafeRunError("private_artifact_inventory_invalid")
        total += size
        records.append({"name": path.name, "bytes": size, "sha256": _sha256_file(path)})
    if not records or total > PRIVATE_REVIEW_MAX_TOTAL_BYTES:
        raise SafeRunError("private_artifact_inventory_invalid")
    return tuple(records)


def _write_new(path: Path, payload: bytes, *, maximum: int) -> None:
    if not payload or len(payload) > maximum:
        raise SafeRunError("output_size_invalid")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(payload)
        os.chmod(path, 0o600)
    except OSError as error:
        raise SafeRunError("output_write_failed") from error


def _rounded_benchmark(report: Any) -> dict[str, object]:
    def timing(value: Any) -> dict[str, float]:
        return {
            "minimum_seconds": round(float(value.minimum_seconds), 6),
            "median_seconds": round(float(value.median_seconds), 6),
            "maximum_seconds": round(float(value.maximum_seconds), 6),
        }

    compatibility = report.kaggle_compatibility
    return {
        "iterations": report.iterations,
        "decode_time": timing(report.decode_time),
        "preprocessing_time": timing(report.preprocessing_time),
        "representative_tensor_cache_mib_ceiling": max(
            1, math.ceil(report.representative_tensor_cache_bytes / 1024**2)
        ),
        "process_peak_rss_mib_ceiling": max(1, math.ceil(report.process_peak_rss_bytes / 1024**2)),
        "peak_rss_increase_mib_ceiling": math.ceil(report.peak_rss_increase_bytes / 1024**2),
        "cpu_parallelism": [
            {
                "workers": item.workers,
                "tasks": item.tasks,
                "wall_seconds": round(float(item.wall_seconds), 6),
                "tasks_per_second": round(float(item.tasks_per_second), 6),
                "speedup_vs_one_worker": round(float(item.speedup_vs_one_worker), 6),
            }
            for item in report.cpu_parallelism
        ],
        "kaggle_compatibility": {
            "python_version": compatibility.python_version,
            "platform_system": compatibility.platform_system,
            "platform_machine": compatibility.platform_machine,
            "cpu_count": compatibility.cpu_count,
            "numpy_version": compatibility.numpy_version,
            "pydicom_version": compatibility.pydicom_version,
            "python_supported": compatibility.python_supported,
            "linux_runtime_observed": compatibility.linux_runtime_observed,
            "offline_bundle_verified": compatibility.offline_bundle_verified,
            "kaggle_runtime_verified": compatibility.kaggle_runtime_verified,
            "accelerator": compatibility.accelerator,
            "horizontal_flip": compatibility.horizontal_flip,
            "through_plane_resampling": compatibility.through_plane_resampling,
        },
        "deterministic_replay": report.deterministic_replay,
    }


def _validate_performance(
    value: object, *, expected_inference_limit_seconds: int | None = None
) -> None:
    if not isinstance(value, dict) or set(value) != {
        "runtime_seconds",
        "phase_seconds",
        "resources",
        "cpu",
        "throughput",
        "representative_cpu_scaling",
        "inference_runtime_budget",
        "determinism_status",
    }:
        raise SafeRunError("sanitized_performance_invalid")

    runtime = value.get("runtime_seconds")
    phases = value.get("phase_seconds")
    resources = value.get("resources")
    cpu = value.get("cpu")
    throughput = value.get("throughput")
    scaling = value.get("representative_cpu_scaling")
    budget = value.get("inference_runtime_budget")
    if (
        not isinstance(runtime, dict)
        or set(runtime) != {"total_run_wall_seconds", "full_dataset_pipeline_wall_seconds"}
        or not isinstance(phases, dict)
        or set(phases)
        != {
            "decode_accumulated_seconds",
            "preprocessing_accumulated_seconds",
            "slot_assignment_seconds",
            "qa_generation_seconds",
            "cache_generation_seconds",
        }
        or not isinstance(resources, dict)
        or set(resources)
        != {
            "process_peak_rss_mib_ceiling",
            "logical_cache_power_of_two_mib_ceiling",
            "peak_ephemeral_cache_power_of_two_mib_ceiling",
            "peak_private_working_disk_power_of_two_mib_ceiling",
        }
        or not isinstance(cpu, dict)
        or set(cpu) != {"capacity_threads", "average_utilization_percent"}
        or not isinstance(throughput, dict)
        or set(throughput)
        != {
            "scope",
            "disclosure_policy",
            "decode_files_per_second_token",
            "preprocessing_series_per_second_token",
            "end_to_end_files_per_second_token",
            "end_to_end_series_per_second_token",
            "end_to_end_studies_per_second_token",
        }
        or not isinstance(scaling, dict)
        or set(scaling)
        != {
            "selection_method",
            "requested_workers",
            "available_workers",
            "unavailable_workers",
            "profiles",
        }
        or not isinstance(budget, dict)
        or set(budget)
        != {
            "limit_seconds",
            "limit_source",
            "measured_preprocessing_pipeline_wall_seconds",
            "remaining_after_preprocessing_seconds",
            "preprocessing_within_limit",
            "model_runtime_included",
            "model_viability_assessed",
            "scope",
        }
    ):
        raise SafeRunError("sanitized_performance_invalid")

    def finite_number(candidate: object, *, positive: bool) -> bool:
        return (
            not isinstance(candidate, bool)
            and isinstance(candidate, (int, float))
            and math.isfinite(float(candidate))
            and (candidate > 0 if positive else candidate >= 0)
        )

    if (
        any(not finite_number(item, positive=True) for item in runtime.values())
        or runtime["total_run_wall_seconds"] < runtime["full_dataset_pipeline_wall_seconds"]
        or any(not finite_number(item, positive=False) for item in phases.values())
        or any(
            isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= 1_048_576
            for item in resources.values()
        )
        or any(
            cast(int, resources[name]) & (cast(int, resources[name]) - 1)
            for name in (
                "logical_cache_power_of_two_mib_ceiling",
                "peak_ephemeral_cache_power_of_two_mib_ceiling",
                "peak_private_working_disk_power_of_two_mib_ceiling",
            )
        )
        or isinstance(cpu.get("capacity_threads"), bool)
        or not isinstance(cpu.get("capacity_threads"), int)
        or not 1 <= cast(int, cpu["capacity_threads"]) <= 4096
        or not finite_number(cpu.get("average_utilization_percent"), positive=False)
        or float(cpu["average_utilization_percent"]) > 100.0
        or throughput.get("scope")
        != "complete_private_run_including_post_pass_qa_and_representative_benchmark"
        or throughput.get("disclosure_policy") != "fixed_order_of_magnitude_rate_buckets_v1"
        or any(
            throughput.get(name) not in {item[0] for item in THROUGHPUT_BUCKETS}
            for name in (
                "decode_files_per_second_token",
                "preprocessing_series_per_second_token",
                "end_to_end_files_per_second_token",
                "end_to_end_series_per_second_token",
                "end_to_end_studies_per_second_token",
            )
        )
    ):
        raise SafeRunError("sanitized_performance_invalid")

    requested = scaling.get("requested_workers")
    available = scaling.get("available_workers")
    unavailable = scaling.get("unavailable_workers")
    profiles = scaling.get("profiles")
    if (
        scaling.get("selection_method") != "model_eligible_slice_count_rank_small_median_large_v1"
        or requested != list(REPRESENTATIVE_WORKER_COUNTS)
        or not isinstance(available, list)
        or not isinstance(unavailable, list)
        or any(isinstance(item, bool) or not isinstance(item, int) for item in available)
        or any(isinstance(item, bool) or not isinstance(item, int) for item in unavailable)
        or sorted(available) != available
        or sorted(unavailable) != unavailable
        or set(available).intersection(unavailable)
        or sorted([*available, *unavailable]) != list(REPRESENTATIVE_WORKER_COUNTS)
        or available != list(REPRESENTATIVE_WORKER_COUNTS[: len(available)])
        or unavailable != list(REPRESENTATIVE_WORKER_COUNTS[len(available) :])
        or 1 not in available
        or any(item > cast(int, cpu["capacity_threads"]) for item in available)
        or not isinstance(profiles, list)
        or len(profiles) != 3
    ):
        raise SafeRunError("sanitized_performance_invalid")
    expected_profiles = ("small", "median", "large")
    for profile, expected_profile in zip(profiles, expected_profiles, strict=True):
        if (
            not isinstance(profile, dict)
            or set(profile) != {"profile", "iterations", "cpu_parallelism"}
            or profile.get("profile") != expected_profile
            or isinstance(profile.get("iterations"), bool)
            or not isinstance(profile.get("iterations"), int)
            or profile["iterations"] != (3 if expected_profile == "median" else 1)
            or not isinstance(profile.get("cpu_parallelism"), list)
            or any(
                not isinstance(item, dict)
                for item in cast(list[object], profile.get("cpu_parallelism"))
            )
            or [item.get("workers") for item in profile["cpu_parallelism"]] != available
        ):
            raise SafeRunError("sanitized_performance_invalid")
        for item in profile["cpu_parallelism"]:
            if (
                not isinstance(item, dict)
                or set(item)
                != {
                    "workers",
                    "tasks",
                    "wall_seconds",
                    "tasks_per_second",
                    "speedup_vs_one_worker",
                }
                or isinstance(item.get("tasks"), bool)
                or not isinstance(item.get("tasks"), int)
                or not 1 <= cast(int, item["tasks"]) <= 10_000
                or any(
                    not finite_number(item.get(name), positive=True)
                    for name in (
                        "wall_seconds",
                        "tasks_per_second",
                        "speedup_vs_one_worker",
                    )
                )
            ):
                raise SafeRunError("sanitized_performance_invalid")

    limit = budget.get("limit_seconds")
    measured = budget.get("measured_preprocessing_pipeline_wall_seconds")
    remaining = budget.get("remaining_after_preprocessing_seconds")
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 86_400
        or (
            expected_inference_limit_seconds is not None
            and limit != expected_inference_limit_seconds
        )
        or budget.get("limit_source") != "bundled_competition_contract"
        or measured != runtime["full_dataset_pipeline_wall_seconds"]
        or not finite_number(measured, positive=True)
        or not finite_number(remaining, positive=False)
    ):
        raise SafeRunError("sanitized_performance_invalid")
    measured_number = float(cast(int | float, measured))
    remaining_number = float(cast(int | float, remaining))
    if (
        remaining_number != round(max(0.0, limit - measured_number), 6)
        or budget.get("preprocessing_within_limit") is not (measured_number <= limit)
        or budget.get("model_runtime_included") is not False
        or budget.get("model_viability_assessed") is not False
        or budget.get("scope") != "measured_preprocessing_only"
        or value.get("determinism_status") != "pending_independent_run_comparison"
    ):
        raise SafeRunError("sanitized_performance_invalid")


def _sanitized_performance(
    full_run_metrics: Mapping[str, object], inference_limit_seconds: int
) -> dict[str, object]:
    def rounded(value: object, *, positive: bool = False) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or (value <= 0 if positive else value < 0)
        ):
            raise SafeRunError("private_metrics_invalid")
        result = round(float(value), 6)
        if positive and result <= 0:
            raise SafeRunError("private_metrics_invalid")
        return result

    def mib_ceiling(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SafeRunError("private_metrics_invalid")
        return max(1, math.ceil(value / 1024**2))

    def power_of_two_mib_ceiling(value: object) -> int:
        mib = mib_ceiling(value)
        return 1 << mib.bit_length()

    def throughput_token(value: object) -> str:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value <= 0
        ):
            raise SafeRunError("private_metrics_invalid")
        number = float(value)
        return next(token for token, lower, upper in THROUGHPUT_BUCKETS if lower <= number < upper)

    try:
        timings = cast(Mapping[str, object], full_run_metrics["timings_seconds"])
        end_to_end = cast(Mapping[str, object], full_run_metrics["end_to_end_throughput"])
        representative = cast(Mapping[str, object], full_run_metrics["representative_scaling"])
        profiles = cast(Sequence[Mapping[str, object]], representative["profiles"])
        full_dataset_seconds = rounded(full_run_metrics["full_dataset_wall_seconds"], positive=True)
        total_seconds = rounded(full_run_metrics["total_wall_seconds"], positive=True)
        decode_seconds = rounded(timings["decode_seconds"], positive=True)
        preprocessing_seconds = rounded(timings["preprocessing_seconds"], positive=True)
        performance: dict[str, object] = {
            "runtime_seconds": {
                "total_run_wall_seconds": total_seconds,
                "full_dataset_pipeline_wall_seconds": full_dataset_seconds,
            },
            "phase_seconds": {
                "decode_accumulated_seconds": decode_seconds,
                "preprocessing_accumulated_seconds": preprocessing_seconds,
                "slot_assignment_seconds": rounded(timings["slot_assignment_seconds"]),
                "qa_generation_seconds": rounded(timings["qa_generation_seconds"]),
                "cache_generation_seconds": rounded(timings["cache_generation_seconds"]),
            },
            "resources": {
                "process_peak_rss_mib_ceiling": mib_ceiling(
                    full_run_metrics["process_peak_rss_bytes"]
                ),
                "logical_cache_power_of_two_mib_ceiling": power_of_two_mib_ceiling(
                    full_run_metrics["logical_cache_bytes"]
                ),
                "peak_ephemeral_cache_power_of_two_mib_ceiling": power_of_two_mib_ceiling(
                    full_run_metrics["peak_ephemeral_cache_bytes"]
                ),
                "peak_private_working_disk_power_of_two_mib_ceiling": power_of_two_mib_ceiling(
                    full_run_metrics["peak_private_working_disk_bytes"]
                ),
            },
            "cpu": {
                "capacity_threads": full_run_metrics["cpu_capacity_threads"],
                "average_utilization_percent": rounded(full_run_metrics["cpu_utilization_percent"]),
            },
            "throughput": {
                "scope": (
                    "complete_private_run_including_post_pass_qa_and_representative_benchmark"
                ),
                "disclosure_policy": "fixed_order_of_magnitude_rate_buckets_v1",
                "decode_files_per_second_token": throughput_token(
                    cast(int, full_run_metrics["files_processed"]) / decode_seconds
                ),
                "preprocessing_series_per_second_token": throughput_token(
                    cast(int, full_run_metrics["model_eligible_series"]) / preprocessing_seconds
                ),
                "end_to_end_files_per_second_token": throughput_token(
                    end_to_end["files_per_second"]
                ),
                "end_to_end_series_per_second_token": throughput_token(
                    end_to_end["series_per_second"]
                ),
                "end_to_end_studies_per_second_token": throughput_token(
                    end_to_end["studies_per_second"]
                ),
            },
            "representative_cpu_scaling": {
                "selection_method": representative["selection_method"],
                "requested_workers": representative["requested_worker_counts"],
                "available_workers": representative["available_worker_counts"],
                "unavailable_workers": representative["unavailable_worker_counts"],
                "profiles": [
                    {
                        "profile": profile["profile"],
                        "iterations": profile["iterations"],
                        "cpu_parallelism": profile["cpu_parallelism"],
                    }
                    for profile in profiles
                ],
            },
            "inference_runtime_budget": {
                "limit_seconds": inference_limit_seconds,
                "limit_source": "bundled_competition_contract",
                "measured_preprocessing_pipeline_wall_seconds": full_dataset_seconds,
                "remaining_after_preprocessing_seconds": round(
                    max(0.0, inference_limit_seconds - full_dataset_seconds), 6
                ),
                "preprocessing_within_limit": full_dataset_seconds <= inference_limit_seconds,
                "model_runtime_included": False,
                "model_viability_assessed": False,
                "scope": "measured_preprocessing_only",
            },
            "determinism_status": "pending_independent_run_comparison",
        }
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise SafeRunError("private_metrics_invalid") from error
    _validate_performance(performance, expected_inference_limit_seconds=inference_limit_seconds)
    return performance


def _render_benchmark(summary: Mapping[str, Any]) -> bytes:
    benchmark = cast(Mapping[str, Any], summary["benchmark"])
    performance = cast(Mapping[str, Any], summary["performance"])
    runtime = cast(Mapping[str, Any], performance["runtime_seconds"])
    phases = cast(Mapping[str, Any], performance["phase_seconds"])
    resources = cast(Mapping[str, Any], performance["resources"])
    cpu = cast(Mapping[str, Any], performance["cpu"])
    throughput = cast(Mapping[str, Any], performance["throughput"])
    scaling = cast(Mapping[str, Any], performance["representative_cpu_scaling"])
    scaling_profiles = cast(Sequence[Mapping[str, Any]], scaling["profiles"])
    budget = cast(Mapping[str, Any], performance["inference_runtime_budget"])
    provenance = cast(Mapping[str, Any], summary["provenance"])
    selection = cast(Mapping[str, Any], summary["selection"])
    pipeline = cast(Mapping[str, Any], summary["pipeline"])
    qa = cast(Mapping[str, Any], summary["qa"])
    decode = cast(Mapping[str, Any], benchmark["decode_time"])
    preprocessing = cast(Mapping[str, Any], benchmark["preprocessing_time"])
    compatibility = cast(Mapping[str, Any], benchmark["kaggle_compatibility"])
    workers = cast(Sequence[Mapping[str, Any]], benchmark["cpu_parallelism"])
    lines = [
        "# DICOM preprocessing performance report",
        "",
        "## Scope",
        "",
        "- environment: private Kaggle CPU",
        "- network: disabled",
        "- data disclosure: aggregate measurements only",
        "",
        "## Complete private run",
        "",
        f"- total run wall seconds: {runtime['total_run_wall_seconds']}",
        "- full-dataset preprocessing pipeline wall seconds: "
        f"{runtime['full_dataset_pipeline_wall_seconds']}",
        f"- decode accumulated seconds: {phases['decode_accumulated_seconds']}",
        f"- preprocessing accumulated seconds: {phases['preprocessing_accumulated_seconds']}",
        f"- series-slot assignment seconds: {phases['slot_assignment_seconds']}",
        f"- QA generation seconds: {phases['qa_generation_seconds']}",
        f"- cache generation seconds: {phases['cache_generation_seconds']}",
        "- phase timing note: accumulated worker phases may overlap",
        f"- process peak RSS MiB ceiling: {resources['process_peak_rss_mib_ceiling']}",
        "- logical cache power-of-two MiB ceiling: "
        f"{resources['logical_cache_power_of_two_mib_ceiling']}",
        "- peak ephemeral cache power-of-two MiB ceiling: "
        f"{resources['peak_ephemeral_cache_power_of_two_mib_ceiling']}",
        "- peak private working disk power-of-two MiB ceiling: "
        f"{resources['peak_private_working_disk_power_of_two_mib_ceiling']}",
        f"- CPU capacity threads: {cpu['capacity_threads']}",
        f"- average CPU utilization percent: {cpu['average_utilization_percent']}",
        f"- decode files per second token: {throughput['decode_files_per_second_token']}",
        "- preprocessing series per second token: "
        f"{throughput['preprocessing_series_per_second_token']}",
        f"- end-to-end files per second token: {throughput['end_to_end_files_per_second_token']}",
        f"- end-to-end series per second token: {throughput['end_to_end_series_per_second_token']}",
        "- end-to-end studies per second token: "
        f"{throughput['end_to_end_studies_per_second_token']}",
        f"- throughput disclosure policy: {throughput['disclosure_policy']}",
        f"- throughput scope: {throughput['scope']}",
        "",
        "## Representative CPU scaling",
        "",
        "- selection: small, median, and large model-eligible series by slice-count rank",
        "- requested workers: " + ",".join(str(item) for item in scaling["requested_workers"]),
        "- available workers: " + ",".join(str(item) for item in scaling["available_workers"]),
        "- unavailable workers: "
        + (",".join(str(item) for item in scaling["unavailable_workers"]) or "none"),
    ]
    for profile in scaling_profiles:
        lines.append(f"- {profile['profile']} profile iterations: {profile['iterations']}")
        lines.extend(
            f"  - workers {item['workers']}: tasks={item['tasks']}, "
            f"wall_seconds={item['wall_seconds']}, "
            f"tasks_per_second={item['tasks_per_second']}, "
            f"speedup={item['speedup_vs_one_worker']}"
            for item in cast(Sequence[Mapping[str, Any]], profile["cpu_parallelism"])
        )
    lines.extend(
        [
            "",
            "## Nine-hour runtime budget",
            "",
            f"- inference limit seconds: {budget['limit_seconds']}",
            "- measured preprocessing pipeline contribution seconds: "
            f"{budget['measured_preprocessing_pipeline_wall_seconds']}",
            "- remaining after measured preprocessing seconds: "
            f"{budget['remaining_after_preprocessing_seconds']}",
            "- preprocessing contribution within limit: "
            f"{str(budget['preprocessing_within_limit']).lower()}",
            f"- model runtime included: {str(budget['model_runtime_included']).lower()}",
            f"- model viability assessed: {str(budget['model_viability_assessed']).lower()}",
            "- interpretation: measured preprocessing contribution and arithmetic remainder only; "
            "no model-runtime viability claim",
            "",
            "## Completion gates",
            "",
            f"- independent full Run A/Run B determinism: {performance['determinism_status']}",
            f"- QA cohort study count token: {selection['selected_studies']}",
            f"- QA eligible-series count token: {qa['rendered_series']}",
            f"- all nine human checks: {qa['visual_review_status']}",
            f"- unresolved blocker token: {pipeline['unresolved_blockers']}",
            "",
            "## Public versions",
            "",
            f"- input/source manifest version: {provenance['source_manifest_version']}",
            f"- preprocessing pipeline version: {provenance['preprocessing_version']}",
            f"- QA cohort selection version: {provenance['qa_cohort_selection_version']}",
            "",
            "## Representative timing",
            "",
            f"- decode minimum seconds: {decode['minimum_seconds']}",
            f"- decode median seconds: {decode['median_seconds']}",
            f"- decode maximum seconds: {decode['maximum_seconds']}",
            f"- preprocessing minimum seconds: {preprocessing['minimum_seconds']}",
            f"- preprocessing median seconds: {preprocessing['median_seconds']}",
            f"- preprocessing maximum seconds: {preprocessing['maximum_seconds']}",
            "",
            "## Representative resources",
            "",
            "- representative tensor cache MiB ceiling: "
            f"{benchmark['representative_tensor_cache_mib_ceiling']}",
            f"- process peak RSS MiB ceiling: {benchmark['process_peak_rss_mib_ceiling']}",
            f"- peak RSS increase MiB ceiling: {benchmark['peak_rss_increase_mib_ceiling']}",
            "",
            "## Representative median-profile CPU parallelism",
            "",
        ]
    )
    lines.extend(
        f"- workers {item['workers']}: tasks={item['tasks']}, wall_seconds={item['wall_seconds']}, "
        f"tasks_per_second={item['tasks_per_second']}, speedup={item['speedup_vs_one_worker']}"
        for item in workers
    )
    lines.extend(
        [
            "",
            "## Kaggle compatibility",
            "",
            f"- Python: {compatibility['python_version']}",
            f"- platform: {compatibility['platform_system']} {compatibility['platform_machine']}",
            f"- CPU count: {compatibility['cpu_count']}",
            f"- NumPy: {compatibility['numpy_version']}",
            f"- pydicom: {compatibility['pydicom_version']}",
            f"- supported Python: {str(compatibility['python_supported']).lower()}",
            f"- Linux runtime observed: {str(compatibility['linux_runtime_observed']).lower()}",
            f"- offline bundle verified: {str(compatibility['offline_bundle_verified']).lower()}",
            f"- Kaggle runtime verified: {str(compatibility['kaggle_runtime_verified']).lower()}",
            f"- accelerator: {compatibility['accelerator']}",
            f"- horizontal flip: {str(compatibility['horizontal_flip']).lower()}",
            f"- through-plane resampling: {str(compatibility['through_plane_resampling']).lower()}",
            f"- deterministic replay: {str(benchmark['deterministic_replay']).lower()}",
            "",
        ]
    )
    return "\n".join(lines).encode("ascii")


def _scan_downloadable(payload: bytes, canary: str) -> None:
    if canary.encode("ascii") in payload or any(
        pattern.search(payload) for pattern in SENSITIVE_DOWNLOAD_BYTES
    ):
        raise SafeRunError("downloadable_privacy_invalid")


def _validate_summary(
    payload: bytes,
    run_config: Mapping[str, Any],
    *,
    expected_inference_limit_seconds: int | None = None,
) -> dict[str, Any]:
    summary = _json_object(payload, "sanitized_summary_invalid")
    if payload != _canonical_json_bytes(summary):
        raise SafeRunError("sanitized_summary_invalid")
    if set(summary) != {
        "schema_version",
        "artifact_type",
        "status",
        "provenance",
        "selection",
        "pipeline",
        "qa",
        "anatomical_safety",
        "privacy",
        "performance",
        "benchmark",
    }:
        raise SafeRunError("sanitized_summary_invalid")
    provenance = summary.get("provenance")
    status = summary.get("status")
    if (
        summary.get("schema_version") != 1
        or summary.get("artifact_type") != "dicom-qa-sanitized-aggregate"
        or status
        not in {
            "complete_pending_human_review",
            "blocked_unresolved_integrity",
        }
        or not isinstance(provenance, dict)
        or provenance.get("git_commit") != run_config.get("code_commit")
        or provenance.get("bundle_sha256") != run_config.get("bundle_sha256")
        or provenance.get("preprocessing_config_file_sha256")
        != cast(Mapping[str, Any], run_config["provenance"])["preprocessing_config_sha256"]
    ):
        raise SafeRunError("sanitized_summary_invalid")
    selection = summary.get("selection")
    pipeline_summary = summary.get("pipeline")
    qa = summary.get("qa")
    if (
        selection
        != {
            "source": "full_run_terminal_records_plus_authenticated_manifest_v2",
            "target_studies": TARGET_STUDIES,
            "maximum_studies": MAX_TARGET_STUDIES,
            "selected_studies": "between_120_and_240",
            "minimum_eligible_studies": MINIMUM_ELIGIBLE_STUDIES,
            "eligible_studies": "at_least_100",
            "stratified": True,
            "slice_count_stratified": True,
            "material_strata_covered": True,
            "bounded_deterministic_expansion": True,
            "selected_after_full_pass": True,
            "source_manifest_authenticated": True,
            "available_required_strata_dispositioned": True,
            "cohort_selection_version": QA_COHORT_SELECTION_VERSION,
        }
        or not isinstance(qa, dict)
        or qa.get("all_model_eligible_series_rendered") is not True
        or qa.get("repeat_render_byte_identical") is not True
        or qa.get("visual_review_status") != "pending_private_human_review"
    ):
        raise SafeRunError("sanitized_summary_invalid")
    if not isinstance(pipeline_summary, dict) or pipeline_summary not in (
        {
            "full_training_dataset_processed": True,
            "all_series_terminal": True,
            "integrity_gate": "pass",
            "unresolved_blockers": "zero",
            "series_slot_system_exercised": True,
            "model_eligible_series": "at_least_100",
            "failure_reporting": "fixed_codes_with_case_details_private",
            "all_preprocessing_provenance_private": True,
        },
        {
            "full_training_dataset_processed": True,
            "all_series_terminal": True,
            "integrity_gate": "block",
            "unresolved_blockers": "one_or_more",
            "series_slot_system_exercised": True,
            "model_eligible_series": "at_least_100",
            "failure_reporting": "fixed_codes_with_case_details_private",
            "all_preprocessing_provenance_private": True,
        },
    ):
        raise SafeRunError("sanitized_summary_invalid")
    if (status == "complete_pending_human_review") is not (
        pipeline_summary["integrity_gate"] == "pass"
    ):
        raise SafeRunError("sanitized_summary_invalid")
    if qa != {
        "rendered_series": "at_least_100",
        "all_model_eligible_series_rendered": True,
        "repeat_render_byte_identical": True,
        "full_cohort_replay_byte_identical": True,
        "review_files_present": True,
        "visual_review_status": "pending_private_human_review",
        "systematic_ordering_or_orientation_error": "not_evaluated_pending_human_review",
    }:
        raise SafeRunError("sanitized_summary_invalid")
    if set(provenance) != {
        "git_commit",
        "bundle_sha256",
        "runner_sha256",
        "review_finalizer_sha256",
        "preprocessing_config_file_sha256",
        "preprocessing_configuration_hash",
        "preprocessing_version",
        "source_manifest_version",
        "qa_cohort_selection_version",
        "dicom_library_versions",
    }:
        raise SafeRunError("sanitized_summary_invalid")
    for key in (
        "bundle_sha256",
        "runner_sha256",
        "review_finalizer_sha256",
        "preprocessing_config_file_sha256",
        "preprocessing_configuration_hash",
    ):
        value = provenance.get(key)
        if not isinstance(value, str) or not HEX_64.fullmatch(value):
            raise SafeRunError("sanitized_summary_invalid")
    if (
        provenance.get("source_manifest_version") != SOURCE_MANIFEST_VERSION
        or provenance.get("qa_cohort_selection_version") != QA_COHORT_SELECTION_VERSION
    ):
        raise SafeRunError("sanitized_summary_invalid")
    library_versions = provenance.get("dicom_library_versions")
    expected_packages = {
        "numpy",
        "pydicom",
        "pylibjpeg",
        "pylibjpeg-libjpeg",
        "pylibjpeg-openjpeg",
    }
    if (
        not isinstance(library_versions, list)
        or len(library_versions) != len(expected_packages)
        or {item.get("package") for item in library_versions if isinstance(item, dict)}
        != expected_packages
        or any(
            not isinstance(item, dict)
            or set(item) != {"package", "version"}
            or not isinstance(item.get("version"), str)
            or not re.fullmatch(r"[A-Za-z0-9.+_-]{1,50}", str(item.get("version")))
            for item in library_versions
        )
    ):
        raise SafeRunError("sanitized_summary_invalid")
    if summary.get("anatomical_safety") != run_config.get("anatomical_safety"):
        raise SafeRunError("sanitized_summary_invalid")
    if (
        provenance.get("review_finalizer_sha256")
        != cast(Mapping[str, Any], run_config["provenance"])["review_finalizer_sha256"]
    ):
        raise SafeRunError("sanitized_summary_invalid")
    _validate_performance(
        summary.get("performance"),
        expected_inference_limit_seconds=expected_inference_limit_seconds,
    )
    privacy = summary.get("privacy")
    if privacy != {
        "downloaded_case_details": False,
        "downloaded_identifiers": False,
        "downloaded_paths": False,
        "downloaded_pixels": False,
        "private_review_artifacts_remote_only": True,
    }:
        raise SafeRunError("sanitized_summary_invalid")
    benchmark = summary.get("benchmark")
    if not isinstance(benchmark, dict) or set(benchmark) != {
        "iterations",
        "decode_time",
        "preprocessing_time",
        "representative_tensor_cache_mib_ceiling",
        "process_peak_rss_mib_ceiling",
        "peak_rss_increase_mib_ceiling",
        "cpu_parallelism",
        "kaggle_compatibility",
        "deterministic_replay",
    }:
        raise SafeRunError("sanitized_summary_invalid")
    if (
        benchmark.get("iterations") != 3
        or benchmark.get("deterministic_replay") is not True
        or any(
            isinstance(benchmark.get(key), bool)
            or not isinstance(benchmark.get(key), int)
            or not 1 <= cast(int, benchmark[key]) <= 1_048_576
            for key in (
                "representative_tensor_cache_mib_ceiling",
                "process_peak_rss_mib_ceiling",
            )
        )
        or isinstance(benchmark.get("peak_rss_increase_mib_ceiling"), bool)
        or not isinstance(benchmark.get("peak_rss_increase_mib_ceiling"), int)
        or not 0 <= cast(int, benchmark["peak_rss_increase_mib_ceiling"]) <= 1_048_576
    ):
        raise SafeRunError("sanitized_summary_invalid")
    for timing_name in ("decode_time", "preprocessing_time"):
        timing = benchmark.get(timing_name)
        if (
            not isinstance(timing, dict)
            or set(timing) != {"minimum_seconds", "median_seconds", "maximum_seconds"}
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
                for value in timing.values()
            )
            or not timing["minimum_seconds"]
            <= timing["median_seconds"]
            <= timing["maximum_seconds"]
        ):
            raise SafeRunError("sanitized_summary_invalid")
    parallel = benchmark.get("cpu_parallelism")
    if (
        not isinstance(parallel, list)
        or not 1 <= len(parallel) <= 16
        or any(
            not isinstance(item, dict)
            or set(item)
            != {
                "workers",
                "tasks",
                "wall_seconds",
                "tasks_per_second",
                "speedup_vs_one_worker",
            }
            for item in parallel
        )
    ):
        raise SafeRunError("sanitized_summary_invalid")
    for item in parallel:
        if (
            isinstance(item["workers"], bool)
            or not isinstance(item["workers"], int)
            or not 1 <= item["workers"] <= 16
            or isinstance(item["tasks"], bool)
            or not isinstance(item["tasks"], int)
            or not 1 <= item["tasks"] <= 10_000
            or any(
                isinstance(item[key], bool)
                or not isinstance(item[key], (int, float))
                or not math.isfinite(float(item[key]))
                or item[key] <= 0
                for key in ("wall_seconds", "tasks_per_second", "speedup_vs_one_worker")
            )
        ):
            raise SafeRunError("sanitized_summary_invalid")
    compatibility = benchmark.get("kaggle_compatibility")
    if (
        not isinstance(compatibility, dict)
        or set(compatibility)
        != {
            "python_version",
            "platform_system",
            "platform_machine",
            "cpu_count",
            "numpy_version",
            "pydicom_version",
            "python_supported",
            "linux_runtime_observed",
            "offline_bundle_verified",
            "kaggle_runtime_verified",
            "accelerator",
            "horizontal_flip",
            "through_plane_resampling",
        }
        or compatibility.get("python_supported") is not True
        or compatibility.get("linux_runtime_observed") is not True
        or compatibility.get("offline_bundle_verified") is not True
        or compatibility.get("kaggle_runtime_verified") is not True
        or compatibility.get("accelerator") != "cpu"
        or compatibility.get("horizontal_flip") is not False
        or compatibility.get("through_plane_resampling") is not False
        or any(
            not isinstance(compatibility.get(key), str)
            or not re.fullmatch(r"[A-Za-z0-9._+-]{1,50}", str(compatibility[key]))
            for key in (
                "python_version",
                "platform_system",
                "platform_machine",
                "numpy_version",
                "pydicom_version",
            )
        )
        or isinstance(compatibility.get("cpu_count"), bool)
        or not isinstance(compatibility.get("cpu_count"), int)
        or not 1 <= cast(int, compatibility["cpu_count"]) <= 4096
    ):
        raise SafeRunError("sanitized_summary_invalid")
    _scan_downloadable(payload, str(cast(Mapping[str, Any], run_config["privacy"])["canary"]))
    return summary


def _validate_inventory(
    payload: bytes,
    *,
    run_config: Mapping[str, Any],
    summary_payload: bytes,
    benchmark_payload: bytes,
) -> None:
    inventory = _json_object(payload, "sanitized_inventory_invalid")
    if payload != _canonical_json_bytes(inventory):
        raise SafeRunError("sanitized_inventory_invalid")
    expected = {
        "schema_version": 1,
        "artifact_type": "dicom-qa-sanitized-artifact-inventory",
        "provenance": {
            "git_commit": run_config["code_commit"],
            "bundle_sha256": run_config["bundle_sha256"],
        },
        "artifacts": [
            {
                "name": "benchmark.md",
                "kind": "aggregate_documentation",
                "bytes": len(benchmark_payload),
                "sha256": _sha256_bytes(benchmark_payload),
            },
            {
                "name": "sanitized_summary.json",
                "kind": "aggregate_json",
                "bytes": len(summary_payload),
                "sha256": _sha256_bytes(summary_payload),
            },
        ],
    }
    if inventory != expected:
        raise SafeRunError("sanitized_inventory_invalid")
    _scan_downloadable(payload, str(cast(Mapping[str, Any], run_config["privacy"])["canary"]))


def _run_private_qa(
    *,
    input_root: Path,
    competition_root: Path,
    output_root: Path,
    run_config: Mapping[str, Any],
    preprocessing_config_path: Path,
    inference_limit_seconds: int,
    deadline_at: float | None = None,
) -> None:
    import numpy as np

    from rsna_knee.data import series_slots as slots
    from rsna_knee.dicom import benchmark as benchmark_module
    from rsna_knee.dicom import pipeline
    from rsna_knee.qa import preprocessing as qa

    if output_root.exists():
        raise SafeRunError("output_exists")
    _decoder_preflight()
    rows = _read_series_rows(competition_root / "train_series.csv")
    input_identity = cast(Mapping[str, Any], run_config["input_identity"])
    source_binding = _discover_source_manifest_binding(
        input_root,
        cast(Mapping[str, object], input_identity["source_manifest"]),
    )
    try:
        (
            source_manifest_facts,
            source_manifest_identity,
            source_manifest_reconciliation,
        ) = _load_source_manifest_facts(source_binding, rows)
        config = _preprocessing_config(preprocessing_config_path, pipeline)
        versions = pipeline.PipelineVersions(
            code_commit=str(run_config["code_commit"]),
            source_manifest_version=SOURCE_MANIFEST_VERSION,
        )
        workers = int(run_config["workers"])
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        if "source_manifest_reconciliation" in locals():
            source_manifest_reconciliation.connection.close()
        raise SafeRunError("worker_count_invalid") from error
    except BaseException:
        if "source_manifest_reconciliation" in locals():
            source_manifest_reconciliation.connection.close()
        raise
    if not 1 <= workers <= 16:
        source_manifest_reconciliation.connection.close()
        raise SafeRunError("worker_count_invalid")

    private_run_started = time.perf_counter()
    private_run_cpu_started = _cpu_seconds()
    private_run_peak_rss_started = _peak_rss_bytes()
    staging_parent = Path(tempfile.mkdtemp(prefix=".dicom-qa-output-", dir=output_root.parent))
    first_render = staging_parent / "first-render"
    repeat_render = staging_parent / "repeat-render"
    final_staging = staging_parent / OUTPUT_DIRECTORY
    first_render.mkdir()
    repeat_render.mkdir()
    final_staging.mkdir()
    private_cases: list[dict[str, object]] = []
    representative_inputs: tuple[RepresentativeSeriesInput, ...] | None = None
    eligible_studies = 0
    eligible_series = 0
    rendered_series = 0
    eligible_strata: set[tuple[str, ...]] = set()
    first_provenance: Any | None = None
    qa_generation_seconds = 0.0
    try:
        full_manifest_staging = staging_parent / "private_full_run_manifest.jsonl"
        (
            full_run_metrics,
            representative_inputs,
            first_provenance,
            selection_plan,
            full_replay_evidence,
        ) = _run_full_dataset_pass(
            competition_root=competition_root,
            rows=rows,
            private_manifest_path=full_manifest_staging,
            run_config=run_config,
            config=config,
            versions=versions,
            pipeline_module=pipeline,
            slots_module=slots,
            workers=workers,
            deadline_at=deadline_at,
            source_manifest_facts=source_manifest_facts,
            source_manifest_identity=source_manifest_identity,
            source_manifest_reconciliation=source_manifest_reconciliation,
        )
        source_manifest_reconciliation.connection.close()
        selected = selection_plan.studies
        selected_uids = {item.study_uid for item in selected}
        selected_rows: dict[str, list[SeriesRow]] = defaultdict(list)
        for row in rows:
            if row.study_uid in selected_uids:
                selected_rows[row.study_uid].append(row)
        if set(selected_rows) != selected_uids:
            raise SafeRunError("selection_reconciliation_failed")
        cohort_replay_started = time.perf_counter()
        for case_ordinal, selected_study in enumerate(selected):
            _check_deadline(deadline_at)
            study_rows = sorted(
                selected_rows[selected_study.study_uid],
                key=lambda row: hashlib.sha256(
                    f"{SELECTION_SEED}:{row.series_uid}".encode()
                ).digest(),
            )
            states: list[dict[str, Any]] = []
            candidates: list[Any] = []
            for series_ordinal, row in enumerate(study_rows):
                _check_deadline(deadline_at)
                full_evidence = full_replay_evidence.get((row.study_uid, row.series_uid))
                if not isinstance(full_evidence, Mapping):
                    raise SafeRunError("full_cohort_replay_mismatch")
                source_failure = full_evidence.get("source_failure")
                paths: tuple[Path, ...]
                decoded: tuple[Any, ...]
                ordered: Any | None
                repeat_ordered: Any | None
                decode_failures: tuple[dict[str, str | None], ...]
                order_failure: dict[str, str | None] | None
                quality: Any
                if full_evidence.get("terminal_state") == "source_access_blocked":
                    paths = ()
                    decoded = ()
                    ordered = None
                    repeat_ordered = None
                    decode_failures = ()
                    order_failure = None
                    quality = full_evidence.get("quality")
                    if quality is None:
                        raise SafeRunError("full_cohort_replay_mismatch")
                    base_terminal = "source_access_blocked"
                else:
                    paths = _series_files(competition_root, row)
                    first_pass = _decode_order_pass(paths, pipeline, deadline_at=deadline_at)
                    repeat_pass = _decode_order_pass(paths, pipeline, deadline_at=deadline_at)
                    if _canonical_json_bytes(
                        _series_pass_record(first_pass)
                    ) != _canonical_json_bytes(_series_pass_record(repeat_pass)):
                        raise SafeRunError("full_cohort_replay_mismatch")
                    decoded = first_pass.decoded
                    ordered = first_pass.ordered
                    repeat_ordered = repeat_pass.ordered
                    decode_failures = first_pass.decode_failures
                    order_failure = first_pass.order_failure
                    quality = _quality(
                        total=len(paths),
                        decoded=len(decoded),
                        ordered=ordered,
                        slots_module=slots,
                    )
                    repeat_quality = _quality(
                        total=len(paths),
                        decoded=len(repeat_pass.decoded),
                        ordered=repeat_ordered,
                        slots_module=slots,
                    )
                    if quality != repeat_quality:
                        raise SafeRunError("full_cohort_replay_mismatch")
                    base_terminal = (
                        "decode_blocked"
                        if decode_failures or not decoded
                        else "ordering_blocked"
                        if order_failure is not None or ordered is None
                        else "quality_blocked"
                        if quality.blocked or not ordered.model_eligible
                        else "preprocessing_candidate"
                    )
                terminal_state, preprocessing_failure = _selected_replay_terminal(
                    base_terminal, full_evidence
                )
                orientation = (
                    ordered.slices[0].metadata.image_orientation
                    if ordered is not None
                    else decoded[0].metadata.image_orientation
                    if decoded
                    else None
                )
                series_key = f"case_{case_ordinal:06d}_series_{series_ordinal:03d}"
                candidate = slots.SeriesCandidate(
                    series_key=series_key,
                    tie_break_key=hashlib.sha256(row.series_uid.encode("ascii")).hexdigest(),
                    organizer_plane=None if row.plane == "missing" else row.plane,
                    organizer_fluid_sensitive=(
                        True
                        if row.fluid_sensitive == "present"
                        else False
                        if row.fluid_sensitive == "absent"
                        else None
                    ),
                    image_orientation_patient=orientation,
                    quality=quality,
                )
                candidates.append(candidate)
                states.append(
                    {
                        "row": row,
                        "paths": paths,
                        "series_ordinal": series_ordinal,
                        "ordered": ordered,
                        "repeat_ordered": repeat_ordered,
                        "quality": quality,
                        "source_failure": source_failure,
                        "decode_failures": decode_failures,
                        "order_failure": order_failure,
                        "preprocessing_failure": preprocessing_failure,
                        "terminal_state": terminal_state,
                        "candidate": candidate,
                        "model_reconstruction": None,
                        "qa_reconstruction": None,
                        "model_eligible": False,
                        "slot": None,
                        "retention_reasons": (),
                    }
                )
            assignment = slots.assign_series_slots(tuple(candidates))
            primary_slots = {
                selection.primary.candidate.series_key: selection.slot.value
                for selection in assignment.primary_slots
                if selection.primary is not None
            }
            additional = {
                item.candidate.series_key: tuple(reason.value for reason in item.reasons)
                for item in assignment.additional_or_duplicate
            }
            study_eligible = False
            for state in states:
                candidate = state["candidate"]
                state["slot"] = primary_slots.get(candidate.series_key, "additional_or_duplicate")
                state["retention_reasons"] = additional.get(candidate.series_key, ())
                ordered = state["ordered"]
                repeat_ordered = state["repeat_ordered"]
                if state["terminal_state"] != "model_eligible":
                    continue
                if ordered is None or repeat_ordered is None:
                    raise SafeRunError("full_cohort_replay_mismatch")
                try:
                    model_result = pipeline.preprocess_series(ordered, config, versions)
                    qa_result = pipeline.preprocess_series(
                        ordered, replace(config, sample_count=None), versions
                    )
                    repeated_model_result = pipeline.preprocess_series(
                        repeat_ordered, config, versions
                    )
                    repeated_qa_result = pipeline.preprocess_series(
                        repeat_ordered, replace(config, sample_count=None), versions
                    )
                except pipeline.PipelineError:
                    raise SafeRunError("full_cohort_replay_mismatch") from None
                if (
                    not np.array_equal(model_result.tensor, repeated_model_result.tensor)
                    or model_result.provenance != repeated_model_result.provenance
                    or not np.array_equal(qa_result.tensor, repeated_qa_result.tensor)
                    or qa_result.provenance != repeated_qa_result.provenance
                    or _private_reconstruction_record(model_result)
                    != _private_reconstruction_record(repeated_model_result)
                    or _private_reconstruction_record(qa_result)
                    != _private_reconstruction_record(repeated_qa_result)
                ):
                    raise SafeRunError("full_cohort_replay_mismatch")
                state["model_reconstruction"] = _private_reconstruction_record(model_result)
                state["qa_reconstruction"] = _private_reconstruction_record(qa_result)
                state["model_eligible"] = True
                study_eligible = True
                eligible_series += 1

                qa_started = time.perf_counter()
                metadata = _qa_metadata(
                    case_ordinal=case_ordinal,
                    series_ordinal=state["series_ordinal"],
                    row=state["row"],
                    ordered=ordered,
                    qa_result=qa_result,
                    qa_module=qa,
                    slots_module=slots,
                )
                source = np.stack([item.pixels for item in ordered.slices], axis=0)
                repeated_source = np.stack([item.pixels for item in repeat_ordered.slices], axis=0)
                processed = qa_result.tensor[:, 0, :, :]
                contact_count = min(qa.CONTACT_MAX_SLICES, len(ordered.slices))
                contact = tuple(
                    sorted(
                        set(
                            pipeline.deterministic_slice_indices(
                                ordered.geometry.projected_positions_mm, contact_count
                            )
                        )
                    )
                )
                qa.render_private_qa(
                    source,
                    processed,
                    metadata=metadata,
                    output_dir=first_render,
                    contact_slice_indices=contact,
                )
                qa.render_private_qa(
                    repeated_source,
                    repeated_qa_result.tensor[:, 0, :, :],
                    metadata=metadata,
                    output_dir=repeat_render,
                    contact_slice_indices=contact,
                )
                qa_generation_seconds += time.perf_counter() - qa_started
                rendered_series += 1
            if study_eligible:
                eligible_studies += 1
                eligible_strata.add(selected_study.stratum)

            private_series: list[dict[str, object]] = []
            for state in states:
                terminal_state = str(state["terminal_state"])
                private_series.append(
                    {
                        "series_ordinal": state["series_ordinal"],
                        "series_uid": state["row"].series_uid,
                        **_review_plane_context(
                            state["row"],
                            state["candidate"].image_orientation_patient,
                            slots,
                        ),
                        "slot": state["slot"],
                        "retention_reasons": list(state["retention_reasons"]),
                        "quality": {
                            "blocked_reasons": [
                                reason.value for reason in state["quality"].blocked_reasons
                            ],
                            "components": asdict(state["quality"].components),
                        },
                        "source_failure": state["source_failure"],
                        "decode_failures": list(state["decode_failures"]),
                        "ordering_failure": state["order_failure"],
                        "preprocessing_failure": state["preprocessing_failure"],
                        "terminal_state": terminal_state,
                        "model_eligible": state["model_eligible"],
                        "model_output_reconstruction": state["model_reconstruction"],
                        "qa_output_reconstruction": state["qa_reconstruction"],
                    }
                )
            private_cases.append(
                {
                    "case_ordinal": case_ordinal,
                    "study_uid": selected_study.study_uid,
                    "selection_stratum": list(selected_study.stratum),
                    "review_eligible": study_eligible,
                    "missing_series_mask": list(assignment.missing_mask),
                    "series": private_series,
                }
            )

        if eligible_studies < MINIMUM_ELIGIBLE_STUDIES:
            raise SafeRunError("eligible_study_gate_failed")
        material_strata = {item.stratum for item in selection_plan.census if item.material}
        if not material_strata.issubset(eligible_strata):
            raise SafeRunError("eligible_material_strata_coverage_failed")
        if eligible_series < eligible_studies or rendered_series != eligible_series:
            raise SafeRunError("eligible_series_render_incomplete")
        cohort_replay_seconds = time.perf_counter() - cohort_replay_started
        first_records = _directory_records(first_render)
        repeat_records = _directory_records(repeat_render)
        if first_records != repeat_records:
            raise SafeRunError("repeat_render_nondeterministic")
        if not representative_inputs or first_provenance is None:
            raise SafeRunError("benchmark_input_missing")

        worker_ceiling = min(workers, os.cpu_count() or 1, 8)
        requested_worker_counts = REPRESENTATIVE_WORKER_COUNTS
        worker_counts = tuple(value for value in requested_worker_counts if value <= worker_ceiling)
        summary_profile_index = len(representative_inputs) // 2
        representative_reports: list[tuple[RepresentativeSeriesInput, Any, dict[str, object]]] = []
        for profile_index, representative in enumerate(representative_inputs):
            report = benchmark_module.benchmark_dicom_pipeline(
                representative.paths,
                config,
                versions,
                iterations=3 if profile_index == summary_profile_index else 1,
                worker_counts=worker_counts,
                offline_bundle_verified=True,
            )
            representative_reports.append((representative, report, _rounded_benchmark(report)))
        benchmark_report = representative_reports[summary_profile_index][1]
        benchmark = _rounded_benchmark(benchmark_report)
        timings = cast(dict[str, float], full_run_metrics["timings_seconds"])
        timings["qa_generation_seconds"] = qa_generation_seconds
        timings["selected_cohort_replay_seconds"] = cohort_replay_seconds
        full_dataset_wall_seconds = float(cast(Any, full_run_metrics["total_wall_seconds"]))
        full_run_metrics["full_dataset_wall_seconds"] = full_dataset_wall_seconds
        total_wall_seconds = time.perf_counter() - private_run_started
        full_run_metrics["total_wall_seconds"] = total_wall_seconds
        timings["total_seconds"] = total_wall_seconds
        process_cpu_seconds = max(0.0, _cpu_seconds() - private_run_cpu_started)
        full_run_metrics["process_cpu_seconds"] = process_cpu_seconds
        cpu_capacity = int(cast(Any, full_run_metrics["cpu_capacity_threads"]))
        full_run_metrics["cpu_utilization_percent"] = min(
            100.0,
            100.0 * process_cpu_seconds / max(total_wall_seconds * cpu_capacity, 1e-12),
        )
        process_peak_rss_bytes = _peak_rss_bytes()
        full_run_metrics["process_peak_rss_bytes"] = process_peak_rss_bytes
        full_run_metrics["process_peak_rss_increase_bytes"] = max(
            0, process_peak_rss_bytes - private_run_peak_rss_started
        )
        review_bytes = sum(int(cast(Any, item["bytes"])) for item in first_records)
        repeated_review_bytes = sum(int(cast(Any, item["bytes"])) for item in repeat_records)
        full_run_metrics["private_review_artifact_bytes"] = review_bytes
        full_run_metrics["peak_private_working_disk_bytes"] = max(
            int(cast(Any, full_run_metrics["peak_private_working_disk_bytes"])),
            int(cast(Any, full_run_metrics["manifest_bytes"]))
            + review_bytes
            + repeated_review_bytes,
        )
        full_run_metrics["peak_private_working_disk_observation"] = (
            "full_manifest_plus_first_and_repeat_review_artifacts_before_repeat_deletion"
        )
        full_run_metrics["qa_generation_measurement"] = {
            "scope": "selected_post_full_pass_cohort",
            "render_passes": 2,
            "series_rendered_per_pass": rendered_series,
            "separately_timed": True,
        }
        full_run_metrics["representative_scaling"] = {
            "selection_method": "model_eligible_slice_count_rank_small_median_large_v1",
            "requested_worker_counts": list(requested_worker_counts),
            "available_worker_counts": list(worker_counts),
            "unavailable_worker_counts": [
                value for value in requested_worker_counts if value not in worker_counts
            ],
            "profiles": [
                {
                    "profile": representative.profile,
                    "slice_count": representative.slice_count,
                    "iterations": report.iterations,
                    "decode_time": rounded["decode_time"],
                    "preprocessing_time": rounded["preprocessing_time"],
                    "representative_tensor_cache_mib_ceiling": rounded[
                        "representative_tensor_cache_mib_ceiling"
                    ],
                    "process_peak_rss_mib_ceiling": rounded["process_peak_rss_mib_ceiling"],
                    "peak_rss_increase_mib_ceiling": rounded["peak_rss_increase_mib_ceiling"],
                    "cpu_parallelism": rounded["cpu_parallelism"],
                }
                for representative, report, rounded in representative_reports
            ],
        }
        full_run_metrics["end_to_end_throughput"] = {
            "files_per_second": int(cast(Any, full_run_metrics["files_processed"]))
            / max(total_wall_seconds, 1e-12),
            "series_per_second": int(cast(Any, full_run_metrics["series_processed"]))
            / max(total_wall_seconds, 1e-12),
            "studies_per_second": int(cast(Any, full_run_metrics["studies_processed"]))
            / max(total_wall_seconds, 1e-12),
        }
        performance = _sanitized_performance(full_run_metrics, inference_limit_seconds)
        runner_sha256 = _sha256_file(Path(__file__).resolve(strict=True))
        provenance_config = cast(Mapping[str, Any], run_config["provenance"])
        qa_cohort_selection = cast(dict[str, object], full_run_metrics["qa_cohort_selection"])
        integrity_status = cast(Mapping[str, object], full_run_metrics["integrity_gate"])["status"]
        summary = {
            "schema_version": 1,
            "artifact_type": "dicom-qa-sanitized-aggregate",
            "status": (
                "complete_pending_human_review"
                if integrity_status == "pass"
                else "blocked_unresolved_integrity"
            ),
            "provenance": {
                "git_commit": run_config["code_commit"],
                "bundle_sha256": run_config["bundle_sha256"],
                "runner_sha256": runner_sha256,
                "review_finalizer_sha256": provenance_config["review_finalizer_sha256"],
                "preprocessing_config_file_sha256": provenance_config[
                    "preprocessing_config_sha256"
                ],
                "preprocessing_configuration_hash": first_provenance.configuration_hash,
                "preprocessing_version": first_provenance.preprocessing_version,
                "source_manifest_version": first_provenance.source_manifest_version,
                "qa_cohort_selection_version": QA_COHORT_SELECTION_VERSION,
                "dicom_library_versions": [
                    {"package": package, "version": version}
                    for package, version in first_provenance.dicom_library_versions
                ],
            },
            "selection": {
                "source": "full_run_terminal_records_plus_authenticated_manifest_v2",
                "target_studies": TARGET_STUDIES,
                "maximum_studies": MAX_TARGET_STUDIES,
                "selected_studies": "between_120_and_240",
                "minimum_eligible_studies": MINIMUM_ELIGIBLE_STUDIES,
                "eligible_studies": "at_least_100",
                "stratified": True,
                "slice_count_stratified": True,
                "material_strata_covered": True,
                "bounded_deterministic_expansion": True,
                "selected_after_full_pass": True,
                "source_manifest_authenticated": True,
                "available_required_strata_dispositioned": True,
                "cohort_selection_version": QA_COHORT_SELECTION_VERSION,
            },
            "pipeline": {
                "full_training_dataset_processed": True,
                "all_series_terminal": True,
                "integrity_gate": integrity_status,
                "unresolved_blockers": ("zero" if integrity_status == "pass" else "one_or_more"),
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
        summary_payload = _canonical_json_bytes(summary)
        _validate_summary(
            summary_payload,
            run_config,
            expected_inference_limit_seconds=inference_limit_seconds,
        )
        benchmark_payload = _render_benchmark(summary)
        _scan_downloadable(
            benchmark_payload, str(cast(Mapping[str, Any], run_config["privacy"])["canary"])
        )
        sanitized_inventory = {
            "schema_version": 1,
            "artifact_type": "dicom-qa-sanitized-artifact-inventory",
            "provenance": {
                "git_commit": run_config["code_commit"],
                "bundle_sha256": run_config["bundle_sha256"],
            },
            "artifacts": [
                {
                    "name": "benchmark.md",
                    "kind": "aggregate_documentation",
                    "bytes": len(benchmark_payload),
                    "sha256": _sha256_bytes(benchmark_payload),
                },
                {
                    "name": "sanitized_summary.json",
                    "kind": "aggregate_json",
                    "bytes": len(summary_payload),
                    "sha256": _sha256_bytes(summary_payload),
                },
            ],
        }
        sanitized_inventory_payload = _canonical_json_bytes(sanitized_inventory)
        _validate_inventory(
            sanitized_inventory_payload,
            run_config=run_config,
            summary_payload=summary_payload,
            benchmark_payload=benchmark_payload,
        )
        if (
            _case_index_cohort_sha256(private_cases) != qa_cohort_selection["cohort_sha256"]
            or qa_cohort_selection["selected_studies"] != len(private_cases)
            or qa_cohort_selection["eligible_series"] != eligible_series
        ):
            raise SafeRunError("qa_cohort_identity_mismatch")
        private_status = (
            "pending_private_human_review"
            if integrity_status == "pass"
            else "blocked_unresolved_integrity"
        )
        private_input_identity = {
            "source_manifest": {
                "audit_id": source_manifest_identity["audit_id"],
                "version": source_manifest_identity["manifest_version"],
                "source_manifest_artifact_sha256": source_manifest_identity[
                    "source_manifest_artifact_sha256"
                ],
            },
            "official_competition": {
                "slug": COMPETITION_SLUG,
                "official_input_snapshot_sha256": source_manifest_identity[
                    "official_input_snapshot_sha256"
                ],
            },
        }
        private_case_payload = _canonical_json_bytes(
            {
                "schema_version": 1,
                "artifact_type": "private-dicom-qa-case-index",
                "status": private_status,
                "provenance": {
                    "git_commit": run_config["code_commit"],
                    "bundle_sha256": run_config["bundle_sha256"],
                    "runner_sha256": runner_sha256,
                    "review_finalizer_sha256": provenance_config["review_finalizer_sha256"],
                },
                "input_identity": private_input_identity,
                "qa_cohort_selection": qa_cohort_selection,
                "selection_census": [asdict(item) for item in selection_plan.census],
                "represented_review_strata": [list(item) for item in sorted(eligible_strata)],
                "studies": private_cases,
                "benchmark": asdict(benchmark_report),
                "full_run": full_run_metrics,
            }
        )
        private_inventory_payload = _canonical_json_bytes(
            {
                "schema_version": 1,
                "artifact_type": "private-dicom-qa-artifact-inventory",
                "status": private_status,
                "provenance": {
                    "git_commit": run_config["code_commit"],
                    "bundle_sha256": run_config["bundle_sha256"],
                    "runner_sha256": runner_sha256,
                    "review_finalizer_sha256": provenance_config["review_finalizer_sha256"],
                    "private_case_index_sha256": _sha256_bytes(private_case_payload),
                },
                "artifacts": list(first_records),
            }
        )
        if len(private_case_payload) > PRIVATE_OUTPUT_POLICY["private_case_index.json"]:
            raise SafeRunError("private_case_index_too_large")
        if (
            len(private_inventory_payload)
            > PRIVATE_OUTPUT_POLICY["private_artifact_inventory.json"]
        ):
            raise SafeRunError("private_artifact_inventory_too_large")

        shutil.rmtree(repeat_render)
        first_render.rename(final_staging / PRIVATE_REVIEW_DIRECTORY)
        full_manifest_staging.rename(final_staging / "private_full_run_manifest.jsonl")
        _write_new(
            final_staging / "private_full_run_metrics.json",
            _canonical_json_bytes(full_run_metrics),
            maximum=PRIVATE_OUTPUT_POLICY["private_full_run_metrics.json"],
        )
        _write_new(
            final_staging / "private_case_index.json",
            private_case_payload,
            maximum=PRIVATE_OUTPUT_POLICY["private_case_index.json"],
        )
        _write_new(
            final_staging / "private_artifact_inventory.json",
            private_inventory_payload,
            maximum=PRIVATE_OUTPUT_POLICY["private_artifact_inventory.json"],
        )
        _write_new(
            final_staging / "sanitized_summary.json",
            summary_payload,
            maximum=DOWNLOADABLE_OUTPUT_POLICY["sanitized_summary.json"][1],
        )
        _write_new(
            final_staging / "benchmark.md",
            benchmark_payload,
            maximum=DOWNLOADABLE_OUTPUT_POLICY["benchmark.md"][1],
        )
        _write_new(
            final_staging / "sanitized_artifact_inventory.json",
            sanitized_inventory_payload,
            maximum=DOWNLOADABLE_OUTPUT_POLICY["sanitized_artifact_inventory.json"][1],
        )
        final_staging.rename(output_root)
    except BaseException:
        source_manifest_reconciliation.connection.close()
        shutil.rmtree(staging_parent, ignore_errors=True)
        raise
    shutil.rmtree(staging_parent, ignore_errors=True)


def main() -> int:
    phase = "bundle"
    started = time.monotonic()
    runtime_root: Path | None = None
    package_root = "rsna_knee"
    displaced_modules: dict[str, ModuleType] = {}
    runtime_modules_active = False
    try:
        _safe_event("dicom_qa_started")
        input_root = Path(os.environ.get("KAGGLE_INPUT_ROOT", "/kaggle/input"))
        working_root = Path(os.environ.get("KAGGLE_WORKING_ROOT", "/kaggle/working"))
        output_root = working_root / OUTPUT_DIRECTORY
        bundle_root, manifest = _find_bundle(input_root)
        records = _validated_records(bundle_root, manifest)
        run_config, paths, dependencies = _verify_run_config(bundle_root, manifest, records)
        inference_limit_seconds = _competition_cpu_limit_seconds(paths["competition_contract"])
        competition_root = _find_competition_root(input_root)
        deadline_at = started + SELF_DEADLINE_SECONDS
        remaining = deadline_at - time.monotonic()
        phase = "selection"
        with _enforce_self_deadline(remaining), _silence_process_output():
            runtime_root = _install_offline_runtime(
                bundle_root, paths["project_wheel"], dependencies
            )
            sys.path.insert(0, str(runtime_root))
            displaced_modules = {
                name: module
                for name, module in tuple(sys.modules.items())
                if name == package_root or name.startswith(f"{package_root}.")
            }
            for name in displaced_modules:
                del sys.modules[name]
            runtime_modules_active = True
            phase = "processing"
            _run_private_qa(
                input_root=input_root,
                competition_root=competition_root,
                output_root=output_root,
                run_config=run_config,
                preprocessing_config_path=paths["preprocessing_config"],
                inference_limit_seconds=inference_limit_seconds,
                deadline_at=deadline_at,
            )
        phase = "output"
        _safe_event("dicom_qa_complete")
        return 0
    except SafeRunError as error:
        _safe_event("dicom_qa_failed", phase=phase, code=error.code)
        return 2
    except _DeadlineExceeded:
        _safe_event("dicom_qa_failed", phase=phase, code="self_deadline_exceeded")
        return 2
    except BaseException:
        _safe_event("dicom_qa_failed", phase=phase, code="internal_error")
        return 2
    finally:
        if runtime_modules_active:
            for name in tuple(sys.modules):
                if name == package_root or name.startswith(f"{package_root}."):
                    del sys.modules[name]
            sys.modules.update(displaced_modules)
        if runtime_root is not None:
            runtime_text = str(runtime_root)
            if runtime_text in sys.path:
                sys.path.remove(runtime_text)
            shutil.rmtree(runtime_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
