#!/usr/bin/env python3
"""Authenticate the one private r16 on-demand notebook without retrieving private artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import validate_dicom_qa_output as base

HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
REF = re.compile(r"[a-z0-9][a-z0-9_-]{0,49}/[a-z0-9][a-z0-9_-]{0,49}\Z")
COMPETITION_SLUG: Final = "rsna-knee-abnormality-detection"
NOTEBOOK_FILE: Final = "on_demand_review.ipynb"
REGISTRY_VERSION: Final = "qa-stratum-registry-v1"
REGISTRY_SHA256: Final = (
    "13829b49acec7ed2a3cb83cc862caaf3"  # pragma: allowlist secret
    "251ecbab9f1b11eca4061c0c9ae5acf3"  # pragma: allowlist secret
)
EXPECTED_OUTPUTS: Final = {
    "private_on_demand_plan.json",
    "private_coverage_ledger.json",
    "sanitized_readiness.json",
}


class OnDemandValidationError(RuntimeError):
    """Fixed validation failure."""


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii")


def assert_kernel_absent(ref: str) -> None:
    """Require that no current owned kernel has the exact fresh ref."""

    if REF.fullmatch(ref) is None:
        raise OnDemandValidationError("kernel_ref_invalid")
    slug = ref.partition("/")[2]
    payload = base._run_kaggle_cli(
        ("kernels", "list", "--mine", "--search", slug, "--csv"),
        maximum=2 * 1024**2,
    )
    try:
        rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8"))))
    except (UnicodeError, csv.Error) as error:
        raise OnDemandValidationError("kernel_absence_check_invalid") from error
    normalized = {
        str(row.get("ref", row.get("Ref", row.get("id", row.get("Id", ""))))).strip()
        for row in rows
    }
    if ref in normalized:
        raise OnDemandValidationError("kernel_ref_already_exists")


def validate_readiness(
    payload: bytes, *, source_sha256: str, selector_sha256: str
) -> Mapping[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise OnDemandValidationError("readiness_invalid") from error
    expected_keys = {
        "schema_version",
        "artifact_type",
        "status",
        "review_bundle_id",
        "preprocessing_version",
        "cohort_hash",
        "selector_version",
        "selector_sha256",
        "registry_version",
        "registry_sha256",
        "notebook_source_sha256",
        "total_studies",
        "total_eligible_series",
        "minimum_studies",
        "minimum_is_not_maximum",
        "represented_value_quota",
        "singletons_mandatory",
        "all_represented_registry_values_covered",
        "human_review_status",
        "submission_approved",
        "clinical_use",
    }
    if (
        not isinstance(value, dict)
        or payload != _canonical_json_bytes(value)
        or set(value) != expected_keys
        or value.get("schema_version") != 1
        or value.get("artifact_type") != "dicom-qa-on-demand-readiness"
        or value.get("status") != "human_review_ready"
        or HEX_64.fullmatch(str(value.get("review_bundle_id"))) is None
        or value.get("preprocessing_version") != "dicom-model-v1"
        or HEX_64.fullmatch(str(value.get("cohort_hash"))) is None
        or value.get("selector_version") != "qa-cohort-selection-v3"
        or value.get("selector_sha256") != selector_sha256
        or value.get("registry_version") != REGISTRY_VERSION
        or value.get("registry_sha256") != REGISTRY_SHA256
        or value.get("notebook_source_sha256") != source_sha256
        or type(value.get("total_studies")) is not int
        or value["total_studies"] < 100
        or type(value.get("total_eligible_series")) is not int
        or value["total_eligible_series"] < 100
        or value.get("minimum_studies") != 100
        or value.get("minimum_is_not_maximum") is not True
        or value.get("represented_value_quota") != 2
        or value.get("singletons_mandatory") is not True
        or value.get("all_represented_registry_values_covered") is not True
        or value.get("human_review_status") != "not_started"
        or value.get("submission_approved") is not False
        or value.get("clinical_use") != "prohibited"
    ):
        raise OnDemandValidationError("readiness_invalid")
    return value


def _validate_listing(ref: str) -> None:
    records = base._kernel_listing_records(base._authenticated_listing(ref, 1))
    observed: set[str] = set()
    logs = 0
    for record, _size in records:
        name = base._safe_remote_name(record.get("name"))
        if "/" not in name and base.SAFE_LOG_PATTERN.fullmatch(name):
            logs += 1
            continue
        if name in observed or name not in EXPECTED_OUTPUTS:
            raise OnDemandValidationError("remote_output_invalid")
        observed.add(name)
    if observed != EXPECTED_OUTPUTS or logs > 1:
        raise OnDemandValidationError("remote_output_invalid")


def _retrieve_readiness(ref: str, *, source_sha256: str, selector_sha256: str) -> Mapping[str, Any]:
    with tempfile.TemporaryDirectory(prefix="rsna-knee-on-demand-readiness-") as temporary:
        root = Path(temporary)
        base._run_kaggle_cli(
            (
                "kernels",
                "output",
                ref,
                "--path",
                str(root),
                "--file-pattern",
                r"^sanitized_readiness\.json$",
                "--quiet",
            ),
            maximum=64 * 1024,
            allow_empty=True,
        )
        try:
            entries = list(root.iterdir())
        except OSError as error:
            raise OnDemandValidationError("readiness_retrieval_invalid") from error
        path = root / "sanitized_readiness.json"
        if (
            len(entries) != 1
            or entries[0] != path
            or path.is_symlink()
            or not path.is_file()
            or not 0 < path.stat().st_size <= 256 * 1024
        ):
            raise OnDemandValidationError("readiness_retrieval_invalid")
        return validate_readiness(
            path.read_bytes(),
            source_sha256=source_sha256,
            selector_sha256=selector_sha256,
        )


def validate_remote(
    *,
    ref: str,
    notebook_path: Path,
    bundle_ref: str,
    source_ref: str,
    source_sha256: str,
    selector_sha256: str,
) -> Mapping[str, Any]:
    if (
        REF.fullmatch(ref) is None
        or base._validated_dataset_ref(bundle_ref) is None
        or REF.fullmatch(source_ref) is None
        or HEX_64.fullmatch(source_sha256) is None
        or HEX_64.fullmatch(selector_sha256) is None
        or notebook_path.is_symlink()
        or not notebook_path.is_file()
    ):
        raise OnDemandValidationError("argument_invalid")
    notebook_sha256 = hashlib.sha256(notebook_path.read_bytes()).hexdigest()
    base._authenticate_kernel_api_version(ref, 1)
    base._assert_version_absent(ref, 2)
    base._pull_and_verify_exact_kernel(
        ref,
        1,
        NOTEBOOK_FILE,
        notebook_sha256,
        expected_kernel_type="notebook",
        expected_dataset_sources=(bundle_ref,),
        expected_kernel_sources=(source_ref,),
        expected_competition_sources=(COMPETITION_SLUG,),
        normalize_notebook_json=True,
    )
    base._kernel_status_complete(ref)
    _validate_listing(ref)
    return _retrieve_readiness(ref, source_sha256=source_sha256, selector_sha256=selector_sha256)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", required=True)
    parser.add_argument("--notebook", type=Path)
    parser.add_argument("--bundle-ref")
    parser.add_argument("--source-ref")
    parser.add_argument("--source-sha256")
    parser.add_argument("--selector-sha256")
    parser.add_argument("--expect-absent", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.expect_absent:
            assert_kernel_absent(args.ref)
            print("on_demand_kernel_absent=PASS")
            return 0
        if any(
            value is None
            for value in (
                args.notebook,
                args.bundle_ref,
                args.source_ref,
                args.source_sha256,
                args.selector_sha256,
            )
        ):
            raise OnDemandValidationError("argument_invalid")
        readiness = validate_remote(
            ref=args.ref,
            notebook_path=args.notebook.resolve(strict=True),
            bundle_ref=args.bundle_ref,
            source_ref=args.source_ref,
            source_sha256=args.source_sha256,
            selector_sha256=args.selector_sha256,
        )
    except (OnDemandValidationError, base.OutputValidationError, OSError) as error:
        print(f"on_demand_remote=FAIL code={error}")
        return 2
    print("on_demand_remote=PASS")
    print(f"review_bundle_id={readiness['review_bundle_id']}")
    print(f"cohort_hash={readiness['cohort_hash']}")
    print("human_review_status=NOT_STARTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
