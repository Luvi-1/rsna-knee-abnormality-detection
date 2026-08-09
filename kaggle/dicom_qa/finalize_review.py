"""Private, immutable finalizer for the Chunk 5 human DICOM review.

Run only in a private, offline Kaggle kernel with the original QA output and immutable bundle
mounted. Detailed rows, identifiers, artifact hashes, and completion evidence remain private; only
the fixed aggregate review and performance reports may be retrieved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any, Final, cast

OUTPUT_DIRECTORY: Final = "dicom-qa-review-output"
TEMPLATE_OUTPUT_DIRECTORY: Final = "dicom-qa-review-template-output"
SANITIZED_SUMMARY: Final = "human_review_summary.json"
SANITIZED_PERFORMANCE: Final = "final_performance_report.json"
PRIVATE_COMPLETION: Final = "private_human_review_completion.json"
MINIMUM_REVIEWED_STUDIES: Final = 100
MAX_REVIEWED_STUDIES: Final = 240
MAX_INPUT_BYTES: Final = 64 * 1024**2
MAX_LEDGER_BYTES: Final = 32 * 1024**2
MAX_SUMMARY_BYTES: Final = 128 * 1024
MAX_PERFORMANCE_BYTES: Final = 256 * 1024
MAX_PRIVATE_ARTIFACT_FILES: Final = 20_000
MAX_PRIVATE_ARTIFACT_BYTES: Final = 8 * 1024**3
REVIEW_PLAN_BASENAME: Final = "private_review_plan.json"
REVIEW_LEDGER_BASENAME: Final = "completed_review_ledger.json"
REVIEW_PROTOCOL_VERSION: Final = "private-dicom-qa-human-review-v1"
QA_COHORT_SELECTION_VERSION: Final = "qa-cohort-selection-v2"
HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
K20_RANGE = re.compile(r"range_([0-9]+)_([0-9]+)\Z")
SAFE_ARTIFACT = re.compile(
    r"case_[0-9]{6}_series_[0-9]{3}_"
    r"(?:contact|orthogonal|histogram|animation|before_after|review|metadata)"
    r"\.(?:png|gif|json)\Z"
)
REQUIRED_SUFFIXES: Final = frozenset(
    {
        "contact.png",
        "histogram.png",
        "animation.gif",
        "before_after.png",
        "review.json",
        "metadata.json",
    }
)
ALLOWED_SUFFIXES: Final = REQUIRED_SUFFIXES | {"orthogonal.png"}
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
REVIEW_STATUSES: Final = frozenset({"PASS", "BLOCK", "NOT_APPLICABLE"})
NOT_APPLICABLE_CHECKS: Final = frozenset({"duplicate_missing_abnormal_handling"})
TERMINAL_STATES: Final = frozenset(
    {
        "model_eligible",
        "source_access_blocked",
        "decode_blocked",
        "ordering_blocked",
        "quality_blocked",
        "preprocessing_blocked",
    }
)
PRIMARY_SERIES_SLOTS: Final = (
    "sagittal_fluid_sensitive",
    "sagittal_structural",
    "coronal_fluid_sensitive",
    "coronal_structural",
    "axial_fluid_sensitive",
    "axial_structural",
)
SERIES_SLOTS: Final = frozenset((*PRIMARY_SERIES_SLOTS, "additional_or_duplicate"))
ORGANIZER_PLANES: Final = frozenset({"sagittal", "coronal", "axial", "missing"})
PHYSICAL_PLANES: Final = frozenset({"sagittal", "coronal", "axial", "oblique", "unknown"})
RETENTION_REASON_ORDER: Final = (
    "unknown_plane",
    "conflicting_plane_metadata",
    "unknown_fluid_state",
    "blocked_quality",
    "duplicate_slot",
)
QUALITY_BLOCK_REASON_ORDER: Final = (
    "no_decodable_slices",
    "decode_failure",
    "invalid_geometry",
    "missing_pixel_spacing",
    "missing_slice_spacing",
    "irregular_slice_spacing",
    "duplicate_slices",
    "missing_physical_coverage",
)
DETERMINISM_PASS: Final = {
    "schema_version": 1,
    "artifact_type": "dicom-run-determinism-aggregate",
    "status": "pass",
    "independent_runs_compared": True,
    "exact_manifest_byte_equality": True,
    "deterministic_metrics_equal": True,
    "case_index_deterministic_projection_equal": True,
    "qa_artifact_inventory_equal": True,
    "unresolved_mismatches": "zero",
    "private_case_details_downloaded": False,
}


class ReviewFinalizationError(RuntimeError):
    """A fixed failure code that never contains private input values."""

    def __init__(self, code: str) -> None:
        self.code = code if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code) else "internal_error"
        super().__init__(self.code)


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


def _count_token(count: int, *, public_cap: int | None = None) -> str:
    if isinstance(count, bool) or count < 0 or (public_cap is not None and count > public_cap):
        raise ReviewFinalizationError("count_disclosure_invalid")
    if count == 0:
        return "zero"
    if count < 20:
        return "below_threshold_nonzero"
    if public_cap is not None and count >= public_cap - 20:
        return "at_or_above_threshold"
    lower = count // 20 * 20
    return f"range_{lower}_{lower + 19}"


def _k20_range_bounds(value: object) -> tuple[int, int] | None:
    if not isinstance(value, str) or (match := K20_RANGE.fullmatch(value)) is None:
        return None
    lower, upper = (int(item) for item in match.groups())
    return (lower, upper) if lower % 20 == 0 and upper == lower + 19 else None


def _reviewed_study_bounds(value: object) -> tuple[int, int] | None:
    if value == "at_or_above_threshold":
        return MAX_REVIEWED_STUDIES - 20, MAX_REVIEWED_STUDIES
    bounds = _k20_range_bounds(value)
    return bounds if bounds is not None and bounds[1] <= MAX_REVIEWED_STUDIES else None


def _count_token_bounds(value: object) -> tuple[int, int] | None:
    if value == "zero":
        return 0, 0
    if value == "below_threshold_nonzero":
        return 1, 19
    return _k20_range_bounds(value)


def _read_bounded(path: Path, maximum: int, code: str) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise ReviewFinalizationError(code)
        size = path.stat().st_size
        if size <= 0 or size > maximum:
            raise ReviewFinalizationError(code)
        payload = path.read_bytes()
    except ReviewFinalizationError:
        raise
    except OSError as error:
        raise ReviewFinalizationError(code) from error
    if len(payload) != size:
        raise ReviewFinalizationError(code)
    return payload


def _verify_private_artifacts(root: Path, inventory: Mapping[str, Any]) -> None:
    artifacts = inventory.get("artifacts")
    if not isinstance(artifacts, list):
        raise ReviewFinalizationError("private_inventory_invalid")
    expected: dict[str, tuple[int, str]] = {}
    for item in artifacts:
        if not isinstance(item, dict):
            raise ReviewFinalizationError("private_inventory_invalid")
        name = item.get("name")
        size = item.get("bytes")
        digest = item.get("sha256")
        if (
            not isinstance(name, str)
            or SAFE_ARTIFACT.fullmatch(name) is None
            or name in expected
            or isinstance(size, bool)
            or not isinstance(size, int)
            or not 0 < size <= 32 * 1024**2
            or not isinstance(digest, str)
            or HEX_64.fullmatch(digest) is None
        ):
            raise ReviewFinalizationError("private_inventory_invalid")
        expected[name] = (size, digest)
    if (
        not expected
        or len(expected) > MAX_PRIVATE_ARTIFACT_FILES
        or sum(size for size, _digest in expected.values()) > MAX_PRIVATE_ARTIFACT_BYTES
    ):
        raise ReviewFinalizationError("private_inventory_invalid")
    try:
        if root.is_symlink() or not root.is_dir():
            raise ReviewFinalizationError("private_artifact_root_invalid")
        entries = list(root.iterdir())
    except ReviewFinalizationError:
        raise
    except OSError as error:
        raise ReviewFinalizationError("private_artifact_root_invalid") from error
    if len(entries) != len(expected) or {path.name for path in entries} != set(expected):
        raise ReviewFinalizationError("private_artifact_set_invalid")
    for path in entries:
        size, expected_digest = expected[path.name]
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size != size:
                raise ReviewFinalizationError("private_artifact_invalid")
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
        except ReviewFinalizationError:
            raise
        except OSError as error:
            raise ReviewFinalizationError("private_artifact_invalid") from error
        if digest.hexdigest() != expected_digest:
            raise ReviewFinalizationError("private_artifact_hash_mismatch")


def _json_object(payload: bytes, code: str, *, canonical: bool = True) -> dict[str, Any]:
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
        raise ReviewFinalizationError(code) from error
    if not isinstance(value, dict) or (canonical and payload != _canonical_json_bytes(value)):
        raise ReviewFinalizationError(code)
    return value


def _derived_refs(run_config: Mapping[str, Any]) -> dict[str, str]:
    deployment = run_config.get("deployment")
    owner = deployment.get("owner") if isinstance(deployment, dict) else None
    commit = run_config.get("code_commit")
    bundle = run_config.get("bundle_sha256")
    if (
        not isinstance(owner, str)
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}", owner) is None
        or not isinstance(commit, str)
        or HEX_40.fullmatch(commit) is None
        or not isinstance(bundle, str)
        or HEX_64.fullmatch(bundle) is None
    ):
        raise ReviewFinalizationError("review_identity_invalid")
    prefixes = {
        "run_a": "rsna-knee-dqa-a",
        "run_b": "rsna-knee-dqa-b",
        "comparison": "rsna-knee-dqa-cmp",
        "review_plan": "rsna-knee-dqa-plan",
        "review_ui_template": "rsna-knee-dqa-ui",
        "review_session": "rsna-knee-dqa-review",
        "review_finalizer": "rsna-knee-dqa-final",
    }
    return {
        role: f"{owner}/{prefix}-{commit[:7]}-{bundle[:12]}" for role, prefix in prefixes.items()
    }


def _public_review_identity(
    run_config: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the trusted static identity used by private review and remote validation."""

    provenance = run_config.get("provenance")
    input_identity = run_config.get("input_identity")
    policy = run_config.get("review_policy")
    kernel = manifest.get("kernel")
    comparison = manifest.get("comparison")
    finalizer = manifest.get("review_finalizer")
    review_ui = manifest.get("review_ui")
    output_validator = manifest.get("output_validator")
    if (
        not isinstance(provenance, dict)
        or not isinstance(input_identity, dict)
        or not isinstance(policy, dict)
        or not isinstance(kernel, dict)
        or not isinstance(comparison, dict)
        or not isinstance(finalizer, dict)
        or not isinstance(review_ui, dict)
        or not isinstance(output_validator, dict)
        or set(kernel) != {"code_file", "sha256"}
        or kernel.get("code_file") != "run.py"
        or set(comparison) != {"code_file", "sha256"}
        or comparison.get("code_file") != "compare_runs.py"
        or set(finalizer) != {"code_file", "sha256"}
        or finalizer.get("code_file") != "finalize_review.py"
        or set(review_ui) != {"code_file", "sha256", "module_file", "module_sha256"}
        or review_ui.get("code_file") != "review_ui.ipynb"
        or review_ui.get("module_file") != "review_ui.py"
        or set(output_validator) != {"code_file", "sha256"}
        or output_validator.get("code_file") != "validate_output.py"
        or policy
        != {
            "protocol_version": REVIEW_PROTOCOL_VERSION,
            "cohort_selection_version": QA_COHORT_SELECTION_VERSION,
            "kernel_version": 1,
            "checks": list(REVIEW_CHECKS),
            "statuses": ["PASS", "BLOCK", "NOT_APPLICABLE"],
            "artifact_presence_separate": True,
            "minimum_reviewed_studies": MINIMUM_REVIEWED_STUDIES,
        }
    ):
        raise ReviewFinalizationError("review_identity_invalid")
    official = input_identity.get("official_competition")
    source_manifest = input_identity.get("source_manifest")
    if (
        not isinstance(official, dict)
        or set(official) != {"slug", "contract_sha256", "snapshot_identity_source"}
        or official.get("snapshot_identity_source") != "chunk4_private_manifest"
        or official.get("slug") != "rsna-knee-abnormality-detection"
        or not isinstance(official.get("contract_sha256"), str)
        or HEX_64.fullmatch(str(official["contract_sha256"])) is None
        or not isinstance(source_manifest, dict)
        or set(source_manifest)
        != {
            "version",
            "audit_id",
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
        or source_manifest.get("version") != "manifest-v2"
        or source_manifest.get("audit_id") != "audit-0002-manifest-remediation"
        or source_manifest.get("kernel_version") != 1
        or source_manifest.get("bundle_dataset_version") != 1
        or source_manifest.get("kernel_code_file") != "run.py"
        or source_manifest.get("artifact_inventory_filename") != "private_artifact_inventory.json"
        or source_manifest.get("database_filename") != "private_manifest.sqlite3"
        or source_manifest.get("audit_key_filename") != "audit_key.bin"
        or any(
            not isinstance(source_manifest.get(key), str)
            or re.fullmatch(
                r"[a-z0-9][a-z0-9_-]{0,49}/[a-z0-9][a-z0-9_-]{0,99}",
                str(source_manifest[key]),
            )
            is None
            for key in ("kernel_ref", "bundle_dataset_ref")
        )
        or any(
            not isinstance(source_manifest.get(key), str)
            or HEX_64.fullmatch(str(source_manifest[key])) is None
            for key in (
                "kernel_code_sha256",
                "bundle_sha256",
                "schema_sha256",
            )
        )
        or not isinstance(source_manifest.get("bundle_dataset_files"), list)
        or not source_manifest["bundle_dataset_files"]
        or not isinstance(source_manifest.get("private_output_policy"), list)
        or not source_manifest["private_output_policy"]
        or not isinstance(provenance.get("preprocessing_version"), str)
        or not isinstance(provenance.get("preprocessing_config_sha256"), str)
        or HEX_64.fullmatch(str(provenance["preprocessing_config_sha256"])) is None
    ):
        raise ReviewFinalizationError("review_identity_invalid")
    hashes = {
        "runner_sha256": kernel.get("sha256"),
        "comparison_sha256": comparison.get("sha256"),
        "review_finalizer_sha256": finalizer.get("sha256"),
        "review_ui_sha256": review_ui.get("module_sha256"),
        "review_notebook_sha256": review_ui.get("sha256"),
        "output_validator_sha256": output_validator.get("sha256"),
    }
    if any(
        not isinstance(value, str)
        or HEX_64.fullmatch(value) is None
        or provenance.get(key) != value
        for key, value in hashes.items()
    ):
        raise ReviewFinalizationError("review_identity_invalid")
    refs = _derived_refs(run_config)
    return {
        "schema_version": 1,
        "git_commit": run_config.get("code_commit"),
        "project_bundle_sha256": run_config.get("bundle_sha256"),
        "official_competition": dict(official),
        "source_manifest": {
            key: source_manifest[key]
            for key in (
                "version",
                "audit_id",
                "kernel_ref",
                "kernel_version",
                "kernel_code_file",
                "kernel_code_sha256",
                "bundle_dataset_ref",
                "bundle_dataset_version",
                "bundle_sha256",
                "schema_sha256",
            )
        },
        "preprocessing": {
            "version": provenance.get("preprocessing_version"),
            "config_sha256": provenance.get("preprocessing_config_sha256"),
        },
        "cohort_selection_version": QA_COHORT_SELECTION_VERSION,
        "kernels": {role: {"ref": ref, "version": 1} for role, ref in refs.items()},
        "code": hashes,
    }


def _binding(
    run_config_payload: bytes,
    manifest_payload: bytes,
    case_payload: bytes,
    inventory_payload: bytes,
    *,
    finalizer_sha256: str,
    bundle_root: Path,
    run_config_path: Path,
    runner_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], ModuleType]:
    run_config = _json_object(run_config_payload, "run_config_invalid")
    manifest = _json_object(manifest_payload, "bundle_manifest_invalid")
    case_index = _json_object(case_payload, "private_case_index_invalid")
    inventory = _json_object(inventory_payload, "private_inventory_invalid")
    provenance = run_config.get("provenance")
    manifest_provenance = manifest.get("provenance")
    kernel = manifest.get("kernel")
    finalizer = manifest.get("review_finalizer")
    commit = run_config.get("code_commit")
    bundle = run_config.get("bundle_sha256")
    if (
        not isinstance(commit, str)
        or HEX_40.fullmatch(commit) is None
        or not isinstance(bundle, str)
        or HEX_64.fullmatch(bundle) is None
        or not isinstance(provenance, dict)
        or not isinstance(manifest_provenance, dict)
        or manifest.get("bundle_sha256") != bundle
        or manifest_provenance.get("git_commit") != commit
        or not isinstance(kernel, dict)
        or kernel.get("code_file") != "run.py"
        or not isinstance(kernel.get("sha256"), str)
        or HEX_64.fullmatch(str(kernel["sha256"])) is None
        or not isinstance(finalizer, dict)
        or finalizer.get("code_file") != "finalize_review.py"
        or finalizer.get("sha256") != finalizer_sha256
        or provenance.get("git_commit") != commit
        or provenance.get("runner_sha256") != kernel.get("sha256")
        or provenance.get("review_finalizer_sha256") != finalizer_sha256
    ):
        raise ReviewFinalizationError("bundle_binding_invalid")
    runner_payload = _read_bounded(runner_path, 1024 * 1024, "runner_binding_invalid")
    if _sha256_bytes(runner_payload) != kernel.get("sha256"):
        raise ReviewFinalizationError("runner_binding_invalid")
    runner = ModuleType("_verified_private_dicom_qa_runner")
    runner.__file__ = str(runner_path)
    sys.modules[runner.__name__] = runner
    try:
        exec(compile(runner_payload, str(runner_path), "exec"), runner.__dict__)
        records = runner._validated_records(bundle_root, manifest)
        verified_config, paths, _dependencies = runner._verify_run_config(
            bundle_root, manifest, records
        )
        expected_run_config = paths["run_config"].resolve(strict=True)
        expected_runner = paths["runner_source"].resolve(strict=True)
    except Exception as error:
        raise ReviewFinalizationError("bundle_binding_invalid") from error
    finally:
        sys.modules.pop(runner.__name__, None)
    if (
        verified_config != run_config
        or run_config_path.resolve(strict=True) != expected_run_config
        or runner_path.resolve(strict=True) != expected_runner
    ):
        raise ReviewFinalizationError("bundle_binding_invalid")
    artifact_public = {
        "git_commit": commit,
        "bundle_sha256": bundle,
        "runner_sha256": str(kernel["sha256"]),
        "review_finalizer_sha256": finalizer_sha256,
    }
    expected_private = {
        **artifact_public,
        "private_case_index_sha256": _sha256_bytes(case_payload),
    }
    case_provenance = case_index.get("provenance")
    inventory_provenance = inventory.get("provenance")
    if (
        not isinstance(case_provenance, dict)
        or case_provenance != artifact_public
        or not isinstance(inventory_provenance, dict)
        or inventory_provenance != expected_private
    ):
        raise ReviewFinalizationError("private_artifact_binding_invalid")
    return _public_review_identity(run_config, manifest), case_index, inventory, runner


