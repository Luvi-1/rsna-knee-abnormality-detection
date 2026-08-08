from __future__ import annotations

import json
from pathlib import Path

from rsna_knee.cli import COMMANDS, run
from rsna_knee.config import ExperimentConfig, config_hash, load_experiment_config
from rsna_knee.registry import SCHEMA_VERSION, initialize_registry, schema_version
from rsna_knee.submission import validate_submission

ROOT = Path(__file__).parents[1]


def test_chunk_one_smoke(tmp_path: Path) -> None:
    config_path = ROOT / "configs" / "experiment.example.toml"
    config = load_experiment_config(config_path)
    assert len(config_hash(config)) == 64

    registry = tmp_path / "experiments.sqlite3"
    initialize_registry(registry)
    assert schema_version(registry) == SCHEMA_VERSION

    summary = validate_submission(ROOT / "synthetic_data" / "sample_submission.csv")
    assert summary.rows == 2

    assert set(COMMANDS) == {
        "audit",
        "preprocess",
        "label",
        "make-folds",
        "train",
        "evaluate",
        "infer",
        "ensemble",
        "validate-submission",
    }
    assert run(["audit", "--config", str(config_path)]) == 0


def test_exported_schema_matches_model() -> None:
    exported = json.loads((ROOT / "configs" / "experiment.schema.json").read_text())
    assert exported == ExperimentConfig.model_json_schema()
