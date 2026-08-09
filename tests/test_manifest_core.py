from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from rsna_knee.data.manifest import (
    LABEL_VERSION,
    ManifestAuditError,
    enumerate_dicom_files,
    initialize_private_database,
    insert_source_placeholders,
    load_contract,
    normalize_report,
    official_label_state,
    privacy_scan_text,
    read_source_inventory,
    report_features,
    validate_schema,
)

ROOT = Path(__file__).parents[1]


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _synthetic_source(root: Path, labels: tuple[str, ...]) -> None:
    for split in ("train", "test"):
        (root / f"{split}_series" / f"{split}-study" / f"{split}-series").mkdir(parents=True)
    train_labels = ["1", "0", *("" for _ in range(10))]
    _write_csv(
        root / "train.csv",
        ["StudyInstanceUID", "Report", *labels],
        [["train-study", "Synthetic normal report phrase", *train_labels]],
    )
    _write_csv(root / "test.csv", ["StudyInstanceUID"], [["test-study"]])
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
        [["train-study", "train-series", "true", "true", "sagittal"]],
    )
    _write_csv(
        root / "test_series.csv",
        series_header,
        [["test-study", "test-series", "false", "false", "axial"]],
    )


def test_five_level_source_ingest_never_persists_raw_text_or_ids(tmp_path: Path) -> None:
    _, labels = load_contract(ROOT / "docs" / "competition_contract" / "contract.yaml")
    _synthetic_source(tmp_path, labels)
    inventory = read_source_inventory(tmp_path, labels)
    assert (len(inventory.studies), len(inventory.series)) == (2, 2)

    database = tmp_path / "private.sqlite3"
    connection = initialize_private_database(database, {"schema_version": "1"})
    try:
        study_keys, series_keys, _ = insert_source_placeholders(connection, inventory, b"x" * 32)
        assert len(study_keys) == 2
        assert len(series_keys) == 2
        assert connection.execute("SELECT COUNT(*) FROM study_manifest").fetchone() == (2,)
        assert connection.execute("SELECT COUNT(*) FROM series_manifest").fetchone() == (2,)
        assert connection.execute("SELECT COUNT(*) FROM report_manifest").fetchone() == (2,)
        assert connection.execute("SELECT COUNT(*) FROM label_source_manifest").fetchone() == (12,)
        states = dict(
            connection.execute(
                "SELECT label_state, COUNT(*) FROM label_source_manifest GROUP BY label_state"
            )
        )
        assert states == {"negative": 1, "positive": 1, "unknown": 10}
        versions = {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT source_version FROM label_source_manifest"
            )
        }
        assert versions == {LABEL_VERSION}
    finally:
        connection.close()
    persisted = database.read_bytes()
    assert b"Synthetic normal report phrase" not in persisted
    assert b"train-study" not in persisted
    assert b"train-series" not in persisted


def test_report_features_are_deterministic_and_private() -> None:
    secret = b"a" * 32
    first = report_features("Knee REPORT 12 mm\nnormal", secret)
    second = report_features("Knee REPORT 12 mm\nnormal", secret)
    assert first == second
    assert first.presence_state == "present"
    assert first.raw_text_exact_key is not None
    assert first.canonical_text_exact_key is not None
    assert normalize_report("A 12 mm finding") == "a <measurement:mm> finding"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, "unknown"), ("", "unknown"), ("0", "negative"), ("1.0", "positive"), ("?", "conflict")],
)
def test_official_label_state_never_coerces_unknown(value: str | None, expected: str) -> None:
    assert official_label_state(value) == expected


def test_schema_and_privacy_guard(tmp_path: Path) -> None:
    schema = validate_schema(ROOT / "configs" / "manifest_schema.yaml")
    assert len(schema["tables"]) == 14
    privacy_scan_text('{"event":"safe","count":20}')
    with pytest.raises(ManifestAuditError, match="privacy_scan_failed"):
        privacy_scan_text("StudyInstanceUID")
    with pytest.raises(ManifestAuditError, match="privacy_scan_failed"):
        privacy_scan_text("1.2.840.113619")
    with pytest.raises(ManifestAuditError, match="privacy_scan_failed"):
        privacy_scan_text("/kaggle/input/private")


def test_enumeration_is_deterministic_and_accounts_for_non_dicom_files(tmp_path: Path) -> None:
    for split in ("train", "test"):
        root = tmp_path / f"{split}_series" / "study" / "series"
        root.mkdir(parents=True)
        (root / "b.dcm").write_bytes(b"b")
        (root / "a.bin").write_bytes(b"a")
    relative = [path.relative_to(tmp_path).as_posix() for path in enumerate_dicom_files(tmp_path)]
    assert relative == [
        "test_series/study/series/a.bin",
        "test_series/study/series/b.dcm",
        "train_series/study/series/a.bin",
        "train_series/study/series/b.dcm",
    ]


def test_registry_v1_migrates_to_audit_aware_v2(tmp_path: Path) -> None:
    from rsna_knee.registry import SCHEMA_VERSION, initialize_registry, schema_version

    path = tmp_path / "registry.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO schema_meta VALUES('schema_version', '1')")
        connection.execute(
            """CREATE TABLE artifacts(
                artifact_id TEXT PRIMARY KEY, experiment_id TEXT, artifact_type TEXT NOT NULL,
                uri TEXT NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
                code_version TEXT NOT NULL, config_hash TEXT NOT NULL,
                data_manifest_version TEXT NOT NULL, label_version TEXT NOT NULL,
                fold_version TEXT NOT NULL, preprocessing_version TEXT NOT NULL,
                created_utc TEXT NOT NULL
            )"""
        )
    initialize_registry(path)
    assert schema_version(path) == SCHEMA_VERSION == "2"
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(artifacts)")}
        assert "audit_id" in columns
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_runs'"
        ).fetchone() == ("audit_runs",)
