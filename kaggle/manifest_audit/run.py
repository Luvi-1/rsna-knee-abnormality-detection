"""Verified, offline Kaggle entry point for the private manifest audit."""

from __future__ import annotations

import contextlib
import copy
import ctypes
import hashlib
import importlib
import io
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from concurrent.futures.process import BrokenProcessPool
from itertools import islice
from pathlib import Path, PurePosixPath
from typing import Any, Final

BUNDLE_FORMAT: Final = "rsna-knee-manifest-audit-bundle-v1"
BUNDLE_PLACEHOLDER: Final = "0" * 64
MAX_MANIFEST_BYTES: Final = 2 * 1024 * 1024
MAX_BUNDLE_BYTES: Final = 64 * 1024 * 1024
MAX_SUMMARY_BYTES: Final = 1024 * 1024
MAX_MOUNT_SEARCH_DEPTH: Final = 4
MAX_MOUNT_DIRECTORY_ENTRIES: Final = 128
EXPECTED_SINGLETON_ROLES: Final = {
    "project_wheel",
    "manifest_schema",
    "competition_pointer",
    "competition_contract",
    "dependency_lock",
    "runtime_requirements",
    "run_config",
    "audit_key",
}
DEPENDENCY_ROLE: Final = "dependency_wheel"
AUDIT_KEY_FILENAME: Final = "audit-key.bin"
REQUIRED_DECODER_PACKAGES: Final = {
    "pylibjpeg": "2.1.0",
    "pylibjpeg-libjpeg": "2.4.0",
    "pylibjpeg-openjpeg": "2.5.0",
}
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,199}\Z")
SAFE_SOURCE_PART = re.compile(r"[A-Za-z0-9._-]{1,100}\Z")
SAFE_IMPORT = re.compile(r"rsna_knee(?:\.[A-Za-z_][A-Za-z0-9_]*)+\Z")
SAFE_CALLABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,99}\Z")
SAFE_EVENT_VALUE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
SHIFT_FEATURES: Final = (
    "patient_sex",
    "scanner_manufacturer",
    "scanner_model",
    "protocol_cluster",
    "plane_availability",
    "sequence_composition",
    "report_language",
    "site_domain_cluster",
    "series_description_vocabulary",
    "patient_age_years",
    "field_strength_t",
    "study_complexity_series_count",
    "study_complexity_slice_count",
    "in_plane_resolution_area_mm2",
    "slice_thickness_mm",
    "overall_missingness",
)
SHIFT_STATUS_VALUES: Final = {
    "suppressed_low_test_support",
    "not_evaluable_test_reports_unavailable",
}
SENSITIVE_BYTES: Final = (
    re.compile(
        rb"StudyInstanceUID|SeriesInstanceUID|SOPInstanceUID|Patient(?:Name|ID)|"
        rb"(?:raw[_ -]?report|report[_ -]?text)|accession[_ -]?(?:number|id)",
        re.IGNORECASE,
    ),
    re.compile(rb"(?<![0-9])(?:[0-9]{1,12}\.){3,}[0-9]{1,12}(?![0-9])"),
    re.compile(rb"(?:^|[\"'\s])/kaggle/input/", re.MULTILINE),
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"KAGGLE_API_TOKEN\s*[:=]", re.IGNORECASE),
)
AGGREGATE_FIELDS: Final = {
    "scope": {"mode", "source_context", "example_test_only", "hidden_test_evaluable"},
    "coverage": {
        "studies_total",
        "train_studies",
        "test_studies",
        "series_total",
        "train_series",
        "test_series",
        "files_total",
        "files_terminal",
        "files_decoded",
        "files_quarantined",
        "complete",
    },
    "quality": {
        "series_geometry_pass",
        "series_fallback",
        "series_quarantined",
        "files_unreadable",
        "files_decode_failure",
        "path_header_mismatch",
        "patient_group_missing",
        "unexplained_dicom_issues",
    },
    "labels": {
        "official_only",
        "non_official_sources",
        "official_cells",
        "positive_cells",
        "negative_cells",
        "unknown_cells",
        "conflict_cells",
    },
    "duplicates": {
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
    },
    "shift": {"evaluation_scope", *SHIFT_FEATURES},
    "qa": {"selected_studies"},
    "integrity": {
        "foreign_keys",
        "all_files_terminal",
        "all_series_terminal",
        "protected_graph_closed",
        "private_artifacts_complete",
        "five_levels_reconciled",
        "dicom_issue_dispositions_complete",
    },
    "versions": {
        "manifest_version",
        "group_version",
        "label_version",
        "preprocessing_version",
    },
    "runtime": {"elapsed_seconds"},
}
COUNT_FIELDS: Final = {
    "coverage": AGGREGATE_FIELDS["coverage"] - {"complete"},
    "quality": AGGREGATE_FIELDS["quality"],
    "labels": AGGREGATE_FIELDS["labels"] - {"official_only"},
    "duplicates": AGGREGATE_FIELDS["duplicates"]
    - {
        "near_slice_study_pair_space_overflow",
        "near_series_candidate_space_overflow",
        "near_report_candidate_space_overflow",
    },
    "qa": AGGREGATE_FIELDS["qa"],
}
DISCLOSURE_POLICY: Final = {
    "policy": "joint-complementary-k20-v1",
    "minimum_export_cell": 20,
    "interval_width": 20,
    "count_representation": ("zero-below-threshold-at-or-above-threshold-or-fixed-width-range"),
    "percentages_published": False,
    "cross_snapshot_protection": "fixed-width-intervals",
}
STRUCTURAL_GROUPING_STATUS: Final = {
    "folds_assigned": False,
    "fold_feasibility": "not_assessed",
}
DISCLOSED_ZERO: Final = "zero"
DISCLOSED_LOW: Final = "below_threshold_nonzero"
DISCLOSED_HIGH: Final = "at_or_above_threshold"
DISCLOSED_MAXIMUM: Final = 2**63 - 1
DISCLOSED_RANGE = re.compile(r"range_(0|[1-9][0-9]*)_(0|[1-9][0-9]*)\Z")
COMPLEMENTARY_COUNT_GROUPS: Final = (
    (
        ("coverage", "studies_total"),
        ("coverage", "train_studies"),
        ("coverage", "test_studies"),
    ),
    (
        ("coverage", "series_total"),
        ("coverage", "train_series"),
        ("coverage", "test_series"),
    ),
    (
        ("coverage", "files_total"),
        ("coverage", "files_terminal"),
        ("coverage", "files_decoded"),
        ("coverage", "files_quarantined"),
        ("quality", "files_unreadable"),
        ("quality", "files_decode_failure"),
        ("quality", "path_header_mismatch"),
    ),
    (
        ("coverage", "series_total"),
        ("quality", "series_geometry_pass"),
        ("quality", "series_fallback"),
        ("quality", "series_quarantined"),
    ),
    (
        ("labels", "official_cells"),
        ("labels", "positive_cells"),
        ("labels", "negative_cells"),
        ("labels", "unknown_cells"),
        ("labels", "conflict_cells"),
    ),
    (
        ("duplicates", "exact_report_raw_pairs"),
        ("duplicates", "exact_report_normalized_pairs"),
        ("duplicates", "exact_report_overlap_pairs"),
        ("duplicates", "exact_report_union_pairs"),
    ),
    (
        ("duplicates", "near_slice_edges"),
        ("duplicates", "near_slice_edges_suppressed"),
    ),
    (
        ("duplicates", "candidate_edges"),
        ("duplicates", "near_slice_overflow_study_edges"),
        ("duplicates", "near_series_overflow_study_edges"),
        ("duplicates", "near_report_overflow_study_edges"),
    ),
    (
        ("duplicates", "protected_components"),
        ("duplicates", "cross_split_components"),
        ("duplicates", "future_fold_crossings"),
    ),
)
PRIVATE_OUTPUT_POLICY: Final = {
    "private_manifest.sqlite3": (8 * 1024**3, None),
    "private_duplicate_groups.csv": (256 * 1024**2, None),
    "private_preliminary_group_keys.csv": (256 * 1024**2, None),
    "private_qa_samples.csv": (64 * 1024**2, None),
    "private_artifact_inventory.json": (1024 * 1024, None),
    "audit_key.bin": (64, 32),
}
DOWNLOADABLE_OUTPUT_POLICY: Final = {
    "sanitized_summary.json": ("aggregate_json", 1024**2),
    "data_audit.md": ("documentation", 512 * 1024),
    "leakage_audit.md": ("documentation", 512 * 1024),
    "domain_shift_audit.md": ("documentation", 512 * 1024),
    "sanitized_artifact_inventory.json": ("aggregate_json", 128 * 1024),
}
SESSION_LOG_PATTERN: Final = r"[a-z0-9][a-z0-9_-]{0,99}\.log"
OUTPUT_DIRECTORY: Final = "audit-output"
UNSTRUCTURED_SENSITIVE_BYTES: Final = (
    *SENSITIVE_BYTES,
    re.compile(rb"\b(?:[0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{64})\b", re.IGNORECASE),
    re.compile(
        rb"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
        re.IGNORECASE,
    ),
    re.compile(rb"https?://|(?:www\.)?kaggle\.com/", re.IGNORECASE),
    re.compile(rb"(?:^|[\s\"'])\.?(?:private_outputs|data|reports?)/", re.IGNORECASE),
    re.compile(
        rb"\b(?:scanner|language|manufacturer|site|protocol|metadata)\s+"
        rb"(?:category|label|value)\s*:",
        re.IGNORECASE,
    ),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bBearer\s+[A-Za-z0-9._~+/-]{12,}", re.IGNORECASE),
    re.compile(
        rb"[\"']?(?:pixels?|pixel_array|decoded_pixel|phash|ncc|row_data)[\"']?\s*[:=]",
        re.IGNORECASE,
    ),
    re.compile(rb"\b(?:findings|impression|clinical history|technique)\s*:", re.IGNORECASE),
)
DOCUMENT_HEADINGS: Final = {
    "data_audit.md": {
        "# Data audit",
        "## Disclosure",
        "## Scope",
        "## Coverage",
        "## Quality",
        "## Labels",
        "## Integrity",
        "## Versions",
        "## Runtime",
    },
    "leakage_audit.md": {
        "# Leakage audit",
        "## Disclosure",
        "## Duplicates",
        "## Protected components",
        "## Structural grouping checks",
        "## Integrity",
    },
    "domain_shift_audit.md": {
        "# Domain shift audit",
        "## Disclosure",
        "## Scope",
        "## Shift",
        "## Limitations",
        "## Integrity",
    },
}
DOCUMENT_TITLES: Final = {
    "data_audit.md": "# Data audit",
    "leakage_audit.md": "# Leakage audit",
    "domain_shift_audit.md": "# Domain shift audit",
}
DOCUMENT_KEYS: Final = {
    "data_audit.md": (
        set(DISCLOSURE_POLICY)
        | AGGREGATE_FIELDS["scope"]
        | AGGREGATE_FIELDS["coverage"]
        | AGGREGATE_FIELDS["quality"]
        | AGGREGATE_FIELDS["labels"]
        | AGGREGATE_FIELDS["integrity"]
        | AGGREGATE_FIELDS["versions"]
        | AGGREGATE_FIELDS["runtime"]
    ),
    "leakage_audit.md": (
        set(DISCLOSURE_POLICY)
        | set(STRUCTURAL_GROUPING_STATUS)
        | AGGREGATE_FIELDS["duplicates"]
        | AGGREGATE_FIELDS["integrity"]
    ),
    "domain_shift_audit.md": (
        set(DISCLOSURE_POLICY)
        | AGGREGATE_FIELDS["scope"]
        | AGGREGATE_FIELDS["shift"]
        | AGGREGATE_FIELDS["integrity"]
    ),
}


