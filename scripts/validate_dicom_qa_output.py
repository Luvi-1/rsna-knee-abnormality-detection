"""Authenticate and validate private Chunk 5 Kaggle outputs without persisting case listings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, Final, cast

MAX_POLICY_BYTES: Final = 2 * 1024 * 1024
MAX_REMOTE_RECORDS: Final = 20_100
MAX_KERNEL_LISTING_SIZE: Final = (1 << 63) - 1
MAX_DATASET_CONTENT_FILES: Final = 512
MAX_DATASET_CONTENT_BYTES: Final = 128 * 1024 * 1024
MAX_DATASET_CONTENT_SECONDS: Final = 900.0
DATASET_CONTENT_CHUNK_BYTES: Final = 1024 * 1024
HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
FAILURE_PHASES: Final = {"bundle", "selection", "processing", "output"}
PERFORMANCE_SMOKE_FAILURE_PHASES: Final = {
    "bundle",
    "authentication",
    "performance_smoke",
    "output",
}
DATASET_VERSION: Final = 1
DATASET_PAGE_SIZE: Final = 200
KAGGLE_CLI_VERSION: Final = "Kaggle CLI 2.2.4"
SOURCE_MANIFEST_AUDIT_ID: Final = "audit-0003-wheel-sanitization"
SOURCE_MANIFEST_VERSION: Final = "manifest-v2"
SOURCE_MANIFEST_DOWNLOADABLE_OUTPUTS: Final = {
    "audit-output/sanitized_summary.json": 1024**2,
    "audit-output/data_audit.md": 512 * 1024,
    "audit-output/leakage_audit.md": 512 * 1024,
    "audit-output/domain_shift_audit.md": 512 * 1024,
    "audit-output/sanitized_artifact_inventory.json": 128 * 1024,
}
STAGE_SLUG_PREFIXES: Final = {
    "performance_smoke": "rsna-knee-dqa-smoke",
    "run_a": "rsna-knee-dqa-a",
    "run_b": "rsna-knee-dqa-b",
    "comparator": "rsna-knee-dqa-cmp",
    "plan": "rsna-knee-dqa-plan",
    "review_ui": "rsna-knee-dqa-ui",
    "review_session": "rsna-knee-dqa-review",
    "finalizer": "rsna-knee-dqa-final",
}
WORKFLOW_STAGES: Final = (
    "inputs",
    "performance-smoke",
    "run-a",
    "run-b",
    "comparison",
    "plan",
    "ui",
    "review",
    "final",
)
PERFORMANCE_SMOKE_OUTPUT_DIRECTORY: Final = "dicom-qa-performance-smoke"
PERFORMANCE_SMOKE_SUMMARY: Final = "sanitized_performance_smoke.json"
PERFORMANCE_SMOKE_SUMMARY_MAX_BYTES: Final = 16 * 1024
PERFORMANCE_SMOKE_SELF_DEADLINE_SECONDS: Final = 3_600
POST_COMPARISON_PREPARATION_CEILING_SECONDS: Final = 3_600
PERFORMANCE_SMOKE_PROJECTION_QUANTUM_SECONDS: Final = 60
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
REVIEW_SESSION_LEDGER: Final = "completed_review_ledger.json"
REVIEW_SESSION_MAX_LEDGER_BYTES: Final = 32 * 1024**2
SAFE_LOG_PATTERN: Final = re.compile(r"[a-z0-9][a-z0-9_-]{0,49}\.log\Z")
COMPLETION_TIMESTAMP_PATTERN: Final = re.compile(
    r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z"
)

_KERNEL_API_METADATA_PROBE: Final = r"""
import contextlib
import io
import json
import sys

result = {"error": "metadata"}
try:
    raw = sys.stdin.buffer.read(65537)
    if not raw or len(raw) > 65536:
        raise ValueError("request")
    request_payload = json.loads(raw)
    if set(request_payload) != {"owner", "slug"}:
        raise ValueError("request")
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        from kaggle.api.kaggle_api_extended import KaggleApi
        from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest

        api = KaggleApi()
        api.authenticate()
        with api.build_kaggle_client() as client:
            request = ApiGetKernelRequest()
            request.user_name = request_payload["owner"]
            request.kernel_slug = request_payload["slug"]
            response = client.kernels.kernels_api_client.get_kernel(request)
    if response.metadata is None:
        raise ValueError("metadata")
    metadata = response.metadata.to_dict()
    if not isinstance(metadata, dict):
        raise ValueError("metadata")
    result = {
        "current_version_number": metadata.get("currentVersionNumber"),
        "enable_internet": metadata.get("enableInternet"),
        "is_private": metadata.get("isPrivate"),
        "ref": metadata.get("ref"),
        "slug": metadata.get("slug"),
        "title": metadata.get("title"),
    }
except BaseException:
    pass
sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
sys.stdout.flush()
"""

_REVIEW_SESSION_METADATA_PROBE: Final = r"""
import contextlib
import io
import json
import sys

result = "review_session_metadata=FAIL\n"
try:
    raw = sys.stdin.buffer.read(65537)
    if not raw or len(raw) > 65536:
        raise ValueError("request")
    request = json.loads(raw)
    if set(request) != {
        "ref", "parent_ref", "owner", "slug", "dataset_sources",
        "kernel_sources", "competition_sources", "model_sources"
    }:
        raise ValueError("request")
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        from kaggle.api.kaggle_api_extended import KaggleApi

        api = KaggleApi()
        api.authenticate()
        response = api.kernels_list_with_response(
            page_size=100,
            search=request["slug"],
            mine=True,
            parent_kernel=request["parent_ref"],
            kernel_type="notebook",
            sort_by="relevance",
        )
    kernels = list(response.kernels or [])
    if response.next_page_token or len(kernels) != 1:
        raise ValueError("result")
    item = kernels[0]
    expected = {
        "ref": request["ref"],
        "title": request["slug"],
        "author": request["owner"],
        "slug": request["slug"],
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": False,
        "enable_tpu": False,
        "enable_internet": False,
        "current_version_number": 1,
        "dataset_data_sources": request["dataset_sources"],
        "kernel_data_sources": request["kernel_sources"],
        "competition_data_sources": request["competition_sources"],
        "model_data_sources": request["model_sources"],
    }
    observed = {key: getattr(item, key, None) for key in expected}
    if observed != expected:
        raise ValueError("metadata")
    result = "review_session_metadata=PASS\n"
except BaseException:
    pass
sys.stdout.write(result)
sys.stdout.flush()
raise SystemExit(0 if result.endswith("PASS\n") else 2)
"""


class OutputValidationError(RuntimeError):
    """A fixed validation error that never includes inspected content."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _read_bounded(path: Path, maximum: int, code: str) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise OutputValidationError(code)
        size = path.stat().st_size
        if not 0 < size <= maximum:
            raise OutputValidationError(code)
        with path.open("rb") as stream:
            payload = stream.read(maximum + 1)
    except OutputValidationError:
        raise
    except OSError as error:
        raise OutputValidationError(code) from error
    if len(payload) != size:
        raise OutputValidationError(code)
    return payload


def _json_object(path: Path, maximum: int, code: str) -> dict[str, Any]:
    raw = _read_bounded(path, maximum, code)
    value = _json_bytes(raw, code)
    if raw != _canonical_json_bytes(value):
        raise OutputValidationError(code)
    return value


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


