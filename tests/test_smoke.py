from __future__ import annotations

import json
import runpy
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

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
violations = cast(
    Callable[[list[Path]], list[str]],
    runpy.run_path(str(ROOT / "scripts" / "check_no_sensitive_files.py"))["violations"],
)
contract_check_main = cast(
    Callable[[], int],
    runpy.run_path(str(ROOT / "scripts" / "check_competition_contract.py"))["main"],
)


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
    additional_sections = (
        "efficiency_prize",
        "external_assets",
        "team_and_sharing",
        "license",
        "winner_obligations",
        "ambiguities",
    )
    observed = json.loads(canonical_path.read_text())
    observed["targets"]["labels"][0] = "Changed target"
    observed["submission"]["columns"][1] = "Changed target"
    observed["timeline"]["final_submission_deadline"] = "2099-01-01T00:00:00Z"
    observed["runtime"]["cpu_limit_seconds"] = 1
    observed["limits"]["daily_submissions"] = 1
    observed["data"]["description_fingerprint"] = "changed"
    observed["data"]["inventory"]["total_files"] += 1
    for section in additional_sections:
        observed[section] = {"changed": True}
    observed_path = tmp_path / "observed.yaml"
    observed_path.write_text(json.dumps(observed))

    changed = material_drift(load_contract(canonical_path), load_contract(observed_path))
    assert changed == (
        "targets",
        "submission",
        "timeline",
        "runtime",
        "limits",
        "data",
        *additional_sections,
    )

    removed = json.loads(canonical_path.read_text())
    for section in additional_sections:
        removed.pop(section)
    removed_path = tmp_path / "removed.yaml"
    removed_path.write_text(json.dumps(removed))
    assert material_drift(load_contract(canonical_path), load_contract(removed_path)) == (
        additional_sections
    )

    invalid_path = tmp_path / "invalid.yaml"
    invalid_path.write_text('{"schema_version":"private-marker"}')
    with pytest.raises(ValueError) as captured:
        load_contract(invalid_path)
    assert "private-marker" not in contract_error_summary(captured.value)


def test_contract_check_rejects_non_independent_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canonical_path = ROOT / "docs" / "competition_contract" / "contract.yaml"
    observed_path = tmp_path / "observed.yaml"
    observed_path.symlink_to(canonical_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_competition_contract.py",
            str(observed_path),
            "--canonical",
            str(canonical_path),
        ],
    )

    assert contract_check_main() == 2
    assert capsys.readouterr().out == ("contract_valid=no reason=observed_not_independent\n")


def test_submission_filename_is_enforced(tmp_path: Path) -> None:
    wrong_name = tmp_path / "wrong.csv"
    wrong_name.write_text((ROOT / "synthetic_data" / "submission.csv").read_text())
    with pytest.raises(ValueError, match="filename must be submission.csv"):
        validate_submission(wrong_name, ROOT / "configs" / "competition.yaml")


def test_sensitive_guard_blocks_qa_media_and_preprocessing_caches() -> None:
    paths = [
        Path("qa/contact.png"),
        Path("qa/order.gif"),
        Path("cache/tensor.npy"),
        Path("cache/series.zarr/0"),
        Path("elsewhere/private_full_run_manifest.jsonl"),
        Path("elsewhere/COMPLETED_REVIEW_LEDGER.JSON"),
        Path("elsewhere/audit_key.bin"),
        Path("elsewhere/case_000001_series_002_metadata.json"),
    ]

    assert all(violations([path]) for path in paths)
