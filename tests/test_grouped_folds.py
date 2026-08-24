"""Tests for grouped multi-label fold construction using synthetic data."""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from rsna_knee.folds.grouped_multilabel import build_grouped_folds


class TestGroupedFolds:
    def test_each_study_in_one_fold(self) -> None:
        keys = ["aa" * 32, "bb" * 32, "cc" * 32]
        labels = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        result = build_grouped_folds(keys, labels, n_splits=2)
        assert len(result) == 3
        assert all(0 <= a.fold_index < 2 for a in result)

    def test_no_duplicate_study_keys(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            build_grouped_folds(["aa" * 32] * 2, np.ones((2, 1)), n_splits=2)

    def test_deterministic_repeat(self) -> None:
        keys = ["aa" * 32, "bb" * 32, "cc" * 32]
        labels = np.array([[1.0], [0.0], [1.0]])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            r1 = build_grouped_folds(keys, labels, n_splits=3)
            r2 = build_grouped_folds(keys, labels, n_splits=3)
            assert r1 == r2

    def test_too_few_studies_raises(self) -> None:
        with pytest.raises(ValueError, match="not enough"):
            build_grouped_folds(["aa" * 32], np.array([[1.0]]), n_splits=5)