def _json_value(payload: bytes, code: str) -> Any:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    try:
        return json.loads(payload, object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise OutputValidationError(code) from error


def _json_bytes(payload: bytes, code: str) -> dict[str, Any]:
    value = _json_value(payload, code)
    if not isinstance(value, dict):
        raise OutputValidationError(code)
    return value


def _runner_module(expected_sha256: str, runner_path: Path | None = None) -> ModuleType:
    if not HEX_64.fullmatch(expected_sha256):
        raise OutputValidationError("trusted_runner_unavailable")
    path = runner_path or Path(__file__).parents[1] / "kaggle" / "dicom_qa" / "run.py"
    payload = _read_bounded(path, 1024 * 1024, "trusted_runner_unavailable")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise OutputValidationError("trusted_runner_hash_mismatch")
    module = ModuleType("_trusted_dicom_qa_runner")
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    try:
        exec(compile(payload, str(path), "exec"), module.__dict__)
    except Exception as error:
        sys.modules.pop(module.__name__, None)
        raise OutputValidationError("trusted_runner_unavailable") from error
    return module


def _finalizer_module(expected_sha256: str, path: Path | None = None) -> ModuleType:
    if not HEX_64.fullmatch(expected_sha256):
        raise OutputValidationError("trusted_finalizer_unavailable")
    source = path or Path(__file__).parents[1] / "kaggle" / "dicom_qa" / "finalize_review.py"
    payload = _read_bounded(source, 1024 * 1024, "trusted_finalizer_unavailable")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise OutputValidationError("trusted_finalizer_hash_mismatch")
    module = ModuleType("_trusted_dicom_qa_review_finalizer")
    module.__file__ = str(source)
    sys.modules[module.__name__] = module
    try:
        exec(compile(payload, str(source), "exec"), module.__dict__)
    except Exception as error:
        sys.modules.pop(module.__name__, None)
        raise OutputValidationError("trusted_finalizer_unavailable") from error
    return module


def _comparison_module(expected_sha256: str, path: Path | None = None) -> ModuleType:
    if not HEX_64.fullmatch(expected_sha256):
        raise OutputValidationError("trusted_comparator_unavailable")
    source = path or Path(__file__).parents[1] / "kaggle" / "dicom_qa" / "compare_runs.py"
    payload = _read_bounded(source, 1024 * 1024, "trusted_comparator_unavailable")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise OutputValidationError("trusted_comparator_hash_mismatch")
    module = ModuleType("_trusted_dicom_qa_run_comparator")
    module.__file__ = str(source)
    sys.modules[module.__name__] = module
    try:
        exec(compile(payload, str(source), "exec"), module.__dict__)
    except Exception as error:
        sys.modules.pop(module.__name__, None)
        raise OutputValidationError("trusted_comparator_unavailable") from error
    return module


def load_verified_policy(
    run_config_path: Path,
    bundle_manifest_path: Path,
    *,
    expected_commit: str,
    expected_bundle: str,
    runner_path: Path | None = None,
) -> tuple[dict[str, Any], ModuleType, dict[str, Any]]:
    if not HEX_40.fullmatch(expected_commit):
        raise OutputValidationError("expected_commit_invalid")
    if not HEX_64.fullmatch(expected_bundle):
        raise OutputValidationError("expected_bundle_invalid")
    manifest = _json_object(bundle_manifest_path, MAX_POLICY_BYTES, "bundle_manifest_invalid")
    kernel = manifest.get("kernel")
    if (
        not isinstance(kernel, dict)
        or kernel.get("code_file") != "run.py"
        or not isinstance(kernel.get("sha256"), str)
    ):
        raise OutputValidationError("bundle_manifest_invalid")
    runner = _runner_module(str(kernel["sha256"]), runner_path)
    requested_config = _json_object(run_config_path, MAX_POLICY_BYTES, "run_config_invalid")
    try:
        records = runner._validated_records(bundle_manifest_path.parent, manifest)
        verified_config, paths, _dependencies = runner._verify_run_config(
            bundle_manifest_path.parent, manifest, records
        )
        requested_path = run_config_path.resolve(strict=True)
        verified_path = paths["run_config"].resolve(strict=True)
    except Exception as error:
        raise OutputValidationError("bundle_verification_failed") from error
    if requested_path != verified_path or requested_config != verified_config:
        raise OutputValidationError("policy_provenance_invalid")
    if verified_config.get("code_commit") != expected_commit:
        raise OutputValidationError("expected_commit_mismatch")
    if verified_config.get("bundle_sha256") != expected_bundle:
        raise OutputValidationError("expected_bundle_mismatch")
    if manifest.get("bundle_sha256") != expected_bundle:
        raise OutputValidationError("expected_bundle_mismatch")
    return verified_config, runner, manifest


def _safe_remote_name(value: object) -> str:
    if not isinstance(value, str) or len(value) > 240 or "\\" in value:
        raise OutputValidationError("remote_listing_invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise OutputValidationError("remote_listing_invalid")
    if any(not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", part) for part in path.parts):
        raise OutputValidationError("remote_listing_invalid")
    return path.as_posix()


def _validated_dataset_ref(ref: str) -> tuple[str, str]:
    if ref.count("/") != 1:
        raise OutputValidationError("dataset_identity_invalid")
    owner, slug = ref.split("/", 1)
    if (
        re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}", owner) is None
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{5,49}", slug) is None
    ):
        raise OutputValidationError("dataset_identity_invalid")
    return owner, slug


def _listing_page(payload: bytes) -> tuple[list[dict[str, Any]], str | None]:
    token: str | None = None
    prefix = b"Next Page Token = "
    if payload.startswith(prefix):
        first, separator, payload = payload.partition(b"\n")
        if not separator:
            raise OutputValidationError("remote_listing_invalid")
        try:
            token = first.removeprefix(prefix).decode("ascii")
        except UnicodeDecodeError as error:
            raise OutputValidationError("remote_listing_invalid") from error
        if (
            not 1 <= len(token) <= 512
            or re.fullmatch(r"[A-Za-z0-9._~+/=-]+", token) is None
            or payload.startswith(prefix)
        ):
            raise OutputValidationError("remote_listing_invalid")
    elif prefix in payload:
        raise OutputValidationError("remote_listing_invalid")
    value = _json_value(payload, "remote_listing_invalid")
    records: object
    if isinstance(value, list):
        records = value
    elif isinstance(value, dict):
        records = value.get("files", value.get("data"))
        raw_token = value.get("nextPageToken", value.get("next_page_token"))
        if raw_token is not None and (
            not isinstance(raw_token, str)
            or not 1 <= len(raw_token) <= 512
            or not re.fullmatch(r"[A-Za-z0-9._~+/=-]+", raw_token)
        ):
            raise OutputValidationError("remote_listing_invalid")
        if token is not None and raw_token is not None and token != raw_token:
            raise OutputValidationError("remote_listing_invalid")
        token = cast(str | None, raw_token) if raw_token is not None else token
    else:
        raise OutputValidationError("remote_listing_invalid")
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        raise OutputValidationError("remote_listing_invalid")
    return cast(list[dict[str, Any]], records), token


def _listing_records(pages: Sequence[bytes]) -> list[dict[str, Any]]:
    if not pages or len(pages) > 128:
        raise OutputValidationError("remote_listing_invalid")
    all_records: list[dict[str, Any]] = []
    tokens: set[str] = set()
    for index, page in enumerate(pages):
        records, token = _listing_page(page)
        if index < len(pages) - 1:
            if token is None or token in tokens:
                raise OutputValidationError("remote_listing_incomplete")
            tokens.add(token)
        elif token is not None:
            raise OutputValidationError("remote_listing_incomplete")
        all_records.extend(records)
        if len(all_records) > MAX_REMOTE_RECORDS:
            raise OutputValidationError("remote_listing_too_large")
    return all_records


def _remote_bytes(record: Mapping[str, Any]) -> int:
    fields = [key for key in ("totalBytes", "bytes", "size") if key in record]
    if len(fields) != 1:
        raise OutputValidationError("remote_size_unavailable")
    value = record[fields[0]]
    if isinstance(value, str) and value.isdecimal():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise OutputValidationError("remote_size_invalid")
    return value


def _kernel_listing_records(
    pages: Sequence[bytes],
) -> list[tuple[dict[str, Any], int]]:
    records = _listing_records(pages)
    parsed: list[tuple[dict[str, Any], int]] = []
    for record in records:
        fields = [key for key in ("totalBytes", "bytes", "size") if key in record]
        if fields != ["size"]:
            raise OutputValidationError("remote_size_unavailable")
        if any(key in record for key in ("unit", "units", "sizeUnit", "size_unit")):
            raise OutputValidationError("remote_size_invalid")
        value = record["size"]
        if type(value) is not int or not 0 < value <= MAX_KERNEL_LISTING_SIZE:
            raise OutputValidationError("remote_size_invalid")
        parsed.append((record, value))
    # Kaggle CLI 2.2.4 kernel listings expose `size` as an opaque metric, not
    # logical bytes. Pinned producers/consumers enforce actual lengths and hashes.
    return parsed


def _policy_names(runner: ModuleType, attribute: str) -> set[str]:
    value = getattr(runner, attribute, None)
    if (
        not isinstance(value, dict)
        or not value
        or any(not isinstance(name, str) or "/" in name for name in value)
    ):
        raise OutputValidationError("runner_output_policy_invalid")
    return set(value)


def _canonical_remote_name(
    name: str,
    runner: ModuleType,
    *,
    private_names: set[str],
    downloadable_names: set[str],
) -> str:
    prefix = f"{runner.OUTPUT_DIRECTORY}/"
    if name.startswith(prefix):
        return name
    if name in private_names or name in downloadable_names:
        return prefix + name
    if name.startswith(f"{runner.PRIVATE_REVIEW_DIRECTORY}/"):
        return prefix + name
    return name


def _validate_review_output_listing(
    pages: Sequence[bytes],
    runner: ModuleType,
    *,
    finalizer: ModuleType | None = None,
) -> None:
    records = _kernel_listing_records(pages)
    prefix = f"{runner.OUTPUT_DIRECTORY}/"
    private_names = _policy_names(runner, "PRIVATE_OUTPUT_POLICY")
    downloadable_names = _policy_names(runner, "DOWNLOADABLE_OUTPUT_POLICY")
    required_fixed = {
        *(prefix + name for name in private_names),
        *(prefix + name for name in downloadable_names),
    }
    plan_name = (
        None
        if finalizer is None
        else f"{finalizer.TEMPLATE_OUTPUT_DIRECTORY}/{finalizer.REVIEW_PLAN_BASENAME}"
    )
    plan_aliases = (
        frozenset()
        if finalizer is None
        else frozenset({plan_name, str(finalizer.REVIEW_PLAN_BASENAME)})
    )
    observed: set[str] = set()
    review_groups: dict[str, set[str]] = defaultdict(set)
    log_count = 0
    required_suffixes = frozenset(
        {
            "contact.png",
            "histogram.png",
            "animation.gif",
            "before_after.png",
            "review.json",
            "metadata.json",
        }
    )
    allowed_suffixes = required_suffixes | {"orthogonal.png"}
    if finalizer is not None:
        producer_required = getattr(finalizer, "REQUIRED_SUFFIXES", None)
        producer_allowed = getattr(finalizer, "ALLOWED_SUFFIXES", None)
        if (
            not isinstance(producer_required, frozenset)
            or not isinstance(producer_allowed, frozenset)
            or producer_allowed != producer_required | {"orthogonal.png"}
            or len(producer_required) != 6
            or any(not isinstance(suffix, str) for suffix in producer_allowed)
        ):
            raise OutputValidationError("runner_output_policy_invalid")
        required_suffixes = producer_required
        allowed_suffixes = producer_allowed
    for record, _size in records:
        raw_name = _safe_remote_name(record.get("name"))
        name = (
            plan_name
            if plan_name is not None and raw_name in plan_aliases
            else _canonical_remote_name(
                raw_name,
                runner,
                private_names=private_names,
                downloadable_names=downloadable_names,
            )
        )
        if name in observed:
            raise OutputValidationError("remote_duplicate_name")
        observed.add(name)
        if name in required_fixed or name == plan_name:
            continue
        review_prefix = f"{prefix}{runner.PRIVATE_REVIEW_DIRECTORY}/"
        if name.startswith(review_prefix):
            basename = name.removeprefix(review_prefix)
            if re.fullmatch(runner.PRIVATE_REVIEW_PATTERN, basename) is None:
                raise OutputValidationError("remote_review_name_invalid")
            match = re.fullmatch(r"(case_([0-9]{6})_series_([0-9]{3}))_(.+)", basename)
            if match is None:
                raise OutputValidationError("remote_review_name_invalid")
            review_groups[match.group(1)].add(match.group(4))
            continue
        if "/" not in raw_name and re.fullmatch(runner.SESSION_LOG_PATTERN, raw_name):
            log_count += 1
            continue
        raise OutputValidationError("remote_name_not_allowed")
    if (
        not required_fixed.issubset(observed)
        or (plan_name is not None and plan_name not in observed)
        or log_count > 1
    ):
        raise OutputValidationError("remote_required_output_missing")
    reviewed_cases = {group.split("_series_", 1)[0] for group in review_groups}
    if (
        len(reviewed_cases) < runner.MINIMUM_ELIGIBLE_STUDIES
        or any(
            not required_suffixes.issubset(suffixes) or not suffixes.issubset(allowed_suffixes)
            for suffixes in review_groups.values()
        )
        or sum(len(suffixes) for suffixes in review_groups.values())
        > runner.PRIVATE_REVIEW_MAX_FILES
    ):
        raise OutputValidationError("remote_review_output_incomplete")


def validate_remote_listing(
    pages: Sequence[bytes], _run_config: Mapping[str, Any], runner: ModuleType
) -> None:
    """Validate the downstream review-plan output without retrieving private files."""

    _validate_review_output_listing(pages, runner)


def _validate_run_listing(pages: Sequence[bytes], runner: ModuleType) -> None:
    """Require only the immutable full-pass outputs from Run A or Run B."""

    records = _kernel_listing_records(pages)
    prefix = f"{runner.OUTPUT_DIRECTORY}/"
    private_names = _policy_names(runner, "RUN_PRIVATE_OUTPUT_POLICY")
    downloadable_names = _policy_names(runner, "RUN_DOWNLOADABLE_OUTPUT_POLICY")
    if private_names != {
        "private_full_run_manifest.jsonl",
        "private_full_run_metrics.json",
        "private_cohort_plan.json",
    } or downloadable_names != {
        "sanitized_summary.json",
        "sanitized_artifact_inventory.json",
    }:
        raise OutputValidationError("runner_output_policy_invalid")
    required = {
        *(prefix + name for name in private_names),
        *(prefix + name for name in downloadable_names),
    }
    observed: set[str] = set()
    log_count = 0
    for record, _size in records:
        raw_name = _safe_remote_name(record.get("name"))
        if "/" not in raw_name and re.fullmatch(runner.SESSION_LOG_PATTERN, raw_name):
            log_count += 1
            continue
        name = _canonical_remote_name(
            raw_name,
            runner,
            private_names=private_names,
            downloadable_names=downloadable_names,
        )
        if name in observed:
            raise OutputValidationError("remote_duplicate_name")
        observed.add(name)
        if name in required:
            continue
        raise OutputValidationError("remote_name_not_allowed")
    if observed - required or not required.issubset(observed) or log_count > 1:
        raise OutputValidationError("remote_required_output_missing")


def _validate_source_manifest_listing(pages: Sequence[bytes], identity: Mapping[str, Any]) -> None:
    expected_private = _source_manifest_output_policy(identity)
    expected = set(expected_private) | set(SOURCE_MANIFEST_DOWNLOADABLE_OUTPUTS)
    observed: set[str] = set()
    log_count = 0
    records = _kernel_listing_records(pages)
    for record, _size in records:
        name = _safe_remote_name(record.get("name"))
        if name.startswith("audit-output/"):
            canonical = name
        elif f"audit-output/{name}" in expected:
            canonical = f"audit-output/{name}"
        elif "/" not in name and SAFE_LOG_PATTERN.fullmatch(name):
            log_count += 1
            continue
        else:
            raise OutputValidationError("remote_name_not_allowed")
        if canonical not in expected:
            raise OutputValidationError("remote_name_not_allowed")
        if canonical in observed:
            raise OutputValidationError("remote_size_invalid")
        observed.add(canonical)
    if observed != expected or log_count > 1:
        raise OutputValidationError("remote_required_output_missing")


def _deployment_identity(run_config: Mapping[str, Any]) -> tuple[str, str, str]:
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
        raise OutputValidationError("kernel_identity_invalid")
    return owner, commit, bundle


def _derived_stage_kernel_ref(run_config: Mapping[str, Any], stage: str) -> str:
    prefix = STAGE_SLUG_PREFIXES.get(stage)
    if prefix is None:
        raise OutputValidationError("kernel_identity_invalid")
    owner, commit, bundle = _deployment_identity(run_config)
    slug = f"{prefix}-{commit[:7]}-{bundle[:12]}"
    if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}", slug) is None:
        raise OutputValidationError("kernel_identity_invalid")
    return f"{owner}/{slug}"


def _run_kaggle_cli(
    arguments: Sequence[str],
    *,
    maximum: int = 4 * 1024 * 1024,
    allow_empty: bool = False,
    timeout_seconds: float = 300.0,
) -> bytes:
    executable = shutil.which("kaggle")
    if executable is None:
        raise OutputValidationError("kaggle_cli_unavailable")
    try:
        completed = subprocess.run(
            [executable, *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise OutputValidationError("kaggle_cli_failed") from error
    if (
        completed.returncode != 0
        or len(completed.stdout) > maximum
        or (not allow_empty and not completed.stdout)
    ):
        raise OutputValidationError("kaggle_cli_failed")
    return completed.stdout


def _supported_kaggle_cli_interpreter() -> Path:
    executable_text = shutil.which("kaggle")
    if executable_text is None:
        raise OutputValidationError("kaggle_cli_unavailable")
    executable = Path(executable_text)
    try:
        executable = executable.resolve(strict=True)
        if not executable.is_file():
            raise OutputValidationError("kaggle_cli_version_invalid")
        version = subprocess.run(
            [str(executable), "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=30,
            env=os.environ.copy(),
        )
        with executable.open("rb") as stream:
            first_line = stream.readline(4097)
        if (
            version.returncode != 0
            or version.stdout != (KAGGLE_CLI_VERSION + "\n").encode("ascii")
            or version.stderr
            or len(first_line) > 4096
            or not first_line.startswith(b"#!")
        ):
            raise OutputValidationError("kaggle_cli_version_invalid")
        interpreter_text = first_line[2:].strip().decode("utf-8")
        interpreter = Path(interpreter_text)
        if not interpreter.is_absolute():
            raise OutputValidationError("kaggle_cli_version_invalid")
        resolved_interpreter = interpreter.resolve(strict=True)
        if not resolved_interpreter.is_file() or not os.access(interpreter, os.X_OK):
            raise OutputValidationError("kaggle_cli_version_invalid")
    except OutputValidationError:
        raise
    except (OSError, UnicodeDecodeError, subprocess.SubprocessError) as error:
        raise OutputValidationError("kaggle_cli_version_invalid") from error
    return interpreter


def _verify_review_session_metadata(
    *,
    interpreter: Path,
    ref: str,
    parent_ref: str,
    dataset_sources: Sequence[str],
    kernel_sources: Sequence[str],
    competition_sources: Sequence[str],
    model_sources: Sequence[str] = (),
) -> None:
    owner, separator, slug = ref.partition("/")
    if (
        not separator
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}", owner) is None
        or re.fullmatch(r"rsna-knee-dqa-review-[0-9a-f]{7}-[0-9a-f]{12}", slug) is None
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}/[a-z0-9][a-z0-9_-]{0,49}", parent_ref) is None
    ):
        raise OutputValidationError("review_session_identity_invalid")
    request = _canonical_json_bytes(
        {
            "ref": ref,
            "parent_ref": parent_ref,
            "owner": owner,
            "slug": slug,
            "dataset_sources": list(dataset_sources),
            "kernel_sources": list(kernel_sources),
            "competition_sources": list(competition_sources),
            "model_sources": list(model_sources),
        }
    )
    if len(request) > 64 * 1024:
        raise OutputValidationError("review_session_identity_invalid")
    try:
        completed = subprocess.run(
            [str(interpreter), "-c", _REVIEW_SESSION_METADATA_PROBE],
            input=request,
            capture_output=True,
            check=False,
            timeout=300,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise OutputValidationError("review_session_metadata_invalid") from error
    if (
        completed.returncode != 0
        or completed.stdout != b"review_session_metadata=PASS\n"
        or completed.stderr
    ):
        raise OutputValidationError("review_session_metadata_invalid")


def _authenticated_dataset_listing(ref: str, expected_version: int) -> tuple[bytes, ...]:
    if expected_version != DATASET_VERSION:
        raise OutputValidationError("dataset_version_invalid")
    pages: list[bytes] = []
    token: str | None = None
    observed_tokens: set[str] = set()
    while True:
        arguments = [
            "datasets",
            "files",
            f"{ref}/{expected_version}",
            "--page-size",
            str(DATASET_PAGE_SIZE),
            "--format",
            "json",
        ]
        if token is not None:
            arguments.extend(("--page-token", token))
        page = _run_kaggle_cli(tuple(arguments))
        _records, next_token = _listing_page(page)
        pages.append(page)
        if next_token is None:
            break
        if next_token in observed_tokens or len(pages) >= 128:
            raise OutputValidationError("dataset_listing_incomplete")
        observed_tokens.add(next_token)
        token = next_token
    return tuple(pages)


def _validate_dataset_listing(
    pages: Sequence[bytes], expected_files: Mapping[str, int]
) -> tuple[tuple[str, int], ...]:
    try:
        records = _listing_records(pages)
    except OutputValidationError as error:
        raise OutputValidationError("dataset_listing_invalid") from error
    observed: dict[str, int] = {}
    for record in records:
        try:
            name = _safe_remote_name(record.get("name"))
            size = _remote_bytes(record)
        except OutputValidationError as error:
            raise OutputValidationError("dataset_listing_invalid") from error
        if name in observed:
            raise OutputValidationError("dataset_listing_invalid")
        observed[name] = size
    if observed != dict(expected_files):
        raise OutputValidationError("dataset_file_set_invalid")
    return tuple(sorted(observed.items()))


def _same_filesystem_object(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _downloaded_digest(
    directory_fd: int,
    name: str,
    expected_size: int,
) -> str:
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    if not no_follow or not close_on_exec:
        raise OutputValidationError("dataset_download_layout_invalid")
    descriptor = -1
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | no_follow | close_on_exec,
            dir_fd=directory_fd,
        )
        os.fchmod(descriptor, 0o600)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size != expected_size
        ):
            code = (
                "dataset_download_size_mismatch"
                if stat.S_ISREG(before.st_mode) and before.st_size != expected_size
                else "dataset_download_layout_invalid"
            )
            raise OutputValidationError(code)
        digest = hashlib.sha256()
        consumed = 0
        while True:
            payload = os.read(descriptor, DATASET_CONTENT_CHUNK_BYTES)
            if not payload:
                break
            consumed += len(payload)
            if consumed > expected_size:
                raise OutputValidationError("dataset_download_size_mismatch")
            digest.update(payload)
        after = os.fstat(descriptor)
        path_after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            consumed != expected_size
            or after.st_size != expected_size
            or not _same_filesystem_object(before, after)
            or not _same_filesystem_object(after, path_after)
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
            or after.st_mtime_ns != path_after.st_mtime_ns
            or after.st_ctime_ns != path_after.st_ctime_ns
            or not stat.S_ISREG(path_after.st_mode)
            or path_after.st_nlink != 1
            or stat.S_IMODE(path_after.st_mode) != 0o600
        ):
            raise OutputValidationError("dataset_download_layout_invalid")
        return digest.hexdigest()
    except OutputValidationError:
        raise
    except OSError as error:
        raise OutputValidationError("dataset_download_layout_invalid") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _authenticate_dataset_content(
    ref: str,
    expected_files: Mapping[str, tuple[int, str]],
    *,
    deadline: float | None = None,
) -> None:
    """Download and hash only an authorized immutable input-bundle allowlist."""

    _validated_dataset_ref(ref)
    if not 1 <= len(expected_files) <= MAX_DATASET_CONTENT_FILES:
        raise OutputValidationError("dataset_content_policy_invalid")
    validated: dict[str, tuple[int, str]] = {}
    total = 0
    for raw_name, record in expected_files.items():
        try:
            name = _safe_remote_name(raw_name)
        except OutputValidationError as error:
            raise OutputValidationError("dataset_content_policy_invalid") from error
        if "/" in name or name in validated or not isinstance(record, tuple) or len(record) != 2:
            raise OutputValidationError("dataset_content_policy_invalid")
        size, digest = record
        if (
            isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
            or not isinstance(digest, str)
            or HEX_64.fullmatch(digest) is None
        ):
            raise OutputValidationError("dataset_content_policy_invalid")
        total += size
        if total > MAX_DATASET_CONTENT_BYTES:
            raise OutputValidationError("dataset_content_policy_invalid")
        validated[name] = (size, digest)

    directory_flag = getattr(os, "O_DIRECTORY", 0)
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    if not directory_flag or not no_follow or not close_on_exec:
        raise OutputValidationError("dataset_download_layout_invalid")
    with tempfile.TemporaryDirectory(prefix="rsna-knee-dataset-content-") as temporary:
        container = Path(temporary)
        os.chmod(container, 0o700)
        download_root = container / "download"
        download_root.mkdir(mode=0o700)
        container_fd = -1
        download_fd = -1
        try:
            flags = os.O_RDONLY | directory_flag | no_follow | close_on_exec
            container_fd = os.open(container, flags)
            download_fd = os.open(download_root, flags)
            container_before = os.fstat(container_fd)
            download_before = os.fstat(download_fd)
            if (
                not stat.S_ISDIR(container_before.st_mode)
                or not stat.S_ISDIR(download_before.st_mode)
                or stat.S_IMODE(container_before.st_mode) != 0o700
                or stat.S_IMODE(download_before.st_mode) != 0o700
                or os.listdir(container_fd) != ["download"]
                or os.listdir(download_fd)
            ):
                raise OutputValidationError("dataset_download_layout_invalid")

            if deadline is None:
                deadline = time.monotonic() + MAX_DATASET_CONTENT_SECONDS
            # ponytail: 0.25s pacing keeps ~60 per-file downloads under Kaggle's
            # HTTP-429 throttle; batched archive download if this ever grows.
            download_pacing_seconds: Final = 0.25
            for name in sorted(validated):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise OutputValidationError("dataset_download_timeout")
                _run_kaggle_cli(
                    (
                        "datasets",
                        "download",
                        f"{ref}/{DATASET_VERSION}",
                        "--file",
                        name,
                        "--path",
                        str(download_root),
                        "--force",
                        "--quiet",
                    ),
                    maximum=64 * 1024,
                    allow_empty=True,
                    timeout_seconds=min(300.0, remaining),
                )
                time.sleep(download_pacing_seconds)
                if time.monotonic() > deadline:
                    raise OutputValidationError("dataset_download_timeout")

            container_after = os.fstat(container_fd)
            download_after = os.fstat(download_fd)
            path_after = os.stat(
                download_root.name,
                dir_fd=container_fd,
                follow_symlinks=False,
            )
            if (
                not _same_filesystem_object(container_before, container_after)
                or not _same_filesystem_object(download_before, download_after)
                or not _same_filesystem_object(download_after, path_after)
                or stat.S_IMODE(container_after.st_mode) != 0o700
                or stat.S_IMODE(download_after.st_mode) != 0o700
                or set(os.listdir(container_fd)) != {"download"}
                or set(os.listdir(download_fd)) != set(validated)
            ):
                raise OutputValidationError("dataset_download_layout_invalid")
            for name, (size, expected_digest) in sorted(validated.items()):
                if _downloaded_digest(download_fd, name, size) != expected_digest:
                    raise OutputValidationError("dataset_download_hash_mismatch")
            if time.monotonic() > deadline:
                raise OutputValidationError("dataset_download_timeout")
        except OutputValidationError:
            raise
        except OSError as error:
            raise OutputValidationError("dataset_download_layout_invalid") from error
        finally:
            if download_fd >= 0:
                os.close(download_fd)
            if container_fd >= 0:
                os.close(container_fd)


def _authenticated_dataset_snapshot(
    ref: str, expected_files: Mapping[str, int]
) -> dict[str, object]:
    _owner, slug = _validated_dataset_ref(ref)
    status = _json_bytes(
        _run_kaggle_cli(("datasets", "status", ref, "--format", "json"), maximum=16 * 1024),
        "dataset_status_invalid",
    )
    version = status.get("current_version_number")
    if (
        set(status) != {"status", "current_version_number"}
        or status.get("status") != "ready"
        or isinstance(version, bool)
        or not isinstance(version, int)
        or version != DATASET_VERSION
    ):
        raise OutputValidationError("dataset_status_invalid")

    with tempfile.TemporaryDirectory(prefix="rsna-knee-dataset-metadata-") as temporary:
        root = Path(temporary)
        _run_kaggle_cli(
            ("datasets", "metadata", ref, "--path", str(root)),
            maximum=64 * 1024,
            allow_empty=True,
        )
        try:
            entries = list(root.iterdir())
        except OSError as error:
            raise OutputValidationError("dataset_metadata_invalid") from error
        if (
            len(entries) != 1
            or entries[0].name != "dataset-metadata.json"
            or entries[0].is_symlink()
            or not entries[0].is_file()
        ):
            raise OutputValidationError("dataset_metadata_invalid")
        metadata = _json_bytes(
            _read_bounded(entries[0], MAX_POLICY_BYTES, "dataset_metadata_invalid"),
            "dataset_metadata_invalid",
        )
    info = metadata.get("info")
    if set(metadata) != {"info"} or not isinstance(info, dict):
        raise OutputValidationError("dataset_metadata_invalid")
    dataset_id = info.get("datasetId")
    if (
        info.get("datasetSlug") != slug
        or info.get("title") != slug
        or info.get("isPrivate") is not True
        or isinstance(dataset_id, bool)
        or not isinstance(dataset_id, int)
        or dataset_id <= 0
    ):
        raise OutputValidationError("dataset_metadata_invalid")
    files = _validate_dataset_listing(
        _authenticated_dataset_listing(ref, DATASET_VERSION), expected_files
    )
    return {
        "dataset_id": dataset_id,
        "dataset_slug": slug,
        "is_private": True,
        "status": "ready",
        "version": DATASET_VERSION,
        "files": files,
    }


def _bundle_dataset_ref(run_config: Mapping[str, Any]) -> str:
    owner, commit, bundle = _deployment_identity(run_config)
    return f"{owner}/rsna-knee-dicom-qa-bundle-{commit[:7]}-{bundle[:12]}"


def _bundle_dataset_content_policy(
    manifest: Mapping[str, Any],
) -> dict[str, tuple[int, str]]:
    records = manifest.get("files")
    if not isinstance(records, list) or not records or len(records) > MAX_REMOTE_RECORDS:
        raise OutputValidationError("dataset_manifest_invalid")
    expected: dict[str, tuple[int, str]] = {}
    try:
        for record in records:
            if not isinstance(record, dict):
                raise OutputValidationError("dataset_manifest_invalid")
            name = _safe_remote_name(record.get("path"))
            size = record.get("bytes")
            digest = record.get("sha256")
            if (
                "/" in name
                or name in expected
                or name == "dataset-metadata.json"
                or isinstance(size, bool)
                or not isinstance(size, int)
                or size <= 0
                or not isinstance(digest, str)
                or HEX_64.fullmatch(digest) is None
            ):
                raise OutputValidationError("dataset_manifest_invalid")
            expected[name] = (size, digest)
    except OutputValidationError as error:
        raise OutputValidationError("dataset_manifest_invalid") from error
    manifest_name = "bundle-manifest.json"
    if manifest_name in expected:
        raise OutputValidationError("dataset_manifest_invalid")
    payload = _canonical_json_bytes(manifest)
    expected[manifest_name] = (len(payload), hashlib.sha256(payload).hexdigest())
    return expected


def _bundle_dataset_files(manifest: Mapping[str, Any]) -> dict[str, int]:
    return {
        name: size for name, (size, _digest) in _bundle_dataset_content_policy(manifest).items()
    }


def _workflow_refs(run_config: Mapping[str, Any]) -> dict[str, str]:
    refs = {
        "performance_smoke": _derived_stage_kernel_ref(run_config, "performance_smoke"),
        "run_a": _derived_stage_kernel_ref(run_config, "run_a"),
        "run_b": _derived_stage_kernel_ref(run_config, "run_b"),
        "comparison": _derived_stage_kernel_ref(run_config, "comparator"),
        "review_plan": _derived_stage_kernel_ref(run_config, "plan"),
        "review_ui_template": _derived_stage_kernel_ref(run_config, "review_ui"),
        "review_session": _derived_stage_kernel_ref(run_config, "review_session"),
        "review_finalizer": _derived_stage_kernel_ref(run_config, "finalizer"),
    }
    return _apply_core_reuse(run_config, refs)


_CORE_REUSE_UPSTREAM_ROLES: Final = frozenset({"performance_smoke", "run_a", "run_b", "comparison"})


def _apply_core_reuse(run_config: Mapping[str, Any], refs: dict[str, str]) -> dict[str, str]:
    """Redirect certified-core upstream kernel refs for stage-aware QA-adapter reuse."""
    reuse = run_config.get("core_reuse")
    if reuse is None:
        return refs
    if not isinstance(reuse, dict):
        raise OutputValidationError("kernel_identity_invalid")
    lineage = reuse.get("core_lineage_id")
    payload = reuse.get("core_certificate_payload_sha256")
    upstream = reuse.get("upstream_refs")
    if (
        not isinstance(lineage, str)
        or re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,99}", lineage) is None
        or not isinstance(payload, str)
        or HEX_64.fullmatch(payload) is None
        or not isinstance(upstream, dict)
        or set(upstream) - _CORE_REUSE_UPSTREAM_ROLES
    ):
        raise OutputValidationError("kernel_identity_invalid")
    for role, ref in upstream.items():
        if (
            not isinstance(ref, str)
            or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}/[a-z0-9][a-z0-9_-]{0,99}", ref) is None
        ):
            raise OutputValidationError("kernel_identity_invalid")
        refs[str(role)] = ref
    return refs


