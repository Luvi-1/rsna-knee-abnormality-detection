from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from rsna_knee.data import series_slots as slots

ROOT = Path(__file__).parents[1]


def _runner() -> ModuleType:
    path = ROOT / "kaggle" / "dicom_qa" / "run.py"
    name = "_dicom_qa_full_run_test_runner"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = _runner()


def _comparator() -> ModuleType:
    path = ROOT / "kaggle" / "dicom_qa" / "compare_runs.py"
    name = "_dicom_qa_full_run_test_comparator"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


comparator = _comparator()


def _rows_and_files(root: Path) -> tuple[tuple[Any, ...], dict[str, str]]:
    specifications = (
        ("1.2.826.0.1.1001", "1.2.826.0.1.2001", "sagittal", "present", 1, "eligible"),
        ("1.2.826.0.1.1002", "1.2.826.0.1.2002", "coronal", "absent", 3, "eligible"),
        ("1.2.826.0.1.1003", "1.2.826.0.1.2003", "axial", "present", 5, "eligible"),
        ("1.2.826.0.1.1004", "1.2.826.0.1.2004", "sagittal", "present", 2, "eligible"),
        (
            "1.2.826.0.1.1004",
            "1.2.826.0.1.2005",
            "sagittal",
            "present",
            4,
            "quality_blocked",
        ),
        (
            "1.2.826.0.1.1005",
            "1.2.826.0.1.2006",
            "coronal",
            "absent",
            6,
            "decode_blocked",
        ),
    )
    states: dict[str, str] = {}
    rows: list[Any] = []
    for study_uid, series_uid, plane, fluid, count, terminal in specifications:
        directory = root / "train_series" / study_uid / series_uid
        directory.mkdir(parents=True)
        for index in range(count):
            (directory / f"slice-{index:03d}").write_bytes(b"synthetic-dicom-container")
        rows.append(
            runner.SeriesRow(
                study_uid=study_uid,
                series_uid=series_uid,
                fluid_sensitive=fluid,
                fat_suppression="present" if count % 2 else "absent",
                plane=plane,
            )
        )
        states[series_uid] = terminal
    return tuple(rows), states


def _quality(*, files: int, terminal: str) -> slots.SeriesQuality:
    decoded = 0 if terminal == "decode_blocked" else files
    return slots.SeriesQuality(
        total_slices=files,
        decoded_slices=decoded,
        decode_failure_count=files - decoded,
        duplicate_slices=0,
        geometry_valid=terminal in {"eligible", "preprocessing_blocked"},
        spacing_regular=terminal != "decode_blocked",
        median_slice_spacing_mm=1.0 if decoded > 1 else None,
        spacing_coefficient_of_variation=0.0 if decoded > 1 else None,
        pixel_spacing_mm=(0.5, 0.6) if decoded else None,
        physical_coverage_mm=float(decoded - 1) if decoded else None,
    )


def _selection_features(row: Any, files: int, terminal_state: str) -> dict[str, tuple[str, ...]]:
    return {
        "plane": (row.plane,),
        "sequence": ("fluid_sensitive" if row.fluid_sensitive == "present" else "structural",),
        "fat_suppression": (row.fat_suppression,),
        "slice_count": (runner._slice_count_bucket(files),),
        "bit_depth": ("le_16",),
        "photometric": ("monochrome2",),
        "transfer_syntax": ("native",),
        "resolution": ("le_512",),
        "slice_thickness": ("le_3",),
        "slice_spacing": ("le_1_5",),
        "orientation": ("orthogonal",),
        "quality": ("high" if terminal_state == "model_eligible" else "blocked",),
        "duplicate_integrity": (),
        "dicom_edge_case": (() if terminal_state == "model_eligible" else ("present",)),
        "terminal_state": (terminal_state,),
    }


