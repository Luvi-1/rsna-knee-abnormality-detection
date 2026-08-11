from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import math
import sqlite3
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest

from rsna_knee.data import manifest as producer_manifest
from rsna_knee.data import qa_strata
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


def test_cache_tensor_hashes_canonical_npy_without_fsync_or_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tensor = np.arange(3 * 5 * 7, dtype=np.float32).reshape(3, 5, 7)
    canonical = io.BytesIO()
    np.save(canonical, tensor, allow_pickle=False)
    expected = canonical.getvalue()
    real_fdopen = runner.os.fdopen
    modes: list[str] = []

    def checked_fdopen(descriptor: int, mode: str) -> Any:
        modes.append(mode)
        assert "r" not in mode and "+" not in mode
        return real_fdopen(descriptor, mode)

    monkeypatch.setattr(runner.os, "fdopen", checked_fdopen)
    monkeypatch.setattr(
        runner.os,
        "fsync",
        lambda _descriptor: pytest.fail("ephemeral tensor cache must not force durability"),
    )

    path, size, sha256, _seconds = runner._cache_tensor(
        SimpleNamespace(tensor=tensor), cache_root=tmp_path
    )

    assert modes == ["wb"]
    assert path.read_bytes() == expected
    assert size == len(expected)
    assert sha256 == hashlib.sha256(expected).hexdigest()
    assert np.array_equal(np.load(path, allow_pickle=False), tensor)


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
            "source_manifest_quality_flag": ("none",),
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


def test_source_manifest_loader_uses_entity_key_and_excludes_protected_singletons(
    tmp_path: Path,
) -> None:
    secret = b"s" * 32
    code_commit = "a" * 40
    bundle_sha256 = "b" * 64
    schema_sha256 = "e" * 64
    study_uid = "1.2.826.0.1.7101"
    series_uid = "1.2.826.0.1.7201"
    low_priority_study_uid = "1.2.826.0.1.7102"
    low_priority_series_uid = "1.2.826.0.1.7202"
    row = runner.SeriesRow(study_uid, series_uid, "present", "absent", "sagittal")
    low_priority_row = runner.SeriesRow(
        low_priority_study_uid,
        low_priority_series_uid,
        "present",
        "absent",
        "sagittal",
    )
    study_key = runner._source_manifest_study_key(secret, study_uid)
    series_key = runner._source_manifest_series_key(secret, series_uid)
    low_priority_study_key = runner._source_manifest_study_key(secret, low_priority_study_uid)
    low_priority_series_key = runner._source_manifest_series_key(secret, low_priority_series_uid)
    nontrain_study_key = runner._source_manifest_study_key(secret, "1.2.826.0.1.7103")
    database_path = tmp_path / "private_manifest.sqlite3"
    audit_key_path = tmp_path / "audit_key.bin"
    audit_key_path.write_bytes(secret)

    connection = sqlite3.connect(database_path)
    connection.executescript(producer_manifest.PRIVATE_SCHEMA_SQL)
    metadata = {
        "audit_id": f"manifest-audit-{code_commit[:12]}",
        "bundle_sha256": bundle_sha256,
        "code_commit": code_commit,
        "manifest_version": runner.SOURCE_MANIFEST_VERSION,
        "schema_sha256": schema_sha256,
        "five_levels_reconciled": "true",
        **{
            f"reconciliation:{name}": "pass"
            for name in ("studies", "series", "files", "reports", "official_label_cells")
        },
        **{
            f"table_sha256:{name}": "f" * 64
            for name in runner.SOURCE_MANIFEST_TABLES - {"manifest_run"}
        },
    }
    connection.executemany("INSERT INTO manifest_run VALUES(?,?)", metadata.items())
    connection.execute(
        """INSERT INTO study_manifest(
                study_key,split,source_row_count,patient_key_evidence,series_count,
                plane_availability,sequence_categories,total_slice_count,report_available,
                label_status,known_label_count,positive_label_count,negative_label_count,
                data_quality_flags,terminal_state
            ) VALUES(?,'train',1,'study_uid',1,'sagittal','fluid_sensitive',0,0,
                'unavailable',0,0,0,'[]','pass')""",
        (study_key,),
    )
    connection.execute(
        """INSERT INTO series_manifest(
                series_key,study_key,source_row_count,plane,fluid_sensitive,fat_suppression,
                slice_count,missing_tag_flags,quality_score,localizer_likelihood,
                ordering_method,orientation_state,spacing_state,decode_state,terminal_state
            ) VALUES(?,?,1,'sagittal','true','false',0,'[]',100,0,
                'physical','consistent','consistent','decoded','pass')""",
        (series_key, study_key),
    )
    connection.execute(
        "INSERT INTO protected_component VALUES('hard-protected',?,?, 'singleton')",
        ("c" * 64, study_key),
    )
    connection.execute(
        """INSERT INTO manifest_issue VALUES(
                'study',?,'pixel_decode_remediated','warning','none','remediated','v1',
                'decoder','v1','remediated','v1','study','{}')""",
        (study_key,),
    )
    connection.execute(
        "INSERT INTO qa_sample VALUES('quality',?,?, 'deterministic_stratified_review',1)",
        ("d" * 64, study_key),
    )
    distractors = ((low_priority_study_key, "train", 2, 1), (nontrain_study_key, "test", 1, 0))
    connection.executemany(
        """INSERT INTO study_manifest(
                study_key,split,source_row_count,patient_key_evidence,series_count,
                plane_availability,sequence_categories,total_slice_count,report_available,
                label_status,known_label_count,positive_label_count,negative_label_count,
                data_quality_flags,terminal_state
            ) VALUES(?,?,1,'study_uid',?,'missing','missing',0,0,
                'unavailable',0,0,0,'[]','pass')""",
        ((key, split, series_count) for key, split, _priority, series_count in distractors),
    )
    connection.execute(
        """INSERT INTO series_manifest(
                series_key,study_key,source_row_count,plane,fluid_sensitive,fat_suppression,
                slice_count,missing_tag_flags,quality_score,localizer_likelihood,
                ordering_method,orientation_state,spacing_state,decode_state,terminal_state
            ) VALUES(?,?,1,'sagittal','true','false',0,'[]',100,0,
                'physical','consistent','consistent','decoded','pass')""",
        (low_priority_series_key, low_priority_study_key),
    )
    connection.executemany(
        "INSERT INTO qa_sample VALUES('quality',?,?, 'deterministic_stratified_review',?)",
        (
            ("0" * 63 + str(priority), key, priority)
            for key, _split, priority, _series_count in distractors
        ),
    )
    connection.commit()
    connection.close()

    binding = replace(
        _source_binding(code_commit=code_commit, bundle_sha256=bundle_sha256),
        database_path=database_path,
        audit_key_path=audit_key_path,
        database_sha256=hashlib.sha256(database_path.read_bytes()).hexdigest(),
        audit_key_sha256=hashlib.sha256(secret).hexdigest(),
        schema_sha256=schema_sha256,
    )
    facts, _, reconciliation = runner._load_source_manifest_facts(binding, (row, low_priority_row))
    try:
        assert facts[study_uid]["remediated_decode_case"] == ("present",)
        assert facts[study_uid]["protected_duplicate_group"] == ()
        assert reconciliation.performance_sample_study_uids == (study_uid,)
    finally:
        reconciliation.connection.close()


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
    return runner.SourceManifestReconciliation(
        connection,
        secret,
        len(rows),
        files,
        tuple(sorted({row.study_uid for row in rows})),
    )


