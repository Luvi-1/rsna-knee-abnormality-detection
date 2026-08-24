"""Deterministic active-learning queue for annotation prioritization."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QueueItem:
    study_key: str
    target_column: str
    uncertainty_score: float  # 0.0 = confident; 1.0 = maximally uncertain


def build_queue(
    items: list[QueueItem],
    *,
    batch_size: int,
) -> list[QueueItem]:
    """Rank by descending uncertainty, then ascending study_key for determinism."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    ranked = sorted(items, key=lambda item: (-item.uncertainty_score, item.study_key))
    return ranked[:batch_size]
