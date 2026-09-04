"""Targetwise probability/logit/rank blending primitives for T137."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import numpy as np

from rsna_knee.targetwise_specialist.rank import as_finite_vector, normalized_average_ranks


class BlendError(ValueError):
    """Raised when blend inputs violate the targetwise contract."""


def validate_weights(weights: Sequence[float], expected_count: int) -> np.ndarray:
    """Return a validated nonnegative weight vector summing to one."""

    if len(weights) != expected_count:
        raise BlendError("weight count must match model count")
    vector = np.asarray(weights, dtype=np.float64)
    if not np.isfinite(vector).all() or np.any(vector < 0.0):
        raise BlendError("weights must be finite and nonnegative")
    if not math.isclose(float(vector.sum()), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise BlendError("weights must sum to one")
    return vector


def probability_blend(
    predictions: Sequence[Iterable[float]], weights: Sequence[float]
) -> np.ndarray:
    """Blend calibrated probabilities directly."""

    matrix = _prediction_matrix(predictions)
    weight_vector = validate_weights(weights, matrix.shape[0])
    if np.any((matrix < 0.0) | (matrix > 1.0)):
        raise BlendError("probability inputs must lie within [0, 1]")
    return weight_vector @ matrix


def logit_blend(
    predictions: Sequence[Iterable[float]],
    weights: Sequence[float],
    *,
    epsilon: float = 1e-6,
) -> np.ndarray:
    """Blend probabilities in logit space and return probabilities."""

    if not 0.0 < epsilon < 0.5:
        raise BlendError("epsilon must be in (0, 0.5)")
    matrix = _prediction_matrix(predictions)
    weight_vector = validate_weights(weights, matrix.shape[0])
    if np.any((matrix < 0.0) | (matrix > 1.0)):
        raise BlendError("probability inputs must lie within [0, 1]")
    clipped = np.clip(matrix, epsilon, 1.0 - epsilon)
    logits = np.log(clipped / (1.0 - clipped))
    blended = weight_vector @ logits
    return 1.0 / (1.0 + np.exp(-blended))


def rank_blend(
    predictions: Sequence[Iterable[float]], weights: Sequence[float]
) -> np.ndarray:
    """Blend independently normalized ranks for an AUC-oriented candidate."""

    matrix = _prediction_matrix(predictions)
    weight_vector = validate_weights(weights, matrix.shape[0])
    rank_matrix = np.vstack([normalized_average_ranks(row) for row in matrix])
    return weight_vector @ rank_matrix


def target_swap(
    champion: np.ndarray,
    challenger: np.ndarray,
    *,
    target_indices: Sequence[int],
) -> np.ndarray:
    """Replace selected target columns in a complete prediction matrix."""

    base, other = _paired_prediction_matrices(champion, challenger)
    selected = tuple(target_indices)
    if len(set(selected)) != len(selected):
        raise BlendError("target_indices must be unique")
    if any(index < 0 or index >= base.shape[1] for index in selected):
        raise BlendError("target index outside matrix bounds")
    result = base.copy()
    if selected:
        result[:, selected] = other[:, selected]
    return result


def targetwise_rank_blend(
    champion: np.ndarray,
    challenger: np.ndarray,
    *,
    target_indices: Sequence[int],
    champion_weight: float,
) -> np.ndarray:
    """Rank-blend selected targets while preserving champion columns elsewhere."""

    base, other = _paired_prediction_matrices(champion, challenger)
    if not 0.0 <= champion_weight <= 1.0:
        raise BlendError("champion_weight must be within [0, 1]")
    selected = tuple(target_indices)
    if len(set(selected)) != len(selected):
        raise BlendError("target_indices must be unique")
    if any(index < 0 or index >= base.shape[1] for index in selected):
        raise BlendError("target index outside matrix bounds")
    result = base.copy()
    for index in selected:
        result[:, index] = rank_blend(
            (base[:, index], other[:, index]),
            (champion_weight, 1.0 - champion_weight),
        )
    return result


def validate_submission_matrix(values: np.ndarray, *, expected_targets: int = 12) -> None:
    """Fail closed on malformed prediction matrices before packaging."""

    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2:
        raise BlendError("submission matrix must be two-dimensional")
    if matrix.shape[0] == 0:
        raise BlendError("submission matrix cannot be empty")
    if matrix.shape[1] != expected_targets:
        raise BlendError(f"submission matrix must contain {expected_targets} targets")
    if not np.isfinite(matrix).all():
        raise BlendError("submission matrix contains nonfinite predictions")
    if np.any((matrix < 0.0) | (matrix > 1.0)):
        raise BlendError("submission predictions must lie within [0, 1]")


def _prediction_matrix(predictions: Sequence[Iterable[float]]) -> np.ndarray:
    if not predictions:
        raise BlendError("at least one prediction vector is required")
    rows = [as_finite_vector(item) for item in predictions]
    width = rows[0].size
    if any(row.size != width for row in rows):
        raise BlendError("all prediction vectors must have equal length")
    return np.vstack(rows)


def _paired_prediction_matrices(
    champion: np.ndarray, challenger: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    base = np.asarray(champion, dtype=np.float64)
    other = np.asarray(challenger, dtype=np.float64)
    if base.ndim != 2 or other.ndim != 2:
        raise BlendError("prediction matrices must be two-dimensional")
    if base.shape != other.shape:
        raise BlendError("champion and challenger matrices must have equal shape")
    if not np.isfinite(base).all() or not np.isfinite(other).all():
        raise BlendError("prediction matrices must be finite")
    return base, other
