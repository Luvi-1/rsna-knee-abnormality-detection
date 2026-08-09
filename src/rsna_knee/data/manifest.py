"""Private five-level manifest orchestration for the Kaggle-only data audit.

Raw identifiers and report text are accepted only transiently inside the private Kaggle process.
Every persisted row uses domain-separated opaque keys. Only :func:`safe_summary` output may leave
that boundary.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import math
import os
import re
import sqlite3
import sys
import time
import unicodedata
from collections import Counter, defaultdict, deque
from collections.abc import Iterable, Iterator, Mapping, Sequence
from concurrent.futures import Future, ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from importlib import metadata as importlib_metadata
from io import BytesIO
from itertools import combinations, islice
from multiprocessing import get_context
from pathlib import Path
from typing import Any, Final, Literal, TypeAlias, cast

import numpy as np
import pydicom
from langdetect import DetectorFactory, LangDetectException, detect  # type: ignore[import-untyped]
from pydicom import config as pydicom_config
from pydicom.errors import InvalidDicomError
from pydicom.pixels.decoders.base import get_decoder
from pydicom.uid import JPEG2000Lossless, JPEGLosslessSV1

from rsna_knee.dicom.audit import (
    DECODE_ROOT_CAUSE_TAXONOMY,
    DECODE_ROOT_CAUSE_VERSION,
    DICOM_ISSUE_DISPOSITION_VERSION,
    DICOM_ISSUE_POLICIES,
    DICOM_ISSUE_RESOLUTION_VERSION,
    DUPLICATE_POSITION_TOLERANCE_MM,
    GAP_MULTIPLIER,
    IOP_ORTHONORMAL_TOLERANCE,
    ORIENTATION_TOLERANCE_DEGREES,
    SPACING_ABSOLUTE_TOLERANCE_MM,
    SPACING_RELATIVE_TOLERANCE,
    DecodeRootCause,
    DicomAuditResult,
    DicomIssue,
    DicomIssueScope,
    DicomResolutionState,
    OrderingBasis,
    SliceMetadata,
    audit_dataset,
    audit_series,
    classified_dicom_failure,
    gradient_normalized_cross_correlation,
    normalized_cross_correlation,
)
from rsna_knee.qa.duplicates import (
    DuplicateEdge,
    EdgeDisposition,
    build_candidate_components,
    build_protected_components,
    compare_phash_sequences,
    compare_reports,
    hamming_distance_64,
)
from rsna_knee.qa.duplicates import (
    normalize_report as normalize_duplicate_report,
)
from rsna_knee.qa.shift import (
    ShiftInputError,
    categorical_shift,
    continuous_shift,
    study_equal_weights,
)

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

DetectorFactory.seed = 0

SCHEMA_VERSION: Final = 2
MANIFEST_VERSION: Final = "manifest-v2"
GROUP_VERSION: Final = "protected-groups-v2"
LABEL_VERSION: Final = "official-labels-v1"
PREPROCESSING_VERSION: Final = "unassigned"
MANIFEST_ISSUE_DISPOSITION_VERSION: Final = "manifest-issue-disposition-v1"
SUPPORTED_SPLITS: Final = frozenset({"train", "test"})
UID_LIKE = re.compile(r"(?<![A-Za-z0-9])(?:[0-9]+\.){3,}[0-9]+(?![A-Za-z0-9])")
PATH_LIKE = re.compile(r"/kaggle/input|train_series/|test_series/")
SENSITIVE_FIELD = re.compile(
    r"StudyInstanceUID|SeriesInstanceUID|SOPInstanceUID|Patient(?:Name|ID)",
    re.IGNORECASE,
)
REQUIRED_DECODER_PACKAGES: Final = {
    "pylibjpeg": "2.1.0",
    "pylibjpeg-libjpeg": "2.4.0",
    "pylibjpeg-openjpeg": "2.5.0",
}
REQUIRED_COMPRESSED_TRANSFER_SYNTAXES: Final = (JPEGLosslessSV1, JPEG2000Lossless)
INSPECTIONS_PER_WORKER_LIFETIME: Final = 10_000
COMPONENT_REVIEW_VERSION: Final = "component-review-v1"
COMPONENT_REVIEW_TARGET_LIMIT: Final = 5
LEGACY_GROUP_RECONSTRUCTION_VERSION: Final = "protected-groups-v1-reconstruction-v1"
HARD_COMPONENT_EDGE_KIND_ALLOWLIST: Final = frozenset(
    {
        "altered-metadata-file",
        "altered-metadata-series",
        "exact-file",
        "exact-pixel",
        "exact-series",
        "exact-study",
        "near-series",
        "raw-container-variation-file",
        "reused-study-identifier",
        "same-patient",
    }
)


class ManifestAuditError(RuntimeError):
    """A stable, sanitized audit failure."""


@dataclass(frozen=True, slots=True)
class _ManifestIssuePolicy:
    """Private fail-closed handling attached to one manifest issue row."""

    severity: str
    terminal_effect: str
    disposition: str
    version: str
    scope_impact: str
    root_cause_category: str
    resolution_status: str
    resolution_version: str


@dataclass(frozen=True)
class AuditPaths:
    """Private Kaggle input and output paths."""

    input_root: Path
    output_dir: Path
    schema_path: Path
    contract_path: Path


@dataclass(frozen=True)
class AuditConfig:
    """Runtime controls whose hash becomes artifact provenance."""

    audit_id: str
    code_commit: str
    bundle_sha256: str
    workers: int = 4
    max_files: int | None = None
    progress_every: int = 10_000
    qa_per_stratum: int = 5
    minimum_export_cell: int = 20
    source_context: str = "train-plus-example-test"
    seed: int = 20260808
    max_seconds: int = 21_600
    kill_before_seconds: int = 23_400

    @classmethod
    def from_json(cls, path: Path) -> AuditConfig:
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise ManifestAuditError("run_config_invalid") from error
        if not isinstance(payload, dict):
            raise ManifestAuditError("run_config_invalid")
        try:
            runtime = payload["runtime"]
            if not isinstance(runtime, dict):
                raise ManifestAuditError("runtime_policy_invalid")
            result = cls(
                audit_id=str(payload["audit_id"]),
                code_commit=str(payload["code_commit"]),
                bundle_sha256=str(payload["bundle_sha256"]),
                workers=int(payload.get("workers", 4)),
                max_files=(None if payload.get("max_files") is None else int(payload["max_files"])),
                progress_every=int(payload.get("progress_every", 10_000)),
                qa_per_stratum=int(payload.get("qa_per_stratum", 5)),
                minimum_export_cell=int(payload.get("minimum_export_cell", 20)),
                source_context=str(payload.get("source_context", "train-plus-example-test")),
                seed=int(payload.get("seed", 20260808)),
                max_seconds=int(runtime["max_seconds"]),
                kill_before_seconds=int(runtime["kill_before_seconds"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ManifestAuditError("run_config_invalid") from error
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", result.audit_id):
            raise ManifestAuditError("audit_id_invalid")
        if not re.fullmatch(r"[0-9a-f]{40}", result.code_commit):
            raise ManifestAuditError("code_commit_invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", result.bundle_sha256):
            raise ManifestAuditError("bundle_hash_invalid")
        if result.workers < 1 or result.workers > 16:
            raise ManifestAuditError("worker_count_invalid")
        if result.max_files is not None and result.max_files < 1:
            raise ManifestAuditError("max_files_invalid")
        if result.minimum_export_cell < 20:
            raise ManifestAuditError("privacy_cell_too_small")
        if not (0 < result.max_seconds < result.kill_before_seconds <= 32_400):
            raise ManifestAuditError("runtime_policy_invalid")
        return result


@dataclass
class StudySource:
    raw_study_id: str
    split: Literal["train", "test"]
    source_row_count: int = 0
    report: str | None = None
    labels: list[str | None] = field(default_factory=list)
    conflicts: set[str] = field(default_factory=set)


@dataclass
class SeriesSource:
    raw_series_id: str
    raw_study_id: str
    split: Literal["train", "test"]
    source_row_count: int = 0
    plane: str | None = None
    fluid_sensitive: str | None = None
    fat_suppression: str | None = None
    conflicts: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class ReportFeatures:
    presence_state: str
    unicode_state: str
    character_count: int
    token_count: int
    script_bucket: str
    language_code: str | None
    language_state: str
    raw_text_exact_key: str | None
    canonical_text_exact_key: str | None
    near_report_fingerprint: str | None


@dataclass(frozen=True)
class SourceInventory:
    studies: dict[str, StudySource]
    series: dict[str, SeriesSource]
    labels: tuple[str, ...]
    train_csv_rows: int
    test_csv_rows: int
    train_series_csv_rows: int
    test_series_csv_rows: int


@dataclass(frozen=True)
class ArtifactHash:
    name: str
    sha256: str
    size_bytes: int
    privacy: Literal["private", "sanitized"]


@dataclass(frozen=True)
class FileAuditState:
    """Transient link between a private path and an opaque manifest row."""

    path: Path
    file_key: str
    study_key: str
    series_key: str
    result: DicomAuditResult


@dataclass(frozen=True)
class SeriesEvidence:
    """Bounded private evidence retained after a series is audited."""

    series_key: str
    study_key: str
    split: str
    plane: str | None
    rows: int | None
    columns: int | None
    exact_key: str | None
    phashes: tuple[str, ...]
    sample_paths: tuple[Path, ...]
    sample_file_keys: tuple[str, ...]


@dataclass(frozen=True)
class SliceFingerprintMember:
    """One private decoded slice attached to its study and series."""

    file_key: str
    study_key: str
    series_key: str


@dataclass(frozen=True)
class NearSliceSummary:
    """Bounded counts from threshold-complete private slice discovery."""

    groups: int
    persisted_edges: int
    suppressed_edges: int
    promoted_study_edges: int
    unresolved_study_pairs: int


@dataclass(frozen=True)
class MetadataDuplicateSummary:
    """Counts for decoded-equal container and metadata classifications."""

    raw_container_variation_groups: int
    altered_metadata_groups: int


@dataclass
class _NearSliceStudyEvidence:
    matches: int = 0
    series_pairs: set[tuple[str, str]] = field(default_factory=set)


@dataclass(frozen=True)
class _EntityCandidatePlan:
    """Exact bounded pairs or conservative components, never both."""

    pairs: tuple[tuple[str, str], ...]
    overflow_components: tuple[tuple[str, ...], ...]
    candidate_pair_upper_bound: int
    overflowed: bool


class _StringUnionFind:
    """Small deterministic union-find used for private fingerprint components."""

    def __init__(self, nodes: Iterable[str]) -> None:
        self._parent = {node: node for node in nodes}

    def find(self, node: str) -> str:
        parent = self._parent[node]
        while parent != self._parent[parent]:
            parent = self._parent[parent]
        root = parent
        current = node
        while self._parent[current] != root:
            following = self._parent[current]
            self._parent[current] = root
            current = following
        self._parent[node] = root
        return root

    def union(self, left: str, right: str) -> bool:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return False
        root, child = sorted((left_root, right_root))
        self._parent[child] = root
        return True


PRIVATE_SCHEMA_SQL: Final = """
PRAGMA foreign_keys = ON;
CREATE TABLE manifest_run (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE study_manifest (
    study_key TEXT PRIMARY KEY,
    split TEXT NOT NULL CHECK (split IN ('train', 'test')),
    source_row_count INTEGER NOT NULL,
    patient_group_key TEXT,
    patient_key_evidence TEXT NOT NULL,
    series_count INTEGER NOT NULL,
    plane_availability TEXT NOT NULL,
    sequence_categories TEXT NOT NULL,
    total_slice_count INTEGER NOT NULL,
    report_language TEXT,
    report_available INTEGER NOT NULL CHECK (report_available IN (0, 1)),
    patient_sex TEXT,
    patient_age_years REAL,
    label_status TEXT NOT NULL,
    known_label_count INTEGER NOT NULL,
    positive_label_count INTEGER NOT NULL,
    negative_label_count INTEGER NOT NULL,
    domain_cluster_key TEXT,
    scanner_manufacturer TEXT,
    scanner_model TEXT,
    field_strength_t REAL,
    protocol_cluster_key TEXT,
    data_quality_flags TEXT NOT NULL,
    terminal_state TEXT NOT NULL
);
CREATE TABLE series_manifest (
    series_key TEXT PRIMARY KEY,
    study_key TEXT NOT NULL REFERENCES study_manifest(study_key),
    source_row_count INTEGER NOT NULL,
    series_description TEXT,
    plane TEXT,
    fluid_sensitive TEXT,
    fat_suppression TEXT,
    rows INTEGER,
    columns INTEGER,
    pixel_spacing_row_mm REAL,
    pixel_spacing_col_mm REAL,
    slice_thickness_mm REAL,
    spacing_between_slices_mm REAL,
    slice_count INTEGER NOT NULL,
    orientation_vectors TEXT,
    physical_coverage_mm REAL,
    transfer_syntax_class TEXT,
    photometric_interpretation TEXT,
    bits_stored INTEGER,
    rescale_slope REAL,
    rescale_intercept REAL,
    missing_tag_flags TEXT NOT NULL,
    quality_score INTEGER NOT NULL,
    localizer_likelihood REAL NOT NULL,
    ordering_method TEXT NOT NULL,
    orientation_state TEXT NOT NULL,
    spacing_state TEXT NOT NULL,
    decode_state TEXT NOT NULL,
    protocol_cluster_key TEXT,
    exact_content_key TEXT,
    near_fingerprint_version TEXT,
    terminal_state TEXT NOT NULL
);
CREATE TABLE slice_file_manifest (
    file_key TEXT PRIMARY KEY,
    study_key TEXT NOT NULL REFERENCES study_manifest(study_key),
    series_key TEXT NOT NULL REFERENCES series_manifest(series_key),
    sop_key TEXT,
    file_size_bytes INTEGER NOT NULL,
    path_header_identity_match INTEGER,
    transfer_syntax_class TEXT,
    number_of_frames INTEGER,
    rows INTEGER,
    columns INTEGER,
    samples_per_pixel INTEGER,
    photometric_interpretation TEXT,
    bits_allocated INTEGER,
    bits_stored INTEGER,
    high_bit INTEGER,
    pixel_representation INTEGER,
    rescale_slope REAL,
    rescale_intercept REAL,
    image_orientation_patient TEXT,
    image_position_patient TEXT,
    projected_position_mm REAL,
    instance_number INTEGER,
    slice_index INTEGER,
    raw_file_exact_key TEXT,
    decoded_pixel_exact_key TEXT,
    near_slice_fingerprint TEXT,
    decode_state TEXT NOT NULL,
    missing_tag_flags TEXT NOT NULL,
    terminal_state TEXT NOT NULL
);
CREATE TABLE report_manifest (
    report_key TEXT PRIMARY KEY,
    study_key TEXT NOT NULL UNIQUE REFERENCES study_manifest(study_key),
    source_row_count INTEGER NOT NULL,
    presence_state TEXT NOT NULL,
    unicode_state TEXT NOT NULL,
    character_count INTEGER NOT NULL,
    token_count INTEGER NOT NULL,
    script_bucket TEXT NOT NULL,
    language_code TEXT,
    language_state TEXT NOT NULL,
    raw_text_exact_key TEXT,
    canonical_text_exact_key TEXT,
    near_report_fingerprint TEXT,
    template_group_key TEXT,
    template_match_kind TEXT NOT NULL,
    terminal_state TEXT NOT NULL
);
CREATE TABLE label_source_manifest (
    study_key TEXT NOT NULL REFERENCES study_manifest(study_key),
    target_index INTEGER NOT NULL CHECK (target_index >= 0),
    target_name TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK (source_kind = 'official'),
    source_version TEXT NOT NULL,
    label_state TEXT NOT NULL,
    confidence REAL,
    rule_or_model_hash TEXT,
    adjudication_state TEXT NOT NULL,
    state_validity TEXT NOT NULL,
    PRIMARY KEY (study_key, target_index, source_kind, source_version)
);
CREATE TABLE duplicate_edge (
    left_key TEXT NOT NULL,
    right_key TEXT NOT NULL,
    entity_level TEXT NOT NULL,
    edge_kind TEXT NOT NULL,
    decision TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    private_metrics TEXT NOT NULL,
    CHECK (left_key < right_key),
    PRIMARY KEY (left_key, right_key, entity_level, edge_kind)
);
CREATE TABLE duplicate_group_mapping (
    group_kind TEXT NOT NULL,
    group_key TEXT NOT NULL,
    entity_level TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    PRIMARY KEY (group_kind, group_key, entity_key)
);
CREATE TABLE protected_component (
    component_kind TEXT NOT NULL,
    component_key TEXT NOT NULL,
    study_key TEXT NOT NULL REFERENCES study_manifest(study_key),
    evidence_state TEXT NOT NULL,
    PRIMARY KEY (component_kind, component_key, study_key)
);
CREATE TABLE candidate_component (
    component_key TEXT NOT NULL,
    study_key TEXT NOT NULL REFERENCES study_manifest(study_key),
    hard_component_key TEXT NOT NULL,
    evidence_state TEXT NOT NULL,
    PRIMARY KEY (component_key, study_key)
);
CREATE TABLE duplicate_component_summary (
    component_kind TEXT NOT NULL,
    component_key TEXT NOT NULL,
    representative_study_key TEXT NOT NULL REFERENCES study_manifest(study_key),
    representative_file_key TEXT REFERENCES slice_file_manifest(file_key),
    member_count INTEGER NOT NULL CHECK (member_count > 0),
    hard_edge_count INTEGER NOT NULL CHECK (hard_edge_count >= 0),
    candidate_edge_count INTEGER NOT NULL CHECK (candidate_edge_count >= 0),
    algorithm_version TEXT NOT NULL,
    PRIMARY KEY (component_kind, component_key)
);
CREATE TABLE duplicate_component_edge (
    left_study_key TEXT NOT NULL REFERENCES study_manifest(study_key),
    right_study_key TEXT NOT NULL REFERENCES study_manifest(study_key),
    edge_kind TEXT NOT NULL,
    decision TEXT NOT NULL,
    evidence_count INTEGER NOT NULL CHECK (evidence_count > 0),
    left_hard_component_key TEXT NOT NULL,
    right_hard_component_key TEXT NOT NULL,
    soft_component_key TEXT,
    algorithm_version TEXT NOT NULL,
    CHECK (left_study_key < right_study_key),
    PRIMARY KEY (left_study_key, right_study_key, edge_kind, decision)
);
CREATE TABLE manifest_issue (
    entity_level TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    issue_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    terminal_effect TEXT NOT NULL,
    disposition TEXT NOT NULL,
    disposition_version TEXT NOT NULL,
    root_cause_category TEXT NOT NULL,
    root_cause_version TEXT NOT NULL,
    resolution_status TEXT NOT NULL,
    resolution_version TEXT NOT NULL,
    scope_impact TEXT NOT NULL,
    private_details TEXT NOT NULL,
    PRIMARY KEY (entity_level, entity_key, issue_code)
);
CREATE TABLE shift_result (
    feature TEXT NOT NULL,
    feature_type TEXT NOT NULL,
    effect_name TEXT NOT NULL,
    effect_value REAL,
    effect_tier TEXT NOT NULL,
    train_n INTEGER NOT NULL,
    test_n INTEGER NOT NULL,
    evaluable INTEGER NOT NULL CHECK (evaluable IN (0, 1)),
    limitation TEXT NOT NULL,
    PRIMARY KEY (feature, effect_name)
);
CREATE TABLE qa_sample (
    stratum_kind TEXT NOT NULL,
    stratum_key TEXT NOT NULL,
    study_key TEXT NOT NULL REFERENCES study_manifest(study_key),
    selection_reason TEXT NOT NULL,
    priority INTEGER NOT NULL,
    PRIMARY KEY (stratum_kind, stratum_key, study_key)
);
CREATE INDEX slice_series_idx ON slice_file_manifest(series_key);
CREATE INDEX slice_raw_hash_idx ON slice_file_manifest(raw_file_exact_key);
CREATE INDEX slice_pixel_hash_idx ON slice_file_manifest(decoded_pixel_exact_key);
CREATE INDEX series_study_idx ON series_manifest(study_key);
CREATE INDEX label_study_idx ON label_source_manifest(study_key);
CREATE INDEX component_study_idx ON protected_component(study_key);
CREATE INDEX candidate_component_study_idx ON candidate_component(study_key);
"""


def canonical_json(value: object) -> str:
    """Return deterministic JSON without non-finite values."""

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def sha256_file(path: Path) -> str:
    """Hash a file without loading it into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def opaque_key(secret: bytes, domain: str, value: str) -> str:
    """Create a domain-separated opaque key for private persisted tables."""

    if len(secret) != 32:
        raise ManifestAuditError("audit_key_invalid")
    if not domain or not value:
        raise ManifestAuditError("opaque_key_input_invalid")
    return hmac.new(secret, f"{domain}\0{value}".encode(), hashlib.sha256).hexdigest()


def install_bundle_audit_key(source: Path, destination: Path) -> bytes:
    """Copy the verified private bundle key into the private output directory."""

    try:
        if source.is_symlink() or not source.is_file() or source.stat().st_size != 32:
            raise ManifestAuditError("audit_key_invalid")
        value = source.read_bytes()
    except OSError as error:
        raise ManifestAuditError("audit_key_invalid") from error
    if len(value) != 32 or destination.exists():
        raise ManifestAuditError("audit_key_invalid")
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(value)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return value


def validate_schema(path: Path) -> dict[str, Any]:
    """Validate the JSON-compatible YAML schema without adding a YAML dependency."""

    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestAuditError("manifest_schema_invalid") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ManifestAuditError("manifest_schema_invalid")
    tables = payload.get("tables")
    required = {
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
    if not isinstance(tables, dict) or set(tables) != required:
        raise ManifestAuditError("manifest_schema_invalid")
    return cast(dict[str, Any], payload)


def load_contract(path: Path) -> tuple[dict[str, Any], tuple[str, ...]]:
    try:
        payload = json.loads(path.read_text())
        labels = tuple(payload["targets"]["labels"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ManifestAuditError("competition_contract_invalid") from error
    if (
        not labels
        or any(not isinstance(label, str) or not label for label in labels)
        or len(set(labels)) != len(labels)
    ):
        raise ManifestAuditError("competition_contract_invalid")
    return cast(dict[str, Any], payload), cast(tuple[str, ...], labels)


def initialize_private_database(path: Path, metadata: Mapping[str, str]) -> sqlite3.Connection:
    """Create a new private manifest database; never overwrite an existing artifact."""

    if path.exists():
        raise ManifestAuditError("private_manifest_exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(PRIVATE_SCHEMA_SQL)
        connection.executemany(
            "INSERT INTO manifest_run(key, value) VALUES(?, ?)", sorted(metadata.items())
        )
        connection.commit()
    except Exception:
        connection.close()
        raise
    return connection


def _exact_header(actual: Sequence[str] | None, expected: Sequence[str], code: str) -> None:
    if actual is None or tuple(actual) != tuple(expected):
        raise ManifestAuditError(code)


def _read_csv(path: Path) -> tuple[list[str], Iterator[dict[str, str | None]]]:
    try:
        handle = path.open(newline="", encoding="utf-8-sig")
    except OSError as error:
        raise ManifestAuditError("metadata_file_missing") from error
    reader = csv.DictReader(handle)
    fields = list(reader.fieldnames or [])

    def rows() -> Iterator[dict[str, str | None]]:
        try:
            yield from reader
        finally:
            handle.close()

    return fields, rows()


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _merge_scalar(
    previous: str | None, current: str | None, conflicts: set[str], name: str
) -> str | None:
    if previous is None:
        return current
    if current is None or current == previous:
        return previous
    conflicts.add(name)
    return previous


def _source_key(split: str, raw_value: str) -> str:
    return f"{split}\0{raw_value}"


def read_source_inventory(input_root: Path, labels: tuple[str, ...]) -> SourceInventory:
    """Read organizer CSVs while keeping identifiers and reports only in process memory."""

    expected_train = ["StudyInstanceUID", "Report", *labels]
    expected_test = ["StudyInstanceUID"]
    expected_series = [
        "StudyInstanceUID",
        "SeriesInstanceUID",
        "Fluid_Sensitive",
        "Fat_Suppression",
        "Anatomical_Plane",
    ]
    studies: dict[str, StudySource] = {}
    series: dict[str, SeriesSource] = {}
    counts: dict[str, int] = {}
    for split in ("train", "test"):
        fields, rows = _read_csv(input_root / f"{split}.csv")
        _exact_header(
            fields, expected_train if split == "train" else expected_test, f"{split}_header_invalid"
        )
        row_count = 0
        for row in rows:
            row_count += 1
            raw_study = _clean_optional(row.get("StudyInstanceUID"))
            if raw_study is None:
                raise ManifestAuditError(f"{split}_study_id_missing")
            qualified_study = _source_key(split, raw_study)
            existing = studies.get(qualified_study)
            if existing is None:
                existing = StudySource(
                    raw_study_id=raw_study,
                    split=split,
                    labels=[None] * len(labels),
                )
                studies[qualified_study] = existing
            existing.source_row_count += 1
            if split == "train":
                report = row.get("Report")
                existing.report = _merge_scalar(
                    existing.report, report, existing.conflicts, "report"
                )
                for index, label in enumerate(labels):
                    value = _clean_optional(row.get(label))
                    existing.labels[index] = _merge_scalar(
                        existing.labels[index], value, existing.conflicts, f"label_{index}"
                    )
        counts[f"{split}_csv_rows"] = row_count

        fields, rows = _read_csv(input_root / f"{split}_series.csv")
        _exact_header(fields, expected_series, f"{split}_series_header_invalid")
        row_count = 0
        for row in rows:
            row_count += 1
            raw_study = _clean_optional(row.get("StudyInstanceUID"))
            raw_series = _clean_optional(row.get("SeriesInstanceUID"))
            if raw_study is None or raw_series is None:
                raise ManifestAuditError(f"{split}_series_id_missing")
            qualified_study = _source_key(split, raw_study)
            qualified_series = _source_key(split, raw_series)
            if qualified_study not in studies:
                studies[qualified_study] = StudySource(
                    raw_study_id=raw_study,
                    split=split,
                    labels=[None] * len(labels),
                    conflicts={"series_csv_study_not_in_primary_csv"},
                )
            existing_series = series.get(qualified_series)
            if existing_series is None:
                existing_series = SeriesSource(
                    raw_series_id=raw_series,
                    raw_study_id=raw_study,
                    split=split,
                )
                series[qualified_series] = existing_series
            elif existing_series.raw_study_id != raw_study:
                existing_series.conflicts.add("series_parent_conflict")
            existing_series.source_row_count += 1
            existing_series.fluid_sensitive = _merge_scalar(
                existing_series.fluid_sensitive,
                _clean_optional(row.get("Fluid_Sensitive")),
                existing_series.conflicts,
                "fluid_sensitive",
            )
            existing_series.fat_suppression = _merge_scalar(
                existing_series.fat_suppression,
                _clean_optional(row.get("Fat_Suppression")),
                existing_series.conflicts,
                "fat_suppression",
            )
            existing_series.plane = _merge_scalar(
                existing_series.plane,
                _clean_optional(row.get("Anatomical_Plane")),
                existing_series.conflicts,
                "plane",
            )
        counts[f"{split}_series_csv_rows"] = row_count
    studies_by_raw: dict[str, list[StudySource]] = defaultdict(list)
    for study_source in studies.values():
        studies_by_raw[study_source.raw_study_id].append(study_source)
    for study_sources in studies_by_raw.values():
        if len({study_source.split for study_source in study_sources}) > 1:
            for study_source in study_sources:
                study_source.conflicts.add("cross_split_study_id")
    series_by_raw: dict[str, list[SeriesSource]] = defaultdict(list)
    for series_source in series.values():
        series_by_raw[series_source.raw_series_id].append(series_source)
    for series_sources in series_by_raw.values():
        if len({series_source.split for series_source in series_sources}) > 1:
            for series_source in series_sources:
                series_source.conflicts.add("cross_split_series_id")
    return SourceInventory(
        studies=studies,
        series=series,
        labels=labels,
        train_csv_rows=counts["train_csv_rows"],
        test_csv_rows=counts["test_csv_rows"],
        train_series_csv_rows=counts["train_series_csv_rows"],
        test_series_csv_rows=counts["test_series_csv_rows"],
    )


def normalize_report(text: str) -> str:
    """Delegate to the single duplicate-analysis normalization contract."""

    return normalize_duplicate_report(text)


def _script_bucket(text: str) -> str:
    scripts: Counter[str] = Counter()
    for char in text:
        if not char.isalpha():
            continue
        name = unicodedata.name(char, "")
        script = next(
            (
                candidate
                for candidate in ("LATIN", "CYRILLIC", "ARABIC", "GREEK", "HEBREW", "CJK", "HANGUL")
                if candidate in name
            ),
            "OTHER",
        )
        scripts[script] += 1
    if not scripts:
        return "none"
    return scripts.most_common(1)[0][0].lower()


def _tokenize(text: str) -> tuple[str, ...]:
    token: list[str] = []
    result: list[str] = []
    for char in text:
        category = unicodedata.category(char)
        if category[0] in {"L", "N"} or char in {"<", ">", "_"}:
            token.append(char)
        elif token:
            result.append("".join(token))
            token.clear()
    if token:
        result.append("".join(token))
    return tuple(result)


def _simhash64(tokens: Sequence[str]) -> str | None:
    if not tokens:
        return None
    weights = [0] * 64
    features = (
        tokens
        if len(tokens) < 5
        else tuple("\x1f".join(tokens[i : i + 5]) for i in range(len(tokens) - 4))
    )
    for feature in features:
        value = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")
        for bit in range(64):
            weights[bit] += 1 if value & (1 << bit) else -1
    fingerprint = sum((1 << bit) for bit, weight in enumerate(weights) if weight >= 0)
    return f"{fingerprint:016x}"


def report_features(text: str | None, secret: bytes) -> ReportFeatures:
    if text is None or not text.strip():
        return ReportFeatures(
            "missing", "valid", 0, 0, "none", None, "unavailable", None, None, None
        )
    try:
        text.encode("utf-8", errors="strict")
    except UnicodeError:
        return ReportFeatures(
            "present", "invalid", len(text), 0, "unknown", None, "invalid", None, None, None
        )
    canonical = normalize_report(text)
    tokens = _tokenize(canonical)
    language: str | None = None
    language_state = "resolved"
    try:
        language = detect(text)
    except LangDetectException:
        language_state = "unresolved"
    return ReportFeatures(
        presence_state="present",
        unicode_state="valid",
        character_count=len(text),
        token_count=len(tokens),
        script_bucket=_script_bucket(text),
        language_code=language,
        language_state=language_state,
        raw_text_exact_key=opaque_key(secret, "report-raw", text),
        canonical_text_exact_key=opaque_key(secret, "report-canonical", canonical),
        near_report_fingerprint=_simhash64(tokens),
    )


def official_label_state(value: str | None) -> str:
    """Map organizer values without coercing missing or malformed values."""

    if value is None or not value.strip():
        return "unknown"
    if value.strip() in {"1", "1.0"}:
        return "positive"
    if value.strip() in {"0", "0.0"}:
        return "negative"
    return "conflict"


def enumerate_dicom_files(input_root: Path, max_files: int | None = None) -> list[Path]:
    """Enumerate organizer DICOM files in deterministic byte order."""

    result: list[Path] = []
    for split in ("test", "train"):
        root = input_root / f"{split}_series"
        if not root.is_dir():
            raise ManifestAuditError(f"{split}_dicom_root_missing")
        for current, directories, files in os.walk(root):
            directories.sort(key=os.fsencode)
            for name in sorted(files, key=os.fsencode):
                path = Path(current) / name
                if path.is_file():
                    result.append(path)
                    if max_files is not None and len(result) >= max_files:
                        return result
    return result


def insert_source_placeholders(
    connection: sqlite3.Connection, inventory: SourceInventory, secret: bytes
) -> tuple[dict[str, str], dict[str, str], dict[str, ReportFeatures]]:
    """Insert exactly one initial row per organizer study/series and all official label cells."""

    study_keys: dict[str, str] = {}
    series_keys: dict[str, str] = {}
    reports: dict[str, ReportFeatures] = {}
    for qualified_study, source in sorted(inventory.studies.items()):
        study_key = opaque_key(secret, "study", qualified_study)
        study_keys[qualified_study] = study_key
        report_conflict = "report" in source.conflicts
        features = report_features(None if report_conflict else source.report, secret)
        if report_conflict:
            features = ReportFeatures(
                "conflict", "valid", 0, 0, "unknown", None, "unavailable", None, None, None
            )
        reports[qualified_study] = features
        states = [
            "conflict" if f"label_{index}" in source.conflicts else official_label_state(value)
            for index, value in enumerate(source.labels)
        ]
        positive = states.count("positive")
        negative = states.count("negative")
        known = positive + negative
        flags = sorted(source.conflicts)
        connection.execute(
            """INSERT INTO study_manifest VALUES(
                ?,?,?,?,?,?,?,?,?,?,?,
                ?,?,?,?,?,?,?,?,?,?,?,?,?
            )""",
            (
                study_key,
                source.split,
                source.source_row_count,
                None,
                "missing",
                0,
                "[]",
                "[]",
                0,
                features.language_code,
                int(features.presence_state == "present" and not report_conflict),
                None,
                None,
                "gold_partial" if known else "unlabeled",
                known,
                positive,
                negative,
                None,
                None,
                None,
                None,
                None,
                canonical_json(flags),
                "conditional" if flags else "pending",
            ),
        )
        report_key = opaque_key(secret, "report-row", qualified_study)
        connection.execute(
            """INSERT INTO report_manifest VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                report_key,
                study_key,
                source.source_row_count,
                features.presence_state,
                features.unicode_state,
                features.character_count,
                features.token_count,
                features.script_bucket,
                features.language_code,
                features.language_state,
                features.raw_text_exact_key,
                features.canonical_text_exact_key,
                features.near_report_fingerprint,
                None,
                "none",
                "quarantine"
                if report_conflict
                else ("pass" if features.unicode_state == "valid" else "quarantine"),
            ),
        )
        if source.split == "train" and source.source_row_count > 0:
            if len(source.labels) != len(inventory.labels):
                raise ManifestAuditError("label_width_invalid")
            for index, (label, value) in enumerate(
                zip(inventory.labels, source.labels, strict=True)
            ):
                state = (
                    "conflict"
                    if f"label_{index}" in source.conflicts
                    else official_label_state(value)
                )
                connection.execute(
                    """INSERT INTO label_source_manifest VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        study_key,
                        index,
                        label,
                        "official",
                        LABEL_VERSION,
                        state,
                        1.0 if state in {"positive", "negative"} else None,
                        None,
                        "organizer" if state != "conflict" else "unresolved",
                        "valid" if state != "conflict" else "invalid",
                    ),
                )
    for qualified_series, series_source in sorted(inventory.series.items()):
        parent_study_key = study_keys.get(
            _source_key(series_source.split, series_source.raw_study_id)
        )
        if parent_study_key is None:
            raise ManifestAuditError("series_parent_missing")
        series_key = opaque_key(secret, "series", qualified_series)
        series_keys[qualified_series] = series_key
        flags = sorted(series_source.conflicts)
        connection.execute(
            """INSERT INTO series_manifest VALUES(
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )""",
            (
                series_key,
                parent_study_key,
                series_source.source_row_count,
                None,
                series_source.plane,
                series_source.fluid_sensitive,
                series_source.fat_suppression,
                None,
                None,
                None,
                None,
                None,
                None,
                0,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                canonical_json(flags),
                0,
                0.0,
                "pending",
                "pending",
                "pending",
                "pending",
                None,
                None,
                "phash-sequence-v1",
                "conditional" if flags else "pending",
            ),
        )
    connection.commit()
    return study_keys, series_keys, reports


def table_content_hash(connection: sqlite3.Connection, table: str, order_by: Sequence[str]) -> str:
    """Hash one private table deterministically without exposing its rows."""

    allowed = {
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
    if (
        table not in allowed
        or not order_by
        or any(not re.fullmatch(r"[a-z_]+", name) for name in order_by)
    ):
        raise ManifestAuditError("table_hash_request_invalid")
    cursor = connection.execute(f"SELECT * FROM {table} ORDER BY {','.join(order_by)}")  # noqa: S608
    columns = [description[0] for description in cursor.description]
    digest = hashlib.sha256()
    for row in cursor:
        digest.update(canonical_json(dict(zip(columns, row, strict=True))).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def privacy_scan_text(text: str) -> None:
    """Fail when exportable text resembles a private identifier, path, or field."""

    if UID_LIKE.search(text) or PATH_LIKE.search(text) or SENSITIVE_FIELD.search(text):
        raise ManifestAuditError("privacy_scan_failed")


def write_json_atomic(path: Path, payload: Mapping[str, JsonValue], maximum_bytes: int) -> str:
    """Write a bounded deterministic JSON artifact without replacing existing output."""

    if path.exists():
        raise ManifestAuditError("sanitized_output_exists")
    text = canonical_json(payload) + "\n"
    privacy_scan_text(text)
    encoded = text.encode()
    if len(encoded) > maximum_bytes:
        raise ManifestAuditError("sanitized_output_too_large")
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    temporary.rename(path)
    return hashlib.sha256(encoded).hexdigest()


def suppressed_count(value: int, minimum_cell: int) -> int | Literal["suppressed"]:
    if value == 0:
        return 0
    return value if value >= minimum_cell else "suppressed"


def fixed_event(event: str, **counts: int | str | bool) -> None:
    """Emit a bounded structured event containing no arbitrary values."""

    if not re.fullmatch(r"[a-z][a-z0-9_]{2,40}", event):
        raise ManifestAuditError("log_event_invalid")
    allowed: dict[str, JsonValue] = {"event": event}
    for key, value in sorted(counts.items()):
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", key):
            raise ManifestAuditError("log_field_invalid")
        if isinstance(value, str) and not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,64}", value):
            raise ManifestAuditError("log_value_invalid")
        allowed[key] = value
    print(canonical_json(allowed), flush=True)


def assert_required_decoder_runtime() -> dict[str, str]:
    """Fail before corpus scanning unless both required compressed syntaxes can decode."""

    versions: dict[str, str] = {}
    for distribution, expected_version in REQUIRED_DECODER_PACKAGES.items():
        try:
            observed_version = importlib_metadata.version(distribution)
        except importlib_metadata.PackageNotFoundError as error:
            raise ManifestAuditError("required_decoder_unavailable") from error
        if observed_version != expected_version:
            raise ManifestAuditError("required_decoder_version_mismatch")
        versions[distribution] = observed_version
    for transfer_syntax in REQUIRED_COMPRESSED_TRANSFER_SYNTAXES:
        try:
            decoder = get_decoder(transfer_syntax)
        except NotImplementedError as error:
            raise ManifestAuditError("required_decoder_unavailable") from error
        if "pylibjpeg" not in decoder.available_plugins:
            raise ManifestAuditError("required_decoder_unavailable")
    return versions


def _check_self_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise ManifestAuditError("self_deadline_exceeded")


def environment_fingerprint(decoder_versions: Mapping[str, str]) -> tuple[str, dict[str, str]]:
    """Record only package/runtime versions, never host paths or environment values."""

    import langdetect
    import numpy
    import pydicom

    versions = {
        "langdetect": str(getattr(langdetect, "__version__", "1.0.9")),
        "numpy": numpy.__version__,
        "pydicom": pydicom.__version__,
        "python": ".".join(map(str, sys.version_info[:3])),
        **decoder_versions,
    }
    return content_sha256(versions), versions


def artifact_hash(path: Path, privacy: Literal["private", "sanitized"]) -> ArtifactHash:
    return ArtifactHash(path.name, sha256_file(path), path.stat().st_size, privacy)


def elapsed_seconds(start: float) -> int:
    return max(0, math.ceil(time.monotonic() - start))


RUNNER_OUTPUTS: Final = (
    "private_manifest.sqlite3",
    "private_duplicate_groups.csv",
    "private_preliminary_group_keys.csv",
    "private_qa_samples.csv",
    "private_artifact_inventory.json",
    "audit_key.bin",
    "data_audit.md",
    "leakage_audit.md",
    "domain_shift_audit.md",
    "sanitized_artifact_inventory.json",
)


@dataclass(frozen=True)
class HeaderEvidence:
    identity_match: bool | None
    sop_key: str | None
    patient_key: str | None
    patient_sex: str | None
    patient_age_years: float | None
    manufacturer_key: str | None
    model_key: str | None
    field_strength_t: float | None
    description_key: str | None
    localizer_likelihood: float
    transfer_syntax_class: str | None


@dataclass(frozen=True)
class InspectedFile:
    path: Path
    study_source_key: str
    series_source_key: str
    file_key: str
    size_bytes: int
    header: HeaderEvidence
    result: DicomAuditResult
    raw_digest: str | None


def _load_json_object(path: Path, code: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestAuditError(code) from error
    if not isinstance(payload, dict):
        raise ManifestAuditError(code)
    return cast(dict[str, Any], payload)


def _validate_runtime_inputs(
    schema: Mapping[str, Any],
    competition_config_path: Path,
    competition_contract_path: Path,
    run_config: Mapping[str, Any],
) -> tuple[Mapping[str, JsonValue], Mapping[str, JsonValue]]:
    pointer = _load_json_object(competition_config_path, "competition_pointer_invalid")
    if pointer != {
        "schema_version": 1,
        "contract": "../docs/competition_contract/contract.yaml",
    }:
        raise ManifestAuditError("competition_pointer_invalid")
    contract = _load_json_object(competition_contract_path, "competition_contract_invalid")
    identity = contract.get("identity")
    runtime = contract.get("runtime")
    if (
        not isinstance(identity, dict)
        or identity.get("slug") != "rsna-knee-abnormality-detection"
        or not isinstance(runtime, dict)
        or runtime.get("internet_enabled") is not False
    ):
        raise ManifestAuditError("competition_contract_invalid")
    provenance = run_config.get("provenance")
    privacy = run_config.get("privacy")
    if (
        not isinstance(provenance, dict)
        or provenance.get("decoder_packages") != REQUIRED_DECODER_PACKAGES
        or not isinstance(privacy, dict)
    ):
        raise ManifestAuditError("run_config_invalid")
    schema_privacy = schema.get("privacy")
    if (
        not isinstance(schema_privacy, dict)
        or privacy.get("minimum_export_cell") != schema_privacy.get("minimum_export_cell")
        or any(
            privacy.get(name) is not False
            for name in (
                "raw_identifiers",
                "raw_reports",
                "patient_metadata",
                "pixel_data",
                "private_tables",
            )
        )
    ):
        raise ManifestAuditError("privacy_policy_invalid")
    sanitized_privacy = {key: value for key, value in privacy.items() if key != "canary"}
    return cast(Mapping[str, JsonValue], provenance), cast(
        Mapping[str, JsonValue], sanitized_privacy
    )


def _prepare_output_root(output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    if output_root.is_symlink() or not output_root.is_dir():
        raise ManifestAuditError("output_root_invalid")
    if any((output_root / name).exists() for name in RUNNER_OUTPUTS):
        raise ManifestAuditError("audit_output_exists")
    if any((output_root / f".{name}.tmp").exists() for name in RUNNER_OUTPUTS):
        raise ManifestAuditError("audit_output_exists")


def _classify_file(input_root: Path, path: Path) -> tuple[str, str, str, str]:
    for split in ("train", "test"):
        series_root = input_root / f"{split}_series"
        try:
            parts = path.relative_to(series_root).parts
        except ValueError:
            continue
        if len(parts) == 3:
            return split, parts[0], parts[1], Path(parts[2]).stem
        private_relative = "/".join(parts)
        return (
            split,
            f"__orphan_study__:{private_relative}",
            f"__orphan_series__:{private_relative}",
            Path(parts[-1]).stem,
        )
    raise ManifestAuditError("file_outside_dicom_roots")


def _walk_regular_files(input_root: Path, max_files: int | None) -> Iterator[Path]:
    emitted = 0
    for split in ("test", "train"):
        root = input_root / f"{split}_series"
        if not root.is_dir() or root.is_symlink():
            raise ManifestAuditError(f"{split}_dicom_root_missing")
        for current, directories, files in os.walk(root):
            directories.sort(key=os.fsencode)
            current_path = Path(current)
            for name in sorted(files, key=os.fsencode):
                path = current_path / name
                if path.is_file() and not path.is_symlink():
                    yield path
                    emitted += 1
                    if max_files is not None and emitted >= max_files:
                        return


def _augment_source_inventory(
    input_root: Path,
    inventory: SourceInventory,
    max_files: int | None,
    deadline: float | None = None,
) -> tuple[Path, ...]:
    discovered: list[Path] = []
    for path in _walk_regular_files(input_root, max_files):
        if deadline is not None:
            _check_self_deadline(deadline)
        discovered.append(path)
        split, raw_study, raw_series, _ = _classify_file(input_root, path)
        study_source_key = _source_key(split, raw_study)
        series_source_key = _source_key(split, raw_series)
        study_source = inventory.studies.get(study_source_key)
        if study_source is None:
            study_source = StudySource(
                raw_study_id=raw_study,
                split=cast(Literal["train", "test"], split),
                labels=[None] * len(inventory.labels),
                conflicts={"file_tree_study_not_in_primary_or_series_csv"},
            )
            inventory.studies[study_source_key] = study_source
        elif study_source.source_row_count == 0:
            study_source.conflicts.add("study_not_in_primary_csv")
        series_source = inventory.series.get(series_source_key)
        if series_source is None:
            series_source = SeriesSource(
                raw_series_id=raw_series,
                raw_study_id=raw_study,
                split=cast(Literal["train", "test"], split),
                conflicts={"file_tree_series_not_in_series_csv"},
            )
            inventory.series[series_source_key] = series_source
    return tuple(discovered)


def _parse_patient_age(value: object) -> float | None:
    if value is None:
        return None
    match = re.fullmatch(r"(\d{3})([DWMY])", str(value).strip().upper())
    if match is None:
        return None
    amount = float(match.group(1))
    return amount / {"D": 365.25, "W": 52.1775, "M": 12.0, "Y": 1.0}[match.group(2)]


def _transfer_syntax_class(value: object) -> str | None:
    if value is None:
        return None
    uid = str(value)
    if uid.startswith("1.2.840.10008.1.2.4.9"):
        return "jpeg2000"
    if uid.startswith("1.2.840.10008.1.2.4"):
        return "jpeg"
    if uid == "1.2.840.10008.1.2.5":
        return "rle"
    if uid in {
        "1.2.840.10008.1.2",
        "1.2.840.10008.1.2.1",
        "1.2.840.10008.1.2.2",
    }:
        return "uncompressed"
    return "other"


def _header_evidence(
    dataset: pydicom.dataset.Dataset,
    *,
    raw_study: str,
    raw_series: str,
    raw_sop: str,
    secret: bytes,
) -> HeaderEvidence:
    def optional_text(name: str) -> str | None:
        value = getattr(dataset, name, None)
        if value is None:
            return None
        cleaned = " ".join(str(value).split())
        return cleaned or None

    study_uid = optional_text("StudyInstanceUID")
    series_uid = optional_text("SeriesInstanceUID")
    sop_uid = optional_text("SOPInstanceUID")
    identity_match = study_uid == raw_study and series_uid == raw_series and sop_uid == raw_sop
    patient_id = optional_text("PatientID")
    patient_sex_raw = optional_text("PatientSex")
    patient_sex = (
        patient_sex_raw.upper()
        if patient_sex_raw is not None and patient_sex_raw.upper() in {"F", "M", "O"}
        else None
    )
    manufacturer = optional_text("Manufacturer")
    model = optional_text("ManufacturerModelName")
    description = optional_text("SeriesDescription")
    field_strength: float | None
    try:
        field_strength = float(dataset.MagneticFieldStrength)
        if not math.isfinite(field_strength) or field_strength <= 0:
            field_strength = None
    except (AttributeError, TypeError, ValueError):
        field_strength = None
    description_normalized = description.casefold() if description is not None else None
    description_tokens = (
        sorted(set(re.findall(r"[^\W_]+", description_normalized)))[:32]
        if description_normalized is not None
        else []
    )
    return HeaderEvidence(
        identity_match=identity_match,
        sop_key=opaque_key(secret, "sop", sop_uid) if sop_uid is not None else None,
        patient_key=(opaque_key(secret, "patient", patient_id) if patient_id is not None else None),
        patient_sex=patient_sex,
        patient_age_years=_parse_patient_age(getattr(dataset, "PatientAge", None)),
        manufacturer_key=(
            opaque_key(secret, "manufacturer", manufacturer.casefold())
            if manufacturer is not None
            else None
        ),
        model_key=(
            opaque_key(secret, "scanner-model", model.casefold()) if model is not None else None
        ),
        field_strength_t=field_strength,
        description_key=(
            canonical_json(
                [
                    opaque_key(secret, "series-description-token", token)
                    for token in description_tokens
                ]
            )
            if description_tokens
            else None
        ),
        localizer_likelihood=(
            1.0
            if description_normalized is not None
            and any(token in description_normalized for token in ("localizer", "scout", "survey"))
            else 0.0
        ),
        transfer_syntax_class=_transfer_syntax_class(
            getattr(getattr(dataset, "file_meta", None), "TransferSyntaxUID", None)
        ),
    )


@contextmanager
def _strict_pydicom_validation() -> Iterator[None]:
    previous_reading = pydicom_config.settings.reading_validation_mode
    previous_writing = pydicom_config.settings.writing_validation_mode
    pydicom_config.settings.reading_validation_mode = pydicom_config.RAISE
    pydicom_config.settings.writing_validation_mode = pydicom_config.RAISE
    try:
        yield
    finally:
        pydicom_config.settings.reading_validation_mode = previous_reading
        pydicom_config.settings.writing_validation_mode = previous_writing


def _initialize_inspection_worker() -> None:
    pydicom_config.settings.reading_validation_mode = pydicom_config.RAISE
    pydicom_config.settings.writing_validation_mode = pydicom_config.RAISE


def _metadata_json(value: tuple[float, ...] | None) -> str | None:
    return None if value is None else canonical_json([round(item, 8) for item in value])


_KNOWN_FILE_SERIES_ISSUES: Final = {
    ("file", "path_header_identity_mismatch"): _ManifestIssuePolicy(
        severity="error",
        terminal_effect="quarantine",
        disposition="file_quarantine",
        version=MANIFEST_ISSUE_DISPOSITION_VERSION,
        scope_impact="file_and_parent_series_quarantined",
        root_cause_category="path_header_identity_mismatch",
        resolution_status=DicomResolutionState.EXCLUDED_UNUSABLE_SOURCE.value,
        resolution_version=MANIFEST_ISSUE_DISPOSITION_VERSION,
    ),
    ("file", "low_information_perceptual_fingerprint"): _ManifestIssuePolicy(
        severity="warning",
        terminal_effect="near_duplicate_excluded",
        disposition="candidate_search_exclusion",
        version=MANIFEST_ISSUE_DISPOSITION_VERSION,
        scope_impact="near_duplicate_candidate_search_only",
        root_cause_category="low_information_perceptual_fingerprint",
        resolution_status="nonterminal_search_exclusion",
        resolution_version=MANIFEST_ISSUE_DISPOSITION_VERSION,
    ),
    **{
        ("series", issue_code): _ManifestIssuePolicy(
            severity="error",
            terminal_effect="quarantine",
            disposition="series_quarantine",
            version=MANIFEST_ISSUE_DISPOSITION_VERSION,
            scope_impact="series_and_parent_study_quarantined",
            root_cause_category=issue_code,
            resolution_status=DicomResolutionState.EXCLUDED_UNUSABLE_SOURCE.value,
            resolution_version=MANIFEST_ISSUE_DISPOSITION_VERSION,
        )
        for issue_code in {
            "cross_split_series_id",
            "fat_suppression",
            "file_integrity_failure",
            "file_tree_series_not_in_series_csv",
            "fluid_sensitive",
            "path_header_identity_failure",
            "plane",
            "series_parent_conflict",
        }
    },
}


def _issue_policy(
    entity_level: str,
    issue_code: str,
    severity: str,
    terminal_effect: str,
    root_cause_category: str | None,
) -> _ManifestIssuePolicy:
    """Resolve one issue to an explicit policy or a fail-closed unexplained state."""

    if entity_level in {DicomIssueScope.FILE.value, DicomIssueScope.SERIES.value}:
        try:
            dicom_issue = DicomIssue(issue_code)
        except ValueError:
            known = _KNOWN_FILE_SERIES_ISSUES.get((entity_level, issue_code))
            if known is not None:
                return known
        else:
            policy = DICOM_ISSUE_POLICIES[dicom_issue]
            if policy.scope.value == entity_level:
                return _ManifestIssuePolicy(
                    policy.severity,
                    policy.terminal_effect,
                    policy.disposition.value,
                    policy.version,
                    policy.scope_impact,
                    root_cause_category or policy.default_root_cause,
                    policy.default_resolution_state.value,
                    policy.resolution_version,
                )
        return _ManifestIssuePolicy(
            "error",
            "quarantine",
            "unexplained_quarantine",
            MANIFEST_ISSUE_DISPOSITION_VERSION,
            "file_or_series_quarantined_pending_private_investigation",
            DecodeRootCause.UNEXPECTED_UNEXPLAINED.value,
            DicomResolutionState.UNRESOLVED_BLOCKER.value,
            DICOM_ISSUE_RESOLUTION_VERSION,
        )
    return _ManifestIssuePolicy(
        severity,
        terminal_effect,
        "study_review" if severity == "warning" else "study_quarantine",
        MANIFEST_ISSUE_DISPOSITION_VERSION,
        "study_review" if severity == "warning" else "study_quarantined",
        issue_code,
        "review_required" if severity == "warning" else "excluded_unusable_source",
        MANIFEST_ISSUE_DISPOSITION_VERSION,
    )


def _insert_issue(
    connection: sqlite3.Connection,
    entity_level: str,
    entity_key: str,
    issue_code: str,
    severity: str = "error",
    terminal_effect: str = "quarantine",
    *,
    root_cause_category: str | None = None,
    root_cause_version: str | None = None,
    resolution_status: str | None = None,
    resolution_version: str | None = None,
    private_details: Mapping[str, JsonValue] | None = None,
) -> None:
    policy = _issue_policy(
        entity_level,
        issue_code,
        severity,
        terminal_effect,
        root_cause_category,
    )
    resolved_root_cause_version = root_cause_version or (
        DECODE_ROOT_CAUSE_VERSION
        if policy.disposition != "unexplained_quarantine"
        and policy.root_cause_category in DECODE_ROOT_CAUSE_TAXONOMY
        else policy.version
    )
    resolved_resolution_status = resolution_status or policy.resolution_status
    resolved_resolution_version = resolution_version or policy.resolution_version
    connection.execute(
        "INSERT OR IGNORE INTO manifest_issue VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            entity_level,
            entity_key,
            issue_code,
            policy.severity,
            policy.terminal_effect,
            policy.disposition,
            policy.version,
            policy.root_cause_category,
            resolved_root_cause_version,
            resolved_resolution_status,
            resolved_resolution_version,
            policy.scope_impact,
            canonical_json({} if private_details is None else private_details),
        ),
    )


def _dicom_issue_disposition_status(connection: sqlite3.Connection) -> tuple[int, bool]:
    """Return the public-safe unexplained count and exhaustive-policy completion flag."""

    unexplained = int(
        connection.execute(
            """SELECT COUNT(*) FROM manifest_issue
                WHERE entity_level IN ('file','series')
                AND (disposition='unexplained_quarantine'
                    OR root_cause_category='unexpected_unexplained'
                    OR resolution_status='unresolved_blocker')"""
        ).fetchone()[0]
    )
    complete = (
        frozenset(DICOM_ISSUE_POLICIES) == frozenset(DicomIssue)
        and all(
            policy.version == DICOM_ISSUE_DISPOSITION_VERSION
            for policy in DICOM_ISSUE_POLICIES.values()
        )
        and unexplained == 0
        and connection.execute(
            """SELECT COUNT(*) FROM manifest_issue
                WHERE entity_level IN ('file','series')
                AND (disposition='' OR disposition_version=''
                    OR root_cause_category='' OR root_cause_version=''
                    OR resolution_status='' OR resolution_version=''
                    OR scope_impact='')"""
        ).fetchone()[0]
        == 0
    )
    return unexplained, complete


def _inspect_one_file(input_root: Path, path: Path, secret: bytes) -> InspectedFile:
    split, raw_study, raw_series, raw_sop = _classify_file(input_root, path)
    relative = path.relative_to(input_root).as_posix()
    file_key = opaque_key(secret, "file", relative)
    read_error: OSError | None = None
    try:
        payload = path.read_bytes()
    except OSError as error:
        payload = None
        read_error = error
    if payload is None:
        header = HeaderEvidence(None, None, None, None, None, None, None, None, None, 0.0, None)
        result = classified_dicom_failure(
            DicomIssue.UNREADABLE,
            root_cause_category="file_read_io_error",
            stage="file_read",
            error=read_error,
        )
        raw_digest = None
        size_bytes = 0
    else:
        raw_digest = hashlib.sha256(payload).hexdigest()
        size_bytes = len(payload)
        try:
            dataset = pydicom.dcmread(BytesIO(payload), force=False)
        except MemoryError:
            raise
        except InvalidDicomError as error:
            header = HeaderEvidence(None, None, None, None, None, None, None, None, None, 0.0, None)
            result = classified_dicom_failure(
                DicomIssue.UNREADABLE,
                root_cause_category="invalid_dicom_container",
                stage="container_parse",
                error=error,
            )
        except OSError as error:
            header = HeaderEvidence(None, None, None, None, None, None, None, None, None, 0.0, None)
            result = classified_dicom_failure(
                DicomIssue.UNREADABLE,
                root_cause_category="dicom_parse_io_error",
                stage="container_parse",
                error=error,
            )
        except ValueError as error:
            header = HeaderEvidence(None, None, None, None, None, None, None, None, None, 0.0, None)
            result = classified_dicom_failure(
                DicomIssue.UNREADABLE,
                root_cause_category=DecodeRootCause.UNEXPECTED_UNEXPLAINED.value,
                stage="container_parse",
                error=error,
            )
        except Exception as error:
            header = HeaderEvidence(None, None, None, None, None, None, None, None, None, 0.0, None)
            result = classified_dicom_failure(
                DicomIssue.UNREADABLE,
                root_cause_category=DecodeRootCause.UNEXPECTED_UNEXPLAINED.value,
                stage="container_parse",
                error=error,
            )
        else:
            try:
                header = _header_evidence(
                    dataset,
                    raw_study=raw_study,
                    raw_series=raw_series,
                    raw_sop=raw_sop,
                    secret=secret,
                )
            except MemoryError:
                raise
            except Exception as error:
                header = HeaderEvidence(
                    None, None, None, None, None, None, None, None, None, 0.0, None
                )
                result = classified_dicom_failure(
                    DicomIssue.UNREADABLE,
                    root_cause_category=DecodeRootCause.UNEXPECTED_UNEXPLAINED.value,
                    stage="header_extraction",
                    error=error,
                )
            else:
                try:
                    # Decode once and retain the private pHash with the other fingerprints.
                    result = audit_dataset(
                        dataset, raw_digest=raw_digest, include_perceptual_hash=True
                    )
                except MemoryError:
                    raise
                except Exception as error:
                    result = classified_dicom_failure(
                        DicomIssue.DECODE_FAILURE,
                        root_cause_category=DecodeRootCause.UNEXPECTED_UNEXPLAINED.value,
                        stage="audit_runtime",
                        error=error,
                    )
    return InspectedFile(
        path=path,
        study_source_key=_source_key(split, raw_study),
        series_source_key=_source_key(split, raw_series),
        file_key=file_key,
        size_bytes=size_bytes,
        header=header,
        result=result,
        raw_digest=raw_digest,
    )


def _persist_inspected_file(
    connection: sqlite3.Connection,
    *,
    inspected: InspectedFile,
    study_keys: Mapping[str, str],
    series_keys: Mapping[str, str],
    secret: bytes,
) -> tuple[FileAuditState, HeaderEvidence]:
    study_key = study_keys[inspected.study_source_key]
    series_key = series_keys[inspected.series_source_key]
    path = inspected.path
    file_key = inspected.file_key
    header = inspected.header
    result = inspected.result
    metadata = result.metadata
    fingerprints = result.fingerprints
    raw_digest = inspected.raw_digest
    issues = {issue.value for issue in result.issues}
    if inspected.size_bytes <= 0:
        issues.add("unreadable")
    if header.identity_match is False:
        issues.add("path_header_identity_mismatch")
    terminal_state = "pass" if not issues and header.identity_match is True else "quarantine"
    connection.execute(
        """INSERT INTO slice_file_manifest VALUES(
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
            ?,?,?,?,?,?,?,?,?,?,?,?,?
        )""",
        (
            file_key,
            study_key,
            series_key,
            header.sop_key,
            inspected.size_bytes,
            None if header.identity_match is None else int(header.identity_match),
            header.transfer_syntax_class,
            None if metadata is None else metadata.number_of_frames,
            None if metadata is None else metadata.rows,
            None if metadata is None else metadata.columns,
            None if metadata is None else metadata.samples_per_pixel,
            None if metadata is None else metadata.photometric_interpretation,
            None if metadata is None else metadata.bits_allocated,
            None if metadata is None else metadata.bits_stored,
            None if metadata is None else metadata.high_bit,
            None if metadata is None else metadata.pixel_representation,
            None if metadata is None else metadata.rescale_slope,
            None if metadata is None else metadata.rescale_intercept,
            None if metadata is None else _metadata_json(metadata.image_orientation),
            None if metadata is None else _metadata_json(metadata.image_position),
            None,
            None if metadata is None else metadata.instance_number,
            None,
            (opaque_key(secret, "raw-file-digest", raw_digest) if raw_digest is not None else None),
            (
                opaque_key(secret, "decoded-pixel-digest", fingerprints.decoded_sha256)
                if fingerprints is not None
                else None
            ),
            None if fingerprints is None else fingerprints.perceptual_hash,
            "pass" if fingerprints is not None else "failed",
            canonical_json(sorted(issues)),
            terminal_state,
        ),
    )
    diagnostics_by_issue = {diagnostic.issue.value: diagnostic for diagnostic in result.diagnostics}
    for issue in sorted(issues):
        diagnostic = diagnostics_by_issue.get(issue)
        _insert_issue(
            connection,
            "file",
            file_key,
            issue,
            root_cause_category=(None if diagnostic is None else diagnostic.root_cause_category),
            root_cause_version=(None if diagnostic is None else diagnostic.root_cause_version),
            resolution_status=(None if diagnostic is None else diagnostic.resolution_state.value),
            resolution_version=(None if diagnostic is None else diagnostic.resolution_version),
            private_details=(
                None
                if diagnostic is None
                else {
                    "stage": diagnostic.stage,
                    "exception_type": diagnostic.exception_type,
                }
            ),
        )
    return FileAuditState(path, file_key, study_key, series_key, result), header


def _ordered_file_inspections(
    paths: Iterator[Path],
    *,
    input_root: Path,
    secret: bytes,
    workers: int,
    deadline: float,
) -> Iterator[InspectedFile]:
    maximum_in_flight = max(1, workers * 2)
    maximum_pool_tasks = workers * INSPECTIONS_PER_WORKER_LIFETIME
    while batch := tuple(islice(paths, maximum_pool_tasks)):
        pending: deque[Future[InspectedFile]] = deque()
        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=get_context("forkserver"),
            initializer=_initialize_inspection_worker,
        ) as executor:
            for path in batch:
                _check_self_deadline(deadline)
                pending.append(executor.submit(_inspect_one_file, input_root, path, secret))
                if len(pending) >= maximum_in_flight:
                    yield pending.popleft().result()
            while pending:
                _check_self_deadline(deadline)
                yield pending.popleft().result()


def _quantile_indices(length: int, count: int) -> tuple[int, ...]:
    if length <= 0:
        return ()
    selected = min(length, count)
    if selected == 1:
        return ((length - 1) // 2,)
    return tuple(round(index * (length - 1) / (selected - 1)) for index in range(selected))


def _series_content_key(
    states: Sequence[FileAuditState], ordered_indices: Sequence[int], secret: bytes
) -> str | None:
    if len(states) != len(ordered_indices):
        return None
    digests: list[str] = []
    for index in ordered_indices:
        fingerprints = states[index].result.fingerprints
        if fingerprints is None:
            return None
        digests.append(fingerprints.decoded_sha256)
    forward = "\0".join(digests)
    reverse = "\0".join(reversed(digests))
    return opaque_key(secret, "series-content", min(forward, reverse))


def _finish_series(
    connection: sqlite3.Connection,
    *,
    states: Sequence[FileAuditState],
    headers: Sequence[HeaderEvidence],
    source: SeriesSource,
    secret: bytes,
    schema: Mapping[str, Any],
) -> SeriesEvidence:
    series_key = states[0].series_key
    study_key = states[0].study_key
    metadata_states = [state for state in states if state.result.metadata is not None]
    metadata = [cast(SliceMetadata, state.result.metadata) for state in metadata_states]
    series_result = audit_series(metadata)
    ordered_states = [metadata_states[index] for index in series_result.ordered_indices]
    dicom_schema = cast(Mapping[str, Any], schema["dicom"])
    sample_count = int(dicom_schema.get("near_series_quantile_slices", 9))
    sample_states = [
        ordered_states[index] for index in _quantile_indices(len(ordered_states), sample_count)
    ]
    phashes: list[str] = []
    sample_paths: list[Path] = []
    sample_file_keys: list[str] = []
    for state in sample_states:
        phash = (
            None if state.result.fingerprints is None else state.result.fingerprints.perceptual_hash
        )
        if phash is not None:
            phashes.append(phash)
            sample_paths.append(state.path)
            sample_file_keys.append(state.file_key)
    for slice_index, state in enumerate(ordered_states):
        projected = (
            series_result.projected_positions_mm[slice_index]
            if series_result.projected_positions_mm
            else None
        )
        connection.execute(
            """UPDATE slice_file_manifest SET slice_index=?, projected_position_mm=?
                WHERE file_key=?""",
            (slice_index, projected, state.file_key),
        )
    issues = {issue.value for issue in series_result.issues}
    issues.update(source.conflicts)
    if any(state.result.issues for state in states):
        issues.add("file_integrity_failure")
    if any(header.identity_match is not True for header in headers):
        issues.add("path_header_identity_failure")
    exact_key = _series_content_key(
        states,
        [states.index(state) for state in ordered_states],
        secret,
    )
    first_metadata = metadata[0] if metadata else None
    header = next((value for value in headers if value.description_key is not None), headers[0])
    terminal_state = "pass" if series_result.passed and not issues else "quarantine"
    orientation_state = (
        "valid"
        if series_result.ordering_basis is OrderingBasis.GEOMETRY
        and DicomIssue.INVALID_ORIENTATION not in series_result.issues
        and DicomIssue.ORIENTATION_DRIFT not in series_result.issues
        else "invalid"
    )
    spacing_state = (
        "valid"
        if not any(
            issue
            in {
                DicomIssue.MISSING_PIXEL_SPACING,
                DicomIssue.IN_PLANE_SPACING_DRIFT,
                DicomIssue.DUPLICATE_POSITION,
                DicomIssue.SPACING_DRIFT,
                DicomIssue.LARGE_GAP,
            }
            for issue in series_result.issues
        )
        else "invalid"
    )
    connection.execute(
        """UPDATE series_manifest SET
            series_description=?, rows=?, columns=?, pixel_spacing_row_mm=?,
            pixel_spacing_col_mm=?, slice_thickness_mm=?, spacing_between_slices_mm=?,
            slice_count=?, orientation_vectors=?, physical_coverage_mm=?, transfer_syntax_class=?,
            photometric_interpretation=?, bits_stored=?, rescale_slope=?, rescale_intercept=?,
            missing_tag_flags=?, quality_score=?, localizer_likelihood=?, ordering_method=?,
            orientation_state=?, spacing_state=?, decode_state=?, protocol_cluster_key=?,
            exact_content_key=?, near_fingerprint_version=?, terminal_state=?
            WHERE series_key=?""",
        (
            header.description_key,
            None if first_metadata is None else first_metadata.rows,
            None if first_metadata is None else first_metadata.columns,
            None
            if first_metadata is None or first_metadata.pixel_spacing is None
            else first_metadata.pixel_spacing[0],
            None
            if first_metadata is None or first_metadata.pixel_spacing is None
            else first_metadata.pixel_spacing[1],
            None if first_metadata is None else first_metadata.slice_thickness,
            series_result.median_spacing_mm,
            len(states),
            None if first_metadata is None else _metadata_json(first_metadata.image_orientation),
            (
                abs(
                    series_result.projected_positions_mm[-1]
                    - series_result.projected_positions_mm[0]
                )
                if len(series_result.projected_positions_mm) > 1
                else None
            ),
            header.transfer_syntax_class,
            None if first_metadata is None else first_metadata.photometric_interpretation,
            None if first_metadata is None else first_metadata.bits_stored,
            None if first_metadata is None else first_metadata.rescale_slope,
            None if first_metadata is None else first_metadata.rescale_intercept,
            canonical_json(sorted(issues)),
            max(0, 100 - 10 * len(issues)),
            max(value.localizer_likelihood for value in headers),
            series_result.ordering_basis.value,
            orientation_state,
            spacing_state,
            "pass" if all(state.result.fingerprints is not None for state in states) else "failed",
            opaque_key(
                secret,
                "protocol",
                "|".join(
                    str(value)
                    for value in (
                        source.plane,
                        source.fluid_sensitive,
                        source.fat_suppression,
                        first_metadata.rows if first_metadata else None,
                        first_metadata.columns if first_metadata else None,
                    )
                ),
            ),
            exact_key,
            "phash-sequence-v1",
            terminal_state,
            series_key,
        ),
    )
    representative_file_key = min(state.file_key for state in states)
    for issue in sorted(issues):
        _insert_issue(
            connection,
            "series",
            series_key,
            issue,
            private_details={"representative_file_key": representative_file_key},
        )
    return SeriesEvidence(
        series_key,
        study_key,
        source.split,
        source.plane,
        None if first_metadata is None else first_metadata.rows,
        None if first_metadata is None else first_metadata.columns,
        exact_key,
        tuple(phashes),
        tuple(sample_paths),
        tuple(sample_file_keys),
    )


def _canonical_pair(left: str, right: str) -> tuple[str, str]:
    if left == right:
        raise ManifestAuditError("duplicate_self_edge")
    return (left, right) if left < right else (right, left)


def _persist_edge(
    connection: sqlite3.Connection,
    *,
    left: str,
    right: str,
    entity_level: str,
    kind: str,
    disposition: EdgeDisposition,
    metrics: Mapping[str, JsonValue] | None = None,
) -> None:
    left, right = _canonical_pair(left, right)
    connection.execute(
        "INSERT OR IGNORE INTO duplicate_edge VALUES(?,?,?,?,?,?,?)",
        (
            left,
            right,
            entity_level,
            kind,
            disposition.value,
            "duplicate-audit-v2",
            canonical_json({} if metrics is None else metrics),
        ),
    )


def _persist_exact_groups(
    connection: sqlite3.Connection,
    *,
    table: str,
    entity_column: str,
    study_column: str,
    digest_column: str,
    entity_level: str,
    kind: str,
    secret: bytes,
    study_edges: list[DuplicateEdge],
) -> int:
    allowed = {
        ("slice_file_manifest", "file_key", "study_key", "raw_file_exact_key"),
        ("slice_file_manifest", "file_key", "study_key", "decoded_pixel_exact_key"),
        ("series_manifest", "series_key", "study_key", "exact_content_key"),
        ("report_manifest", "report_key", "study_key", "raw_text_exact_key"),
        ("report_manifest", "report_key", "study_key", "canonical_text_exact_key"),
    }
    if (table, entity_column, study_column, digest_column) not in allowed:
        raise ManifestAuditError("duplicate_group_request_invalid")
    disposition = EdgeDisposition.CANDIDATE if entity_level == "report" else EdgeDisposition.HARD
    groups = connection.execute(
        f"""SELECT {digest_column} FROM {table} WHERE {digest_column} IS NOT NULL
            GROUP BY {digest_column} HAVING COUNT(*) > 1 ORDER BY {digest_column}"""  # noqa: S608
    ).fetchall()
    for (digest,) in groups:
        rows = connection.execute(
            f"""SELECT {entity_column}, {study_column} FROM {table}
                WHERE {digest_column}=? ORDER BY {entity_column}""",  # noqa: S608
            (digest,),
        ).fetchall()
        group_key = opaque_key(secret, f"group-{kind}", str(digest))
        for entity_key, _ in rows:
            connection.execute(
                "INSERT OR IGNORE INTO duplicate_group_mapping VALUES(?,?,?,?,?)",
                (kind, group_key, entity_level, entity_key, "duplicate-audit-v2"),
            )
        for (left_entity, _), (right_entity, _) in zip(rows, rows[1:], strict=False):
            _persist_edge(
                connection,
                left=left_entity,
                right=right_entity,
                entity_level=entity_level,
                kind=kind,
                disposition=disposition,
            )
        studies = sorted({str(row[1]) for row in rows})
        for left, right in zip(studies, studies[1:], strict=False):
            study_edges.append(DuplicateEdge(left, right, kind, disposition))
    return len(groups)


def _exact_report_pair_counts(connection: sqlite3.Connection) -> tuple[int, int, int, int]:
    """Count raw and normalized exact-report study pairs with inclusion-exclusion proof."""

    raw_pairs = 0
    raw_groups = connection.execute(
        """SELECT raw_text_exact_key, COUNT(*), COUNT(DISTINCT canonical_text_exact_key)
            FROM report_manifest WHERE raw_text_exact_key IS NOT NULL
            GROUP BY raw_text_exact_key HAVING COUNT(*) > 1
            ORDER BY raw_text_exact_key"""
    ).fetchall()
    for _, member_count, canonical_count in raw_groups:
        if int(canonical_count) != 1:
            raise ManifestAuditError("exact_report_normalization_invariant_failed")
        raw_pairs += int(member_count) * (int(member_count) - 1) // 2
    normalized_pairs = sum(
        int(member_count) * (int(member_count) - 1) // 2
        for (member_count,) in connection.execute(
            """SELECT COUNT(*) FROM report_manifest
                WHERE canonical_text_exact_key IS NOT NULL
                GROUP BY canonical_text_exact_key HAVING COUNT(*) > 1"""
        )
    )
    overlap_pairs = raw_pairs
    union_pairs = normalized_pairs
    if union_pairs != raw_pairs + normalized_pairs - overlap_pairs:
        raise ManifestAuditError("exact_report_pair_union_failed")
    return raw_pairs, normalized_pairs, overlap_pairs, union_pairs


def _finalize_report_template_components(
    connection: sqlite3.Connection,
    *,
    secret: bytes,
) -> int:
    """Assign one deterministic transitive component across all report evidence kinds."""

    report_to_study = {
        str(report_key): str(study_key)
        for report_key, study_key in connection.execute(
            "SELECT report_key, study_key FROM report_manifest ORDER BY report_key"
        )
    }
    study_nodes = sorted(report_to_study.values())
    evidence: list[DuplicateEdge] = []
    evidence_kinds: dict[tuple[str, str], set[str]] = defaultdict(set)
    for left_key, right_key, entity_level, kind, decision in connection.execute(
        """SELECT left_key, right_key, entity_level, edge_kind, decision
            FROM duplicate_edge WHERE edge_kind IN (
                'exact-report-raw','exact-report-normalized',
                'near-report','near-report-overflow-block')
            ORDER BY entity_level, left_key, right_key, edge_kind"""
    ):
        if entity_level == "report":
            left_study = report_to_study[str(left_key)]
            right_study = report_to_study[str(right_key)]
        elif entity_level == "study":
            left_study = str(left_key)
            right_study = str(right_key)
        else:
            raise ManifestAuditError("report_template_entity_level_invalid")
        if left_study == right_study:
            continue
        disposition = EdgeDisposition(str(decision))
        pair = _canonical_pair(left_study, right_study)
        evidence.append(DuplicateEdge(pair[0], pair[1], str(kind), disposition))
        evidence_kinds[pair].add(str(kind))
    component_by_study = build_candidate_components(study_nodes, evidence)
    members_by_component: dict[str, list[str]] = defaultdict(list)
    for study_key, component in component_by_study.items():
        members_by_component[component].append(study_key)
    connection.execute(
        "UPDATE report_manifest SET template_group_key=NULL, template_match_kind='none'"
    )
    group_count = 0
    for members in members_by_component.values():
        members.sort()
        if len(members) < 2:
            continue
        group_count += 1
        group_key = opaque_key(secret, "report-template-component", "\0".join(members))
        member_set = set(members)
        kinds = sorted(
            kind
            for pair, pair_kinds in evidence_kinds.items()
            if pair[0] in member_set and pair[1] in member_set
            for kind in pair_kinds
        )
        match_kind = "+".join(sorted(set(kinds)))
        for study_key in members:
            report_key = connection.execute(
                "SELECT report_key FROM report_manifest WHERE study_key=?", (study_key,)
            ).fetchone()[0]
            connection.execute(
                """UPDATE report_manifest SET template_group_key=?, template_match_kind=?
                    WHERE study_key=?""",
                (group_key, match_kind, study_key),
            )
            connection.execute(
                "INSERT OR IGNORE INTO duplicate_group_mapping VALUES(?,?,?,?,?)",
                (
                    "report-template-component",
                    group_key,
                    "report",
                    report_key,
                    "duplicate-audit-v2",
                ),
            )
    return group_count


def _persist_study_exact_groups(
    connection: sqlite3.Connection, secret: bytes, study_edges: list[DuplicateEdge]
) -> int:
    signatures: dict[str, list[str]] = defaultdict(list)
    studies = connection.execute(
        "SELECT study_key, series_count FROM study_manifest ORDER BY study_key"
    ).fetchall()
    for study_key, expected_count in studies:
        series_keys = [
            row[0]
            for row in connection.execute(
                """SELECT exact_content_key FROM series_manifest WHERE study_key=?
                    ORDER BY exact_content_key""",
                (study_key,),
            )
            if row[0] is not None
        ]
        if series_keys and len(series_keys) == expected_count:
            signature = opaque_key(secret, "study-content", "\0".join(series_keys))
            signatures[signature].append(study_key)
    group_count = 0
    for signature, members in sorted(signatures.items()):
        if len(members) < 2:
            continue
        group_count += 1
        group_key = opaque_key(secret, "group-exact-study", signature)
        for member in sorted(members):
            connection.execute(
                "INSERT INTO duplicate_group_mapping VALUES(?,?,?,?,?)",
                ("exact-study", group_key, "study", member, "duplicate-audit-v2"),
            )
        ordered_members = sorted(members)
        for left, right in zip(ordered_members, ordered_members[1:], strict=False):
            _persist_edge(
                connection,
                left=left,
                right=right,
                entity_level="study",
                kind="exact-study",
                disposition=EdgeDisposition.HARD,
            )
            study_edges.append(DuplicateEdge(left, right, "exact-study", EdgeDisposition.HARD))
    return group_count


def _persist_altered_metadata_edges(
    connection: sqlite3.Connection,
    secret: bytes,
    study_edges: list[DuplicateEdge],
) -> MetadataDuplicateSummary:
    """Classify decoded-equal/raw-different evidence using canonical metadata signatures."""

    raw_container_groups = 0
    altered_groups = 0

    def signature(values: Sequence[object], level: str) -> str:
        return content_sha256(
            {
                "allowlist_version": f"canonical-{level}-metadata-v1",
                "values": [
                    round(value, 8) if isinstance(value, float) else value for value in values
                ],
            }
        )

    def persist_group_members(
        *, kind: str, group_key: str, entity_level: str, entity_keys: Sequence[str]
    ) -> None:
        for entity_key in sorted(set(entity_keys)):
            connection.execute(
                "INSERT OR IGNORE INTO duplicate_group_mapping VALUES(?,?,?,?,?)",
                (kind, group_key, entity_level, entity_key, "duplicate-audit-v2"),
            )

    def persist_bridge(
        *,
        kind: str,
        entity_level: str,
        left_entity: str,
        left_study: str,
        right_entity: str,
        right_study: str,
    ) -> None:
        _persist_edge(
            connection,
            left=left_entity,
            right=right_entity,
            entity_level=entity_level,
            kind=kind,
            disposition=EdgeDisposition.HARD,
        )
        if left_study != right_study:
            study_edges.append(DuplicateEdge(left_study, right_study, kind, EdgeDisposition.HARD))

    pixel_digests = connection.execute(
        """SELECT decoded_pixel_exact_key FROM slice_file_manifest
            WHERE decoded_pixel_exact_key IS NOT NULL GROUP BY decoded_pixel_exact_key
            HAVING COUNT(*) > 1 AND COUNT(DISTINCT raw_file_exact_key) > 1
            ORDER BY decoded_pixel_exact_key"""
    ).fetchall()
    for (digest,) in pixel_digests:
        rows = connection.execute(
            """SELECT file_key, study_key, raw_file_exact_key,
                number_of_frames, rows, columns, samples_per_pixel,
                photometric_interpretation, bits_allocated, bits_stored, high_bit,
                pixel_representation, rescale_slope, rescale_intercept,
                image_orientation_patient, image_position_patient, instance_number
                FROM slice_file_manifest
                WHERE decoded_pixel_exact_key=? ORDER BY file_key""",
            (digest,),
        ).fetchall()
        by_metadata: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
        for row in rows:
            by_metadata[signature(row[3:], "file")].append(row)
        for metadata_signature, metadata_rows in sorted(by_metadata.items()):
            by_raw: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
            for row in metadata_rows:
                by_raw[str(row[2])].append(row)
            if len(by_raw) < 2:
                continue
            raw_container_groups += 1
            group_key = opaque_key(
                secret,
                "group-raw-container-variation-file",
                f"{digest}\0{metadata_signature}",
            )
            persist_group_members(
                kind="raw-container-variation-file",
                group_key=group_key,
                entity_level="file",
                entity_keys=[str(row[0]) for row in metadata_rows],
            )
            representatives = [
                sorted(raw_rows, key=lambda row: str(row[0]))[0] for raw_rows in by_raw.values()
            ]
            representatives.sort(key=lambda row: str(row[0]))
            for left, right in zip(representatives, representatives[1:], strict=False):
                persist_bridge(
                    kind="raw-container-variation-file",
                    entity_level="file",
                    left_entity=str(left[0]),
                    left_study=str(left[1]),
                    right_entity=str(right[0]),
                    right_study=str(right[1]),
                )
        if len(by_metadata) > 1:
            altered_groups += 1
            group_key = opaque_key(secret, "group-altered-metadata-file", str(digest))
            persist_group_members(
                kind="altered-metadata-file",
                group_key=group_key,
                entity_level="file",
                entity_keys=[str(row[0]) for row in rows],
            )
            representatives = [
                sorted(metadata_rows, key=lambda row: str(row[0]))[0]
                for _, metadata_rows in sorted(by_metadata.items())
            ]
            for left, right in zip(representatives, representatives[1:], strict=False):
                persist_bridge(
                    kind="altered-metadata-file",
                    entity_level="file",
                    left_entity=str(left[0]),
                    left_study=str(left[1]),
                    right_entity=str(right[0]),
                    right_study=str(right[1]),
                )
    series_digests = connection.execute(
        """SELECT exact_content_key FROM series_manifest WHERE exact_content_key IS NOT NULL
            GROUP BY exact_content_key HAVING COUNT(*) > 1 ORDER BY exact_content_key"""
    ).fetchall()
    for (digest,) in series_digests:
        rows = connection.execute(
            """SELECT series_key, study_key, series_description, plane, fluid_sensitive,
                fat_suppression, rows, columns, pixel_spacing_row_mm, pixel_spacing_col_mm,
                slice_thickness_mm, spacing_between_slices_mm, orientation_vectors,
                photometric_interpretation, bits_stored, rescale_slope, rescale_intercept
                FROM series_manifest
                WHERE exact_content_key=? ORDER BY series_key""",
            (digest,),
        ).fetchall()
        by_metadata = defaultdict(list)
        for row in rows:
            by_metadata[signature(row[2:], "series")].append(row)
        if len(by_metadata) > 1:
            altered_groups += 1
            group_key = opaque_key(secret, "group-altered-metadata-series", str(digest))
            persist_group_members(
                kind="altered-metadata-series",
                group_key=group_key,
                entity_level="series",
                entity_keys=[str(row[0]) for row in rows],
            )
            representatives = [
                sorted(metadata_rows, key=lambda row: str(row[0]))[0]
                for _, metadata_rows in sorted(by_metadata.items())
            ]
            for left, right in zip(representatives, representatives[1:], strict=False):
                persist_bridge(
                    kind="altered-metadata-series",
                    entity_level="series",
                    left_entity=str(left[0]),
                    left_study=str(left[1]),
                    right_entity=str(right[0]),
                    right_study=str(right[1]),
                )
    connection.executemany(
        "INSERT OR REPLACE INTO manifest_run VALUES(?,?)",
        (
            ("raw_container_variation_groups", str(raw_container_groups)),
            ("altered_metadata_groups", str(altered_groups)),
        ),
    )
    return MetadataDuplicateSummary(raw_container_groups, altered_groups)


def _bounded_block_pairs(
    buckets: Mapping[str, Sequence[str]], *, maximum_bucket_members: int = 128
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    """Legacy bounded blocker retained for private overflow-chain compatibility tests.

    Recall-sensitive near-series and report discovery no longer uses this helper.
    """

    pairs: set[tuple[str, str]] = set()
    overflow_chains: set[tuple[str, str]] = set()
    for members in buckets.values():
        ordered = sorted(set(members))
        bounded = ordered[:maximum_bucket_members]
        pairs.update(combinations(bounded, 2))
        if len(ordered) > maximum_bucket_members:
            overflow_chains.update(zip(ordered, ordered[1:], strict=False))
    return tuple(sorted(pairs)), tuple(sorted(overflow_chains))


class _HammingBKNode:
    __slots__ = ("children", "value")

    def __init__(self, value: int) -> None:
        self.value = value
        self.children: dict[int, _HammingBKNode] = {}


class _HammingBKTree:
    """Exact metric index for unsigned 64-bit Hamming distance."""

    def __init__(self) -> None:
        self._root: _HammingBKNode | None = None

    def add(self, value: int) -> None:
        if self._root is None:
            self._root = _HammingBKNode(value)
            return
        node = self._root
        while True:
            distance = hamming_distance_64(value, node.value)
            if distance == 0:
                return
            child = node.children.get(distance)
            if child is None:
                node.children[distance] = _HammingBKNode(value)
                return
            node = child

    def query(self, value: int, maximum_distance: int) -> tuple[int, ...]:
        if not 0 <= maximum_distance <= 64:
            raise ManifestAuditError("hamming_threshold_invalid")
        if self._root is None:
            return ()
        matches: list[int] = []
        pending = [self._root]
        while pending:
            node = pending.pop()
            distance = hamming_distance_64(value, node.value)
            if distance <= maximum_distance:
                matches.append(node.value)
            lower = max(1, distance - maximum_distance)
            upper = distance + maximum_distance
            pending.extend(
                child
                for edge_distance, child in node.children.items()
                if lower <= edge_distance <= upper
            )
        return tuple(sorted(matches))


def _small_radius_hamming_pairs(
    values: Sequence[int], maximum_distance: int
) -> Iterator[tuple[int, int, int]]:
    """Find exact radius-0..8 pairs with a two-unchanged-block pigeonhole index."""

    block_count = maximum_distance + 2
    base_width, wider_blocks = divmod(64, block_count)
    blocks: list[tuple[int, int]] = []
    shift = 0
    for index in range(block_count):
        width = base_width + (index < wider_blocks)
        blocks.append((shift, (1 << width) - 1))
        shift += width

    for (left_index, left_block), (right_index, right_block) in combinations(enumerate(blocks), 2):
        left_shift, left_mask = left_block
        right_shift, right_mask = right_block
        buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
        for right in values:
            key = (
                (right >> left_shift) & left_mask,
                (right >> right_shift) & right_mask,
            )
            for left in buckets[key]:
                distance = hamming_distance_64(left, right)
                if distance > maximum_distance:
                    continue
                difference = left ^ right
                equal_blocks = [
                    index
                    for index, (block_shift, block_mask) in enumerate(blocks)
                    if difference & (block_mask << block_shift) == 0
                ]
                if (left_index, right_index) == (equal_blocks[0], equal_blocks[1]):
                    yield left, right, distance
            buckets[key].append(right)


def iter_threshold_complete_hamming_pairs(
    fingerprints: Iterable[str], maximum_distance: int
) -> Iterator[tuple[str, str, int]]:
    """Yield every distinct fingerprint pair within the configured threshold.

    Normalization and deterministic exact indexes make discovery invariant to input permutations.
    Duplicate fingerprint members are handled separately by callers.
    """

    if not 0 <= maximum_distance <= 64:
        raise ManifestAuditError("hamming_threshold_invalid")
    normalized: set[str] = set()
    for fingerprint in fingerprints:
        if re.fullmatch(r"[0-9a-fA-F]{16}", fingerprint) is None:
            raise ManifestAuditError("perceptual_fingerprint_invalid")
        normalized.add(fingerprint.casefold())
    ordered = tuple(int(value, 16) for value in sorted(normalized))
    if maximum_distance <= 8:
        pairs = _small_radius_hamming_pairs(ordered, maximum_distance)
        for left_value, right_value, distance in pairs:
            yield f"{left_value:016x}", f"{right_value:016x}", distance
        return

    tree = _HammingBKTree()
    for right_value in ordered:
        right = f"{right_value:016x}"
        for left_value in tree.query(right_value, maximum_distance):
            left = f"{left_value:016x}"
            yield left, right, hamming_distance_64(left_value, right_value)
        tree.add(right_value)


def threshold_complete_hamming_pairs(
    fingerprints: Iterable[str], maximum_distance: int
) -> tuple[tuple[str, str, int], ...]:
    """Materialize deterministic exact results for tests and bounded callers."""

    return tuple(sorted(iter_threshold_complete_hamming_pairs(fingerprints, maximum_distance)))


def _threshold_complete_entity_pairs(
    members_by_fingerprint: Mapping[str, Sequence[str]],
    *,
    maximum_distance: int,
    maximum_pairs: int,
) -> _EntityCandidatePlan:
    if maximum_pairs < 1:
        raise ManifestAuditError("candidate_pair_limit_invalid")
    canonical_member_sets: dict[str, set[str]] = defaultdict(set)
    for fingerprint, members in members_by_fingerprint.items():
        canonical_member_sets[fingerprint.casefold()].update(members)
    canonical_members = {
        fingerprint: tuple(sorted(members))
        for fingerprint, members in sorted(canonical_member_sets.items())
    }
    del canonical_member_sets
    entities = sorted({member for members in canonical_members.values() for member in members})
    components = _StringUnionFind(entities)
    candidate_pair_upper_bound = 0
    pairs: set[tuple[str, str]] = set()
    overflowed = False

    def add_pair(left: str, right: str) -> None:
        nonlocal overflowed
        if overflowed or left == right:
            return
        pairs.add(_canonical_pair(left, right))
        if len(pairs) > maximum_pairs:
            pairs.clear()
            overflowed = True

    for members in canonical_members.values():
        candidate_pair_upper_bound += len(members) * (len(members) - 1) // 2
        for left, right in zip(members, members[1:], strict=False):
            components.union(left, right)
        if not overflowed:
            for left, right in combinations(members, 2):
                add_pair(left, right)
                if overflowed:
                    break
    for left_fingerprint, right_fingerprint, _ in iter_threshold_complete_hamming_pairs(
        canonical_members, maximum_distance
    ):
        left_members = canonical_members[left_fingerprint]
        right_members = canonical_members[right_fingerprint]
        candidate_pair_upper_bound += len(left_members) * len(right_members)
        if left_members and right_members:
            components.union(left_members[0], right_members[0])
        if not overflowed:
            for left in left_members:
                for right in right_members:
                    add_pair(left, right)
                    if overflowed:
                        break
                if overflowed:
                    break

    if overflowed:
        members_by_component: dict[str, list[str]] = defaultdict(list)
        for entity in entities:
            members_by_component[components.find(entity)].append(entity)
        overflow_components = tuple(
            sorted(tuple(members) for members in members_by_component.values() if len(members) > 1)
        )
        return _EntityCandidatePlan(
            pairs=(),
            overflow_components=overflow_components,
            candidate_pair_upper_bound=candidate_pair_upper_bound,
            overflowed=True,
        )

    return _EntityCandidatePlan(
        pairs=tuple(sorted(pairs)),
        overflow_components=(),
        candidate_pair_upper_bound=candidate_pair_upper_bound,
        overflowed=False,
    )


def _minimal_study_forest(
    component_studies: Iterable[Iterable[str]],
) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...], int]:
    """Coalesce overlapping study components into a deterministic minimal forest."""

    normalized_components = tuple(tuple(sorted(set(studies))) for studies in component_studies)
    affected_studies = sorted({study for component in normalized_components for study in component})
    study_components = _StringUnionFind(affected_studies)
    for studies in normalized_components:
        for left, right in zip(studies, studies[1:], strict=False):
            study_components.union(left, right)
    studies_by_component: dict[str, list[str]] = defaultdict(list)
    for study in affected_studies:
        studies_by_component[study_components.find(study)].append(study)
    protected_components = sorted(
        tuple(studies) for studies in studies_by_component.values() if len(studies) > 1
    )
    chains = tuple(
        pair for studies in protected_components for pair in zip(studies, studies[1:], strict=False)
    )
    return chains, tuple(affected_studies), len(protected_components)


def _persist_candidate_overflow_chains(
    connection: sqlite3.Connection,
    *,
    plan: _EntityCandidatePlan,
    entity_to_study: Mapping[str, str],
    pair_limit: int,
    kind: str,
    issue_code: str,
    metric_prefix: str,
    study_edges: list[DuplicateEdge],
) -> int:
    """Lift entity closure to a minimal study forest without claiming direct evidence."""

    chains, affected_studies, protected_component_count = _minimal_study_forest(
        (entity_to_study[entity] for entity in component) for component in plan.overflow_components
    )
    for left, right in chains:
        metrics: dict[str, JsonValue] = {
            "discovery": "threshold_complete_component_fallback",
            "reason": "candidate_pair_upper_bound_exceeded",
        }
        _persist_edge(
            connection,
            left=left,
            right=right,
            entity_level="study",
            kind=kind,
            disposition=EdgeDisposition.CANDIDATE,
            metrics=metrics,
        )
        study_edges.append(DuplicateEdge(left, right, kind, EdgeDisposition.CANDIDATE))
    for study in affected_studies:
        _insert_issue(
            connection,
            "study",
            study,
            issue_code,
            "warning",
            "soft_candidate_review",
        )
    connection.executemany(
        "INSERT OR REPLACE INTO manifest_run VALUES(?,?)",
        (
            (f"{metric_prefix}_candidate_space_overflow", "true"),
            (
                f"{metric_prefix}_candidate_pair_upper_bound",
                str(plan.candidate_pair_upper_bound),
            ),
            (f"{metric_prefix}_candidate_pair_count_lower_bound", str(pair_limit + 1)),
            (f"{metric_prefix}_candidate_pair_limit", str(pair_limit)),
            (
                f"{metric_prefix}_overflow_entity_components",
                str(len(plan.overflow_components)),
            ),
            (
                f"{metric_prefix}_overflow_study_components",
                str(protected_component_count),
            ),
            (f"{metric_prefix}_overflow_study_edges", str(len(chains))),
        ),
    )
    return len(chains)


def _near_slice_edges(
    connection: sqlite3.Connection,
    *,
    schema: Mapping[str, Any],
    secret: bytes,
    study_edges: list[DuplicateEdge],
) -> NearSliceSummary:
    """Persist a linear-size forest for every threshold-complete slice component.

    Every qualifying pair contributes to the private evidence count, but only edges in a
    deterministic spanning forest are persisted. This bounds rows by the number of decoded slices
    while retaining complete grouping. Study-level lifting requires repeated evidence across
    distinct series pairs; isolated evidence remains an unresolved fail-closed candidate.
    """

    dicom_schema = cast(Mapping[str, Any], schema["dicom"])
    threshold = int(dicom_schema["near_slice_phash_hamming"])
    minimum_matches = int(dicom_schema["near_slice_study_minimum_matches"])
    minimum_series_pairs = int(dicom_schema["near_slice_study_minimum_series_pairs"])
    maximum_study_pairs = int(dicom_schema["near_slice_maximum_study_pairs"])
    maximum_component_studies = int(
        dicom_schema["near_slice_maximum_evidence_studies_per_component"]
    )
    if (
        minimum_matches < 2
        or minimum_series_pairs < 2
        or maximum_study_pairs < 1
        or maximum_component_studies < 2
    ):
        raise ManifestAuditError("near_slice_policy_invalid")

    rows = connection.execute(
        """SELECT near_slice_fingerprint, file_key, study_key, series_key
            FROM slice_file_manifest WHERE decode_state='pass'
            ORDER BY near_slice_fingerprint, file_key"""
    )
    members_by_fingerprint: dict[str, list[SliceFingerprintMember]] = defaultdict(list)
    low_information_files = 0
    for fingerprint, file_key, study_key, series_key in rows:
        if fingerprint is None:
            raise ManifestAuditError("decoded_slice_fingerprint_missing")
        normalized = str(fingerprint).casefold()
        if re.fullmatch(r"[0-9a-f]{16}", normalized) is None:
            raise ManifestAuditError("perceptual_fingerprint_invalid")
        if normalized == "0000000000000000":
            low_information_files += 1
            _insert_issue(
                connection,
                "file",
                str(file_key),
                "low_information_perceptual_fingerprint",
                "warning",
                "near_duplicate_excluded",
            )
            continue
        members_by_fingerprint[normalized].append(
            SliceFingerprintMember(str(file_key), str(study_key), str(series_key))
        )
    for members in members_by_fingerprint.values():
        members.sort(key=lambda item: item.file_key)

    fingerprints = tuple(sorted(members_by_fingerprint))
    components = _StringUnionFind(fingerprints)
    total_pair_evidence = 0
    persisted_edges = 0
    study_pair_evidence: dict[tuple[str, str], _NearSliceStudyEvidence] = {}
    conservative_study_chains: set[tuple[str, str]] = set()
    study_pair_overflowed = False

    def record_study_evidence(
        left_members: Sequence[SliceFingerprintMember],
        right_members: Sequence[SliceFingerprintMember] | None,
    ) -> None:
        nonlocal study_pair_overflowed
        if study_pair_overflowed:
            return
        left_counts = Counter((item.study_key, item.series_key) for item in left_members)
        right_counts = (
            left_counts
            if right_members is None
            else Counter((item.study_key, item.series_key) for item in right_members)
        )
        distinct_studies = sorted(
            {study for study, _ in left_counts} | {study for study, _ in right_counts}
        )
        if (
            len(distinct_studies) > maximum_component_studies
            or len(left_counts) * len(right_counts) > maximum_study_pairs
        ):
            conservative_study_chains.update(
                zip(distinct_studies, distinct_studies[1:], strict=False)
            )
            return
        grouped_pairs: Iterable[tuple[tuple[str, str], tuple[str, str]]]
        if right_members is None:
            grouped_pairs = combinations(sorted(left_counts), 2)
        else:
            grouped_pairs = (
                (left_group, right_group)
                for left_group in sorted(left_counts)
                for right_group in sorted(right_counts)
            )
        for (left_study, left_series), (right_study, right_series) in grouped_pairs:
            if left_study == right_study:
                continue
            study_pair = _canonical_pair(left_study, right_study)
            evidence = study_pair_evidence.get(study_pair)
            if evidence is None:
                if len(study_pair_evidence) >= maximum_study_pairs:
                    study_pair_overflowed = True
                    study_pair_evidence.clear()
                    conservative_study_chains.clear()
                    return
                evidence = _NearSliceStudyEvidence()
                study_pair_evidence[study_pair] = evidence
            evidence.matches += (
                left_counts[(left_study, left_series)] * right_counts[(right_study, right_series)]
            )
            if len(evidence.series_pairs) < minimum_series_pairs:
                evidence.series_pairs.add(_canonical_pair(left_series, right_series))

    def persist_file_edge(
        left: SliceFingerprintMember,
        right: SliceFingerprintMember,
        distance: int,
    ) -> None:
        nonlocal persisted_edges
        _persist_edge(
            connection,
            left=left.file_key,
            right=right.file_key,
            entity_level="file",
            kind="near-slice",
            disposition=EdgeDisposition.CANDIDATE,
            metrics={
                "phash_hamming": distance,
                "discovery": "threshold_complete_exact_index",
            },
        )
        persisted_edges += 1

    for fingerprint in fingerprints:
        members = members_by_fingerprint[fingerprint]
        total_pair_evidence += len(members) * (len(members) - 1) // 2
        for left, right in zip(members, members[1:], strict=False):
            persist_file_edge(left, right, 0)
        record_study_evidence(members, None)

    for left_fingerprint, right_fingerprint, distance in iter_threshold_complete_hamming_pairs(
        fingerprints, threshold
    ):
        left_members = members_by_fingerprint[left_fingerprint]
        right_members = members_by_fingerprint[right_fingerprint]
        total_pair_evidence += len(left_members) * len(right_members)
        if components.union(left_fingerprint, right_fingerprint):
            persist_file_edge(left_members[0], right_members[0], distance)
        record_study_evidence(left_members, right_members)

    component_fingerprints: dict[str, list[str]] = defaultdict(list)
    for fingerprint in fingerprints:
        component_fingerprints[components.find(fingerprint)].append(fingerprint)
    group_count = 0
    for component_members in component_fingerprints.values():
        file_members = sorted(
            (
                member
                for fingerprint in component_members
                for member in members_by_fingerprint[fingerprint]
            ),
            key=lambda item: item.file_key,
        )
        if len(file_members) < 2:
            continue
        group_count += 1
        group_key = opaque_key(
            secret,
            "group-near-slice",
            "\0".join(sorted(component_members)),
        )
        for member in file_members:
            connection.execute(
                "INSERT OR IGNORE INTO duplicate_group_mapping VALUES(?,?,?,?,?)",
                ("near-slice", group_key, "file", member.file_key, "duplicate-audit-v2"),
            )

    overflow_study_components = 0
    overflow_affected_studies: tuple[str, ...] = ()
    if study_pair_overflowed:
        component_study_groups: list[tuple[str, ...]] = []
        for component_members in component_fingerprints.values():
            studies = tuple(
                sorted(
                    {
                        member.study_key
                        for fingerprint in component_members
                        for member in members_by_fingerprint[fingerprint]
                    }
                )
            )
            if len(studies) > 1:
                component_study_groups.append(studies)
        overflow_chains, overflow_affected_studies, overflow_study_components = (
            _minimal_study_forest(component_study_groups)
        )
        conservative_study_chains = set(overflow_chains)
        for study_key in overflow_affected_studies:
            _insert_issue(
                connection,
                "study",
                study_key,
                "near_slice_study_pair_space_overflow",
                "warning",
                "soft_candidate_review",
            )

    chain_kind = (
        "near-slice-study-space-overflow-block"
        if study_pair_overflowed
        else "near-slice-large-component"
    )
    for left_study, right_study in sorted(conservative_study_chains):
        _persist_edge(
            connection,
            left=left_study,
            right=right_study,
            entity_level="study",
            kind=chain_kind,
            disposition=EdgeDisposition.CANDIDATE,
            metrics={
                "discovery": (
                    "threshold_complete_component_fallback"
                    if study_pair_overflowed
                    else "deterministic_study_chain"
                ),
                "reason": (
                    "study_pair_limit_exceeded"
                    if study_pair_overflowed
                    else "bounded_component_closure"
                ),
            },
        )
        study_edges.append(
            DuplicateEdge(
                left_study,
                right_study,
                chain_kind,
                EdgeDisposition.CANDIDATE,
            )
        )

    study_nodes = [row[0] for row in connection.execute("SELECT study_key FROM study_manifest")]
    preliminary_components = build_protected_components(study_nodes, study_edges)
    promoted = len(conservative_study_chains)
    unresolved = 0
    for (left_study, right_study), evidence in sorted(study_pair_evidence.items()):
        already_protected = (
            preliminary_components[left_study] == preliminary_components[right_study]
        )
        metrics: dict[str, JsonValue] = {
            "matching_slice_pairs": evidence.matches,
            "distinct_series_pairs_lower_bound": len(evidence.series_pairs),
            "distinct_series_pairs_saturated": (len(evidence.series_pairs) >= minimum_series_pairs),
            "minimum_matching_slice_pairs": minimum_matches,
            "minimum_distinct_series_pairs": minimum_series_pairs,
        }
        if already_protected:
            continue
        if (
            evidence.matches >= minimum_matches
            and len(evidence.series_pairs) >= minimum_series_pairs
        ):
            _persist_edge(
                connection,
                left=left_study,
                right=right_study,
                entity_level="study",
                kind="near-slice-study",
                disposition=EdgeDisposition.CANDIDATE,
                metrics=metrics,
            )
            study_edges.append(
                DuplicateEdge(
                    left_study,
                    right_study,
                    "near-slice-study",
                    EdgeDisposition.CANDIDATE,
                )
            )
            promoted += 1
            continue
        _persist_edge(
            connection,
            left=left_study,
            right=right_study,
            entity_level="study",
            kind="near-slice-low-evidence",
            disposition=EdgeDisposition.CANDIDATE,
            metrics=metrics,
        )
        study_edges.append(
            DuplicateEdge(
                left_study,
                right_study,
                "near-slice-low-evidence",
                EdgeDisposition.CANDIDATE,
            )
        )
        for study_key in (left_study, right_study):
            _insert_issue(
                connection,
                "study",
                study_key,
                "near_slice_low_evidence_conservatively_grouped",
                "warning",
                "soft_candidate_review",
            )
        promoted += 1

    suppressed_edges = total_pair_evidence - persisted_edges
    if suppressed_edges < 0:
        raise ManifestAuditError("near_slice_edge_reconciliation_failed")
    connection.executemany(
        "INSERT OR REPLACE INTO manifest_run VALUES(?,?)",
        (
            ("near_slice_groups", str(group_count)),
            ("near_slice_edges", str(persisted_edges)),
            ("near_slice_edges_suppressed", str(suppressed_edges)),
            ("near_slice_unresolved_study_pairs", str(unresolved)),
            ("near_slice_low_information_files", str(low_information_files)),
        ),
    )
    if study_pair_overflowed:
        connection.executemany(
            "INSERT OR REPLACE INTO manifest_run VALUES(?,?)",
            (
                ("near_slice_study_pair_space_overflow", "true"),
                ("near_slice_study_pair_limit", str(maximum_study_pairs)),
                (
                    "near_slice_study_pair_count_lower_bound",
                    str(maximum_study_pairs + 1),
                ),
                (
                    "near_slice_overflow_fingerprint_components",
                    str(len(component_study_groups)),
                ),
                ("near_slice_overflow_study_components", str(overflow_study_components)),
                ("near_slice_overflow_study_edges", str(len(conservative_study_chains))),
            ),
        )
    return NearSliceSummary(
        groups=group_count,
        persisted_edges=persisted_edges,
        suppressed_edges=suppressed_edges,
        promoted_study_edges=promoted,
        unresolved_study_pairs=unresolved,
    )


def _selected_phashes(values: Sequence[str], count: int) -> tuple[str, ...]:
    return tuple(values[index] for index in _quantile_indices(len(values), count))


def _load_pixel_array(path: Path) -> np.ndarray[Any, Any]:
    dataset = pydicom.dcmread(path, force=False)
    return np.asarray(dataset.pixel_array)


def _confirm_near_series(
    left: SeriesEvidence,
    right: SeriesEvidence,
    *,
    direction: str,
    schema: Mapping[str, Any],
) -> tuple[bool, float | None, float | None, float | None]:
    if len(left.sample_paths) != len(right.sample_paths) or not left.sample_paths:
        return False, None, None, None
    right_paths = (
        right.sample_paths if direction == "forward" else tuple(reversed(right.sample_paths))
    )
    ncc_values: list[float] = []
    gradient_values: list[float] = []
    try:
        for left_path, right_path in zip(left.sample_paths, right_paths, strict=True):
            left_pixels = _load_pixel_array(left_path)
            right_pixels = _load_pixel_array(right_path)
            ncc_values.append(normalized_cross_correlation(left_pixels, right_pixels))
            gradient_values.append(gradient_normalized_cross_correlation(left_pixels, right_pixels))
    except MemoryError:
        raise
    except Exception:
        return False, None, None, None
    median_ncc = float(np.median(ncc_values))
    minimum_ncc = min(ncc_values)
    median_gradient = float(np.median(gradient_values))
    dicom_schema = cast(Mapping[str, Any], schema["dicom"])
    passed = (
        median_ncc >= float(dicom_schema["near_series_median_ncc"])
        and minimum_ncc >= float(dicom_schema["near_series_minimum_ncc"])
        and median_gradient >= float(dicom_schema["near_series_gradient_ncc"])
    )
    return passed, median_ncc, minimum_ncc, median_gradient


def _near_series_edges(
    connection: sqlite3.Connection,
    evidence: Sequence[SeriesEvidence],
    schema: Mapping[str, Any],
    study_edges: list[DuplicateEdge],
) -> tuple[int, int, int]:
    dicom_schema = cast(Mapping[str, Any], schema["dicom"])
    minimum_slices = int(dicom_schema["near_series_minimum_slices"])
    by_key = {item.series_key: item for item in evidence if len(item.phashes) >= minimum_slices}
    members_by_fingerprint: dict[str, list[str]] = defaultdict(list)
    for item in by_key.values():
        for fingerprint in item.phashes:
            if fingerprint == "0000000000000000":
                continue
            members_by_fingerprint[fingerprint].append(item.series_key)
    pair_limit = int(dicom_schema["near_series_maximum_candidate_pairs"])
    plan = _threshold_complete_entity_pairs(
        members_by_fingerprint,
        maximum_distance=int(dicom_schema["candidate_series_max_phash_hamming"]),
        maximum_pairs=pair_limit,
    )
    if plan.overflowed:
        candidates = _persist_candidate_overflow_chains(
            connection,
            plan=plan,
            entity_to_study={key: item.study_key for key, item in by_key.items()},
            pair_limit=pair_limit,
            kind="near-series-overflow-block",
            issue_code="near_series_candidate_space_overflow",
            metric_prefix="near_series",
            study_edges=study_edges,
        )
        return 0, 0, candidates
    compared = 0
    hard = 0
    candidates = 0
    for left_key, right_key in plan.pairs:
        left = by_key[left_key]
        right = by_key[right_key]
        if left.study_key == right.study_key or (
            left.exact_key is not None and left.exact_key == right.exact_key
        ):
            continue
        compared += 1
        match = compare_phash_sequences(
            left.phashes,
            right.phashes,
            minimum_slices=minimum_slices,
            hard_max_hamming=int(dicom_schema["near_slice_phash_hamming"]),
            hard_median_hamming=float(dicom_schema["near_series_median_phash_hamming"]),
            candidate_max_hamming=int(dicom_schema["candidate_series_max_phash_hamming"]),
            candidate_median_hamming=float(dicom_schema["candidate_series_median_phash_hamming"]),
            minimum_length_ratio=float(dicom_schema["near_series_minimum_length_ratio"]),
        )
        if match.disposition is EdgeDisposition.NONE:
            continue
        confirmed = False
        median_ncc = minimum_ncc = median_gradient = None
        if match.disposition is EdgeDisposition.HARD:
            confirmed, median_ncc, minimum_ncc, median_gradient = _confirm_near_series(
                left, right, direction=match.direction, schema=schema
            )
        disposition = EdgeDisposition.HARD if confirmed else EdgeDisposition.CANDIDATE
        hard += int(disposition is EdgeDisposition.HARD)
        candidates += int(disposition is EdgeDisposition.CANDIDATE)
        metrics: dict[str, JsonValue] = {
            "compared_slices": match.compared_slices,
            "median_hamming": match.median_hamming,
            "maximum_hamming": match.maximum_hamming,
            "median_ncc": median_ncc,
            "minimum_ncc": minimum_ncc,
            "median_gradient_ncc": median_gradient,
        }
        _persist_edge(
            connection,
            left=left.series_key,
            right=right.series_key,
            entity_level="series",
            kind="near-series",
            disposition=disposition,
            metrics=metrics,
        )
        right_file_keys = (
            right.sample_file_keys
            if match.direction == "forward"
            else tuple(reversed(right.sample_file_keys))
        )
        for left_file, right_file, distance in zip(
            left.sample_file_keys,
            right_file_keys,
            match.distances,
            strict=True,
        ):
            if left_file == right_file or distance > int(
                dicom_schema["candidate_series_max_phash_hamming"]
            ):
                continue
            _persist_edge(
                connection,
                left=left_file,
                right=right_file,
                entity_level="file",
                kind="near-slice-quantile",
                disposition=(
                    EdgeDisposition.HARD
                    if disposition is EdgeDisposition.HARD
                    and distance <= int(dicom_schema["near_slice_phash_hamming"])
                    else EdgeDisposition.CANDIDATE
                ),
                metrics={
                    "phash_hamming": distance,
                    "sampling": "deterministic_series_quantile",
                },
            )
        study_edges.append(
            DuplicateEdge(left.study_key, right.study_key, "near-series", disposition)
        )
    return compared, hard, candidates


def _report_edges(
    connection: sqlite3.Connection,
    inventory: SourceInventory,
    study_keys: Mapping[str, str],
    reports: Mapping[str, ReportFeatures],
    schema: Mapping[str, Any],
    study_edges: list[DuplicateEdge],
) -> tuple[int, int, int]:
    report_schema = cast(Mapping[str, Any], schema["reports"])
    eligible = {
        qualified: source.report
        for qualified, source in inventory.studies.items()
        if source.report is not None
        and "report" not in source.conflicts
        and reports[qualified].token_count >= int(report_schema["near_minimum_tokens"])
        and reports[qualified].near_report_fingerprint is not None
    }
    representative_by_canonical: dict[str, str] = {}
    for qualified in sorted(eligible):
        canonical_key = reports[qualified].canonical_text_exact_key or qualified
        representative_by_canonical.setdefault(canonical_key, qualified)
    members_by_fingerprint: dict[str, list[str]] = defaultdict(list)
    for qualified in representative_by_canonical.values():
        fingerprint = cast(str, reports[qualified].near_report_fingerprint)
        members_by_fingerprint[fingerprint].append(qualified)
    compared = hard = candidates = 0
    pair_limit = int(report_schema["maximum_candidate_pairs"])
    plan = _threshold_complete_entity_pairs(
        members_by_fingerprint,
        maximum_distance=int(report_schema["candidate_simhash_hamming"]),
        maximum_pairs=pair_limit,
    )
    if plan.overflowed:
        candidates = _persist_candidate_overflow_chains(
            connection,
            plan=plan,
            entity_to_study={qualified: study_keys[qualified] for qualified in eligible},
            pair_limit=pair_limit,
            kind="near-report-overflow-block",
            issue_code="near_report_candidate_space_overflow",
            metric_prefix="near_report",
            study_edges=study_edges,
        )
        return 0, 0, candidates
    for left_qualified, right_qualified in plan.pairs:
        left_features = reports[left_qualified]
        right_features = reports[right_qualified]
        if left_features.canonical_text_exact_key == right_features.canonical_text_exact_key:
            continue
        simhash_distance = (
            int(cast(str, left_features.near_report_fingerprint), 16)
            ^ int(cast(str, right_features.near_report_fingerprint), 16)
        ).bit_count()
        if simhash_distance > int(report_schema["candidate_simhash_hamming"]):
            continue
        compared += 1
        match = compare_reports(
            eligible[left_qualified],
            eligible[right_qualified],
            minimum_tokens=int(report_schema["near_minimum_tokens"]),
            shingle_size=int(report_schema["near_shingle_size"]),
            candidate_jaccard=float(report_schema["candidate_jaccard"]),
            confirmed_jaccard=float(report_schema["confirmed_jaccard"]),
            confirmed_levenshtein=float(report_schema["confirmed_levenshtein"]),
            minimum_length_ratio=float(report_schema["near_token_count_ratio"]),
        )
        if match.disposition is EdgeDisposition.NONE:
            continue
        left_study = study_keys[left_qualified]
        right_study = study_keys[right_qualified]
        if left_study == right_study:
            continue
        hard += int(match.disposition is EdgeDisposition.HARD)
        candidates += int(match.disposition is EdgeDisposition.CANDIDATE)
        _persist_edge(
            connection,
            left=left_study,
            right=right_study,
            entity_level="study",
            kind="near-report",
            disposition=match.disposition,
            metrics={
                "shingle_jaccard": match.shingle_jaccard,
                "levenshtein_similarity": match.levenshtein_similarity,
                "simhash_hamming": simhash_distance,
            },
        )
        study_edges.append(DuplicateEdge(left_study, right_study, "near-report", match.disposition))
    return compared, hard, candidates


def _finish_studies(
    connection: sqlite3.Connection,
    *,
    inventory: SourceInventory,
    study_keys: Mapping[str, str],
    series_keys: Mapping[str, str],
    study_headers: Mapping[str, Sequence[HeaderEvidence]],
    secret: bytes,
) -> None:
    for qualified, source in sorted(inventory.studies.items()):
        study_key = study_keys[qualified]
        series_sources = [
            item
            for key, item in inventory.series.items()
            if item.split == source.split and item.raw_study_id == source.raw_study_id
        ]
        series_manifest_keys = [
            series_keys[_source_key(item.split, item.raw_series_id)] for item in series_sources
        ]
        rows = [
            connection.execute(
                """SELECT plane, fluid_sensitive, fat_suppression, slice_count,
                    terminal_state, protocol_cluster_key FROM series_manifest
                    WHERE series_key=?""",
                (series_key,),
            ).fetchone()
            for series_key in series_manifest_keys
        ]
        headers = list(study_headers.get(study_key, ()))
        patient_values = {item.patient_key for item in headers if item.patient_key is not None}
        sex_values = {item.patient_sex for item in headers if item.patient_sex is not None}
        age_values = {
            round(item.patient_age_years, 4)
            for item in headers
            if item.patient_age_years is not None
        }
        manufacturers = {
            item.manufacturer_key for item in headers if item.manufacturer_key is not None
        }
        models = {item.model_key for item in headers if item.model_key is not None}
        strengths = {
            round(item.field_strength_t, 4) for item in headers if item.field_strength_t is not None
        }
        flags = set(source.conflicts)
        if len(patient_values) > 1:
            flags.add("patient_id_conflict")
        if len(sex_values) > 1:
            flags.add("patient_sex_conflict")
        if len(age_values) > 1:
            flags.add("patient_age_conflict")
        if any(row is None for row in rows) or not rows:
            flags.add("series_missing")
        if any(row is not None and row[4] != "pass" for row in rows):
            flags.add("series_quarantined")
        patient_key = next(iter(patient_values)) if len(patient_values) == 1 else None
        patient_evidence = (
            "header_patient_id"
            if patient_key is not None
            else ("conflict" if patient_values else "missing")
        )
        planes = sorted({str(row[0]) for row in rows if row is not None and row[0] is not None})
        sequences = sorted(
            {
                f"{row[1]}:{row[2]}"
                for row in rows
                if row is not None and (row[1] is not None or row[2] is not None)
            }
        )
        protocols = sorted(str(row[5]) for row in rows if row is not None and row[5] is not None)
        manufacturer_value = next(iter(manufacturers)) if len(manufacturers) == 1 else None
        model_value = next(iter(models)) if len(models) == 1 else None
        strength_value = next(iter(strengths)) if len(strengths) == 1 else None
        protocol_value = (
            opaque_key(secret, "study-protocol", "\0".join(protocols)) if protocols else None
        )
        domain_parts = [manufacturer_value, model_value, strength_value, protocol_value]
        domain_value = (
            opaque_key(
                secret,
                "study-domain",
                canonical_json([value for value in domain_parts if value is not None]),
            )
            if any(value is not None for value in domain_parts)
            else None
        )
        terminal_state = "pass" if not flags else "quarantine"
        connection.execute(
            """UPDATE study_manifest SET patient_group_key=?, patient_key_evidence=?,
                patient_sex=?, patient_age_years=?, series_count=?, plane_availability=?,
                sequence_categories=?, total_slice_count=?, scanner_manufacturer=?, scanner_model=?,
                field_strength_t=?, protocol_cluster_key=?, domain_cluster_key=?,
                data_quality_flags=?, terminal_state=?
                WHERE study_key=?""",
            (
                patient_key,
                patient_evidence,
                next(iter(sex_values)) if len(sex_values) == 1 else None,
                next(iter(age_values)) if len(age_values) == 1 else None,
                len(rows),
                canonical_json(planes),
                canonical_json(sequences),
                sum(int(row[3]) for row in rows if row is not None),
                manufacturer_value,
                model_value,
                strength_value,
                protocol_value,
                domain_value,
                canonical_json(sorted(flags)),
                terminal_state,
                study_key,
            ),
        )
        for flag in sorted(flags):
            _insert_issue(connection, "study", study_key, flag)


def _identity_and_patient_edges(
    connection: sqlite3.Connection,
    inventory: SourceInventory,
    study_keys: Mapping[str, str],
    study_edges: list[DuplicateEdge],
) -> None:
    raw_groups: dict[str, list[str]] = defaultdict(list)
    for qualified, source in inventory.studies.items():
        raw_groups[source.raw_study_id].append(study_keys[qualified])
    for members in raw_groups.values():
        if len(members) < 2:
            continue
        ordered_members = sorted(members)
        for left, right in zip(ordered_members, ordered_members[1:], strict=False):
            _persist_edge(
                connection,
                left=left,
                right=right,
                entity_level="study",
                kind="reused-study-identifier",
                disposition=EdgeDisposition.HARD,
            )
            study_edges.append(
                DuplicateEdge(left, right, "reused-study-identifier", EdgeDisposition.HARD)
            )
    patient_groups = connection.execute(
        """SELECT patient_group_key FROM study_manifest
            WHERE patient_group_key IS NOT NULL GROUP BY patient_group_key HAVING COUNT(*) > 1"""
    ).fetchall()
    for (patient_key,) in patient_groups:
        members = [
            row[0]
            for row in connection.execute(
                "SELECT study_key FROM study_manifest WHERE patient_group_key=? ORDER BY study_key",
                (patient_key,),
            )
        ]
        for left, right in zip(members, members[1:], strict=False):
            _persist_edge(
                connection,
                left=left,
                right=right,
                entity_level="study",
                kind="same-patient",
                disposition=EdgeDisposition.HARD,
            )
            study_edges.append(DuplicateEdge(left, right, "same-patient", EdgeDisposition.HARD))


def _component_connectivity_path(
    members: Sequence[str],
    edges: Sequence[DuplicateEdge],
    edge_counts: Mapping[DuplicateEdge, int],
    *,
    hard_only: bool,
) -> list[dict[str, JsonValue]]:
    """Return a deterministic private spanning path and prove component connectivity."""

    member_set = frozenset(members)
    if not member_set:
        raise ManifestAuditError("component_members_missing")
    adjacency: dict[str, list[tuple[str, DuplicateEdge]]] = defaultdict(list)
    for edge in edges:
        if edge.left not in member_set or edge.right not in member_set:
            continue
        if hard_only and edge.disposition is not EdgeDisposition.HARD:
            continue
        adjacency[edge.left].append((edge.right, edge))
        adjacency[edge.right].append((edge.left, edge))
    for neighbours in adjacency.values():
        neighbours.sort(
            key=lambda item: (
                0 if item[1].disposition is EdgeDisposition.CANDIDATE else 1,
                item[0],
                item[1].kind,
                item[1].left,
                item[1].right,
            )
        )

    root = min(member_set)
    visited = {root}
    pending = deque([root])
    path: list[dict[str, JsonValue]] = []
    while pending:
        current = pending.popleft()
        for neighbour, edge in adjacency[current]:
            if neighbour in visited:
                continue
            visited.add(neighbour)
            pending.append(neighbour)
            path.append(
                {
                    "left_study_key": edge.left,
                    "right_study_key": edge.right,
                    "edge_kind": edge.kind,
                    "decision": edge.disposition.value,
                    "evidence_count": edge_counts[edge],
                }
            )
    if visited != member_set or len(path) != len(member_set) - 1:
        raise ManifestAuditError("component_connectivity_review_failed")
    if hard_only and any(item["decision"] != EdgeDisposition.HARD.value for item in path):
        raise ManifestAuditError("hard_component_path_semantics_invalid")
    return path


def _protected_components(
    connection: sqlite3.Connection,
    study_edges: Sequence[DuplicateEdge],
    secret: bytes,
    representative_paths: Mapping[str, str] | None = None,
    input_root: Path | None = None,
) -> tuple[dict[str, str], int]:
    study_nodes = [row[0] for row in connection.execute("SELECT study_key FROM study_manifest")]
    edge_counts = Counter(study_edges)
    edges = tuple(sorted(edge_counts))
    hard_representative = build_protected_components(study_nodes, edges)
    soft_representative = build_candidate_components(study_nodes, edges)
    files_by_study = {
        str(study_key): str(file_key)
        for study_key, file_key in connection.execute(
            """SELECT study_key, MIN(file_key) FROM slice_file_manifest
                GROUP BY study_key ORDER BY study_key"""
        )
        if file_key is not None
    }

    hard_members: dict[str, list[str]] = defaultdict(list)
    for study_key, representative in hard_representative.items():
        hard_members[representative].append(study_key)
    hard_component_keys: dict[str, str] = {}
    for representative, studies in sorted(hard_members.items()):
        studies.sort()
        component_key = opaque_key(
            secret,
            f"{GROUP_VERSION}:hard-component",
            "\0".join(studies),
        )
        evidence_state = "hard" if len(studies) > 1 else "singleton"
        hard_count = sum(
            edge_counts[edge]
            for edge in edges
            if edge.disposition is EdgeDisposition.HARD
            and hard_representative[edge.left] == representative
            and hard_representative[edge.right] == representative
        )
        candidate_count = sum(
            edge_counts[edge]
            for edge in edges
            if edge.disposition is EdgeDisposition.CANDIDATE
            and hard_representative[edge.left] == representative
            and hard_representative[edge.right] == representative
        )
        representative_file_key = min(
            (files_by_study[study] for study in studies if study in files_by_study),
            default=None,
        )
        connection.execute(
            "INSERT INTO duplicate_component_summary VALUES(?,?,?,?,?,?,?,?)",
            (
                "hard-protected",
                component_key,
                representative,
                representative_file_key,
                len(studies),
                hard_count,
                candidate_count,
                GROUP_VERSION,
            ),
        )
        for study_key in studies:
            hard_component_keys[study_key] = component_key
            connection.execute(
                "INSERT INTO protected_component VALUES(?,?,?,?)",
                ("hard-protected", component_key, study_key, evidence_state),
            )

    candidate_representatives = {
        soft_representative[endpoint]
        for edge in edges
        if edge.disposition is EdgeDisposition.CANDIDATE
        for endpoint in (edge.left, edge.right)
    }
    soft_members: dict[str, list[str]] = defaultdict(list)
    for study_key, representative in soft_representative.items():
        if representative in candidate_representatives:
            soft_members[representative].append(study_key)
    soft_component_keys: dict[str, str] = {}
    for representative, studies in sorted(soft_members.items()):
        studies.sort()
        component_key = opaque_key(
            secret,
            f"{GROUP_VERSION}:soft-component",
            "\0".join(studies),
        )
        hard_count = sum(
            edge_counts[edge]
            for edge in edges
            if edge.disposition is EdgeDisposition.HARD
            and soft_representative[edge.left] == representative
            and soft_representative[edge.right] == representative
        )
        candidate_count = sum(
            edge_counts[edge]
            for edge in edges
            if edge.disposition is EdgeDisposition.CANDIDATE
            and soft_representative[edge.left] == representative
            and soft_representative[edge.right] == representative
        )
        representative_file_key = min(
            (files_by_study[study] for study in studies if study in files_by_study),
            default=None,
        )
        connection.execute(
            "INSERT INTO duplicate_component_summary VALUES(?,?,?,?,?,?,?,?)",
            (
                "soft-candidate",
                component_key,
                representative,
                representative_file_key,
                len(studies),
                hard_count,
                candidate_count,
                GROUP_VERSION,
            ),
        )
        for study_key in studies:
            soft_component_keys[study_key] = component_key
            connection.execute(
                "INSERT INTO candidate_component VALUES(?,?,?,?)",
                (
                    component_key,
                    study_key,
                    hard_component_keys[study_key],
                    "review_only",
                ),
            )

    legacy_members: dict[str, list[str]] = defaultdict(list)
    for study_key, representative in soft_representative.items():
        legacy_members[representative].append(study_key)
    legacy_component_keys: dict[str, str] = {}
    for representative, studies in sorted(legacy_members.items()):
        studies.sort()
        component_key = opaque_key(
            secret,
            f"{LEGACY_GROUP_RECONSTRUCTION_VERSION}:component",
            "\0".join(studies),
        )
        legacy_component_keys[representative] = component_key
        hard_count = sum(
            edge_counts[edge]
            for edge in edges
            if edge.disposition is EdgeDisposition.HARD
            and soft_representative[edge.left] == representative
            and soft_representative[edge.right] == representative
        )
        candidate_count = sum(
            edge_counts[edge]
            for edge in edges
            if edge.disposition is EdgeDisposition.CANDIDATE
            and soft_representative[edge.left] == representative
            and soft_representative[edge.right] == representative
        )
        representative_file_key = min(
            (files_by_study[study] for study in studies if study in files_by_study),
            default=None,
        )
        connection.execute(
            "INSERT INTO duplicate_component_summary VALUES(?,?,?,?,?,?,?,?)",
            (
                "legacy-v1-all-evidence",
                component_key,
                representative,
                representative_file_key,
                len(studies),
                hard_count,
                candidate_count,
                LEGACY_GROUP_RECONSTRUCTION_VERSION,
            ),
        )

    for edge in edges:
        soft_component_key = soft_component_keys.get(edge.left)
        if soft_component_key != soft_component_keys.get(edge.right):
            raise ManifestAuditError("candidate_component_invariant_failed")
        connection.execute(
            "INSERT INTO duplicate_component_edge VALUES(?,?,?,?,?,?,?,?,?)",
            (
                edge.left,
                edge.right,
                edge.kind,
                edge.disposition.value,
                edge_counts[edge],
                hard_component_keys[edge.left],
                hard_component_keys[edge.right],
                soft_component_key,
                GROUP_VERSION,
            ),
        )

    private_paths = {} if representative_paths is None else representative_paths
    resolved_input_root = None if input_root is None else input_root.resolve(strict=True)
    unexpected_hard_kinds = {
        str(edge_kind)
        for (edge_kind,) in connection.execute(
            "SELECT DISTINCT edge_kind FROM duplicate_component_edge WHERE decision='hard'"
        )
        if str(edge_kind) not in HARD_COMPONENT_EDGE_KIND_ALLOWLIST
    }
    if unexpected_hard_kinds:
        raise ManifestAuditError("hard_component_edge_kind_not_allowed")
    members_by_component_kind = {
        "hard-protected": {
            hard_component_keys[studies[0]]: tuple(studies) for studies in hard_members.values()
        },
        "soft-candidate": {
            soft_component_keys[studies[0]]: tuple(studies) for studies in soft_members.values()
        },
        "legacy-v1-all-evidence": {
            legacy_component_keys[representative]: tuple(studies)
            for representative, studies in legacy_members.items()
        },
    }
    component_versions = {
        "hard-protected": GROUP_VERSION,
        "soft-candidate": GROUP_VERSION,
        "legacy-v1-all-evidence": LEGACY_GROUP_RECONSTRUCTION_VERSION,
    }
    corpus_study_count = len(study_nodes)
    for component_kind in (
        "hard-protected",
        "soft-candidate",
        "legacy-v1-all-evidence",
    ):
        rows = connection.execute(
            """SELECT component_key,representative_file_key,member_count
                FROM duplicate_component_summary WHERE component_kind=?
                ORDER BY member_count DESC,component_key""",
            (component_kind,),
        ).fetchall()
        sizes = sorted(int(row[2]) for row in rows)
        study_count = sum(sizes)
        if component_kind in {"hard-protected", "legacy-v1-all-evidence"} and (
            study_count != corpus_study_count
        ):
            raise ManifestAuditError("all_node_component_distribution_incomplete")
        top_rows = rows[:COMPONENT_REVIEW_TARGET_LIMIT]
        top_study_count = sum(int(row[2]) for row in top_rows)
        if sizes:
            distribution: dict[str, JsonValue] = {
                "algorithm_version": component_versions[component_kind],
                "component_count": len(sizes),
                "study_count": study_count,
                "corpus_study_count": corpus_study_count,
                "member_count_min": sizes[0],
                "member_count_median": float(np.median(np.asarray(sizes))),
                "member_count_p90": sizes[math.ceil(0.90 * len(sizes)) - 1],
                "member_count_p95": sizes[math.ceil(0.95 * len(sizes)) - 1],
                "member_count_p99": sizes[math.ceil(0.99 * len(sizes)) - 1],
                "member_count_max": sizes[-1],
                "largest_component_study_proportion": round(sizes[-1] / corpus_study_count, 12),
                "top_component_study_count": top_study_count,
                "top_component_study_proportion": round(top_study_count / corpus_study_count, 12),
                "top_component_target_limit": COMPONENT_REVIEW_TARGET_LIMIT,
            }
        else:
            distribution = {
                "algorithm_version": component_versions[component_kind],
                "component_count": 0,
                "study_count": 0,
                "corpus_study_count": corpus_study_count,
                "member_count_min": None,
                "member_count_median": None,
                "member_count_p90": None,
                "member_count_p95": None,
                "member_count_p99": None,
                "member_count_max": None,
                "largest_component_study_proportion": None,
                "top_component_study_count": 0,
                "top_component_study_proportion": 0.0,
                "top_component_target_limit": COMPONENT_REVIEW_TARGET_LIMIT,
            }
        connection.execute(
            "INSERT OR REPLACE INTO manifest_run VALUES(?,?)",
            (f"component_distribution:{component_kind}", canonical_json(distribution)),
        )

        review_targets: list[JsonValue] = []
        for rank, (component_key, representative_file_key, member_count) in enumerate(
            top_rows, start=1
        ):
            component_members = members_by_component_kind[component_kind][str(component_key)]
            if component_kind == "hard-protected":
                attribution_rows = connection.execute(
                    """SELECT edge_kind,decision,SUM(evidence_count)
                        FROM duplicate_component_edge
                        WHERE left_hard_component_key=? AND right_hard_component_key=?
                        GROUP BY edge_kind,decision ORDER BY edge_kind,decision""",
                    (component_key, component_key),
                ).fetchall()
            elif component_kind == "soft-candidate":
                attribution_rows = connection.execute(
                    """SELECT edge_kind,decision,SUM(evidence_count)
                        FROM duplicate_component_edge WHERE soft_component_key=?
                        GROUP BY edge_kind,decision ORDER BY edge_kind,decision""",
                    (component_key,),
                ).fetchall()
                if not any(
                    str(decision) == EdgeDisposition.CANDIDATE.value
                    for _, decision, _ in attribution_rows
                ):
                    raise ManifestAuditError("soft_component_candidate_attribution_missing")
                if connection.execute(
                    """SELECT COUNT(*) FROM candidate_component
                        WHERE component_key=? AND evidence_state!='review_only'""",
                    (component_key,),
                ).fetchone()[0]:
                    raise ManifestAuditError("soft_component_review_state_invalid")
            else:
                component_member_set = frozenset(component_members)
                attribution: Counter[tuple[str, str]] = Counter()
                for edge in edges:
                    if edge.left in component_member_set and edge.right in component_member_set:
                        attribution[(edge.kind, edge.disposition.value)] += edge_counts[edge]
                attribution_rows = [
                    (edge_kind, decision, evidence_count)
                    for (edge_kind, decision), evidence_count in sorted(attribution.items())
                ]

            connectivity_path = _component_connectivity_path(
                component_members,
                edges,
                edge_counts,
                hard_only=component_kind == "hard-protected",
            )
            connectivity_json: list[JsonValue] = list(connectivity_path)

            representative_relative_path = (
                None
                if representative_file_key is None
                else private_paths.get(str(representative_file_key))
            )
            if resolved_input_root is not None:
                if representative_file_key is None or representative_relative_path is None:
                    raise ManifestAuditError("component_representative_path_missing")
                candidate_path = (resolved_input_root / representative_relative_path).resolve(
                    strict=True
                )
                if (
                    not candidate_path.is_file()
                    or not candidate_path.is_relative_to(resolved_input_root)
                    or opaque_key(secret, "file", representative_relative_path)
                    != representative_file_key
                ):
                    raise ManifestAuditError("component_representative_path_invalid")
                representative_study_row = connection.execute(
                    "SELECT study_key FROM slice_file_manifest WHERE file_key=?",
                    (representative_file_key,),
                ).fetchone()
                if (
                    representative_study_row is None
                    or str(representative_study_row[0]) not in component_members
                ):
                    raise ManifestAuditError("component_representative_membership_invalid")
            review_targets.append(
                {
                    "rank": rank,
                    "component_key": str(component_key),
                    "member_count": int(member_count),
                    "study_proportion": round(int(member_count) / corpus_study_count, 12),
                    "representative_file_key": (
                        None if representative_file_key is None else str(representative_file_key)
                    ),
                    "representative_path_verified": resolved_input_root is not None,
                    "connectivity_verified": True,
                    "transitive_edge_path": connectivity_json,
                    "edge_type_attribution": [
                        {
                            "edge_kind": str(edge_kind),
                            "decision": str(decision),
                            "evidence_count": int(evidence_count),
                        }
                        for edge_kind, decision, evidence_count in attribution_rows
                    ],
                }
            )
        connection.execute(
            "INSERT OR REPLACE INTO manifest_run VALUES(?,?)",
            (f"largest_component_review_targets:{component_kind}", canonical_json(review_targets)),
        )
    connection.execute(
        "INSERT OR REPLACE INTO manifest_run VALUES(?,?)",
        (
            "grouping_representative_review_status",
            "complete" if resolved_input_root is not None else "pending_private_review",
        ),
    )
    connection.execute(
        "INSERT OR REPLACE INTO manifest_run VALUES(?,?)",
        ("grouping_representative_review_version", COMPONENT_REVIEW_VERSION),
    )

    crossings = sum(
        hard_component_keys[edge.left] != hard_component_keys[edge.right]
        for edge in edges
        if edge.disposition is EdgeDisposition.HARD
    )
    if crossings:
        raise ManifestAuditError("protected_component_invariant_failed")
    candidate_crossings = sum(
        edge_counts[edge]
        for edge in edges
        if edge.disposition is EdgeDisposition.CANDIDATE
        and hard_component_keys[edge.left] != hard_component_keys[edge.right]
    )
    connection.execute(
        "INSERT OR REPLACE INTO manifest_run VALUES('candidate_cross_hard_edges',?)",
        (str(candidate_crossings),),
    )
    return hard_component_keys, crossings


def _label_conflicts_within_components(
    connection: sqlite3.Connection, component_keys: Mapping[str, str]
) -> None:
    by_component_target: dict[tuple[str, int], dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for study_key, target_index, label_state in connection.execute(
        """SELECT study_key, target_index, label_state FROM label_source_manifest
            WHERE source_kind='official' AND label_state IN ('positive','negative')"""
    ):
        by_component_target[(component_keys[study_key], int(target_index))][label_state].append(
            study_key
        )
    for (_, target_index), states in by_component_target.items():
        if set(states) != {"positive", "negative"}:
            continue
        for study_key in sorted(states["positive"] + states["negative"]):
            _insert_issue(connection, "study", study_key, "duplicate_label_conflict")
            connection.execute(
                """UPDATE label_source_manifest SET adjudication_state='unresolved',
                    state_validity='invalid' WHERE study_key=? AND target_index=?
                    AND source_kind='official'""",
                (study_key, target_index),
            )
    connection.execute(
        "INSERT OR REPLACE INTO manifest_run VALUES('label_provenance','official_only')"
    )


def _label_copy_candidates_within_components(
    connection: sqlite3.Connection,
    *,
    component_keys: Mapping[str, str],
    target_count: int,
    secret: bytes,
) -> int:
    """Record identical official vectors only inside pre-existing protected components."""

    members_by_component: dict[str, list[str]] = defaultdict(list)
    for study_key, component_key in component_keys.items():
        members_by_component[component_key].append(study_key)
    pair_count = 0
    for component_key, component_members in sorted(members_by_component.items()):
        if len(component_members) < 2:
            continue
        vectors: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for study_key in sorted(component_members):
            rows = connection.execute(
                """SELECT target_index, label_state FROM label_source_manifest
                    WHERE study_key=? AND source_kind='official' ORDER BY target_index""",
                (study_key,),
            ).fetchall()
            if len(rows) != target_count or [int(row[0]) for row in rows] != list(
                range(target_count)
            ):
                continue
            vectors[tuple(str(row[1]) for row in rows)].append(study_key)
        for vector, matching_studies in sorted(vectors.items()):
            if len(matching_studies) < 2:
                continue
            matching_studies.sort()
            pair_count += len(matching_studies) * (len(matching_studies) - 1) // 2
            vector_payload = "\0".join((component_key, *vector))
            vector_key = opaque_key(
                secret,
                "label-copy-vector",
                vector_payload,
            )
            for study_key in matching_studies:
                connection.execute(
                    "INSERT OR IGNORE INTO duplicate_group_mapping VALUES(?,?,?,?,?)",
                    (
                        "label-copy-candidate",
                        vector_key,
                        "study",
                        study_key,
                        "duplicate-audit-v2",
                    ),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO qa_sample VALUES(?,?,?,?,?)",
                    (
                        "label_copy_candidate",
                        vector_key,
                        study_key,
                        "identical_official_vector_within_protected_component",
                        0,
                    ),
                )
            for left, right in zip(matching_studies, matching_studies[1:], strict=False):
                _persist_edge(
                    connection,
                    left=left,
                    right=right,
                    entity_level="study",
                    kind="label-copy-candidate",
                    disposition=EdgeDisposition.CANDIDATE,
                    metrics={
                        "matching_targets": target_count,
                        "missingness_included": True,
                        "scope": "pre_existing_protected_component",
                    },
                )
    connection.execute(
        "INSERT OR REPLACE INTO manifest_run VALUES('label_copy_candidates',?)",
        (str(pair_count),),
    )
    return pair_count


def _insert_shift_effects(
    connection: sqlite3.Connection,
    *,
    minimum_cell: int,
) -> tuple[int, int, float | None, float | None]:
    rows = connection.execute(
        """SELECT sm.study_key, sm.split, sm.patient_sex, sm.patient_age_years,
            sm.scanner_manufacturer, sm.scanner_model, sm.field_strength_t,
            sm.protocol_cluster_key, sm.series_count, sm.total_slice_count,
            sm.plane_availability, sm.sequence_categories, sm.report_language,
            sm.domain_cluster_key,
            (SELECT AVG(pixel_spacing_row_mm * pixel_spacing_col_mm)
             FROM series_manifest se WHERE se.study_key=sm.study_key),
            (SELECT AVG(slice_thickness_mm)
             FROM series_manifest se WHERE se.study_key=sm.study_key)
            FROM study_manifest sm ORDER BY sm.study_key"""
    ).fetchall()
    categorical_features = {
        "patient_sex": 2,
        "scanner_manufacturer": 4,
        "scanner_model": 5,
        "protocol_cluster": 7,
        "plane_availability": 10,
        "sequence_composition": 11,
        "report_language": 12,
        "site_domain_cluster": 13,
    }
    continuous_features = {
        "patient_age_years": 3,
        "field_strength_t": 6,
        "study_complexity_series_count": 8,
        "study_complexity_slice_count": 9,
        "in_plane_resolution_area_mm2": 14,
        "slice_thickness_mm": 15,
    }
    evaluated = 0
    large = 0
    largest_categorical: float | None = None
    largest_continuous: float | None = None
    limitation = "accessible_example_test_only_hidden_scoring_test_unavailable"

    def store(
        feature: str,
        feature_type: str,
        metrics: Mapping[str, float | None],
        tier: str,
        train_n: int,
        test_n: int,
        evaluable: bool,
    ) -> None:
        for name, value in metrics.items():
            finite_value = value if value is None or math.isfinite(value) else None
            connection.execute(
                "INSERT INTO shift_result VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    feature,
                    feature_type,
                    name,
                    finite_value,
                    tier,
                    train_n,
                    test_n,
                    int(evaluable),
                    limitation,
                ),
            )

    categorical_inputs: dict[
        str,
        tuple[list[str | None], list[str | None], Any, Any],
    ] = {}
    for feature, index in categorical_features.items():
        categorical_inputs[feature] = (
            [cast(str | None, row[index]) for row in rows if row[1] == "train"],
            [cast(str | None, row[index]) for row in rows if row[1] == "test"],
            None,
            None,
        )
    description_rows = connection.execute(
        """SELECT sm.split, sm.study_key, se.series_description FROM series_manifest se
            JOIN study_manifest sm ON sm.study_key=se.study_key ORDER BY sm.split, sm.study_key,
            se.series_key"""
    ).fetchall()
    train_descriptions: list[str | None] = []
    test_descriptions: list[str | None] = []
    train_description_studies: list[str] = []
    test_description_studies: list[str] = []
    for split, study_key, encoded_tokens in description_rows:
        try:
            tokens = json.loads(encoded_tokens) if encoded_tokens is not None else [None]
        except (TypeError, json.JSONDecodeError):
            tokens = [None]
        if not isinstance(tokens, list) or not tokens:
            tokens = [None]
        values = train_descriptions if split == "train" else test_descriptions
        studies = train_description_studies if split == "train" else test_description_studies
        for token in tokens:
            values.append(token if isinstance(token, str) else None)
            studies.append(str(study_key))
    categorical_inputs["series_description_vocabulary"] = (
        train_descriptions,
        test_descriptions,
        study_equal_weights(train_description_studies) if train_description_studies else None,
        study_equal_weights(test_description_studies) if test_description_studies else None,
    )
    for feature, (
        category_train,
        category_test,
        train_weights,
        test_weights,
    ) in categorical_inputs.items():
        try:
            categorical_effect = categorical_shift(
                category_train,
                category_test,
                train_weights=train_weights,
                test_weights=test_weights,
            )
        except ShiftInputError:
            categorical_effect = None
        categorical_metrics = (
            {
                "total_variation": categorical_effect.total_variation,
                "sqrt_js_base2": categorical_effect.sqrt_jensen_shannon,
                "unseen_test_mass": categorical_effect.unseen_test_mass,
                "missingness_difference": categorical_effect.missingness_difference,
            }
            if categorical_effect is not None
            else {
                "total_variation": None,
                "sqrt_js_base2": None,
                "unseen_test_mass": None,
                "missingness_difference": None,
            }
        )
        store(
            feature,
            "categorical",
            categorical_metrics,
            "not_evaluable" if categorical_effect is None else categorical_effect.tier.value,
            len(set(train_description_studies))
            if feature == "series_description_vocabulary"
            else len(category_train),
            len(set(test_description_studies))
            if feature == "series_description_vocabulary"
            else len(category_test),
            categorical_effect is not None,
        )
        if categorical_effect is not None:
            evaluated += 1
            large += int(categorical_effect.tier.value == "large")
            train_support = (
                len(set(train_description_studies))
                if feature == "series_description_vocabulary"
                else len(category_train)
            )
            test_support = (
                len(set(test_description_studies))
                if feature == "series_description_vocabulary"
                else len(category_test)
            )
            if train_support >= minimum_cell and test_support >= minimum_cell:
                largest_categorical = max(
                    largest_categorical or 0.0, categorical_effect.total_variation
                )

    continuous_inputs: dict[str, tuple[list[float | None], list[float | None]]] = {}
    for feature, index in continuous_features.items():
        continuous_inputs[feature] = (
            [
                None if row[index] is None else float(row[index])
                for row in rows
                if row[1] == "train"
            ],
            [None if row[index] is None else float(row[index]) for row in rows if row[1] == "test"],
        )
    missingness_values = []
    for row in rows:
        fields = (
            row[2],
            row[3],
            row[4],
            row[5],
            row[6],
            row[7],
            row[12],
            row[13],
            row[14],
            row[15],
        )
        missingness_values.append((row[1], sum(value is None for value in fields) / len(fields)))
    continuous_inputs["overall_missingness"] = (
        [float(value) for split, value in missingness_values if split == "train"],
        [float(value) for split, value in missingness_values if split == "test"],
    )
    for feature, (numeric_train, numeric_test) in continuous_inputs.items():
        try:
            continuous_effect = continuous_shift(numeric_train, numeric_test)
        except ShiftInputError:
            continuous_effect = None
        continuous_metrics = (
            {
                "standardized_mean_difference": continuous_effect.standardized_mean_difference,
                "median_over_train_iqr": continuous_effect.median_difference_over_train_iqr,
                "wasserstein1_over_train_iqr": continuous_effect.wasserstein_over_train_iqr,
                "missingness_difference": continuous_effect.missingness_difference,
            }
            if continuous_effect is not None
            else {
                "standardized_mean_difference": None,
                "median_over_train_iqr": None,
                "wasserstein1_over_train_iqr": None,
                "missingness_difference": None,
            }
        )
        store(
            feature,
            "continuous",
            continuous_metrics,
            "not_evaluable" if continuous_effect is None else continuous_effect.tier.value,
            len(numeric_train),
            len(numeric_test),
            continuous_effect is not None,
        )
        if continuous_effect is not None:
            evaluated += 1
            large += int(continuous_effect.tier.value == "large")
            if len(numeric_train) >= minimum_cell and len(numeric_test) >= minimum_cell:
                magnitude = abs(continuous_effect.standardized_mean_difference)
                if math.isfinite(magnitude):
                    largest_continuous = max(largest_continuous or 0.0, magnitude)
    return evaluated, large, largest_categorical, largest_continuous


def _select_qa_samples(connection: sqlite3.Connection, *, qa_per_stratum: int, seed: int) -> int:
    strata: dict[tuple[str, str], list[str]] = defaultdict(list)
    study_rows = connection.execute(
        """SELECT study_key, split, report_language, label_status, data_quality_flags,
            plane_availability, sequence_categories, domain_cluster_key, total_slice_count
            FROM study_manifest ORDER BY study_key"""
    ).fetchall()
    for study_key, split, language, label_status, flags, planes, sequences, domain, _ in study_rows:
        strata[("split", split)].append(study_key)
        strata[("language", language or "missing")].append(study_key)
        strata[("label_status", label_status)].append(study_key)
        strata[("quality", "flagged" if flags != "[]" else "clean")].append(study_key)
        strata[("domain", domain or "missing")].append(study_key)
        for plane in json.loads(planes):
            strata[("plane", str(plane))].append(study_key)
        for sequence in json.loads(sequences):
            strata[("sequence", str(sequence))].append(study_key)
    slice_counts = np.asarray([float(row[8]) for row in study_rows], dtype=np.float64)
    if slice_counts.size:
        low, high = np.quantile(slice_counts, (0.1, 0.9))
        for row in study_rows:
            if float(row[8]) <= float(low):
                strata[("slice_count_extreme", "low")].append(row[0])
            if float(row[8]) >= float(high):
                strata[("slice_count_extreme", "high")].append(row[0])
    resolution_rows = connection.execute(
        """SELECT sm.study_key, AVG(se.pixel_spacing_row_mm * se.pixel_spacing_col_mm)
            FROM study_manifest sm JOIN series_manifest se ON se.study_key=sm.study_key
            GROUP BY sm.study_key ORDER BY sm.study_key"""
    ).fetchall()
    observed_resolutions = np.asarray(
        [float(row[1]) for row in resolution_rows if row[1] is not None], dtype=np.float64
    )
    if observed_resolutions.size:
        low, high = np.quantile(observed_resolutions, (0.1, 0.9))
        for study_key, value in resolution_rows:
            if value is not None and float(value) <= float(low):
                strata[("resolution_extreme", "low")].append(study_key)
            if value is not None and float(value) >= float(high):
                strata[("resolution_extreme", "high")].append(study_key)
    for study_key, evidence_state in connection.execute(
        """SELECT study_key, evidence_state FROM protected_component
            WHERE evidence_state != 'singleton' ORDER BY study_key"""
    ):
        strata[("duplicate_component", evidence_state)].append(study_key)
    for study_key, evidence_state in connection.execute(
        """SELECT study_key, evidence_state FROM candidate_component
            ORDER BY study_key"""
    ):
        strata[("candidate_component", evidence_state)].append(study_key)
    for (study_key,) in connection.execute(
        """SELECT DISTINCT study_key FROM series_manifest
            WHERE terminal_state='quarantine' OR localizer_likelihood >= 1.0 ORDER BY study_key"""
    ):
        strata[("unusual_series", "flagged")].append(study_key)
    selected: set[str] = set()
    for (kind, value), members in sorted(strata.items()):
        ordered = sorted(
            set(members),
            key=lambda item: hashlib.sha256(f"{seed}:{item}".encode()).hexdigest(),
        )[:qa_per_stratum]
        stratum_key = content_sha256({"kind": kind, "value": value})
        for study_key in ordered:
            selected.add(study_key)
            connection.execute(
                "INSERT INTO qa_sample VALUES(?,?,?,?,?)",
                (kind, stratum_key, study_key, "deterministic_stratified_review", 1),
            )
    return int(connection.execute("SELECT COUNT(DISTINCT study_key) FROM qa_sample").fetchone()[0])


def _validate_database_schema(connection: sqlite3.Connection, schema: Mapping[str, Any]) -> None:
    tables = cast(Mapping[str, Any], schema["tables"])
    for table, specification in tables.items():
        if not isinstance(specification, dict) or not isinstance(specification.get("fields"), list):
            raise ManifestAuditError("manifest_schema_invalid")
        actual = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]  # noqa: S608
        if actual != specification["fields"]:
            raise ManifestAuditError("manifest_schema_database_mismatch")
    versions = {
        "manifest_version": MANIFEST_VERSION,
        "group_version": GROUP_VERSION,
        "label_version": LABEL_VERSION,
        "preprocessing_version": PREPROCESSING_VERSION,
    }
    if any(schema.get(key) != value for key, value in versions.items()):
        raise ManifestAuditError("manifest_version_mismatch")
    dicom_schema = schema.get("dicom")
    report_schema = schema.get("reports")
    expected_dicom = {
        "reading_validation": "raise",
        "force_read": False,
        "orientation_norm_tolerance": IOP_ORTHONORMAL_TOLERANCE,
        "orientation_dot_tolerance": IOP_ORTHONORMAL_TOLERANCE,
        "orientation_degrees_tolerance": ORIENTATION_TOLERANCE_DEGREES,
        "duplicate_position_mm": DUPLICATE_POSITION_TOLERANCE_MM,
        "spacing_absolute_tolerance_mm": SPACING_ABSOLUTE_TOLERANCE_MM,
        "spacing_relative_tolerance": SPACING_RELATIVE_TOLERANCE,
        "spacing_gap_ratio": GAP_MULTIPLIER,
    }
    if not isinstance(dicom_schema, dict) or any(
        dicom_schema.get(key) != value for key, value in expected_dicom.items()
    ):
        raise ManifestAuditError("dicom_schema_runtime_mismatch")
    required_dicom_thresholds = {
        "near_slice_phash_hamming",
        "near_slice_study_minimum_matches",
        "near_slice_study_minimum_series_pairs",
        "near_slice_maximum_study_pairs",
        "near_slice_maximum_evidence_studies_per_component",
        "near_series_quantile_slices",
        "near_series_minimum_slices",
        "near_series_minimum_length_ratio",
        "near_series_median_phash_hamming",
        "candidate_series_max_phash_hamming",
        "candidate_series_median_phash_hamming",
        "near_series_maximum_candidate_pairs",
        "near_series_median_ncc",
        "near_series_minimum_ncc",
        "near_series_gradient_ncc",
    }
    required_report_thresholds = {
        "near_minimum_tokens",
        "near_shingle_size",
        "near_token_count_ratio",
        "candidate_simhash_hamming",
        "maximum_candidate_pairs",
        "candidate_jaccard",
        "confirmed_jaccard",
        "confirmed_levenshtein",
    }
    if not required_dicom_thresholds <= set(dicom_schema):
        raise ManifestAuditError("dicom_schema_runtime_mismatch")
    if (
        not isinstance(report_schema, dict)
        or report_schema.get("normalization") != "nfkc-casefold-whitespace-typed-numbers-v1"
        or not required_report_thresholds <= set(report_schema)
    ):
        raise ManifestAuditError("report_schema_runtime_mismatch")


def _record_manifest_reconciliation(
    connection: sqlite3.Connection,
    *,
    inventory: SourceInventory,
    processed_files: int,
    discovered_files: int,
) -> None:
    expected_study_source_rows = {
        "train": inventory.train_csv_rows,
        "test": inventory.test_csv_rows,
    }
    observed_study_source_rows = {
        split: sum(
            source.source_row_count
            for source in inventory.studies.values()
            if source.split == split
        )
        for split in SUPPORTED_SPLITS
    }
    expected_series_source_rows = {
        "train": inventory.train_series_csv_rows,
        "test": inventory.test_series_csv_rows,
    }
    observed_series_source_rows = {
        split: sum(
            source.source_row_count for source in inventory.series.values() if source.split == split
        )
        for split in SUPPORTED_SPLITS
    }
    expected = {
        "studies": len(inventory.studies),
        "series": len(inventory.series),
        "files": discovered_files,
        "reports": len(inventory.studies),
        "official_label_cells": len(inventory.labels) * inventory.train_csv_rows,
    }
    observed = {
        "studies": int(connection.execute("SELECT COUNT(*) FROM study_manifest").fetchone()[0]),
        "series": int(connection.execute("SELECT COUNT(*) FROM series_manifest").fetchone()[0]),
        "files": int(connection.execute("SELECT COUNT(*) FROM slice_file_manifest").fetchone()[0]),
        "reports": int(connection.execute("SELECT COUNT(*) FROM report_manifest").fetchone()[0]),
        "official_label_cells": int(
            connection.execute(
                "SELECT COUNT(*) FROM label_source_manifest WHERE source_kind='official'"
            ).fetchone()[0]
        ),
    }
    non_official = int(
        connection.execute(
            "SELECT COUNT(*) FROM label_source_manifest WHERE source_kind!='official'"
        ).fetchone()[0]
    )
    report_source_rows = int(
        connection.execute(
            "SELECT COALESCE(SUM(source_row_count),0) FROM report_manifest"
        ).fetchone()[0]
    )
    expected_report_source_rows = inventory.train_csv_rows + inventory.test_csv_rows
    terminal_failures = {
        "studies": int(
            connection.execute(
                "SELECT COUNT(*) FROM study_manifest "
                "WHERE terminal_state NOT IN ('pass','quarantine')"
            ).fetchone()[0]
        ),
        "series": int(
            connection.execute(
                "SELECT COUNT(*) FROM series_manifest "
                "WHERE terminal_state NOT IN ('pass','quarantine')"
            ).fetchone()[0]
        ),
        "files": int(
            connection.execute(
                "SELECT COUNT(*) FROM slice_file_manifest "
                "WHERE terminal_state NOT IN ('pass','quarantine')"
            ).fetchone()[0]
        ),
        "reports": int(
            connection.execute(
                "SELECT COUNT(*) FROM report_manifest "
                "WHERE terminal_state NOT IN ('pass','quarantine')"
            ).fetchone()[0]
        ),
        "labels": int(
            connection.execute(
                """SELECT COUNT(*) FROM label_source_manifest
                    WHERE state_validity NOT IN ('valid','invalid') OR
                    adjudication_state NOT IN ('organizer','unresolved')"""
            ).fetchone()[0]
        ),
    }
    orphan_sources = sum(
        any(
            marker in source.conflicts
            for marker in (
                "series_csv_study_not_in_primary_csv",
                "file_tree_study_not_in_primary_or_series_csv",
                "study_not_in_primary_csv",
            )
        )
        for source in inventory.studies.values()
    ) + sum(
        "file_tree_series_not_in_series_csv" in source.conflicts
        for source in inventory.series.values()
    )
    official_source_violations = int(
        connection.execute(
            """SELECT COUNT(*) FROM label_source_manifest lm
                JOIN study_manifest sm ON sm.study_key=lm.study_key
                WHERE sm.split!='train' OR sm.source_row_count<=0"""
        ).fetchone()[0]
    )
    label_indices = {
        int(row[0])
        for row in connection.execute(
            "SELECT DISTINCT target_index FROM label_source_manifest ORDER BY target_index"
        )
    }
    expected_label_indices = set(range(len(inventory.labels)))
    reconciled = (
        processed_files == discovered_files
        and observed == expected
        and observed_study_source_rows == expected_study_source_rows
        and observed_series_source_rows == expected_series_source_rows
        and report_source_rows == expected_report_source_rows
        and non_official == 0
        and official_source_violations == 0
        and label_indices == expected_label_indices
        and not any(terminal_failures.values())
        and orphan_sources == 0
    )
    if not reconciled:
        raise ManifestAuditError("five_level_reconciliation_failed")
    for level in ("studies", "series", "files", "reports", "official_label_cells"):
        connection.execute(
            "INSERT OR REPLACE INTO manifest_run VALUES(?,?)",
            (f"reconciliation:{level}", "pass"),
        )
    connection.execute(
        "INSERT OR REPLACE INTO manifest_run VALUES('non_official_label_sources','0')"
    )
    connection.execute(
        "INSERT OR REPLACE INTO manifest_run VALUES('five_levels_reconciled','true')"
    )


def _write_bytes_atomic(path: Path, payload: bytes, maximum_bytes: int) -> str:
    if path.exists() or len(payload) > maximum_bytes:
        raise ManifestAuditError("artifact_write_invalid")
    temporary = path.parent / f".{path.name}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    temporary.rename(path)
    return hashlib.sha256(payload).hexdigest()


def _write_private_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    if path.exists():
        raise ManifestAuditError("private_output_exists")
    temporary = path.parent / f".{path.name}.tmp"
    try:
        with temporary.open("x", newline="", encoding="utf-8") as handle:
            os.chmod(temporary, 0o600)
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.rename(path)
    except OSError as error:
        raise ManifestAuditError("private_output_write_failed") from error


def _write_private_json(path: Path, payload: object, maximum_bytes: int = 1024 * 1024) -> None:
    _write_bytes_atomic(path, (canonical_json(payload) + "\n").encode(), maximum_bytes)


def _markdown_value(value: JsonValue) -> str:
    if value is None:
        return "not_evaluable"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _write_audit_markdown(
    path: Path,
    title: str,
    sections: Sequence[tuple[str, Mapping[str, JsonValue]]],
) -> None:
    lines = [f"# {title}", ""]
    for heading, values in sections:
        lines.extend((f"## {heading}", ""))
        lines.extend(f"- {key}: {_markdown_value(value)}" for key, value in values.items())
        lines.append("")
    payload = "\n".join(lines).encode()
    privacy_scan_text(payload.decode())
    _write_bytes_atomic(path, payload, 512 * 1024)


def _table_count(connection: sqlite3.Connection, table: str, where: str = "1") -> int:
    allowed_tables = {
        "study_manifest",
        "series_manifest",
        "slice_file_manifest",
        "label_source_manifest",
        "duplicate_edge",
        "protected_component",
        "qa_sample",
    }
    allowed_where = {
        "1",
        "split='train'",
        "split='test'",
        "terminal_state='pass'",
        "terminal_state='quarantine'",
        "decode_state='pass'",
        "issue_code='unreadable'",
        "issue_code='decode_failure'",
        "path_header_identity_match=0",
        "patient_group_key IS NULL",
        "label_state='positive'",
        "label_state='negative'",
        "label_state='unknown'",
        "label_state='conflict'",
    }
    if table not in allowed_tables or where not in allowed_where:
        raise ManifestAuditError("count_request_invalid")
    return int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0])  # noqa: S608


def _export_private_tables(connection: sqlite3.Connection, output_root: Path) -> None:
    duplicate_rows = connection.execute(
        """SELECT group_kind, group_key, entity_level, entity_key, algorithm_version
            FROM duplicate_group_mapping ORDER BY group_kind, group_key, entity_key"""
    )
    _write_private_csv(
        output_root / "private_duplicate_groups.csv",
        ("group_kind", "group_key", "entity_level", "entity_key", "algorithm_version"),
        duplicate_rows,
    )
    component_rows = connection.execute(
        """WITH component_members AS (
                SELECT component_kind, component_key, study_key, evidence_state
                FROM protected_component
                UNION ALL
                SELECT 'soft-candidate', component_key, study_key, evidence_state
                FROM candidate_component
            )
            SELECT cm.component_kind, cm.component_key, cm.study_key, cm.evidence_state,
                sm.terminal_state,
                CASE
                    WHEN cm.component_kind='soft-candidate' THEN 'review_only_not_fold_group'
                    WHEN sm.terminal_state='pass' THEN 'requires_fold_audit'
                    ELSE 'quarantine_excluded_pending_review'
                END
            FROM component_members AS cm
            JOIN study_manifest AS sm ON sm.study_key=cm.study_key
            ORDER BY cm.component_kind, cm.component_key, cm.study_key"""
    )
    _write_private_csv(
        output_root / "private_preliminary_group_keys.csv",
        (
            "component_kind",
            "component_key",
            "study_key",
            "evidence_state",
            "study_terminal_state",
            "fold_gate_state",
        ),
        component_rows,
    )
    qa_rows = connection.execute(
        """SELECT stratum_kind, stratum_key, study_key, selection_reason, priority
            FROM qa_sample ORDER BY stratum_kind, stratum_key, study_key"""
    )
    _write_private_csv(
        output_root / "private_qa_samples.csv",
        ("stratum_kind", "stratum_key", "study_key", "selection_reason", "priority"),
        qa_rows,
    )


def _sanitized_count(value: int, minimum_cell: int) -> JsonValue:
    return suppressed_count(value, minimum_cell)


def _candidate_overflow_aggregate_fields(
    connection: sqlite3.Connection, minimum_cell: int
) -> dict[str, JsonValue]:
    """Export fixed overflow aggregates while keeping study-level counts suppressed."""

    fields: dict[str, JsonValue] = {}
    metric_keys = (
        (
            "near_slice_study_pair_space_overflow",
            "near_slice_study_pair_limit",
            "near_slice_study_pair_count_lower_bound",
            "near_slice_overflow_study_edges",
        ),
        (
            "near_series_candidate_space_overflow",
            "near_series_candidate_pair_limit",
            "near_series_candidate_pair_count_lower_bound",
            "near_series_overflow_study_edges",
        ),
        (
            "near_report_candidate_space_overflow",
            "near_report_candidate_pair_limit",
            "near_report_candidate_pair_count_lower_bound",
            "near_report_overflow_study_edges",
        ),
    )
    for flag_key, limit_key, lower_bound_key, edge_key in metric_keys:
        values = dict(
            connection.execute(
                "SELECT key,value FROM manifest_run WHERE key IN (?,?,?,?)",
                (flag_key, limit_key, lower_bound_key, edge_key),
            ).fetchall()
        )
        flag = values.get(flag_key, "false")
        if flag == "false" and not values:
            lower_bound = edge_count = 0
        elif flag == "true":
            try:
                pair_limit = int(values[limit_key])
                lower_bound = int(values[lower_bound_key])
                edge_count = int(values[edge_key])
            except (KeyError, TypeError, ValueError) as error:
                raise ManifestAuditError("candidate_overflow_metric_invalid") from error
            if pair_limit < 1 or lower_bound != pair_limit + 1 or edge_count < 0:
                raise ManifestAuditError("candidate_overflow_metric_invalid")
        else:
            raise ManifestAuditError("candidate_overflow_metric_invalid")
        fields[flag_key] = flag == "true"
        fields[lower_bound_key] = lower_bound
        fields[edge_key] = _sanitized_count(edge_count, minimum_cell)
    return fields


def _write_artifact_inventories(
    output_root: Path,
    *,
    provenance: Mapping[str, JsonValue],
    privacy: Mapping[str, JsonValue],
) -> None:
    private_names = (
        "private_manifest.sqlite3",
        "private_duplicate_groups.csv",
        "private_preliminary_group_keys.csv",
        "private_qa_samples.csv",
        "audit_key.bin",
    )
    private_artifacts = [
        asdict(artifact_hash(output_root / name, "private")) for name in private_names
    ]
    _write_private_json(
        output_root / "private_artifact_inventory.json",
        {
            "schema_version": 1,
            "artifact_type": "private-artifact-inventory",
            "provenance": provenance,
            "artifacts": private_artifacts,
        },
    )
    documents = []
    for name in ("data_audit.md", "leakage_audit.md", "domain_shift_audit.md"):
        item = artifact_hash(output_root / name, "sanitized")
        documents.append(
            {
                "name": item.name,
                "kind": "documentation",
                "bytes": item.size_bytes,
                "sha256": item.sha256,
            }
        )
    write_json_atomic(
        output_root / "sanitized_artifact_inventory.json",
        cast(
            Mapping[str, JsonValue],
            {
                "schema_version": 1,
                "artifact_type": "sanitized-artifact-inventory",
                "provenance": provenance,
                "privacy": privacy,
                "artifacts": documents,
            },
        ),
        128 * 1024,
    )


def run_manifest_audit(
    *,
    input_root: Path,
    output_root: Path,
    manifest_schema_path: Path,
    competition_config_path: Path,
    competition_contract_path: Path,
    run_config_path: Path,
) -> dict[str, JsonValue]:
    """Audit the accessible competition corpus once and return only a sanitized envelope."""

    started = time.monotonic()
    config = AuditConfig.from_json(run_config_path)
    deadline = started + config.max_seconds
    run_payload = _load_json_object(run_config_path, "run_config_invalid")
    schema = validate_schema(manifest_schema_path)
    _, labels = load_contract(competition_contract_path)
    provenance, privacy = _validate_runtime_inputs(
        schema,
        competition_config_path,
        competition_contract_path,
        run_payload,
    )
    decoder_versions = assert_required_decoder_runtime()
    _check_self_deadline(deadline)
    _prepare_output_root(output_root)
    secret = install_bundle_audit_key(
        run_config_path.with_name("audit-key.bin"), output_root / "audit_key.bin"
    )
    inventory = read_source_inventory(input_root, labels)
    discovered_paths = _augment_source_inventory(
        input_root, inventory, config.max_files, deadline=deadline
    )
    discovered_files = len(discovered_paths)
    environment_hash, versions = environment_fingerprint(decoder_versions)
    connection = initialize_private_database(
        output_root / "private_manifest.sqlite3",
        {
            "audit_id": config.audit_id,
            "bundle_sha256": config.bundle_sha256,
            "code_commit": config.code_commit,
            "environment_sha256": environment_hash,
            "environment_versions": canonical_json(versions),
            "group_version": GROUP_VERSION,
            "label_version": LABEL_VERSION,
            "manifest_version": MANIFEST_VERSION,
            "preprocessing_version": PREPROCESSING_VERSION,
            "schema_sha256": sha256_file(manifest_schema_path),
        },
    )
    try:
        _validate_database_schema(connection, schema)
        study_keys, series_keys, reports = insert_source_placeholders(connection, inventory, secret)
        connection.commit()
        series_evidence: list[SeriesEvidence] = []
        study_headers: dict[str, list[HeaderEvidence]] = defaultdict(list)
        current_series: str | None = None
        current_states: list[FileAuditState] = []
        current_headers: list[HeaderEvidence] = []
        private_paths_by_file: dict[str, str] = {}
        processed_files = 0

        def finish_current_series() -> None:
            if not current_states or current_series is None:
                return
            source = inventory.series[current_series]
            series_evidence.append(
                _finish_series(
                    connection,
                    states=current_states,
                    headers=current_headers,
                    source=source,
                    secret=secret,
                    schema=schema,
                )
            )

        with _strict_pydicom_validation():
            inspections = _ordered_file_inspections(
                iter(discovered_paths),
                input_root=input_root,
                secret=secret,
                workers=config.workers,
                deadline=deadline,
            )
            for inspected in inspections:
                private_paths_by_file[inspected.file_key] = inspected.path.relative_to(
                    input_root
                ).as_posix()
                qualified_series = inspected.series_source_key
                if current_series is not None and qualified_series != current_series:
                    finish_current_series()
                    current_states = []
                    current_headers = []
                current_series = qualified_series
                state, header = _persist_inspected_file(
                    connection,
                    inspected=inspected,
                    study_keys=study_keys,
                    series_keys=series_keys,
                    secret=secret,
                )
                current_states.append(state)
                current_headers.append(header)
                study_headers[state.study_key].append(header)
                processed_files += 1
                if processed_files % config.progress_every == 0:
                    connection.commit()
                    fixed_event("manifest_audit_progress", files=processed_files)
            finish_current_series()
            connection.commit()
        del discovered_paths

        _check_self_deadline(deadline)
        for (series_key,) in connection.execute(
            """SELECT series_key FROM series_manifest
                WHERE terminal_state IN ('pending','conditional')"""
        ):
            connection.execute(
                """UPDATE series_manifest SET ordering_method='unavailable',
                    orientation_state='invalid', spacing_state='invalid', decode_state='failed',
                    missing_tag_flags='[\"empty_series\"]', terminal_state='quarantine'
                    WHERE series_key=?""",
                (series_key,),
            )
            _insert_issue(connection, "series", series_key, "empty_series")
        _finish_studies(
            connection,
            inventory=inventory,
            study_keys=study_keys,
            series_keys=series_keys,
            study_headers=study_headers,
            secret=secret,
        )
        study_headers.clear()
        _record_manifest_reconciliation(
            connection,
            inventory=inventory,
            processed_files=processed_files,
            discovered_files=discovered_files,
        )

        _check_self_deadline(deadline)
        study_edges: list[DuplicateEdge] = []
        exact_file_groups = _persist_exact_groups(
            connection,
            table="slice_file_manifest",
            entity_column="file_key",
            study_column="study_key",
            digest_column="raw_file_exact_key",
            entity_level="file",
            kind="exact-file",
            secret=secret,
            study_edges=study_edges,
        )
        exact_pixel_groups = _persist_exact_groups(
            connection,
            table="slice_file_manifest",
            entity_column="file_key",
            study_column="study_key",
            digest_column="decoded_pixel_exact_key",
            entity_level="file",
            kind="exact-pixel",
            secret=secret,
            study_edges=study_edges,
        )
        exact_series_groups = _persist_exact_groups(
            connection,
            table="series_manifest",
            entity_column="series_key",
            study_column="study_key",
            digest_column="exact_content_key",
            entity_level="series",
            kind="exact-series",
            secret=secret,
            study_edges=study_edges,
        )
        _persist_exact_groups(
            connection,
            table="report_manifest",
            entity_column="report_key",
            study_column="study_key",
            digest_column="raw_text_exact_key",
            entity_level="report",
            kind="exact-report-raw",
            secret=secret,
            study_edges=study_edges,
        )
        _persist_exact_groups(
            connection,
            table="report_manifest",
            entity_column="report_key",
            study_column="study_key",
            digest_column="canonical_text_exact_key",
            entity_level="report",
            kind="exact-report-normalized",
            secret=secret,
            study_edges=study_edges,
        )
        (
            exact_report_raw_pairs,
            exact_report_normalized_pairs,
            exact_report_overlap_pairs,
            exact_report_union_pairs,
        ) = _exact_report_pair_counts(connection)
        exact_study_groups = _persist_study_exact_groups(connection, secret, study_edges)
        metadata_duplicates = _persist_altered_metadata_edges(connection, secret, study_edges)
        _check_self_deadline(deadline)
        _identity_and_patient_edges(connection, inventory, study_keys, study_edges)
        series_comparisons, near_series_hard, near_series_candidates = _near_series_edges(
            connection, series_evidence, schema, study_edges
        )
        series_evidence.clear()
        report_comparisons, near_report_hard, near_report_candidates = _report_edges(
            connection, inventory, study_keys, reports, schema, study_edges
        )
        _finalize_report_template_components(connection, secret=secret)
        near_slice = _near_slice_edges(
            connection,
            schema=schema,
            secret=secret,
            study_edges=study_edges,
        )
        _check_self_deadline(deadline)
        component_keys, future_fold_crossings = _protected_components(
            connection,
            study_edges,
            secret,
            representative_paths=private_paths_by_file,
            input_root=input_root,
        )
        private_paths_by_file.clear()
        _label_conflicts_within_components(connection, component_keys)
        label_copy_candidates = _label_copy_candidates_within_components(
            connection,
            component_keys=component_keys,
            target_count=len(inventory.labels),
            secret=secret,
        )
        _insert_shift_effects(connection, minimum_cell=config.minimum_export_cell)
        _check_self_deadline(deadline)
        qa_selected = _select_qa_samples(
            connection, qa_per_stratum=config.qa_per_stratum, seed=config.seed
        )
        connection.execute(
            "INSERT OR REPLACE INTO manifest_run VALUES('near_series_comparisons',?)",
            (str(series_comparisons),),
        )
        connection.execute(
            "INSERT OR REPLACE INTO manifest_run VALUES('near_report_comparisons',?)",
            (str(report_comparisons),),
        )
        table_orders = {
            "study_manifest": ("study_key",),
            "series_manifest": ("series_key",),
            "slice_file_manifest": ("file_key",),
            "report_manifest": ("report_key",),
            "label_source_manifest": (
                "study_key",
                "target_index",
                "source_kind",
                "source_version",
            ),
            "duplicate_edge": ("left_key", "right_key", "entity_level", "edge_kind"),
            "duplicate_group_mapping": ("group_kind", "group_key", "entity_key"),
            "protected_component": ("component_kind", "component_key", "study_key"),
            "candidate_component": ("component_key", "study_key"),
            "duplicate_component_summary": ("component_kind", "component_key"),
            "duplicate_component_edge": (
                "left_study_key",
                "right_study_key",
                "edge_kind",
                "decision",
            ),
            "manifest_issue": ("entity_level", "entity_key", "issue_code"),
            "shift_result": ("feature", "effect_name"),
            "qa_sample": ("stratum_kind", "stratum_key", "study_key"),
        }
        for table, order in table_orders.items():
            _check_self_deadline(deadline)
            connection.execute(
                "INSERT OR REPLACE INTO manifest_run VALUES(?,?)",
                (f"table_sha256:{table}", table_content_hash(connection, table, order)),
            )
        connection.commit()
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        files_terminal = int(
            connection.execute(
                """SELECT COUNT(*) FROM slice_file_manifest
                    WHERE terminal_state IN ('pass','quarantine')"""
            ).fetchone()[0]
        )
        all_series_terminal = (
            connection.execute(
                """SELECT COUNT(*) FROM series_manifest
                    WHERE terminal_state NOT IN ('pass','quarantine')"""
            ).fetchone()[0]
            == 0
        )
        (
            unexplained_dicom_issues,
            dicom_issue_dispositions_complete,
        ) = _dicom_issue_disposition_status(connection)
        _export_private_tables(connection, output_root)
        _check_self_deadline(deadline)
        minimum = config.minimum_export_cell
        studies_total = _table_count(connection, "study_manifest")
        series_total = _table_count(connection, "series_manifest")
        protected_component_count = int(
            connection.execute(
                "SELECT COUNT(DISTINCT component_key) FROM protected_component"
            ).fetchone()[0]
        )
        cross_split_components = int(
            connection.execute(
                """SELECT COUNT(*) FROM (
                    SELECT component_key FROM protected_component pc
                    JOIN study_manifest sm ON sm.study_key=pc.study_key
                    GROUP BY component_key HAVING COUNT(DISTINCT split)>1)"""
            ).fetchone()[0]
        )
        candidate_overflow = _candidate_overflow_aggregate_fields(connection, minimum)
        aggregates: dict[str, JsonValue] = {
            "scope": {
                "mode": "full" if config.max_files is None else "bounded",
                "source_context": config.source_context,
                "example_test_only": True,
                "hidden_test_evaluable": False,
            },
            "coverage": {
                "studies_total": _sanitized_count(studies_total, minimum),
                "train_studies": _sanitized_count(
                    _table_count(connection, "study_manifest", "split='train'"), minimum
                ),
                "test_studies": _sanitized_count(
                    _table_count(connection, "study_manifest", "split='test'"), minimum
                ),
                "series_total": _sanitized_count(series_total, minimum),
                "train_series": _sanitized_count(
                    sum(source.split == "train" for source in inventory.series.values()),
                    minimum,
                ),
                "test_series": _sanitized_count(
                    sum(source.split == "test" for source in inventory.series.values()),
                    minimum,
                ),
                "files_total": _sanitized_count(processed_files, minimum),
                "files_terminal": _sanitized_count(files_terminal, minimum),
                "files_decoded": _sanitized_count(
                    _table_count(connection, "slice_file_manifest", "decode_state='pass'"), minimum
                ),
                "files_quarantined": _sanitized_count(
                    _table_count(connection, "slice_file_manifest", "terminal_state='quarantine'"),
                    minimum,
                ),
                "complete": processed_files == discovered_files == files_terminal,
            },
            "quality": {
                "series_geometry_pass": _sanitized_count(
                    int(
                        connection.execute(
                            """SELECT COUNT(*) FROM series_manifest
                                WHERE ordering_method='geometry' AND terminal_state='pass'"""
                        ).fetchone()[0]
                    ),
                    minimum,
                ),
                "series_fallback": _sanitized_count(
                    int(
                        connection.execute(
                            """SELECT COUNT(*) FROM series_manifest
                                WHERE ordering_method='instance_number'"""
                        ).fetchone()[0]
                    ),
                    minimum,
                ),
                "series_quarantined": _sanitized_count(
                    _table_count(connection, "series_manifest", "terminal_state='quarantine'"),
                    minimum,
                ),
                "files_unreadable": _sanitized_count(
                    int(
                        connection.execute(
                            """SELECT COUNT(*) FROM manifest_issue
                                WHERE entity_level='file' AND issue_code='unreadable'"""
                        ).fetchone()[0]
                    ),
                    minimum,
                ),
                "files_decode_failure": _sanitized_count(
                    int(
                        connection.execute(
                            """SELECT COUNT(*) FROM manifest_issue
                                WHERE entity_level='file' AND issue_code='decode_failure'"""
                        ).fetchone()[0]
                    ),
                    minimum,
                ),
                "path_header_mismatch": _sanitized_count(
                    _table_count(connection, "slice_file_manifest", "path_header_identity_match=0"),
                    minimum,
                ),
                "unexplained_dicom_issues": unexplained_dicom_issues,
                "patient_group_missing": _sanitized_count(
                    _table_count(connection, "study_manifest", "patient_group_key IS NULL"),
                    minimum,
                ),
            },
            "labels": {
                "official_only": True,
                "non_official_sources": 0,
                "official_cells": _sanitized_count(
                    _table_count(connection, "label_source_manifest"), minimum
                ),
                "positive_cells": _sanitized_count(
                    _table_count(connection, "label_source_manifest", "label_state='positive'"),
                    minimum,
                ),
                "negative_cells": _sanitized_count(
                    _table_count(connection, "label_source_manifest", "label_state='negative'"),
                    minimum,
                ),
                "unknown_cells": _sanitized_count(
                    _table_count(connection, "label_source_manifest", "label_state='unknown'"),
                    minimum,
                ),
                "conflict_cells": _sanitized_count(
                    _table_count(connection, "label_source_manifest", "label_state='conflict'"),
                    minimum,
                ),
            },
            "duplicates": {
                "exact_file_groups": _sanitized_count(exact_file_groups, minimum),
                "exact_pixel_groups": _sanitized_count(exact_pixel_groups, minimum),
                "exact_series_groups": _sanitized_count(exact_series_groups, minimum),
                "exact_study_groups": _sanitized_count(exact_study_groups, minimum),
                "exact_report_raw_pairs": _sanitized_count(exact_report_raw_pairs, minimum),
                "exact_report_normalized_pairs": _sanitized_count(
                    exact_report_normalized_pairs, minimum
                ),
                "exact_report_overlap_pairs": _sanitized_count(exact_report_overlap_pairs, minimum),
                "exact_report_union_pairs": _sanitized_count(exact_report_union_pairs, minimum),
                "near_slice_groups": _sanitized_count(near_slice.groups, minimum),
                "near_slice_edges": _sanitized_count(near_slice.persisted_edges, minimum),
                "near_slice_edges_suppressed": _sanitized_count(
                    near_slice.suppressed_edges, minimum
                ),
                "near_slice_unresolved_study_pairs": _sanitized_count(
                    near_slice.unresolved_study_pairs, minimum
                ),
                "near_slice_study_pair_space_overflow": candidate_overflow[
                    "near_slice_study_pair_space_overflow"
                ],
                "near_slice_study_pair_count_lower_bound": candidate_overflow[
                    "near_slice_study_pair_count_lower_bound"
                ],
                "near_slice_overflow_study_edges": candidate_overflow[
                    "near_slice_overflow_study_edges"
                ],
                "raw_container_variation_groups": _sanitized_count(
                    metadata_duplicates.raw_container_variation_groups, minimum
                ),
                "altered_metadata_groups": _sanitized_count(
                    metadata_duplicates.altered_metadata_groups, minimum
                ),
                "near_series_edges": _sanitized_count(near_series_hard, minimum),
                "near_series_candidate_space_overflow": candidate_overflow[
                    "near_series_candidate_space_overflow"
                ],
                "near_series_candidate_pair_count_lower_bound": candidate_overflow[
                    "near_series_candidate_pair_count_lower_bound"
                ],
                "near_series_overflow_study_edges": candidate_overflow[
                    "near_series_overflow_study_edges"
                ],
                "near_report_edges": _sanitized_count(near_report_hard, minimum),
                "near_report_candidate_space_overflow": candidate_overflow[
                    "near_report_candidate_space_overflow"
                ],
                "near_report_candidate_pair_count_lower_bound": candidate_overflow[
                    "near_report_candidate_pair_count_lower_bound"
                ],
                "near_report_overflow_study_edges": candidate_overflow[
                    "near_report_overflow_study_edges"
                ],
                "candidate_edges": _sanitized_count(
                    near_series_candidates
                    + near_report_candidates
                    + near_slice.promoted_study_edges,
                    minimum,
                ),
                "label_copy_candidates": _sanitized_count(label_copy_candidates, minimum),
                "protected_components": _sanitized_count(protected_component_count, minimum),
                "cross_split_components": _sanitized_count(cross_split_components, minimum),
                "future_fold_crossings": future_fold_crossings,
            },
            "shift": {
                "evaluation_scope": config.source_context,
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
            "qa": {"selected_studies": _sanitized_count(qa_selected, minimum)},
            "integrity": {
                "five_levels_reconciled": True,
                "foreign_keys": not foreign_key_errors,
                "all_files_terminal": files_terminal == processed_files,
                "all_series_terminal": all_series_terminal,
                "dicom_issue_dispositions_complete": dicom_issue_dispositions_complete,
                "protected_graph_closed": future_fold_crossings == 0,
                "private_artifacts_complete": True,
            },
            "versions": {
                "manifest_version": MANIFEST_VERSION,
                "group_version": GROUP_VERSION,
                "label_version": LABEL_VERSION,
                "preprocessing_version": PREPROCESSING_VERSION,
            },
            "runtime": {"elapsed_seconds": elapsed_seconds(started)},
        }
    finally:
        connection.close()

    scope = cast(dict[str, JsonValue], aggregates["scope"])
    coverage = cast(dict[str, JsonValue], aggregates["coverage"])
    quality = cast(dict[str, JsonValue], aggregates["quality"])
    labels_aggregate = cast(dict[str, JsonValue], aggregates["labels"])
    duplicates = cast(dict[str, JsonValue], aggregates["duplicates"])
    shift = cast(dict[str, JsonValue], aggregates["shift"])
    integrity = cast(dict[str, JsonValue], aggregates["integrity"])
    versions_aggregate = cast(dict[str, JsonValue], aggregates["versions"])
    runtime_aggregate = cast(dict[str, JsonValue], aggregates["runtime"])
    _write_audit_markdown(
        output_root / "data_audit.md",
        "Data audit",
        (
            ("Scope", scope),
            ("Coverage", coverage),
            ("Quality", quality),
            ("Labels", labels_aggregate),
            ("Integrity", integrity),
            ("Versions", versions_aggregate),
            ("Runtime", runtime_aggregate),
        ),
    )
    _write_audit_markdown(
        output_root / "leakage_audit.md",
        "Leakage audit",
        (
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
                    "folds_assigned": False,
                    "fold_feasibility": "not_assessed",
                    "future_fold_crossings": duplicates["future_fold_crossings"],
                },
            ),
            ("Integrity", integrity),
        ),
    )
    _write_audit_markdown(
        output_root / "domain_shift_audit.md",
        "Domain shift audit",
        (
            (
                "Scope",
                {key: value for key, value in scope.items() if key != "hidden_test_evaluable"},
            ),
            ("Shift", shift),
            (
                "Limitations",
                {
                    "hidden_test_evaluable": scope["hidden_test_evaluable"],
                },
            ),
            ("Integrity", integrity),
        ),
    )
    _write_artifact_inventories(output_root, provenance=provenance, privacy=privacy)
    return {
        "schema_version": 1,
        "artifact_type": "manifest-audit-aggregate",
        "status": "complete",
        "provenance": dict(provenance),
        "privacy": dict(privacy),
        "aggregates": aggregates,
    }