class SafeRunError(RuntimeError):
    """A failure carrying only a fixed, non-sensitive code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _Discard(io.TextIOBase):
    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        return len(value)

    def flush(self) -> None:
        return None


def _runner_failure_code(error: BaseException, module: object | None) -> str:
    """Reduce a verified runner failure to one bounded, non-sensitive code."""

    manifest_error_type = (
        getattr(module, "ManifestAuditError", None) if module is not None else None
    )
    module_name = getattr(module, "__name__", None) if module is not None else None
    if (
        isinstance(manifest_error_type, type)
        and issubclass(manifest_error_type, BaseException)
        and manifest_error_type.__name__ == "ManifestAuditError"
        and isinstance(module_name, str)
        and manifest_error_type.__module__ == module_name
        and type(error) is manifest_error_type
    ):
        if (
            len(error.args) == 1
            and isinstance(error.args[0], str)
            and SAFE_EVENT_VALUE.fullmatch(error.args[0]) is not None
        ):
            return error.args[0]
        return "runner_failed"
    if isinstance(error, MemoryError):
        return "runner_memory_exhausted"
    if isinstance(error, BrokenProcessPool):
        return "runner_worker_pool_broken"
    if isinstance(error, sqlite3.Error):
        return "runner_database_failed"
    return "runner_failed"


def _canonical_json_bytes(payload: object) -> bytes:
    try:
        rendered = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise SafeRunError("json_invalid") from error
    return (rendered + "\n").encode()


def _safe_event(event: str, *, phase: str | None = None, code: str | None = None) -> None:
    payload = {"event": event}
    if phase is not None:
        payload["phase"] = phase
    if code is not None:
        payload["code"] = code
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), flush=True)


def _flush_native_stdio() -> None:
    try:
        library = ctypes.CDLL(None)
        flush = library.fflush
        flush.argtypes = [ctypes.c_void_p]
        flush.restype = ctypes.c_int
        if flush(None) != 0:
            raise SafeRunError("output_redirection_failed")
    except (AttributeError, OSError) as error:
        raise SafeRunError("output_redirection_failed") from error


@contextlib.contextmanager
def _silence_process_output() -> Any:
    """Suppress Python, native-extension, and child-process output at the FD boundary."""

    saved: list[tuple[int, int]] = []
    null_descriptor: int | None = None
    try:
        sys.stdout.flush()
        sys.stderr.flush()
        _flush_native_stdio()
        null_descriptor = os.open(os.devnull, os.O_WRONLY)
        for descriptor in (1, 2):
            saved_descriptor = os.dup(descriptor)
            saved.append((descriptor, saved_descriptor))
            os.dup2(null_descriptor, descriptor)
    except OSError as error:
        for descriptor, saved_descriptor in reversed(saved):
            with contextlib.suppress(OSError):
                os.dup2(saved_descriptor, descriptor)
            with contextlib.suppress(OSError):
                os.close(saved_descriptor)
        if null_descriptor is not None:
            with contextlib.suppress(OSError):
                os.close(null_descriptor)
        raise SafeRunError("output_redirection_failed") from error
    try:
        yield
    finally:
        restore_failed = False
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            _flush_native_stdio()
        except (OSError, SafeRunError):
            restore_failed = True
        for descriptor, saved_descriptor in reversed(saved):
            try:
                os.dup2(saved_descriptor, descriptor)
            except OSError:
                restore_failed = True
            finally:
                with contextlib.suppress(OSError):
                    os.close(saved_descriptor)
        if null_descriptor is not None:
            with contextlib.suppress(OSError):
                os.close(null_descriptor)
        if restore_failed:
            raise SafeRunError("output_redirection_failed")


@contextlib.contextmanager
def _enforce_self_deadline(seconds: float) -> Any:
    """Raise a fixed failure before the declared Kaggle self-deadline."""

    if seconds <= 0:
        raise SafeRunError("self_deadline_exceeded")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def expire(_signum: int, _frame: object) -> None:
        raise SafeRunError("self_deadline_exceeded")

    try:
        signal.signal(signal.SIGALRM, expire)
        signal.setitimer(signal.ITIMER_REAL, seconds)
    except (OSError, ValueError) as error:
        raise SafeRunError("self_deadline_unavailable") from error
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise SafeRunError("bundle_file_unreadable") from error
    return digest.hexdigest()


def _read_bounded(
    path: Path, maximum_bytes: int, code: str, *, allow_symlink: bool = False
) -> bytes:
    try:
        if (path.is_symlink() and not allow_symlink) or not path.is_file():
            raise SafeRunError(code)
        size = path.stat().st_size
        if size <= 0 or size > maximum_bytes:
            raise SafeRunError(code)
        with path.open("rb") as stream:
            payload = stream.read(maximum_bytes + 1)
    except OSError as error:
        raise SafeRunError(code) from error
    if len(payload) != size:
        raise SafeRunError(code)
    return payload


def _json_object(payload: bytes, code: str) -> dict[str, Any]:
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SafeRunError(code) from error
    if not isinstance(decoded, dict):
        raise SafeRunError(code)
    return decoded


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
                    entry for entry in sorted(entries, key=lambda item: item.name) if entry.is_dir()
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
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise SafeRunError("input_root_unreadable") from error
        candidates.setdefault(resolved, candidate)
    if not candidates:
        raise SafeRunError("bundle_missing")
    if len(candidates) > 1:
        raise SafeRunError("bundle_ambiguous")
    manifest_path = next(iter(candidates.values()))
    manifest = _json_object(
        _read_bounded(
            manifest_path,
            MAX_MANIFEST_BYTES,
            "bundle_manifest_invalid",
            allow_symlink=True,
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
                resolved = directory.resolve(strict=True)
            except OSError as error:
                raise SafeRunError("competition_input_missing") from error
            candidates.setdefault(resolved, directory)
    if len(candidates) != 1:
        raise SafeRunError("competition_input_missing")
    return next(iter(candidates.values()))


def _validated_records(
    bundle_root: Path, manifest: Mapping[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    records = manifest.get("files")
    if not isinstance(records, list) or not (
        len(EXPECTED_SINGLETON_ROLES) + 1 <= len(records) <= 64
    ):
        raise SafeRunError("bundle_manifest_invalid")
    by_role: dict[str, list[dict[str, Any]]] = {}
    names: set[str] = set()
    total_bytes = 0
    for raw_record in records:
        if not isinstance(raw_record, dict):
            raise SafeRunError("bundle_manifest_invalid")
        path_name = _safe_manifest_path(raw_record.get("path"))
        role = raw_record.get("role")
        digest = raw_record.get("sha256")
        size = raw_record.get("bytes")
        _safe_source_path(raw_record.get("source_path"))
        if (
            not isinstance(role, str)
            or role not in EXPECTED_SINGLETON_ROLES | {DEPENDENCY_ROLE}
            or path_name in names
            or not isinstance(digest, str)
            or not HEX_64.fullmatch(digest)
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
            or size > MAX_BUNDLE_BYTES
        ):
            raise SafeRunError("bundle_manifest_invalid")
        candidate = bundle_root / path_name
        try:
            if not candidate.is_file() or candidate.stat().st_size != size:
                raise SafeRunError("bundle_file_invalid")
        except OSError as error:
            raise SafeRunError("bundle_file_invalid") from error
        if _sha256_file(candidate) != digest:
            raise SafeRunError("bundle_hash_mismatch")
        by_role.setdefault(role, []).append(raw_record)
        names.add(path_name)
        total_bytes += size
    if (
        set(by_role) != EXPECTED_SINGLETON_ROLES | {DEPENDENCY_ROLE}
        or any(len(by_role[role]) != 1 for role in EXPECTED_SINGLETON_ROLES)
        or not by_role[DEPENDENCY_ROLE]
        or total_bytes > MAX_BUNDLE_BYTES
    ):
        raise SafeRunError("bundle_manifest_invalid")
    expected_entries = names | {"bundle-manifest.json"}
    try:
        observed_entries = {entry.name for entry in bundle_root.iterdir()}
        if any(not entry.is_file() for entry in bundle_root.iterdir()):
            raise SafeRunError("bundle_root_allowlist_invalid")
    except OSError as error:
        raise SafeRunError("bundle_root_allowlist_invalid") from error
    if not expected_entries.issubset(
        observed_entries
    ) or observed_entries - expected_entries not in (
        set(),
        {"dataset-metadata.json"},
    ):
        raise SafeRunError("bundle_root_allowlist_invalid")
    return by_role


def _identity_payload(
    manifest: Mapping[str, Any],
    records: Mapping[str, Sequence[Mapping[str, Any]]],
    run_config: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_config = dict(run_config)
    normalized_config["bundle_sha256"] = BUNDLE_PLACEHOLDER
    normalized_bytes = _canonical_json_bytes(normalized_config)
    normalized_record = dict(records["run_config"][0])
    normalized_record["bytes"] = len(normalized_bytes)
    normalized_record["sha256"] = _sha256_bytes(normalized_bytes)
    identity_records: list[dict[str, Any]] = []
    for role, role_records in records.items():
        if role == "run_config":
            identity_records.append(normalized_record)
        else:
            identity_records.extend(dict(record) for record in role_records)
    return {
        "schema_version": manifest.get("schema_version"),
        "bundle_format": manifest.get("bundle_format"),
        "provenance": manifest.get("provenance"),
        "competition": manifest.get("competition"),
        "kernel": manifest.get("kernel"),
        "files": sorted(identity_records, key=lambda item: str(item.get("path"))),
    }


def _verify_run_config(
    bundle_root: Path,
    manifest: Mapping[str, Any],
    records: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[dict[str, Any], dict[str, Path], tuple[Path, ...]]:
    if manifest.get("schema_version") != 1 or manifest.get("bundle_format") != BUNDLE_FORMAT:
        raise SafeRunError("bundle_manifest_invalid")
    bundle_sha256 = manifest.get("bundle_sha256")
    if not isinstance(bundle_sha256, str) or not HEX_64.fullmatch(bundle_sha256):
        raise SafeRunError("bundle_manifest_invalid")

    paths = {
        role: bundle_root / str(role_records[0]["path"])
        for role, role_records in records.items()
        if role in EXPECTED_SINGLETON_ROLES
    }
    dependency_paths = tuple(
        bundle_root / str(record["path"])
        for record in sorted(records[DEPENDENCY_ROLE], key=lambda item: str(item["path"]))
    )
    run_config = _json_object(
        _read_bounded(
            paths["run_config"],
            MAX_MANIFEST_BYTES,
            "run_config_invalid",
            allow_symlink=True,
        ),
        "run_config_invalid",
    )
    if run_config.get("schema_version") != 1:
        raise SafeRunError("run_config_invalid")
    if run_config.get("bundle_sha256") != bundle_sha256:
        raise SafeRunError("bundle_identity_mismatch")
    identity_digest = _sha256_bytes(
        _canonical_json_bytes(_identity_payload(manifest, records, run_config))
    )
    if identity_digest != bundle_sha256:
        raise SafeRunError("bundle_identity_mismatch")

    provenance = manifest.get("provenance")
    config_provenance = run_config.get("provenance")
    if not isinstance(provenance, dict) or not isinstance(config_provenance, dict):
        raise SafeRunError("provenance_invalid")
    commit = provenance.get("git_commit")
    if not isinstance(commit, str) or not HEX_40.fullmatch(commit):
        raise SafeRunError("provenance_invalid")
    if run_config.get("code_commit") != commit or config_provenance.get("git_commit") != commit:
        raise SafeRunError("provenance_invalid")
    expected_hashes = {
        "manifest_schema_sha256": records["manifest_schema"][0]["sha256"],
        "competition_config_sha256": records["competition_pointer"][0]["sha256"],
        "competition_contract_sha256": records["competition_contract"][0]["sha256"],
        "uv_lock_sha256": records["dependency_lock"][0]["sha256"],
    }
    if any(config_provenance.get(key) != value for key, value in expected_hashes.items()):
        raise SafeRunError("provenance_invalid")
    if config_provenance.get("decoder_packages") != REQUIRED_DECODER_PACKAGES:
        raise SafeRunError("decoder_provenance_invalid")
    competition = manifest.get("competition")
    config_competition = run_config.get("competition")
    if (
        not isinstance(competition, dict)
        or not isinstance(config_competition, dict)
        or competition.get("slug") != config_competition.get("slug")
        or not isinstance(competition.get("slug"), str)
        or not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,99}", str(competition.get("slug")))
    ):
        raise SafeRunError("competition_source_invalid")
    runtime = run_config.get("runtime")
    _validate_runtime_policy(runtime)
    _validate_output_policy(run_config.get("output_policy"))
    runtime_dependencies = run_config.get("runtime_dependencies")
    dependency_identity = [
        {"path": record["path"], "bytes": record["bytes"], "sha256": record["sha256"]}
        for record in sorted(records[DEPENDENCY_ROLE], key=lambda item: str(item["path"]))
    ]
    if (
        not isinstance(runtime_dependencies, dict)
        or runtime_dependencies.get("python_versions") != ["3.11", "3.12"]
        or runtime_dependencies.get("install_mode") != "pip-no-index-find-links"
        or runtime_dependencies.get("wheel_count") != len(dependency_identity)
        or runtime_dependencies.get("wheel_set_sha256")
        != _sha256_bytes(_canonical_json_bytes(dependency_identity))
    ):
        raise SafeRunError("runtime_dependency_policy_invalid")
    privacy = run_config.get("privacy")
    if (
        not isinstance(privacy, dict)
        or not isinstance(privacy.get("canary"), str)
        or not str(privacy.get("canary")).startswith("RSNA_PRIVATE_CANARY_")
        or privacy.get("minimum_export_cell") != 20
        or any(
            privacy.get(key) is not False
            for key in (
                "raw_identifiers",
                "raw_reports",
                "patient_metadata",
                "pixel_data",
                "private_tables",
            )
        )
    ):
        raise SafeRunError("privacy_policy_invalid")

    kernel = manifest.get("kernel")
    if (
        not isinstance(kernel, dict)
        or kernel.get("code_file") != "run.py"
        or not isinstance(kernel.get("sha256"), str)
        or not HEX_64.fullmatch(str(kernel.get("sha256")))
    ):
        raise SafeRunError("kernel_provenance_invalid")
    try:
        current_runner = Path(__file__).resolve(strict=True)
    except OSError as error:
        raise SafeRunError("kernel_provenance_invalid") from error
    if _sha256_file(current_runner) != kernel.get("sha256"):
        raise SafeRunError("kernel_provenance_invalid")
    return run_config, paths, dependency_paths


def _validate_output_policy(value: object) -> None:
    if not isinstance(value, dict):
        raise SafeRunError("output_policy_invalid")
    expected_private = [
        {
            "path": f"{OUTPUT_DIRECTORY}/{name}",
            "max_bytes": limits[0],
            **({"exact_bytes": limits[1]} if limits[1] is not None else {}),
        }
        for name, limits in PRIVATE_OUTPUT_POLICY.items()
    ]
    expected_downloadable = [
        {
            "path": f"{OUTPUT_DIRECTORY}/{name}",
            "kind": policy[0],
            "max_bytes": policy[1],
        }
        for name, policy in DOWNLOADABLE_OUTPUT_POLICY.items()
    ]
    expected_log = {
        "basename_pattern": SESSION_LOG_PATTERN,
        "kind": "log",
        "max_bytes": 2 * 1024 * 1024,
        "max_files": 1,
    }
    if (
        value.get("private_remote_only") != expected_private
        or value.get("downloadable") != expected_downloadable
        or value.get("session_log") != expected_log
        or value.get("max_remote_bytes") != 9 * 1024**3
        or value.get("max_download_bytes") != 4 * 1024**2
    ):
        raise SafeRunError("output_policy_invalid")


def _validate_runtime_policy(value: object) -> None:
    if value != {
        "internet": False,
        "accelerator": "cpu",
        "max_seconds": 21_600,
        "kill_before_seconds": 23_400,
    }:
        raise SafeRunError("runtime_policy_invalid")


def _scan_sensitive(payload: bytes, canary: str) -> None:
    if canary.encode() in payload or any(pattern.search(payload) for pattern in SENSITIVE_BYTES):
        raise SafeRunError("privacy_scan_failed")


def _scan_unstructured(payload: bytes, canary: str) -> None:
    if canary.encode() in payload or any(
        pattern.search(payload) for pattern in UNSTRUCTURED_SENSITIVE_BYTES
    ):
        raise SafeRunError("privacy_scan_failed")


def _suppressed_count(value: object) -> bool:
    return (
        not isinstance(value, bool) and isinstance(value, int) and (value == 0 or value >= 20)
    ) or value == "suppressed"


def _disclose_count(value: object, minimum_cell: int) -> str:
    """Coarsen one private count so complements and later snapshots stay non-exact."""

    if value == "suppressed":
        return DISCLOSED_LOW
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SafeRunError("aggregate_suppression_invalid")
    if value == 0:
        return DISCLOSED_ZERO
    if value < minimum_cell:
        return DISCLOSED_LOW
    lower = value - (value % minimum_cell)
    return f"range_{lower}_{lower + minimum_cell - 1}"


def _disclosed_count_interval(value: object, minimum_cell: int = 20) -> tuple[int, int]:
    """Validate a disclosed count token and return its inclusive public interval."""

    if value == DISCLOSED_ZERO:
        return 0, 0
    if value == DISCLOSED_LOW:
        return 1, minimum_cell - 1
    if value == DISCLOSED_HIGH:
        return minimum_cell, DISCLOSED_MAXIMUM
    if not isinstance(value, str):
        raise SafeRunError("aggregate_disclosure_invalid")
    match = DISCLOSED_RANGE.fullmatch(value)
    if match is None:
        raise SafeRunError("aggregate_disclosure_invalid")
    lower, upper = (int(part) for part in match.groups())
    if lower < minimum_cell or lower % minimum_cell or upper != lower + minimum_cell - 1:
        raise SafeRunError("aggregate_disclosure_invalid")
    return lower, upper


def _validate_exact_aggregates(
    aggregates: object,
    *,
    run_config: Mapping[str, Any],
) -> None:
    if not isinstance(aggregates, dict) or set(aggregates) != set(AGGREGATE_FIELDS):
        raise SafeRunError("aggregate_schema_invalid")
    for section, fields in AGGREGATE_FIELDS.items():
        value = aggregates.get(section)
        if not isinstance(value, dict) or set(value) != fields:
            raise SafeRunError("aggregate_schema_invalid")

    scope = aggregates["scope"]
    if (
        scope["mode"] not in {"full", "bounded"}
        or scope["source_context"] != run_config.get("source_context")
        or scope["example_test_only"] is not True
        or scope["hidden_test_evaluable"] is not False
    ):
        raise SafeRunError("aggregate_schema_invalid")
    count_sections = ("coverage", "quality", "labels", "duplicates", "qa")
    boolean_fields = {
        ("coverage", "complete"),
        ("labels", "official_only"),
    }
    overflow_boolean_fields = {
        ("duplicates", "near_slice_study_pair_space_overflow"),
        ("duplicates", "near_series_candidate_space_overflow"),
        ("duplicates", "near_report_candidate_space_overflow"),
    }
    for section in count_sections:
        for key, value in aggregates[section].items():
            if (section, key) in boolean_fields:
                if value is not True:
                    raise SafeRunError("aggregate_schema_invalid")
            elif (section, key) in overflow_boolean_fields:
                if not isinstance(value, bool):
                    raise SafeRunError("aggregate_schema_invalid")
            elif not _suppressed_count(value):
                raise SafeRunError("aggregate_suppression_invalid")
    duplicates = aggregates["duplicates"]
    if (
        duplicates["near_slice_unresolved_study_pairs"] != 0
        or duplicates["future_fold_crossings"] != 0
    ):
        raise SafeRunError("aggregate_integrity_invalid")
    overflow_fields = (
        (
            "near_slice_study_pair_space_overflow",
            "near_slice_study_pair_count_lower_bound",
            "near_slice_overflow_study_edges",
        ),
        (
            "near_series_candidate_space_overflow",
            "near_series_candidate_pair_count_lower_bound",
            "near_series_overflow_study_edges",
        ),
        (
            "near_report_candidate_space_overflow",
            "near_report_candidate_pair_count_lower_bound",
            "near_report_overflow_study_edges",
        ),
    )
    for flag_key, lower_bound_key, chain_edges_key in overflow_fields:
        overflowed = duplicates[flag_key]
        lower_bound = duplicates[lower_bound_key]
        chain_edges = duplicates[chain_edges_key]
        if overflowed:
            if (
                not isinstance(lower_bound, int)
                or isinstance(lower_bound, bool)
                or lower_bound < 20
            ):
                raise SafeRunError("aggregate_integrity_invalid")
        elif lower_bound != 0 or chain_edges != 0:
            raise SafeRunError("aggregate_integrity_invalid")
    chain_edge_values = tuple(duplicates[fields[2]] for fields in overflow_fields)
    candidate_edges = duplicates["candidate_edges"]
    minimum_chain_edges = sum(
        value if isinstance(value, int) and not isinstance(value, bool) else 1
        for value in chain_edge_values
        if value != 0
    )
    candidate_edges_are_numeric = isinstance(candidate_edges, int) and not isinstance(
        candidate_edges, bool
    )
    if minimum_chain_edges and candidate_edges == 0:
        raise SafeRunError("aggregate_integrity_invalid")
    if minimum_chain_edges >= 20 and not candidate_edges_are_numeric:
        raise SafeRunError("aggregate_integrity_invalid")
    if candidate_edges_are_numeric and candidate_edges < minimum_chain_edges:
        raise SafeRunError("aggregate_integrity_invalid")
    report_pair_keys = (
        "exact_report_raw_pairs",
        "exact_report_normalized_pairs",
        "exact_report_overlap_pairs",
        "exact_report_union_pairs",
    )
    report_pair_counts = tuple(duplicates[key] for key in report_pair_keys)
    if all(isinstance(value, int) and not isinstance(value, bool) for value in report_pair_counts):
        raw_pairs, normalized_pairs, overlap_pairs, union_pairs = report_pair_counts
        if union_pairs != raw_pairs + normalized_pairs - overlap_pairs:
            raise SafeRunError("aggregate_integrity_invalid")
    if aggregates["integrity"] != {
        "foreign_keys": True,
        "all_files_terminal": True,
        "all_series_terminal": True,
        "protected_graph_closed": True,
        "private_artifacts_complete": True,
        "five_levels_reconciled": True,
        "dicom_issue_dispositions_complete": True,
    }:
        raise SafeRunError("aggregate_integrity_invalid")
    if aggregates["quality"]["unexplained_dicom_issues"] != 0:
        raise SafeRunError("aggregate_integrity_invalid")
    if aggregates["labels"]["non_official_sources"] != 0:
        raise SafeRunError("aggregate_integrity_invalid")
    shift = aggregates["shift"]
    if shift["evaluation_scope"] != run_config.get("source_context"):
        raise SafeRunError("aggregate_schema_invalid")
    for feature in SHIFT_FEATURES:
        value = shift[feature]
        if not isinstance(value, str) or value not in SHIFT_STATUS_VALUES:
            raise SafeRunError("aggregate_suppression_invalid")
        expected = (
            "not_evaluable_test_reports_unavailable"
            if feature == "report_language"
            else "suppressed_low_test_support"
        )
        if value != expected:
            raise SafeRunError("aggregate_suppression_invalid")
    provenance = run_config.get("provenance")
    if not isinstance(provenance, dict) or aggregates["versions"] != {
        "manifest_version": provenance.get("manifest_version"),
        "group_version": provenance.get("group_version"),
        "label_version": provenance.get("label_version"),
        "preprocessing_version": provenance.get("preprocessing_version"),
    }:
        raise SafeRunError("aggregate_provenance_invalid")
    elapsed = aggregates["runtime"]["elapsed_seconds"]
    runtime = run_config.get("runtime")
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, int)
        or elapsed < 0
        or not isinstance(runtime, dict)
        or not isinstance(runtime.get("max_seconds"), int)
        or elapsed > runtime["max_seconds"]
    ):
        raise SafeRunError("aggregate_schema_invalid")


def _validate_private_summary(payload: object, run_config: Mapping[str, Any]) -> None:
    """Validate the runner's private aggregate envelope before any release transform."""

    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "artifact_type",
        "status",
        "provenance",
        "privacy",
        "aggregates",
    }:
        raise SafeRunError("summary_schema_invalid")
    if (
        payload.get("schema_version") != 1
        or payload.get("artifact_type") != "manifest-audit-aggregate"
        or payload.get("status") != "complete"
    ):
        raise SafeRunError("summary_schema_invalid")
    expected_provenance = run_config.get("provenance")
    provenance = payload.get("provenance")
    if not isinstance(expected_provenance, dict) or provenance != expected_provenance:
        raise SafeRunError("summary_provenance_invalid")
    config_privacy = run_config.get("privacy")
    if not isinstance(config_privacy, dict):
        raise SafeRunError("summary_privacy_invalid")
    expected_privacy = {key: value for key, value in config_privacy.items() if key != "canary"}
    if payload.get("privacy") != expected_privacy:
        raise SafeRunError("summary_privacy_invalid")
    aggregates = payload.get("aggregates")
    _validate_exact_aggregates(aggregates, run_config=run_config)


