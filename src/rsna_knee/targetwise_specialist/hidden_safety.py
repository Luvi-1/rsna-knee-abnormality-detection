"""Hidden-shape safety checks for dynamic T137 inference packaging."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass


class HiddenSafetyError(ValueError):
    """Raised when a synthetic or private hidden-shape contract is violated."""


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Aggregate reconciliation result without exposing identifier values."""

    expected_count: int
    produced_count: int
    unique_produced_count: int
    missing_count: int
    unexpected_count: int
    duplicate_count: int

    @property
    def complete(self) -> bool:
        return (
            self.expected_count == self.produced_count
            and self.missing_count == 0
            and self.unexpected_count == 0
            and self.duplicate_count == 0
        )


def reconcile_counts(
    expected_ids: Sequence[str],
    produced_ids: Sequence[str],
) -> ReconciliationResult:
    """Reconcile an output set against dynamic test IDs using aggregate counts only."""

    if not expected_ids:
        raise HiddenSafetyError("expected test identifiers cannot be empty")
    if len(set(expected_ids)) != len(expected_ids):
        raise HiddenSafetyError("expected test identifiers must be unique")

    expected_set = set(expected_ids)
    produced_set = set(produced_ids)
    duplicate_count = len(produced_ids) - len(produced_set)
    return ReconciliationResult(
        expected_count=len(expected_ids),
        produced_count=len(produced_ids),
        unique_produced_count=len(produced_set),
        missing_count=len(expected_set - produced_set),
        unexpected_count=len(produced_set - expected_set),
        duplicate_count=duplicate_count,
    )


def bounded_batches(total_items: int, batch_size: int) -> tuple[range, ...]:
    """Create dynamic bounded index ranges without assuming a public test size."""

    if total_items < 0:
        raise HiddenSafetyError("total_items cannot be negative")
    if batch_size <= 0:
        raise HiddenSafetyError("batch_size must be positive")
    return tuple(
        range(start, min(start + batch_size, total_items))
        for start in range(0, total_items, batch_size)
    )


def classify_series_outcomes(
    outcomes: Iterable[str],
    *,
    recoverable_categories: Sequence[str],
) -> dict[str, int]:
    """Count recoverable and terminal synthetic/private series outcomes.

    Values must be either ``ok`` or a caller-declared failure category. Unknown
    categories fail closed so hidden-data behavior cannot silently disappear.
    """

    allowed = {"ok", *recoverable_categories}
    counts: dict[str, int] = {name: 0 for name in sorted(allowed)}
    for outcome in outcomes:
        if outcome not in allowed:
            raise HiddenSafetyError(f"undeclared series outcome category: {outcome}")
        counts[outcome] += 1
    return counts


def validate_study_prediction_coverage(
    study_to_successful_series: Mapping[str, int],
) -> None:
    """Require at least one usable series for every dynamically discovered study."""

    if not study_to_successful_series:
        raise HiddenSafetyError("study coverage cannot be empty")
    for count in study_to_successful_series.values():
        if count < 1:
            raise HiddenSafetyError("at least one study has no usable series")


def estimate_peak_queue_bytes(
    *,
    workers: int,
    items_per_worker: int,
    bytes_per_item: int,
) -> int:
    """Return a conservative bounded-queue byte estimate with integer arithmetic."""

    if workers < 1 or items_per_worker < 1 or bytes_per_item < 1:
        raise HiddenSafetyError("queue dimensions must be positive")
    return workers * items_per_worker * bytes_per_item