def _validate_series_terminal_evidence(item: Mapping[str, Any]) -> bool:
    terminal = item.get("terminal_state")
    model_eligible = item.get("model_eligible")
    if model_eligible:
        if (
            item.get("source_failure") is not None
            or item.get("preprocessing_failure") is not None
            or item.get("model_output_reconstruction") is None
            or item.get("qa_output_reconstruction") is None
        ):
            raise ReviewFinalizationError("private_case_index_invalid")
        return True
    if (terminal == "decode_blocked" and not item.get("decode_failures")) or (
        terminal == "ordering_blocked" and item.get("ordering_failure") is None
    ):
        raise ReviewFinalizationError("private_case_index_invalid")
    if terminal == "source_access_blocked":
        source_failure = item.get("source_failure")
        if (
            not isinstance(source_failure, str)
            or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", source_failure) is None
            or item.get("decode_failures")
            or item.get("ordering_failure") is not None
            or item.get("preprocessing_failure") is not None
            or item.get("model_output_reconstruction") is not None
            or item.get("qa_output_reconstruction") is not None
        ):
            raise ReviewFinalizationError("private_case_index_invalid")
    elif terminal == "preprocessing_blocked":
        failure = item.get("preprocessing_failure")
        if (
            item.get("source_failure") is not None
            or item.get("decode_failures")
            or item.get("ordering_failure") is not None
            or not isinstance(failure, dict)
            or set(failure) != {"issue", "stage", "root_cause", "exception_type"}
            or not isinstance(failure.get("issue"), str)
            or not isinstance(failure.get("stage"), str)
            or item.get("model_output_reconstruction") is not None
            or item.get("qa_output_reconstruction") is not None
        ):
            raise ReviewFinalizationError("private_case_index_invalid")
    elif item.get("source_failure") is not None or item.get("preprocessing_failure") is not None:
        raise ReviewFinalizationError("private_case_index_invalid")
    return False