def _source_manifest_dataset_content_policy(
    identity: Mapping[str, Any],
) -> dict[str, tuple[int, str]]:
    records = identity.get("bundle_dataset_files")
    if not isinstance(records, list) or not records or len(records) > MAX_REMOTE_RECORDS:
        raise OutputValidationError("source_manifest_identity_invalid")
    expected: dict[str, tuple[int, str]] = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != {"name", "bytes", "sha256"}:
            raise OutputValidationError("source_manifest_identity_invalid")
        try:
            name = _safe_remote_name(record.get("name"))
        except OutputValidationError as error:
            raise OutputValidationError("source_manifest_identity_invalid") from error
        size = record.get("bytes")
        digest = record.get("sha256")
        if (
            "/" in name
            or name in expected
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
            or not isinstance(digest, str)
            or HEX_64.fullmatch(digest) is None
        ):
            raise OutputValidationError("source_manifest_identity_invalid")
        expected[name] = (size, digest)
    if "bundle-manifest.json" not in expected:
        raise OutputValidationError("source_manifest_identity_invalid")
    return expected


def _source_manifest_dataset_files(identity: Mapping[str, Any]) -> dict[str, int]:
    return {
        name: size
        for name, (size, _digest) in _source_manifest_dataset_content_policy(identity).items()
    }


