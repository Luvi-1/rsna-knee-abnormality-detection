from __future__ import annotations

import csv
import importlib.util
import json
import sqlite3
import time
from collections.abc import Mapping
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from pydicom import config as pydicom_config
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

import rsna_knee.data.manifest as manifest_module
from rsna_knee.data.manifest import (
    REQUIRED_DECODER_PACKAGES,
    RUNNER_OUTPUTS,
    AuditConfig,
    ManifestAuditError,
    _augment_source_inventory,
    _bounded_block_pairs,
    _initialize_inspection_worker,
    _inspect_one_file,
    assert_required_decoder_runtime,
    initialize_private_database,
    insert_source_placeholders,
    load_contract,
    read_source_inventory,
    run_manifest_audit,
)
from rsna_knee.dicom.audit import DicomIssue

ROOT = Path(__file__).parents[1]


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _write_dicom(
    path: Path,
    *,
    study_uid: str,
    series_uid: str,
    sop_uid: str,
    patient_id: str,
    index: int,
) -> None:
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = MRImageStorage
    file_meta.MediaStorageSOPInstanceUID = sop_uid
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset = FileDataset(path.name, {}, file_meta=file_meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = MRImageStorage
    dataset.SOPInstanceUID = sop_uid
    dataset.StudyInstanceUID = study_uid
    dataset.SeriesInstanceUID = series_uid
    dataset.PatientID = patient_id
    dataset.PatientSex = "F"
    dataset.PatientAge = "042Y"
    dataset.Modality = "MR"
    dataset.Manufacturer = "SYNTHETIC"
    dataset.ManufacturerModelName = "FIXTURE"
    dataset.MagneticFieldStrength = "3.0"
    dataset.SeriesDescription = "sagittal synthetic"
    dataset.Rows = 16
    dataset.Columns = 16
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = 16
    dataset.BitsStored = 12
    dataset.HighBit = 11
    dataset.PixelRepresentation = 0
    dataset.PixelSpacing = ["0.5", "0.5"]
    dataset.SliceThickness = "1.0"
    dataset.SpacingBetweenSlices = "1.0"
    dataset.ImageOrientationPatient = ["1", "0", "0", "0", "1", "0"]
    dataset.ImagePositionPatient = ["0", "0", str(index)]
    dataset.InstanceNumber = index + 1
    dataset.RescaleSlope = "1"
    dataset.RescaleIntercept = "0"
    pixels = (np.arange(256, dtype=np.uint16).reshape(16, 16) + index).astype(np.uint16)
    dataset.PixelData = pixels.tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    dataset.save_as(path, enforce_file_format=True)


def _synthetic_competition(root: Path) -> tuple[str, str]:
    contract = json.loads((ROOT / "docs/competition_contract/contract.yaml").read_text())
    labels = contract["targets"]["labels"]
    train_study, test_study = generate_uid(), generate_uid()
    train_series, test_series = generate_uid(), generate_uid()
    _write_csv(
        root / "train.csv",
        ["StudyInstanceUID", "Report", *labels],
        [[train_study, "Synthetic report 12 mm", "1", "0", *([""] * 10)]],
    )
    _write_csv(root / "test.csv", ["StudyInstanceUID"], [[test_study]])
    series_header = [
        "StudyInstanceUID",
        "SeriesInstanceUID",
        "Fluid_Sensitive",
        "Fat_Suppression",
        "Anatomical_Plane",
    ]
    _write_csv(
        root / "train_series.csv",
        series_header,
        [[train_study, train_series, "true", "true", "sagittal"]],
    )
    _write_csv(
        root / "test_series.csv",
        series_header,
        [[test_study, test_series, "true", "true", "sagittal"]],
    )
    for study_uid, series_uid, split in (
        (train_study, train_series, "train"),
        (test_study, test_series, "test"),
    ):
        for index in range(5):
            sop_uid = generate_uid()
            _write_dicom(
                root / f"{split}_series" / study_uid / series_uid / f"{sop_uid}.dcm",
                study_uid=study_uid,
                series_uid=series_uid,
                sop_uid=sop_uid,
                patient_id="shared-synthetic-patient",
                index=index,
            )
    return train_study, test_study


def _run_config(path: Path) -> None:
    payload = {
        "schema_version": 1,
        "audit_id": "manifest-audit-test",
        "code_commit": "a" * 40,
        "bundle_sha256": "b" * 64,
        "workers": 2,
        "progress_every": 100,
        "qa_per_stratum": 2,
        "minimum_export_cell": 20,
        "source_context": "train-plus-example-test",
        "seed": 20260808,
        "provenance": {
            "git_commit": "a" * 40,
            "manifest_schema_sha256": "c" * 64,
            "competition_config_sha256": "d" * 64,
            "competition_contract_sha256": "e" * 64,
            "uv_lock_sha256": "f" * 64,
            "manifest_version": "manifest-v2",
            "group_version": "protected-groups-v2",
            "label_version": "official-labels-v1",
            "preprocessing_version": "unassigned",
            "decoder_packages": dict(REQUIRED_DECODER_PACKAGES),
        },
        "privacy": {
            "canary": "RSNA_PRIVATE_CANARY_fixture",
            "minimum_export_cell": 20,
            "raw_identifiers": False,
            "raw_reports": False,
            "patient_metadata": False,
            "pixel_data": False,
            "private_tables": False,
        },
        "runtime": {
            "internet": False,
            "accelerator": "cpu",
            "max_seconds": 21_600,
            "kill_before_seconds": 23_400,
        },
    }
    path.write_text(json.dumps(payload))
    path.with_name("audit-key.bin").write_bytes(b"k" * 32)


def test_required_compressed_decoders_and_runtime_policy_are_available(tmp_path: Path) -> None:
    assert assert_required_decoder_runtime() == REQUIRED_DECODER_PACKAGES
    run_config = tmp_path / "run-config.json"
    _run_config(run_config)
    assert AuditConfig.from_json(run_config).max_seconds == 21_600
    payload = json.loads(run_config.read_text())
    payload["runtime"]["kill_before_seconds"] = payload["runtime"]["max_seconds"]
    run_config.write_text(json.dumps(payload))
    with pytest.raises(ManifestAuditError, match="runtime_policy_invalid"):
        AuditConfig.from_json(run_config)


def test_inspection_worker_enforces_strict_pydicom_validation() -> None:
    previous_reading = pydicom_config.settings.reading_validation_mode
    previous_writing = pydicom_config.settings.writing_validation_mode
    try:
        pydicom_config.settings.reading_validation_mode = pydicom_config.WARN
        pydicom_config.settings.writing_validation_mode = pydicom_config.WARN
        _initialize_inspection_worker()
        assert pydicom_config.settings.reading_validation_mode == pydicom_config.RAISE
        assert pydicom_config.settings.writing_validation_mode == pydicom_config.RAISE
    finally:
        pydicom_config.settings.reading_validation_mode = previous_reading
        pydicom_config.settings.writing_validation_mode = previous_writing


def test_manifest_inspection_reads_each_source_file_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    study_uid, series_uid, sop_uid = generate_uid(), generate_uid(), generate_uid()
    path = tmp_path / "train_series" / study_uid / series_uid / f"{sop_uid}.dcm"
    _write_dicom(
        path,
        study_uid=study_uid,
        series_uid=series_uid,
        sop_uid=sop_uid,
        patient_id="synthetic-patient",
        index=0,
    )
    original_open = Path.open
    opened = 0

    def tracked_open(self: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal opened
        if self == path:
            opened += 1
        return original_open(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "open", tracked_open)
    assert _inspect_one_file(tmp_path, path, b"k" * 32).result.passed
    assert opened == 1


@pytest.mark.parametrize(
    ("stage", "expected_issue"),
    [
        ("read", DicomIssue.UNREADABLE),
        ("header", DicomIssue.UNREADABLE),
        ("decode", DicomIssue.DECODE_FAILURE),
    ],
)
def test_file_inspection_sanitizes_unexpected_input_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    expected_issue: DicomIssue,
) -> None:
    study_uid, series_uid, sop_uid = generate_uid(), generate_uid(), generate_uid()
    path = tmp_path / "train_series" / study_uid / series_uid / f"{sop_uid}.dcm"
    _write_dicom(
        path,
        study_uid=study_uid,
        series_uid=series_uid,
        sop_uid=sop_uid,
        patient_id="synthetic-patient",
        index=0,
    )

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("RSNA_PRIVATE_CANARY_untrusted_exception")

    target = {
        "header": "_header_evidence",
        "decode": "audit_dataset",
    }.get(stage)
    if target is None:
        monkeypatch.setattr("rsna_knee.data.manifest.pydicom.dcmread", fail)
    else:
        monkeypatch.setattr(manifest_module, target, fail)

    inspected = _inspect_one_file(tmp_path, path, b"k" * 32)
    assert inspected.result.issues == (expected_issue,)
    assert inspected.result.diagnostics[0].root_cause_category == "unexpected_unexplained"
    assert inspected.result.diagnostics[0].resolution_state.value == "unresolved_blocker"
    assert inspected.result.diagnostics[0].exception_type == "builtins.RuntimeError"
    assert "RSNA_PRIVATE_CANARY" not in repr(inspected)


def test_file_inspection_parse_value_error_is_not_called_source_corruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    study_uid, series_uid, sop_uid = generate_uid(), generate_uid(), generate_uid()
    path = tmp_path / "train_series" / study_uid / series_uid / f"{sop_uid}.dcm"
    _write_dicom(
        path,
        study_uid=study_uid,
        series_uid=series_uid,
        sop_uid=sop_uid,
        patient_id="synthetic-patient",
        index=0,
    )

    def parser_bug(*args: object, **kwargs: object) -> object:
        raise ValueError("RSNA_PRIVATE_CANARY_parser_detail")

    monkeypatch.setattr("rsna_knee.data.manifest.pydicom.dcmread", parser_bug)
    inspected = _inspect_one_file(tmp_path, path, b"k" * 32)

    assert inspected.result.issues == (DicomIssue.UNREADABLE,)
    assert inspected.result.diagnostics[0].root_cause_category == "unexpected_unexplained"
    assert inspected.result.diagnostics[0].resolution_state.value == "unresolved_blocker"
    assert inspected.result.diagnostics[0].exception_type == "builtins.ValueError"
    assert "RSNA_PRIVATE_CANARY" not in repr(inspected)


def test_file_inspection_does_not_hide_memory_exhaustion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    study_uid, series_uid, sop_uid = generate_uid(), generate_uid(), generate_uid()
    path = tmp_path / "train_series" / study_uid / series_uid / f"{sop_uid}.dcm"
    _write_dicom(
        path,
        study_uid=study_uid,
        series_uid=series_uid,
        sop_uid=sop_uid,
        patient_id="synthetic-patient",
        index=0,
    )

    def fail(*args: object, **kwargs: object) -> None:
        raise MemoryError

    monkeypatch.setattr("rsna_knee.data.manifest.pydicom.dcmread", fail)
    with pytest.raises(MemoryError):
        _inspect_one_file(tmp_path, path, b"k" * 32)


def test_ordered_inspections_recycle_workers_without_loss_or_reordering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths: list[Path] = []
    for index in range(5):
        study_uid, series_uid, sop_uid = generate_uid(), generate_uid(), generate_uid()
        path = tmp_path / "train_series" / study_uid / series_uid / f"{sop_uid}.dcm"
        _write_dicom(
            path,
            study_uid=study_uid,
            series_uid=series_uid,
            sop_uid=sop_uid,
            patient_id="synthetic-patient",
            index=index,
        )
        paths.append(path)

    created_pools = 0

    original_executor = manifest_module.ProcessPoolExecutor

    def counting_executor(*args: Any, **kwargs: Any) -> ProcessPoolExecutor:
        nonlocal created_pools
        created_pools += 1
        return original_executor(*args, **kwargs)

    monkeypatch.setattr(manifest_module, "INSPECTIONS_PER_WORKER_LIFETIME", 1)
    monkeypatch.setattr(manifest_module, "ProcessPoolExecutor", counting_executor)
    inspected = list(
        manifest_module._ordered_file_inspections(
            iter(paths),
            input_root=tmp_path,
            secret=b"k" * 32,
            workers=2,
            deadline=time.monotonic() + 60,
        )
    )
    assert [item.path for item in inspected] == paths
    assert created_pools == 3


def test_runner_audits_every_file_and_keeps_private_rows_private(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    input_root.mkdir()
    train_uid, test_uid = _synthetic_competition(input_root)
    run_config = tmp_path / "run-config.json"
    _run_config(run_config)

    summary = run_manifest_audit(
        input_root=input_root,
        output_root=output_root,
        manifest_schema_path=ROOT / "configs/manifest_schema.yaml",
        competition_config_path=ROOT / "configs/competition.yaml",
        competition_contract_path=ROOT / "docs/competition_contract/contract.yaml",
        run_config_path=run_config,
    )

    assert summary["status"] == "complete"
    aggregates = cast(Mapping[str, object], summary["aggregates"])
    quality = cast(Mapping[str, object], aggregates["quality"])
    integrity = cast(Mapping[str, object], aggregates["integrity"])
    assert quality["unexplained_dicom_issues"] == 0
    assert integrity["dicom_issue_dispositions_complete"] is True
    summary_provenance = cast(Mapping[str, object], summary["provenance"])
    assert summary_provenance["decoder_packages"] == REQUIRED_DECODER_PACKAGES
    assert b"k" * 32 not in json.dumps(summary, sort_keys=True).encode()
    assert set(path.name for path in output_root.iterdir()) == set(RUNNER_OUTPUTS)
    assert not (output_root / "sanitized_summary.json").exists()
    with sqlite3.connect(output_root / "private_manifest.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM slice_file_manifest").fetchone() == (10,)
        assert connection.execute(
            "SELECT COUNT(*) FROM slice_file_manifest WHERE terminal_state='pass'"
        ).fetchone() == (10,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT COUNT(DISTINCT component_key) FROM protected_component"
        ).fetchone() == (1,)
        first_private_state = {
            "table_hashes": connection.execute(
                "SELECT key,value FROM manifest_run WHERE key LIKE 'table_sha256:%' ORDER BY key"
            ).fetchall(),
            "study_keys": connection.execute(
                "SELECT study_key,patient_group_key FROM study_manifest ORDER BY study_key"
            ).fetchall(),
            "environment_versions": connection.execute(
                "SELECT value FROM manifest_run WHERE key='environment_versions'"
            ).fetchone(),
        }
    assert first_private_state["environment_versions"] is not None
    for distribution, version in REQUIRED_DECODER_PACKAGES.items():
        assert f'"{distribution}":"{version}"' in first_private_state["environment_versions"][0]
    persisted = b"".join(path.read_bytes() for path in output_root.iterdir())
    assert train_uid.encode() not in persisted
    assert test_uid.encode() not in persisted
    assert b"Synthetic report 12 mm" not in persisted
    runner_path = ROOT / "kaggle/manifest_audit/run.py"
    specification = importlib.util.spec_from_file_location("_manifest_runner_contract", runner_path)
    assert specification is not None and specification.loader is not None
    runner_contract = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(runner_contract)
    run_payload = json.loads(run_config.read_text())
    runner_contract._validate_exact_aggregates(summary["aggregates"], run_config=run_payload)
    disclosed = runner_contract._apply_disclosure_control(summary, run_payload)
    runner_contract._rewrite_disclosed_outputs(
        output_root,
        run_config=run_payload,
        summary=disclosed,
    )
    runner_contract._validate_working_outputs(
        output_root,
        run_payload,
        disclosed["aggregates"],
    )

    rerun_root = tmp_path / "rerun-output"
    rerun_summary = run_manifest_audit(
        input_root=input_root,
        output_root=rerun_root,
        manifest_schema_path=ROOT / "configs/manifest_schema.yaml",
        competition_config_path=ROOT / "configs/competition.yaml",
        competition_contract_path=ROOT / "docs/competition_contract/contract.yaml",
        run_config_path=run_config,
    )
    with sqlite3.connect(rerun_root / "private_manifest.sqlite3") as connection:
        second_private_state = {
            "table_hashes": connection.execute(
                "SELECT key,value FROM manifest_run WHERE key LIKE 'table_sha256:%' ORDER BY key"
            ).fetchall(),
            "study_keys": connection.execute(
                "SELECT study_key,patient_group_key FROM study_manifest ORDER BY study_key"
            ).fetchall(),
        }
    runner_contract._validate_exact_aggregates(rerun_summary["aggregates"], run_config=run_payload)
    assert {
        key: value for key, value in rerun_summary["aggregates"].items() if key != "runtime"
    } == {key: value for key, value in summary["aggregates"].items() if key != "runtime"}
    assert second_private_state == {
        "table_hashes": first_private_state["table_hashes"],
        "study_keys": first_private_state["study_keys"],
    }
    assert (rerun_root / "private_qa_samples.csv").read_bytes() == (
        output_root / "private_qa_samples.csv"
    ).read_bytes()
    assert (rerun_root / "audit_key.bin").read_bytes() == b"k" * 32


def test_oversized_blocks_keep_a_conservative_chain() -> None:
    members = [f"opaque-{index:03d}" for index in range(130)]
    compared, protected = _bounded_block_pairs({"same-block": members}, maximum_bucket_members=4)
    assert len(compared) == 6
    assert len(protected) == 129
    assert {item for pair in protected for item in pair} == set(members)


def test_conflicts_cross_split_ids_and_orphans_fail_closed(tmp_path: Path) -> None:
    _, labels = load_contract(ROOT / "docs/competition_contract/contract.yaml")
    for split in ("train", "test"):
        (tmp_path / f"{split}_series" / "same-study" / "same-series").mkdir(parents=True)
    (tmp_path / "train_series/orphan-study/orphan-series").mkdir(parents=True)
    (tmp_path / "train_series/orphan-study/orphan-series/bad.bin").write_bytes(b"invalid")
    _write_csv(
        tmp_path / "train.csv",
        ["StudyInstanceUID", "Report", *labels],
        [
            ["same-study", "first report", "1", *([""] * 11)],
            ["same-study", "conflicting report", "0", *([""] * 11)],
        ],
    )
    _write_csv(tmp_path / "test.csv", ["StudyInstanceUID"], [["same-study"]])
    header = [
        "StudyInstanceUID",
        "SeriesInstanceUID",
        "Fluid_Sensitive",
        "Fat_Suppression",
        "Anatomical_Plane",
    ]
    _write_csv(
        tmp_path / "train_series.csv",
        header,
        [["same-study", "same-series", "true", "true", "sagittal"]],
    )
    _write_csv(
        tmp_path / "test_series.csv",
        header,
        [["same-study", "same-series", "true", "true", "sagittal"]],
    )
    inventory = read_source_inventory(tmp_path, labels)
    assert len(_augment_source_inventory(tmp_path, inventory, None)) == 1
    assert len(inventory.studies) == 3
    assert all(
        "cross_split_study_id" in source.conflicts
        for source in inventory.studies.values()
        if source.raw_study_id == "same-study"
    )
    with initialize_private_database(tmp_path / "private.sqlite3", {"schema_version": "2"}) as db:
        insert_source_placeholders(db, inventory, b"x" * 32)
        assert db.execute(
            """SELECT label_state, state_validity FROM label_source_manifest
                WHERE target_index=0 AND label_state='conflict'"""
        ).fetchone() == ("conflict", "invalid")
        assert db.execute(
            "SELECT terminal_state FROM report_manifest WHERE presence_state='conflict'"
        ).fetchone() == ("quarantine",)
