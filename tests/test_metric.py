"""Tests for exact ROC AUC and macro averaging using hand-computed values."""

from __future__ import annotations

import numpy as np
import pytest

from rsna_knee.evaluation.metrics import macro_auc, roc_auc


class TestRocAuc:
    def test_perfect_separation(self) -> None:
        y = np.array([0.0, 0.0, 1.0, 1.0])
        s = np.array([0.1, 0.2, 0.8, 0.9])
        assert roc_auc(y, s) == 1.0

    def test_random_gives_half(self) -> None:
        y = np.array([1.0, 0.0])
        s = np.array([0.5, 0.5])
        assert roc_auc(y, s) == 0.5

    def test_single_class_returns_half(self) -> None:
        assert roc_auc(np.array([1.0, 1.0]), np.array([0.9, 0.8])) == 0.5

    def test_known_value_with_ties(self) -> None:
        # AUC for y=[0,0,1,1], s=[0.1,0.4,0.35,0.8]:
        # pairs: (0.1<0.35)=1, (0.1<0.8)=1, (0.4>0.35)=0, (0.4<0.8)=1 -> 3/4
        y = np.array([0.0, 0.0, 1.0, 1.0])
        s = np.array([0.1, 0.4, 0.35, 0.8])
        assert abs(roc_auc(y, s) - 0.75) < 1e-10

    def test_ties_count_as_half(self) -> None:
        # One tied pair contributes 0.5.
        y = np.array([0.0, 1.0])
        s = np.array([0.5, 0.5])
        assert roc_auc(y, s) == 0.5


class TestMacroAuc:
    def test_macro_is_mean_of_columns(self) -> None:
        y = np.array([[0.0, 1.0], [1.0, 0.0], [0.0, 1.0], [1.0, 0.0]])
        s = np.array([[0.1, 0.9], [0.9, 0.1], [0.2, 0.8], [0.8, 0.2]])
        result = macro_auc(y, s)
        assert result.macro_auc == 1.0
        assert result.per_label_auc == (1.0, 1.0)

    def test_shape_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="shape_mismatch"):
            macro_auc(np.zeros((2, 2)), np.zeros((2, 3)))
