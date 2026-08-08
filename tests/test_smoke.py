from __future__ import annotations

import json
from pathlib import Path

import pytest

from rsna_knee.cli import COMMANDS, run
from rsna_knee.competition_contract import (
    contract_error_summary,
    load_competition_contract,
    load_contract,
    material_drift,
)
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

    contract_config = ROOT / "configs" / "competition.yaml"
    contract = load_competition_contract(contract_config)
    assert contract.identity.slug == "rsna-knee-abnormality-detection"

    summary = validate_submission(ROOT / "synthetic_data" / "submission.csv", contract_config)
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


def test_material_contract_drift_is_detected(tmp_path: Path) -> None:
    canonical_path = ROOT / "docs" / "competition_contract" / "contract.yaml"
    observed = json.loads(canonical_path.read_text())
    observed["targets"]["labels"][0] = "Changed target"
    observed["submission"]["columns"][1] = "Changed target"
    observed["timeline"]["final_submission_deadline"] = "2099-01-01T00:00:00Z"
    observed["runtime"]["cpu_limit_seconds"] = 1
    observed["limits"]["daily_submissions"] = 1
    observed["data"]["description_fingerprint"] = "changed"
    observed["data"]["inventory"]["total_files"] += 1
    observed_path = tmp_path / "observed.yaml"
    observed_path.write_text(json.dumps(observed))

    changed = material_drift(load_contract(canonical_path), load_contract(observed_path))
    assert changed == ("targets", "submission", "timeline", "runtime", "limits", "data")

    invalid_path = tmp_path / "invalid.yaml"
    invalid_path.write_text('{"schema_version":"private-marker"}')
    with pytest.raises(ValueError) as captured:
        load_contract(invalid_path)
    assert "private-marker" not in contract_error_summary(captured.value)


def test_submission_filename_is_enforced(tmp_path: Path) -> None:
    wrong_name = tmp_path / "wrong.csv"
    wrong_name.write_text((ROOT / "synthetic_data" / "submission.csv").read_text())
    with pytest.raises(ValueError, match="filename must be submission.csv"):
        validate_submission(wrong_name, ROOT / "configs" / "competition.yaml")
