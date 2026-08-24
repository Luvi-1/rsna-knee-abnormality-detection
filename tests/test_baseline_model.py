"""Tests for the synthetic baseline model."""

from __future__ import annotations

import numpy as np
import pytest

from rsna_knee.models.baseline_2_5d import Baseline2_5D


class TestBaseline2_5D:
    def test_output_shape_matches_targets(self) -> None:
        model = Baseline2_5D(n_targets=12)
        x = np.random.default_rng(0).normal(0.5, 0.1, size=(4, 32, 32))
        out = model.forward(x)
        assert out.shape == (4, 12)

    def test_output_is_probability(self) -> None:
        model = Baseline2_5D(n_targets=3)
        x = np.random.default_rng(1).normal(0.5, 0.1, size=(8, 64, 64))
        out = model.forward(x)
        assert np.all(out >= 0.0) and np.all(out <= 1.0)

    def test_deterministic_seed(self) -> None:
        m1 = Baseline2_5D(seed=42)
        m2 = Baseline2_5D(seed=42)
        assert np.array_equal(m1.weights, m2.weights)

    def test_zero_targets_raises(self) -> None:
        with pytest.raises(ValueError, match="n_targets"):
            Baseline2_5D(n_targets=0)