def _source_manifest_output_policy(
    identity: Mapping[str, Any],
) -> dict[str, tuple[int, int | None]]:
    records = identity.get("private_output_policy")
    if not isinstance(records, list) or not records or len(records) > 64:
        raise OutputValidationError("source_manifest_identity_invalid")
    expected: dict[str, tuple[int, int | None]] = {}
    for record in records:
        if (
            not isinstance(record, dict)
            or not set(record)
            <= {
                "path",
                "max_bytes",
                "exact_bytes",
            }
            or not {"path", "max_bytes"} <= set(record)
        ):
            raise OutputValidationError("source_manifest_identity_invalid")
        try:
            name = _safe_remote_name(record.get("path"))
        except OutputValidationError as error:
            raise OutputValidationError("source_manifest_identity_invalid") from error
        maximum = record.get("max_bytes")
        exact = record.get("exact_bytes")
        if (
            not name.startswith("audit-output/private_") and name != "audit-output/audit_key.bin"
        ) or (
            name in expected
            or isinstance(maximum, bool)
            or not isinstance(maximum, int)
            or maximum <= 0
            or (
                exact is not None
                and (
                    isinstance(exact, bool)
                    or not isinstance(exact, int)
                    or not 0 < exact <= maximum
                )
            )
        ):
            raise OutputValidationError("source_manifest_identity_invalid")
        expected[name] = (maximum, exact)
    required_names = {
        "audit-output/private_manifest.sqlite3",
        "audit-output/private_duplicate_groups.csv",
        "audit-output/private_preliminary_group_keys.csv",
        "audit-output/private_qa_samples.csv",
        "audit-output/private_artifact_inventory.json",
        "audit-output/audit_key.bin",
    }
    if set(expected) != required_names or expected["audit-output/audit_key.bin"][1] != 32:
        raise OutputValidationError("source_manifest_identity_invalid")
    return expected


def _validated_workflow_identity(
    run_config: Mapping[str, Any], manifest: Mapping[str, Any], finalizer: ModuleType
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        public = finalizer._public_review_identity(run_config, manifest)
    except Exception as error:
        raise OutputValidationError("review_identity_invalid") from error
    input_identity = run_config.get("input_identity")
    source = input_identity.get("source_manifest") if isinstance(input_identity, dict) else None
    official = (
        input_identity.get("official_competition") if isinstance(input_identity, dict) else None
    )
    provenance = run_config.get("provenance")
    policy = run_config.get("review_policy")
    competition = run_config.get("competition")
    expected_source_keys = {
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
    if (
        not isinstance(source, dict)
        or set(source) != expected_source_keys
        or source.get("version") != SOURCE_MANIFEST_VERSION
        or source.get("audit_id") != SOURCE_MANIFEST_AUDIT_ID
        or source.get("kernel_version") != 1
        or source.get("kernel_code_file") != "run.py"
        or source.get("bundle_dataset_version") != 1
        or source.get("artifact_inventory_filename") != "private_artifact_inventory.json"
        or source.get("database_filename") != "private_manifest.sqlite3"
        or source.get("audit_key_filename") != "audit_key.bin"
        or not isinstance(source.get("kernel_code_sha256"), str)
        or HEX_64.fullmatch(str(source["kernel_code_sha256"])) is None
        or not isinstance(source.get("bundle_sha256"), str)
        or HEX_64.fullmatch(str(source["bundle_sha256"])) is None
        or not isinstance(source.get("schema_sha256"), str)
        or HEX_64.fullmatch(str(source["schema_sha256"])) is None
        or not isinstance(source.get("kernel_ref"), str)
        or not isinstance(source.get("bundle_dataset_ref"), str)
        or not isinstance(official, dict)
        or set(official) != {"slug", "contract_sha256", "snapshot_identity_source"}
        or not isinstance(competition, dict)
        or official.get("slug") != competition.get("slug")
        or official.get("snapshot_identity_source") != "chunk4_private_manifest"
        or not isinstance(provenance, dict)
        or official.get("contract_sha256") != provenance.get("competition_contract_sha256")
        or policy
        != {
            "protocol_version": "private-dicom-qa-human-review-v2",
            "instructions_version": "private-dicom-qa-review-instructions-v2",
            "cohort_selection_version": "qa-cohort-selection-v3",
            "stratum_registry_version": "qa-stratum-registry-v1",
            "stratum_registry_sha256": (
                "13829b49acec7ed2a3cb83cc862caaf3"  # pragma: allowlist secret
                "251ecbab9f1b11eca4061c0c9ae5acf3"  # pragma: allowlist secret
            ),
            "kernel_version": 1,
            "checks": list(REVIEW_CHECKS),
            "statuses": list(REVIEW_STATUSES),
            "artifact_presence_separate": True,
            "minimum_reviewed_studies": 100,
        }
    ):
        raise OutputValidationError("review_identity_invalid")
    try:
        _validated_dataset_ref(cast(str, source["bundle_dataset_ref"]))
        _validated_dataset_ref(_bundle_dataset_ref(run_config))
        _source_manifest_dataset_files(source)
        _source_manifest_output_policy(source)
    except OutputValidationError as error:
        raise OutputValidationError("review_identity_invalid") from error
    source_ref = cast(str, source["kernel_ref"])
    if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}/[a-z0-9][a-z0-9_-]{0,49}", source_ref) is None:
        raise OutputValidationError("review_identity_invalid")
    refs = _workflow_refs(run_config)
    public_kernels = public.get("kernels") if isinstance(public, dict) else None
    expected_public_kernels = {role: {"ref": ref, "version": 1} for role, ref in refs.items()}
    if not isinstance(public, dict) or public_kernels != expected_public_kernels:
        raise OutputValidationError("review_identity_invalid")
    return cast(dict[str, Any], source), refs


def _performance_smoke_identity(
    run_config: Mapping[str, Any], manifest: Mapping[str, Any]
) -> tuple[str, str]:
    record = manifest.get("performance_smoke")
    provenance = run_config.get("provenance")
    if (
        not isinstance(record, dict)
        or set(record) != {"code_file", "sha256", "policy_file", "policy_sha256"}
        or record.get("code_file") != "performance_smoke.py"
        or record.get("policy_file") != "performance-smoke-policy.json"
        or not isinstance(record.get("sha256"), str)
        or HEX_64.fullmatch(cast(str, record["sha256"])) is None
        or not isinstance(record.get("policy_sha256"), str)
        or HEX_64.fullmatch(cast(str, record["policy_sha256"])) is None
        or not isinstance(provenance, dict)
        or provenance.get("performance_smoke_sha256") != record.get("sha256")
        or provenance.get("performance_smoke_policy_sha256") != record.get("policy_sha256")
        or run_config.get("bundle_sha256") != manifest.get("bundle_sha256")
    ):
        raise OutputValidationError("performance_smoke_identity_invalid")
    return cast(str, record["sha256"]), cast(str, record["policy_sha256"])


def _validate_exact_kernel_metadata(
    metadata: Mapping[str, Any],
    *,
    ref: str,
    expected_code_file: str,
    expected_kernel_type: str,
    expected_dataset_sources: Sequence[str],
    expected_kernel_sources: Sequence[str],
    expected_competition_sources: Sequence[str],
    expected_model_sources: Sequence[str] = (),
) -> dict[str, Any]:
    if expected_kernel_type not in {"script", "notebook"}:
        raise OutputValidationError("kernel_metadata_invalid")
    try:
        expected_keys = {
            "id",
            "id_no",
            "title",
            "code_file",
            "language",
            "kernel_type",
            "is_private",
            "enable_gpu",
            "enable_tpu",
            "enable_internet",
            "keywords",
            "dataset_sources",
            "kernel_sources",
            "competition_sources",
            "model_sources",
            "docker_image",
            "machine_shape",
        }
        dataset_sources = metadata.get("dataset_sources")
        kernel_sources = metadata.get("kernel_sources")
        competition_sources = metadata.get("competition_sources")
        model_sources = metadata.get("model_sources")
        id_number = metadata.get("id_no")
        docker_image = metadata.get("docker_image")
        machine_shape = metadata.get("machine_shape")
        if (
            set(metadata) != expected_keys
            or metadata.get("id") != ref
            or metadata.get("title") != ref.partition("/")[2]
            or metadata.get("code_file") != expected_code_file
            or str(metadata.get("language", "")).lower() != "python"
            or str(metadata.get("kernel_type", "")).lower() != expected_kernel_type
            or metadata.get("is_private") is not True
            or metadata.get("enable_internet") is not False
            or metadata.get("enable_gpu") is not False
            or metadata.get("enable_tpu") is not False
            or isinstance(id_number, bool)
            or not isinstance(id_number, int)
            or id_number <= 0
            or metadata.get("keywords") != []
            or not isinstance(docker_image, str)
            or len(docker_image) > 200
            or re.fullmatch(r"[A-Za-z0-9./:_@+-]*", docker_image) is None
            or not isinstance(machine_shape, str)
            or len(machine_shape) > 100
            or re.fullmatch(r"[A-Za-z0-9._ -]*", machine_shape) is None
            or dataset_sources != list(expected_dataset_sources)
            or kernel_sources != list(expected_kernel_sources)
            or competition_sources != list(expected_competition_sources)
            or model_sources != list(expected_model_sources)
        ):
            raise OutputValidationError("kernel_metadata_invalid")
    except (KeyError, TypeError, ValueError) as error:
        raise OutputValidationError("kernel_metadata_invalid") from error
    return {
        "id": ref,
        "id_no": id_number,
        "title": ref.partition("/")[2],
        "code_file": expected_code_file,
        "dataset_sources": list(cast(list[object], dataset_sources)),
        "kernel_sources": list(cast(list[object], kernel_sources)),
        "competition_sources": list(cast(list[object], competition_sources)),
        "model_sources": list(cast(list[object], model_sources)),
        "is_private": True,
        "enable_internet": False,
        "enable_gpu": False,
        "enable_tpu": False,
        "kernel_type": expected_kernel_type,
        "language": "python",
        "keywords": [],
        "docker_image": docker_image,
        "machine_shape": machine_shape,
    }


def _validate_kernel_api_metadata(
    payload: Mapping[str, Any], *, ref: str, expected_version: int
) -> dict[str, object]:
    owner, separator, slug = ref.partition("/")
    version = payload.get("current_version_number")
    if (
        not separator
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}", owner) is None
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}", slug) is None
        or expected_version != 1
        or set(payload)
        != {
            "current_version_number",
            "enable_internet",
            "is_private",
            "ref",
            "slug",
            "title",
        }
        or payload.get("ref") != ref
        or payload.get("slug") != slug
        or payload.get("title") != slug
        or payload.get("is_private") is not True
        or payload.get("enable_internet") is not False
        or isinstance(version, bool)
        or not isinstance(version, int)
        or version != expected_version
    ):
        raise OutputValidationError("kernel_api_metadata_invalid")
    return {
        "current_version_number": version,
        "enable_internet": False,
        "is_private": True,
        "ref": ref,
        "slug": slug,
        "title": slug,
    }


