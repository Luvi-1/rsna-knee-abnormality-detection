from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _module(repo_root: Path) -> ModuleType:
    path = repo_root / "kaggle" / "dicom_qa" / "compare_runs.py"
    spec = importlib.util.spec_from_file_location("dicom_qa_compare_runs", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _line(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii")


def _manifest(
    path: Path,
    *,
    checksum: str = "a" * 64,
    footer_files: int | None = None,
    file_ordinals: tuple[int, ...] = (0, 1),
    failed_ordinal: int | None = None,
    footer_override: dict[str, object] | None = None,
    source_blocked_files: int | None = None,
) -> None:
    terminal = "decode_blocked" if failed_ordinal is not None else "model_eligible"
    resolution = "unresolved_blocker" if failed_ordinal is not None else "pass"
    file_records = [
        {
            "file_ordinal": ordinal,
            "decode_state": "failed" if ordinal == failed_ordinal else "pass",
            **(
                {
                    "failure": {
                        "issue": "pixel_decode_failed",
                        "stage": "pixel_decode",
                        "root_cause": "decoder_unavailable",
                        "exception_type": "RuntimeError",
                    }
                }
                if ordinal == failed_ordinal
                else {}
            ),
            "terminal_state": terminal,
            "resolution_state": resolution,
            "disposition": (
                "file_quarantine"
                if ordinal == failed_ordinal
                else "series_quarantine"
                if failed_ordinal is not None
                else "included_in_model_series"
            ),
        }
        for ordinal in file_ordinals
    ]
    series = [
        {
            "series_uid": "private-series",
            "files": 2,
            "file_records": file_records,
            "source_failure": None,
            "terminal_state": terminal,
            "resolution_state": resolution,
            "disposition": (
                "series_quarantine" if failed_ordinal is not None else "model_eligible"
            ),
            "model_eligible": failed_ordinal is None,
            "model_output_reconstruction": {"output_checksum": checksum},
        }
    ]
    terminal_counts = {terminal: 1}
    resolution_counts = {resolution: 1}
    if source_blocked_files is not None:
        series.append(
            {
                "series_uid": "private-source-blocked-series",
                "files": source_blocked_files,
                "file_records": [
                    {
                        "file_ordinal": ordinal,
                        "decode_state": "not_attempted",
                        "terminal_state": "source_access_blocked",
                        "resolution_state": "unresolved_blocker",
                        "disposition": "series_quarantine",
                    }
                    for ordinal in range(source_blocked_files)
                ],
                "source_failure": "series_directory_invalid",
                "terminal_state": "source_access_blocked",
                "resolution_state": "unresolved_blocker",
                "disposition": "series_quarantine",
                "model_eligible": False,
                "model_output_reconstruction": None,
            }
        )
        terminal_counts["source_access_blocked"] = 1
        resolution_counts["unresolved_blocker"] = resolution_counts.get("unresolved_blocker", 0) + 1
    file_terminal_counts = {terminal: 2}
    file_resolution_counts = {resolution: 2}
    file_disposition_counts = (
        {"file_quarantine": 1, "series_quarantine": 1}
        if failed_ordinal is not None
        else {"included_in_model_series": 2}
    )
    if source_blocked_files:
        file_terminal_counts["source_access_blocked"] = source_blocked_files
        file_resolution_counts["unresolved_blocker"] = (
            file_resolution_counts.get("unresolved_blocker", 0) + source_blocked_files
        )
        file_disposition_counts["series_quarantine"] = (
            file_disposition_counts.get("series_quarantine", 0) + source_blocked_files
        )
    footer = {
        "record_type": "footer",
        "studies": 1,
        "series": len(series),
        "files": 2 + (source_blocked_files or 0) if footer_files is None else footer_files,
        "terminal_counts": dict(sorted(terminal_counts.items())),
        "resolution_counts": dict(sorted(resolution_counts.items())),
        "file_terminal_counts": file_terminal_counts,
        "file_resolution_counts": file_resolution_counts,
        "file_disposition_counts": file_disposition_counts,
        "logical_cache_bytes": 128,
    }
    if footer_override is not None:
        footer.update(footer_override)
    records = (
        {
            "schema_version": 1,
            "artifact_type": "private-dicom-full-run-manifest",
            "record_type": "header",
            "provenance": {"bundle_sha256": "b" * 64},
        },
        {
            "record_type": "study",
            "study_ordinal": 0,
            "study_uid": "private-study",
            "missing_series_mask": [False, True],
            "series": series,
        },
        footer,
    )
    path.write_bytes(b"".join(_line(record) for record in records))


def test_exact_independent_manifests_compare_and_mismatch_fails(tmp_path: Path) -> None:
    module = _module(Path(__file__).parents[1])
    run_a = tmp_path / "run-a.jsonl"
    run_b = tmp_path / "run-b.jsonl"
    _manifest(run_a)
    _manifest(run_b)

    snapshot = module.compare_run_manifests(run_a, run_b)
    assert (snapshot.studies, snapshot.series, snapshot.files) == (1, 1, 2)

    _manifest(run_b, checksum="c" * 64)
    with pytest.raises(module.RunComparisonError, match="deterministic_manifest_mismatch"):
        module.compare_run_manifests(run_a, run_b)

    _manifest(run_a, failed_ordinal=0)
    _manifest(run_b, failed_ordinal=1)
    with pytest.raises(module.RunComparisonError, match="deterministic_manifest_mismatch"):
        module.compare_run_manifests(run_a, run_b)


def test_manifest_parser_rejects_duplicate_keys_and_bad_reconciliation(tmp_path: Path) -> None:
    module = _module(Path(__file__).parents[1])
    malformed = tmp_path / "duplicate.jsonl"
    malformed.write_bytes(
        b'{"artifact_type":"private-dicom-full-run-manifest","record_type":"header",'
        b'"schema_version":1,"schema_version":1}\n'
    )
    with pytest.raises(module.RunComparisonError, match="manifest_json_invalid"):
        module.inspect_manifest(malformed)

    bad = tmp_path / "bad.jsonl"
    _manifest(bad, footer_files=3)
    with pytest.raises(module.RunComparisonError, match="manifest_reconciliation_failed"):
        module.inspect_manifest(bad)


@pytest.mark.parametrize("file_ordinals", [(0, 2), (0, 0)])
def test_manifest_parser_rejects_skipped_or_duplicate_file_ordinals(
    tmp_path: Path, file_ordinals: tuple[int, ...]
) -> None:
    module = _module(Path(__file__).parents[1])
    malformed = tmp_path / "malformed-file-ordinals.jsonl"
    _manifest(malformed, file_ordinals=file_ordinals)

    with pytest.raises(module.RunComparisonError, match="manifest_file_records_invalid"):
        module.inspect_manifest(malformed)


@pytest.mark.parametrize(
    ("footer_key", "value"),
    [
        ("file_terminal_counts", {"model_eligible": 1}),
        ("file_resolution_counts", {"pass": 1}),
        ("file_disposition_counts", {"included_in_model_series": 1}),
    ],
)
def test_manifest_parser_rejects_file_footer_count_mismatch(
    tmp_path: Path, footer_key: str, value: dict[str, int]
) -> None:
    module = _module(Path(__file__).parents[1])
    malformed = tmp_path / f"bad-{footer_key}.jsonl"
    _manifest(malformed, footer_override={footer_key: value})

    with pytest.raises(module.RunComparisonError, match="manifest_reconciliation_failed"):
        module.inspect_manifest(malformed)


def test_manifest_parser_allows_contractual_zero_file_source_access_block(
    tmp_path: Path,
) -> None:
    module = _module(Path(__file__).parents[1])
    manifest = tmp_path / "manifest.jsonl"
    _manifest(manifest, source_blocked_files=0)

    snapshot = module.inspect_manifest(manifest)
    assert (snapshot.series, snapshot.files) == (2, 2)


def test_manifest_parser_reconciles_partial_source_access_block(tmp_path: Path) -> None:
    module = _module(Path(__file__).parents[1])
    manifest = tmp_path / "manifest.jsonl"
    _manifest(manifest, source_blocked_files=3)

    snapshot = module.inspect_manifest(manifest)
    assert (snapshot.series, snapshot.files) == (2, 5)


def _metrics(path: Path, snapshot: object, *, model_eligible: int = 1) -> None:
    path.write_bytes(
        _line(
            {
                "schema_version": 1,
                "artifact_type": "private-dicom-full-run-metrics",
                "studies_processed": snapshot.studies,
                "series_processed": snapshot.series,
                "files_processed": snapshot.files,
                "terminal_counts": dict(snapshot.terminal_counts),
                "model_eligible_series": model_eligible,
                "logical_cache_bytes": 128,
                "manifest_sha256": snapshot.sha256,
                "total_wall_seconds": 1.0,
            }
        )
    )


def _case_index_and_inventory(root: Path, *, study_marker: str = "same") -> None:
    case_payload = _line(
        {
            "schema_version": 1,
            "artifact_type": "private-dicom-qa-case-index",
            "status": "pending_private_human_review",
            "provenance": {
                "git_commit": "a" * 40,
                "bundle_sha256": "b" * 64,
            },
            "input_identity": {"source": "synthetic"},
            "qa_cohort_selection": {"cohort": "fixed"},
            "selection_census": [],
            "represented_review_strata": [],
            "studies": [{"marker": study_marker}],
            "benchmark": {"wall_seconds": 1.0},
            "full_run": {"cpu_seconds": 1.0},
        }
    )
    (root / "private_case_index.json").write_bytes(case_payload)
    (root / "private_artifact_inventory.json").write_bytes(
        _line(
            {
                "schema_version": 1,
                "artifact_type": "private-dicom-qa-artifact-inventory",
                "status": "pending_private_human_review",
                "provenance": {
                    "git_commit": "a" * 40,
                    "bundle_sha256": "b" * 64,
                    "runner_sha256": "c" * 64,
                    "review_finalizer_sha256": "d" * 64,
                    "private_case_index_sha256": hashlib.sha256(case_payload).hexdigest(),
                },
                "artifacts": [
                    {
                        "kind": "contact_sheet",
                        "basename": "case_000001_series_001_contact.png",
                        "bytes": 1,
                        "sha256": "e" * 64,
                    }
                ],
            }
        )
    )


def test_private_comparator_discovers_two_runs_and_emits_only_fixed_aggregate(
    tmp_path: Path,
) -> None:
    module = _module(Path(__file__).parents[1])
    input_root = tmp_path / "input"
    for name in ("run-a", "run-b"):
        root = input_root / name / "dicom_qa"
        root.mkdir(parents=True)
        manifest = root / "private_full_run_manifest.jsonl"
        _manifest(manifest)
        snapshot = module.inspect_manifest(manifest)
        _metrics(root / "private_full_run_metrics.json", snapshot)
        _case_index_and_inventory(root)

    output = tmp_path / "working" / module.OUTPUT_DIRECTORY
    output.parent.mkdir()
    module.compare_private_run_roots(input_root, output)

    assert sorted(path.name for path in output.iterdir()) == [
        module.PRIVATE_OUTPUT,
        module.SANITIZED_OUTPUT,
    ]
    sanitized = json.loads((output / module.SANITIZED_OUTPUT).read_bytes())
    assert sanitized == {
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
    assert "private-study" not in (output / module.SANITIZED_OUTPUT).read_text()

    _metrics(
        input_root / "run-b" / "dicom_qa" / "private_full_run_metrics.json",
        module.inspect_manifest(
            input_root / "run-b" / "dicom_qa" / "private_full_run_manifest.jsonl"
        ),
        model_eligible=2,
    )
    with pytest.raises(module.RunComparisonError, match="deterministic_metrics_mismatch"):
        module.compare_private_run_roots(input_root, tmp_path / "second")


def test_private_comparator_rejects_independent_qa_artifact_drift(tmp_path: Path) -> None:
    module = _module(Path(__file__).parents[1])
    input_root = tmp_path / "input"
    for name in ("run-a", "run-b"):
        root = input_root / name / "dicom_qa"
        root.mkdir(parents=True)
        manifest = root / "private_full_run_manifest.jsonl"
        _manifest(manifest)
        _metrics(root / "private_full_run_metrics.json", module.inspect_manifest(manifest))
        _case_index_and_inventory(root, study_marker=name)

    with pytest.raises(module.RunComparisonError, match="deterministic_case_index_mismatch"):
        module.compare_private_run_roots(input_root, tmp_path / "output")