def _run_full(
    *,
    competition_root: Path,
    rows: tuple[Any, ...],
    manifest_path: Path,
    source_available: bool,
    progress: list[str] | None = None,
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
            selection_minimum_eligible=3,
            progress=progress.append if progress is not None else None,
        )
    finally:
        if reconciliation is not None:
            reconciliation.connection.close()
    return metrics, representatives, selection


def _manifest_records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="ascii").splitlines()]


def test_performance_smoke_projects_full_pass_and_fails_before_budget_burn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    competition = tmp_path / "competition"
    rows, requested_states = _rows_and_files(competition)
    monkeypatch.setattr(runner, "_full_series_state", _fake_series_state_factory(requested_states))
    times = iter((0.0, 100.0, 200.0, 300.0))
    monkeypatch.setattr(runner.time, "perf_counter", lambda: next(times))
    base = _source_reconciliation(competition, rows)
    reconciliation = replace(
        base,
        expected_series_count=base.expected_series_count * 2,
        expected_file_count=base.expected_file_count * 2,
    )
    arguments = {
        "competition_root": competition,
        "rows": rows,
        "reconciliation": reconciliation,
        "pipeline_module": SimpleNamespace(),
        "slots_module": slots,
        "config": SimpleNamespace(),
        "versions": SimpleNamespace(),
        "workers": 3,
        "cache_parent": tmp_path,
        "deadline_at": None,
    }
    try:
        runner._run_performance_smoke(**arguments, budget_seconds=3_901.0)
        with pytest.raises(runner.SafeRunError, match="throughput_projection_exceeds_budget"):
            runner._run_performance_smoke(**arguments, budget_seconds=3_899.0)
    finally:
        base.connection.close()
    assert not list(tmp_path.glob(".performance-smoke-cache-*"))


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
        return str(original_hash(path))

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
                *(
                    (rule.dimension, ("common",))
                    for rule in qa_strata.QA_STRATUM_REGISTRY
                    if rule.dimension != "scanner_model"
                ),
                ("scanner_model", ("singleton_model" if uid == singleton_uid else "common",)),
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
    assert first.coverage is not None
    coverage = {(item["dimension"], item["value"]): item for item in first.coverage["rows"]}
    singleton = coverage[("scanner_model", "singleton_model")]
    assert (singleton["population"], singleton["selected"], singleton["required_quota"]) == (
        1,
        1,
        1,
    )
    assert singleton["reason"] == "mandatory_represented_singleton"


def test_series_features_preserve_laterality_plane_conflict_and_individual_dicom_edges() -> None:
    orientation = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    metadata = SimpleNamespace(
        bits_stored=16,
        photometric_interpretation="MONOCHROME1",
        rows=1024,
        columns=1024,
        slice_thickness=6.0,
        spacing_between_slices=6.0,
        image_orientation=orientation,
    )
    decoded = SimpleNamespace(
        metadata=metadata,
        transfer_syntax="1.2.840.10008.1.2.4.90",
        laterality="R",
    )
    series_pass = runner.SeriesPass(
        (decoded, decoded),
        (),
        (),
        (),
        SimpleNamespace(laterality="R"),
        None,
        0.0,
        0.0,
    )
    quality = slots.SeriesQuality(
        total_slices=2,
        decoded_slices=2,
        decode_failure_count=0,
        duplicate_slices=1,
        geometry_valid=True,
        spacing_regular=True,
        median_slice_spacing_mm=6.0,
        spacing_coefficient_of_variation=0.0,
        pixel_spacing_mm=(0.5, 0.5),
        physical_coverage_mm=6.0,
    )

    features = runner._series_selection_features(
        runner.SeriesRow("study", "series", "present", "present", "sagittal"),
        series_pass,
        quality,
        "quality_blocked",
        slots,
    )

    assert features["laterality"] == ("right",)
    assert features["organizer_plane"] == ("sagittal",)
    assert features["physical_plane"] == ("coronal",)
    assert features["organizer_physical_plane_relation"] == ("conflict",)
    assert features["photometric_interpretation"] == ("monochrome1",)
    assert features["transfer_syntax"] == ("jpeg2000",)
    assert features["slice_thickness_stratum"] == ("gt_5",)
    assert features["slice_spacing_stratum"] == ("gt_5",)
    assert features["resolution_extreme"] == ("gt_512",)
    assert set(features["dicom_edge_case_subtype"]) == {
        "photometric_monochrome1",
        "quality_duplicate_slices",
        "terminal_quality_blocked",
        "transfer_jpeg2000",
    }


