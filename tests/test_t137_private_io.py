from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from rsna_knee.targetwise_specialist import (
    TARGETS,
    BlendError,
    PredictionTableError,
    load_prediction_csv,
    reconcile_identifier_order,
    write_prediction_csv,
)


def _write(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerows(rows)


def _valid_rows() -> list[list[str]]:
    header = ["StudyInstanceUID", *TARGETS]
    first = ["study-a", *[str(0.05 + index * 0.01) for index in range(12)]]
    second = ["study-b", *[str(0.15 + index * 0.01) for index in range(12)]]
    return [header, first, second]


def test_load_prediction_csv_exact_contract(tmp_path: Path) -> None:
    path = tmp_path / "predictions.csv"
    _write(path, _valid_rows())
    identifiers, matrix = load_prediction_csv(path)
    assert identifiers == ("study-a", "study-b")
    assert matrix.shape == (2, 12)
    assert np.isfinite(matrix).all()


def test_load_prediction_csv_rejects_wrong_target_order(tmp_path: Path) -> None:
    rows = _valid_rows()
    rows[0][1], rows[0][2] = rows[0][2], rows[0][1]
    path = tmp_path / "bad.csv"
    _write(path, rows)
    with pytest.raises(PredictionTableError, match="exact target order"):
        load_prediction_csv(path)


def test_load_prediction_csv_rejects_duplicate_identifiers(tmp_path: Path) -> None:
    rows = _valid_rows()
    rows[2][0] = rows[1][0]
    path = tmp_path / "bad.csv"
    _write(path, rows)
    with pytest.raises(PredictionTableError, match="duplicate identifiers"):
        load_prediction_csv(path)


def test_load_prediction_csv_rejects_non_numeric_prediction(tmp_path: Path) -> None:
    rows = _valid_rows()
    rows[1][1] = "not-a-number"
    path = tmp_path / "bad.csv"
    _write(path, rows)
    with pytest.raises(PredictionTableError, match="nonnumeric"):
        load_prediction_csv(path)


def test_load_prediction_csv_rejects_probability_outside_bounds(tmp_path: Path) -> None:
    rows = _valid_rows()
    rows[1][1] = "1.2"
    path = tmp_path / "bad.csv"
    _write(path, rows)
    with pytest.raises(BlendError, match="\[0, 1\]"):
        load_prediction_csv(path)


def test_reconcile_identifier_order() -> None:
    order = reconcile_identifier_order(("a", "b", "c"), ("c", "a", "b"))
    np.testing.assert_array_equal(order, [1, 2, 0])


def test_reconcile_identifier_order_rejects_different_sets() -> None:
    with pytest.raises(PredictionTableError, match="different identifier sets"):
        reconcile_identifier_order(("a", "b"), ("a", "c"))


def test_write_prediction_csv_round_trip(tmp_path: Path) -> None:
    output = tmp_path / "candidate.csv"
    identifiers = ("a", "b")
    matrix = np.vstack([np.linspace(0.01, 0.12, 12), np.linspace(0.21, 0.32, 12)])
    write_prediction_csv(output, identifiers, matrix)
    loaded_ids, loaded = load_prediction_csv(output)
    assert loaded_ids == identifiers
    np.testing.assert_allclose(loaded, matrix, atol=1e-12, rtol=0.0)


def test_write_prediction_csv_rejects_identifier_count_mismatch(tmp_path: Path) -> None:
    with pytest.raises(PredictionTableError, match="identifier count"):
        write_prediction_csv(tmp_path / "bad.csv", ("a",), np.zeros((2, 12)))


def test_write_prediction_csv_rejects_duplicate_identifiers(tmp_path: Path) -> None:
    with pytest.raises(PredictionTableError, match="unique"):
        write_prediction_csv(tmp_path / "bad.csv", ("a", "a"), np.zeros((2, 12)))