def _fake_series_state_factory(states: dict[str, str]) -> Any:
    def fake_series_state(
        *,
        competition_root: Path,
        row: Any,
        pipeline_module: Any,
        slots_module: Any,
        config: Any,
        versions: Any,
        cache_root: Path,
        deadline_at: float | None,
    ) -> dict[str, Any]:
        del pipeline_module, config, versions, deadline_at
        paths = runner._series_files(competition_root, row)
        requested_terminal = states[row.series_uid]
        quality = _quality(files=len(paths), terminal=requested_terminal)
        candidate = slots_module.SeriesCandidate(
            series_key=row.series_uid,
            tie_break_key=hashlib.sha256(row.series_uid.encode("ascii")).hexdigest(),
            organizer_plane=row.plane,
            organizer_fluid_sensitive=row.fluid_sensitive == "present",
            image_orientation_patient=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
            quality=quality,
        )
        model_eligible = requested_terminal == "eligible"
        terminal_state = "model_eligible" if model_eligible else requested_terminal
        decode_failures = (
            [
                {
                    "issue": "decoder_unavailable",
                    "stage": "pixel_decode",
                    "root_cause": "decoder_unavailable",
                    "exception_type": "RuntimeError",
                }
            ]
            if terminal_state == "decode_blocked"
            else []
        )
        cache_path: Path | None = None
        cache: dict[str, object] | None = None
        provenance: object | None = None
        reconstruction: dict[str, object] | None = None
        if model_eligible:
            payload = (row.series_uid + "\n").encode("ascii") * len(paths)
            cache_path = cache_root / f"{hashlib.sha256(row.series_uid.encode()).hexdigest()}.npy"
            cache_path.write_bytes(payload)
            cache = {
                "format": "npy-v1",
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            provenance = SimpleNamespace(configuration_hash="c" * 64)
            reconstruction = {
                "source_slice_count": len(paths),
                "output_tensor_shape": [len(paths), 1, 8, 8],
                "provenance": {
                    "configuration_hash": "c" * 64,
                    "input_checksum": hashlib.sha256(row.series_uid.encode()).hexdigest(),
                    "output_checksum": hashlib.sha256(payload).hexdigest(),
                },
            }
        resolution_state = (
            "pass"
            if model_eligible
            else "unresolved_blocker"
            if terminal_state == "decode_blocked"
            else "excluded_unusable_source"
        )
        preprocessing_failure = (
            {
                "issue": "normalization_collapsed",
                "stage": "normalization",
                "root_cause": "constant_image",
                "exception_type": "PipelineError",
            }
            if terminal_state == "preprocessing_blocked"
            else None
        )
        file_records = []
        for file_ordinal in range(len(paths)):
            failed = terminal_state == "decode_blocked" and file_ordinal == 1
            file_records.append(
                {
                    "file_ordinal": file_ordinal,
                    "decode_state": "failed" if failed else "pass",
                    **({"failure": decode_failures[0]} if failed else {}),
                    "terminal_state": "decode_blocked" if failed else terminal_state,
                    "resolution_state": resolution_state,
                    "disposition": (
                        "file_quarantine"
                        if failed
                        else "included_in_model_series"
                        if model_eligible
                        else "series_quarantine"
                    ),
                }
            )
        return {
            "row": row,
            "candidate": candidate,
            "paths": paths,
            "file_raw_checksums": tuple(
                hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
            ),
            "provenance": provenance,
            "quality": quality,
            "selection_features": _selection_features(row, len(paths), terminal_state),
            "cache_path": cache_path,
            "timings": {
                "decode_seconds": 0.01 * len(paths),
                "ordering_seconds": 0.001,
                "preprocessing_seconds": 0.02 if model_eligible else 0.0,
                "cache_generation_seconds": 0.003 if model_eligible else 0.0,
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
                    "components": {
                        "decode_fraction": quality.components.decode_fraction,
                        "duplicate_fraction": quality.components.duplicate_fraction,
                        "spacing_coefficient_of_variation": (
                            quality.components.spacing_coefficient_of_variation
                        ),
                        "in_plane_resolution_area_mm2": (
                            quality.components.in_plane_resolution_area_mm2
                        ),
                        "physical_coverage_mm": quality.components.physical_coverage_mm,
                        "decoded_slices": quality.components.decoded_slices,
                    },
                },
                "source_failure": None,
                "decode_failures": decode_failures,
                "file_records": file_records,
                "ordering_failure": None,
                "preprocessing_failure": preprocessing_failure,
                "terminal_state": terminal_state,
                "resolution_state": resolution_state,
                "disposition": "model_eligible" if model_eligible else "series_quarantine",
                "model_eligible": model_eligible,
                "model_output_reconstruction": reconstruction,
                "cache": cache,
            },
        }

    return fake_series_state


def _source_facts(rows: tuple[Any, ...]) -> dict[str, dict[str, tuple[str, ...]]]:
    return {
        row.study_uid: {
            "scanner_manufacturer": ("vendor_a",),
            "scanner_model": ("model_a",),
            "field_strength": ("le_3",),
            "site_domain_cluster": ("domain_a",),
            "protected_duplicate_group": (),
            "candidate_duplicate_group": (),
            "remediated_decode_case": (),
            "source_manifest_quality_flag": (),
            "source_manifest_terminal_state": ("pass",),
        }
        for row in rows
    }


def _source_identity() -> dict[str, str]:
    return {
        "audit_id": runner.SOURCE_MANIFEST_AUDIT_ID,
        "manifest_version": runner.SOURCE_MANIFEST_VERSION,
        "source_manifest_artifact_sha256": "d" * 64,
        "official_input_snapshot_sha256": "e" * 64,
    }


def _source_binding(
    *,
    owner: str = "test-owner",
    code_commit: str = "a" * 40,
    bundle_sha256: str = "b" * 64,
) -> Any:
    return runner.SourceManifestBinding(
        database_path=Path("private_manifest.sqlite3"),
        audit_key_path=Path("audit_key.bin"),
        producer_code_commit=code_commit,
        kernel_ref=(f"{owner}/rsna-knee-manifest-audit-{code_commit[:7]}-{bundle_sha256[:12]}"),
        bundle_dataset_ref=(
            f"{owner}/rsna-knee-manifest-bundle-{code_commit[:7]}-{bundle_sha256[:12]}"
        ),
        bundle_sha256=bundle_sha256,
        database_sha256="c" * 64,
        audit_key_sha256="d" * 64,
        schema_sha256="e" * 64,
        source_manifest_artifact_sha256="f" * 64,
    )


def test_source_manifest_producer_identity_is_distinct_from_governance_audit_id() -> None:
    code_commit = "a" * 40
    bundle_sha256 = "b" * 64
    metadata = {
        "audit_id": f"manifest-audit-{code_commit[:12]}",
        "bundle_sha256": bundle_sha256,
        "code_commit": code_commit,
    }

    assert (
        runner._source_manifest_producer_identity(
            _source_binding(code_commit=code_commit, bundle_sha256=bundle_sha256), metadata
        )
        == metadata
    )
    assert metadata["audit_id"] != runner.SOURCE_MANIFEST_AUDIT_ID


