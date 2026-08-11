"""Private interactive reviewer for the immutable Chunk 5 DICOM QA plan.

This module runs only in an interactive, private Kaggle notebook. It never prints identifiers,
paths, artifact hashes, or free text, and it writes the detailed ledger only under
``/kaggle/working``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

PLAN_BASENAME: Final = "private_review_plan.json"
LEDGER_BASENAME: Final = "completed_review_ledger.json"
MAX_PLAN_BYTES: Final = 32 * 1024**2
MAX_ARTIFACT_BYTES: Final = 32 * 1024**2
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
DECISION_CODES: Final = {"P": "PASS", "B": "BLOCK", "N": "NOT_APPLICABLE"}
NOT_APPLICABLE_CHECKS: Final = frozenset({"duplicate_missing_abnormal_handling"})
REVIEW_INSTRUCTIONS_VERSION: Final = "private-dicom-qa-review-instructions-v2"
HUMAN_ATTESTATION_STATEMENT: Final = (
    "I ATTEST THAT I AM AN AUTHORIZED HUMAN REVIEWER, I PERSONALLY INSPECTED EVERY "
    "DISPLAYED PRIVATE ARTIFACT, AND NO LLM OR BROWSER AUTOMATION VIEWED THE PRIVATE ARTIFACTS."
)
QA_STRATUM_REGISTRY_VERSION: Final = "qa-stratum-registry-v1"
QA_STRATUM_REGISTRY_SHA256: Final = (
    "13829b49acec7ed2a3cb83cc862caaf3"  # pragma: allowlist secret
    "251ecbab9f1b11eca4061c0c9ae5acf3"  # pragma: allowlist secret
)
QA_RENDERER_VERSION: Final = "private-qa-renderer-v1"
REVIEW_GUIDANCE: Final = (
    (
        "slice_order",
        "PASS only when physical slice progression is smooth, ordered, and unrepeated.",
    ),
    (
        "anatomical_orientation",
        "PASS only when anatomy agrees with the physical-plane and direction evidence.",
    ),
    (
        "laterality_preservation",
        "PASS only when every available source side marker or cue is unchanged in the processed "
        "view and bound provenance records no laterality-changing transform; unknown source "
        "laterality must remain unknown and must never be invented.",
    ),
    (
        "no_unintended_mirroring",
        "PASS only when source-to-processed comparison shows no unintended reflection.",
    ),
    (
        "intensity_polarity",
        "PASS only when source-to-processed tissue polarity is consistent and not inverted.",
    ),
    ("anatomy_not_clipped", "PASS only when the knee remains fully inside the processed field."),
    (
        "sequence_slot_assignment",
        "PASS only when plane, contrast, slot, siblings, missing mask, and reasons agree.",
    ),
    (
        "preprocessing_appearance",
        "PASS only when anatomy and contrast are preserved without banding, washout, nonfinite "
        "regions, or interpolation distortion.",
    ),
    (
        "duplicate_missing_abnormal_handling",
        "PASS only when duplicate, missing, blocked, or reasoned-series handling matches the "
        "displayed context.",
    ),
)
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
CHECK_9_REASON_ORDER: Final = (
    "missing_diagnostic_slot",
    "additional_or_duplicate_series",
    "non_model_eligible_sibling",
    "retention_reason",
    "quality_block_reason",
    "source_manifest_quality_flag",
    "recoverable_pipeline_case",
    "dicom_edge_case",
    "retained_nonduplicate_abnormal_series",
    "duplicate_handling",
)
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
KERNEL_REF = re.compile(r"[a-z0-9][a-z0-9_-]{0,49}/[a-z0-9][a-z0-9_-]{0,99}\Z")


class ReviewUIError(RuntimeError):
    """Fixed private-UI failure code."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _duplicate_missing_abnormal_applicable(context: dict[str, object]) -> bool:
    return context.get("check_9_applicable") is True


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def _read_json(path: Path, maximum: int) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise ReviewUIError("input_invalid")
    size = path.stat().st_size
    if not 0 < size <= maximum:
        raise ReviewUIError("input_invalid")
    payload = path.read_bytes()
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReviewUIError("input_invalid") from error
    if not isinstance(value, dict) or payload != _canonical_json_bytes(value):
        raise ReviewUIError("input_invalid")
    return payload, value