def _authenticate_kernel_api_version(ref: str, expected_version: int) -> dict[str, object]:
    owner, separator, slug = ref.partition("/")
    if (
        not separator
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}", owner) is None
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,49}", slug) is None
        or expected_version != 1
    ):
        raise OutputValidationError("kernel_api_metadata_invalid")
    request = _canonical_json_bytes({"owner": owner, "slug": slug})
    try:
        completed = subprocess.run(
            [str(_supported_kaggle_cli_interpreter()), "-c", _KERNEL_API_METADATA_PROBE],
            input=request,
            capture_output=True,
            check=False,
            timeout=300,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise OutputValidationError("kernel_api_metadata_invalid") from error
    if completed.returncode != 0 or completed.stderr or not completed.stdout:
        raise OutputValidationError("kernel_api_metadata_invalid")
    payload = _json_bytes(completed.stdout, "kernel_api_metadata_invalid")
    return _validate_kernel_api_metadata(payload, ref=ref, expected_version=expected_version)


def _assert_version_absent(ref: str, absent_version: int) -> None:
    if absent_version != 2:
        raise OutputValidationError("kernel_api_metadata_invalid")
    _authenticate_kernel_api_version(ref, 1)


def _pull_and_verify_exact_kernel(
    ref: str,
    expected_version: int,
    expected_code_file: str,
    expected_code_sha256: str,
    *,
    expected_kernel_type: str,
    expected_dataset_sources: Sequence[str],
    expected_kernel_sources: Sequence[str],
    expected_competition_sources: Sequence[str],
    expected_model_sources: Sequence[str] = (),
) -> dict[str, Any]:
    if expected_version != 1:
        raise OutputValidationError("kernel_version_invalid")
    with tempfile.TemporaryDirectory(prefix="rsna-knee-kernel-source-") as temporary:
        root = Path(temporary)
        code_path = root / expected_code_file
        try:
            code_path.touch(exist_ok=False)
        except OSError as error:
            raise OutputValidationError("kernel_source_invalid") from error
        _run_kaggle_cli(
            (
                "kernels",
                "pull",
                ref,
                "--path",
                str(code_path),
                "--metadata",
            )
        )
        try:
            entries = list(root.iterdir())
        except OSError as error:
            raise OutputValidationError("kernel_source_invalid") from error
        expected_names = {"kernel-metadata.json", expected_code_file}
        if (
            len(entries) != len(expected_names)
            or {entry.name for entry in entries} != expected_names
            or any(entry.is_symlink() or not entry.is_file() for entry in entries)
        ):
            raise OutputValidationError("kernel_source_invalid")
        metadata_path = root / "kernel-metadata.json"
        metadata = _json_bytes(
            _read_bounded(metadata_path, MAX_POLICY_BYTES, "kernel_source_invalid"),
            "kernel_source_invalid",
        )
        code_file = metadata.get("code_file")
        if code_file != expected_code_file or metadata.get("id") != ref:
            raise OutputValidationError("kernel_source_invalid")
        payload = _read_bounded(code_path, 1024 * 1024, "kernel_source_invalid")
        if hashlib.sha256(payload).hexdigest() != expected_code_sha256:
            raise OutputValidationError("kernel_source_hash_mismatch")
        return _validate_exact_kernel_metadata(
            metadata,
            ref=ref,
            expected_code_file=expected_code_file,
            expected_kernel_type=expected_kernel_type,
            expected_dataset_sources=expected_dataset_sources,
            expected_kernel_sources=expected_kernel_sources,
            expected_competition_sources=expected_competition_sources,
            expected_model_sources=expected_model_sources,
        )


def _normalize_kernel_status(value: object) -> str:
    if value not in {"complete", "COMPLETE", "KernelWorkerStatus.COMPLETE"}:
        raise OutputValidationError("kernel_status_invalid")
    return "complete"


def _kernel_status_complete(ref: str) -> None:
    payload = _run_kaggle_cli(("kernels", "status", ref), maximum=16 * 1024)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise OutputValidationError("kernel_status_invalid") from error
    match = re.fullmatch(re.escape(ref) + r' has status "([^"\r\n]+)"\s*', text)
    if match is None:
        raise OutputValidationError("kernel_status_invalid")
    _normalize_kernel_status(match.group(1))


def _authenticated_listing(ref: str, expected_version: int) -> tuple[bytes, ...]:
    pages: list[bytes] = []
    token: str | None = None
    observed_tokens: set[str] = set()
    while True:
        arguments = [
            "kernels",
            "files",
            f"{ref}/{expected_version}",
            "--page-size",
            "200",
            "--format",
            "json",
        ]
        if token is not None:
            arguments.extend(("--page-token", token))
        page = _run_kaggle_cli(tuple(arguments))
        _records, next_token = _listing_page(page)
        pages.append(page)
        if next_token is None:
            break
        if next_token in observed_tokens or len(pages) >= 128:
            raise OutputValidationError("remote_listing_incomplete")
        observed_tokens.add(next_token)
        token = next_token
    return tuple(pages)


def _validate_performance_smoke_listing(pages: Sequence[bytes]) -> None:
    expected = f"{PERFORMANCE_SMOKE_OUTPUT_DIRECTORY}/{PERFORMANCE_SMOKE_SUMMARY}"
    observed_summary = False
    log_count = 0
    for record, _size in _kernel_listing_records(pages):
        name = _safe_remote_name(record.get("name"))
        if name in {expected, PERFORMANCE_SMOKE_SUMMARY}:
            if observed_summary:
                raise OutputValidationError("remote_duplicate_name")
            observed_summary = True
        elif "/" not in name and SAFE_LOG_PATTERN.fullmatch(name):
            log_count += 1
        else:
            raise OutputValidationError("remote_name_not_allowed")
    if not observed_summary or log_count > 1:
        raise OutputValidationError("remote_required_output_missing")


def _validate_performance_smoke_summary(
    payload: bytes,
    *,
    run_config: Mapping[str, Any],
    runner: ModuleType,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    summary = _json_bytes(payload, "performance_smoke_summary_invalid")
    smoke_sha256, policy_sha256 = _performance_smoke_identity(run_config, manifest)
    provenance = run_config.get("provenance")
    runtime = run_config.get("runtime")
    if not isinstance(provenance, dict) or not isinstance(runtime, dict):
        raise OutputValidationError("performance_smoke_summary_invalid")
    input_binding = (
        summary.get("provenance", {}).get("input_binding_sha256")
        if isinstance(summary.get("provenance"), dict)
        else None
    )
    expected_provenance = {
        "git_commit": run_config.get("code_commit"),
        "bundle_sha256": run_config.get("bundle_sha256"),
        "runner_sha256": provenance.get("runner_sha256"),
        "smoke_entrypoint_sha256": smoke_sha256,
        "performance_smoke_policy_sha256": policy_sha256,
        "preprocessing_config_sha256": provenance.get("preprocessing_config_sha256"),
        "preprocessing_version": provenance.get("preprocessing_version"),
        "source_manifest_version": SOURCE_MANIFEST_VERSION,
        "source_manifest_audit_id": SOURCE_MANIFEST_AUDIT_ID,
        "input_binding_sha256": input_binding,
    }
    smoke_runtime = summary.get("runtime")
    performance = summary.get("performance")
    privacy = summary.get("privacy")
    competition_limit = (
        smoke_runtime.get("competition_cpu_limit_seconds")
        if isinstance(smoke_runtime, dict)
        else None
    )
    expected_runtime = {
        "private_kernel": True,
        "internet": False,
        "accelerator": "cpu",
        "self_deadline_seconds": PERFORMANCE_SMOKE_SELF_DEADLINE_SECONDS,
        "full_pass_budget_seconds": runner.SELF_DEADLINE_SECONDS,
        "competition_cpu_limit_seconds": competition_limit,
    }
    expected_privacy = {
        "identifiers_emitted": False,
        "paths_emitted": False,
        "pixels_emitted": False,
        "reports_emitted": False,
        "private_resource_locators_emitted": False,
        "private_artifact_checksums_emitted": False,
    }
    if (
        payload != _canonical_json_bytes(summary)
        or set(summary)
        != {
            "schema_version",
            "artifact_type",
            "status",
            "full_run_started",
            "provenance",
            "runtime",
            "performance",
            "privacy",
        }
        or summary.get("schema_version") != 1
        or summary.get("artifact_type") != "dicom-qa-performance-smoke-sanitized-aggregate"
        or summary.get("status") != "pass"
        or summary.get("full_run_started") is not False
        or not isinstance(input_binding, str)
        or HEX_64.fullmatch(input_binding) is None
        or summary.get("provenance") != expected_provenance
        or smoke_runtime != expected_runtime
        or isinstance(competition_limit, bool)
        or not isinstance(competition_limit, int)
        or competition_limit <= runner.SELF_DEADLINE_SECONDS
        or runtime.get("internet") is not False
        or runtime.get("accelerator") != "cpu"
        or runtime.get("self_deadline_seconds") != runner.SELF_DEADLINE_SECONDS
        or privacy != expected_privacy
        or not isinstance(performance, dict)
        or set(performance)
        != {
            "production_path_exercised",
            "authenticated_sample",
            "admission_status",
            "smoke_elapsed_seconds_ceiling",
            "projected_full_run_seconds_ceiling",
            "post_comparison_preparation_path_exercised",
            "qa_replay_render_seconds_per_series_ceiling",
            "representative_benchmark_seconds_ceiling",
            "review_artifacts_per_series_ceiling",
            "review_artifact_bytes_per_series_power_of_two_mib_ceiling",
        }
        or performance.get("production_path_exercised") is not True
        or performance.get("authenticated_sample") is not True
        or performance.get("admission_status") != "pass"
        or performance.get("post_comparison_preparation_path_exercised") is not True
        or performance.get("review_artifacts_per_series_ceiling") != 7
    ):
        raise OutputValidationError("performance_smoke_summary_invalid")
    for key, upper_bound in (
        ("smoke_elapsed_seconds_ceiling", PERFORMANCE_SMOKE_SELF_DEADLINE_SECONDS),
        ("projected_full_run_seconds_ceiling", runner.SELF_DEADLINE_SECONDS),
    ):
        value = performance.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not PERFORMANCE_SMOKE_PROJECTION_QUANTUM_SECONDS <= value <= upper_bound
            or value % PERFORMANCE_SMOKE_PROJECTION_QUANTUM_SECONDS
        ):
            raise OutputValidationError("performance_smoke_summary_invalid")
    replay_ceiling = performance.get("qa_replay_render_seconds_per_series_ceiling")
    benchmark_ceiling = performance.get("representative_benchmark_seconds_ceiling")
    if (
        isinstance(replay_ceiling, bool)
        or not isinstance(replay_ceiling, int)
        or not 1 <= replay_ceiling <= POST_COMPARISON_PREPARATION_CEILING_SECONDS
        or isinstance(benchmark_ceiling, bool)
        or not isinstance(benchmark_ceiling, int)
        or not PERFORMANCE_SMOKE_PROJECTION_QUANTUM_SECONDS
        <= benchmark_ceiling
        <= POST_COMPARISON_PREPARATION_CEILING_SECONDS
        or benchmark_ceiling % PERFORMANCE_SMOKE_PROJECTION_QUANTUM_SECONDS
    ):
        raise OutputValidationError("performance_smoke_summary_invalid")
    artifact_mib = performance.get("review_artifact_bytes_per_series_power_of_two_mib_ceiling")
    if (
        isinstance(artifact_mib, bool)
        or not isinstance(artifact_mib, int)
        or not 1 <= artifact_mib <= 256
        or artifact_mib & (artifact_mib - 1)
    ):
        raise OutputValidationError("performance_smoke_summary_invalid")
    try:
        runner._scan_downloadable(
            payload, str(cast(Mapping[str, Any], run_config["privacy"])["canary"])
        )
    except Exception as error:
        raise OutputValidationError("performance_smoke_summary_invalid") from error
    return summary


def _retrieve_performance_smoke_summary(
    ref: str,
    *,
    run_config: Mapping[str, Any],
    runner: ModuleType,
    manifest: Mapping[str, Any],
) -> None:
    pattern = (
        rf"^({re.escape(PERFORMANCE_SMOKE_OUTPUT_DIRECTORY)}/)?"
        rf"{re.escape(PERFORMANCE_SMOKE_SUMMARY)}$"
    )
    with tempfile.TemporaryDirectory(prefix="rsna-knee-performance-smoke-") as temporary:
        root = Path(temporary)
        _run_kaggle_cli(
            (
                "kernels",
                "output",
                ref,
                "--path",
                str(root),
                "--file-pattern",
                pattern,
                "--quiet",
            ),
            maximum=64 * 1024,
            allow_empty=True,
        )
        try:
            entries = list(root.rglob("*"))
        except OSError as error:
            raise OutputValidationError("performance_smoke_output_layout_invalid") from error
        directories = [path for path in entries if path.is_dir()]
        files = [path for path in entries if path.is_file()]
        expected_summaries = {
            root / PERFORMANCE_SMOKE_SUMMARY,
            root / PERFORMANCE_SMOKE_OUTPUT_DIRECTORY / PERFORMANCE_SMOKE_SUMMARY,
        }
        summaries = [path for path in files if path in expected_summaries]
        logs = [
            path for path in files if path.parent == root and SAFE_LOG_PATTERN.fullmatch(path.name)
        ]
        expected_directories = (
            {root / PERFORMANCE_SMOKE_OUTPUT_DIRECTORY}
            if summaries and summaries[0].parent == root / PERFORMANCE_SMOKE_OUTPUT_DIRECTORY
            else set()
        )
        if (
            any(path.is_symlink() for path in entries)
            or any(not path.is_file() and not path.is_dir() for path in entries)
            or len(summaries) != 1
            or len(logs) > 1
            or set(files) != {*summaries, *logs}
            or set(directories) != expected_directories
        ):
            raise OutputValidationError("performance_smoke_output_layout_invalid")
        _validate_performance_smoke_summary(
            _read_bounded(
                summaries[0],
                PERFORMANCE_SMOKE_SUMMARY_MAX_BYTES,
                "performance_smoke_summary_invalid",
            ),
            run_config=run_config,
            runner=runner,
            manifest=manifest,
        )
        if logs:
            try:
                runner._scan_downloadable(
                    _read_bounded(logs[0], 2 * 1024 * 1024, "performance_smoke_log_invalid"),
                    str(cast(Mapping[str, Any], run_config["privacy"])["canary"]),
                )
            except OutputValidationError:
                raise
            except Exception as error:
                raise OutputValidationError("performance_smoke_log_invalid") from error


def _retrieve_safe_qa_output(
    ref: str,
    run_config: Mapping[str, Any],
    runner: ModuleType,
    manifest: Mapping[str, Any],
) -> None:
    pattern = (
        r"^(dicom-qa-output/)?(sanitized_summary\.json|benchmark\.md|"
        r"sanitized_artifact_inventory\.json)$"
    )
    with tempfile.TemporaryDirectory(prefix="rsna-knee-safe-output-") as temporary:
        root = Path(temporary)
        _run_kaggle_cli(
            (
                "kernels",
                "output",
                ref,
                "--path",
                str(root),
                "--file-pattern",
                pattern,
                "--quiet",
            ),
            maximum=64 * 1024,
            allow_empty=True,
        )
        summary = validate_local_output(root, run_config, runner, manifest)
        _validate_qa_exit_gate(summary)


def _retrieve_safe_run_output(
    ref: str,
    run_config: Mapping[str, Any],
    runner: ModuleType,
    manifest: Mapping[str, Any],
) -> None:
    pattern = (
        r"^(dicom-qa-output/)?(sanitized_summary\.json|"
        r"sanitized_artifact_inventory\.json)$"
    )
    with tempfile.TemporaryDirectory(prefix="rsna-knee-safe-full-run-") as temporary:
        root = Path(temporary)
        _run_kaggle_cli(
            (
                "kernels",
                "output",
                ref,
                "--path",
                str(root),
                "--file-pattern",
                pattern,
                "--quiet",
            ),
            maximum=64 * 1024,
            allow_empty=True,
        )
        summary = validate_local_run_output(root, run_config, runner, manifest)
        _validate_run_exit_gate(summary)


def _validate_run_exit_gate(summary: Mapping[str, Any]) -> None:
    pipeline = summary.get("pipeline")
    selection = summary.get("selection")
    if (
        summary.get("status") != "complete_pending_comparison"
        or not isinstance(pipeline, dict)
        or pipeline.get("full_training_dataset_processed") is not True
        or pipeline.get("all_series_terminal") is not True
        or pipeline.get("integrity_gate") != "pass"
        or pipeline.get("unresolved_blockers") != "zero"
        or not isinstance(selection, dict)
        or selection.get("cohort_plan_status") != "complete"
        or selection.get("all_required_represented_registry_values_satisfy_quotas") is not True
    ):
        raise OutputValidationError("dicom_integrity_exit_gate_failed")


def _validate_qa_exit_gate(summary: Mapping[str, Any]) -> None:
    pipeline = summary.get("pipeline")
    if (
        summary.get("status") != "complete_pending_human_review"
        or not isinstance(pipeline, dict)
        or pipeline.get("integrity_gate") != "pass"
        or pipeline.get("unresolved_blockers") != "zero"
    ):
        raise OutputValidationError("dicom_integrity_exit_gate_failed")


def _validated_log_events(payload: bytes, runner: ModuleType, canary: str) -> list[dict[str, str]]:
    try:
        text = payload.decode("utf-8")
        runner._scan_downloadable(payload, canary)
    except Exception as error:
        raise OutputValidationError("log_privacy_invalid") from error
    try:
        wrapper = _json_value(payload, "log_schema_invalid")
    except OutputValidationError:
        wrapper = None
    if isinstance(wrapper, list):
        lines: list[str] = []
        if not wrapper or len(wrapper) > 10_000:
            raise OutputValidationError("log_schema_invalid")
        for record in wrapper:
            if (
                not isinstance(record, dict)
                or set(record) != {"stream_name", "time", "data"}
                or record.get("stream_name") not in {"stdout", "stderr"}
                or isinstance(record.get("time"), bool)
                or not isinstance(record.get("time"), (int, float))
                or not isinstance(record.get("data"), str)
            ):
                raise OutputValidationError("log_schema_invalid")
            if record["stream_name"] == "stdout":
                lines.extend(line for line in record["data"].splitlines() if line)
    else:
        lines = text.splitlines()
    events: list[dict[str, str]] = []
    for line in lines:
        try:
            event = _json_value(line.encode("utf-8"), "log_schema_invalid")
        except (UnicodeEncodeError, OutputValidationError) as error:
            raise OutputValidationError("log_schema_invalid") from error
        if (
            not isinstance(event, dict)
            or not {"event"} <= set(event) <= {"event", "phase", "code"}
            or any(
                not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value)
                for value in event.values()
            )
        ):
            raise OutputValidationError("log_schema_invalid")
        events.append({str(key): str(value) for key, value in event.items()})
    return events