@pytest.mark.parametrize(
    ("binding_mutation", "metadata_mutation", "missing_key"),
    [
        ({}, {"code_commit": "A" * 40}, None),
        ({}, {"code_commit": "a" * 39}, None),
        ({}, {"code_commit": "g" * 40}, None),
        ({}, {"code_commit": "a" * 39 + "c"}, None),
        ({}, {}, "code_commit"),
        ({}, {"bundle_sha256": "b" * 63 + "c"}, None),
        ({}, {"bundle_sha256": "B" * 64}, None),
        ({}, {}, "bundle_sha256"),
        ({}, {"audit_id": runner.SOURCE_MANIFEST_AUDIT_ID}, None),
        ({}, {"audit_id": "wrong-prefix-aaaaaaaaaaaa"}, None),
        ({}, {}, "audit_id"),
        ({"kernel_ref": "other-owner/rsna-knee-manifest-audit-aaaaaaa-bbbbbbbbbbbb"}, {}, None),
        (
            {"bundle_dataset_ref": "other-owner/rsna-knee-manifest-bundle-aaaaaaa-bbbbbbbbbbbb"},
            {},
            None,
        ),
        ({"kernel_ref": "test-owner/rsna-knee-manifest-bundle-aaaaaaa-bbbbbbbbbbbb"}, {}, None),
        (
            {"bundle_dataset_ref": "test-owner/rsna-knee-manifest-audit-aaaaaaa-bbbbbbbbbbbb"},
            {},
            None,
        ),
        ({"kernel_ref": "test-owner/rsna-knee-manifest-audit-ccccccc-bbbbbbbbbbbb"}, {}, None),
        (
            {"bundle_dataset_ref": "test-owner/rsna-knee-manifest-bundle-aaaaaaa-cccccccccccc"},
            {},
            None,
        ),
        ({"bundle_sha256": "b" * 63 + "c"}, {}, None),
    ],
)
def test_source_manifest_producer_identity_rejects_mismatch(
    binding_mutation: dict[str, str],
    metadata_mutation: dict[str, str],
    missing_key: str | None,
) -> None:
    code_commit = "a" * 40
    bundle_sha256 = "b" * 64
    binding = _source_binding(code_commit=code_commit, bundle_sha256=bundle_sha256)
    binding = replace(binding, **binding_mutation)
    metadata = {
        "audit_id": f"manifest-audit-{code_commit[:12]}",
        "bundle_sha256": bundle_sha256,
        "code_commit": code_commit,
        **metadata_mutation,
    }
    if missing_key is not None:
        metadata.pop(missing_key)

    with pytest.raises(runner.SafeRunError, match="source_manifest_version_mismatch"):
        runner._source_manifest_producer_identity(binding, metadata)