def _fixed_enum_list(value: object, order: tuple[str, ...]) -> list[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return None
    items = cast(list[str], value)
    positions = {item: index for index, item in enumerate(order)}
    if (
        len(items) > len(order)
        or len(set(items)) != len(items)
        or any(item not in positions for item in items)
        or items != sorted(items, key=positions.__getitem__)
    ):
        return None
    return items


def _validate_review_context(value: object, series_ordinal: int) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {
        "organizer_plane",
        "physical_plane",
        "assigned_slot",
        "retention_reasons",
        "missing_series_mask",
        "sibling_series",
    }:
        raise ReviewFinalizationError("private_case_index_invalid")
    organizer_plane = value.get("organizer_plane")
    physical_plane = value.get("physical_plane")
    assigned_slot = value.get("assigned_slot")
    retention_reasons = _fixed_enum_list(value.get("retention_reasons"), RETENTION_REASON_ORDER)
    missing_mask = value.get("missing_series_mask")
    siblings = value.get("sibling_series")
    if (
        organizer_plane not in ORGANIZER_PLANES
        or physical_plane not in PHYSICAL_PLANES
        or assigned_slot not in SERIES_SLOTS
        or retention_reasons is None
        or not isinstance(missing_mask, list)
        or len(missing_mask) != len(PRIMARY_SERIES_SLOTS)
        or any(not isinstance(item, bool) for item in missing_mask)
        or not isinstance(siblings, list)
        or not 1 <= len(siblings) <= 1_000
        or not 0 <= series_ordinal < len(siblings)
    ):
        raise ReviewFinalizationError("private_case_index_invalid")
    if (
        assigned_slot in PRIMARY_SERIES_SLOTS
        and missing_mask[PRIMARY_SERIES_SLOTS.index(cast(str, assigned_slot))] is not False
    ):
        raise ReviewFinalizationError("private_case_index_invalid")
    for expected_ordinal, sibling in enumerate(siblings):
        if not isinstance(sibling, dict) or set(sibling) != {
            "series_ordinal",
            "slot",
            "terminal_state",
            "model_eligible",
            "retention_reasons",
            "quality_blocked_reasons",
        }:
            raise ReviewFinalizationError("private_case_index_invalid")
        terminal = sibling.get("terminal_state")
        model_eligible = sibling.get("model_eligible")
        if (
            sibling.get("series_ordinal") != expected_ordinal
            or sibling.get("slot") not in SERIES_SLOTS
            or terminal not in TERMINAL_STATES
            or not isinstance(model_eligible, bool)
            or (terminal == "model_eligible") is not model_eligible
            or _fixed_enum_list(sibling.get("retention_reasons"), RETENTION_REASON_ORDER) is None
            or _fixed_enum_list(sibling.get("quality_blocked_reasons"), QUALITY_BLOCK_REASON_ORDER)
            is None
        ):
            raise ReviewFinalizationError("private_case_index_invalid")
    current = cast(dict[str, object], siblings[series_ordinal])
    if (
        current.get("terminal_state") != "model_eligible"
        or current.get("model_eligible") is not True
        or current.get("slot") != assigned_slot
        or current.get("retention_reasons") != retention_reasons
    ):
        raise ReviewFinalizationError("private_case_index_invalid")
    return cast(dict[str, object], value)


def _case_series(
    case_index: Mapping[str, Any], inventory: Mapping[str, Any]
) -> tuple[
    dict[int, tuple[tuple[str, ...], tuple[int, ...]]],
    dict[tuple[int, int], tuple[dict[str, str], ...]],
    dict[tuple[int, int], dict[str, object]],
]:
    if (
        set(case_index)
        != {
            "schema_version",
            "artifact_type",
            "status",
            "provenance",
            "input_identity",
            "qa_cohort_selection",
            "selection_census",
            "represented_review_strata",
            "studies",
            "benchmark",
            "full_run",
        }
        or case_index.get("schema_version") != 1
        or case_index.get("artifact_type") != "private-dicom-qa-case-index"
        or case_index.get("status") != "pending_private_human_review"
        or not isinstance(case_index.get("selection_census"), list)
        or not isinstance(case_index.get("studies"), list)
    ):
        raise ReviewFinalizationError("private_case_index_invalid")
    census = cast(list[object], case_index["selection_census"])
    census_population: dict[tuple[str, ...], tuple[int, int, bool]] = {}
    for item in census:
        if not isinstance(item, dict) or set(item) != {
            "stratum",
            "population_studies",
            "selected_studies",
            "material",
        }:
            raise ReviewFinalizationError("private_case_index_invalid")
        stratum_raw = item.get("stratum")
        population = item.get("population_studies")
        selected = item.get("selected_studies")
        material = item.get("material")
        if (
            not isinstance(stratum_raw, list)
            or len(stratum_raw) != 11
            or any(not isinstance(value, str) or not value for value in stratum_raw)
            or isinstance(population, bool)
            or not isinstance(population, int)
            or population < 1
            or isinstance(selected, bool)
            or not isinstance(selected, int)
            or not 0 <= selected <= population
            or not isinstance(material, bool)
            or material is not (population >= 2)
        ):
            raise ReviewFinalizationError("private_case_index_invalid")
        stratum = tuple(cast(list[str], stratum_raw))
        if stratum in census_population:
            raise ReviewFinalizationError("private_case_index_invalid")
        census_population[stratum] = (population, selected, material)
    if not census_population:
        raise ReviewFinalizationError("private_case_index_invalid")

    eligible: dict[int, tuple[tuple[str, ...], tuple[int, ...]]] = {}
    review_contexts: dict[tuple[int, int], dict[str, object]] = {}
    observed_cases: set[int] = set()
    selected_counts: dict[tuple[str, ...], int] = defaultdict(int)
    observed_review_strata: set[tuple[str, ...]] = set()
    for study in cast(list[object], case_index["studies"]):
        if not isinstance(study, dict) or set(study) != {
            "case_ordinal",
            "study_uid",
            "selection_stratum",
            "review_eligible",
            "missing_series_mask",
            "series",
        }:
            raise ReviewFinalizationError("private_case_index_invalid")
        case = study.get("case_ordinal")
        stratum_raw = study.get("selection_stratum")
        series = study.get("series")
        missing_mask = study.get("missing_series_mask")
        if (
            isinstance(case, bool)
            or not isinstance(case, int)
            or not 0 <= case < MAX_REVIEWED_STUDIES
            or case in observed_cases
            or not isinstance(study.get("study_uid"), str)
            or len(str(study.get("study_uid"))) > 80
            or not isinstance(stratum_raw, list)
            or len(stratum_raw) != 11
            or any(not isinstance(value, str) for value in stratum_raw)
            or not isinstance(study.get("review_eligible"), bool)
            or not isinstance(missing_mask, list)
            or len(missing_mask) != len(PRIMARY_SERIES_SLOTS)
            or any(not isinstance(value, bool) for value in missing_mask)
            or not isinstance(series, list)
            or not series
        ):
            raise ReviewFinalizationError("private_case_index_invalid")
        observed_cases.add(case)
        study_stratum = tuple(cast(list[str], stratum_raw))
        if study_stratum not in census_population:
            raise ReviewFinalizationError("private_case_index_invalid")
        selected_counts[study_stratum] += 1
        eligible_series: list[int] = []
        observed_series: set[int] = set()
        sibling_series: list[dict[str, object]] = []
        context_fields: dict[int, tuple[str, str, str, list[str]]] = {}
        for item in series:
            if not isinstance(item, dict) or set(item) != {
                "series_ordinal",
                "series_uid",
                "organizer_plane",
                "physical_plane",
                "slot",
                "retention_reasons",
                "quality",
                "source_failure",
                "decode_failures",
                "ordering_failure",
                "preprocessing_failure",
                "terminal_state",
                "model_eligible",
                "model_output_reconstruction",
                "qa_output_reconstruction",
            }:
                raise ReviewFinalizationError("private_case_index_invalid")
            ordinal = item.get("series_ordinal")
            terminal = item.get("terminal_state")
            model_eligible = item.get("model_eligible")
            organizer_plane = item.get("organizer_plane")
            physical_plane = item.get("physical_plane")
            slot = item.get("slot")
            retention_reasons = _fixed_enum_list(
                item.get("retention_reasons"), RETENTION_REASON_ORDER
            )
            quality = item.get("quality")
            quality_blocked_reasons = (
                _fixed_enum_list(quality.get("blocked_reasons"), QUALITY_BLOCK_REASON_ORDER)
                if isinstance(quality, dict) and set(quality) == {"blocked_reasons", "components"}
                else None
            )
            if (
                isinstance(ordinal, bool)
                or not isinstance(ordinal, int)
                or not 0 <= ordinal <= 999
                or ordinal in observed_series
                or terminal not in TERMINAL_STATES
                or not isinstance(model_eligible, bool)
                or (terminal == "model_eligible") is not model_eligible
                or not isinstance(item.get("series_uid"), str)
                or len(str(item.get("series_uid"))) > 80
                or organizer_plane not in ORGANIZER_PLANES
                or physical_plane not in PHYSICAL_PLANES
                or slot not in SERIES_SLOTS
                or retention_reasons is None
                or quality_blocked_reasons is None
            ):
                raise ReviewFinalizationError("private_case_index_invalid")
            observed_series.add(ordinal)
            context_fields[ordinal] = (
                cast(str, organizer_plane),
                cast(str, physical_plane),
                cast(str, slot),
                retention_reasons,
            )
            sibling_series.append(
                {
                    "series_ordinal": ordinal,
                    "slot": slot,
                    "terminal_state": terminal,
                    "model_eligible": model_eligible,
                    "retention_reasons": retention_reasons,
                    "quality_blocked_reasons": quality_blocked_reasons,
                }
            )
            if _validate_series_terminal_evidence(item):
                eligible_series.append(ordinal)
        if sorted(observed_series) != list(range(len(series))):
            raise ReviewFinalizationError("private_case_index_invalid")
        sibling_series.sort(key=lambda item: cast(int, item["series_ordinal"]))
        for eligible_ordinal in eligible_series:
            organizer_plane, physical_plane, assigned_slot, retention_reasons = context_fields[
                eligible_ordinal
            ]
            context = {
                "organizer_plane": organizer_plane,
                "physical_plane": physical_plane,
                "assigned_slot": assigned_slot,
                "retention_reasons": retention_reasons,
                "missing_series_mask": cast(list[bool], missing_mask),
                "sibling_series": sibling_series,
            }
            review_contexts[(case, eligible_ordinal)] = _validate_review_context(
                context, eligible_ordinal
            )
        if bool(eligible_series) is not study["review_eligible"]:
            raise ReviewFinalizationError("private_case_index_invalid")
        if eligible_series:
            eligible[case] = (study_stratum, tuple(sorted(eligible_series)))
            observed_review_strata.add(study_stratum)
    if (
        len(observed_cases) > MAX_REVIEWED_STUDIES
        or sum(selected for _population, selected, _material in census_population.values())
        != len(observed_cases)
        or any(
            selected_counts[stratum] != selected or (material and selected < min(2, population))
            for stratum, (population, selected, material) in census_population.items()
        )
    ):
        raise ReviewFinalizationError("private_case_index_invalid")
    represented = case_index.get("represented_review_strata")
    if represented != [list(item) for item in sorted(observed_review_strata)]:
        raise ReviewFinalizationError("private_case_index_invalid")
    if len(eligible) < MINIMUM_REVIEWED_STUDIES:
        raise ReviewFinalizationError("review_population_insufficient")

    if (
        set(inventory) != {"schema_version", "artifact_type", "status", "provenance", "artifacts"}
        or inventory.get("schema_version") != 1
        or inventory.get("artifact_type") != "private-dicom-qa-artifact-inventory"
        or inventory.get("status") != "pending_private_human_review"
        or not isinstance(inventory.get("artifacts"), list)
    ):
        raise ReviewFinalizationError("private_inventory_invalid")
    grouped: dict[tuple[int, int], list[dict[str, str]]] = defaultdict(list)
    names: set[str] = set()
    for item in cast(list[object], inventory["artifacts"]):
        if (
            not isinstance(item, dict)
            or set(item) != {"name", "bytes", "sha256"}
            or not isinstance(item.get("name"), str)
            or SAFE_ARTIFACT.fullmatch(str(item["name"])) is None
            or item["name"] in names
            or isinstance(item.get("bytes"), bool)
            or not isinstance(item.get("bytes"), int)
            or not 0 < cast(int, item["bytes"]) <= 32 * 1024**2
            or not isinstance(item.get("sha256"), str)
            or HEX_64.fullmatch(str(item["sha256"])) is None
        ):
            raise ReviewFinalizationError("private_inventory_invalid")
        name = str(item["name"])
        names.add(name)
        match = re.fullmatch(r"case_([0-9]{6})_series_([0-9]{3})_(.+)", name)
        if match is None:
            raise ReviewFinalizationError("private_inventory_invalid")
        grouped[(int(match.group(1)), int(match.group(2)))].append(
            {"name": name, "sha256": str(item["sha256"])}
        )
    expected_keys = {
        (case, series_ordinal)
        for case, (_stratum, series) in eligible.items()
        for series_ordinal in series
    }
    if set(grouped) != expected_keys:
        raise ReviewFinalizationError("private_inventory_invalid")
    artifact_map: dict[tuple[int, int], tuple[dict[str, str], ...]] = {}
    for key, records in grouped.items():
        prefix = f"case_{key[0]:06d}_series_{key[1]:03d}_"
        suffixes = {record["name"].removeprefix(prefix) for record in records}
        if not REQUIRED_SUFFIXES.issubset(suffixes) or not suffixes.issubset(ALLOWED_SUFFIXES):
            raise ReviewFinalizationError("private_inventory_invalid")
        artifact_map[key] = tuple(sorted(records, key=lambda item: item["name"]))
    if set(review_contexts) != expected_keys:
        raise ReviewFinalizationError("private_case_index_invalid")
    return eligible, artifact_map, review_contexts


def _review_case_ordinals(
    eligible: Mapping[int, tuple[tuple[str, ...], tuple[int, ...]]],
) -> tuple[int, ...]:
    selected = tuple(sorted(eligible))
    if len(selected) < MINIMUM_REVIEWED_STUDIES:
        raise ReviewFinalizationError("review_selection_invalid")
    return selected


def _private_review_identity(
    static_identity: Mapping[str, Any], case_index: Mapping[str, Any]
) -> dict[str, Any]:
    input_identity = case_index.get("input_identity")
    selection = case_index.get("qa_cohort_selection")
    studies = case_index.get("studies")
    if (
        not isinstance(input_identity, dict)
        or set(input_identity) != {"source_manifest", "official_competition"}
        or not isinstance(selection, dict)
        or set(selection)
        != {
            "selection_version",
            "selected_studies",
            "eligible_series",
            "cohort_sha256",
            "source_manifest_gate",
            "coverage",
        }
        or selection.get("selection_version") != QA_COHORT_SELECTION_VERSION
        or selection.get("source_manifest_gate") != "pass"
        or not isinstance(studies, list)
        or not studies
    ):
        raise ReviewFinalizationError("review_identity_invalid")
    private_source = input_identity.get("source_manifest")
    private_official = input_identity.get("official_competition")
    if (
        not isinstance(private_source, dict)
        or set(private_source) != {"audit_id", "version", "source_manifest_artifact_sha256"}
        or private_source.get("audit_id") != static_identity["source_manifest"]["audit_id"]
        or private_source.get("version") != static_identity["source_manifest"]["version"]
        or not isinstance(private_source.get("source_manifest_artifact_sha256"), str)
        or HEX_64.fullmatch(str(private_source["source_manifest_artifact_sha256"])) is None
        or not isinstance(private_official, dict)
        or set(private_official) != {"slug", "official_input_snapshot_sha256"}
        or private_official.get("slug") != static_identity["official_competition"]["slug"]
        or not isinstance(private_official.get("official_input_snapshot_sha256"), str)
        or HEX_64.fullmatch(str(private_official["official_input_snapshot_sha256"])) is None
    ):
        raise ReviewFinalizationError("review_identity_invalid")

    ordered_studies = sorted(
        (cast(dict[str, Any], study) for study in studies),
        key=lambda study: study.get("case_ordinal", -1),
    )
    cohort_studies: list[dict[str, object]] = []
    eligible_series = 0
    for ordinal, study in enumerate(ordered_studies):
        series = study.get("series")
        if (
            study.get("case_ordinal") != ordinal
            or not isinstance(study.get("study_uid"), str)
            or not isinstance(study.get("selection_stratum"), list)
            or len(study["selection_stratum"]) != 11
            or not isinstance(series, list)
        ):
            raise ReviewFinalizationError("review_identity_invalid")
        series_uids = sorted(
            str(item["series_uid"])
            for item in series
            if isinstance(item, dict) and item.get("model_eligible") is True
        )
        if any(not uid or len(uid) > 80 for uid in series_uids):
            raise ReviewFinalizationError("review_identity_invalid")
        eligible_series += len(series_uids)
        cohort_studies.append(
            {
                "study_uid": study["study_uid"],
                "selection_stratum": study["selection_stratum"],
                "eligible_series_uids": series_uids,
            }
        )
    cohort_sha256 = _sha256_bytes(
        _canonical_json_bytes(
            {
                "domain": "rsna-knee-dicom-qa-cohort-v2",
                "selection_version": QA_COHORT_SELECTION_VERSION,
                "studies": cohort_studies,
            }
        )
    )
    if (
        selection.get("selected_studies") != len(ordered_studies)
        or selection.get("eligible_series") != eligible_series
        or selection.get("cohort_sha256") != cohort_sha256
    ):
        raise ReviewFinalizationError("review_identity_invalid")
    coverage = selection.get("coverage")
    observed_coverage: set[tuple[str, str]] = set()
    if not isinstance(coverage, list) or not coverage:
        raise ReviewFinalizationError("review_identity_invalid")
    for row in coverage:
        if not isinstance(row, dict) or set(row) != {
            "dimension",
            "value",
            "population_studies",
            "selected_studies",
            "disposition",
            "source",
        }:
            raise ReviewFinalizationError("review_identity_invalid")
        key = (row.get("dimension"), row.get("value"))
        population = row.get("population_studies")
        selected = row.get("selected_studies")
        disposition = row.get("disposition")
        if (
            any(not isinstance(value, str) or not value for value in key)
            or cast(tuple[str, str], key) in observed_coverage
            or isinstance(population, bool)
            or not isinstance(population, int)
            or population < 0
            or isinstance(selected, bool)
            or not isinstance(selected, int)
            or not 0 <= selected <= population
            or disposition not in {"covered", "represented_nonmaterial", "not_represented"}
            or row.get("source") not in {"manifest-v2", "full_run_terminal_records"}
            or (disposition == "not_represented") is not (population == selected == 0)
            or (population > 0 and selected == 0)
        ):
            raise ReviewFinalizationError("review_identity_invalid")
        observed_coverage.add(cast(tuple[str, str], key))
    if len({dimension for dimension, _value in observed_coverage}) != 19:
        raise ReviewFinalizationError("review_identity_invalid")

    identity = {
        **dict(static_identity),
        "official_competition_input": {
            **dict(static_identity["official_competition"]),
            "snapshot_version": "chunk4-private-root-inventory-v1",
            "snapshot_sha256": private_official["official_input_snapshot_sha256"],
        },
        "source_manifest": {
            **dict(static_identity["source_manifest"]),
            "artifact_sha256": private_source["source_manifest_artifact_sha256"],
        },
        "qa_cohort": {
            "selection_version": QA_COHORT_SELECTION_VERSION,
            "sha256": cohort_sha256,
            "coverage": coverage,
        },
    }
    identity.pop("official_competition")
    identity["review_bundle_id"] = (
        "c5qa-"
        + _sha256_bytes(
            _canonical_json_bytes(
                {"domain": "rsna-knee-private-review-bundle-v1", "identity": identity}
            )
        )[:20]
    )
    return identity


def _template(
    static_identity: Mapping[str, Any],
    case_index: Mapping[str, Any],
    eligible: Mapping[int, tuple[tuple[str, ...], tuple[int, ...]]],
    artifact_map: Mapping[tuple[int, int], tuple[dict[str, str], ...]],
    review_contexts: Mapping[tuple[int, int], dict[str, object]],
) -> dict[str, object]:
    selected = _review_case_ordinals(eligible)
    selected_series = {(case, series) for case in selected for series in eligible[case][1]}
    if set(review_contexts) != selected_series:
        raise ReviewFinalizationError("private_case_index_invalid")
    rows = []
    for case in selected:
        for series in eligible[case][1]:
            rows.append(
                {
                    "case_ordinal": case,
                    "series_ordinal": series,
                    "review_context": _validate_review_context(
                        review_contexts[(case, series)], series
                    ),
                    "decisions": {check: "not_reviewed" for check in REVIEW_CHECKS},
                    "artifacts": list(artifact_map[(case, series)]),
                }
            )
    return {
        "schema_version": 1,
        "artifact_type": "private-dicom-qa-review-plan",
        "status": "pending_private_human_review",
        "review_identity": _private_review_identity(static_identity, case_index),
        "rows": rows,
    }


def create_template(
    *,
    run_config_payload: bytes,
    manifest_payload: bytes,
    case_payload: bytes,
    inventory_payload: bytes,
    finalizer_sha256: str,
    bundle_root: Path,
    run_config_path: Path,
    runner_path: Path,
    private_review_root: Path,
) -> bytes:
    """Create the canonical private plan for the minimum sufficient review cohort."""

    static_identity, case_index, inventory, _runner = _binding(
        run_config_payload,
        manifest_payload,
        case_payload,
        inventory_payload,
        finalizer_sha256=finalizer_sha256,
        bundle_root=bundle_root,
        run_config_path=run_config_path,
        runner_path=runner_path,
    )
    eligible, artifacts, review_contexts = _case_series(case_index, inventory)
    _verify_private_artifacts(private_review_root, inventory)
    return _canonical_json_bytes(
        _template(static_identity, case_index, eligible, artifacts, review_contexts)
    )


def validate_sanitized_summary(
    payload: bytes,
    run_config: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the human-review aggregate allowed to leave the private environment."""

    summary = _json_object(payload, "review_summary_invalid")
    static = _public_review_identity(run_config, manifest)
    review = summary.get("review")
    versions = summary.get("versions")
    privacy = summary.get("privacy")
    reviewed_range = (
        _reviewed_study_bounds(review.get("reviewed_studies")) if isinstance(review, dict) else None
    )
    eligible_range = (
        _k20_range_bounds(review.get("eligible_series_reviewed"))
        if isinstance(review, dict)
        else None
    )
    block_range = (
        _count_token_bounds(review.get("block_decisions")) if isinstance(review, dict) else None
    )
    if (
        set(summary)
        != {
            "schema_version",
            "artifact_type",
            "status",
            "completed_at_utc",
            "versions",
            "review",
            "privacy",
        }
        or summary.get("schema_version") != 1
        or summary.get("artifact_type") != "dicom-qa-human-review-sanitized-aggregate"
        or summary.get("status") not in {"complete", "blocked"}
        or not isinstance(summary.get("completed_at_utc"), str)
        or re.fullmatch(
            r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
            str(summary["completed_at_utc"]),
        )
        is None
        or versions
        != {
            "preprocessing": static["preprocessing"]["version"],
            "source_manifest": static["source_manifest"]["version"],
            "source_manifest_audit": static["source_manifest"].get("audit_id"),
            "cohort_selection": static["cohort_selection_version"],
            "review_protocol": REVIEW_PROTOCOL_VERSION,
        }
        or not isinstance(review, dict)
        or set(review)
        != {
            "reviewed_studies",
            "eligible_series_reviewed",
            "represented_strata",
            "all_eligible_series_complete",
            "all_nine_checks_terminal",
            "artifact_presence_verified",
            "review_identity_bound",
            "check_results",
            "block_decisions",
            "zero_blocks",
        }
        or reviewed_range is None
        or not MINIMUM_REVIEWED_STUDIES <= reviewed_range[0] <= MAX_REVIEWED_STUDIES
        or eligible_range is None
        or eligible_range[0] < reviewed_range[0]
        or review.get("represented_strata") != "all_material_covered"
        or not isinstance(review.get("check_results"), dict)
        or set(review["check_results"]) != set(REVIEW_CHECKS)
        or any(value not in {"PASS", "BLOCK"} for value in review["check_results"].values())
        or block_range is None
        or any(
            review.get(key) is not True
            for key in (
                "all_eligible_series_complete",
                "all_nine_checks_terminal",
                "artifact_presence_verified",
                "review_identity_bound",
            )
        )
        or review.get("zero_blocks") is not (review["block_decisions"] == "zero")
        or (summary["status"] == "complete")
        is not (
            review["zero_blocks"]
            and all(value == "PASS" for value in review["check_results"].values())
        )
        or privacy
        != {
            "case_rows_downloadable": False,
            "identifiers_downloadable": False,
            "cohort_hash_downloadable": False,
            "private_artifact_hashes_downloadable": False,
            "free_text_downloadable": False,
            "pixels_downloadable": False,
        }
    ):
        raise ReviewFinalizationError("review_summary_invalid")
    return summary


def _validated_determinism_summary(payload: bytes) -> dict[str, Any]:
    summary = _json_object(payload, "comparison_summary_invalid")
    if summary != DETERMINISM_PASS:
        raise ReviewFinalizationError("comparison_summary_invalid")
    return summary


def validate_sanitized_performance_report(
    payload: bytes,
    run_config: Mapping[str, Any],
    manifest: Mapping[str, Any],
    runner: ModuleType,
    human_review: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the disclosure-safe final performance artifact and its review binding."""

    report = _json_object(payload, "performance_report_invalid")
    static = _public_review_identity(run_config, manifest)
    review_summary = validate_sanitized_summary(
        _canonical_json_bytes(human_review), run_config, manifest
    )
    review = cast(Mapping[str, Any], review_summary["review"])
    check_results = cast(Mapping[str, Any], review["check_results"])
    all_checks_pass = all(check_results[check] == "PASS" for check in REVIEW_CHECKS)
    expected_status = "pass" if review_summary["status"] == "complete" else "blocked"
    expected_review = {
        "completed_at_utc": review_summary["completed_at_utc"],
        "reviewed_studies": review["reviewed_studies"],
        "eligible_series_reviewed": review["eligible_series_reviewed"],
        "represented_strata": review["represented_strata"],
        "check_results": dict(check_results),
        "all_nine_checks_pass": all_checks_pass,
        "block_decisions": review["block_decisions"],
        "zero_blocks": review["zero_blocks"],
    }
    performance = report.get("performance")
    if not isinstance(performance, dict):
        raise ReviewFinalizationError("performance_report_invalid")
    pending_performance = dict(performance)
    if pending_performance.get("determinism_status") != "pass_exact_independent_runs":
        raise ReviewFinalizationError("performance_report_invalid")
    pending_performance["determinism_status"] = "pending_independent_run_comparison"
    try:
        runner._validate_performance(pending_performance)
    except Exception as error:
        raise ReviewFinalizationError("performance_report_invalid") from error
    if (
        set(report)
        != {
            "schema_version",
            "artifact_type",
            "status",
            "provenance",
            "input_snapshot",
            "performance",
            "determinism",
            "human_review",
            "exit_gate",
            "privacy",
        }
        or report.get("schema_version") != 1
        or report.get("artifact_type") != "dicom-qa-final-sanitized-performance-report"
        or report.get("status") != expected_status
        or report.get("provenance")
        != {
            "git_commit": static["git_commit"],
            "project_bundle_sha256": static["project_bundle_sha256"],
            "preprocessing_config_sha256": static["preprocessing"]["config_sha256"],
            "pipeline_version": static["preprocessing"]["version"],
        }
        or report.get("input_snapshot")
        != {
            "competition_slug": static["official_competition"]["slug"],
            "snapshot_identity_source": static["official_competition"]["snapshot_identity_source"],
            "source_manifest_version": static["source_manifest"]["version"],
            "source_manifest_audit": static["source_manifest"]["audit_id"],
        }
        or report.get("determinism") != DETERMINISM_PASS
        or report.get("human_review") != expected_review
        or report.get("exit_gate")
        != {
            "unresolved_blockers": "zero",
            "disclosure_policy": "joint-complementary-k20-v1",
        }
        or report.get("privacy")
        != {
            "case_details_downloadable": False,
            "identifiers_downloadable": False,
            "private_counts_downloadable": False,
            "private_digests_downloadable": False,
            "raw_throughput_downloadable": False,
            "pixels_downloadable": False,
        }
        or all_checks_pass is not (review["zero_blocks"] is True)
    ):
        raise ReviewFinalizationError("performance_report_invalid")
    return report


def _final_performance_report(
    *,
    run_a_payload: bytes,
    comparison_payload: bytes,
    review_payload: bytes,
    run_config: Mapping[str, Any],
    manifest: Mapping[str, Any],
    runner: ModuleType,
) -> bytes:
    try:
        run_a = runner._validate_summary(run_a_payload, run_config)
    except Exception as error:
        raise ReviewFinalizationError("run_a_summary_invalid") from error
    provenance = run_a.get("provenance")
    pipeline = run_a.get("pipeline")
    if (
        run_a.get("status") != "complete_pending_human_review"
        or not isinstance(provenance, dict)
        or provenance.get("runner_sha256") != cast(Mapping[str, Any], manifest["kernel"])["sha256"]
        or not isinstance(pipeline, dict)
        or pipeline.get("integrity_gate") != "pass"
        or pipeline.get("unresolved_blockers") != "zero"
    ):
        raise ReviewFinalizationError("run_a_summary_invalid")
    determinism = _validated_determinism_summary(comparison_payload)
    review = validate_sanitized_summary(review_payload, run_config, manifest)
    review_values = cast(Mapping[str, Any], review["review"])
    performance = dict(cast(Mapping[str, Any], run_a["performance"]))
    performance["determinism_status"] = "pass_exact_independent_runs"
    all_checks_pass = all(
        value == "PASS"
        for value in cast(Mapping[str, Any], review_values["check_results"]).values()
    )
    report = {
        "schema_version": 1,
        "artifact_type": "dicom-qa-final-sanitized-performance-report",
        "status": "pass" if review["status"] == "complete" else "blocked",
        "provenance": {
            "git_commit": run_config["code_commit"],
            "project_bundle_sha256": run_config["bundle_sha256"],
            "preprocessing_config_sha256": cast(Mapping[str, Any], run_config["provenance"])[
                "preprocessing_config_sha256"
            ],
            "pipeline_version": provenance["preprocessing_version"],
        },
        "input_snapshot": {
            "competition_slug": cast(Mapping[str, Any], run_config["competition"])["slug"],
            "snapshot_identity_source": cast(
                Mapping[str, Any],
                cast(Mapping[str, Any], run_config["input_identity"])["official_competition"],
            )["snapshot_identity_source"],
            "source_manifest_version": provenance["source_manifest_version"],
            "source_manifest_audit": cast(
                Mapping[str, Any],
                cast(Mapping[str, Any], run_config["input_identity"])["source_manifest"],
            )["audit_id"],
        },
        "performance": performance,
        "determinism": determinism,
        "human_review": {
            "completed_at_utc": review["completed_at_utc"],
            "reviewed_studies": review_values["reviewed_studies"],
            "eligible_series_reviewed": review_values["eligible_series_reviewed"],
            "represented_strata": review_values["represented_strata"],
            "check_results": review_values["check_results"],
            "all_nine_checks_pass": all_checks_pass,
            "block_decisions": review_values["block_decisions"],
            "zero_blocks": review_values["zero_blocks"],
        },
        "exit_gate": {
            "unresolved_blockers": "zero",
            "disclosure_policy": "joint-complementary-k20-v1",
        },
        "privacy": {
            "case_details_downloadable": False,
            "identifiers_downloadable": False,
            "private_counts_downloadable": False,
            "private_digests_downloadable": False,
            "raw_throughput_downloadable": False,
            "pixels_downloadable": False,
        },
    }
    payload = _canonical_json_bytes(report)
    validate_sanitized_performance_report(payload, run_config, manifest, runner, review)
    return payload


def _validated_ledger(payload: bytes, plan: Mapping[str, Any]) -> dict[str, Any]:
    ledger = _json_object(payload, "review_ledger_invalid")
    rows = ledger.get("rows")
    plan_rows = plan.get("rows")
    if (
        set(ledger)
        != {
            "schema_version",
            "artifact_type",
            "status",
            "review_identity",
            "plan_sha256",
            "completed_at_utc",
            "rows",
        }
        or ledger.get("schema_version") != 1
        or ledger.get("artifact_type") != "private-dicom-qa-completed-review-ledger"
        or ledger.get("status") != "complete"
        or ledger.get("review_identity") != plan.get("review_identity")
        or ledger.get("plan_sha256") != _sha256_bytes(_canonical_json_bytes(plan))
        or not isinstance(ledger.get("completed_at_utc"), str)
        or re.fullmatch(
            r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
            str(ledger["completed_at_utc"]),
        )
        is None
        or not isinstance(rows, list)
        or not isinstance(plan_rows, list)
        or len(rows) != len(plan_rows)
    ):
        raise ReviewFinalizationError("review_ledger_invalid")
    passed_checks: set[str] = set()
    for row, expected in zip(rows, plan_rows, strict=True):
        if (
            not isinstance(row, dict)
            or not isinstance(expected, dict)
            or set(row)
            != {
                "case_ordinal",
                "series_ordinal",
                "artifact_hashes_verified",
                "decisions",
            }
            or row.get("case_ordinal") != expected.get("case_ordinal")
            or row.get("series_ordinal") != expected.get("series_ordinal")
            or row.get("artifact_hashes_verified") is not True
            or not isinstance(row.get("decisions"), dict)
            or set(row["decisions"]) != set(REVIEW_CHECKS)
            or any(value not in REVIEW_STATUSES for value in row["decisions"].values())
            or any(
                value == "NOT_APPLICABLE" and check not in NOT_APPLICABLE_CHECKS
                for check, value in row["decisions"].items()
            )
        ):
            raise ReviewFinalizationError("review_ledger_invalid")
        passed_checks.update(check for check, value in row["decisions"].items() if value == "PASS")
    if passed_checks != set(REVIEW_CHECKS):
        raise ReviewFinalizationError("review_ledger_invalid")
    return ledger


def finalize_review(
    *,
    run_config_payload: bytes,
    manifest_payload: bytes,
    case_payload: bytes,
    inventory_payload: bytes,
    ledger_payload: bytes,
    run_a_summary_payload: bytes,
    comparison_summary_payload: bytes,
    finalizer_sha256: str,
    bundle_root: Path,
    run_config_path: Path,
    runner_path: Path,
    private_review_root: Path,
) -> tuple[bytes, bytes, bytes]:
    """Derive the aggregate attestation from exact private completed review rows."""

    static_identity, case_index, inventory, runner = _binding(
        run_config_payload,
        manifest_payload,
        case_payload,
        inventory_payload,
        finalizer_sha256=finalizer_sha256,
        bundle_root=bundle_root,
        run_config_path=run_config_path,
        runner_path=runner_path,
    )
    eligible, artifacts, review_contexts = _case_series(case_index, inventory)
    _verify_private_artifacts(private_review_root, inventory)
    plan = _template(static_identity, case_index, eligible, artifacts, review_contexts)
    ledger = _validated_ledger(ledger_payload, plan)
    reviewed_cases = sorted({int(row["case_ordinal"]) for row in ledger["rows"]})
    if reviewed_cases != list(_review_case_ordinals(eligible)):
        raise ReviewFinalizationError("review_ledger_invalid")
    block_count = sum(
        decision == "BLOCK" for row in ledger["rows"] for decision in row["decisions"].values()
    )
    decision_counts = {
        check: {
            status: sum(row["decisions"][check] == status for row in ledger["rows"])
            for status in sorted(REVIEW_STATUSES)
        }
        for check in REVIEW_CHECKS
    }
    represented_strata = [
        list(value) for value in sorted({eligible[case][0] for case in reviewed_cases})
    ]
    private_completion = _canonical_json_bytes(
        {
            "schema_version": 1,
            "artifact_type": "private-dicom-qa-human-review-completion",
            "status": "complete" if block_count == 0 else "blocked",
            "review_identity": plan["review_identity"],
            "plan_sha256": _sha256_bytes(_canonical_json_bytes(plan)),
            "ledger_sha256": _sha256_bytes(ledger_payload),
            "completed_at_utc": ledger["completed_at_utc"],
            "review": {
                "reviewed_studies": len(reviewed_cases),
                "eligible_series_reviewed": len(ledger["rows"]),
                "represented_strata": represented_strata,
                "decision_counts": decision_counts,
                "block_decisions": block_count,
                "all_eligible_series_complete": True,
                "artifact_presence_verified": True,
            },
            "rows": ledger["rows"],
        }
    )
    summary = {
        "schema_version": 1,
        "artifact_type": "dicom-qa-human-review-sanitized-aggregate",
        "status": "complete" if block_count == 0 else "blocked",
        "completed_at_utc": ledger["completed_at_utc"],
        "versions": {
            "preprocessing": static_identity["preprocessing"]["version"],
            "source_manifest": static_identity["source_manifest"]["version"],
            "source_manifest_audit": static_identity["source_manifest"].get("audit_id"),
            "cohort_selection": static_identity["cohort_selection_version"],
            "review_protocol": REVIEW_PROTOCOL_VERSION,
        },
        "review": {
            "reviewed_studies": _count_token(len(reviewed_cases), public_cap=MAX_REVIEWED_STUDIES),
            "eligible_series_reviewed": _count_token(len(ledger["rows"])),
            "represented_strata": "all_material_covered",
            "all_eligible_series_complete": True,
            "all_nine_checks_terminal": True,
            "artifact_presence_verified": True,
            "review_identity_bound": True,
            "check_results": {
                check: "PASS" if decision_counts[check]["BLOCK"] == 0 else "BLOCK"
                for check in REVIEW_CHECKS
            },
            "block_decisions": _count_token(block_count),
            "zero_blocks": block_count == 0,
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
    summary_payload = _canonical_json_bytes(summary)
    validate_sanitized_summary(
        summary_payload,
        run_config=_json_object(run_config_payload, "run_config_invalid"),
        manifest=_json_object(manifest_payload, "bundle_manifest_invalid"),
    )
    performance_payload = _final_performance_report(
        run_a_payload=run_a_summary_payload,
        comparison_payload=comparison_summary_payload,
        review_payload=summary_payload,
        run_config=_json_object(run_config_payload, "run_config_invalid"),
        manifest=_json_object(manifest_payload, "bundle_manifest_invalid"),
        runner=runner,
    )
    return private_completion, summary_payload, performance_payload


def _write_new(path: Path, payload: bytes, maximum: int) -> None:
    if not payload or len(payload) > maximum:
        raise ReviewFinalizationError("output_size_invalid")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(payload)
        os.chmod(path, 0o600)
    except OSError as error:
        raise ReviewFinalizationError("output_write_failed") from error


def _self_hash() -> str:
    return _sha256_bytes(
        _read_bounded(Path(__file__).resolve(strict=True), 1024 * 1024, "self_invalid")
    )


def _inputs(args: argparse.Namespace) -> tuple[bytes, bytes, bytes, bytes]:
    return (
        _read_bounded(args.run_config, 2 * 1024**2, "run_config_invalid"),
        _read_bounded(args.bundle_manifest, 2 * 1024**2, "bundle_manifest_invalid"),
        _read_bounded(args.private_case_index, MAX_INPUT_BYTES, "private_case_index_invalid"),
        _read_bounded(
            args.private_artifact_inventory, MAX_INPUT_BYTES, "private_inventory_invalid"
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-config", type=Path, required=True)
    parser.add_argument("--bundle-manifest", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--private-case-index", type=Path, required=True)
    parser.add_argument("--private-artifact-inventory", type=Path, required=True)
    parser.add_argument("--private-review-root", type=Path, required=True)
    parser.add_argument("--run-a-sanitized-summary", type=Path)
    parser.add_argument("--comparison-summary", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--template-output", type=Path)
    mode.add_argument("--completed-review-ledger", type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser


def _discover_matches(root: Path, basename: str) -> tuple[Path, ...]:
    matches: list[Path] = []
    try:
        resolved = root.resolve(strict=True)
        for current, directories, files in os.walk(resolved, followlinks=False):
            current_path = Path(current)
            depth = len(current_path.relative_to(resolved).parts)
            directories[:] = [name for name in directories if name != "private-review"]
            if depth >= 4:
                directories[:] = []
            if len(directories) + len(files) > 4096:
                raise ReviewFinalizationError("input_discovery_invalid")
            if basename in files:
                candidate = current_path / basename
                if candidate.is_symlink() or not candidate.is_file():
                    raise ReviewFinalizationError("input_discovery_invalid")
                matches.append(candidate)
    except ReviewFinalizationError:
        raise
    except OSError as error:
        raise ReviewFinalizationError("input_discovery_invalid") from error
    return tuple(matches)


def _discover_one(root: Path, basename: str) -> Path:
    matches = _discover_matches(root, basename)
    if len(matches) != 1:
        raise ReviewFinalizationError("input_discovery_invalid")
    return matches[0]


def _discover_optional_one(root: Path, basename: str) -> Path | None:
    matches = _discover_matches(root, basename)
    if len(matches) > 1:
        raise ReviewFinalizationError("input_discovery_invalid")
    return matches[0] if matches else None


def _discover_from_kernel(root: Path, basename: str, kernel_ref: str) -> Path:
    slug = kernel_ref.partition("/")[2]
    matches = [path for path in _discover_matches(root, basename) if slug in path.parts]
    if len(matches) != 1:
        raise ReviewFinalizationError("input_discovery_invalid")
    return matches[0]


def _automatic_args() -> argparse.Namespace:
    input_root = Path(os.environ.get("KAGGLE_INPUT_ROOT", "/kaggle/input"))
    working_root = Path(os.environ.get("KAGGLE_WORKING_ROOT", "/kaggle/working"))
    manifest = _discover_one(input_root, "bundle-manifest.json")
    run_config = _discover_one(input_root, "run-config.json")
    runner = _discover_one(input_root, "qa_runner.py")
    if manifest.parent != run_config.parent or manifest.parent != runner.parent:
        raise ReviewFinalizationError("input_discovery_invalid")
    run_config_value = _json_object(
        _read_bounded(run_config, 2 * 1024**2, "run_config_invalid"), "run_config_invalid"
    )
    refs = _derived_refs(run_config_value)
    run_a_ref = refs["run_a"]
    case_index = _discover_from_kernel(input_root, "private_case_index.json", run_a_ref)
    private_inventory = _discover_from_kernel(
        input_root, "private_artifact_inventory.json", run_a_ref
    )
    if case_index.parent != private_inventory.parent:
        raise ReviewFinalizationError("input_discovery_invalid")
    private_review_root = case_index.parent / "private-review"
    if private_review_root.is_symlink() or not private_review_root.is_dir():
        raise ReviewFinalizationError("input_discovery_invalid")
    completed_review_ledger = _discover_optional_one(input_root, REVIEW_LEDGER_BASENAME)
    return argparse.Namespace(
        run_config=run_config,
        bundle_manifest=manifest,
        runner=runner,
        private_case_index=case_index,
        private_artifact_inventory=private_inventory,
        private_review_root=private_review_root,
        run_a_sanitized_summary=_discover_from_kernel(
            input_root, "sanitized_summary.json", run_a_ref
        ),
        comparison_summary=_discover_from_kernel(
            input_root, "sanitized_determinism.json", refs["comparison"]
        ),
        template_output=(
            None
            if completed_review_ledger is not None
            else working_root / TEMPLATE_OUTPUT_DIRECTORY / REVIEW_PLAN_BASENAME
        ),
        completed_review_ledger=completed_review_ledger,
        output_dir=working_root / OUTPUT_DIRECTORY if completed_review_ledger is not None else None,
    )


def main(argv: Sequence[str] | None = None) -> int:
    print('{"event":"dicom_qa_review_started"}', flush=True)
    staging: Path | None = None
    try:
        args = (
            _automatic_args() if argv is None and len(sys.argv) == 1 else _parser().parse_args(argv)
        )
        run_config, manifest, case_index, inventory = _inputs(args)
        finalizer_sha256 = _self_hash()
        if args.template_output is not None:
            if args.output_dir is not None:
                raise ReviewFinalizationError("arguments_invalid")
            payload = create_template(
                run_config_payload=run_config,
                manifest_payload=manifest,
                case_payload=case_index,
                inventory_payload=inventory,
                finalizer_sha256=finalizer_sha256,
                bundle_root=args.bundle_manifest.parent,
                run_config_path=args.run_config,
                runner_path=args.runner,
                private_review_root=args.private_review_root,
            )
            _write_new(args.template_output, payload, MAX_LEDGER_BYTES)
            print('{"event":"dicom_qa_review_template_complete"}', flush=True)
            return 0
        if (
            args.output_dir is None
            or args.completed_review_ledger is None
            or args.run_a_sanitized_summary is None
            or args.comparison_summary is None
            or args.output_dir.exists()
        ):
            raise ReviewFinalizationError("arguments_invalid")
        ledger = _read_bounded(
            args.completed_review_ledger, MAX_LEDGER_BYTES, "review_ledger_invalid"
        )
        private, summary, performance = finalize_review(
            run_config_payload=run_config,
            manifest_payload=manifest,
            case_payload=case_index,
            inventory_payload=inventory,
            ledger_payload=ledger,
            run_a_summary_payload=_read_bounded(
                args.run_a_sanitized_summary, MAX_SUMMARY_BYTES, "run_a_summary_invalid"
            ),
            comparison_summary_payload=_read_bounded(
                args.comparison_summary, MAX_SUMMARY_BYTES, "comparison_summary_invalid"
            ),
            finalizer_sha256=finalizer_sha256,
            bundle_root=args.bundle_manifest.parent,
            run_config_path=args.run_config,
            runner_path=args.runner,
            private_review_root=args.private_review_root,
        )
        staging = Path(tempfile.mkdtemp(prefix=".dicom-qa-review-", dir=args.output_dir.parent))
        _write_new(staging / PRIVATE_COMPLETION, private, MAX_LEDGER_BYTES)
        _write_new(staging / SANITIZED_SUMMARY, summary, MAX_SUMMARY_BYTES)
        _write_new(staging / SANITIZED_PERFORMANCE, performance, MAX_PERFORMANCE_BYTES)
        staging.rename(args.output_dir)
        staging = None
        print('{"event":"dicom_qa_review_complete"}', flush=True)
        return 0
    except ReviewFinalizationError as error:
        print(
            _canonical_json_bytes({"event": "dicom_qa_review_failed", "code": error.code})
            .decode("ascii")
            .rstrip(),
            flush=True,
        )
        return 2
    except BaseException:
        print('{"event":"dicom_qa_review_failed","code":"internal_error"}', flush=True)
        return 2
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