def _discover_one(root: Path, basename: str) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise ReviewUIError("input_invalid")
    matches = [
        path for path in root.glob(f"*/*/{basename}") if not path.is_symlink() and path.is_file()
    ]
    if len(matches) != 1:
        raise ReviewUIError("input_invalid")
    return matches[0]


def _review_plan_ref(identity: object) -> str:
    kernels = identity.get("kernels") if isinstance(identity, dict) else None
    review_plan = kernels.get("review_plan") if isinstance(kernels, dict) else None
    ref = review_plan.get("ref") if isinstance(review_plan, dict) else None
    if (
        not isinstance(review_plan, dict)
        or set(review_plan) != {"ref", "version"}
        or isinstance(review_plan.get("version"), bool)
        or review_plan.get("version") != 1
        or not isinstance(ref, str)
        or KERNEL_REF.fullmatch(ref) is None
    ):
        raise ReviewUIError("plan_invalid")
    return ref


def _validate_identity_bindings(identity: dict[str, Any], review_plan_ref: str) -> None:
    review_bundle_id = identity.get("review_bundle_id")
    identity_body = dict(identity)
    identity_body.pop("review_bundle_id", None)
    expected_bundle_id = (
        "c5qa-"
        + hashlib.sha256(
            _canonical_json_bytes(
                {"domain": "rsna-knee-private-review-bundle-v2", "identity": identity_body}
            )
        ).hexdigest()[:20]
    )
    preprocessing = identity.get("preprocessing")
    cohort = identity.get("qa_cohort")
    materialization = identity.get("qa_materialization")
    review_plan = materialization.get("review_plan") if isinstance(materialization, dict) else None
    registry = (
        materialization.get("stratum_registry") if isinstance(materialization, dict) else None
    )
    if (
        not isinstance(review_bundle_id, str)
        or review_bundle_id != expected_bundle_id
        or not isinstance(preprocessing, dict)
        or not isinstance(preprocessing.get("version"), str)
        or not preprocessing["version"]
        or not isinstance(cohort, dict)
        or not isinstance(cohort.get("sha256"), str)
        or HEX_64.fullmatch(str(cohort["sha256"])) is None
        or not isinstance(materialization, dict)
        or set(materialization)
        != {
            "run_a_full_manifest_sha256",
            "cohort_plan_sha256",
            "comparison_proof_sha256",
            "review_plan",
            "stratum_registry",
            "renderer_version",
            "capacity_certificate_sha256",
        }
        or any(
            not isinstance(materialization.get(key), str)
            or HEX_64.fullmatch(str(materialization[key])) is None
            for key in (
                "run_a_full_manifest_sha256",
                "cohort_plan_sha256",
                "comparison_proof_sha256",
                "capacity_certificate_sha256",
            )
        )
        or review_plan != {"ref": review_plan_ref, "version": 1}
        or registry
        != {
            "version": QA_STRATUM_REGISTRY_VERSION,
            "sha256": QA_STRATUM_REGISTRY_SHA256,
        }
        or materialization.get("renderer_version") != QA_RENDERER_VERSION
    ):
        raise ReviewUIError("plan_invalid")


def _review_plan_artifact_root(root: Path, review_plan_ref: str) -> Path:
    slug = review_plan_ref.partition("/")[2]
    try:
        if root.is_symlink() or not root.is_dir():
            raise ReviewUIError("artifact_invalid")
        matches: list[Path] = []
        for candidate in root.glob("*/*/private-review"):
            relative = candidate.relative_to(root)
            if relative.parts[0] != slug:
                continue
            ancestors = [root.joinpath(*relative.parts[:depth]) for depth in range(1, 4)]
            if any(path.is_symlink() or not path.is_dir() for path in ancestors):
                raise ReviewUIError("artifact_invalid")
            matches.append(candidate)
    except OSError as error:
        raise ReviewUIError("artifact_invalid") from error
    if len(matches) != 1:
        raise ReviewUIError("artifact_invalid")
    return matches[0]