def _source_reconciliation(competition_root: Path, rows: tuple[Any, ...]) -> Any:
    secret = b"s" * 32
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE study_manifest(study_key TEXT PRIMARY KEY, split TEXT NOT NULL);
        CREATE TABLE series_manifest(
            series_key TEXT PRIMARY KEY,
            study_key TEXT NOT NULL,
            source_row_count INTEGER NOT NULL,
            plane TEXT,
            fluid_sensitive TEXT,
            fat_suppression TEXT
        );
        CREATE TABLE slice_file_manifest(
            file_key TEXT PRIMARY KEY,
            study_key TEXT NOT NULL,
            series_key TEXT NOT NULL,
            file_size_bytes INTEGER NOT NULL,
            raw_file_exact_key TEXT
        );
        """
    )
    studies: set[str] = set()
    files = 0
    for row in rows:
        study_key = runner._source_manifest_study_key(secret, row.study_uid)
        series_key = runner._source_manifest_series_key(secret, row.series_uid)
        if study_key not in studies:
            connection.execute("INSERT INTO study_manifest VALUES(?, 'train')", (study_key,))
            studies.add(study_key)
        connection.execute(
            "INSERT INTO series_manifest VALUES(?,?,?,?,?,?)",
            (
                series_key,
                study_key,
                1,
                row.plane,
                (
                    "true"
                    if row.fluid_sensitive == "present"
                    else "false"
                    if row.fluid_sensitive == "absent"
                    else None
                ),
                (
                    "true"
                    if row.fat_suppression == "present"
                    else "false"
                    if row.fat_suppression == "absent"
                    else None
                ),
            ),
        )
        for path in runner._series_files(competition_root, row):
            payload = path.read_bytes()
            relative = path.relative_to(competition_root).as_posix()
            raw_checksum = hashlib.sha256(payload).hexdigest()
            connection.execute(
                "INSERT INTO slice_file_manifest VALUES(?,?,?,?,?)",
                (
                    runner._source_manifest_opaque_key(secret, "file", relative),
                    study_key,
                    series_key,
                    len(payload),
                    runner._source_manifest_opaque_key(secret, "raw-file-digest", raw_checksum),
                ),
            )
            files += 1
    return runner.SourceManifestReconciliation(connection, secret, len(rows), files)


def _run_full(
    *,
    competition_root: Path,
    rows: tuple[Any, ...],
    manifest_path: Path,
    source_available: bool,
) -> tuple[dict[str, Any], tuple[Any, ...], Any]:
    reconciliation = _source_reconciliation(competition_root, rows) if source_available else None
    try:
        metrics, representatives, _, selection, _ = runner._run_full_dataset_pass(
            competition_root=competition_root,
            rows=rows,
            private_manifest_path=manifest_path,
            run_config={"code_commit": "a" * 40, "bundle_sha256": "b" * 64},
            config=SimpleNamespace(),
            versions=SimpleNamespace(
                source_manifest_version=runner.SOURCE_MANIFEST_VERSION,
                preprocessing_version="dicom-model-v1",
            ),
            pipeline_module=SimpleNamespace(preprocessing_config_hash=lambda _config: "c" * 64),
            slots_module=slots,
            workers=3,
            deadline_at=None,
            source_manifest_facts=_source_facts(rows) if source_available else None,
            source_manifest_identity=_source_identity() if source_available else None,
            source_manifest_reconciliation=reconciliation,
            selection_target=3,
            selection_maximum=5,
            selection_minimum_eligible=3,
        )
    finally:
        if reconciliation is not None:
            reconciliation.connection.close()
    return metrics, representatives, selection


def _manifest_records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="ascii").splitlines()]


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _all_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _all_keys(item)}
    return set()


def test_source_manifest_rejects_same_study_added_or_removed_series(tmp_path: Path) -> None:
    competition = tmp_path / "competition"
    study_uid = "1.2.826.0.1.7101"
    rows = tuple(
        runner.SeriesRow(study_uid, series_uid, "present", "absent", "sagittal")
        for series_uid in ("1.2.826.0.1.7201", "1.2.826.0.1.7202")
    )
    for row in rows:
        directory = competition / "train_series" / row.study_uid / row.series_uid
        directory.mkdir(parents=True)
        (directory / "slice-000").write_bytes(b"synthetic-dicom")
    reconciliation = _source_reconciliation(competition, rows)
    try:
        assert (
            runner._validate_source_manifest_series_population(
                reconciliation.connection, reconciliation.secret, rows
            )
            == 2
        )
        added = rows + (
            runner.SeriesRow(study_uid, "1.2.826.0.1.7203", "present", "absent", "sagittal"),
        )
        for changed in (added, rows[:1]):
            with pytest.raises(runner.SafeRunError, match="source_manifest_population_mismatch"):
                runner._validate_source_manifest_series_population(
                    reconciliation.connection, reconciliation.secret, changed
                )
        for plane, fluid_sensitive, fat_suppression in (
            ("coronal", rows[0].fluid_sensitive, rows[0].fat_suppression),
            (rows[0].plane, "absent", rows[0].fat_suppression),
            (rows[0].plane, rows[0].fluid_sensitive, "present"),
        ):
            mutated = (
                runner.SeriesRow(
                    rows[0].study_uid,
                    rows[0].series_uid,
                    fluid_sensitive,
                    fat_suppression,
                    plane,
                ),
                rows[1],
            )
            with pytest.raises(runner.SafeRunError, match="source_manifest_population_mismatch"):
                runner._validate_source_manifest_series_population(
                    reconciliation.connection, reconciliation.secret, mutated
                )
    finally:
        reconciliation.connection.close()


def test_source_manifest_rejects_added_removed_or_changed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    competition = tmp_path / "competition"
    row = runner.SeriesRow(
        "1.2.826.0.1.7301",
        "1.2.826.0.1.7401",
        "present",
        "absent",
        "sagittal",
    )
    directory = competition / "train_series" / row.study_uid / row.series_uid
    directory.mkdir(parents=True)
    original_payloads = (b"slice-a", b"slice-b")
    for ordinal, payload in enumerate(original_payloads):
        (directory / f"slice-{ordinal:03d}").write_bytes(payload)
    reconciliation = _source_reconciliation(competition, (row,))

    def current() -> tuple[tuple[Path, ...], tuple[str, ...]]:
        paths = runner._series_files(competition, row)
        return paths, tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in paths)

    original_hash = runner._sha256_file
    fallback_reads: list[Path] = []

    def tracked_hash(path: Path) -> str:
        fallback_reads.append(path)
        return original_hash(path)

    monkeypatch.setattr(runner, "_sha256_file", tracked_hash)
    try:
        paths, checksums = current()
        assert (
            runner._reconcile_source_manifest_series_files(
                reconciliation,
                competition_root=competition,
                row=row,
                paths=paths,
                raw_checksums=checksums,
                deadline_at=None,
            )
            == 2
        )
        assert fallback_reads == []
        runner._reconcile_source_manifest_series_files(
            reconciliation,
            competition_root=competition,
            row=row,
            paths=paths,
            raw_checksums=(None, checksums[1]),
            deadline_at=None,
        )
        assert fallback_reads == [paths[0]]

        added = directory / "slice-002"
        added.write_bytes(b"slice-c")
        changed_paths, changed_checksums = current()
        with pytest.raises(runner.SafeRunError, match="source_manifest_population_mismatch"):
            runner._reconcile_source_manifest_series_files(
                reconciliation,
                competition_root=competition,
                row=row,
                paths=changed_paths,
                raw_checksums=changed_checksums,
                deadline_at=None,
            )
        added.unlink()

        removed = directory / "slice-001"
        removed.unlink()
        changed_paths, changed_checksums = current()
        with pytest.raises(runner.SafeRunError, match="source_manifest_population_mismatch"):
            runner._reconcile_source_manifest_series_files(
                reconciliation,
                competition_root=competition,
                row=row,
                paths=changed_paths,
                raw_checksums=changed_checksums,
                deadline_at=None,
            )
        removed.write_bytes(original_payloads[1])

        first = directory / "slice-000"
        first.write_bytes(b"SLICE-A")
        changed_paths, changed_checksums = current()
        with pytest.raises(runner.SafeRunError, match="source_manifest_population_mismatch"):
            runner._reconcile_source_manifest_series_files(
                reconciliation,
                competition_root=competition,
                row=row,
                paths=changed_paths,
                raw_checksums=changed_checksums,
                deadline_at=None,
            )

        first.write_bytes(b"different-size")
        changed_paths, changed_checksums = current()
        with pytest.raises(runner.SafeRunError, match="source_manifest_population_mismatch"):
            runner._reconcile_source_manifest_series_files(
                reconciliation,
                competition_root=competition,
                row=row,
                paths=changed_paths,
                raw_checksums=changed_checksums,
                deadline_at=None,
            )
    finally:
        reconciliation.connection.close()


def test_conflicting_organizer_plane_uses_physical_plane_in_qa_and_context() -> None:
    row = runner.SeriesRow(
        "1.2.826.0.1.7501",
        "1.2.826.0.1.7601",
        "present",
        "absent",
        "sagittal",
    )
    coronal_iop = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    ordered = SimpleNamespace(
        slices=(SimpleNamespace(metadata=SimpleNamespace(image_orientation=coronal_iop)),)
    )
    qa_module = SimpleNamespace(
        QaPlane=SimpleNamespace(
            SAGITTAL="sagittal",
            CORONAL="coronal",
            AXIAL="axial",
            OBLIQUE="oblique",
            UNKNOWN="unknown",
        )
    )

    assert runner._qa_plane(row, ordered, qa_module, slots) == "coronal"
    assert runner._review_plane_context(row, coronal_iop, slots) == {
        "organizer_plane": "sagittal",
        "physical_plane": "coronal",
    }
    candidate = slots.SeriesCandidate(
        series_key="series-000",
        tie_break_key="a" * 64,
        organizer_plane=row.plane,
        organizer_fluid_sensitive=True,
        image_orientation_patient=coronal_iop,
        quality=_quality(files=3, terminal="eligible"),
    )
    assignment = slots.assign_series_slots((candidate,))
    assert [reason.value for reason in assignment.additional_or_duplicate[0].reasons] == [
        "conflicting_plane_metadata"
    ]


def test_post_full_pass_selection_includes_represented_singleton_value() -> None:
    study_uids = [f"1.2.840.10008.{index}" for index in range(121)]
    singleton_uid = max(
        study_uids,
        key=lambda uid: hashlib.sha256(f"{runner.SELECTION_SEED}:fill:{uid}".encode()).digest(),
    )
    studies = tuple(
        runner.CohortStudy(
            study_uid=uid,
            stratum=("shared",) * 11,
            dimensions=(
                ("plane", ("sagittal",)),
                (
                    "scanner_model",
                    ("singleton_model" if uid == singleton_uid else "common_model",),
                ),
            ),
            eligible_series_uids=(f"{uid}.1",),
        )
        for uid in study_uids
    )

    first = runner._select_after_full_pass(studies, source_manifest_available=True)
    second = runner._select_after_full_pass(
        tuple(reversed(studies)), source_manifest_available=True
    )

    assert first == second
    assert len(first.studies) == runner.TARGET_STUDIES
    assert singleton_uid in {study.study_uid for study in first.studies}
    coverage = {(item.dimension, item.value): item for item in first.coverage}
    singleton = coverage[("scanner_model", "singleton_model")]
    assert (singleton.population_studies, singleton.selected_studies) == (1, 1)
    assert singleton.disposition == "represented_nonmaterial"


def test_full_run_is_permutation_deterministic_private_and_terminally_reconciled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    competition = tmp_path / "competition"
    rows, requested_states = _rows_and_files(competition)
    monkeypatch.setattr(runner, "_full_series_state", _fake_series_state_factory(requested_states))
    first_path = tmp_path / "first.jsonl"
    second_path = tmp_path / "second.jsonl"

    first_metrics, first_representatives, first_selection = _run_full(
        competition_root=competition,
        rows=rows,
        manifest_path=first_path,
        source_available=True,
    )
    second_metrics, second_representatives, second_selection = _run_full(
        competition_root=competition,
        rows=tuple(reversed(rows)),
        manifest_path=second_path,
        source_available=True,
    )

    assert first_path.read_bytes() == second_path.read_bytes()
    snapshot = comparator.inspect_manifest(first_path)
    assert (snapshot.studies, snapshot.series, snapshot.files) == (5, 6, 21)
    assert first_metrics["manifest_sha256"] == second_metrics["manifest_sha256"]
    assert first_metrics["qa_cohort_selection"] == second_metrics["qa_cohort_selection"]
    assert first_selection == second_selection
    assert [(item.profile, item.slice_count) for item in first_representatives] == [
        ("small", 1),
        ("median", 2),
        ("large", 5),
    ]
    assert [(item.profile, item.slice_count) for item in second_representatives] == [
        ("small", 1),
        ("median", 2),
        ("large", 5),
    ]

    records = _manifest_records(first_path)
    assert [record["record_type"] for record in records] == [
        "header",
        "study",
        "study",
        "study",
        "study",
        "study",
        "footer",
    ]
    header, *study_records, footer = records
    assert header["output_policy"] == {
        "case_data": "permitted_private_only",
        "classification": "private_remote_only",
        "dynamic_measurements": "excluded",
        "filename": "private_full_run_manifest.jsonl",
        "format": "canonical-json-lines-v1",
        "maximum_bytes": runner.PRIVATE_OUTPUT_POLICY["private_full_run_manifest.jsonl"],
    }
    series_records = [series for study in study_records for series in study["series"]]
    assert len(series_records) == len(rows) == 6
    assert {record["series_uid"] for record in series_records} == {row.series_uid for row in rows}
    assert footer["studies"] == 5
    assert footer["series"] == 6
    assert footer["files"] == 21
    assert footer["terminal_counts"] == {
        "decode_blocked": 1,
        "model_eligible": 4,
        "quality_blocked": 1,
    }
    assert footer["resolution_counts"] == {
        "excluded_unusable_source": 1,
        "pass": 4,
        "unresolved_blocker": 1,
    }
    assert footer["file_terminal_counts"] == {
        "decode_blocked": 6,
        "model_eligible": 11,
        "quality_blocked": 4,
    }
    assert footer["file_resolution_counts"] == {
        "excluded_unusable_source": 4,
        "pass": 11,
        "unresolved_blocker": 6,
    }
    assert footer["file_disposition_counts"] == {
        "file_quarantine": 1,
        "included_in_model_series": 11,
        "series_quarantine": 9,
    }
    assert all(
        [item["file_ordinal"] for item in record["file_records"]] == list(range(record["files"]))
        for record in series_records
    )
    assert sum(len(record["file_records"]) for record in series_records) == footer["files"]
    eligible_files = [
        item
        for record in series_records
        if record["model_eligible"]
        for item in record["file_records"]
    ]
    assert all(
        item["decode_state"] == "pass"
        and item["terminal_state"] == "model_eligible"
        and item["resolution_state"] == "pass"
        and item["disposition"] == "included_in_model_series"
        for item in eligible_files
    )
    decode_blocked_files = next(
        record["file_records"]
        for record in series_records
        if record["terminal_state"] == "decode_blocked"
    )
    assert sum(item["disposition"] == "file_quarantine" for item in decode_blocked_files) == 1
    assert sum(item["disposition"] == "series_quarantine" for item in decode_blocked_files) == 5
    assert all(
        record["disposition"] == "series_quarantine"
        for record in series_records
        if not record["model_eligible"]
    )
    manifest_keys = _all_keys(records)
    assert not any("seconds" in key or "timing" in key for key in manifest_keys)
    assert "path" not in manifest_keys
    assert "pixels" not in manifest_keys
    assert str(tmp_path) not in first_path.read_text(encoding="ascii")

    assert first_metrics["studies_processed"] == 5
    assert first_metrics["series_processed"] == 6
    assert first_metrics["files_processed"] == 21
    assert first_metrics["model_eligible_series"] == 4
    assert first_metrics["integrity_gate"] == {
        "terminal_reconciled": True,
        "unresolved_blocker_count": 1,
        "unresolved_stage_counts": {"decode_blocked": 1},
        "unresolved_issue_counts": {"decoder_unavailable": 1},
        "status": "block",
    }
    timings = first_metrics["timings_seconds"]
    assert isinstance(timings, dict)
    assert set(timings) == {
        "total_seconds",
        "decode_seconds",
        "ordering_seconds",
        "slot_assignment_seconds",
        "preprocessing_seconds",
        "cache_generation_seconds",
        "qa_generation_seconds",
    }
    assert timings["qa_generation_seconds"] == 0.0
    assert first_metrics["process_peak_rss_bytes"] > 0
    assert first_metrics["process_peak_rss_increase_bytes"] >= 0
    assert first_metrics["peak_ephemeral_cache_bytes"] > 0
    assert first_metrics["peak_private_working_disk_bytes"] >= first_metrics["manifest_bytes"]
    assert set(first_metrics["throughput"]) == {
        "files_per_second",
        "series_per_second",
        "studies_per_second",
    }
    assert first_metrics["input_identity"] == _source_identity()
    assert first_metrics["qa_cohort_selection"]["source_manifest_gate"] == "pass"
    metrics_text = json.dumps(first_metrics, sort_keys=True)
    assert all(row.study_uid not in metrics_text for row in rows)
    assert all(row.series_uid not in metrics_text for row in rows)

    by_study = {record["study_uid"]: record for record in study_records}
    case_index_studies = [
        {
            "case_ordinal": ordinal,
            "study_uid": selected.study_uid,
            "selection_stratum": list(selected.stratum),
            "series": by_study[selected.study_uid]["series"],
        }
        for ordinal, selected in enumerate(first_selection.studies)
    ]
    assert (
        runner._case_index_cohort_sha256(case_index_studies)
        == first_metrics["qa_cohort_selection"]["cohort_sha256"]
    )


def test_file_terminal_records_preserve_success_and_mixed_failure_ordinals() -> None:
    class FakePipelineError(Exception):
        def __init__(self) -> None:
            self.issue = SimpleNamespace(value="pixel_decode_failed")
            self.stage = "pixel_decode"
            self.root_cause = "decoder_unavailable"
            self.exception_type = "RuntimeError"

    class Pipeline:
        PipelineError = FakePipelineError

        @staticmethod
        def decode_dicom(path: Path) -> SimpleNamespace:
            if path.name == "slice-001":
                raise FakePipelineError
            return SimpleNamespace(raw_checksum=hashlib.sha256(path.name.encode()).hexdigest())

        @staticmethod
        def order_series(decoded: tuple[Any, ...]) -> tuple[Any, ...]:
            return decoded

    paths = tuple(Path(f"slice-{index:03d}") for index in range(3))
    mixed = runner._decode_order_pass(paths, Pipeline, deadline_at=None)
    mixed_records = runner._file_terminal_records(mixed, "decode_blocked", "unresolved_blocker")

    assert [item["file_ordinal"] for item in mixed_records] == [0, 1, 2]
    assert [item["decode_state"] for item in mixed_records] == ["pass", "failed", "pass"]
    assert [item["disposition"] for item in mixed_records] == [
        "series_quarantine",
        "file_quarantine",
        "series_quarantine",
    ]
    assert mixed_records[1]["resolution_state"] == "unresolved_blocker"
    assert "path" not in _all_keys(mixed_records)

    success = runner._decode_order_pass((paths[0], paths[2]), Pipeline, deadline_at=None)
    success_records = runner._file_terminal_records(success, "model_eligible", "pass")
    assert all(
        item["decode_state"] == "pass"
        and item["terminal_state"] == "model_eligible"
        and item["resolution_state"] == "pass"
        and item["disposition"] == "included_in_model_series"
        for item in success_records
    )


def _source_blocked_state(root: Path, row: Any) -> dict[str, Any]:
    return runner._full_series_state(
        competition_root=root,
        row=row,
        pipeline_module=SimpleNamespace(),
        slots_module=slots,
        config=SimpleNamespace(),
        versions=SimpleNamespace(),
        cache_root=root,
        deadline_at=None,
    )


def test_source_validation_failure_retains_only_discovered_regular_files(
    tmp_path: Path,
) -> None:
    row = runner.SeriesRow("1.2.826.0.1.3001", "1.2.826.0.1.4001", "present", "absent", "axial")
    directory = tmp_path / "train_series" / row.study_uid / row.series_uid
    directory.mkdir(parents=True)
    (directory / "slice-001").write_bytes(b"synthetic")
    (directory / "slice-002").write_bytes(b"synthetic")
    (directory / "slice-empty").write_bytes(b"")
    (directory / "not-a-dicom").mkdir()

    state = _source_blocked_state(tmp_path, row)
    record = state["record"]

    assert record["source_failure"] == "series_file_invalid"
    assert record["files"] == state["quality"].total_slices == 3
    assert record["file_records"] == [
        {
            "file_ordinal": ordinal,
            "decode_state": "not_attempted",
            "terminal_state": "source_access_blocked",
            "resolution_state": "unresolved_blocker",
            "disposition": "series_quarantine",
        }
        for ordinal in range(3)
    ]
    assert "not-a-dicom" not in json.dumps(record, sort_keys=True)


def test_source_file_count_overflow_retains_only_bounded_regular_file_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "MAX_FILES_PER_SERIES", 2)
    row = runner.SeriesRow("1.2.826.0.1.3002", "1.2.826.0.1.4002", "present", "absent", "axial")
    directory = tmp_path / "train_series" / row.study_uid / row.series_uid
    directory.mkdir(parents=True)
    for ordinal in range(4):
        (directory / f"slice-{ordinal:03d}").write_bytes(b"synthetic")

    record = _source_blocked_state(tmp_path, row)["record"]

    assert record["source_failure"] == "series_file_count_invalid"
    assert record["files"] == len(record["file_records"]) == 3
    assert [item["file_ordinal"] for item in record["file_records"]] == [0, 1, 2]
    assert all(item["decode_state"] == "not_attempted" for item in record["file_records"])


def test_full_run_without_authenticated_source_manifest_records_unavailable_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    competition = tmp_path / "competition"
    rows, requested_states = _rows_and_files(competition)
    monkeypatch.setattr(runner, "_full_series_state", _fake_series_state_factory(requested_states))

    metrics, _, _ = _run_full(
        competition_root=competition,
        rows=rows,
        manifest_path=tmp_path / "unavailable.jsonl",
        source_available=False,
    )

    selection = metrics["qa_cohort_selection"]
    assert selection["source_manifest_gate"] == "unavailable_source_manifest"
    unavailable = [
        item
        for item in selection["coverage"]
        if item["dimension"] in runner.SOURCE_MANIFEST_DIMENSIONS
    ]
    assert {item["dimension"] for item in unavailable} == set(runner.SOURCE_MANIFEST_DIMENSIONS)
    assert all(item["disposition"] == "unavailable_source_manifest" for item in unavailable)
    assert all(item["source"] == "source_manifest_not_attached" for item in unavailable)
    assert _manifest_records(tmp_path / "unavailable.jsonl")[0]["provenance"][
        "source_manifest_identity"
    ] == {"status": "unavailable_source_manifest"}


def test_selected_replay_carries_preprocessing_and_source_blocks_without_rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    competition = tmp_path / "competition"
    study_uid = "1.2.826.0.1.5001"
    rows = tuple(
        runner.SeriesRow(study_uid, series_uid, "present", "absent", plane)
        for series_uid, plane in (
            ("1.2.826.0.1.6001", "sagittal"),
            ("1.2.826.0.1.6002", "coronal"),
        )
    )
    for row in rows:
        directory = competition / "train_series" / row.study_uid / row.series_uid
        directory.mkdir(parents=True)
        for ordinal in range(2):
            (directory / f"slice-{ordinal:03d}").write_bytes(b"synthetic")
    requested = {
        rows[0].series_uid: "eligible",
        rows[1].series_uid: "preprocessing_blocked",
    }
    monkeypatch.setattr(runner, "_full_series_state", _fake_series_state_factory(requested))

    reconciliation = _source_reconciliation(competition, rows)
    try:
        _, _, _, _, evidence = runner._run_full_dataset_pass(
            competition_root=competition,
            rows=rows,
            private_manifest_path=tmp_path / "manifest.jsonl",
            run_config={"code_commit": "a" * 40, "bundle_sha256": "b" * 64},
            config=SimpleNamespace(),
            versions=SimpleNamespace(
                source_manifest_version=runner.SOURCE_MANIFEST_VERSION,
                preprocessing_version="dicom-model-v1",
            ),
            pipeline_module=SimpleNamespace(preprocessing_config_hash=lambda _config: "c" * 64),
            slots_module=slots,
            workers=1,
            deadline_at=None,
            source_manifest_facts=_source_facts(rows),
            source_manifest_identity=_source_identity(),
            source_manifest_reconciliation=reconciliation,
            selection_target=1,
            selection_maximum=1,
            selection_minimum_eligible=1,
        )
    finally:
        reconciliation.connection.close()

    eligible_terminal, eligible_failure = runner._selected_replay_terminal(
        "preprocessing_candidate", evidence[(study_uid, rows[0].series_uid)]
    )
    blocked_terminal, blocked_failure = runner._selected_replay_terminal(
        "preprocessing_candidate", evidence[(study_uid, rows[1].series_uid)]
    )
    source_terminal, source_preprocessing_failure = runner._selected_replay_terminal(
        "source_access_blocked",
        {
            "terminal_state": "source_access_blocked",
            "source_failure": "series_file_invalid",
            "preprocessing_failure": None,
            "quality": SimpleNamespace(),
        },
    )

    assert (eligible_terminal, eligible_failure) == ("model_eligible", None)
    assert blocked_terminal == "preprocessing_blocked"
    assert blocked_failure == evidence[(study_uid, rows[1].series_uid)]["preprocessing_failure"]
    assert (source_terminal, source_preprocessing_failure) == (
        "source_access_blocked",
        None,
    )
    assert (
        sum(
            terminal == "model_eligible"
            for terminal in (eligible_terminal, blocked_terminal, source_terminal)
        )
        == 1
    )


def _private_performance_metrics() -> dict[str, object]:
    cpu_parallelism = [
        {
            "workers": 1,
            "tasks": 8,
            "wall_seconds": 8.0,
            "tasks_per_second": 1.0,
            "speedup_vs_one_worker": 1.0,
        },
        {
            "workers": 2,
            "tasks": 8,
            "wall_seconds": 4.5,
            "tasks_per_second": 1.777778,
            "speedup_vs_one_worker": 1.777778,
        },
    ]
    return {
        "timings_seconds": {
            "decode_seconds": 21.0,
            "preprocessing_seconds": 7.0,
            "slot_assignment_seconds": 0.125,
            "qa_generation_seconds": 9.5,
            "cache_generation_seconds": 1.25,
        },
        "total_wall_seconds": 123.4567894,
        "full_dataset_wall_seconds": 100.25,
        "process_peak_rss_bytes": 513 * 1024**2,
        "logical_cache_bytes": 5 * 1024**2,
        "peak_ephemeral_cache_bytes": 2 * 1024**2,
        "peak_private_working_disk_bytes": 9 * 1024**2,
        "cpu_capacity_threads": 2,
        "cpu_utilization_percent": 55.5555555,
        "files_processed": 21,
        "model_eligible_series": 4,
        "end_to_end_throughput": {
            "files_per_second": 0.1701,
            "series_per_second": 0.0486,
            "studies_per_second": 0.0405,
        },
        "representative_scaling": {
            "selection_method": "model_eligible_slice_count_rank_small_median_large_v1",
            "requested_worker_counts": [1, 2, 4, 8],
            "available_worker_counts": [1, 2],
            "unavailable_worker_counts": [4, 8],
            "profiles": [
                {
                    "profile": profile,
                    "iterations": 3 if profile == "median" else 1,
                    "cpu_parallelism": cpu_parallelism,
                    "slice_count": count,
                    "private_only_extra": "not_released",
                }
                for profile, count in (("small", 1), ("median", 4), ("large", 8))
            ],
        },
    }


def test_sanitized_performance_is_complete_coarse_and_non_reconstructing() -> None:
    private = _private_performance_metrics()
    performance = runner._sanitized_performance(private, 32_400)

    assert performance["runtime_seconds"] == {
        "total_run_wall_seconds": 123.456789,
        "full_dataset_pipeline_wall_seconds": 100.25,
    }
    assert performance["phase_seconds"] == {
        "decode_accumulated_seconds": 21.0,
        "preprocessing_accumulated_seconds": 7.0,
        "slot_assignment_seconds": 0.125,
        "qa_generation_seconds": 9.5,
        "cache_generation_seconds": 1.25,
    }
    assert performance["resources"] == {
        "process_peak_rss_mib_ceiling": 513,
        "logical_cache_power_of_two_mib_ceiling": 8,
        "peak_ephemeral_cache_power_of_two_mib_ceiling": 4,
        "peak_private_working_disk_power_of_two_mib_ceiling": 16,
    }
    throughput = performance["throughput"]
    assert throughput == {
        "scope": "complete_private_run_including_post_pass_qa_and_representative_benchmark",
        "disclosure_policy": "fixed_order_of_magnitude_rate_buckets_v1",
        "decode_files_per_second_token": "one_to_below_ten_per_second",
        "preprocessing_series_per_second_token": "below_one_per_second",
        "end_to_end_files_per_second_token": "below_one_per_second",
        "end_to_end_series_per_second_token": "below_one_per_second",
        "end_to_end_studies_per_second_token": "below_one_per_second",
    }
    assert performance["inference_runtime_budget"] == {
        "limit_seconds": 32_400,
        "limit_source": "bundled_competition_contract",
        "measured_preprocessing_pipeline_wall_seconds": 100.25,
        "remaining_after_preprocessing_seconds": 32_299.75,
        "preprocessing_within_limit": True,
        "model_runtime_included": False,
        "model_viability_assessed": False,
        "scope": "measured_preprocessing_only",
    }
    assert performance["determinism_status"] == "pending_independent_run_comparison"
    assert [
        profile["profile"] for profile in performance["representative_cpu_scaling"]["profiles"]
    ] == [
        "small",
        "median",
        "large",
    ]

    released = json.dumps(performance, sort_keys=True)
    released_keys = _all_keys(performance)
    for forbidden in (
        "files_processed",
        "series_processed",
        "studies_processed",
        "slice_count",
        "private_only_extra",
        "sha256",
        "cohort",
        "uid",
        "path",
    ):
        assert forbidden not in released_keys
    assert 'files_per_second"' not in released
    assert 'series_per_second"' not in released
    assert 'studies_per_second"' not in released
    end_to_end_token = throughput["end_to_end_files_per_second_token"]
    _, lower, upper = next(
        item for item in runner.THROUGHPUT_BUCKETS if item[0] == end_to_end_token
    )
    wall = performance["runtime_seconds"]["total_run_wall_seconds"]
    assert math.ceil(upper * wall) - math.floor(lower * wall) > 2
    runner._validate_performance(performance, expected_inference_limit_seconds=32_400)


def test_sanitized_performance_rejects_point_throughput_and_runtime_claims() -> None:
    performance = runner._sanitized_performance(_private_performance_metrics(), 32_400)
    point_rate = json.loads(json.dumps(performance))
    point_rate["throughput"] = {
        "scope": "complete_private_run_including_post_pass_qa_and_representative_benchmark",
        "files_per_second": 0.1701,
        "series_per_second": 0.0486,
        "studies_per_second": 0.0405,
    }
    with pytest.raises(runner.SafeRunError, match="sanitized_performance_invalid"):
        runner._validate_performance(point_rate)

    claimed_model = json.loads(json.dumps(performance))
    claimed_model["inference_runtime_budget"]["model_viability_assessed"] = True
    with pytest.raises(runner.SafeRunError, match="sanitized_performance_invalid"):
        runner._validate_performance(claimed_model)

    with pytest.raises(runner.SafeRunError, match="sanitized_performance_invalid"):
        runner._validate_performance(performance, expected_inference_limit_seconds=21_600)


def test_competition_cpu_limit_is_loaded_from_the_bound_contract(tmp_path: Path) -> None:
    contract = tmp_path / "contract.yaml"
    contract.write_text(
        json.dumps({"schema_version": 1, "runtime": {"cpu_limit_seconds": 32_400}}),
        encoding="ascii",
    )
    assert runner._competition_cpu_limit_seconds(contract) == 32_400

    contract.write_text(
        json.dumps({"schema_version": 1, "runtime": {"cpu_limit_seconds": True}}),
        encoding="ascii",
    )
    with pytest.raises(runner.SafeRunError, match="competition_contract_invalid"):
        runner._competition_cpu_limit_seconds(contract)
