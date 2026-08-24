"""Tests for the active-learning queue using synthetic items only."""

from __future__ import annotations

import pytest

from rsna_knee.annotation.queue import QueueItem, build_queue


def _item(key: str, score: float) -> QueueItem:
    return QueueItem(study_key=key, target_column="ACL", uncertainty_score=score)


class TestBuildQueue:
    def test_orders_by_descending_uncertainty(self) -> None:
        result = build_queue([_item("aa" * 32, 0.3), _item("bb" * 32, 0.9)], batch_size=2)
        assert result[0].study_key == "bb" * 32

    def test_ties_break_by_study_key(self) -> None:
        a = _item("aa" * 32, 0.5)
        b = _item("bb" * 32, 0.5)
        assert build_queue([b, a], batch_size=2) == [a, b]

    def test_batch_size_limits_output(self) -> None:
        items = [_item("aa" * 32, 0.1), _item("bb" * 32, 0.9), _item("cc" * 32, 0.5)]
        assert len(build_queue(items, batch_size=2)) == 2

    def test_empty_queue_returns_empty(self) -> None:
        assert build_queue([], batch_size=5) == []

    def test_zero_batch_raises(self) -> None:
        with pytest.raises(ValueError, match="batch_size"):
            build_queue([_item("aa" * 32, 0.1)], batch_size=0)