def _artifact(root: Path, name: str, expected_sha256: str) -> Path:
    if (
        not re.fullmatch(r"case_[0-9]{6}_series_[0-9]{3}_[a-z_]+\.(?:png|gif|json)", name)
        or HEX_64.fullmatch(expected_sha256) is None
    ):
        raise ReviewUIError("artifact_invalid")
    path = root / name
    try:
        if (
            root.is_symlink()
            or not root.is_dir()
            or path.is_symlink()
            or not path.is_file()
            or not 0 < path.stat().st_size <= MAX_ARTIFACT_BYTES
        ):
            raise ReviewUIError("artifact_invalid")
        payload = path.read_bytes()
    except OSError as error:
        raise ReviewUIError("artifact_invalid") from error
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ReviewUIError("artifact_invalid")
    return path


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
        "laterality",
        "laterality_transform",
        "horizontal_flip_applied",
        "assigned_slot",
        "retention_reasons",
        "missing_series_mask",
        "sibling_series",
        "check_9_applicable",
        "check_9_reason_codes",
    }:
        raise ReviewUIError("plan_invalid")
    assigned_slot = value.get("assigned_slot")
    retention_reasons = _fixed_enum_list(value.get("retention_reasons"), RETENTION_REASON_ORDER)
    check_9_reasons = _fixed_enum_list(value.get("check_9_reason_codes"), CHECK_9_REASON_ORDER)
    missing_mask = value.get("missing_series_mask")
    siblings = value.get("sibling_series")
    if (
        value.get("organizer_plane") not in ORGANIZER_PLANES
        or value.get("physical_plane") not in PHYSICAL_PLANES
        or value.get("laterality") not in {"left", "right", "bilateral", "unknown"}
        or value.get("laterality_transform") != "none"
        or value.get("horizontal_flip_applied") is not False
        or assigned_slot not in SERIES_SLOTS
        or retention_reasons is None
        or check_9_reasons is None
        or value.get("check_9_applicable") is not bool(check_9_reasons)
        or not isinstance(missing_mask, list)
        or len(missing_mask) != len(PRIMARY_SERIES_SLOTS)
        or any(not isinstance(item, bool) for item in missing_mask)
        or (
            assigned_slot in PRIMARY_SERIES_SLOTS
            and missing_mask[PRIMARY_SERIES_SLOTS.index(cast(str, assigned_slot))]
        )
        or not isinstance(siblings, list)
        or not 1 <= len(siblings) <= 1_000
        or not 0 <= series_ordinal < len(siblings)
    ):
        raise ReviewUIError("plan_invalid")
    for expected_ordinal, sibling in enumerate(siblings):
        if not isinstance(sibling, dict) or set(sibling) != {
            "series_ordinal",
            "slot",
            "terminal_state",
            "model_eligible",
            "retention_reasons",
            "quality_blocked_reasons",
        }:
            raise ReviewUIError("plan_invalid")
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
            raise ReviewUIError("plan_invalid")
    current = cast(dict[str, object], siblings[series_ordinal])
    if (
        current.get("terminal_state") != "model_eligible"
        or current.get("model_eligible") is not True
        or current.get("slot") != assigned_slot
        or current.get("retention_reasons") != retention_reasons
    ):
        raise ReviewUIError("plan_invalid")
    required_reasons = {
        *(("missing_diagnostic_slot",) if any(cast(list[bool], missing_mask)) else ()),
        *(
            ("additional_or_duplicate_series",)
            if any(item["slot"] == "additional_or_duplicate" for item in siblings)
            else ()
        ),
        *(
            ("non_model_eligible_sibling",)
            if any(item["model_eligible"] is False for item in siblings)
            else ()
        ),
        *(
            ("retention_reason",)
            if any(bool(item["retention_reasons"]) for item in siblings)
            else ()
        ),
        *(
            ("quality_block_reason",)
            if any(bool(item["quality_blocked_reasons"]) for item in siblings)
            else ()
        ),
    }
    if not required_reasons.issubset(check_9_reasons):
        raise ReviewUIError("plan_invalid")
    return cast(dict[str, object], value)


