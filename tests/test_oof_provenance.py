"""Tests for OOF provenance and leakage prevention using synthetic data."""

from __future__ import annotations

import numpy as np
import pytest

from rsna_knee.evaluation.bootstrap import bootstrap_macro_auc
from rsna_knee.folds.grouped_multilabel import build_grouped_folds

_KEYS = ["aa" * 32, "bb" * 32, "cc" * 32, "dd" * 32]
_LABELS = np.array([[1.0], [0.0], [1.0], [0.0]])
_SCORES = np.array([[0.9], [0.1], [0.8], [0.2]])


class TestOofProvenance:
    def test_folds_are_deterministic(self) -> None:
        r1 = build_grouped_folds(_KEYS, _LABELS, n_splits=2)
        r2 = build_grouped_folds(_KEYS, _LABELS, n_splits=2)
        assert r1 == r2

    def test_no_study_in_multiple_folds(self) -> None:
        result = build_grouped_folds(_KEYS, _LABELS, n_splits=2)
        fold_map = {a.study_key: a.fold_index for a in result}
        assert len(fold_map) == len(_KEYS)

    def test_bootstrap_ci_is_bounded(self) -> None:
        lo, hi = bootstrap_macro_auc(_LABELS, _SCORES, n_bootstraps=100)
        assert 0.0 <= lo <= hi <= 1.0

    def test_bootstrap_rejects_invalid_confidence(self) -> None:
        with pytest.raises(ValueError, match="confidence_level"):
            bootstrap_macro_auc(_LABELS, _SCORES, confidence_level=1.5)
