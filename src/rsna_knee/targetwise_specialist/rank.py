"""Deterministic rank and diversity helpers for targetwise AUC ensembles."""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np


class RankError(ValueError):
    """Raised when a rank input is malformed."""


def as_finite_vector(values: Iterable[float]) -> np.ndarray:
    """Convert values to a finite 1D float64 array."""

    vector = np.asarray(tuple(values), dtype=np.float64)
    if vector.ndim != 1:
        raise RankError("prediction vector must be one-dimensional")
    if vector.size == 0:
        raise RankError("prediction vector cannot be empty")
    if not np.isfinite(vector).all():
        raise RankError("prediction vector contains a nonfinite value")
    return vector


def normalized_average_ranks(values: Iterable[float]) -> np.ndarray:
    """Return average-tie ranks normalized to [0, 1].

    A stable mergesort provides deterministic ordering. Equal values receive the
    average of their 0-based rank positions. For a one-item vector the rank is 0.
    """

    vector = as_finite_vector(values)
    n = vector.size
    if n == 1:
        return np.zeros(1, dtype=np.float64)

    order = np.argsort(vector, kind="mergesort")
    sorted_values = vector[order]
    sorted_ranks = np.empty(n, dtype=np.float64)

    start = 0
    while start < n:
        end = start + 1
        while end < n and sorted_values[end] == sorted_values[start]:
            end += 1
        average_position = (start + end - 1) / 2.0
        sorted_ranks[start:end] = average_position
        start = end

    ranks = np.empty(n, dtype=np.float64)
    ranks[order] = sorted_ranks
    return ranks / float(n - 1)


def pearson_correlation(left: Iterable[float], right: Iterable[float]) -> float:
    """Return Pearson correlation, failing on constant vectors."""

    a, b = _paired_vectors(left, right)
    a_centered = a - a.mean()
    b_centered = b - b.mean()
    denominator = float(np.linalg.norm(a_centered) * np.linalg.norm(b_centered))
    if denominator == 0.0:
        raise RankError("correlation is undefined for a constant vector")
    return float(np.dot(a_centered, b_centered) / denominator)


def spearman_correlation(left: Iterable[float], right: Iterable[float]) -> float:
    """Return Pearson correlation of deterministic average ranks."""

    a, b = _paired_vectors(left, right)
    return pearson_correlation(normalized_average_ranks(a), normalized_average_ranks(b))


def rank_disagreement(left: Iterable[float], right: Iterable[float]) -> float:
    """Return mean absolute normalized-rank difference in [0, 1]."""

    a, b = _paired_vectors(left, right)
    ra = normalized_average_ranks(a)
    rb = normalized_average_ranks(b)
    return float(np.mean(np.abs(ra - rb)))


def identical_ordering(left: Iterable[float], right: Iterable[float]) -> bool:
    """Return whether two vectors induce exactly the same normalized ranks."""

    a, b = _paired_vectors(left, right)
    return bool(
        np.array_equal(normalized_average_ranks(a), normalized_average_ranks(b))
    )


def top_fraction_overlap(
    left: Iterable[float], right: Iterable[float], *, fraction: float = 0.10
) -> float:
    """Return overlap fraction of the highest-ranked items.

    The selection size is ``max(1, ceil(n * fraction))`` and stable order is
    used to break ties deterministically.
    """

    if not 0.0 < fraction <= 1.0:
        raise RankError("fraction must be in (0, 1]")
    a, b = _paired_vectors(left, right)
    count = max(1, math.ceil(a.size * fraction))
    left_top = set(np.argsort(a, kind="mergesort")[-count:].tolist())
    right_top = set(np.argsort(b, kind="mergesort")[-count:].tolist())
    return len(left_top & right_top) / float(count)


def _paired_vectors(
    left: Iterable[float], right: Iterable[float]
) -> tuple[np.ndarray, np.ndarray]:
    a = as_finite_vector(left)
    b = as_finite_vector(right)
    if a.shape != b.shape:
        raise RankError("prediction vectors must have equal shape")
    return a, b
