"""Private prediction-table I/O with exact schema and identifier reconciliation."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence

import numpy as np

from rsna_knee.targetwise_specialist.blend import validate_submission_matrix
from rsna_knee.targetwise_specialist.contracts import TARGETS


class PredictionTableError(ValueError):
    """Raised when a private prediction table violates the competition schema."""


def load_prediction_csv(path: str | Path) -> tuple[tuple[str, ...], np.ndarray]:
    """Load a 13-column prediction CSV without exposing identifier values."""

    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise PredictionTableError("prediction CSV is empty") from exc
        expected = ["StudyInstanceUID", *TARGETS]
        if header != expected:
            raise PredictionTableError("prediction CSV header does not match exact target order")

        identifiers: list[str] = []
        rows: list[list[float]] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(expected):
                raise PredictionTableError(
                    f"row {row_number} has {len(row)} columns; expected {len(expected)}"
                )
            identifier = row[0].strip()
            if not identifier:
                raise PredictionTableError(f"row {row_number} has an empty identifier")
            identifiers.append(identifier)
            try:
                rows.append([float(value) for value in row[1:]])
            except ValueError as exc:
                raise PredictionTableError(
                    f"row {row_number} contains a nonnumeric prediction"
                ) from exc

    if not identifiers:
        raise PredictionTableError("prediction CSV contains no rows")
    if len(set(identifiers)) != len(identifiers):
        raise PredictionTableError("prediction CSV contains duplicate identifiers")
    matrix = np.asarray(rows, dtype=np.float64)
    validate_submission_matrix(matrix)
    return tuple(identifiers), matrix


def reconcile_identifier_order(
    reference_ids: Sequence[str], candidate_ids: Sequence[str]
) -> np.ndarray:
    """Return row indices that put candidate IDs in exact reference order."""

    if len(reference_ids) != len(candidate_ids):
        raise PredictionTableError("prediction tables contain different row counts")
    if len(set(reference_ids)) != len(reference_ids):
        raise PredictionTableError("reference identifiers are not unique")
    if len(set(candidate_ids)) != len(candidate_ids):
        raise PredictionTableError("candidate identifiers are not unique")

    positions = {identifier: index for index, identifier in enumerate(candidate_ids)}
    if set(reference_ids) != set(candidate_ids):
        raise PredictionTableError("prediction tables contain different identifier sets")
    return np.asarray([positions[identifier] for identifier in reference_ids], dtype=np.int64)


def write_prediction_csv(
    path: str | Path,
    identifiers: Sequence[str],
    predictions: np.ndarray,
) -> None:
    """Write an exact 13-column candidate CSV after validation."""

    matrix = np.asarray(predictions, dtype=np.float64)
    validate_submission_matrix(matrix)
    if matrix.shape[0] != len(identifiers):
        raise PredictionTableError("identifier count does not match prediction rows")
    if len(set(identifiers)) != len(identifiers):
        raise PredictionTableError("identifiers must be unique")

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["StudyInstanceUID", *TARGETS])
        for identifier, values in zip(identifiers, matrix, strict=True):
            writer.writerow([identifier, *[f"{value:.12g}" for value in values]])