def _validate_plan(value: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    identity = value.get("review_identity")
    rows = value.get("rows")
    if (
        set(value)
        != {
            "schema_version",
            "artifact_type",
            "status",
            "review_identity",
            "rows",
        }
        or value.get("schema_version") != 2
        or value.get("artifact_type") != "private-dicom-qa-review-plan"
        or value.get("status") != "pending_private_human_review"
        or not isinstance(identity, dict)
        or not isinstance(identity.get("review_bundle_id"), str)
        or not isinstance(identity.get("preprocessing"), dict)
        or not isinstance(identity.get("qa_cohort"), dict)
        or not isinstance(rows, list)
        or not rows
    ):
        raise ReviewUIError("plan_invalid")
    review_plan_ref = _review_plan_ref(identity)
    _validate_identity_bindings(identity, review_plan_ref)
    observed: set[tuple[int, int]] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "case_ordinal",
            "series_ordinal",
            "review_context",
            "decisions",
            "artifacts",
        }:
            raise ReviewUIError("plan_invalid")
        key = (row.get("case_ordinal"), row.get("series_ordinal"))
        if (
            any(isinstance(item, bool) or not isinstance(item, int) for item in key)
            or key in observed
            or row.get("decisions") != {check: "not_reviewed" for check in REVIEW_CHECKS}
            or not isinstance(row.get("series_ordinal"), int)
            or not isinstance(row.get("artifacts"), list)
            or not row["artifacts"]
        ):
            raise ReviewUIError("plan_invalid")
        _validate_review_context(row["review_context"], row["series_ordinal"])
        observed.add(cast(tuple[int, int], key))
        for artifact in row["artifacts"]:
            if (
                not isinstance(artifact, dict)
                or set(artifact) != {"name", "sha256"}
                or not isinstance(artifact.get("name"), str)
                or not isinstance(artifact.get("sha256"), str)
            ):
                raise ReviewUIError("plan_invalid")
    return rows, review_plan_ref


def _new_ledger(plan: dict[str, Any], plan_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "artifact_type": "private-dicom-qa-completed-review-ledger",
        "status": "in_progress",
        "review_identity": plan["review_identity"],
        "plan_sha256": plan_sha256,
        "started_at_utc": _utc_now(),
        "completed_at_utc": None,
        "human_attestation": None,
        "rows": [
            {
                "case_ordinal": row["case_ordinal"],
                "series_ordinal": row["series_ordinal"],
                "artifact_hashes_verified": False,
                "decisions": {check: "not_reviewed" for check in REVIEW_CHECKS},
            }
            for row in plan["rows"]
        ],
    }