def _intervals_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return max(left[0], right[0]) <= min(left[1], right[1])


def _sum_interval(values: Sequence[tuple[int, int]]) -> tuple[int, int]:
    return sum(value[0] for value in values), sum(value[1] for value in values)


def _validate_disclosed_aggregates(
    aggregates: object,
    *,
    run_config: Mapping[str, Any],
) -> None:
    if not isinstance(aggregates, dict) or set(aggregates) != set(AGGREGATE_FIELDS):
        raise SafeRunError("aggregate_schema_invalid")
    for section, fields in AGGREGATE_FIELDS.items():
        value = aggregates.get(section)
        if not isinstance(value, dict) or set(value) != fields:
            raise SafeRunError("aggregate_schema_invalid")

    scope = aggregates["scope"]
    if (
        scope["mode"] not in {"full", "bounded"}
        or scope["source_context"] != run_config.get("source_context")
        or scope["example_test_only"] is not True
        or scope["hidden_test_evaluable"] is not False
    ):
        raise SafeRunError("aggregate_schema_invalid")

    privacy = run_config.get("privacy")
    if not isinstance(privacy, dict) or privacy.get("minimum_export_cell") != 20:
        raise SafeRunError("summary_privacy_invalid")
    minimum_cell = int(privacy["minimum_export_cell"])
    intervals: dict[tuple[str, str], tuple[int, int]] = {}
    for section, fields in COUNT_FIELDS.items():
        for key in fields:
            intervals[(section, key)] = _disclosed_count_interval(
                aggregates[section][key], minimum_cell
            )

    if aggregates["coverage"]["complete"] is not True:
        raise SafeRunError("aggregate_schema_invalid")
    if aggregates["labels"]["official_only"] is not True:
        raise SafeRunError("aggregate_schema_invalid")
    overflow_flags = (
        "near_slice_study_pair_space_overflow",
        "near_series_candidate_space_overflow",
        "near_report_candidate_space_overflow",
    )
    if any(not isinstance(aggregates["duplicates"][key], bool) for key in overflow_flags):
        raise SafeRunError("aggregate_schema_invalid")

    for total_key, part_keys in (
        ("studies_total", ("train_studies", "test_studies")),
        ("series_total", ("train_series", "test_series")),
    ):
        total = intervals[("coverage", total_key)]
        parts = _sum_interval([intervals[("coverage", key)] for key in part_keys])
        if not _intervals_overlap(total, parts):
            raise SafeRunError("aggregate_integrity_invalid")
    if not _intervals_overlap(
        intervals[("coverage", "files_total")],
        intervals[("coverage", "files_terminal")],
    ):
        raise SafeRunError("aggregate_integrity_invalid")

    labels = aggregates["labels"]
    if labels["non_official_sources"] != DISCLOSED_ZERO:
        raise SafeRunError("aggregate_integrity_invalid")
    label_parts = _sum_interval(
        [
            intervals[("labels", key)]
            for key in ("positive_cells", "negative_cells", "unknown_cells", "conflict_cells")
        ]
    )
    if not _intervals_overlap(intervals[("labels", "official_cells")], label_parts):
        raise SafeRunError("aggregate_integrity_invalid")

    duplicates = aggregates["duplicates"]
    if (
        duplicates["near_slice_unresolved_study_pairs"] != DISCLOSED_ZERO
        or duplicates["future_fold_crossings"] != DISCLOSED_ZERO
    ):
        raise SafeRunError("aggregate_integrity_invalid")
    overflow_fields = (
        (
            "near_slice_study_pair_space_overflow",
            "near_slice_study_pair_count_lower_bound",
            "near_slice_overflow_study_edges",
        ),
        (
            "near_series_candidate_space_overflow",
            "near_series_candidate_pair_count_lower_bound",
            "near_series_overflow_study_edges",
        ),
        (
            "near_report_candidate_space_overflow",
            "near_report_candidate_pair_count_lower_bound",
            "near_report_overflow_study_edges",
        ),
    )
    for flag_key, lower_bound_key, chain_edges_key in overflow_fields:
        lower_bound = intervals[("duplicates", lower_bound_key)]
        chain_edges = intervals[("duplicates", chain_edges_key)]
        if duplicates[flag_key]:
            if lower_bound[0] < minimum_cell:
                raise SafeRunError("aggregate_integrity_invalid")
        elif lower_bound != (0, 0) or chain_edges != (0, 0):
            raise SafeRunError("aggregate_integrity_invalid")

    chain_intervals = [
        intervals[("duplicates", chain_edges_key)]
        for _flag_key, _lower_bound_key, chain_edges_key in overflow_fields
    ]
    candidate_interval = intervals[("duplicates", "candidate_edges")]
    possible_chain_total = _sum_interval(chain_intervals)
    if candidate_interval[1] < possible_chain_total[0]:
        raise SafeRunError("aggregate_integrity_invalid")

    raw_pairs = intervals[("duplicates", "exact_report_raw_pairs")]
    normalized_pairs = intervals[("duplicates", "exact_report_normalized_pairs")]
    overlap_pairs = intervals[("duplicates", "exact_report_overlap_pairs")]
    union_pairs = intervals[("duplicates", "exact_report_union_pairs")]
    possible_union = (
        max(0, raw_pairs[0] + normalized_pairs[0] - overlap_pairs[1]),
        raw_pairs[1] + normalized_pairs[1] - overlap_pairs[0],
    )
    if not _intervals_overlap(union_pairs, possible_union):
        raise SafeRunError("aggregate_integrity_invalid")

    if aggregates["integrity"] != {
        "foreign_keys": True,
        "all_files_terminal": True,
        "all_series_terminal": True,
        "protected_graph_closed": True,
        "private_artifacts_complete": True,
        "five_levels_reconciled": True,
        "dicom_issue_dispositions_complete": True,
    }:
        raise SafeRunError("aggregate_integrity_invalid")
    if aggregates["quality"]["unexplained_dicom_issues"] != DISCLOSED_ZERO:
        raise SafeRunError("aggregate_integrity_invalid")
    shift = aggregates["shift"]
    if shift["evaluation_scope"] != run_config.get("source_context"):
        raise SafeRunError("aggregate_schema_invalid")
    for feature in SHIFT_FEATURES:
        expected = (
            "not_evaluable_test_reports_unavailable"
            if feature == "report_language"
            else "suppressed_low_test_support"
        )
        if shift[feature] != expected:
            raise SafeRunError("aggregate_suppression_invalid")
    provenance = run_config.get("provenance")
    if not isinstance(provenance, dict) or aggregates["versions"] != {
        "manifest_version": provenance.get("manifest_version"),
        "group_version": provenance.get("group_version"),
        "label_version": provenance.get("label_version"),
        "preprocessing_version": provenance.get("preprocessing_version"),
    }:
        raise SafeRunError("aggregate_provenance_invalid")
    elapsed = aggregates["runtime"]["elapsed_seconds"]
    runtime = run_config.get("runtime")
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, int)
        or elapsed < 0
        or not isinstance(runtime, dict)
        or not isinstance(runtime.get("max_seconds"), int)
        or elapsed > runtime["max_seconds"]
    ):
        raise SafeRunError("aggregate_schema_invalid")


