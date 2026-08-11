"""Private exact-determinism comparison for independent Chunk 5 Kaggle runs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

MAX_MANIFEST_BYTES: Final = 512 * 1024**2
MAX_LINE_BYTES: Final = 16 * 1024**2
MAX_METRICS_BYTES: Final = 2 * 1024**2
MAX_COHORT_PLAN_BYTES: Final = 32 * 1024**2
OUTPUT_DIRECTORY: Final = "dicom_qa_comparison"
PRIVATE_OUTPUT: Final = "private_run_comparison.json"
SANITIZED_OUTPUT: Final = "sanitized_determinism.json"
SAFE_CODE: Final = re.compile(r"[a-z][a-z0-9_]{0,63}")
SAFE_FAILURE_COMPONENT: Final = re.compile(r"[A-Za-z0-9_.-]{1,160}")
UID: Final = re.compile(r"(?:[0-9]+\.)*[0-9]+\Z")
FILE_RECORD_KEYS: Final = frozenset(
    {"file_ordinal", "decode_state", "terminal_state", "resolution_state", "disposition"}
)
FAILURE_KEYS: Final = frozenset({"issue", "stage", "root_cause", "exception_type"})


class RunComparisonError(RuntimeError):
    """A fixed-code private comparison failure."""

    def __init__(self, code: str) -> None:
        self.code = code if SAFE_CODE.fullmatch(code) else "comparison_failed"
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class ManifestSnapshot:
    sha256: str
    bytes: int
    studies: int
    series: int
    files: int
    terminal_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class RunFiles:
    manifest: Path
    metrics: Path
    cohort_plan: Path


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise RunComparisonError("manifest_json_invalid")
        value[key] = item
    return value


def _canonical_line(value: object) -> bytes:
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


def _parse_line(payload: bytes) -> dict[str, Any]:
    if not payload.endswith(b"\n") or len(payload) > MAX_LINE_BYTES:
        raise RunComparisonError("manifest_json_invalid")
    try:
        value = json.loads(payload, object_pairs_hook=_object_without_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise RunComparisonError("manifest_json_invalid") from error
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise RunComparisonError("manifest_json_invalid")
    return value


def _file_record_counts(
    item: dict[str, Any], file_count: int
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    records = item.get("file_records")
    terminal = item.get("terminal_state")
    resolution = item.get("resolution_state")
    disposition = item.get("disposition")
    model_eligible = item.get("model_eligible")
    if (
        not isinstance(records, list)
        or len(records) != file_count
        or not isinstance(terminal, str)
        or SAFE_CODE.fullmatch(terminal) is None
        or not isinstance(resolution, str)
        or SAFE_CODE.fullmatch(resolution) is None
        or disposition not in {"model_eligible", "series_quarantine"}
        or type(model_eligible) is not bool
        or (
            terminal == "model_eligible"
            and (resolution != "pass" or disposition != "model_eligible" or not model_eligible)
        )
        or (
            terminal != "model_eligible"
            and (resolution == "pass" or disposition != "series_quarantine" or model_eligible)
        )
    ):
        raise RunComparisonError("manifest_series_invalid")
    if terminal == "source_access_blocked":
        source_failure = item.get("source_failure")
        if (
            resolution != "unresolved_blocker"
            or not isinstance(source_failure, str)
            or SAFE_CODE.fullmatch(source_failure) is None
        ):
            raise RunComparisonError("manifest_series_invalid")
        for ordinal, record in enumerate(records):
            if (
                not isinstance(record, dict)
                or set(record) != FILE_RECORD_KEYS
                or type(record.get("file_ordinal")) is not int
                or record.get("file_ordinal") != ordinal
                or record.get("decode_state") != "not_attempted"
                or record.get("terminal_state") != terminal
                or record.get("resolution_state") != resolution
                or record.get("disposition") != "series_quarantine"
            ):
                raise RunComparisonError("manifest_file_records_invalid")
        return (
            ({terminal: file_count} if file_count else {}),
            ({resolution: file_count} if file_count else {}),
            ({"series_quarantine": file_count} if file_count else {}),
        )
    if file_count == 0 or item.get("source_failure") is not None:
        raise RunComparisonError("manifest_series_invalid")

    terminal_counts: dict[str, int] = {}
    resolution_counts: dict[str, int] = {}
    disposition_counts: dict[str, int] = {}
    for ordinal, record in enumerate(records):
        if (
            not isinstance(record, dict)
            or type(record.get("file_ordinal")) is not int
            or record.get("file_ordinal") != ordinal
            or record.get("decode_state") not in {"pass", "failed"}
        ):
            raise RunComparisonError("manifest_file_records_invalid")
        failed = record["decode_state"] == "failed"
        if set(record) != FILE_RECORD_KEYS | ({"failure"} if failed else set()):
            raise RunComparisonError("manifest_file_records_invalid")
        file_terminal = record["terminal_state"]
        file_resolution = record["resolution_state"]
        file_disposition = record["disposition"]
        if (
            not isinstance(file_terminal, str)
            or SAFE_CODE.fullmatch(file_terminal) is None
            or not isinstance(file_resolution, str)
            or SAFE_CODE.fullmatch(file_resolution) is None
            or not isinstance(file_disposition, str)
            or SAFE_CODE.fullmatch(file_disposition) is None
        ):
            raise RunComparisonError("manifest_file_records_invalid")
        if failed:
            failure = record["failure"]
            if (
                terminal != "decode_blocked"
                or file_terminal != "decode_blocked"
                or file_resolution not in {"excluded_unusable_source", "unresolved_blocker"}
                or file_disposition != "file_quarantine"
                or not isinstance(failure, dict)
                or set(failure) != FAILURE_KEYS
                or any(
                    value is not None
                    and (
                        not isinstance(value, str)
                        or SAFE_FAILURE_COMPONENT.fullmatch(value) is None
                    )
                    for value in failure.values()
                )
                or failure.get("issue") is None
                or failure.get("stage") is None
            ):
                raise RunComparisonError("manifest_file_records_invalid")
        elif (
            file_terminal != terminal
            or file_resolution != resolution
            or file_disposition
            != ("included_in_model_series" if model_eligible else "series_quarantine")
        ):
            raise RunComparisonError("manifest_file_records_invalid")
        terminal_counts[file_terminal] = terminal_counts.get(file_terminal, 0) + 1
        resolution_counts[file_resolution] = resolution_counts.get(file_resolution, 0) + 1
        disposition_counts[file_disposition] = disposition_counts.get(file_disposition, 0) + 1
    if terminal == "decode_blocked" and disposition_counts.get("file_quarantine", 0) == 0:
        raise RunComparisonError("manifest_file_records_invalid")
    return terminal_counts, resolution_counts, disposition_counts


def inspect_manifest(path: Path) -> ManifestSnapshot:
    """Validate one private manifest and return aggregate-only comparison state."""

    try:
        if path.is_symlink() or not path.is_file():
            raise RunComparisonError("manifest_file_invalid")
        size = path.stat().st_size
        if size <= 0 or size > MAX_MANIFEST_BYTES:
            raise RunComparisonError("manifest_file_invalid")
    except OSError as error:
        raise RunComparisonError("manifest_file_invalid") from error

    digest = hashlib.sha256()
    studies = 0
    series = 0
    files = 0
    terminal_counts: dict[str, int] = {}
    resolution_counts: dict[str, int] = {}
    file_terminal_counts: dict[str, int] = {}
    file_resolution_counts: dict[str, int] = {}
    file_disposition_counts: dict[str, int] = {}
    footer: dict[str, Any] | None = None
    bytes_read = 0
    try:
        with path.open("rb") as stream:
            for ordinal, payload in enumerate(stream):
                bytes_read += len(payload)
                digest.update(payload)
                record = _parse_line(payload)
                record_type = record.get("record_type")
                if ordinal == 0:
                    if (
                        record_type != "header"
                        or record.get("schema_version") != 1
                        or record.get("artifact_type") != "private-dicom-full-run-manifest"
                    ):
                        raise RunComparisonError("manifest_header_invalid")
                    continue
                if footer is not None:
                    raise RunComparisonError("manifest_footer_invalid")
                if record_type == "footer":
                    footer = record
                    continue
                if record_type != "study" or record.get("study_ordinal") != studies:
                    raise RunComparisonError("manifest_study_invalid")
                study_series = record.get("series")
                if not isinstance(study_series, list) or not study_series:
                    raise RunComparisonError("manifest_study_invalid")
                studies += 1
                for item in study_series:
                    if not isinstance(item, dict):
                        raise RunComparisonError("manifest_series_invalid")
                    file_count = item.get("files")
                    terminal = item.get("terminal_state")
                    if (
                        not isinstance(file_count, int)
                        or isinstance(file_count, bool)
                        or file_count < 0
                        or not isinstance(terminal, str)
                        or SAFE_CODE.fullmatch(terminal) is None
                    ):
                        raise RunComparisonError("manifest_series_invalid")
                    series_file_counts = _file_record_counts(item, file_count)
                    series += 1
                    files += file_count
                    terminal_counts[terminal] = terminal_counts.get(terminal, 0) + 1
                    resolution = str(item["resolution_state"])
                    resolution_counts[resolution] = resolution_counts.get(resolution, 0) + 1
                    for aggregate, additions in zip(
                        (file_terminal_counts, file_resolution_counts, file_disposition_counts),
                        series_file_counts,
                        strict=True,
                    ):
                        for key, count in additions.items():
                            aggregate[key] = aggregate.get(key, 0) + count
    except RunComparisonError:
        raise
    except OSError as error:
        raise RunComparisonError("manifest_read_failed") from error

    try:
        stable_size = path.stat().st_size
    except OSError as error:
        raise RunComparisonError("manifest_read_failed") from error
    if footer is None or studies < 1 or files < 1 or bytes_read != size or stable_size != size:
        raise RunComparisonError("manifest_footer_invalid")
    expected_terminal = dict(sorted(terminal_counts.items()))
    if (
        footer.get("studies") != studies
        or footer.get("series") != series
        or footer.get("files") != files
        or footer.get("terminal_counts") != expected_terminal
        or footer.get("resolution_counts") != dict(sorted(resolution_counts.items()))
        or footer.get("file_terminal_counts") != dict(sorted(file_terminal_counts.items()))
        or footer.get("file_resolution_counts") != dict(sorted(file_resolution_counts.items()))
        or footer.get("file_disposition_counts") != dict(sorted(file_disposition_counts.items()))
    ):
        raise RunComparisonError("manifest_reconciliation_failed")
    return ManifestSnapshot(
        sha256=digest.hexdigest(),
        bytes=size,
        studies=studies,
        series=series,
        files=files,
        terminal_counts=tuple(expected_terminal.items()),
    )


def _files_equal(left: Path, right: Path) -> bool:
    with left.open("rb") as left_stream, right.open("rb") as right_stream:
        while True:
            left_block = left_stream.read(1024 * 1024)
            right_block = right_stream.read(1024 * 1024)
            if left_block != right_block:
                return False
            if not left_block:
                return True


def compare_run_manifests(run_a: Path, run_b: Path) -> ManifestSnapshot:
    """Require exact equality of two independently produced deterministic manifests."""

    left = inspect_manifest(run_a)
    right = inspect_manifest(run_b)
    if left != right or not _files_equal(run_a, run_b):
        raise RunComparisonError("deterministic_manifest_mismatch")
    return left


def _read_metrics(path: Path, snapshot: ManifestSnapshot) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file():
            raise RunComparisonError("run_metrics_invalid")
        payload = path.read_bytes()
    except OSError as error:
        raise RunComparisonError("run_metrics_invalid") from error
    if not 0 < len(payload) <= MAX_METRICS_BYTES:
        raise RunComparisonError("run_metrics_invalid")
    value = _parse_line(payload)
    if (
        value.get("schema_version") != 1
        or value.get("artifact_type") != "private-dicom-full-run-metrics"
        or value.get("studies_processed") != snapshot.studies
        or value.get("series_processed") != snapshot.series
        or value.get("files_processed") != snapshot.files
        or value.get("terminal_counts") != dict(snapshot.terminal_counts)
        or value.get("manifest_sha256") != snapshot.sha256
    ):
        raise RunComparisonError("run_metrics_invalid")
    return value


def _read_canonical_object(path: Path, maximum: int, code: str) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file():
            raise RunComparisonError(code)
        payload = path.read_bytes()
        if not 0 < len(payload) <= maximum or path.stat().st_size != len(payload):
            raise RunComparisonError(code)
    except OSError as error:
        raise RunComparisonError(code) from error
    try:
        return _parse_line(payload)
    except RunComparisonError as error:
        raise RunComparisonError(code) from error


def _cohort_plan_payload(path: Path, snapshot: ManifestSnapshot) -> bytes:
    value = _read_canonical_object(path, MAX_COHORT_PLAN_BYTES, "cohort_plan_invalid")
    provenance = value.get("provenance")
    selection = value.get("selection")
    coverage = value.get("coverage")
    representatives = value.get("representatives")
    studies = value.get("studies")
    if (
        set(value)
        != {
            "schema_version",
            "artifact_type",
            "status",
            "provenance",
            "selection",
            "coverage",
            "representatives",
            "studies",
        }
        or value.get("schema_version") != 1
        or value.get("artifact_type") != "private-dicom-qa-cohort-plan"
        or value.get("status") != "complete_pending_comparison"
        or not isinstance(provenance, dict)
        or set(provenance)
        != {
            "git_commit",
            "bundle_sha256",
            "runner_sha256",
            "source_manifest_identity",
            "full_run_manifest_sha256",
            "qa_cohort_selection_version",
            "qa_stratum_registry_version",
            "qa_stratum_registry_sha256",
        }
        or provenance.get("full_run_manifest_sha256") != snapshot.sha256
        or any(
            not isinstance(provenance.get(key), str)
            or re.fullmatch(r"[0-9a-f]{64}", str(provenance[key])) is None
            for key in ("bundle_sha256", "runner_sha256", "qa_stratum_registry_sha256")
        )
        or not isinstance(provenance.get("git_commit"), str)
        or re.fullmatch(r"[0-9a-f]{40}", str(provenance["git_commit"])) is None
        or not isinstance(provenance.get("source_manifest_identity"), dict)
        or not isinstance(selection, dict)
        or set(selection)
        != {
            "minimum_studies",
            "selected_studies",
            "eligible_series",
            "cohort_sha256",
        }
        or any(
            type(selection.get(key)) is not int or int(selection[key]) < 1
            for key in ("minimum_studies", "selected_studies", "eligible_series")
        )
        or selection["minimum_studies"] < 100
        or selection["selected_studies"] < selection["minimum_studies"]
        or selection["eligible_series"] < selection["selected_studies"]
        or not isinstance(selection.get("cohort_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", str(selection["cohort_sha256"])) is None
        or not isinstance(coverage, dict)
        or set(coverage) != {"ledger", "ledger_sha256"}
        or not isinstance(coverage.get("ledger"), dict)
        or not isinstance(coverage.get("ledger_sha256"), str)
        or coverage["ledger_sha256"]
        != hashlib.sha256(_canonical_line(coverage["ledger"])).hexdigest()
        or not isinstance(representatives, list)
        or not representatives
        or not isinstance(studies, list)
        or len(studies) != selection["selected_studies"]
    ):
        raise RunComparisonError("cohort_plan_invalid")
    observed_studies: set[str] = set()
    eligible_by_study: dict[str, set[str]] = {}
    eligible_series = 0
    for study in studies:
        if (
            not isinstance(study, dict)
            or set(study)
            != {
                "study_uid",
                "selection_stratum",
                "memberships",
                "eligible_series_uids",
            }
            or not isinstance(study.get("study_uid"), str)
            or UID.fullmatch(study["study_uid"]) is None
            or study["study_uid"] in observed_studies
            or not isinstance(study.get("selection_stratum"), list)
            or not isinstance(study.get("memberships"), list)
            or not study["memberships"]
            or not isinstance(study.get("eligible_series_uids"), list)
            or not study["eligible_series_uids"]
            or study["eligible_series_uids"] != sorted(set(study["eligible_series_uids"]))
            or any(
                not isinstance(item, str) or UID.fullmatch(item) is None
                for item in study["eligible_series_uids"]
            )
        ):
            raise RunComparisonError("cohort_plan_invalid")
        observed_studies.add(study["study_uid"])
        eligible_by_study[study["study_uid"]] = set(study["eligible_series_uids"])
        eligible_series += len(study["eligible_series_uids"])
    if eligible_series != selection["eligible_series"]:
        raise RunComparisonError("cohort_plan_invalid")
    for representative in representatives:
        if (
            not isinstance(representative, dict)
            or set(representative) != {"profile", "slice_count", "study_uid", "series_uid"}
            or representative.get("profile") not in {"small", "median", "large"}
            or type(representative.get("slice_count")) is not int
            or representative["slice_count"] < 1
            or not isinstance(representative.get("study_uid"), str)
            or not isinstance(representative.get("series_uid"), str)
            or representative["series_uid"]
            not in eligible_by_study.get(representative["study_uid"], set())
        ):
            raise RunComparisonError("cohort_plan_invalid")
    return _canonical_line(value)


def _discover_runs(input_root: Path) -> tuple[RunFiles, RunFiles]:
    try:
        resolved_root = input_root.resolve(strict=True)
        manifests = sorted(input_root.rglob("private_full_run_manifest.jsonl"))
    except OSError as error:
        raise RunComparisonError("run_inputs_invalid") from error
    if len(manifests) != 2:
        raise RunComparisonError("run_inputs_invalid")
    runs: list[RunFiles] = []
    for manifest in manifests:
        try:
            resolved = manifest.resolve(strict=True)
            resolved.relative_to(resolved_root)
        except (OSError, ValueError) as error:
            raise RunComparisonError("run_inputs_invalid") from error
        metrics = manifest.with_name("private_full_run_metrics.json")
        cohort_plan = manifest.with_name("private_cohort_plan.json")
        if any(
            candidate.is_symlink() or not candidate.is_file()
            for candidate in (manifest, metrics, cohort_plan)
        ):
            raise RunComparisonError("run_inputs_invalid")
        runs.append(RunFiles(manifest, metrics, cohort_plan))
    return runs[0], runs[1]


def _write_new(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def compare_private_run_roots(input_root: Path, output_root: Path) -> None:
    """Discover two immutable run outputs and write private plus release-safe evidence."""

    run_a, run_b = _discover_runs(input_root)
    snapshot = compare_run_manifests(run_a.manifest, run_b.manifest)
    metrics_a = _read_metrics(run_a.metrics, snapshot)
    metrics_b = _read_metrics(run_b.metrics, snapshot)
    deterministic_metric_keys = (
        "studies_processed",
        "series_processed",
        "files_processed",
        "terminal_counts",
        "model_eligible_series",
        "logical_cache_bytes",
        "manifest_sha256",
        "qa_cohort_selection",
        "cohort_plan_sha256",
        "coverage_ledger_sha256",
    )
    if any(metrics_a.get(key) != metrics_b.get(key) for key in deterministic_metric_keys):
        raise RunComparisonError("deterministic_metrics_mismatch")
    cohort_plan_a = _cohort_plan_payload(run_a.cohort_plan, snapshot)
    cohort_plan_b = _cohort_plan_payload(run_b.cohort_plan, snapshot)
    if cohort_plan_a != cohort_plan_b or not _files_equal(run_a.cohort_plan, run_b.cohort_plan):
        raise RunComparisonError("deterministic_cohort_plan_mismatch")
    cohort_plan_sha256 = hashlib.sha256(cohort_plan_a).hexdigest()
    if any(
        metrics.get("cohort_plan_sha256") != cohort_plan_sha256
        for metrics in (metrics_a, metrics_b)
    ):
        raise RunComparisonError("deterministic_metrics_mismatch")
    if output_root.exists() or output_root.is_symlink():
        raise RunComparisonError("comparison_output_exists")
    staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.", dir=output_root.parent))
    try:
        staging.chmod(0o700)
        private = _canonical_line(
            {
                "schema_version": 1,
                "artifact_type": "private-dicom-run-comparison",
                "status": "pass",
                "exact_manifest_byte_equality": True,
                "cohort_plan_byte_equality": True,
                "cohort_plan_sha256": cohort_plan_sha256,
                "manifest_sha256": snapshot.sha256,
                "studies": snapshot.studies,
                "series": snapshot.series,
                "files": snapshot.files,
                "terminal_counts": dict(snapshot.terminal_counts),
                "deterministic_metric_keys": list(deterministic_metric_keys),
                "expected_nondeterministic_fields": [
                    "phase_timings",
                    "wall_time",
                    "cpu_time",
                    "cpu_utilization",
                    "throughput",
                    "peak_memory",
                ],
                "unresolved_mismatches": 0,
            }
        )
        sanitized = _canonical_line(
            {
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
        )
        _write_new(staging / PRIVATE_OUTPUT, private)
        _write_new(staging / SANITIZED_OUTPUT, sanitized)
        staging.rename(output_root)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> int:
    try:
        input_root = Path(os.environ.get("KAGGLE_INPUT_ROOT", "/kaggle/input"))
        output_root = (
            Path(os.environ.get("KAGGLE_WORKING_ROOT", "/kaggle/working")) / OUTPUT_DIRECTORY
        )
        compare_private_run_roots(input_root, output_root)
    except BaseException:
        print("dicom_qa_comparison_failed", file=sys.stderr)
        return 1
    print("dicom_qa_comparison_complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
