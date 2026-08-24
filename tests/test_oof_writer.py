"""Tests for the OOF prediction writer using in-memory data only."""

from __future__ import annotations

import numpy as np

from rsna_knee.training.smoke_loop import run_synthetic_smoke


class TestOofWriter:
    def test_keys_match_prediction_rows(self) -> None:
        keys = ("aa" * 32, "bb" * 32)
        result = run_synthetic_smoke(n_studies=len(keys))
        assert result.study_keys == tuple(f"{i:064x}" for i in range(len(keys)))

    def test_predictions_in_unit_interval(self) -> None:
        result = run_synthetic_smoke()
        assert np.all(result.oof_predictions >= 0.0)
        assert np.all(result.oof_predictions <= 1.0)
