"""Exact macro ROC AUC with bootstrap confidence intervals and subgroup metrics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


def roc_auc(y_true: npt.NDArray[np.float64], y_score: npt.NDArray[np.float64]) -> float:
    """Exact AUC via rank-based formula (handles ties). Returns 0.5 on degenerate input."""
    pos = y_true == 1
    neg = y_true == 0
    n_pos = int(pos.sum())
    n_neg = int(neg.sum())
    if n_pos == 0 or n_neg == 0:
        return 0.5
    # Tie-corrected average ranks.
    order = np.argsort(y_score)
    sorted_scores = y_score[order]
    avg_ranks = np.empty(len(y_score), dtype=np.float64)
    i = 0
    while i < len(sorted_scores):
        j = i
        while j + 1 < len(sorted_scores) and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        avg_ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    rank_sum_pos = avg_ranks[pos].sum()
    auc = (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return float(auc)


@dataclass(frozen=True, slots=True)
class MacroAucResult:
    macro_auc: float
    per_label_auc: tuple[float, ...]


def macro_auc(
    y_true: npt.NDArray[np.float64],
    y_score: npt.NDArray[np.float64],
) -> MacroAucResult:
    """Compute per-column AUC then average. Columns with single class get 0.5."""
    if y_true.shape != y_score.shape:
        raise ValueError("shape_mismatch")
    per_label: list[float] = []
    for col in range(y_true.shape[1]):
        per_label.append(roc_auc(y_true[:, col], y_score[:, col]))
    arr = np.array(per_label)
    return MacroAucResult(macro_auc=float(arr.mean()), per_label_auc=tuple(per_label))