def _apply_disclosure_control(
    payload: object,
    run_config: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply one release policy to JSON, Markdown, and every future snapshot."""

    _validate_private_summary(payload, run_config)
    if not isinstance(payload, dict):  # narrowed by _validate_private_summary
        raise SafeRunError("summary_schema_invalid")
    disclosed = copy.deepcopy(payload)
    disclosed["schema_version"] = 2
    disclosed["disclosure"] = dict(DISCLOSURE_POLICY)
    aggregates = disclosed["aggregates"]
    minimum_cell = 20
    for section, fields in COUNT_FIELDS.items():
        for key in fields:
            aggregates[section][key] = _disclose_count(aggregates[section][key], minimum_cell)
    for group in COMPLEMENTARY_COUNT_GROUPS:
        if any(aggregates[section][key] == DISCLOSED_LOW for section, key in group):
            for section, key in group:
                if aggregates[section][key] not in {DISCLOSED_ZERO, DISCLOSED_LOW}:
                    aggregates[section][key] = DISCLOSED_HIGH
    _validated_summary(disclosed, run_config)
    return disclosed


def _validated_summary(payload: object, run_config: Mapping[str, Any]) -> bytes:
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "artifact_type",
        "status",
        "provenance",
        "privacy",
        "disclosure",
        "aggregates",
    }:
        raise SafeRunError("summary_schema_invalid")
    if (
        payload.get("schema_version") != 2
        or payload.get("artifact_type") != "manifest-audit-aggregate"
        or payload.get("status") != "complete"
        or payload.get("disclosure") != DISCLOSURE_POLICY
    ):
        raise SafeRunError("summary_schema_invalid")
    expected_provenance = run_config.get("provenance")
    if (
        not isinstance(expected_provenance, dict)
        or payload.get("provenance") != expected_provenance
    ):
        raise SafeRunError("summary_provenance_invalid")
    config_privacy = run_config.get("privacy")
    if not isinstance(config_privacy, dict):
        raise SafeRunError("summary_privacy_invalid")
    expected_privacy = {key: value for key, value in config_privacy.items() if key != "canary"}
    if payload.get("privacy") != expected_privacy:
        raise SafeRunError("summary_privacy_invalid")
    aggregates = payload.get("aggregates")
    _validate_disclosed_aggregates(aggregates, run_config=run_config)
    encoded = _canonical_json_bytes(payload)
    if len(encoded) > MAX_SUMMARY_BYTES:
        raise SafeRunError("summary_size_invalid")
    if str(config_privacy["canary"]).encode() in encoded:
        raise SafeRunError("privacy_scan_failed")
    _scan_unstructured(_canonical_json_bytes(aggregates), str(config_privacy["canary"]))
    return encoded


def _write_summary(output_root: Path, payload: bytes) -> None:
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        if output_root.is_symlink() or not output_root.is_dir():
            raise SafeRunError("output_root_invalid")
        target = output_root / "sanitized_summary.json"
        temporary = output_root / ".sanitized_summary.json.tmp"
        if target.exists() or temporary.exists():
            raise SafeRunError("summary_output_exists")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        temporary.rename(target)
    except SafeRunError:
        raise
    except OSError as error:
        raise SafeRunError("summary_write_failed") from error


def _validate_sanitized_inventory(
    payload: bytes,
    *,
    run_config: Mapping[str, Any],
    documents: Mapping[str, bytes],
) -> None:
    inventory = _json_object(payload, "sanitized_inventory_invalid")
    if set(inventory) != {
        "schema_version",
        "artifact_type",
        "provenance",
        "privacy",
        "disclosure",
        "artifacts",
    }:
        raise SafeRunError("sanitized_inventory_invalid")
    config_privacy = run_config.get("privacy")
    if not isinstance(config_privacy, dict):
        raise SafeRunError("sanitized_inventory_invalid")
    expected_privacy = {key: value for key, value in config_privacy.items() if key != "canary"}
    if (
        inventory.get("schema_version") != 2
        or inventory.get("artifact_type") != "sanitized-artifact-inventory"
        or inventory.get("provenance") != run_config.get("provenance")
        or inventory.get("privacy") != expected_privacy
        or inventory.get("disclosure") != DISCLOSURE_POLICY
    ):
        raise SafeRunError("sanitized_inventory_invalid")
    artifacts = inventory.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(documents):
        raise SafeRunError("sanitized_inventory_invalid")
    observed_names: set[str] = set()
    for record in artifacts:
        if not isinstance(record, dict) or set(record) != {
            "name",
            "kind",
            "bytes",
            "sha256",
        }:
            raise SafeRunError("sanitized_inventory_invalid")
        name = record.get("name")
        size = record.get("bytes")
        digest = record.get("sha256")
        if (
            not isinstance(name, str)
            or name not in documents
            or name in observed_names
            or record.get("kind") != "documentation"
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size != len(documents[name])
            or not isinstance(digest, str)
            or digest != _sha256_bytes(documents[name])
        ):
            raise SafeRunError("sanitized_inventory_invalid")
        observed_names.add(name)
    if observed_names != set(documents):
        raise SafeRunError("sanitized_inventory_invalid")


def _validate_document(
    name: str,
    payload: bytes,
    run_config: Mapping[str, Any],
    aggregates: Mapping[str, Any],
) -> None:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SafeRunError("downloadable_encoding_invalid") from error
    lines = text.splitlines()
    if not lines or lines[0] != DOCUMENT_TITLES[name] or len(lines) > 256:
        raise SafeRunError("documentation_schema_invalid")
    allowed_keys = DOCUMENT_KEYS[name]
    expected_strings = {
        "full",
        "bounded",
        "true",
        "false",
        "not_evaluable",
        str(run_config.get("source_context")),
        *SHIFT_STATUS_VALUES,
        *(
            str(value).lower() if isinstance(value, bool) else str(value)
            for value in DISCLOSURE_POLICY.values()
        ),
        *(
            str(value).lower() if isinstance(value, bool) else str(value)
            for value in STRUCTURAL_GROUPING_STATUS.values()
        ),
    }
    provenance = run_config.get("provenance")
    if isinstance(provenance, dict):
        expected_strings.update(
            str(provenance[key])
            for key in (
                "manifest_version",
                "group_version",
                "label_version",
                "preprocessing_version",
            )
        )
    seen_keys: set[str] = set()
    seen_headings = {lines[0]}
    expected_values = dict(DISCLOSURE_POLICY)
    expected_values.update(STRUCTURAL_GROUPING_STATUS)
    expected_values.update(
        {
            key: value
            for section in aggregates.values()
            if isinstance(section, dict)
            for key, value in section.items()
        }
    )
    for line in lines[1:]:
        if not line:
            continue
        if line.startswith("#"):
            if line not in DOCUMENT_HEADINGS[name]:
                raise SafeRunError("documentation_schema_invalid")
            seen_headings.add(line)
            continue
        match = re.fullmatch(r"- ([a-z][a-z0-9_]{0,63}): ([A-Za-z0-9_.+-]+)", line)
        if match is None:
            raise SafeRunError("documentation_schema_invalid")
        key, value = match.groups()
        if key not in allowed_keys or key in seen_keys:
            raise SafeRunError("documentation_schema_invalid")
        seen_keys.add(key)
        expected = expected_values.get(key)
        expected_text = (
            "not_evaluable"
            if expected is None
            else str(expected).lower()
            if isinstance(expected, bool)
            else str(expected)
        )
        if value != expected_text:
            raise SafeRunError("documentation_value_mismatch")
        if any(key in fields for fields in COUNT_FIELDS.values()):
            _disclosed_count_interval(value)
            continue
        if value in expected_strings:
            continue
        if key not in {"elapsed_seconds", "minimum_export_cell", "interval_width"} or (
            re.fullmatch(r"0|[1-9][0-9]*", value) is None
        ):
            raise SafeRunError("documentation_suppression_invalid")
    if seen_keys != allowed_keys or seen_headings != DOCUMENT_HEADINGS[name]:
        raise SafeRunError("documentation_schema_invalid")
    _scan_unstructured(payload, str(run_config["privacy"]["canary"]))


def _markdown_value(value: object) -> str:
    if value is None:
        return "not_evaluable"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _render_disclosed_documents(
    aggregates: Mapping[str, Any],
    *,
    canary: str,
) -> dict[str, bytes]:
    disclosure = dict(DISCLOSURE_POLICY)
    duplicates = aggregates["duplicates"]
    scope = aggregates["scope"]
    layouts: dict[str, tuple[tuple[str, Mapping[str, Any]], ...]] = {
        "data_audit.md": (
            ("Disclosure", disclosure),
            ("Scope", scope),
            ("Coverage", aggregates["coverage"]),
            ("Quality", aggregates["quality"]),
            ("Labels", aggregates["labels"]),
            ("Integrity", aggregates["integrity"]),
            ("Versions", aggregates["versions"]),
            ("Runtime", aggregates["runtime"]),
        ),
        "leakage_audit.md": (
            ("Disclosure", disclosure),
            (
                "Duplicates",
                {
                    key: value
                    for key, value in duplicates.items()
                    if key
                    not in {
                        "protected_components",
                        "cross_split_components",
                        "future_fold_crossings",
                    }
                },
            ),
            (
                "Protected components",
                {
                    "protected_components": duplicates["protected_components"],
                    "cross_split_components": duplicates["cross_split_components"],
                },
            ),
            (
                "Structural grouping checks",
                {
                    **STRUCTURAL_GROUPING_STATUS,
                    "future_fold_crossings": duplicates["future_fold_crossings"],
                },
            ),
            ("Integrity", aggregates["integrity"]),
        ),
        "domain_shift_audit.md": (
            ("Disclosure", disclosure),
            (
                "Scope",
                {key: value for key, value in scope.items() if key != "hidden_test_evaluable"},
            ),
            ("Shift", aggregates["shift"]),
            ("Limitations", {"hidden_test_evaluable": scope["hidden_test_evaluable"]}),
            ("Integrity", aggregates["integrity"]),
        ),
    }
    documents: dict[str, bytes] = {}
    for name, sections in layouts.items():
        lines = [DOCUMENT_TITLES[name], ""]
        for heading, values in sections:
            lines.extend((f"## {heading}", ""))
            lines.extend(f"- {key}: {_markdown_value(values[key])}" for key in sorted(values))
            lines.append("")
        payload = "\n".join(lines).encode()
        _scan_unstructured(payload, canary)
        documents[name] = payload
    return documents


def _replace_bounded_output(path: Path, payload: bytes, maximum: int) -> None:
    if not path.is_file() or path.is_symlink() or not payload or len(payload) > maximum:
        raise SafeRunError("disclosure_rewrite_invalid")
    temporary = path.parent / f".{path.name}.disclosure.tmp"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        temporary.replace(path)
    except OSError as error:
        with contextlib.suppress(OSError):
            temporary.unlink()
        raise SafeRunError("disclosure_rewrite_invalid") from error


def _rewrite_disclosed_outputs(
    output_root: Path,
    *,
    run_config: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> dict[str, bytes]:
    aggregates = summary.get("aggregates")
    if not isinstance(aggregates, dict):
        raise SafeRunError("summary_schema_invalid")
    canary = str(run_config["privacy"]["canary"])
    documents = _render_disclosed_documents(aggregates, canary=canary)
    for name, payload in documents.items():
        _replace_bounded_output(output_root / name, payload, DOWNLOADABLE_OUTPUT_POLICY[name][1])
    inventory = {
        "schema_version": 2,
        "artifact_type": "sanitized-artifact-inventory",
        "provenance": summary["provenance"],
        "privacy": summary["privacy"],
        "disclosure": dict(DISCLOSURE_POLICY),
        "artifacts": [
            {
                "name": name,
                "kind": "documentation",
                "bytes": len(payload),
                "sha256": _sha256_bytes(payload),
            }
            for name, payload in sorted(documents.items())
        ],
    }
    inventory_payload = _canonical_json_bytes(inventory)
    _replace_bounded_output(
        output_root / "sanitized_artifact_inventory.json",
        inventory_payload,
        DOWNLOADABLE_OUTPUT_POLICY["sanitized_artifact_inventory.json"][1],
    )
    return documents


def _validate_working_outputs(
    output_root: Path,
    run_config: Mapping[str, Any],
    aggregates: Mapping[str, Any],
) -> None:
    try:
        if output_root.is_symlink() or not output_root.is_dir():
            raise SafeRunError("output_root_invalid")
        entries = sorted(output_root.iterdir(), key=lambda item: item.name)
    except OSError as error:
        raise SafeRunError("output_root_invalid") from error
    expected_names = set(PRIVATE_OUTPUT_POLICY) | (
        set(DOWNLOADABLE_OUTPUT_POLICY) - {"sanitized_summary.json"}
    )
    if {entry.name for entry in entries} != expected_names:
        raise SafeRunError("working_output_allowlist_failed")
    documents: dict[str, bytes] = {}
    total_bytes = 0
    for entry in entries:
        try:
            if entry.is_symlink() or not entry.is_file():
                raise SafeRunError("working_output_allowlist_failed")
            size = entry.stat().st_size
        except OSError as error:
            raise SafeRunError("working_output_allowlist_failed") from error
        if size <= 0:
            raise SafeRunError("working_output_size_invalid")
        total_bytes += size
        if entry.name in PRIVATE_OUTPUT_POLICY:
            maximum, exact = PRIVATE_OUTPUT_POLICY[entry.name]
            if size > maximum or (exact is not None and size != exact):
                raise SafeRunError("working_output_size_invalid")
            continue
        _kind, maximum = DOWNLOADABLE_OUTPUT_POLICY[entry.name]
        payload = _read_bounded(entry, maximum, "working_output_size_invalid")
        if entry.suffix == ".md":
            _validate_document(entry.name, payload, run_config, aggregates)
            documents[entry.name] = payload
    if total_bytes > 9 * 1024**3:
        raise SafeRunError("working_output_size_invalid")
    inventory_path = output_root / "sanitized_artifact_inventory.json"
    inventory_payload = _read_bounded(
        inventory_path,
        DOWNLOADABLE_OUTPUT_POLICY[inventory_path.name][1],
        "working_output_size_invalid",
    )
    _validate_sanitized_inventory(
        inventory_payload,
        run_config=run_config,
        documents=documents,
    )


def _runner_spec(run_config: Mapping[str, Any]) -> tuple[str, str]:
    runner = run_config.get("runner")
    if not isinstance(runner, dict):
        raise SafeRunError("runner_config_invalid")
    module = runner.get("module")
    callable_name = runner.get("callable")
    arguments = runner.get("arguments")
    expected_arguments = {
        "input_root": "competition_input",
        "output_root": "working_output",
        "manifest_schema_path": "bundle_manifest_schema",
        "competition_config_path": "bundle_competition_config",
        "competition_contract_path": "bundle_competition_contract",
        "run_config_path": "bundle_run_config",
    }
    if (
        not isinstance(module, str)
        or not SAFE_IMPORT.fullmatch(module)
        or not isinstance(callable_name, str)
        or not SAFE_CALLABLE.fullmatch(callable_name)
        or arguments != expected_arguments
    ):
        raise SafeRunError("runner_config_invalid")
    return module, callable_name


def _validate_runtime_wheel_names(paths: Sequence[Path]) -> None:
    for path in paths:
        name = path.name.lower()
        if (
            not SAFE_NAME.fullmatch(path.name)
            or not name.endswith(".whl")
            or "macosx" in name
            or "win32" in name
            or "win_amd64" in name
            or "arm64" in name
            or "aarch64" in name
            or "musllinux" in name
        ):
            raise SafeRunError("runtime_wheel_platform_invalid")
        if "-none-any.whl" not in name and not (
            "manylinux" in name
            and ("x86_64" in name or "amd64" in name)
            and ("cp311" in name or "cp312" in name)
        ):
            raise SafeRunError("runtime_wheel_platform_invalid")


def _install_offline_runtime(
    bundle_root: Path,
    project_wheel: Path,
    dependency_wheels: Sequence[Path],
) -> Path:
    if sys.version_info[:2] not in {(3, 11), (3, 12)}:
        raise SafeRunError("python_version_unsupported")
    _validate_runtime_wheel_names(dependency_wheels)
    runtime_root = Path(tempfile.mkdtemp(prefix="rsna-knee-runtime-"))
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


def _run_audit(
    *,
    input_root: Path,
    output_root: Path,
    run_config: Mapping[str, Any],
    paths: Mapping[str, Path],
    dependency_paths: Sequence[Path],
    deadline_seconds: float,
) -> bytes:
    module_name, callable_name = _runner_spec(run_config)
    competition = run_config["competition"]
    if not isinstance(competition, dict) or not isinstance(competition.get("slug"), str):
        raise SafeRunError("competition_source_invalid")
    competition_root = _find_competition_root(input_root)
    wheel_path = paths["project_wheel"]
    deadline_at = time.monotonic() + deadline_seconds
    with _enforce_self_deadline(deadline_at - time.monotonic()), _silence_process_output():
        runtime_root = _install_offline_runtime(wheel_path.parent, wheel_path, dependency_paths)
    sys.path.insert(0, str(runtime_root))
    package_root = module_name.split(".", 1)[0]
    displaced_modules = {
        name: module
        for name, module in tuple(sys.modules.items())
        if name == package_root or name.startswith(f"{package_root}.")
    }
    for name in displaced_modules:
        del sys.modules[name]
    discard = _Discard()
    loaded_module: object | None = None
    try:
        with (
            _enforce_self_deadline(deadline_at - time.monotonic()),
            _silence_process_output(),
            contextlib.redirect_stdout(discard),
            contextlib.redirect_stderr(discard),
        ):
            loaded_module = importlib.import_module(module_name)
            runner = getattr(loaded_module, callable_name, None)
            if not callable(runner):
                raise SafeRunError("runner_not_callable")
            try:
                result = runner(
                    input_root=competition_root,
                    output_root=output_root,
                    manifest_schema_path=paths["manifest_schema"],
                    competition_config_path=paths["competition_pointer"],
                    competition_contract_path=paths["competition_contract"],
                    run_config_path=paths["run_config"],
                )
            except SafeRunError as error:
                if error.code == "self_deadline_exceeded":
                    raise
                raise SafeRunError("runner_failed") from None
            except BaseException as error:
                raise SafeRunError(_runner_failure_code(error, loaded_module)) from None
        disclosed = _apply_disclosure_control(result, run_config)
        _rewrite_disclosed_outputs(output_root, run_config=run_config, summary=disclosed)
        summary = _validated_summary(disclosed, run_config)
        _validate_working_outputs(output_root, run_config, disclosed["aggregates"])
        return summary
    except SafeRunError:
        raise
    except BaseException as error:
        raise SafeRunError(_runner_failure_code(error, loaded_module)) from None
    finally:
        for name in tuple(sys.modules):
            if name == package_root or name.startswith(f"{package_root}."):
                del sys.modules[name]
        sys.modules.update(displaced_modules)
        if sys.path and sys.path[0] == str(runtime_root):
            sys.path.pop(0)
        shutil.rmtree(runtime_root, ignore_errors=True)


def main() -> int:
    phase = "bundle"
    started = time.monotonic()
    try:
        input_root = Path(os.environ.get("KAGGLE_INPUT_ROOT", "/kaggle/input"))
        working_root = Path(os.environ.get("KAGGLE_WORKING_ROOT", "/kaggle/working"))
        output_root = working_root / OUTPUT_DIRECTORY
        _safe_event("manifest_audit_started")
        bundle_root, manifest = _find_bundle(input_root)
        records = _validated_records(bundle_root, manifest)
        run_config, paths, dependency_paths = _verify_run_config(bundle_root, manifest, records)
        runtime = run_config["runtime"]
        if not isinstance(runtime, dict) or not isinstance(runtime.get("max_seconds"), int):
            raise SafeRunError("runtime_policy_invalid")
        remaining_seconds = float(runtime["max_seconds"]) - (time.monotonic() - started)
        phase = "audit"
        summary = _run_audit(
            input_root=input_root,
            output_root=output_root,
            run_config=run_config,
            paths=paths,
            dependency_paths=dependency_paths,
            deadline_seconds=remaining_seconds,
        )
        phase = "summary"
        _write_summary(output_root, summary)
        _safe_event("manifest_audit_complete")
        return 0
    except SafeRunError as error:
        _safe_event("manifest_audit_failed", phase=phase, code=error.code)
        return 2
    except BaseException:
        _safe_event("manifest_audit_failed", phase=phase, code="internal_error")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