def _expected_progress_events(
    runner: ModuleType,
    *,
    sequence_attribute: str = "PROGRESS_EVENT_SEQUENCE",
    event_name: str = "dicom_qa_progress",
) -> list[dict[str, str]]:
    sequence = getattr(runner, sequence_attribute, None)
    if not isinstance(sequence, tuple) or any(
        not isinstance(item, tuple)
        or len(item) != 2
        or any(
            not isinstance(value, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value) is None
            for value in item
        )
        for item in sequence
    ):
        raise OutputValidationError("log_schema_invalid")
    if event_name not in {"dicom_qa_progress", "dicom_qa_plan_progress"}:
        raise OutputValidationError("log_schema_invalid")
    return [{"event": event_name, "phase": phase, "code": code} for phase, code in sequence]


def validate_failure_log(
    root: Path, run_config: Mapping[str, Any], runner: ModuleType
) -> tuple[str, str]:
    try:
        entries = list(root.iterdir())
    except OSError as error:
        raise OutputValidationError("failure_log_layout_invalid") from error
    if (
        len(entries) != 1
        or entries[0].is_symlink()
        or not entries[0].is_file()
        or re.fullmatch(runner.SESSION_LOG_PATTERN, entries[0].name) is None
    ):
        raise OutputValidationError("failure_log_layout_invalid")
    events = _validated_log_events(
        _read_bounded(entries[0], 2 * 1024 * 1024, "failure_log_size_invalid"),
        runner,
        str(run_config["privacy"]["canary"]),
    )
    if len(events) < 2:
        raise OutputValidationError("failure_log_completion_invalid")
    progress = events[1:-1]
    terminal = events[-1]
    if events[:1] == [{"event": "dicom_qa_performance_smoke_started"}]:
        started_event = "dicom_qa_performance_smoke_started"
        failed_event = "dicom_qa_performance_smoke_failed"
        failure_phases = PERFORMANCE_SMOKE_FAILURE_PHASES
        allowed_progress_lengths = {
            "bundle": {0},
            "authentication": {0},
            "performance_smoke": {0, 1, 2},
            "output": {2},
        }
        expected_progress = [
            {
                "event": "dicom_qa_performance_smoke_progress",
                "phase": "performance_smoke",
                "code": code,
            }
            for code in ("start", "complete")
        ]
        terminal_keys = {"event", "phase", "code"}
        terminal_phase = terminal.get("phase")
    elif events[:1] == [{"event": "dicom_qa_review_started"}]:
        started_event = "dicom_qa_review_started"
        failed_event = "dicom_qa_review_failed"
        terminal_phase = "review"
        failure_phases = {terminal_phase}
        expected_progress = _expected_progress_events(
            runner,
            sequence_attribute="PLAN_PROGRESS_EVENT_SEQUENCE",
            event_name="dicom_qa_plan_progress",
        )
        allowed_progress_lengths = {terminal_phase: set(range(len(expected_progress) + 1))}
        terminal_keys = {"event", "code"}
    else:
        started_event = "dicom_qa_started"
        failed_event = "dicom_qa_failed"
        failure_phases = FAILURE_PHASES
        allowed_progress_lengths = None
        expected_progress = _expected_progress_events(runner)
        terminal_keys = {"event", "phase", "code"}
        terminal_phase = terminal.get("phase")
    if (
        events[0] != {"event": started_event}
        or set(terminal) != terminal_keys
        or terminal["event"] != failed_event
        or terminal_phase not in failure_phases
        or progress != expected_progress[: len(progress)]
        or (
            allowed_progress_lengths is not None
            and len(progress) not in allowed_progress_lengths[terminal_phase]
        )
    ):
        raise OutputValidationError("failure_log_completion_invalid")
    return terminal_phase, terminal["code"]


