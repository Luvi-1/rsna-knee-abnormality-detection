"""SQLite experiment and artifact provenance registry."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "2"

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('planned', 'running', 'completed', 'failed', 'killed')),
    hypothesis TEXT NOT NULL,
    primary_change TEXT NOT NULL,
    frozen_controls_json TEXT NOT NULL,
    data_manifest_version TEXT NOT NULL,
    label_version TEXT NOT NULL,
    fold_version TEXT NOT NULL,
    preprocessing_version TEXT NOT NULL,
    model_config_json TEXT NOT NULL,
    loss TEXT NOT NULL,
    augmentation_json TEXT NOT NULL,
    seed INTEGER NOT NULL,
    compute_estimate_json TEXT NOT NULL,
    expected_information_gain TEXT NOT NULL,
    promotion_criterion TEXT NOT NULL,
    kill_criterion TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    created_utc TEXT NOT NULL,
    completed_utc TEXT
);
CREATE TABLE IF NOT EXISTS audit_runs (
    audit_id TEXT PRIMARY KEY,
    audit_kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('planned', 'running', 'completed', 'failed', 'blocked')),
    scope_json TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    input_version TEXT NOT NULL,
    manifest_version TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_utc TEXT NOT NULL,
    completed_utc TEXT
);
CREATE TABLE IF NOT EXISTS metrics (
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    split TEXT NOT NULL,
    label TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    ci_low REAL,
    ci_high REAL,
    PRIMARY KEY (experiment_id, split, label, metric)
);
CREATE TABLE IF NOT EXISTS experiment_results (
    experiment_id TEXT PRIMARY KEY REFERENCES experiments(experiment_id),
    actual_runtime_seconds INTEGER NOT NULL CHECK (actual_runtime_seconds >= 0),
    actual_cost_usd REAL NOT NULL CHECK (actual_cost_usd >= 0),
    manual_report_validation_json TEXT NOT NULL,
    manual_mri_validation_json TEXT NOT NULL,
    domain_shift_results_json TEXT NOT NULL,
    failure_modes_json TEXT NOT NULL,
    prediction_correlations_json TEXT NOT NULL,
    hypothesis_supported INTEGER NOT NULL CHECK (hypothesis_supported IN (0, 1)),
    decision TEXT NOT NULL CHECK (decision IN ('keep', 'reject', 'revise', 'ensemble-only'))
);
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    experiment_id TEXT REFERENCES experiments(experiment_id),
    audit_id TEXT REFERENCES audit_runs(audit_id),
    artifact_type TEXT NOT NULL,
    uri TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    data_manifest_version TEXT NOT NULL,
    label_version TEXT NOT NULL,
    fold_version TEXT NOT NULL,
    preprocessing_version TEXT NOT NULL,
    created_utc TEXT NOT NULL
);
"""


def initialize_registry(path: Path) -> None:
    """Create or upgrade the local registry to the current schema."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA_SQL)
        artifact_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(artifacts)").fetchall()
        }
        if "audit_id" not in artifact_columns:
            connection.execute(
                "ALTER TABLE artifacts ADD COLUMN audit_id TEXT REFERENCES audit_runs(audit_id)"
            )
        connection.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
            (SCHEMA_VERSION,),
        )


def schema_version(path: Path) -> str:
    """Read the registry schema version."""

    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        row = connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
    if row is None:
        raise ValueError("registry has no schema version")
    return str(row[0])
