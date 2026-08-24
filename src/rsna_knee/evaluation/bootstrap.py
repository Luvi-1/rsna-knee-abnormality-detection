"""Bootstrap confidence intervals for macro AUC using deterministic resampling."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from rsna_knee.evaluation.metrics import MacroAucResult, macro_auc


def bootstrap_macro_auc(
    y_true: npt.NDArray[np.float64],
    y_score: npt.NDArray[np.float64],
    *,
    n_bootstraps: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """Percentile bootstrap CI for macro AUC with a fixed seed for reproducibility."""
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be in (0, 1)")
    if n_bootstraps < 2:
        raise ValueError("n_bootstraps must be >= 2")
    rng = np.random.default_rng(seed)
    n = y_true.shape[0]
    bootstraps: list[float] = []
    for _ in range(n_bootstraps):
        idx = rng.integers(0, n, size=n)
        result: MacroAucResult = macro_auc(y_true[idx], y_score[idx])
        bootstraps.append(result.macro_auc)
    alpha = (1.0 - confidence_level) / 2.0
    lo, hi = np.percentile(bootstraps, [100 * alpha, 100 * (1 - alpha)])
    return float(lo), float(hi)