def validate_local_output(
    root: Path,
    run_config: Mapping[str, Any],
    runner: ModuleType,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        root_entries = list(root.iterdir())
    except OSError as error:
        raise OutputValidationError("local_output_layout_invalid") from error
    logs = [
        entry
        for entry in root_entries
        if entry.is_file() and re.fullmatch(runner.SESSION_LOG_PATTERN, entry.name)
    ]
    non_logs = [entry for entry in root_entries if entry not in logs]
    nested = len(non_logs) == 1 and non_logs[0].name == runner.OUTPUT_DIRECTORY
    if nested:
        output_root = non_logs[0]
        if output_root.is_symlink() or not output_root.is_dir():
            raise OutputValidationError("private_artifact_download_detected")
        try:
            entries = list(output_root.iterdir())
        except OSError as error:
            raise OutputValidationError("local_output_layout_invalid") from error
    else:
        output_root = root
        entries = non_logs
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise OutputValidationError("private_artifact_download_detected")
    expected = set(runner.DOWNLOADABLE_OUTPUT_POLICY)
    observed = {entry.name for entry in entries}
    if observed != expected or len(logs) > 1:
        raise OutputValidationError("local_output_allowlist_invalid")
    payloads = {
        name: _read_bounded(
            output_root / name,
            runner.DOWNLOADABLE_OUTPUT_POLICY[name][1],
            "local_output_size_invalid",
        )
        for name in expected
    }
    try:
        summary = runner._validate_summary(payloads["sanitized_summary.json"], run_config)
        if summary["provenance"]["runner_sha256"] != manifest["kernel"]["sha256"]:
            raise OutputValidationError("summary_runner_mismatch")
        if payloads["benchmark.md"] != runner._render_benchmark(summary):
            raise OutputValidationError("benchmark_document_mismatch")
        runner._scan_downloadable(payloads["benchmark.md"], str(run_config["privacy"]["canary"]))
        runner._validate_inventory(
            payloads["sanitized_artifact_inventory.json"],
            run_config=run_config,
            summary_payload=payloads["sanitized_summary.json"],
            benchmark_payload=payloads["benchmark.md"],
        )
    except OutputValidationError:
        raise
    except Exception as error:
        raise OutputValidationError("local_output_validation_failed") from error
    for log in logs:
        if _validated_log_events(
            _read_bounded(log, 2 * 1024 * 1024, "log_size_invalid"),
            runner,
            str(run_config["privacy"]["canary"]),
        ) != [
            {"event": "dicom_qa_review_started"},
            *_expected_progress_events(
                runner,
                sequence_attribute="PLAN_PROGRESS_EVENT_SEQUENCE",
                event_name="dicom_qa_plan_progress",
            ),
            {"event": "dicom_qa_review_template_complete"},
        ]:
            raise OutputValidationError("log_completion_invalid")
    return cast(dict[str, Any], summary)


def validate_local_run_output(
    root: Path,
    run_config: Mapping[str, Any],
    runner: ModuleType,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the two release-safe full-pass files without accepting QA artifacts."""

    try:
        root_entries = list(root.iterdir())
    except OSError as error:
        raise OutputValidationError("local_output_layout_invalid") from error
    logs = [
        entry
        for entry in root_entries
        if entry.is_file() and re.fullmatch(runner.SESSION_LOG_PATTERN, entry.name)
    ]
    non_logs = [entry for entry in root_entries if entry not in logs]
    nested = len(non_logs) == 1 and non_logs[0].name == runner.OUTPUT_DIRECTORY
    if nested:
        output_root = non_logs[0]
        if output_root.is_symlink() or not output_root.is_dir():
            raise OutputValidationError("private_artifact_download_detected")
        try:
            entries = list(output_root.iterdir())
        except OSError as error:
            raise OutputValidationError("local_output_layout_invalid") from error
    else:
        output_root = root
        entries = non_logs
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise OutputValidationError("private_artifact_download_detected")
    policy = getattr(runner, "RUN_DOWNLOADABLE_OUTPUT_POLICY", None)
    expected = _policy_names(runner, "RUN_DOWNLOADABLE_OUTPUT_POLICY")
    if expected != {"sanitized_summary.json", "sanitized_artifact_inventory.json"}:
        raise OutputValidationError("runner_output_policy_invalid")
    observed = {entry.name for entry in entries}
    if observed != expected or len(logs) > 1 or not isinstance(policy, dict):
        raise OutputValidationError("local_output_allowlist_invalid")
    try:
        payloads = {
            name: _read_bounded(
                output_root / name,
                cast(tuple[str, int], policy[name])[1],
                "local_output_size_invalid",
            )
            for name in expected
        }
        summary = runner._validate_run_summary(payloads["sanitized_summary.json"], run_config)
        if summary["provenance"]["runner_sha256"] != manifest["kernel"]["sha256"]:
            raise OutputValidationError("summary_runner_mismatch")
        runner._validate_run_inventory(
            payloads["sanitized_artifact_inventory.json"],
            run_config=run_config,
            summary_payload=payloads["sanitized_summary.json"],
        )
    except OutputValidationError:
        raise
    except Exception as error:
        raise OutputValidationError("local_output_validation_failed") from error
    for log in logs:
        if _validated_log_events(
            _read_bounded(log, 2 * 1024 * 1024, "log_size_invalid"),
            runner,
            str(run_config["privacy"]["canary"]),
        ) != [
            {"event": "dicom_qa_started"},
            *_expected_progress_events(runner),
            {"event": "dicom_qa_complete"},
        ]:
            raise OutputValidationError("log_completion_invalid")
    return cast(dict[str, Any], summary)


def _validate_template_listing(
    pages: Sequence[bytes], runner: ModuleType, finalizer: ModuleType
) -> None:
    records = _kernel_listing_records(pages)
    expected = f"{finalizer.TEMPLATE_OUTPUT_DIRECTORY}/{finalizer.REVIEW_PLAN_BASENAME}"
    observed_plan = False
    log_count = 0
    for record, _size in records:
        name = _safe_remote_name(record.get("name"))
        if name in {expected, str(finalizer.REVIEW_PLAN_BASENAME)}:
            if observed_plan:
                raise OutputValidationError("remote_size_invalid")
            observed_plan = True
        elif "/" not in name and re.fullmatch(runner.SESSION_LOG_PATTERN, name):
            log_count += 1
        else:
            raise OutputValidationError("remote_name_not_allowed")
    if not observed_plan or log_count > 1:
        raise OutputValidationError("remote_required_output_missing")


def _validate_optional_log_only_listing(pages: Sequence[bytes]) -> None:
    records = _kernel_listing_records(pages)
    if len(records) > 1:
        raise OutputValidationError("remote_size_invalid")
    for record, _size in records:
        name = _safe_remote_name(record.get("name"))
        if "/" in name or SAFE_LOG_PATTERN.fullmatch(name) is None:
            raise OutputValidationError("remote_name_not_allowed")


def _validate_review_session_listing(pages: Sequence[bytes]) -> None:
    records = _kernel_listing_records(pages)
    ledger_seen = False
    log_count = 0
    for record, _size in records:
        name = _safe_remote_name(record.get("name"))
        if name == REVIEW_SESSION_LEDGER:
            if ledger_seen:
                raise OutputValidationError("remote_size_invalid")
            ledger_seen = True
        elif "/" not in name and SAFE_LOG_PATTERN.fullmatch(name):
            log_count += 1
            if log_count > 1:
                raise OutputValidationError("remote_size_invalid")
        else:
            raise OutputValidationError("remote_name_not_allowed")
    if not ledger_seen:
        raise OutputValidationError("remote_required_output_missing")


def _validate_comparison_listing(
    pages: Sequence[bytes], runner: ModuleType, comparator: ModuleType
) -> None:
    records = _kernel_listing_records(pages)
    prefix = f"{comparator.OUTPUT_DIRECTORY}/"
    required = {
        prefix + comparator.PRIVATE_OUTPUT: 64 * 1024,
        prefix + comparator.SANITIZED_OUTPUT: 32 * 1024,
    }
    observed: set[str] = set()
    log_count = 0
    for record, _size in records:
        name = _safe_remote_name(record.get("name"))
        if name in required:
            canonical = name
        elif name in (comparator.PRIVATE_OUTPUT, comparator.SANITIZED_OUTPUT):
            canonical = prefix + name
        elif "/" not in name and re.fullmatch(runner.SESSION_LOG_PATTERN, name):
            log_count += 1
            continue
        else:
            raise OutputValidationError("remote_name_not_allowed")
        if canonical in observed:
            raise OutputValidationError("remote_size_invalid")
        observed.add(canonical)
    if observed != set(required) or log_count > 1:
        raise OutputValidationError("remote_required_output_missing")


def _validate_comparison_summary(payload: bytes) -> None:
    summary = _json_bytes(payload, "comparison_summary_invalid")
    expected = {
        "schema_version": 1,
        "artifact_type": "dicom-run-determinism-aggregate",
        "status": "pass",
        "independent_runs_compared": True,
        "exact_manifest_byte_equality": True,
        "deterministic_metrics_equal": True,
        "cohort_plan_byte_equality": True,
        "unresolved_mismatches": "zero",
        "private_case_details_downloaded": False,
    }
    if payload != _canonical_json_bytes(summary) or summary != expected:
        raise OutputValidationError("comparison_summary_invalid")


def _retrieve_comparison_summary(
    ref: str,
    *,
    run_config: Mapping[str, Any],
    runner: ModuleType,
    comparator: ModuleType,
) -> None:
    pattern = (
        rf"^({re.escape(comparator.OUTPUT_DIRECTORY)}/)?"
        rf"{re.escape(comparator.SANITIZED_OUTPUT)}$"
    )
    with tempfile.TemporaryDirectory(prefix="rsna-knee-comparison-summary-") as temporary:
        root = Path(temporary)
        _run_kaggle_cli(
            (
                "kernels",
                "output",
                ref,
                "--path",
                str(root),
                "--file-pattern",
                pattern,
                "--quiet",
            ),
            maximum=64 * 1024,
            allow_empty=True,
        )
        try:
            entries = list(root.rglob("*"))
            modes = {path: path.lstat().st_mode for path in entries}
        except OSError as error:
            raise OutputValidationError("comparison_output_layout_invalid") from error
        directories = [path for path, mode in modes.items() if stat.S_ISDIR(mode)]
        files = [path for path, mode in modes.items() if stat.S_ISREG(mode)]
        expected_summaries = {
            root / comparator.SANITIZED_OUTPUT,
            root / comparator.OUTPUT_DIRECTORY / comparator.SANITIZED_OUTPUT,
        }
        summaries = [path for path in files if path in expected_summaries]
        logs = [
            path
            for path in files
            if path.parent == root and re.fullmatch(runner.SESSION_LOG_PATTERN, path.name)
        ]
        expected_directories = (
            {root / comparator.OUTPUT_DIRECTORY}
            if summaries and summaries[0].parent == root / comparator.OUTPUT_DIRECTORY
            else set()
        )
        if (
            any(not stat.S_ISREG(mode) and not stat.S_ISDIR(mode) for mode in modes.values())
            or len(summaries) != 1
            or len(logs) > 1
            or set(files) != {*summaries, *logs}
            or set(directories) != expected_directories
        ):
            raise OutputValidationError("comparison_output_layout_invalid")
        _validate_comparison_summary(
            _read_bounded(summaries[0], 32 * 1024, "comparison_summary_invalid")
        )
        if logs:
            payload = _read_bounded(logs[0], 2 * 1024 * 1024, "comparison_log_invalid")
            try:
                runner._scan_downloadable(
                    payload,
                    cast(str, cast(Mapping[str, Any], run_config["privacy"])["canary"]),
                )
            except Exception as error:
                raise OutputValidationError("comparison_log_invalid") from error


def _validate_review_listing(pages: Sequence[bytes], finalizer: ModuleType) -> None:
    records = _kernel_listing_records(pages)
    prefix = f"{finalizer.OUTPUT_DIRECTORY}/"
    required = {
        prefix + finalizer.SANITIZED_SUMMARY: finalizer.MAX_SUMMARY_BYTES,
        prefix + finalizer.SANITIZED_PERFORMANCE: finalizer.MAX_PERFORMANCE_BYTES,
        prefix + finalizer.PRIVATE_COMPLETION: finalizer.MAX_LEDGER_BYTES,
    }
    observed: set[str] = set()
    log_count = 0
    for record, _size in records:
        name = _safe_remote_name(record.get("name"))
        if name in required:
            canonical = name
        elif name in (
            finalizer.SANITIZED_SUMMARY,
            finalizer.SANITIZED_PERFORMANCE,
            finalizer.PRIVATE_COMPLETION,
        ):
            canonical = prefix + name
        elif "/" not in name and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,99}\.log", name):
            log_count += 1
            continue
        else:
            raise OutputValidationError("remote_name_not_allowed")
        if canonical in observed:
            raise OutputValidationError("remote_size_invalid")
        observed.add(canonical)
    if observed != set(required) or log_count > 1:
        raise OutputValidationError("remote_required_output_missing")


def _retrieve_review_summary(
    ref: str,
    run_config: Mapping[str, Any],
    runner: ModuleType,
    finalizer: ModuleType,
    manifest: Mapping[str, Any],
) -> None:
    pattern = (
        rf"^({re.escape(finalizer.OUTPUT_DIRECTORY)}/)?"
        rf"({re.escape(finalizer.SANITIZED_SUMMARY)}|"
        rf"{re.escape(finalizer.SANITIZED_PERFORMANCE)})$"
    )
    with tempfile.TemporaryDirectory(prefix="rsna-knee-review-summary-") as temporary:
        root = Path(temporary)
        _run_kaggle_cli(
            (
                "kernels",
                "output",
                ref,
                "--path",
                str(root),
                "--file-pattern",
                pattern,
                "--quiet",
            ),
            maximum=64 * 1024,
            allow_empty=True,
        )
        files = [path for path in root.rglob("*") if path.is_file()]
        if any(path.is_symlink() for path in root.rglob("*")):
            raise OutputValidationError("review_output_layout_invalid")
        summaries = [path for path in files if path.name == finalizer.SANITIZED_SUMMARY]
        reports = [path for path in files if path.name == finalizer.SANITIZED_PERFORMANCE]
        logs = [path for path in files if re.fullmatch(runner.SESSION_LOG_PATTERN, path.name)]
        if len(summaries) != 1 or len(reports) != 1 or len(logs) > 1 or len(files) != 2 + len(logs):
            raise OutputValidationError("review_output_layout_invalid")
        payload = _read_bounded(summaries[0], finalizer.MAX_SUMMARY_BYTES, "review_summary_invalid")
        summary = _validate_review_summary_payload(payload, run_config, manifest, finalizer)
        _validate_performance_report_payload(
            _read_bounded(
                reports[0], finalizer.MAX_PERFORMANCE_BYTES, "performance_report_invalid"
            ),
            run_config,
            manifest,
            runner,
            finalizer,
            summary,
        )
        for log in logs:
            events = _validated_log_events(
                _read_bounded(log, 2 * 1024 * 1024, "log_size_invalid"),
                runner,
                str(run_config["privacy"]["canary"]),
            )
            if events != [
                {"event": "dicom_qa_review_started"},
                {"event": "dicom_qa_review_complete"},
            ]:
                raise OutputValidationError("review_log_completion_invalid")


def _validate_review_summary_payload(
    payload: bytes,
    run_config: Mapping[str, Any],
    manifest: Mapping[str, Any],
    finalizer: ModuleType,
) -> dict[str, Any]:
    try:
        decoded = _json_bytes(payload, "review_summary_invalid")
        if (
            payload != _canonical_json_bytes(decoded)
            or not isinstance(decoded.get("completed_at_utc"), str)
            or COMPLETION_TIMESTAMP_PATTERN.fullmatch(str(decoded["completed_at_utc"])) is None
        ):
            raise OutputValidationError("review_summary_invalid")
        summary = finalizer.validate_sanitized_summary(payload, run_config, manifest)
    except OutputValidationError:
        raise
    except Exception as error:
        raise OutputValidationError("review_summary_invalid") from error
    review = summary.get("review")
    check_results = review.get("check_results") if isinstance(review, dict) else None
    reviewed_range = (
        finalizer._reviewed_study_bounds(review.get("reviewed_studies"))
        if isinstance(review, dict)
        else None
    )
    eligible_range = (
        finalizer._k20_range_bounds(review.get("eligible_series_reviewed"))
        if isinstance(review, dict)
        else None
    )
    if (
        summary.get("status") != "complete"
        or not isinstance(review, dict)
        or not isinstance(check_results, dict)
        or reviewed_range is None
        or reviewed_range[0] < finalizer.MINIMUM_REVIEWED_STUDIES
        or eligible_range is None
        or eligible_range[0] < reviewed_range[0]
        or review.get("represented_strata")
        != "all_required_represented_registry_values_satisfy_quotas"
        or set(check_results) != set(REVIEW_CHECKS)
        or any(check_results[check] != "PASS" for check in REVIEW_CHECKS)
        or review.get("block_decisions") != "zero"
        or review.get("zero_blocks") is not True
    ):
        raise OutputValidationError("human_review_exit_gate_failed")
    return cast(dict[str, Any], summary)


def _validate_performance_report_payload(
    payload: bytes,
    run_config: Mapping[str, Any],
    manifest: Mapping[str, Any],
    runner: ModuleType,
    finalizer: ModuleType,
    human_review: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        report = finalizer.validate_sanitized_performance_report(
            payload, run_config, manifest, runner, human_review
        )
    except Exception as error:
        raise OutputValidationError("performance_report_invalid") from error
    performance = report.get("performance")
    budget = performance.get("inference_runtime_budget") if isinstance(performance, dict) else None
    review = report.get("human_review")
    exit_gate = report.get("exit_gate")
    reviewed_range = (
        finalizer._reviewed_study_bounds(review.get("reviewed_studies"))
        if isinstance(review, dict)
        else None
    )
    eligible_range = (
        finalizer._k20_range_bounds(review.get("eligible_series_reviewed"))
        if isinstance(review, dict)
        else None
    )
    if (
        report.get("status") != "pass"
        or not isinstance(performance, dict)
        or performance.get("determinism_status") != "pass_exact_independent_runs"
        or not isinstance(budget, dict)
        or budget.get("preprocessing_within_limit") is not True
        or budget.get("model_runtime_included") is not False
        or budget.get("model_viability_assessed") is not False
        or not isinstance(review, dict)
        or reviewed_range is None
        or eligible_range is None
        or review.get("represented_strata")
        != "all_required_represented_registry_values_satisfy_quotas"
        or review.get("all_nine_checks_pass") is not True
        or review.get("block_decisions") != "zero"
        or review.get("zero_blocks") is not True
        or not isinstance(exit_gate, dict)
        or exit_gate.get("unresolved_blockers") != "zero"
    ):
        raise OutputValidationError("performance_exit_gate_failed")
    return cast(dict[str, Any], report)


def _authenticate_source_manifest_kernel(
    *,
    source: Mapping[str, Any],
    competition_slug: str,
    bundle_dataset_ref: str,
    bundle_dataset_content: Mapping[str, tuple[int, str]],
) -> dict[str, object]:
    ref = cast(str, source["kernel_ref"])
    version = cast(int, source["kernel_version"])
    dataset_ref = cast(str, source["bundle_dataset_ref"])
    source_dataset_content = _source_manifest_dataset_content_policy(source)
    dataset_files = {name: size for name, (size, _digest) in source_dataset_content.items()}
    dataset_before = _authenticated_dataset_snapshot(dataset_ref, dataset_files)
    deadline = time.monotonic() + MAX_DATASET_CONTENT_SECONDS
    _authenticate_dataset_content(
        bundle_dataset_ref,
        bundle_dataset_content,
        deadline=deadline,
    )
    _authenticate_dataset_content(
        dataset_ref,
        source_dataset_content,
        deadline=deadline,
    )
    _assert_version_absent(ref, 2)
    _kernel_status_complete(ref)
    before = _pull_and_verify_exact_kernel(
        ref,
        version,
        cast(str, source["kernel_code_file"]),
        cast(str, source["kernel_code_sha256"]),
        expected_kernel_type="script",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=[],
        expected_competition_sources=[competition_slug],
    )
    _validate_source_manifest_listing(_authenticated_listing(ref, version), source)
    _assert_version_absent(ref, 2)
    _kernel_status_complete(ref)
    after = _pull_and_verify_exact_kernel(
        ref,
        version,
        cast(str, source["kernel_code_file"]),
        cast(str, source["kernel_code_sha256"]),
        expected_kernel_type="script",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=[],
        expected_competition_sources=[competition_slug],
    )
    dataset_after = _authenticated_dataset_snapshot(dataset_ref, dataset_files)
    if before != after:
        raise OutputValidationError("kernel_version_race")
    if dataset_before != dataset_after:
        raise OutputValidationError("dataset_version_race")
    return dataset_after


def _authenticate_performance_smoke_kernel(
    *,
    ref: str,
    dataset_ref: str,
    source_manifest_ref: str,
    competition_slug: str,
    run_config: Mapping[str, Any],
    runner: ModuleType,
    manifest: Mapping[str, Any],
) -> None:
    expected_hash, _policy_sha256 = _performance_smoke_identity(run_config, manifest)
    _assert_version_absent(ref, 2)
    _kernel_status_complete(ref)
    before = _pull_and_verify_exact_kernel(
        ref,
        1,
        "performance_smoke.py",
        expected_hash,
        expected_kernel_type="script",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=[source_manifest_ref],
        expected_competition_sources=[competition_slug],
    )
    _validate_performance_smoke_listing(_authenticated_listing(ref, 1))
    _retrieve_performance_smoke_summary(
        f"{ref}/1",
        run_config=run_config,
        runner=runner,
        manifest=manifest,
    )
    _assert_version_absent(ref, 2)
    _kernel_status_complete(ref)
    after = _pull_and_verify_exact_kernel(
        ref,
        1,
        "performance_smoke.py",
        expected_hash,
        expected_kernel_type="script",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=[source_manifest_ref],
        expected_competition_sources=[competition_slug],
    )
    if before != after:
        raise OutputValidationError("kernel_version_race")


def _authenticate_qa_run(
    *,
    ref: str,
    dataset_ref: str,
    source_manifest_ref: str,
    competition_slug: str,
    run_config: Mapping[str, Any],
    runner: ModuleType,
    manifest: Mapping[str, Any],
) -> None:
    kernel = cast(Mapping[str, Any], manifest["kernel"])
    expected_hash = cast(str, kernel["sha256"])
    _authenticate_kernel_api_version(ref, 1)
    _kernel_status_complete(ref)
    before = _pull_and_verify_exact_kernel(
        ref,
        1,
        "run.py",
        expected_hash,
        expected_kernel_type="script",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=[source_manifest_ref],
        expected_competition_sources=[competition_slug],
    )
    _validate_run_listing(_authenticated_listing(ref, 1), runner)
    _retrieve_safe_run_output(f"{ref}/1", run_config, runner, manifest)
    _authenticate_kernel_api_version(ref, 1)
    _kernel_status_complete(ref)
    after = _pull_and_verify_exact_kernel(
        ref,
        1,
        "run.py",
        expected_hash,
        expected_kernel_type="script",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=[source_manifest_ref],
        expected_competition_sources=[competition_slug],
    )
    if before != after:
        raise OutputValidationError("kernel_version_race")


def _authenticate_comparison_kernel(
    *,
    ref: str,
    dataset_ref: str,
    run_refs: Sequence[str],
    run_config: Mapping[str, Any],
    runner: ModuleType,
    manifest: Mapping[str, Any],
) -> None:
    record = cast(Mapping[str, Any], manifest["comparison"])
    expected_hash = cast(str, record["sha256"])
    comparator = _comparison_module(expected_hash)
    _authenticate_kernel_api_version(ref, 1)
    _kernel_status_complete(ref)
    before = _pull_and_verify_exact_kernel(
        ref,
        1,
        "compare_runs.py",
        expected_hash,
        expected_kernel_type="script",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=run_refs,
        expected_competition_sources=[],
    )
    _validate_comparison_listing(_authenticated_listing(ref, 1), runner, comparator)
    _retrieve_comparison_summary(
        f"{ref}/1", run_config=run_config, runner=runner, comparator=comparator
    )
    _authenticate_kernel_api_version(ref, 1)
    _kernel_status_complete(ref)
    after = _pull_and_verify_exact_kernel(
        ref,
        1,
        "compare_runs.py",
        expected_hash,
        expected_kernel_type="script",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=run_refs,
        expected_competition_sources=[],
    )
    if before != after:
        raise OutputValidationError("kernel_version_race")


def _authenticate_review_plan_kernel(
    *,
    ref: str,
    dataset_ref: str,
    kernel_sources: Sequence[str],
    competition_slug: str,
    run_config: Mapping[str, Any],
    runner: ModuleType,
    finalizer: ModuleType,
    manifest: Mapping[str, Any],
) -> None:
    record = cast(Mapping[str, Any], manifest["review_finalizer"])
    expected_hash = cast(str, record["sha256"])
    _authenticate_kernel_api_version(ref, 1)
    _kernel_status_complete(ref)
    before = _pull_and_verify_exact_kernel(
        ref,
        1,
        "finalize_review.py",
        expected_hash,
        expected_kernel_type="script",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=kernel_sources,
        expected_competition_sources=[competition_slug],
    )
    _validate_review_output_listing(_authenticated_listing(ref, 1), runner, finalizer=finalizer)
    _retrieve_safe_qa_output(f"{ref}/1", run_config, runner, manifest)
    _authenticate_kernel_api_version(ref, 1)
    _kernel_status_complete(ref)
    after = _pull_and_verify_exact_kernel(
        ref,
        1,
        "finalize_review.py",
        expected_hash,
        expected_kernel_type="script",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=kernel_sources,
        expected_competition_sources=[competition_slug],
    )
    if before != after:
        raise OutputValidationError("kernel_version_race")


def _authenticate_review_ui_template_kernel(
    *,
    ref: str,
    dataset_ref: str,
    kernel_sources: Sequence[str],
    manifest: Mapping[str, Any],
) -> None:
    record = cast(Mapping[str, Any], manifest["review_ui"])
    expected_hash = cast(str, record["sha256"])
    _authenticate_kernel_api_version(ref, 1)
    _kernel_status_complete(ref)
    before = _pull_and_verify_exact_kernel(
        ref,
        1,
        "review_ui.ipynb",
        expected_hash,
        expected_kernel_type="notebook",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=kernel_sources,
        expected_competition_sources=[],
    )
    _validate_optional_log_only_listing(_authenticated_listing(ref, 1))
    _authenticate_kernel_api_version(ref, 1)
    _kernel_status_complete(ref)
    after = _pull_and_verify_exact_kernel(
        ref,
        1,
        "review_ui.ipynb",
        expected_hash,
        expected_kernel_type="notebook",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=kernel_sources,
        expected_competition_sources=[],
    )
    if before != after:
        raise OutputValidationError("kernel_version_race")


def _authenticate_review_session_kernel(
    *,
    interpreter: Path,
    ref: str,
    parent_ref: str,
    dataset_ref: str,
    kernel_sources: Sequence[str],
    manifest: Mapping[str, Any],
) -> None:
    record = cast(Mapping[str, Any], manifest["review_ui"])
    expected_hash = cast(str, record["sha256"])
    _kernel_status_complete(ref)
    before = _pull_and_verify_exact_kernel(
        ref,
        1,
        "review_ui.ipynb",
        expected_hash,
        expected_kernel_type="notebook",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=kernel_sources,
        expected_competition_sources=[],
    )
    _verify_review_session_metadata(
        interpreter=interpreter,
        ref=ref,
        parent_ref=parent_ref,
        dataset_sources=[dataset_ref],
        kernel_sources=kernel_sources,
        competition_sources=[],
    )
    _validate_review_session_listing(_authenticated_listing(ref, 1))
    _kernel_status_complete(ref)
    _validate_review_session_listing(_authenticated_listing(ref, 1))
    _verify_review_session_metadata(
        interpreter=interpreter,
        ref=ref,
        parent_ref=parent_ref,
        dataset_sources=[dataset_ref],
        kernel_sources=kernel_sources,
        competition_sources=[],
    )
    after = _pull_and_verify_exact_kernel(
        ref,
        1,
        "review_ui.ipynb",
        expected_hash,
        expected_kernel_type="notebook",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=kernel_sources,
        expected_competition_sources=[],
    )
    if before != after:
        raise OutputValidationError("kernel_version_race")


def _authenticate_review_finalizer_kernel(
    *,
    ref: str,
    dataset_ref: str,
    kernel_sources: Sequence[str],
    run_config: Mapping[str, Any],
    runner: ModuleType,
    finalizer: ModuleType,
    manifest: Mapping[str, Any],
) -> None:
    record = cast(Mapping[str, Any], manifest["review_finalizer"])
    expected_hash = cast(str, record["sha256"])
    _authenticate_kernel_api_version(ref, 1)
    _kernel_status_complete(ref)
    before = _pull_and_verify_exact_kernel(
        ref,
        1,
        "finalize_review.py",
        expected_hash,
        expected_kernel_type="script",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=kernel_sources,
        expected_competition_sources=[],
    )
    _validate_review_listing(_authenticated_listing(ref, 1), finalizer)
    _retrieve_review_summary(f"{ref}/1", run_config, runner, finalizer, manifest)
    _authenticate_kernel_api_version(ref, 1)
    _kernel_status_complete(ref)
    after = _pull_and_verify_exact_kernel(
        ref,
        1,
        "finalize_review.py",
        expected_hash,
        expected_kernel_type="script",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=kernel_sources,
        expected_competition_sources=[],
    )
    if before != after:
        raise OutputValidationError("kernel_version_race")


def validate_authenticated_workflow(
    *,
    expected_version: int,
    stage: str,
    run_config: Mapping[str, Any],
    runner: ModuleType,
    manifest: Mapping[str, Any],
    finalizer_source: Path | None = None,
) -> None:
    """Authenticate the complete immutable private Chunk 5 QA/review chain."""

    if expected_version != 1:
        raise OutputValidationError("kernel_version_invalid")
    if stage not in WORKFLOW_STAGES:
        raise OutputValidationError("workflow_stage_invalid")
    stage_index = WORKFLOW_STAGES.index(stage)
    interpreter = _supported_kaggle_cli_interpreter()
    finalizer_record = cast(Mapping[str, Any], manifest.get("review_finalizer"))
    finalizer = _finalizer_module(
        cast(str, finalizer_record.get("sha256")),
        finalizer_source,
    )
    source, refs = _validated_workflow_identity(run_config, manifest, finalizer)
    dataset_ref = _bundle_dataset_ref(run_config)
    dataset_content = _bundle_dataset_content_policy(manifest)
    dataset_files = {name: size for name, (size, _digest) in dataset_content.items()}
    dataset_before = _authenticated_dataset_snapshot(dataset_ref, dataset_files)
    competition = run_config.get("competition")
    if not isinstance(competition, dict) or not isinstance(competition.get("slug"), str):
        raise OutputValidationError("review_identity_invalid")
    competition_slug = cast(str, competition["slug"])
    source_ref = cast(str, source["kernel_ref"])
    authenticated_kernel_refs: list[str] = []

    source_dataset_snapshot = _authenticate_source_manifest_kernel(
        source=source,
        competition_slug=competition_slug,
        bundle_dataset_ref=dataset_ref,
        bundle_dataset_content=dataset_content,
    )
    authenticated_kernel_refs.append(source_ref)
    if stage_index >= WORKFLOW_STAGES.index("performance-smoke"):
        _authenticate_performance_smoke_kernel(
            ref=refs["performance_smoke"],
            dataset_ref=dataset_ref,
            source_manifest_ref=source_ref,
            competition_slug=competition_slug,
            run_config=run_config,
            runner=runner,
            manifest=manifest,
        )
        authenticated_kernel_refs.append(refs["performance_smoke"])
    if stage_index >= WORKFLOW_STAGES.index("run-a"):
        _authenticate_qa_run(
            ref=refs["run_a"],
            dataset_ref=dataset_ref,
            source_manifest_ref=source_ref,
            competition_slug=competition_slug,
            run_config=run_config,
            runner=runner,
            manifest=manifest,
        )
        authenticated_kernel_refs.append(refs["run_a"])
    if stage_index >= WORKFLOW_STAGES.index("run-b"):
        _authenticate_qa_run(
            ref=refs["run_b"],
            dataset_ref=dataset_ref,
            source_manifest_ref=source_ref,
            competition_slug=competition_slug,
            run_config=run_config,
            runner=runner,
            manifest=manifest,
        )
        authenticated_kernel_refs.append(refs["run_b"])
    run_refs = [refs["run_a"], refs["run_b"]]
    if stage_index >= WORKFLOW_STAGES.index("comparison"):
        _authenticate_comparison_kernel(
            ref=refs["comparison"],
            dataset_ref=dataset_ref,
            run_refs=run_refs,
            run_config=run_config,
            runner=runner,
            manifest=manifest,
        )
        authenticated_kernel_refs.append(refs["comparison"])
    comparison_ref = refs["comparison"]
    plan_sources = [refs["performance_smoke"], *run_refs, comparison_ref]
    if stage_index >= WORKFLOW_STAGES.index("plan"):
        _authenticate_review_plan_kernel(
            ref=refs["review_plan"],
            dataset_ref=dataset_ref,
            kernel_sources=plan_sources,
            competition_slug=competition_slug,
            run_config=run_config,
            runner=runner,
            finalizer=finalizer,
            manifest=manifest,
        )
        authenticated_kernel_refs.append(refs["review_plan"])
    review_sources = [*run_refs, comparison_ref, refs["review_plan"]]
    if stage_index >= WORKFLOW_STAGES.index("ui"):
        _authenticate_review_ui_template_kernel(
            ref=refs["review_ui_template"],
            dataset_ref=dataset_ref,
            kernel_sources=review_sources,
            manifest=manifest,
        )
        authenticated_kernel_refs.append(refs["review_ui_template"])
    if stage_index >= WORKFLOW_STAGES.index("review"):
        _authenticate_review_session_kernel(
            interpreter=interpreter,
            ref=refs["review_session"],
            parent_ref=refs["review_ui_template"],
            dataset_ref=dataset_ref,
            kernel_sources=review_sources,
            manifest=manifest,
        )
        authenticated_kernel_refs.append(refs["review_session"])
    if stage_index >= WORKFLOW_STAGES.index("final"):
        _authenticate_review_finalizer_kernel(
            ref=refs["review_finalizer"],
            dataset_ref=dataset_ref,
            kernel_sources=[
                *run_refs,
                comparison_ref,
                refs["review_plan"],
                refs["review_session"],
            ],
            run_config=run_config,
            runner=runner,
            finalizer=finalizer,
            manifest=manifest,
        )
        authenticated_kernel_refs.append(refs["review_finalizer"])

    source_dataset_ref = cast(str, source["bundle_dataset_ref"])
    source_dataset_after = _authenticated_dataset_snapshot(
        source_dataset_ref, _source_manifest_dataset_files(source)
    )
    if source_dataset_snapshot != source_dataset_after:
        raise OutputValidationError("dataset_version_race")
    dataset_after = _authenticated_dataset_snapshot(dataset_ref, dataset_files)
    if dataset_before != dataset_after:
        raise OutputValidationError("dataset_version_race")
    for ref in authenticated_kernel_refs:
        _kernel_status_complete(ref)
        _authenticate_kernel_api_version(ref, 1)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-config", type=Path, required=True)
    parser.add_argument("--bundle-manifest", type=Path)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-bundle", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--workflow-kernel-version", type=int)
    parser.add_argument("--workflow-stage", choices=WORKFLOW_STAGES)
    mode.add_argument("--local-dir", type=Path)
    mode.add_argument("--failure-log-dir", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest_path = args.bundle_manifest or args.run_config.with_name("bundle-manifest.json")
    try:
        if (args.workflow_kernel_version is None) != (args.workflow_stage is None):
            raise OutputValidationError("workflow_stage_invalid")
        run_config, runner, manifest = load_verified_policy(
            args.run_config,
            manifest_path,
            expected_commit=args.expected_commit,
            expected_bundle=args.expected_bundle,
        )
        failure: tuple[str, str] | None = None
        suffix = ""
        if args.workflow_kernel_version is not None:
            finalizer_record = cast(Mapping[str, Any], manifest.get("review_finalizer"))
            finalizer_file = (
                finalizer_record.get("code_file") if isinstance(finalizer_record, Mapping) else None
            )
            validate_authenticated_workflow(
                expected_version=args.workflow_kernel_version,
                stage=args.workflow_stage,
                run_config=run_config,
                runner=runner,
                manifest=manifest,
                finalizer_source=(
                    manifest_path.parent / finalizer_file if finalizer_file is not None else None
                ),
            )
            mode = "workflow"
            suffix = f" stage={args.workflow_stage}"
            if args.workflow_stage == "final":
                suffix += " determinism=pass human_review=pass"
        elif args.failure_log_dir is not None:
            failure = validate_failure_log(args.failure_log_dir, run_config, runner)
            mode = "failure"
        else:
            validate_local_output(args.local_dir, run_config, runner, manifest)
            mode = "local"
    except OutputValidationError as error:
        print(f"dicom_qa_output_validation=FAIL code={error.code}")
        return 2
    except Exception:
        print("dicom_qa_output_validation=FAIL code=internal_error")
        return 2
    if failure is not None:
        suffix = f" phase={failure[0]} code={failure[1]}"
    print(f"dicom_qa_output_validation=PASS mode={mode}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