def test_study_features_bind_slots_abnormal_retention_and_explicit_missing_hardware() -> None:
    states = (
        {
            "selection_features": {"terminal_state": ("model_eligible",)},
            "record": {
                "series_uid": "series-a",
                "slot": "sagittal_structural",
                "original_slot": "sagittal_structural",
                "retention_reasons": [],
                "model_eligible": True,
                "terminal_state": "model_eligible",
            },
        },
        {
            "selection_features": {"terminal_state": ("quality_blocked",)},
            "record": {
                "series_uid": "series-b",
                "slot": "additional_or_duplicate",
                "original_slot": None,
                "retention_reasons": ["unknown_plane"],
                "model_eligible": False,
                "terminal_state": "quality_blocked",
            },
        },
        {
            "selection_features": {"terminal_state": ("model_eligible",)},
            "record": {
                "series_uid": "series-c",
                "slot": "additional_or_duplicate",
                "original_slot": "sagittal_structural",
                "retention_reasons": ["duplicate_slot"],
                "model_eligible": True,
                "terminal_state": "model_eligible",
            },
        },
    )

    study = runner._cohort_study("study", states, (False, True, False, False, False, False), None)
    dimensions = dict(study.dimensions)

    assert {rule.dimension for rule in qa_strata.QA_STRATUM_REGISTRY} <= set(dimensions)
    assert dimensions["additional_diagnostic_series"] == ("present",)
    assert dimensions["multiple_series_per_slot"] == ("present",)
    assert dimensions["missing_diagnostic_slot"] == ("present",)
    assert dimensions["retained_nonduplicate_abnormal_series"] == ("present",)
    assert dimensions["duplicate_handling"] == ("duplicate_slot",)
    assert dimensions["pipeline_case"] == ("recoverable",)
    for dimension in (
        "scanner_manufacturer",
        "scanner_model",
        "field_strength",
        "site_domain_cluster",
        "source_manifest_quality_flag",
    ):
        assert dimensions[dimension] == ("missing",)


def test_multiple_series_per_slot_counts_quality_blocked_original_slots() -> None:
    candidates = tuple(
        slots.SeriesCandidate(
            series_key=series_key,
            tie_break_key=hashlib.sha256(series_key.encode("ascii")).hexdigest(),
            organizer_plane="sagittal",
            organizer_fluid_sensitive=False,
            image_orientation_patient=None,
            quality=_quality(files=2, terminal="decode_blocked"),
        )
        for series_key in ("blocked-a", "blocked-b")
    )
    assignment = slots.assign_series_slots(candidates)
    slot_assignments = runner._slot_assignment_by_series(assignment)
    states = tuple(
        {
            "selection_features": {"terminal_state": ("decode_blocked",)},
            "record": {
                "series_uid": candidate.series_key,
                "slot": slot_assignments[candidate.series_key][0],
                "original_slot": slot_assignments[candidate.series_key][1],
                "retention_reasons": list(slot_assignments[candidate.series_key][2]),
                "model_eligible": False,
                "terminal_state": "decode_blocked",
            },
        }
        for candidate in candidates
    )

    assert all(selection.primary is None for selection in assignment.primary_slots)
    assert {
        item.original_slot.value if item.original_slot is not None else None
        for item in assignment.additional_or_duplicate
    } == {"sagittal_structural"}
    assert {
        reason.value for item in assignment.additional_or_duplicate for reason in item.reasons
    } == {"blocked_quality"}

    study = runner._cohort_study("study", states, assignment.missing_mask, None)
    dimensions = dict(study.dimensions)
    assert dimensions["multiple_series_per_slot"] == ("present",)
    assert dimensions["duplicate_handling"] == ("none",)


