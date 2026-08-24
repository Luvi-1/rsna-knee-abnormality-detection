"""Tests for the synthetic smoke training loop."""

from __future__ import annotations

import numpy as np

from rsna_knee.training.smoke_loop import run_synthetic_smoke


class TestSmokeLoop:
    def test_produces_correct_shapes(self) -> None:
        result = run_synthetic_smoke(n_studies=16, n_targets=12)
        assert result.oof_predictions.shape == (16, 12)
        assert len(result.study_keys) == 16

    def test_loss_is_finite_positive(self) -> None:
        result = run_synthetic_smoke()
        assert np.isfinite(result.train_loss) and result.train_loss > 0

    def test_deterministic_outputs(self) -> None:
        r1 = run_synthetic_smoke(n_studies=8, seed=7)
        r2 = run_synthetic_smoke(n_studies=8, seed=7)
        assert np.array_equal(r1.oof_predictions, r2.oof_predictions)
