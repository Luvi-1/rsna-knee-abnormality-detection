from __future__ import annotations

import pytest

from rsna_knee.targetwise_specialist.hidden_safety import (
    HiddenSafetyError,
    bounded_batches,
    classify_series_outcomes,
    estimate_peak_queue_bytes,
    reconcile_counts,
    validate_study_prediction_coverage,
)


def test_reconciliation_complete_for_dynamic_hidden_size() -> None:
    expected = tuple(f"study-{index}" for index in range(517))
    produced = tuple(reversed(expected))
    result = reconcile_counts(expected, produced)
    assert result.complete
    assert result.expected_count == 517
    assert result.produced_count == 517


def test_reconciliation_detects_missing_duplicate_and_unexpected() -> None:
    result = reconcile_counts(("a", "b", "c"), ("a", "a", "d"))
    assert not result.complete
    assert result.missing_count == 2
    assert result.unexpected_count == 1
    assert result.duplicate_count == 1


def test_reconciliation_rejects_duplicate_expected_ids() -> None:
    with pytest.raises(HiddenSafetyError, match="unique"):
        reconcile_counts(("a", "a"), ("a",))


def test_bounded_batches_use_runtime_count_not_public_three() -> None:
    batches = bounded_batches(1003, 64)
    assert len(batches) == 16
    assert batches[0].start == 0
    assert batches[-1].stop == 1003
    assert max(len(batch) for batch in batches) <= 64


def test_bounded_batches_allow_zero_items() -> None:
    assert bounded_batches(0, 64) == ()


def test_bounded_batches_reject_invalid_batch_size() -> None:
    with pytest.raises(HiddenSafetyError, match="positive"):
        bounded_batches(10, 0)


def test_declared_recoverable_series_categories_are_counted() -> None:
    counts = classify_series_outcomes(
        ("ok", "decode_failure", "ok", "geometry_failure"),
        recoverable_categories=("decode_failure", "geometry_failure"),
    )
    assert counts == {"decode_failure": 1, "geometry_failure": 1, "ok": 2}


def test_unknown_series_category_fails_closed() -> None:
    with pytest.raises(HiddenSafetyError, match="undeclared"):
        classify_series_outcomes(
            ("ok", "mystery"),
            recoverable_categories=("decode_failure",),
        )


def test_every_study_must_retain_one_usable_series() -> None:
    validate_study_prediction_coverage({"a": 1, "b": 3})
    with pytest.raises(HiddenSafetyError, match="no usable series"):
        validate_study_prediction_coverage({"a": 1, "b": 0})


def test_queue_memory_estimate_is_bounded() -> None:
    assert (
        estimate_peak_queue_bytes(workers=4, items_per_worker=2, bytes_per_item=1_048_576)
        == 8_388_608
    )