def test_full_run_is_permutation_deterministic_private_and_terminally_reconciled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    competition = tmp_path / "competition"
    rows, requested_states = _rows_and_files(competition)
    monkeypatch.setattr(runner, "_full_series_state", _fake_series_state_factory(requested_states))
    first_path = tmp_path / "first.jsonl"
    second_path = tmp_path / "second.jsonl"
    progress: list[str] = []

    first_metrics, first_representatives, first_selection = _run_full(
        competition_root=competition,
        rows=rows,
        manifest_path=first_path,
        source_available=True,
        progress=progress,
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
    assert progress == ["q1", "q2", "q3"]
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
        "maximum_bytes": runner.RUN_PRIVATE_OUTPUT_POLICY["private_full_run_manifest.jsonl"],
    }
    series_records = [series for study in study_records for series in study["series"]]
    assert len(series_records) == len(rows) == 6
    assert {record["series_uid"] for record in series_records} == {row.series_uid for row in rows}
    assert all("original_slot" in record for record in series_records)
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

    assert first_selection.cohort_sha256 == first_metrics["qa_cohort_selection"]["cohort_sha256"]


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
    return cast(
        dict[str, Any],
        runner._full_series_state(
            competition_root=root,
            row=row,
            pipeline_module=SimpleNamespace(),
            slots_module=slots,
            config=SimpleNamespace(),
            versions=SimpleNamespace(),
            cache_root=root,
            deadline_at=None,
        ),
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

    metrics, _, selection_plan = _run_full(
        competition_root=competition,
        rows=rows,
        manifest_path=tmp_path / "unavailable.jsonl",
        source_available=False,
    )

    selection = metrics["qa_cohort_selection"]
    assert selection["source_manifest_gate"] == "unavailable_source_manifest"
    source_dimensions = {
        "scanner_manufacturer",
        "scanner_model",
        "field_strength",
        "site_domain_cluster",
        "source_manifest_quality_flag",
    }
    assert selection_plan.coverage is not None
    unavailable = [
        item for item in selection_plan.coverage["rows"] if item["dimension"] in source_dimensions
    ]
    assert {item["dimension"] for item in unavailable} == source_dimensions
    assert all(item["value"] == "missing" for item in unavailable)
    assert all(item["quota_met"] is True for item in unavailable)
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
            "slot": "additional_or_duplicate",
            "original_slot": "axial_structural",
            "retention_reasons": ("blocked_quality",),
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


def _registry_dimensions(
    domain_bucket: str = "singleton",
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    values = {
        "laterality": "left",
        "organizer_plane": "axial",
        "physical_plane": "axial",
        "organizer_physical_plane_relation": "match",
        "assigned_diagnostic_slot": "axial_structural",
        "additional_diagnostic_series": "absent",
        "multiple_series_per_slot": "absent",
        "missing_diagnostic_slot": "absent",
        "retained_nonduplicate_abnormal_series": "absent",
        "duplicate_handling": "none",
        "bit_depth_category": "le_16",
        "photometric_interpretation": "monochrome2",
        "transfer_syntax": "uncompressed_little_endian",
        "slice_thickness_stratum": "le_3",
        "slice_spacing_stratum": "le_1_5",
        "resolution_extreme": "le_512",
        "slice_count_extreme": "typical",
        "scanner_manufacturer": "vendor",
        "scanner_model": "model",
        "field_strength": "le_3",
        "site_domain_cluster": domain_bucket,
        "source_manifest_quality_flag": "none",
        "terminal_state": "model_eligible",
        "pipeline_case": "clean",
        "dicom_edge_case_subtype": "none",
    }
    assert set(values) == set(runner.REQUIRED_REVIEW_DIMENSIONS)
    return tuple((dimension, (values[dimension],)) for dimension in sorted(values))


def test_opaque_domain_keys_are_bounded_before_mandatory_selection() -> None:
    raw_domains: list[object] = [None]
    raw_domains.extend(f"opaque-{index}" for index in range(241))
    raw_domains.extend(["rare"] * 3)
    raw_domains.extend(["represented"] * 5)
    raw_domains.extend(["common"] * 20)

    buckets = runner._domain_cluster_buckets(raw_domains)

    assert buckets[0] == "missing"
    assert set(buckets[1:242]) == {"singleton"}
    assert set(buckets) == {
        "missing",
        "singleton",
        "rare_2_4",
        "represented_5_19",
        "represented_20_plus",
    }
    studies = tuple(
        runner.CohortStudy(
            study_uid=f"study-{index:04d}",
            stratum=("diagnostic",),
            dimensions=_registry_dimensions(bucket),
            eligible_series_uids=(f"series-{index:04d}",),
        )
        for index, bucket in enumerate(buckets)
    )
    selection = runner._select_after_full_pass(
        studies,
        source_manifest_available=True,
        target=100,
        minimum_eligible=100,
    )

    assert len(selection.studies) == 100
    assert selection.coverage is not None
    domain_rows = [
        item for item in selection.coverage["rows"] if item["dimension"] == "site_domain_cluster"
    ]
    assert {item["value"] for item in domain_rows} == set(buckets)
    assert all(item["quota_met"] is True for item in domain_rows)


def _review_run_config() -> dict[str, Any]:
    return {
        "code_commit": "a" * 40,
        "bundle_sha256": "b" * 64,
        "workers": 1,
        "provenance": {
            "runner_sha256": hashlib.sha256(
                (ROOT / "kaggle" / "dicom_qa" / "run.py").read_bytes()
            ).hexdigest(),
            "performance_smoke_sha256": "c" * 64,
            "performance_smoke_policy_sha256": "d" * 64,
            "preprocessing_config_sha256": "e" * 64,
            "preprocessing_version": "dicom-model-v1",
            "review_finalizer_sha256": "f" * 64,
        },
        "privacy": {"canary": "private_canary_not_emitted"},
        "anatomical_safety": {},
    }


def _private_comparison_payload(metrics: dict[str, Any], plan_sha256: str) -> bytes:
    return cast(
        bytes,
        runner._canonical_json_bytes(
            {
                "schema_version": 1,
                "artifact_type": "private-dicom-run-comparison",
                "status": "pass",
                "exact_manifest_byte_equality": True,
                "cohort_plan_byte_equality": True,
                "cohort_plan_sha256": plan_sha256,
                "manifest_sha256": metrics["manifest_sha256"],
                "studies": metrics["studies_processed"],
                "series": metrics["series_processed"],
                "files": metrics["files_processed"],
                "terminal_counts": metrics["terminal_counts"],
                "deterministic_metric_keys": [
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
                ],
                "expected_nondeterministic_fields": [
                    "phase_timings",
                    "wall_time",
                    "cpu_time",
                    "cpu_utilization",
                    "throughput",
                    "peak_memory",
                ],
                "unresolved_mismatches": 0,
            },
        ),
    )


def _performance_smoke_payload(run_config: dict[str, Any]) -> bytes:
    provenance = run_config["provenance"]
    return cast(
        bytes,
        runner._canonical_json_bytes(
            {
                "schema_version": 1,
                "artifact_type": "dicom-qa-performance-smoke-sanitized-aggregate",
                "status": "pass",
                "full_run_started": False,
                "provenance": {
                    "git_commit": run_config["code_commit"],
                    "bundle_sha256": run_config["bundle_sha256"],
                    "runner_sha256": provenance["runner_sha256"],
                    "smoke_entrypoint_sha256": provenance["performance_smoke_sha256"],
                    "performance_smoke_policy_sha256": provenance[
                        "performance_smoke_policy_sha256"
                    ],
                    "preprocessing_config_sha256": provenance["preprocessing_config_sha256"],
                    "preprocessing_version": provenance["preprocessing_version"],
                    "source_manifest_version": runner.SOURCE_MANIFEST_VERSION,
                    "source_manifest_audit_id": runner.SOURCE_MANIFEST_AUDIT_ID,
                    "input_binding_sha256": "1" * 64,
                },
                "runtime": {
                    "private_kernel": True,
                    "internet": False,
                    "accelerator": "cpu",
                    "self_deadline_seconds": 3_600,
                    "full_pass_budget_seconds": runner.SELF_DEADLINE_SECONDS,
                    "competition_cpu_limit_seconds": 32_400,
                },
                "performance": {
                    "production_path_exercised": True,
                    "authenticated_sample": True,
                    "admission_status": "pass",
                    "smoke_elapsed_seconds_ceiling": 60,
                    "projected_full_run_seconds_ceiling": 600,
                    "post_comparison_preparation_path_exercised": True,
                    "qa_replay_render_seconds_per_series_ceiling": 1,
                    "representative_benchmark_seconds_ceiling": 60,
                    "review_artifacts_per_series_ceiling": 7,
                    "review_artifact_bytes_per_series_power_of_two_mib_ceiling": 1,
                },
                "privacy": {
                    "identifiers_emitted": False,
                    "paths_emitted": False,
                    "pixels_emitted": False,
                    "reports_emitted": False,
                    "private_resource_locators_emitted": False,
                    "private_artifact_checksums_emitted": False,
                },
            },
        ),
    )


def _stage_b_inputs(tmp_path: Path) -> SimpleNamespace:
    run_config = _review_run_config()
    quality = slots.SeriesQuality(
        total_slices=20,
        decoded_slices=20,
        decode_failure_count=0,
        duplicate_slices=0,
        geometry_valid=True,
        spacing_regular=True,
        median_slice_spacing_mm=5.0,
        spacing_coefficient_of_variation=0.0,
        pixel_spacing_mm=(0.5, 0.5),
        physical_coverage_mm=95.0,
    )
    assert not quality.blocked
    provenance = {
        "configuration_hash": "2" * 64,
        "preprocessing_version": "dicom-model-v1",
        "source_manifest_version": runner.SOURCE_MANIFEST_VERSION,
        "dicom_library_versions": [
            [name, "1.0"]
            for name in (
                "numpy",
                "pydicom",
                "pylibjpeg",
                "pylibjpeg-libjpeg",
                "pylibjpeg-openjpeg",
            )
        ],
    }
    reconstruction = {
        "laterality": "L",
        "transformation_ledger": {
            "laterality_transform": "none",
            "horizontal_flip_applied": False,
        },
        "provenance": provenance,
    }
    rows = tuple(
        runner.SeriesRow(
            f"1.2.826.0.1.{10_000 + index}",
            f"1.2.826.0.2.{20_000 + index}",
            "absent",
            "absent",
            "axial",
        )
        for index in range(100)
    )
    cohort_studies = tuple(
        runner.CohortStudy(
            study_uid=row.study_uid,
            stratum=tuple(f"stratum-{value}" for value in range(11)),
            dimensions=_registry_dimensions(),
            eligible_series_uids=(row.series_uid,),
        )
        for row in rows
    )
    selection_plan = runner._select_after_full_pass(
        cohort_studies,
        source_manifest_available=True,
        target=100,
        minimum_eligible=100,
    )
    quality_payload = {
        "blocked_reasons": [reason.value for reason in quality.blocked_reasons],
        "components": runner.asdict(quality.components),
    }
    manifest_records: list[dict[str, Any]] = [
        {
            "schema_version": 1,
            "artifact_type": "private-dicom-full-run-manifest",
            "record_type": "header",
            "provenance": {
                "git_commit": run_config["code_commit"],
                "bundle_sha256": run_config["bundle_sha256"],
            },
        }
    ]
    manifest_records.extend(
        {
            "record_type": "study",
            "study_uid": row.study_uid,
            "missing_series_mask": [False] * 6,
            "series": [
                {
                    "series_uid": row.series_uid,
                    "source": {
                        "plane": row.plane,
                        "fluid_sensitive": row.fluid_sensitive,
                        "fat_suppression": row.fat_suppression,
                    },
                    "files": 1,
                    "slot": "axial_structural",
                    "original_slot": "axial_structural",
                    "retention_reasons": [],
                    "quality": quality_payload,
                    "source_failure": None,
                    "decode_failures": [],
                    "ordering_failure": None,
                    "preprocessing_failure": None,
                    "terminal_state": "model_eligible",
                    "model_output_reconstruction": reconstruction,
                }
            ],
        }
        for row in rows
    )
    manifest_records.append({"record_type": "footer"})
    manifest_payload = b"".join(runner._canonical_json_bytes(record) for record in manifest_records)
    manifest_path = tmp_path / "private_full_run_manifest.jsonl"
    manifest_path.write_bytes(manifest_payload)
    manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()
    assert selection_plan.coverage is not None
    coverage_sha256 = hashlib.sha256(
        runner._canonical_json_bytes(selection_plan.coverage)
    ).hexdigest()
    metrics: dict[str, Any] = {
        "schema_version": 1,
        "artifact_type": "private-dicom-full-run-metrics",
        "input_identity": _source_identity(),
        "studies_processed": 100,
        "series_processed": 100,
        "files_processed": 100,
        "terminal_counts": {"model_eligible": 100},
        "model_eligible_series": 100,
        "logical_cache_bytes": 1024,
        "manifest_sha256": manifest_sha256,
        "manifest_bytes": len(manifest_payload),
        "qa_cohort_selection": {
            "selected_studies": 100,
            "eligible_series": 100,
            "cohort_sha256": selection_plan.cohort_sha256,
            "source_manifest_gate": "pass",
            "coverage_ledger_sha256": coverage_sha256,
            "cohort_plan_sha256": None,
        },
        "coverage_ledger_sha256": coverage_sha256,
        "timings_seconds": {
            "total_seconds": 100.0,
            "decode_seconds": 20.0,
            "ordering_seconds": 2.0,
            "slot_assignment_seconds": 1.0,
            "preprocessing_seconds": 20.0,
            "cache_generation_seconds": 1.0,
            "qa_generation_seconds": 0.0,
        },
        "full_dataset_wall_seconds": 100.0,
        "total_wall_seconds": 100.0,
        "process_cpu_seconds": 20.0,
        "cpu_capacity_threads": 1,
        "cpu_utilization_percent": 20.0,
        "process_peak_rss_bytes": 1_200,
        "process_peak_rss_increase_bytes": 200,
        "peak_ephemeral_cache_bytes": 1024,
        "peak_private_working_disk_bytes": len(manifest_payload),
    }
    representatives = tuple(
        runner.RepresentativeSeriesInput(
            profile=profile,
            slice_count=1,
            study_uid=rows[index].study_uid,
            series_uid=rows[index].series_uid,
            paths=(tmp_path / "slice.dcm",),
        )
        for profile, index in (("small", 0), ("median", 49), ("large", 99))
    )
    evidence = {
        (row.study_uid, row.series_uid): {"terminal_state": "model_eligible"} for row in rows
    }
    plan_payload = runner._cohort_plan_payload(
        run_config=run_config,
        metrics=metrics,
        rows=rows,
        representatives=representatives,
        selection_plan=selection_plan,
        replay_evidence=evidence,
    )
    plan_sha256 = hashlib.sha256(plan_payload).hexdigest()
    metrics["qa_cohort_selection"]["cohort_plan_sha256"] = plan_sha256
    metrics["cohort_plan_sha256"] = plan_sha256
    plan_path = tmp_path / "private_cohort_plan.json"
    plan_path.write_bytes(plan_payload)
    metrics_path = tmp_path / "private_full_run_metrics.json"
    metrics_path.write_bytes(runner._canonical_json_bytes(metrics))
    comparison_path = tmp_path / "private_run_comparison.json"
    comparison_path.write_bytes(_private_comparison_payload(metrics, plan_sha256))
    slice_path = tmp_path / "slice.dcm"
    slice_path.write_bytes(b"synthetic")
    return SimpleNamespace(
        run_config=run_config,
        rows=rows,
        quality=quality,
        reconstruction=reconstruction,
        metrics=metrics,
        manifest_path=manifest_path,
        metrics_path=metrics_path,
        plan_path=plan_path,
        plan_payload=plan_payload,
        comparison_path=comparison_path,
        smoke_payload=_performance_smoke_payload(run_config),
        slice_path=slice_path,
    )


def test_cohort_plan_is_canonical_bound_and_tamper_evident(tmp_path: Path) -> None:
    fixture = _stage_b_inputs(tmp_path)

    assert fixture.plan_payload == runner._canonical_json_bytes(json.loads(fixture.plan_payload))
    assert len(fixture.plan_payload) <= runner.RUN_PRIVATE_OUTPUT_POLICY["private_cohort_plan.json"]
    validated = runner._validated_cohort_plan(
        fixture.plan_payload,
        run_config=fixture.run_config,
        metrics=fixture.metrics,
    )
    assert validated["selection"]["selected_studies"] == 100
    assert "selection_census" not in validated

    tampered = json.loads(fixture.plan_payload)
    tampered["studies"][0]["selection_stratum"][0] = "changed"
    with pytest.raises(runner.SafeRunError, match="private_cohort_plan_invalid"):
        runner._validated_cohort_plan(
            runner._canonical_json_bytes(tampered),
            run_config=fixture.run_config,
            metrics=fixture.metrics,
        )


def test_core_stage_emits_only_core_outputs_without_post_pass_qa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / runner.OUTPUT_DIRECTORY
    run_config = {
        "code_commit": "a" * 40,
        "bundle_sha256": "b" * 64,
        "workers": 1,
        "input_identity": {"source_manifest": {}},
    }

    class Connection:
        def close(self) -> None:
            return None

    reconciliation = SimpleNamespace(connection=Connection())
    monkeypatch.setattr(runner, "_decoder_preflight", lambda: None)
    monkeypatch.setattr(runner, "_read_series_rows", lambda _path: ())
    monkeypatch.setattr(runner, "_discover_source_manifest_binding", lambda *_args: object())
    monkeypatch.setattr(
        runner,
        "_load_source_manifest_facts",
        lambda *_args: ({}, {}, reconciliation),
    )
    monkeypatch.setattr(runner, "_preprocessing_config", lambda *_args: object())

    def fake_full_pass(**kwargs: Any) -> tuple[Any, ...]:
        kwargs["private_manifest_path"].write_bytes(b"manifest\n")
        return (
            {
                "qa_cohort_selection": {"coverage_ledger_sha256": "1" * 64},
                "total_wall_seconds": 1.0,
                "timings_seconds": {"total_seconds": 1.0},
                "cpu_capacity_threads": 1,
                "process_peak_rss_bytes": 1,
            },
            (),
            None,
            runner.SelectionPlan(()),
            {},
        )

    monkeypatch.setattr(runner, "_run_full_dataset_pass", fake_full_pass)
    monkeypatch.setattr(runner, "_cohort_plan_payload", lambda **_kwargs: b'{"plan":true}\n')
    monkeypatch.setattr(runner, "_validated_cohort_plan", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(runner, "_core_summary_payload", lambda **_kwargs: b'{"summary":true}\n')
    monkeypatch.setattr(
        runner, "_core_inventory_payload", lambda **_kwargs: b'{"inventory":true}\n'
    )
    monkeypatch.setattr(runner, "_validate_run_summary", lambda *_args: {})
    monkeypatch.setattr(runner, "_validate_run_inventory", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        runner,
        "_run_preparation_smoke",
        lambda **_kwargs: pytest.fail("Stage A must not run preparation smoke"),
    )
    monkeypatch.setattr(
        runner,
        "_replay_render_series",
        lambda **_kwargs: pytest.fail("Stage A must not replay or render"),
    )

    runner._run_private_core(
        input_root=tmp_path,
        competition_root=tmp_path,
        output_root=output,
        run_config=run_config,
        preprocessing_config_path=tmp_path / "preprocessing.yaml",
        inference_limit_seconds=32_400,
    )

    assert {item.name for item in output.iterdir()} == {
        "private_full_run_manifest.jsonl",
        "private_full_run_metrics.json",
        "private_cohort_plan.json",
        "sanitized_summary.json",
        "sanitized_artifact_inventory.json",
    }
    assert not (output / "benchmark.md").exists()
    assert not (output / runner.PRIVATE_REVIEW_DIRECTORY).exists()


def test_preparation_refuses_plan_comparison_and_capacity_changes_before_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _stage_b_inputs(tmp_path)
    staging = tmp_path / "staging"
    staging.mkdir()
    rendered = False

    def forbidden_render(**_kwargs: Any) -> Any:
        nonlocal rendered
        rendered = True
        pytest.fail("capacity and identity gates must run before pixels")

    monkeypatch.setattr(runner, "_replay_render_series", forbidden_render)
    common = {
        "competition_root": tmp_path,
        "output_root": tmp_path / "review-output",
        "staging_parent": staging,
        "run_config": fixture.run_config,
        "preprocessing_config_path": tmp_path / "preprocessing.yaml",
        "full_manifest_path": fixture.manifest_path,
        "full_metrics_path": fixture.metrics_path,
        "comparison_proof_path": fixture.comparison_path,
        "performance_smoke_summary_payload": fixture.smoke_payload,
        "review_plan_ref": "owner/review-plan",
        "review_plan_version": 1,
        "inference_limit_seconds": 32_400,
        "deadline_at": None,
    }
    changed_plan = json.loads(fixture.plan_payload)
    changed_plan["studies"][0]["selection_stratum"][0] = "changed"
    changed_plan_path = tmp_path / "changed-plan.json"
    changed_plan_path.write_bytes(runner._canonical_json_bytes(changed_plan))
    with pytest.raises(runner.SafeRunError, match="private_cohort_plan_invalid"):
        runner.prepare_private_review(cohort_plan_path=changed_plan_path, **common)

    changed_comparison = json.loads(fixture.comparison_path.read_bytes())
    changed_comparison["manifest_sha256"] = "9" * 64
    changed_comparison_path = tmp_path / "changed-comparison.json"
    changed_comparison_path.write_bytes(runner._canonical_json_bytes(changed_comparison))
    with pytest.raises(runner.SafeRunError, match="comparison_proof_invalid"):
        runner.prepare_private_review(
            cohort_plan_path=fixture.plan_path,
            **{**common, "comparison_proof_path": changed_comparison_path},
        )

    with pytest.raises(runner.SafeRunError, match="qa_preparation_runtime_exceeds_budget"):
        runner.prepare_private_review(
            cohort_plan_path=fixture.plan_path,
            **{
                **common,
                "deadline_at": runner.time.monotonic() + 1,
            },
        )
    assert rendered is False


def test_prepare_private_review_materializes_bound_outputs_and_combined_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rsna_knee.dicom import benchmark as benchmark_module
    from rsna_knee.qa import preprocessing as qa_module

    fixture = _stage_b_inputs(tmp_path)
    staging = tmp_path / "staging"
    staging.mkdir()
    output = tmp_path / "review-output"
    monkeypatch.setattr(runner, "_decoder_preflight", lambda: None)
    monkeypatch.setattr(runner, "_read_series_rows", lambda _path: fixture.rows)
    monkeypatch.setattr(runner, "_preprocessing_config", lambda *_args: object())
    monkeypatch.setattr(runner, "_series_files", lambda *_args: (fixture.slice_path,))
    perf_values = iter((100.0, 105.0))
    cpu_values = iter((10.0, 14.0))
    rss_values = iter((1_000, 1_500))
    monkeypatch.setattr(runner.time, "perf_counter", lambda: next(perf_values))
    monkeypatch.setattr(runner, "_cpu_seconds", lambda: next(cpu_values))
    monkeypatch.setattr(runner, "_peak_rss_bytes", lambda: next(rss_values))

    artifact_suffixes = (
        "contact.png",
        "orthogonal.png",
        "histogram.png",
        "animation.gif",
        "before_after.png",
        "review.json",
        "metadata.json",
    )

    def fake_replay(**kwargs: Any) -> tuple[Any, ...]:
        assert kwargs["expected_model_reconstruction"] == fixture.reconstruction
        case = kwargs["case_ordinal"]
        series = kwargs["series_ordinal"]
        records: list[dict[str, object]] = []
        for suffix in artifact_suffixes:
            basename = f"case_{case:06d}_series_{series:03d}_{suffix}"
            payload = f"artifact-{case}-{series}-{suffix}".encode("ascii")
            (kwargs["first_output_dir"] / basename).write_bytes(payload)
            records.append(
                {
                    "basename": basename,
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        ordered = SimpleNamespace(
            laterality="L",
            slices=(
                SimpleNamespace(
                    metadata=SimpleNamespace(image_orientation=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0))
                ),
            ),
        )
        return (
            fixture.reconstruction,
            fixture.reconstruction,
            fixture.quality,
            ordered,
            tuple(records),
            0.01,
        )

    monkeypatch.setattr(runner, "_replay_render_series", fake_replay)

    def fake_benchmark(
        _paths: tuple[Path, ...],
        _config: object,
        _versions: object,
        *,
        iterations: int,
        worker_counts: tuple[int, ...],
        offline_bundle_verified: bool,
    ) -> Any:
        assert worker_counts == (1,)
        assert offline_bundle_verified is True
        timing = benchmark_module.TimingSummary(0.01, 0.02, 0.03)
        return benchmark_module.BenchmarkReport(
            schema_version=1,
            iterations=iterations,
            slices_per_series=1,
            decode_time=timing,
            preprocessing_time=timing,
            representative_tensor_cache_bytes=1024,
            process_peak_rss_bytes=1024,
            peak_rss_increase_bytes=0,
            cpu_parallelism=(benchmark_module.WorkerTiming(1, 1, 1.0, 1.0, 1.0),),
            kaggle_compatibility=benchmark_module.KaggleCompatibility(
                python_version="3.11.0",
                platform_system="Linux",
                platform_machine="x86_64",
                cpu_count=1,
                numpy_version="1.0",
                pydicom_version="1.0",
                python_supported=True,
                linux_runtime_observed=True,
                offline_bundle_verified=True,
                kaggle_runtime_verified=True,
                accelerator="cpu",
                horizontal_flip=False,
                through_plane_resampling=False,
            ),
            deterministic_replay=True,
        )

    monkeypatch.setattr(benchmark_module, "benchmark_dicom_pipeline", fake_benchmark)

    runner.prepare_private_review(
        competition_root=tmp_path,
        output_root=output,
        staging_parent=staging,
        run_config=fixture.run_config,
        preprocessing_config_path=tmp_path / "preprocessing.yaml",
        full_manifest_path=fixture.manifest_path,
        full_metrics_path=fixture.metrics_path,
        cohort_plan_path=fixture.plan_path,
        comparison_proof_path=fixture.comparison_path,
        performance_smoke_summary_payload=fixture.smoke_payload,
        review_plan_ref="owner/review-plan",
        review_plan_version=1,
        inference_limit_seconds=32_400,
        deadline_at=None,
    )

    assert {item.name for item in output.iterdir()} == {
        "private_case_index.json",
        "private_artifact_inventory.json",
        "private-review",
        "sanitized_summary.json",
        "benchmark.md",
        "sanitized_artifact_inventory.json",
    }
    assert len(tuple((output / "private-review").iterdir())) == 700
    case = json.loads((output / "private_case_index.json").read_bytes())
    inventory = json.loads((output / "private_artifact_inventory.json").read_bytes())
    full_run = case["full_run"]
    assert "selection_census" not in case
    assert case["qa_cohort_selection"] == full_run["qa_cohort_selection"]
    assert case["studies"][0]["registry_memberships"]
    assert len(case["represented_review_strata"]) == 1
    assert full_run["qa_preparation_process_cpu_seconds"] == 4.0
    assert full_run["process_cpu_seconds"] == 24.0
    assert full_run["process_peak_rss_bytes"] == 1_500
    assert full_run["process_peak_rss_increase_bytes"] == 500
    assert full_run["total_wall_seconds"] == 105.0
    assert full_run["cpu_utilization_percent"] == pytest.approx(100 * 24 / 105)
    capacity = case["capacity_certificate"]
    assert capacity["provenance"] == {
        "git_commit": fixture.run_config["code_commit"],
        "bundle_sha256": fixture.run_config["bundle_sha256"],
        "review_plan_ref": "owner/review-plan",
        "review_plan_version": 1,
        "performance_smoke_summary_sha256": hashlib.sha256(fixture.smoke_payload).hexdigest(),
        "full_run_manifest_sha256": fixture.metrics["manifest_sha256"],
        "cohort_plan_sha256": fixture.metrics["cohort_plan_sha256"],
        "comparison_sha256": hashlib.sha256(fixture.comparison_path.read_bytes()).hexdigest(),
        "qa_renderer_version": qa_module.RENDERER_VERSION,
        "qa_stratum_registry_version": runner.QA_STRATUM_REGISTRY_VERSION,
        "qa_stratum_registry_sha256": runner.QA_STRATUM_REGISTRY_SHA256,
    }
    assert (
        inventory["provenance"]["private_case_index_sha256"]
        == hashlib.sha256((output / "private_case_index.json").read_bytes()).hexdigest()
    )


def test_preparation_smoke_benchmarks_full_1_3_1_shape_when_profiles_dedupe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = runner.SeriesRow("1.2.3", "1.2.4", "absent", "absent", "axial")
    path = tmp_path / "slice.dcm"
    path.write_bytes(b"synthetic")
    ordered = SimpleNamespace(model_eligible=True)
    series_pass = SimpleNamespace(
        decode_failures=(), order_failure=None, ordered=ordered, decoded=(object(),)
    )
    monkeypatch.setattr(runner, "_series_files", lambda *_args: (path,))
    monkeypatch.setattr(runner, "_decode_order_pass", lambda *_args, **_kwargs: series_pass)
    monkeypatch.setattr(runner, "_quality", lambda **_kwargs: SimpleNamespace(blocked=False))
    monkeypatch.setattr(
        runner,
        "_replay_render_series",
        lambda **_kwargs: ({}, {}, None, None, ({"bytes": 7},) * 7, 2.0),
    )
    benchmark_iterations: list[int] = []

    class Benchmark:
        @staticmethod
        def benchmark_dicom_pipeline(
            _paths: tuple[Path, ...],
            _config: object,
            _versions: object,
            *,
            iterations: int,
            worker_counts: tuple[int, ...],
            offline_bundle_verified: bool,
        ) -> None:
            del worker_counts, offline_bundle_verified
            benchmark_iterations.append(iterations)

    result = runner._run_preparation_smoke(
        competition_root=tmp_path,
        rows=(row,),
        sample_study_uids=(row.study_uid,),
        config=object(),
        versions=object(),
        pipeline_module=object(),
        qa_module=object(),
        slots_module=object(),
        benchmark_module=Benchmark,
        workers=1,
        cache_parent=tmp_path,
        deadline_at=None,
    )

    assert benchmark_iterations == [1, 3, 1]
    assert result["qa_replay_render_seconds"] == 2.0
    assert result["review_artifacts"] == 7


def test_replay_render_deletes_repeat_directory_per_series(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    @dataclass(frozen=True)
    class Config:
        sample_count: int | None = 2

    pixels = np.zeros((2, 2), dtype=np.float32)
    ordered = SimpleNamespace(
        model_eligible=True,
        laterality="L",
        slices=(
            SimpleNamespace(pixels=pixels),
            SimpleNamespace(pixels=pixels.copy()),
        ),
        geometry=SimpleNamespace(projected_positions_mm=(0.0, 1.0)),
    )
    series_pass = SimpleNamespace(
        decode_failures=(), order_failure=None, ordered=ordered, decoded=(object(), object())
    )
    monkeypatch.setattr(runner, "_decode_order_pass", lambda *_args, **_kwargs: series_pass)
    monkeypatch.setattr(runner, "_series_pass_record", lambda _result: {"same": True})
    monkeypatch.setattr(runner, "_quality", lambda **_kwargs: SimpleNamespace(blocked=False))
    monkeypatch.setattr(runner, "_qa_metadata", lambda **_kwargs: object())
    monkeypatch.setattr(
        runner,
        "_private_reconstruction_record",
        lambda result: {"marker": result.marker},
    )

    class PipelineError(Exception):
        pass

    class Pipeline:
        PipelineError: type[Exception]

        @staticmethod
        def preprocess_series(_ordered: object, config: Config, _versions: object) -> Any:
            marker = "qa" if config.sample_count is None else "model"
            return SimpleNamespace(
                marker=marker,
                tensor=np.zeros((2, 1, 2, 2), dtype=np.float32),
                provenance=(marker,),
            )

        @staticmethod
        def deterministic_slice_indices(_positions: object, _count: int) -> tuple[int, ...]:
            return (0, 1)

    Pipeline.PipelineError = PipelineError

    class Qa:
        CONTACT_MAX_SLICES = 2

        @staticmethod
        def render_private_qa(
            _source: np.ndarray,
            _processed: np.ndarray,
            *,
            metadata: object,
            output_dir: Path,
            contact_slice_indices: tuple[int, ...],
        ) -> Any:
            del metadata, contact_slice_indices
            basename = "case_000000_series_000_contact.png"
            payload = b"same-bytes"
            (output_dir / basename).write_bytes(payload)
            return SimpleNamespace(
                artifacts=(
                    SimpleNamespace(
                        basename=basename,
                        bytes=len(payload),
                        sha256=hashlib.sha256(payload).hexdigest(),
                    ),
                )
            )

    output = tmp_path / "first"
    output.mkdir()
    runner._replay_render_series(
        row=runner.SeriesRow("1.2.3", "1.2.4", "absent", "absent", "axial"),
        paths=(tmp_path / "slice.dcm",),
        case_ordinal=0,
        series_ordinal=0,
        config=Config(),
        versions=object(),
        pipeline_module=Pipeline,
        qa_module=Qa,
        slots_module=object(),
        first_output_dir=output,
        repeat_parent=tmp_path,
        deadline_at=None,
    )

    assert (output / "case_000000_series_000_contact.png").is_file()
    assert not list(tmp_path.glob(".qa-repeat-*"))
