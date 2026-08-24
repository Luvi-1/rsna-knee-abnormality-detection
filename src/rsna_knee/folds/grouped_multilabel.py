"""Leakage-resistant grouped multi-label fold construction.

Groups are opaque study keys. Every slice of the same study stays in exactly one
fold, preventing patient-level leakage across train and validation splits.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class FoldAssignment:
    study_key: str
    fold_index: int


def build_grouped_folds(
    study_keys: list[str],
    labels: npt.NDArray[np.float64],
    *,
    n_splits: int = 5,
) -> list[FoldAssignment]:
    """Assign studies to folds, balancing label prevalence within group constraints.

    Uses a greedy one-pass assignment: for each study (ordered by descending
    positive count), place it in the fold with the lowest current positive mass.
    Ties break by fold index for determinism. This is a heuristic; exact optimal
    multilabel stratification is NP-hard.
    """
    if n_splits < 2:
        raise ValueError("n_splits must be >= 2")
    if len(study_keys) != len(labels):
        raise ValueError("study_keys and labels must have equal length")
    if len(study_keys) < n_splits:
        raise ValueError("not enough studies for requested folds")
    if len(set(study_keys)) != len(study_keys):
        raise ValueError("duplicate_study_key")

    # Sort by descending positive label count to place heavy groups first.
    order = sorted(
        range(len(study_keys)),
        key=lambda i: (-int(labels[i].sum()), study_keys[i]),
    )
    fold_pos_mass = np.zeros(n_splits, dtype=np.int64)
    assignments: dict[str, int] = {}
    for idx in order:
        target_fold = int(np.argmin(fold_pos_mass))
        assignments[study_keys[idx]] = target_fold
        fold_pos_mass[target_fold] += int(labels[idx].sum())

    # Warn if any label has fewer positive examples than n_splits (degenerate AUC risk).
    for col in range(labels.shape[1]):
        n_pos = int((labels[:, col] == 1).sum())
        if 0 < n_pos < n_splits:
            warnings.warn(
                f"label column {col} has only {n_pos} positives across {n_splits} folds; "
                "validation AUC for this target may be degenerate",
                stacklevel=2,
            )
    return [FoldAssignment(study_key=k, fold_index=assignments[k]) for k in study_keys]