def _validate_resume(ledger: dict[str, Any], plan: dict[str, Any], plan_sha256: str) -> None:
    expected = _new_ledger(plan, plan_sha256)
    if (
        set(ledger) != set(expected)
        or ledger.get("schema_version") != 2
        or ledger.get("artifact_type") != expected["artifact_type"]
        or ledger.get("review_identity") != expected["review_identity"]
        or ledger.get("plan_sha256") != plan_sha256
        or ledger.get("status") not in {"in_progress", "complete"}
        or not isinstance(ledger.get("rows"), list)
        or len(ledger["rows"]) != len(expected["rows"])
    ):
        raise ReviewUIError("resume_invalid")
    for row, expected_row, plan_row in zip(
        ledger["rows"], expected["rows"], plan["rows"], strict=True
    ):
        context = plan_row.get("review_context") if isinstance(plan_row, dict) else None
        if (
            not isinstance(row, dict)
            or set(row) != set(expected_row)
            or row.get("case_ordinal") != expected_row["case_ordinal"]
            or row.get("series_ordinal") != expected_row["series_ordinal"]
            or not isinstance(row.get("artifact_hashes_verified"), bool)
            or not isinstance(context, dict)
            or not isinstance(row.get("decisions"), dict)
            or set(row["decisions"]) != set(REVIEW_CHECKS)
            or any(
                value not in {*DECISION_CODES.values(), "not_reviewed"}
                for value in row["decisions"].values()
            )
            or any(
                value == "NOT_APPLICABLE"
                and (
                    check not in NOT_APPLICABLE_CHECKS
                    or _duplicate_missing_abnormal_applicable(context)
                )
                for check, value in row["decisions"].items()
            )
            or (
                any(value != "not_reviewed" for value in row["decisions"].values())
                and (
                    not row["artifact_hashes_verified"]
                    or any(value == "not_reviewed" for value in row["decisions"].values())
                )
            )
        ):
            raise ReviewUIError("resume_invalid")
    rows_complete = all(
        all(value != "not_reviewed" for value in row["decisions"].values())
        for row in ledger["rows"]
    )
    complete = ledger.get("status") == "complete"
    started_at = _utc_timestamp(ledger.get("started_at_utc"))
    completed_at = _utc_timestamp(ledger.get("completed_at_utc"))
    attestation = ledger.get("human_attestation")
    now = datetime.now(UTC)
    if (
        (complete and not rows_complete)
        or started_at is None
        or started_at > now
        or (complete and (completed_at is None or not started_at <= completed_at <= now))
        or (not complete and ledger.get("completed_at_utc") is not None)
        or (not complete and attestation is not None)
        or (
            complete
            and (
                not isinstance(attestation, dict)
                or set(attestation)
                != {
                    "schema_version",
                    "instructions_version",
                    "statement",
                    "authorized_human_reviewer",
                    "direct_visual_review",
                    "no_llm_or_browser_automation_pixel_access",
                    "attested_at_utc",
                }
                or attestation.get("schema_version") != 1
                or attestation.get("instructions_version") != REVIEW_INSTRUCTIONS_VERSION
                or attestation.get("statement") != HUMAN_ATTESTATION_STATEMENT
                or attestation.get("authorized_human_reviewer") is not True
                or attestation.get("direct_visual_review") is not True
                or attestation.get("no_llm_or_browser_automation_pixel_access") is not True
                or _utc_timestamp(attestation.get("attested_at_utc")) != completed_at
            )
        )
    ):
        raise ReviewUIError("resume_invalid")


def _checkpoint(path: Path, value: dict[str, Any]) -> None:
    payload = _canonical_json_bytes(value)
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


def _show(context: dict[str, object], paths: list[Path]) -> None:
    try:
        from IPython.display import JSON, Image, display  # type: ignore[import-not-found]
    except ImportError as error:  # pragma: no cover - Kaggle/IPython runtime boundary
        raise ReviewUIError("ipython_unavailable") from error
    display(JSON(context))
    for path in paths:
        if path.suffix in {".png", ".gif"}:
            display(Image(filename=str(path)))
        elif path.name.endswith(("review.json", "metadata.json")):
            _payload, value = _read_json(path, MAX_ARTIFACT_BYTES)
            display(JSON(value))


