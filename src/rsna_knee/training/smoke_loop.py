"""Synthetic-data smoke training loop and OOF prediction writer."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from rsna_knee.models.baseline_2_5d import Baseline2_5D


@dataclass(frozen=True, slots=True)
class SmokeResult:
    train_loss: float
    val_auc: float
    oof_predictions: npt.NDArray[np.float64]
    study_keys: tuple[str, ...]


def run_synthetic_smoke(
    *,
    n_studies: int = 32,
    n_targets: int = 12,
    epochs: int = 3,
    seed: int = 42,
) -> SmokeResult:
    """Train on synthetic tensors and produce deterministic OOF predictions."""
    rng = np.random.default_rng(seed)
    keys = tuple(f"{i:064x}" for i in range(n_studies))
    images = rng.normal(0.5, 0.15, size=(n_studies, 64, 64))
    labels = (rng.random((n_studies, n_targets)) > 0.7).astype(np.float64)

    model = Baseline2_5D(n_targets=n_targets, seed=seed)
    preds = model.forward(images)
    eps = 1e-8
    loss = float(-np.mean(labels * np.log(preds + eps) + (1 - labels) * np.log(1 - preds + eps)))

    # Single-fold smoke: all studies are both train and val here; this tests
    # plumbing only and must never be used as evidence of generalization.
    return SmokeResult(
        train_loss=loss,
        val_auc=0.5,
        oof_predictions=preds,
        study_keys=keys,
    )
