"""Private, offline, on-demand Chunk 5 human review.

The batch version builds an authenticated metadata-only cohort and stops before ``START``.  An
authorized human may later run the same notebook interactively; only then is one selected study at
a time decoded, rendered once, reviewed, checkpointed, and removed from working storage.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import uuid
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Final, cast

COMPETITION_SLUG: Final = "rsna-knee-abnormality-detection"
PLAN_BASENAME: Final = "private_on_demand_plan.json"
COVERAGE_BASENAME: Final = "private_coverage_ledger.json"
LEDGER_BASENAME: Final = "private_review_ledger.json"
READINESS_BASENAME: Final = "sanitized_readiness.json"
SUMMARY_BASENAME: Final = "sanitized_review_summary.json"
MAX_ROOT_ENTRIES: Final = 128
MAX_PRIVATE_JSON_BYTES: Final = 64 * 1024**2
MAX_SANITIZED_BYTES: Final = 256 * 1024
REF = re.compile(r"[a-z0-9][a-z0-9_-]{0,49}/[a-z0-9][a-z0-9_-]{0,99}\Z")
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
SAFE_TOKEN = re.compile(r"[a-z0-9_]{1,80}\Z")
UID_BYTES = re.compile(rb"(?<![0-9])(?:[0-9]{1,12}\.){3,}[0-9]{1,12}(?![0-9])")
SOURCE_REQUIRED_ENTRIES: Final = frozenset(
    {
        "audit_key.bin",
        "private_artifact_inventory.json",
        "private_duplicate_groups.csv",
        "private_manifest.sqlite3",
        "private_preliminary_group_keys.csv",
        "private_qa_samples.csv",
    }
)
SOURCE_MANIFEST_FILENAME: Final = "source-artifact-manifest.json"
SOURCE_DATASET_ENTRIES: Final = SOURCE_REQUIRED_ENTRIES | {SOURCE_MANIFEST_FILENAME}
EXPECTED_SOURCE_DATASET_REF: Final = "lavicheema/rsna-knee-qa-source-artifacts-da5b9c8-r2"
# pragma: allowlist secret - published content digest identity, not a credential
EXPECTED_SOURCE_MANIFEST_SHA256: Final = (
    "b44f6895c6853320ef289aef50dfc6bd47f640d5f7ef2560a1f8f020b3d4b14b"
)
# pragma: allowlist secret - frozen r16 git commit identifier, not a credential
EXPECTED_SOURCE_R16_COMMIT: Final = "da5b9c83b874f02067ecc8f1c0a4a1d50fe01b1f"
EXPECTED_SOURCE_TOOL_VERSION: Final = "chunk5-final-remediation-v1"
EXPECTED_SOURCE_PURPOSE: Final = "chunk5-on-demand-qa-source-artifacts"
COMPETITION_FILES: Final = frozenset(
    {
        "sample_submission.csv",
        "test.csv",
        "test_series.csv",
        "train.csv",
        "train_series.csv",
    }
)
COMPETITION_DIRECTORIES: Final = frozenset({"test_series", "train_series"})
COMPETITION_ENTRIES: Final = COMPETITION_FILES | COMPETITION_DIRECTORIES


class OnDemandReviewError(RuntimeError):
    """One fixed, disclosure-safe review failure."""

    def __init__(self, code: str) -> None:
        self.code = code if SAFE_TOKEN.fullmatch(code) else "internal_error"
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class SourceDatasetIdentity:
    dataset_ref: str
    manifest_sha256: str
    code_commit: str
    bundle_sha256: str
    runner_sha256: str


@dataclass(frozen=True, slots=True)
class InputRefs:
    bundle_dataset: str
    source_dataset: str
    source_identity: SourceDatasetIdentity


@dataclass(frozen=True, slots=True)
class InputRoots:
    bundle: Path
    source: Path
    competition: Path
    source_manifest: Mapping[str, object]


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, maximum: int = MAX_PRIVATE_JSON_BYTES) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= maximum:
            raise OnDemandReviewError("private_json_invalid")
        payload = path.read_bytes()
        value = json.loads(payload)
    except OnDemandReviewError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise OnDemandReviewError("private_json_invalid") from error
    if not isinstance(value, dict) or payload != _canonical_json_bytes(value):
        raise OnDemandReviewError("private_json_invalid")
    return value


def _checkpoint(path: Path, value: Mapping[str, object], maximum: int) -> None:
    payload = _canonical_json_bytes(value)
    if not 0 < len(payload) <= maximum:
        raise OnDemandReviewError("checkpoint_size_invalid")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        try:
            os.fchmod(descriptor, 0o600)
            view = memoryview(payload)
            while view:
                view = view[os.write(descriptor, view) :]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _bounded_entries(path: Path) -> frozenset[str]:
    try:
        if path.is_symlink() or not path.is_dir():
            raise OnDemandReviewError("input_root_invalid")
        entries = []
        for index, entry in enumerate(path.iterdir()):
            if index >= MAX_ROOT_ENTRIES:
                raise OnDemandReviewError("input_root_too_large")
            entries.append(entry.name)
    except OnDemandReviewError:
        raise
    except OSError as error:
        raise OnDemandReviewError("input_root_invalid") from error
    return frozenset(entries)


def _candidate_paths(input_root: Path, ref: str, source_type: str) -> tuple[Path, ...]:
    owner, separator, slug = ref.partition("/")
    if not separator or REF.fullmatch(ref) is None or source_type not in {"datasets", "notebooks"}:
        raise OnDemandReviewError("input_identity_invalid")
    return (
        input_root / slug,
        input_root / owner / slug,
        input_root / source_type / owner / slug,
    )


def _has_symlink_ancestor(input_root: Path, candidate: Path) -> bool:
    relative = candidate.relative_to(input_root)
    current = input_root
    if input_root.is_symlink():
        return True
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            return True
    return False


def _one_root(
    input_root: Path,
    candidates: Sequence[Path],
    marker: Callable[[frozenset[str]], bool],
) -> Path:
    matches: dict[Path, Path] = {}
    for candidate in candidates:
        if _has_symlink_ancestor(input_root, candidate):
            raise OnDemandReviewError("input_symlink_rejected")
        if not candidate.is_dir():
            continue
        entries = _bounded_entries(candidate)
        if marker(entries):
            try:
                matches[candidate.resolve(strict=True)] = candidate
            except OSError as error:
                raise OnDemandReviewError("input_root_invalid") from error
    if len(matches) != 1:
        raise OnDemandReviewError("input_missing" if not matches else "input_duplicate")
    return next(iter(matches.values()))


def _canonical_source_manifest(payload: bytes) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise OnDemandReviewError("source_dataset_manifest_invalid") from error
    if not isinstance(value, dict) or payload != _canonical_json_bytes(value):
        raise OnDemandReviewError("source_dataset_manifest_invalid")
    return cast(dict[str, Any], value)


def _source_manifest_digest(value: Mapping[str, object]) -> str:
    content = {key: item for key, item in value.items() if key != "manifest_sha256"}
    payload = json.dumps(
        content,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _authenticate_source_manifest(
    source_root: Path, identity: SourceDatasetIdentity
) -> dict[str, Any]:
    manifest_path = source_root / SOURCE_MANIFEST_FILENAME
    try:
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise OnDemandReviewError("source_dataset_manifest_missing")
        size = manifest_path.stat().st_size
        if not 0 < size <= 65536:
            raise OnDemandReviewError("source_dataset_manifest_invalid")
        payload = manifest_path.read_bytes()
    except OSError as error:
        raise OnDemandReviewError("source_dataset_manifest_invalid") from error
    value = _canonical_source_manifest(payload)
    expected_keys = {
        "artifacts",
        "created_at_utc",
        "creation_tool_version",
        "dataset_purpose",
        "manifest_sha256",
        "schema_version",
        "source_producer_identity",
        "source_r16_identity",
    }
    artifacts = value.get("artifacts")
    producer = value.get("source_producer_identity")
    r16 = value.get("source_r16_identity")
    producer_keys = {
        "audit_id",
        "group_version",
        "kernel_ref",
        "kernel_status",
        "kernel_version",
        "manifest_version",
    }
    r16_keys = {"bundle_sha256", "code_commit", "runner_sha256"}
    if (
        set(value) != expected_keys
        or value.get("schema_version") != 1
        or value.get("dataset_purpose") != EXPECTED_SOURCE_PURPOSE
        or value.get("creation_tool_version") != EXPECTED_SOURCE_TOOL_VERSION
        or _source_manifest_digest(value) != cast(str, value.get("manifest_sha256"))
        or not isinstance(artifacts, list)
        or len(artifacts) != len(SOURCE_REQUIRED_ENTRIES)
        or not isinstance(producer, dict)
        or set(producer) != producer_keys
        or not isinstance(r16, dict)
        or set(r16) != r16_keys
    ):
        raise OnDemandReviewError("source_dataset_manifest_invalid")
    records: dict[str, tuple[int, str]] = {}
    for raw in artifacts:
        record = raw if isinstance(raw, dict) else {}
        name = record.get("name")
        record_size = int(record["bytes"]) if "bytes" in record else None
        digest = record.get("sha256")
        prohibited = any(
            bool(record.get(key))
            for key in (
                "contains_pixels",
                "contains_reports_text",
                "contains_patient_identifiers_raw",
                "contains_credentials",
            )
        )
        if (
            not isinstance(name, str)
            or name not in SOURCE_DATASET_ENTRIES
            or name in records
            or isinstance(record_size, bool)
            or not isinstance(record_size, int)
            or record_size <= 0
            or not isinstance(digest, str)
            or HEX_64.fullmatch(digest) is None
            or prohibited
            or record.get("privacy_class") != "private_control_artifact"
        ):
            raise OnDemandReviewError("source_dataset_privacy_rejected")
        path = source_root / name
        try:
            actual_size = path.stat().st_size if path.is_file() else -1
        except OSError:
            actual_size = -1
        if actual_size != record_size or _sha256_file(path) != digest:
            raise OnDemandReviewError("source_dataset_artifact_mismatch")
        records[name] = (record_size, digest)
    if set(records) != SOURCE_REQUIRED_ENTRIES:
        raise OnDemandReviewError("source_dataset_inventory_mismatch")
    if (
        producer["audit_id"] != "audit-0003-wheel-sanitization"
        or producer["group_version"] != "protected-groups-v2"
        or producer["manifest_version"] != "manifest-v2"
        or producer["kernel_status"] != "COMPLETE"
        or producer["kernel_version"] != 1
        or producer["kernel_ref"] != "lavicheema/rsna-knee-manifest-audit-2a1f56e-64a7ae040887"
        or r16["code_commit"] != EXPECTED_SOURCE_R16_COMMIT
        or r16["bundle_sha256"] != identity.bundle_sha256
        or r16["runner_sha256"] != identity.runner_sha256
        or identity.dataset_ref == ""
    ):
        raise OnDemandReviewError("source_dataset_lineage_rejected")
    return value


def discover_inputs(input_root: Path, refs: InputRefs) -> InputRoots:
    """Resolve only direct, owner-qualified, or type-prefixed declared mount roots."""

    if REF.fullmatch(refs.bundle_dataset) is None or REF.fullmatch(refs.source_dataset) is None:
        raise OnDemandReviewError("input_identity_invalid")
    _bounded_entries(input_root)
    bundle = _one_root(
        input_root,
        _candidate_paths(input_root, refs.bundle_dataset, "datasets"),
        lambda entries: "bundle-manifest.json" in entries,
    )
    expected_source = SOURCE_DATASET_ENTRIES
    source_owner, _, source_slug = refs.source_dataset.partition("/")
    source_candidates = (input_root / "datasets" / source_owner / source_slug,)
    source = _one_root(
        input_root,
        source_candidates,
        lambda entries: entries == expected_source,
    )
    if not source.exists():
        raise OnDemandReviewError("input_missing")
    source_manifest = _authenticate_source_manifest(source, refs.source_identity)
    competition = _one_root(
        input_root,
        (input_root / COMPETITION_SLUG, input_root / "competitions" / COMPETITION_SLUG),
        lambda entries: entries >= COMPETITION_ENTRIES,
    )
    if any(not (competition / name).is_file() for name in COMPETITION_FILES) or any(
        not (competition / name).is_dir() for name in COMPETITION_DIRECTORIES
    ):
        raise OnDemandReviewError("input_root_invalid")
    resolved = {path.resolve(strict=True) for path in (bundle, source, competition)}
    if len(resolved) != 3:
        raise OnDemandReviewError("input_duplicate")
    return InputRoots(bundle, source, competition, source_manifest)


def _load_module(name: str, path: Path) -> ModuleType:
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise OnDemandReviewError("module_load_invalid")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    except OnDemandReviewError:
        raise
    except BaseException as error:
        sys.modules.pop(name, None)
        raise OnDemandReviewError("module_load_invalid") from error
    return module


def _frozen_runtime(
    roots: InputRoots, expected_bundle_sha256: str, expected_runner_sha256: str
) -> tuple[ModuleType, dict[str, Any], dict[str, Path], tuple[Path, ...]]:
    manifest_path = roots.bundle / "bundle-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise OnDemandReviewError("bundle_manifest_invalid") from error
    if not isinstance(manifest, dict) or manifest.get("bundle_sha256") != expected_bundle_sha256:
        raise OnDemandReviewError("bundle_identity_invalid")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise OnDemandReviewError("bundle_manifest_invalid")
    runner_records = [
        item for item in files if isinstance(item, dict) and item.get("role") == "runner_source"
    ]
    if (
        len(runner_records) != 1
        or not isinstance(runner_records[0].get("path"), str)
        or Path(runner_records[0]["path"]).name != runner_records[0]["path"]
        or runner_records[0].get("sha256") != expected_runner_sha256
    ):
        raise OnDemandReviewError("bundle_manifest_invalid")
    runner_path = roots.bundle / runner_records[0]["path"]
    if _sha256_file(runner_path) != expected_runner_sha256:
        raise OnDemandReviewError("runner_source_hash_mismatch")
    runner = _load_module("chunk5_frozen_r16_runner", runner_path)
    try:
        records = runner._validated_records(roots.bundle, manifest)
        run_config, paths, dependencies = runner._verify_run_config(roots.bundle, manifest, records)
    except BaseException as error:
        code = getattr(error, "code", "bundle_authentication_failed")
        raise OnDemandReviewError(str(code)) from error
    return runner, run_config, paths, dependencies


def _positive_float(value: object) -> float | None:
    try:
        number = float(cast(Any, value))
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _orientation(value: object) -> tuple[float, float, float, float, float, float] | None:
    try:
        parsed = json.loads(str(value))
        values = tuple(float(item) for item in parsed)
    except (json.JSONDecodeError, TypeError, ValueError, OverflowError):
        return None
    if len(values) != 6 or any(not math.isfinite(item) for item in values):
        return None
    return values


def _issue_codes(value: object) -> frozenset[str]:
    try:
        parsed = json.loads(str(value))
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise OnDemandReviewError("source_manifest_schema_invalid") from error
    if not isinstance(parsed, list) or any(
        not isinstance(item, str) or SAFE_TOKEN.fullmatch(item) is None for item in parsed
    ):
        raise OnDemandReviewError("source_manifest_schema_invalid")
    return frozenset(cast(list[str], parsed))


def _laterality(runner: ModuleType, pipeline: ModuleType, competition_root: Path, row: Any) -> str:
    try:
        import pydicom

        paths = runner._series_files(competition_root, row)
        dataset = pydicom.dcmread(
            paths[0],
            stop_before_pixels=True,
            specific_tags=["ImageLaterality", "Laterality"],
            force=False,
        )
        value = pipeline._laterality(dataset)
    except BaseException as error:
        raise OnDemandReviewError("header_laterality_invalid") from error
    return {"L": "left", "R": "right", "B": "bilateral"}.get(str(value or ""), "unknown")


def _transfer_bucket(value: object) -> str:
    return {
        "uncompressed": "uncompressed_little_endian",
        "jpeg": "jpeg_lossless",
        "jpeg2000": "jpeg2000",
        "rle": "other",
        "other": "other",
    }.get(str(value or ""), "missing")


def _metadata_features(
    runner: ModuleType,
    slots: ModuleType,
    row: Any,
    raw: Sequence[object],
    quality: Any,
    laterality: str,
    terminal_state: str,
) -> dict[str, tuple[str, ...]]:
    rows, columns = _positive_float(raw[2]), _positive_float(raw[3])
    thickness = runner._bucket_number(raw[6], (1.5, 3.0, 5.0), ("le_1_5", "le_3", "le_5"))
    spacing = runner._bucket_number(raw[7], (1.5, 3.0, 5.0), ("le_1_5", "le_3", "le_5"))
    orientation = _orientation(raw[9])
    orientation_bucket = runner._orientation_bucket(orientation)
    physical_plane = runner._physical_plane_value(orientation, slots)
    bits = raw[13]
    bit_bucket = (
        "missing"
        if isinstance(bits, bool) or not isinstance(bits, int) or bits < 1
        else "le_8"
        if bits <= 8
        else "le_12"
        if bits <= 12
        else "le_16"
        if bits <= 16
        else "other"
    )
    photometric = str(raw[12] or "").strip().casefold() or "missing"
    transfer = _transfer_bucket(raw[11])
    resolution = (
        "missing"
        if rows is None or columns is None
        else "le_256"
        if max(rows, columns) <= 256
        else "le_512"
        if max(rows, columns) <= 512
        else "gt_512"
    )
    issues = _issue_codes(raw[14])
    plane_relation = (
        "organizer_missing"
        if row.plane == "missing"
        else "agreement"
        if physical_plane == row.plane
        else "physical_unknown"
        if physical_plane == "unknown"
        else "conflict"
    )
    quality_band = "blocked" if terminal_state != "model_eligible" else "high"
    edge_cases = {
        *(
            (f"orientation_{orientation_bucket}",)
            if not orientation_bucket.startswith("orthogonal_")
            else ()
        ),
        *((f"photometric_{photometric}",) if photometric != "monochrome2" else ()),
        *((f"transfer_{transfer}",) if transfer != "uncompressed_little_endian" else ()),
        *((f"bit_depth_{bit_bucket}",) if bit_bucket in {"missing", "other"} else ()),
        *(f"quality_{reason.value}" for reason in quality.blocked_reasons),
        *(f"manifest_{issue}" for issue in issues),
    } or {"none"}
    slice_count = runner._slice_count_bucket(quality.total_slices)
    sequence = (
        "fluid_sensitive"
        if row.fluid_sensitive == "present"
        else "structural"
        if row.fluid_sensitive == "absent"
        else "missing"
    )
    return {
        "plane": (row.plane,),
        "sequence": (sequence,),
        "fat_suppression": (row.fat_suppression,),
        "slice_count": (slice_count,),
        "bit_depth": (bit_bucket,),
        "photometric": (photometric,),
        "transfer_syntax": (transfer,),
        "resolution": (resolution,),
        "slice_thickness": (thickness,),
        "slice_spacing": (spacing,),
        "orientation": (orientation_bucket,),
        "quality": (quality_band,),
        "duplicate_integrity": (("present",) if quality.duplicate_slices else ()),
        "laterality": (laterality,),
        "organizer_plane": (row.plane,),
        "physical_plane": (physical_plane,),
        "organizer_physical_plane_relation": (plane_relation,),
        "bit_depth_category": (bit_bucket,),
        "photometric_interpretation": (photometric,),
        "slice_thickness_stratum": (thickness,),
        "slice_spacing_stratum": (spacing,),
        "resolution_extreme": (resolution,),
        "slice_count_extreme": (slice_count,),
        "dicom_edge_case_subtype": tuple(sorted(edge_cases)),
        "terminal_state": (terminal_state,),
    }


def _manifest_quality(slots: ModuleType, raw: Sequence[object]) -> Any:
    total = raw[8]
    if isinstance(total, bool) or not isinstance(total, int) or not 1 <= total <= 1024:
        raise OnDemandReviewError("source_manifest_schema_invalid")
    issues = _issue_codes(raw[14])
    decoded = total if raw[17] == "pass" else 0
    spacing = _positive_float(raw[7])
    row_spacing, column_spacing = _positive_float(raw[4]), _positive_float(raw[5])
    return slots.SeriesQuality(
        total_slices=total,
        decoded_slices=decoded,
        decode_failure_count=total - decoded,
        duplicate_slices=1 if decoded and any("duplicate" in item for item in issues) else 0,
        geometry_valid=raw[15] == "valid" and raw[18] == "pass",
        spacing_regular=raw[16] == "valid",
        median_slice_spacing_mm=spacing,
        spacing_coefficient_of_variation=0.0 if raw[16] == "valid" and spacing else None,
        pixel_spacing_mm=(row_spacing, column_spacing)
        if row_spacing is not None and column_spacing is not None
        else None,
        physical_coverage_mm=_positive_float(raw[10]),
    )


def _series_manifest_rows(reconciliation: Any) -> dict[str, tuple[object, ...]]:
    try:
        rows = reconciliation.connection.execute(
            """SELECT series_key,study_key,rows,columns,pixel_spacing_row_mm,
                pixel_spacing_col_mm,slice_thickness_mm,spacing_between_slices_mm,slice_count,
                orientation_vectors,physical_coverage_mm,transfer_syntax_class,
                photometric_interpretation,bits_stored,missing_tag_flags,orientation_state,
                spacing_state,decode_state,terminal_state
                FROM series_manifest ORDER BY series_key"""
        ).fetchall()
    except sqlite3.Error as error:
        raise OnDemandReviewError("source_manifest_schema_invalid") from error
    result = {str(row[0]): tuple(row) for row in rows}
    if len(result) != reconciliation.expected_series_count or len(result) != len(rows):
        raise OnDemandReviewError("source_manifest_population_mismatch")
    return result


def _review_context(
    review_ui: ModuleType,
    state: Mapping[str, Any],
    states: Sequence[Mapping[str, Any]],
    missing_mask: Sequence[bool],
    source_facts: Mapping[str, tuple[str, ...]],
) -> dict[str, object]:
    sibling_series = [
        {
            "series_ordinal": index,
            "slot": item["record"]["slot"],
            "terminal_state": item["record"]["terminal_state"],
            "model_eligible": item["record"]["model_eligible"],
            "retention_reasons": item["record"]["retention_reasons"],
            "quality_blocked_reasons": item["record"]["quality"]["blocked_reasons"],
        }
        for index, item in enumerate(states)
    ]
    reasons = {
        *(("missing_diagnostic_slot",) if any(missing_mask) else ()),
        *(
            ("additional_or_duplicate_series",)
            if any(item["slot"] == "additional_or_duplicate" for item in sibling_series)
            else ()
        ),
        *(
            ("non_model_eligible_sibling",)
            if any(item["model_eligible"] is False for item in sibling_series)
            else ()
        ),
        *(
            ("retention_reason",)
            if any(bool(item["retention_reasons"]) for item in sibling_series)
            else ()
        ),
        *(
            ("quality_block_reason",)
            if any(bool(item["quality_blocked_reasons"]) for item in sibling_series)
            else ()
        ),
        *(
            ("source_manifest_quality_flag",)
            if source_facts.get("source_manifest_quality_flag", ("none",)) != ("none",)
            else ()
        ),
        *(
            ("dicom_edge_case",)
            if any(
                item["selection_features"].get("dicom_edge_case_subtype", ("none",)) != ("none",)
                for item in states
            )
            else ()
        ),
        *(
            ("retained_nonduplicate_abnormal_series",)
            if any(
                item["record"]["slot"] == "additional_or_duplicate"
                and any(
                    reason != "duplicate_slot" for reason in item["record"]["retention_reasons"]
                )
                for item in states
            )
            else ()
        ),
        *(
            ("duplicate_handling",)
            if any("duplicate_slot" in item["record"]["retention_reasons"] for item in states)
            or source_facts.get("protected_duplicate_group") == ("present",)
            or source_facts.get("candidate_duplicate_group") == ("present",)
            else ()
        ),
    }
    ordered_reasons = [item for item in review_ui.CHECK_9_REASON_ORDER if item in reasons]
    return {
        "organizer_plane": state["row"].plane,
        "physical_plane": state["physical_plane"],
        "laterality": state["laterality"],
        "laterality_transform": "none",
        "horizontal_flip_applied": False,
        "assigned_slot": state["record"]["slot"],
        "retention_reasons": state["record"]["retention_reasons"],
        "missing_series_mask": list(missing_mask),
        "sibling_series": sibling_series,
        "check_9_applicable": bool(ordered_reasons),
        "check_9_reason_codes": ordered_reasons,
    }


def _private_plan(
    *,
    runner: ModuleType,
    review_ui: ModuleType,
    slots: ModuleType,
    qa_strata: ModuleType,
    pipeline: ModuleType,
    competition_root: Path,
    run_config: Mapping[str, Any],
    source_root: Path,
    notebook_source_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any], Any]:
    rows = runner._read_series_rows(competition_root / "train_series.csv")
    source_config = run_config["input_identity"]["source_manifest"]
    binding = runner._discover_source_manifest_binding(source_root, source_config)
    source_facts, source_identity, reconciliation = runner._load_source_manifest_facts(
        binding, rows
    )
    raw_rows = _series_manifest_rows(reconciliation)
    grouped: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        grouped[row.study_uid].append(row)
    states_by_study: dict[str, list[dict[str, Any]]] = {}
    cohort_studies = []
    try:
        for study_uid in sorted(grouped):
            states: list[dict[str, Any]] = []
            expected_study_key = runner._source_manifest_study_key(reconciliation.secret, study_uid)
            for row in sorted(grouped[study_uid], key=lambda item: item.series_uid):
                series_key = runner._source_manifest_series_key(
                    reconciliation.secret, row.series_uid
                )
                raw = raw_rows.get(series_key)
                if raw is None or raw[1] != expected_study_key:
                    raise OnDemandReviewError("source_manifest_population_mismatch")
                quality = _manifest_quality(slots, raw)
                orientation = _orientation(raw[9])
                laterality = _laterality(runner, pipeline, competition_root, row)
                terminal = "model_eligible" if not quality.blocked else "quality_blocked"
                candidate = slots.SeriesCandidate(
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
                states.append(
                    {
                        "row": row,
                        "candidate": candidate,
                        "quality": quality,
                        "laterality": laterality,
                        "physical_plane": runner._physical_plane_value(orientation, slots),
                        "selection_features": _metadata_features(
                            runner, slots, row, raw, quality, laterality, terminal
                        ),
                        "record": {
                            "series_uid": row.series_uid,
                            "slot": None,
                            "original_slot": None,
                            "retention_reasons": [],
                            "terminal_state": terminal,
                            "model_eligible": terminal == "model_eligible",
                            "quality": {
                                "blocked_reasons": [
                                    reason.value for reason in quality.blocked_reasons
                                ],
                                "components": asdict(quality.components),
                            },
                        },
                    }
                )
            assignment = slots.assign_series_slots(tuple(item["candidate"] for item in states))
            assigned = runner._slot_assignment_by_series(assignment)
            for state in states:
                slot, original_slot, reasons = assigned[state["row"].series_uid]
                state["record"]["slot"] = slot
                state["record"]["original_slot"] = original_slot
                state["record"]["retention_reasons"] = list(reasons)
            cohort_studies.append(
                runner._cohort_study(
                    study_uid,
                    states,
                    assignment.missing_mask,
                    source_facts[study_uid],
                )
            )
            states_by_study[study_uid] = states
        selection = runner._select_after_full_pass(
            cohort_studies,
            source_manifest_available=True,
            target=100,
            minimum_eligible=100,
        )
        if selection.cohort_sha256 is None or selection.coverage is None:
            raise OnDemandReviewError("cohort_selection_invalid")
        selector_path = Path(cast(str, qa_strata.__file__)).resolve(strict=True)
        selector_sha256 = _sha256_file(selector_path)
        identity_base = {
            "bundle_sha256": run_config["bundle_sha256"],
            "preprocessing_version": run_config["provenance"]["preprocessing_version"],
            "cohort_hash": selection.cohort_sha256,
            "selector_version": qa_strata.QA_COHORT_SELECTOR_VERSION,
            "selector_sha256": selector_sha256,
            "registry_version": qa_strata.QA_STRATUM_REGISTRY_VERSION,
            "registry_sha256": qa_strata.registry_sha256(),
            "notebook_source_sha256": notebook_source_sha256,
            "source_manifest_artifact_sha256": source_identity["source_manifest_artifact_sha256"],
            "official_input_snapshot_sha256": source_identity["official_input_snapshot_sha256"],
        }
        review_bundle_id = hashlib.sha256(_canonical_json_bytes(identity_base)).hexdigest()
        identity = {"review_bundle_id": review_bundle_id, **identity_base}
        selected_uids = {item.study_uid for item in selection.studies}
        by_uid = {item.study_uid: item for item in cohort_studies}
        coverage = cast(dict[str, Any], selection.coverage)
        coverage_rows = coverage.get("rows")
        if not isinstance(coverage_rows, list):
            raise OnDemandReviewError("cohort_coverage_invalid")
        representatives = []
        for row in coverage_rows:
            if not isinstance(row, dict):
                raise OnDemandReviewError("cohort_coverage_invalid")
            dimension, value = row.get("dimension"), row.get("value")
            represented_by = sorted(
                study_uid
                for study_uid in selected_uids
                if value in dict(by_uid[study_uid].dimensions).get(cast(str, dimension), ())
            )
            if len(represented_by) != row.get("selected") or len(represented_by) < cast(
                int, row.get("required_quota", 0)
            ):
                raise OnDemandReviewError("cohort_coverage_invalid")
            representatives.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "selected_representative_study_uids": represented_by,
                }
            )
        private_coverage = {
            "schema_version": 1,
            "artifact_type": "private-on-demand-coverage-ledger",
            "identity": identity,
            "coverage": coverage,
            "representatives": representatives,
        }
        studies = []
        global_review_index = 0
        for study_index, selected in enumerate(selection.studies):
            states = states_by_study[selected.study_uid]
            missing_mask = slots.assign_series_slots(
                tuple(item["candidate"] for item in states)
            ).missing_mask
            all_series = []
            eligible_series = []
            for series_ordinal, state in enumerate(states):
                record = state["record"]
                all_series.append(
                    {
                        "series_ordinal": series_ordinal,
                        "series_uid": state["row"].series_uid,
                        "plane": state["row"].plane,
                        "fluid_sensitive": state["row"].fluid_sensitive,
                        "fat_suppression": state["row"].fat_suppression,
                        "slot": record["slot"],
                        "original_slot": record["original_slot"],
                        "retention_reasons": record["retention_reasons"],
                        "terminal_state": record["terminal_state"],
                        "model_eligible": record["model_eligible"],
                    }
                )
                if record["model_eligible"] is True:
                    eligible_series.append(
                        {
                            "review_index": global_review_index,
                            "series_ordinal": series_ordinal,
                            "series_uid": state["row"].series_uid,
                            "review_context": _review_context(
                                review_ui,
                                state,
                                states,
                                missing_mask,
                                source_facts[selected.study_uid],
                            ),
                        }
                    )
                    global_review_index += 1
            if not eligible_series:
                raise OnDemandReviewError("cohort_selection_invalid")
            studies.append(
                {
                    "review_study_index": study_index,
                    "study_uid": selected.study_uid,
                    "all_series": all_series,
                    "eligible_series": eligible_series,
                }
            )
        plan = {
            "schema_version": 1,
            "artifact_type": "private-dicom-qa-on-demand-plan",
            "status": "pending_private_human_review",
            "identity": identity,
            "total_studies": len(studies),
            "total_eligible_series": global_review_index,
            "studies": studies,
        }
        if len(studies) < 100 or global_review_index < 100:
            raise OnDemandReviewError("cohort_selection_invalid")
        return plan, private_coverage, reconciliation
    except BaseException:
        reconciliation.connection.close()
        raise


def _scan_sanitized(payload: bytes) -> None:
    lowered = payload.lower()
    forbidden = (
        b"study_uid",
        b"series_uid",
        b"studyinstanceuid",
        b"seriesinstanceuid",
        b"sopinstanceuid",
        b"/kaggle/",
        b".dcm",
        b"comment",
    )
    if UID_BYTES.search(payload) or any(token in lowered for token in forbidden):
        raise OnDemandReviewError("sanitized_output_invalid")


def _write_sanitized(path: Path, value: Mapping[str, object]) -> None:
    payload = _canonical_json_bytes(value)
    _scan_sanitized(payload)
    _checkpoint(path, value, MAX_SANITIZED_BYTES)


def _readiness(plan: Mapping[str, Any]) -> dict[str, object]:
    identity = plan["identity"]
    return {
        "schema_version": 1,
        "artifact_type": "dicom-qa-on-demand-readiness",
        "status": "human_review_ready",
        "review_bundle_id": identity["review_bundle_id"],
        "preprocessing_version": identity["preprocessing_version"],
        "cohort_hash": identity["cohort_hash"],
        "selector_version": identity["selector_version"],
        "selector_sha256": identity["selector_sha256"],
        "registry_version": identity["registry_version"],
        "registry_sha256": identity["registry_sha256"],
        "notebook_source_sha256": identity["notebook_source_sha256"],
        "total_studies": plan["total_studies"],
        "total_eligible_series": plan["total_eligible_series"],
        "minimum_studies": 100,
        "minimum_is_not_maximum": True,
        "represented_value_quota": 2,
        "singletons_mandatory": True,
        "all_represented_registry_values_covered": True,
        "human_review_status": "not_started",
        "submission_approved": False,
        "clinical_use": "prohibited",
    }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _pre_start_input(prompt: str) -> str | None:
    try:
        return input(prompt).strip()
    except EOFError:
        return None
    except Exception as error:
        if type(error).__name__ == "StdinNotImplementedError":
            return None
        raise


def _new_ledger(plan: Mapping[str, Any], plan_sha256: str) -> dict[str, Any]:
    session_id = uuid.uuid4().hex
    return {
        "schema_version": 1,
        "artifact_type": "private-dicom-qa-on-demand-review-ledger",
        "status": "in_progress",
        "identity": plan["identity"],
        "plan_sha256": plan_sha256,
        "reviewer_session_id": session_id,
        "started_at_utc": _utc_now(),
        "completed_at_utc": None,
        "last_completed_review_index": -1,
        "series": [
            {
                "schema_version": 1,
                "review_index": item["review_index"],
                "review_study_index": study["review_study_index"],
                "series_ordinal": item["series_ordinal"],
                "study_uid": study["study_uid"],
                "series_uid": item["series_uid"],
                "bundle_identity": plan["identity"]["review_bundle_id"],
                "cohort_hash": plan["identity"]["cohort_hash"],
                "preprocessing_version": plan["identity"]["preprocessing_version"],
                "study_completion_state": "pending",
                "completion_state": "pending",
                "decisions": {check: "not_reviewed" for check in _review_checks()},
                "reviewed_at_utc": None,
                "reviewer_session_id": session_id,
            }
            for study in plan["studies"]
            for item in study["eligible_series"]
        ],
        "studies": [
            {
                "review_study_index": study["review_study_index"],
                "study_uid": study["study_uid"],
                "series_total": len(study["eligible_series"]),
                "series_complete": 0,
                "completion_state": "pending",
                "completed_at_utc": None,
            }
            for study in plan["studies"]
        ],
        "human_attestation": None,
    }


_ACTIVE_REVIEW_UI: ModuleType | None = None


def _review_checks() -> tuple[str, ...]:
    if _ACTIVE_REVIEW_UI is None:
        return (
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
    return cast(tuple[str, ...], _ACTIVE_REVIEW_UI.REVIEW_CHECKS)


def _validate_resume(ledger: Mapping[str, Any], plan: Mapping[str, Any], plan_sha256: str) -> None:
    expected = _new_ledger(plan, plan_sha256)
    expected.pop("reviewer_session_id")
    expected.pop("started_at_utc")
    expected.pop("series")
    expected.pop("studies")
    session_id = ledger.get("reviewer_session_id")
    series = ledger.get("series")
    studies = ledger.get("studies")
    if (
        set(ledger)
        != {
            "schema_version",
            "artifact_type",
            "status",
            "identity",
            "plan_sha256",
            "reviewer_session_id",
            "started_at_utc",
            "completed_at_utc",
            "last_completed_review_index",
            "series",
            "studies",
            "human_attestation",
        }
        or ledger.get("schema_version") != 1
        or ledger.get("artifact_type") != expected["artifact_type"]
        or ledger.get("identity") != plan["identity"]
        or ledger.get("plan_sha256") != plan_sha256
        or ledger.get("status") not in {"in_progress", "complete"}
        or not isinstance(session_id, str)
        or re.fullmatch(r"[0-9a-f]{32}", session_id) is None
        or not isinstance(series, list)
        or not isinstance(studies, list)
        or len(series) != plan["total_eligible_series"]
        or len(studies) != plan["total_studies"]
    ):
        raise OnDemandReviewError("resume_invalid")
    started = _utc(ledger.get("started_at_utc"))
    now = datetime.now(UTC)
    if started is None or started > now:
        raise OnDemandReviewError("resume_invalid")
    expected_series = [
        (
            item["review_index"],
            study["review_study_index"],
            item["series_ordinal"],
            study["study_uid"],
            item["series_uid"],
        )
        for study in plan["studies"]
        for item in study["eligible_series"]
    ]
    completed = 0
    last_time = started
    for record, identity in zip(series, expected_series, strict=True):
        if not isinstance(record, dict):
            raise OnDemandReviewError("resume_invalid")
        observed = (
            record.get("review_index"),
            record.get("review_study_index"),
            record.get("series_ordinal"),
            record.get("study_uid"),
            record.get("series_uid"),
        )
        decisions = record.get("decisions")
        state = record.get("completion_state")
        timestamp = _utc(record.get("reviewed_at_utc"))
        if (
            set(record)
            != {
                "review_index",
                "schema_version",
                "review_study_index",
                "series_ordinal",
                "study_uid",
                "series_uid",
                "bundle_identity",
                "cohort_hash",
                "preprocessing_version",
                "study_completion_state",
                "completion_state",
                "decisions",
                "reviewed_at_utc",
                "reviewer_session_id",
            }
            or observed != identity
            or record.get("schema_version") != 1
            or record.get("bundle_identity") != plan["identity"]["review_bundle_id"]
            or record.get("cohort_hash") != plan["identity"]["cohort_hash"]
            or record.get("preprocessing_version") != plan["identity"]["preprocessing_version"]
            or record.get("study_completion_state") not in {"pending", "in_progress", "complete"}
            or record.get("reviewer_session_id") != session_id
            or not isinstance(decisions, dict)
            or set(decisions) != set(_review_checks())
            or state not in {"pending", "complete"}
            or (
                state == "pending"
                and (timestamp is not None or set(decisions.values()) != {"not_reviewed"})
            )
            or (
                state == "complete"
                and (
                    timestamp is None
                    or not last_time <= timestamp <= now
                    or any(
                        value not in {"PASS", "BLOCK", "NOT_APPLICABLE"}
                        for value in decisions.values()
                    )
                    or any(
                        value == "NOT_APPLICABLE"
                        and (
                            check != "duplicate_missing_abnormal_handling"
                            or next(
                                item["review_context"]["check_9_applicable"]
                                for study in plan["studies"]
                                for item in study["eligible_series"]
                                if item["review_index"] == record["review_index"]
                            )
                        )
                        for check, value in decisions.items()
                    )
                )
            )
        ):
            raise OnDemandReviewError("resume_invalid")
        if state == "complete":
            if record["review_index"] != completed:
                raise OnDemandReviewError("resume_invalid")
            completed += 1
            last_time = cast(datetime, timestamp)
    if ledger.get("last_completed_review_index") != completed - 1:
        raise OnDemandReviewError("resume_invalid")
    for study_record, plan_study in zip(studies, plan["studies"], strict=True):
        matching = [
            item
            for item in series
            if item["review_study_index"] == plan_study["review_study_index"]
        ]
        count = sum(item["completion_state"] == "complete" for item in matching)
        complete = count == len(matching)
        timestamp = _utc(study_record.get("completed_at_utc"))
        expected_series_study_states = {
            "complete"
            if complete
            else "in_progress"
            if item["completion_state"] == "complete"
            else "pending"
            for item in matching
        }
        if (
            set(study_record)
            != {
                "review_study_index",
                "study_uid",
                "series_total",
                "series_complete",
                "completion_state",
                "completed_at_utc",
            }
            or study_record.get("review_study_index") != plan_study["review_study_index"]
            or study_record.get("study_uid") != plan_study["study_uid"]
            or study_record.get("series_total") != len(matching)
            or study_record.get("series_complete") != count
            or study_record.get("completion_state") != ("complete" if complete else "pending")
            or (complete and (timestamp is None or not started <= timestamp <= now))
            or (not complete and timestamp is not None)
            or {item["study_completion_state"] for item in matching} != expected_series_study_states
        ):
            raise OnDemandReviewError("resume_invalid")
    is_complete = ledger.get("status") == "complete"
    completed_at = _utc(ledger.get("completed_at_utc"))
    attestation = ledger.get("human_attestation")
    if (
        (is_complete and completed != len(series))
        or (
            is_complete
            and (
                completed_at is None
                or completed_at <= started
                or not last_time <= completed_at <= now
            )
        )
        or (not is_complete and (completed_at is not None or attestation is not None))
        or (
            is_complete
            and (
                not isinstance(attestation, dict)
                or attestation.get("statement")
                != cast(ModuleType, _ACTIVE_REVIEW_UI).HUMAN_ATTESTATION_STATEMENT
                or attestation.get("authorized_human_reviewer") is not True
                or attestation.get("direct_visual_review") is not True
                or attestation.get("no_llm_or_browser_automation_pixel_access") is not True
                or _utc(attestation.get("attested_at_utc")) != completed_at
            )
        )
    ):
        raise OnDemandReviewError("resume_invalid")


def _decision_vector(review_ui: ModuleType, context: Mapping[str, object]) -> dict[str, str]:
    applicable = context.get("check_9_applicable") is True
    while True:
        vector = input("Nine decisions (P=PASS, B=BLOCK, N=NOT_APPLICABLE): ").strip().upper()
        if (
            len(vector) == len(review_ui.REVIEW_CHECKS)
            and set(vector) <= set(review_ui.DECISION_CODES)
            and all(
                code != "N" or (check in review_ui.NOT_APPLICABLE_CHECKS and not applicable)
                for check, code in zip(review_ui.REVIEW_CHECKS, vector, strict=True)
            )
        ):
            return {
                check: review_ui.DECISION_CODES[code]
                for check, code in zip(review_ui.REVIEW_CHECKS, vector, strict=True)
            }
        print("INVALID_DECISION_VECTOR")


def _actual_study_states(
    *,
    runner: ModuleType,
    slots: ModuleType,
    pipeline: ModuleType,
    competition_root: Path,
    plan_study: Mapping[str, Any],
    reconciliation: Any,
) -> list[dict[str, Any]]:
    planned_by_uid = {item["series_uid"]: item for item in plan_study["all_series"]}
    requested = []
    for eligible in plan_study["eligible_series"]:
        planned = planned_by_uid.get(eligible["series_uid"])
        if (
            planned is None
            or planned["series_ordinal"] != eligible["series_ordinal"]
            or planned["model_eligible"] is not True
        ):
            raise OnDemandReviewError("selected_study_source_changed")
        requested.append(planned)
    if len(requested) != len({item["series_uid"] for item in requested}):
        raise OnDemandReviewError("selected_study_source_changed")
    states = []
    for planned in requested:
        row = runner.SeriesRow(
            study_uid=plan_study["study_uid"],
            series_uid=planned["series_uid"],
            fluid_sensitive=planned["fluid_sensitive"],
            fat_suppression=planned["fat_suppression"],
            plane=planned["plane"],
        )
        paths = runner._series_files(competition_root, row)
        result = runner._decode_order_pass(paths, pipeline, deadline_at=None)
        runner._reconcile_source_manifest_series_files(
            reconciliation,
            competition_root=competition_root,
            row=row,
            paths=paths,
            raw_checksums=result.file_raw_checksums,
            deadline_at=None,
        )
        ordered = result.ordered
        quality = runner._quality(
            total=len(paths), decoded=len(result.decoded), ordered=ordered, slots_module=slots
        )
        orientation = (
            ordered.slices[0].metadata.image_orientation
            if ordered is not None
            else result.decoded[0].metadata.image_orientation
            if result.decoded
            else None
        )
        candidate = slots.SeriesCandidate(
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
        terminal = (
            "model_eligible"
            if not result.decode_failures
            and result.order_failure is None
            and ordered is not None
            and ordered.model_eligible
            and not quality.blocked
            else "quality_blocked"
        )
        states.append(
            {
                "row": row,
                "paths": paths,
                "pass": result,
                "ordered": ordered,
                "quality": quality,
                "candidate": candidate,
                "terminal_state": terminal,
                "series_ordinal": planned["series_ordinal"],
            }
        )
    assignment = slots.assign_series_slots(tuple(item["candidate"] for item in states))
    assigned = runner._slot_assignment_by_series(assignment)
    for state, planned in zip(states, requested, strict=True):
        slot, original_slot, reasons = assigned[state["row"].series_uid]
        observed = {
            "slot": slot,
            "original_slot": original_slot,
            "retention_reasons": list(reasons),
            "terminal_state": state["terminal_state"],
            "model_eligible": state["terminal_state"] == "model_eligible",
        }
        if any(observed[key] != planned[key] for key in observed):
            raise OnDemandReviewError("selected_study_source_changed")
    return states


def _render_one(
    *,
    runner: ModuleType,
    review_ui: ModuleType,
    slots: ModuleType,
    pipeline: ModuleType,
    qa: ModuleType,
    config: Any,
    versions: Any,
    plan_study: Mapping[str, Any],
    planned_series: Mapping[str, Any],
    state: Mapping[str, Any],
    output_dir: Path,
) -> list[Path]:
    import numpy as np

    ordered = state["ordered"]
    if ordered is None:
        raise OnDemandReviewError("selected_study_source_changed")
    try:
        pipeline.preprocess_series(ordered, config, versions)
        qa_result = pipeline.preprocess_series(
            ordered, replace(config, sample_count=None), versions
        )
    except BaseException as error:
        raise OnDemandReviewError("selected_series_preprocessing_failed") from error
    metadata = runner._qa_metadata(
        case_ordinal=plan_study["review_study_index"],
        series_ordinal=planned_series["series_ordinal"],
        row=state["row"],
        ordered=ordered,
        qa_result=qa_result,
        qa_module=qa,
        slots_module=slots,
    )
    source = np.stack([item.pixels for item in ordered.slices], axis=0)
    count = min(qa.CONTACT_MAX_SLICES, len(ordered.slices))
    contact = tuple(
        sorted(
            set(
                pipeline.deterministic_slice_indices(ordered.geometry.projected_positions_mm, count)
            )
        )
    )
    rendered = qa.render_private_qa(
        source,
        qa_result.tensor[:, 0, :, :],
        metadata=metadata,
        output_dir=output_dir,
        contact_slice_indices=contact,
    )
    paths = []
    for artifact in rendered.artifacts:
        path = output_dir / artifact.basename
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != artifact.bytes
            or _sha256_file(path) != artifact.sha256
        ):
            raise OnDemandReviewError("rendered_artifact_invalid")
        paths.append(path)
    if not paths:
        raise OnDemandReviewError("rendered_artifact_invalid")
    review_ui._show(planned_series["review_context"], paths)
    return paths


def _blocking_token(count: int) -> str:
    if count == 0:
        return "zero"
    if count <= 4:
        return "one_to_four"
    if count <= 19:
        return "five_to_nineteen"
    return "twenty_or_more"


def _sanitized_summary(ledger: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, object]:
    decisions = [value for row in ledger["series"] for value in row["decisions"].values()]
    blocking = sum(value == "BLOCK" for value in decisions)
    return {
        "schema_version": 1,
        "artifact_type": "dicom-qa-on-demand-human-review-aggregate",
        "status": "pass" if blocking == 0 else "blocked",
        "review_bundle_id": plan["identity"]["review_bundle_id"],
        "preprocessing_version": plan["identity"]["preprocessing_version"],
        "cohort_hash": plan["identity"]["cohort_hash"],
        "registry_version": plan["identity"]["registry_version"],
        "total_studies_reviewed": plan["total_studies"],
        "total_series_reviewed": plan["total_eligible_series"],
        "all_selected_studies_complete": True,
        "all_selected_series_complete": True,
        "all_nine_checks_complete": True,
        "blocking_decisions": _blocking_token(blocking),
        "human_attestation_valid": True,
        "submission_approved": False,
        "clinical_use": "prohibited",
    }


def _interactive_review(
    *,
    runner: ModuleType,
    review_ui: ModuleType,
    slots: ModuleType,
    pipeline: ModuleType,
    qa: ModuleType,
    competition_root: Path,
    working_root: Path,
    run_config: Mapping[str, Any],
    paths: Mapping[str, Path],
    plan: Mapping[str, Any],
    reconciliation: Any,
) -> Path:
    plan_path = working_root / PLAN_BASENAME
    plan_sha256 = _sha256_file(plan_path)
    ledger_path = working_root / LEDGER_BASENAME
    if ledger_path.exists():
        ledger = _read_json(ledger_path)
        _validate_resume(ledger, plan, plan_sha256)
        if ledger["status"] == "complete":
            _write_sanitized(working_root / SUMMARY_BASENAME, _sanitized_summary(ledger, plan))
            print("PRIVATE_REVIEW_ALREADY_COMPLETE")
            return ledger_path
    else:
        ledger = _new_ledger(plan, plan_sha256)
        _checkpoint(ledger_path, ledger, MAX_PRIVATE_JSON_BYTES)
    print(
        "DECISIONS=PASS requires positive evidence; BLOCK covers defects, missing evidence, "
        "ambiguity, or doubt."
    )
    print("NOT_APPLICABLE=Only check 9, and only when its displayed context is clean.")
    for index, (check, guidance) in enumerate(review_ui.REVIEW_GUIDANCE, start=1):
        print(f"CHECK_{index}={check}: {guidance}")
    config = runner._preprocessing_config(paths["preprocessing_config"], pipeline)
    versions = pipeline.PipelineVersions(
        code_commit=run_config["code_commit"],
        source_manifest_version=runner.SOURCE_MANIFEST_VERSION,
    )
    by_review_index = {row["review_index"]: row for row in ledger["series"]}
    for plan_study, study_record in zip(plan["studies"], ledger["studies"], strict=True):
        if study_record["completion_state"] == "complete":
            continue
        try:
            if (
                input(
                    f"Type NEXT to process review study {plan_study['review_study_index'] + 1}/"
                    f"{plan['total_studies']}: "
                ).strip()
                != "NEXT"
            ):
                print("REVIEW_PAUSED")
                return ledger_path
        except EOFError:
            print("REVIEW_PAUSED")
            return ledger_path
        states = _actual_study_states(
            runner=runner,
            slots=slots,
            pipeline=pipeline,
            competition_root=competition_root,
            plan_study=plan_study,
            reconciliation=reconciliation,
        )
        by_series_ordinal = {state["series_ordinal"]: state for state in states}
        study_temp = Path(
            tempfile.mkdtemp(
                prefix=f".review-study-{plan_study['review_study_index']:06d}-",
                dir=working_root,
            )
        )
        try:
            for planned_series in plan_study["eligible_series"]:
                ledger_row = by_review_index[planned_series["review_index"]]
                if ledger_row["completion_state"] == "complete":
                    continue
                series_temp = study_temp / f"series-{planned_series['series_ordinal']:03d}"
                series_temp.mkdir()
                try:
                    _render_one(
                        runner=runner,
                        review_ui=review_ui,
                        slots=slots,
                        pipeline=pipeline,
                        qa=qa,
                        config=config,
                        versions=versions,
                        plan_study=plan_study,
                        planned_series=planned_series,
                        state=by_series_ordinal[planned_series["series_ordinal"]],
                        output_dir=series_temp,
                    )
                    decisions = _decision_vector(review_ui, planned_series["review_context"])
                    ledger_row["completion_state"] = "complete"
                    ledger_row["decisions"] = decisions
                    ledger_row["reviewed_at_utc"] = _utc_now()
                    ledger["last_completed_review_index"] = planned_series["review_index"]
                    study_record["series_complete"] += 1
                    ledger_row["study_completion_state"] = "in_progress"
                    if study_record["series_complete"] == study_record["series_total"]:
                        study_record["completion_state"] = "complete"
                        study_record["completed_at_utc"] = _utc_now()
                        for row in ledger["series"]:
                            if row["review_study_index"] == plan_study["review_study_index"]:
                                row["study_completion_state"] = "complete"
                    _checkpoint(ledger_path, ledger, MAX_PRIVATE_JSON_BYTES)
                finally:
                    shutil.rmtree(series_temp, ignore_errors=True)
        finally:
            shutil.rmtree(study_temp, ignore_errors=True)
    if any(row["completion_state"] != "complete" for row in ledger["series"]):
        raise OnDemandReviewError("review_incomplete")
    try:
        statement = input(
            f"Type exactly this attestation:\n{review_ui.HUMAN_ATTESTATION_STATEMENT}\n"
        ).strip()
    except EOFError:
        print("HUMAN_ATTESTATION_REQUIRED")
        return ledger_path
    if statement != review_ui.HUMAN_ATTESTATION_STATEMENT:
        print("HUMAN_ATTESTATION_REQUIRED")
        return ledger_path
    completed_at = _utc_now()
    ledger["status"] = "complete"
    ledger["completed_at_utc"] = completed_at
    ledger["human_attestation"] = {
        "statement": review_ui.HUMAN_ATTESTATION_STATEMENT,
        "authorized_human_reviewer": True,
        "direct_visual_review": True,
        "no_llm_or_browser_automation_pixel_access": True,
        "attested_at_utc": completed_at,
    }
    _validate_resume(ledger, plan, plan_sha256)
    _checkpoint(ledger_path, ledger, MAX_PRIVATE_JSON_BYTES)
    _write_sanitized(working_root / SUMMARY_BASENAME, _sanitized_summary(ledger, plan))
    print("PRIVATE_REVIEW_COMPLETE")
    return ledger_path


def run_on_demand_review(
    *,
    bundle_dataset_ref: str,
    source_dataset_ref: str,
    expected_bundle_sha256: str,
    expected_runner_sha256: str,
    notebook_source_sha256: str,
    input_root: Path = Path("/kaggle/input"),
    working_root: Path = Path("/kaggle/working"),
) -> int:
    """Build readiness in batch and enter the private review only after exact ``START``."""

    global _ACTIVE_REVIEW_UI

    if (
        HEX_64.fullmatch(expected_bundle_sha256) is None
        or HEX_64.fullmatch(expected_runner_sha256) is None
        or HEX_64.fullmatch(notebook_source_sha256) is None
    ):
        print("ON_DEMAND_REVIEW_FAILED=input_identity_invalid")
        return 2
    runtime_root: Path | None = None
    reconciliation: Any | None = None
    try:
        refs = InputRefs(
            bundle_dataset_ref,
            source_dataset_ref,
            SourceDatasetIdentity(
                dataset_ref=source_dataset_ref,
                manifest_sha256=EXPECTED_SOURCE_MANIFEST_SHA256,
                code_commit=EXPECTED_SOURCE_R16_COMMIT,
                bundle_sha256=expected_bundle_sha256,
                runner_sha256=expected_runner_sha256,
            ),
        )
        roots = discover_inputs(input_root, refs)
        runner, run_config, paths, dependencies = _frozen_runtime(
            roots, expected_bundle_sha256, expected_runner_sha256
        )
        source_config = run_config["input_identity"]["source_manifest"]
        producer_ref = roots.source_manifest["source_producer_identity"]
        source_r16 = roots.source_manifest["source_r16_identity"]
        if (
            source_config["kernel_ref"] != cast(Mapping[str, Any], producer_ref)["kernel_ref"]
            or cast(Mapping[str, Any], source_r16)["code_commit"] != run_config["code_commit"]
            or run_config["bundle_sha256"] != expected_bundle_sha256
        ):
            raise OnDemandReviewError("input_identity_invalid")
        runtime_root = runner._install_offline_runtime(
            roots.bundle, paths["project_wheel"], dependencies
        )
        sys.path.insert(0, str(runtime_root))
        from rsna_knee.data import qa_strata  # type: ignore[import-untyped]
        from rsna_knee.data import series_slots as slots
        from rsna_knee.dicom import pipeline  # type: ignore[import-untyped]
        from rsna_knee.qa import preprocessing as qa  # type: ignore[import-untyped]

        review_ui = _load_module("chunk5_frozen_r16_review_ui", paths["review_ui_source"])
        _ACTIVE_REVIEW_UI = review_ui
        with runner._silence_process_output():
            plan, coverage, reconciliation = _private_plan(
                runner=runner,
                review_ui=review_ui,
                slots=slots,
                qa_strata=qa_strata,
                pipeline=pipeline,
                competition_root=roots.competition,
                run_config=run_config,
                source_root=roots.source,
                notebook_source_sha256=notebook_source_sha256,
            )
        _checkpoint(working_root / PLAN_BASENAME, plan, MAX_PRIVATE_JSON_BYTES)
        _checkpoint(working_root / COVERAGE_BASENAME, coverage, MAX_PRIVATE_JSON_BYTES)
        _write_sanitized(working_root / READINESS_BASENAME, _readiness(plan))
        identity = plan["identity"]
        print(f"REVIEW_BUNDLE_ID={identity['review_bundle_id']}")
        print(f"PREPROCESSING_VERSION={identity['preprocessing_version']}")
        print(f"COHORT_HASH={identity['cohort_hash']}")
        print(f"REGISTRY_VERSION={identity['registry_version']}")
        print(f"TOTAL_STUDIES={plan['total_studies']}")
        print(f"TOTAL_ELIGIBLE_SERIES={plan['total_eligible_series']}")
        print(
            "HUMAN_ONLY_BOUNDARY=Before typing START, stop all LLM/browser automation, "
            "screenshots, accessibility inspection, screen sharing, and recording."
        )
        start = _pre_start_input("Type START to begin the private review: ")
        if start is None:
            print("INTERACTIVE_REVIEW_REQUIRED")
            return 0
        if start != "START":
            print("INTERACTIVE_REVIEW_REQUIRED")
            return 0
        runner._decoder_preflight()
        _interactive_review(
            runner=runner,
            review_ui=review_ui,
            slots=slots,
            pipeline=pipeline,
            qa=qa,
            competition_root=roots.competition,
            working_root=working_root,
            run_config=run_config,
            paths=paths,
            plan=plan,
            reconciliation=reconciliation,
        )
        return 0
    except OnDemandReviewError as error:
        print(f"ON_DEMAND_REVIEW_FAILED={error.code}")
        return 2
    except BaseException as error:
        code = getattr(error, "code", "internal_error")
        fixed = str(code) if SAFE_TOKEN.fullmatch(str(code)) else "internal_error"
        print(f"ON_DEMAND_REVIEW_FAILED={fixed}")
        return 2
    finally:
        if reconciliation is not None:
            reconciliation.connection.close()
        _ACTIVE_REVIEW_UI = None
        if runtime_root is not None:
            runtime_text = str(runtime_root)
            if runtime_text in sys.path:
                sys.path.remove(runtime_text)
            shutil.rmtree(runtime_root, ignore_errors=True)