def run_review(
    *,
    input_root: Path = Path("/kaggle/input"),
    working_root: Path = Path("/kaggle/working"),
) -> Path | None:
    """Run or resume the fixed nine-decision private review."""

    print(
        "HUMAN_ONLY_BOUNDARY=Stop all LLM/browser automation, screenshots, screen sharing, "
        "and accessibility inspection before typing START."
    )
    try:
        if input("Type START to begin the private review: ").strip() != "START":
            print("INTERACTIVE_REVIEW_REQUIRED")
            return None
    except EOFError:
        print("INTERACTIVE_REVIEW_REQUIRED")
        return None
    print(
        "DECISIONS=PASS requires positive evidence; BLOCK covers defects, missing evidence, "
        "ambiguity, or doubt."
    )
    print("NOT_APPLICABLE=Only check 9, and only when its displayed context is clean.")
    print(f"INSTRUCTIONS_VERSION={REVIEW_INSTRUCTIONS_VERSION}")
    for index, (check, guidance) in enumerate(REVIEW_GUIDANCE, start=1):
        print(f"CHECK_{index}={check}: {guidance}")
    plan_payload, plan = _read_json(_discover_one(input_root, PLAN_BASENAME), MAX_PLAN_BYTES)
    plan_rows, review_plan_ref = _validate_plan(plan)
    artifact_root = _review_plan_artifact_root(input_root, review_plan_ref)
    plan_sha256 = hashlib.sha256(plan_payload).hexdigest()
    ledger_path = working_root / LEDGER_BASENAME
    if ledger_path.exists():
        _payload, ledger = _read_json(ledger_path, MAX_PLAN_BYTES)
        _validate_resume(ledger, plan, plan_sha256)
        if ledger["status"] == "complete":
            print("PRIVATE_REVIEW_ALREADY_COMPLETE")
            return ledger_path
    else:
        ledger = _new_ledger(plan, plan_sha256)
        _checkpoint(ledger_path, ledger)

    identity = plan["review_identity"]
    print(f"REVIEW_BUNDLE_ID={identity['review_bundle_id']}")
    print(f"PREPROCESSING_VERSION={identity['preprocessing']['version']}")
    print(f"QA_COHORT_HASH={identity['qa_cohort']['sha256']}")
    for ordinal, (plan_row, ledger_row) in enumerate(
        zip(plan_rows, ledger["rows"], strict=True), start=1
    ):
        if all(value != "not_reviewed" for value in ledger_row["decisions"].values()):
            continue
        artifacts = [
            _artifact(artifact_root, artifact["name"], artifact["sha256"])
            for artifact in plan_row["artifacts"]
        ]
        print(f"REVIEW_ROW={ordinal}/{len(plan_rows)}")
        applicable = _duplicate_missing_abnormal_applicable(plan_row["review_context"])
        print(f"CHECK_9_APPLICABLE={'YES' if applicable else 'NO'}")
        _show(plan_row["review_context"], artifacts)
        while True:
            vector = input("Nine decisions (P=PASS, B=BLOCK, N=NOT_APPLICABLE): ").strip().upper()
            if (
                len(vector) == len(REVIEW_CHECKS)
                and set(vector) <= set(DECISION_CODES)
                and all(
                    code != "N" or (check in NOT_APPLICABLE_CHECKS and not applicable)
                    for check, code in zip(REVIEW_CHECKS, vector, strict=True)
                )
            ):
                break
            print("INVALID_DECISION_VECTOR")
        ledger_row["artifact_hashes_verified"] = True
        ledger_row["decisions"] = {
            check: DECISION_CODES[code] for check, code in zip(REVIEW_CHECKS, vector, strict=True)
        }
        _checkpoint(ledger_path, ledger)

    try:
        if input(f"Type exactly this attestation:\n{HUMAN_ATTESTATION_STATEMENT}\n").strip() != (
            HUMAN_ATTESTATION_STATEMENT
        ):
            print("HUMAN_ATTESTATION_REQUIRED")
            return ledger_path
    except EOFError:
        print("HUMAN_ATTESTATION_REQUIRED")
        return ledger_path
    completed_at = _utc_now()
    ledger["status"] = "complete"
    ledger["completed_at_utc"] = completed_at
    ledger["human_attestation"] = {
        "schema_version": 1,
        "instructions_version": REVIEW_INSTRUCTIONS_VERSION,
        "statement": HUMAN_ATTESTATION_STATEMENT,
        "authorized_human_reviewer": True,
        "direct_visual_review": True,
        "no_llm_or_browser_automation_pixel_access": True,
        "attested_at_utc": completed_at,
    }
    _checkpoint(ledger_path, ledger)
    print("PRIVATE_REVIEW_COMPLETE")
    return ledger_path


if __name__ == "__main__":  # pragma: no cover - interactive notebook entry point
    run_review()
