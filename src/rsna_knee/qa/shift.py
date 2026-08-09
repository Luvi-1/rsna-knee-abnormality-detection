"""Deterministic, study-weighted train/test distribution-shift summaries."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import numpy.typing as npt

DEFAULT_BOOTSTRAP_REPLICATES = 10_000
DEFAULT_BOOTSTRAP_SEED = 20_260_808
DEFAULT_SUPPRESSION_K = 20


class ShiftInputError(ValueError):
    """Raised when a shift estimate would be ambiguous or invalid."""


class EffectTier(StrEnum):
    """Predeclared descriptive, not inferential, effect-size tiers."""

    NEGLIGIBLE = "negligible"
    SMALL = "small"
    MODERATE = "moderate"
    LARGE = "large"


def study_equal_weights(study_keys: Sequence[str]) -> npt.NDArray[np.float64]:
    """Give every study equal total weight regardless of its number of rows."""

    if not study_keys:
        raise ShiftInputError("study keys must be non-empty")
    if any(not key for key in study_keys):
        raise ShiftInputError("study keys must be non-empty")
    counts = Counter(study_keys)
    study_weight = 1.0 / len(counts)
    return np.asarray([study_weight / counts[key] for key in study_keys], dtype=np.float64)


def _validated_weights(
    size: int, weights: Sequence[float] | npt.NDArray[np.float64] | None
) -> npt.NDArray[np.float64]:
    if size <= 0:
        raise ShiftInputError("shift inputs must be non-empty")
    if weights is None:
        result = np.full(size, 1.0 / size, dtype=np.float64)
    else:
        result = np.asarray(weights, dtype=np.float64)
        if result.ndim != 1 or len(result) != size:
            raise ShiftInputError("weights must match input length")
        if not np.all(np.isfinite(result)) or np.any(result < 0.0):
            raise ShiftInputError("weights must be finite and non-negative")
        total = math.fsum(float(value) for value in result)
        if total <= 0.0:
            raise ShiftInputError("weights must have positive total mass")
        result = result / total
    return result


def categorical_effect_tier(total_variation: float) -> EffectTier:
    """Classify total-variation distance using frozen descriptive thresholds."""

    if not math.isfinite(total_variation) or not 0.0 <= total_variation <= 1.0:
        raise ShiftInputError("total variation must be finite and between zero and one")
    if total_variation < 0.05:
        return EffectTier.NEGLIGIBLE
    if total_variation < 0.10:
        return EffectTier.SMALL
    if total_variation < 0.20:
        return EffectTier.MODERATE
    return EffectTier.LARGE


def continuous_effect_tier(standardized_mean_difference: float) -> EffectTier:
    """Classify absolute SMD using frozen descriptive thresholds."""

    magnitude = abs(standardized_mean_difference)
    if math.isnan(magnitude):
        raise ShiftInputError("standardized mean difference may not be NaN")
    if magnitude < 0.10:
        return EffectTier.NEGLIGIBLE
    if magnitude < 0.20:
        return EffectTier.SMALL
    if magnitude < 0.50:
        return EffectTier.MODERATE
    return EffectTier.LARGE


@dataclass(frozen=True)
class CategoricalShift:
    """Privacy-safe categorical shift effect sizes."""

    total_variation: float
    sqrt_jensen_shannon: float
    unseen_test_mass: float
    train_missing_rate: float
    test_missing_rate: float
    missingness_difference: float
    tier: EffectTier


def _categorical_distribution(
    values: Sequence[str | None], weights: npt.NDArray[np.float64]
) -> tuple[dict[str, float], float]:
    missing_rate = math.fsum(
        float(weight) for value, weight in zip(values, weights, strict=True) if value is None
    )
    missing_rate = min(1.0, max(0.0, missing_rate))
    observed_mass = 1.0 - missing_rate
    if observed_mass <= 0.0:
        raise ShiftInputError("categorical input has no observed values")
    category_weights: dict[str, list[float]] = {}
    for value, weight in zip(values, weights, strict=True):
        if value is None or weight <= 0.0:
            continue
        category_weights.setdefault(value, []).append(float(weight))
    distribution = {
        category: math.fsum(category_weights[category]) / observed_mass
        for category in sorted(category_weights)
    }
    return distribution, missing_rate


def categorical_shift(
    train: Sequence[str | None],
    test: Sequence[str | None],
    *,
    train_weights: Sequence[float] | npt.NDArray[np.float64] | None = None,
    test_weights: Sequence[float] | npt.NDArray[np.float64] | None = None,
) -> CategoricalShift:
    """Compute TV, square-root JS, unseen mass, and missingness shift."""

    train_weight_array = _validated_weights(len(train), train_weights)
    test_weight_array = _validated_weights(len(test), test_weights)
    train_distribution, train_missing = _categorical_distribution(train, train_weight_array)
    test_distribution, test_missing = _categorical_distribution(test, test_weight_array)
    categories = sorted(train_distribution.keys() | test_distribution.keys())
    train_probabilities = np.asarray(
        [train_distribution.get(category, 0.0) for category in categories], dtype=np.float64
    )
    test_probabilities = np.asarray(
        [test_distribution.get(category, 0.0) for category in categories], dtype=np.float64
    )
    total_variation = 0.5 * float(np.abs(train_probabilities - test_probabilities).sum())
    midpoint = 0.5 * (train_probabilities + test_probabilities)
    train_mask = train_probabilities > 0.0
    test_mask = test_probabilities > 0.0
    divergence = 0.5 * float(
        np.sum(
            train_probabilities[train_mask]
            * np.log2(train_probabilities[train_mask] / midpoint[train_mask])
        )
        + np.sum(
            test_probabilities[test_mask]
            * np.log2(test_probabilities[test_mask] / midpoint[test_mask])
        )
    )
    unseen_test_mass = float(
        sum(
            probability
            for category, probability in test_distribution.items()
            if train_distribution.get(category, 0.0) == 0.0
        )
    )
    total_variation = min(1.0, max(0.0, total_variation))
    divergence = min(1.0, max(0.0, divergence))
    return CategoricalShift(
        total_variation=total_variation,
        sqrt_jensen_shannon=math.sqrt(divergence),
        unseen_test_mass=unseen_test_mass,
        train_missing_rate=train_missing,
        test_missing_rate=test_missing,
        missingness_difference=test_missing - train_missing,
        tier=categorical_effect_tier(total_variation),
    )


def _numeric_values(values: Sequence[float | None]) -> npt.NDArray[np.float64]:
    result = np.asarray([math.nan if value is None else float(value) for value in values])
    if result.ndim != 1 or not len(result):
        raise ShiftInputError("continuous inputs must be non-empty")
    if np.any(np.isinf(result)):
        raise ShiftInputError("continuous inputs may not contain infinity")
    return result


def _observed_numeric(
    values: npt.NDArray[np.float64], weights: npt.NDArray[np.float64]
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], float]:
    observed = ~np.isnan(values)
    observed_mass = math.fsum(float(weight) for weight in weights[observed])
    if observed_mass <= 0.0:
        raise ShiftInputError("continuous input has no observed values")
    observed_values = values[observed]
    observed_weights = weights[observed] / observed_mass
    order = np.lexsort((observed_weights, observed_values))
    missing_rate = min(1.0, max(0.0, 1.0 - observed_mass))
    return observed_values[order], observed_weights[order], missing_rate


def _weighted_quantile(
    values: npt.NDArray[np.float64], weights: npt.NDArray[np.float64], quantile: float
) -> float:
    order = np.argsort(values, kind="stable")
    ordered_values = values[order]
    ordered_weights = weights[order]
    positions = np.cumsum(ordered_weights) - 0.5 * ordered_weights
    positions = positions / float(ordered_weights.sum())
    return float(
        np.interp(
            quantile,
            positions,
            ordered_values,
            left=ordered_values[0],
            right=ordered_values[-1],
        )
    )


def _wasserstein_one(
    left_values: npt.NDArray[np.float64],
    left_weights: npt.NDArray[np.float64],
    right_values: npt.NDArray[np.float64],
    right_weights: npt.NDArray[np.float64],
) -> float:
    support = np.union1d(left_values, right_values)
    if len(support) <= 1:
        return 0.0
    left_order = np.argsort(left_values, kind="stable")
    right_order = np.argsort(right_values, kind="stable")
    left_sorted = left_values[left_order]
    right_sorted = right_values[right_order]
    left_cumulative = np.cumsum(left_weights[left_order])
    right_cumulative = np.cumsum(right_weights[right_order])
    interval_starts = support[:-1]
    left_indices = np.searchsorted(left_sorted, interval_starts, side="right") - 1
    right_indices = np.searchsorted(right_sorted, interval_starts, side="right") - 1
    left_cdf = np.where(left_indices >= 0, left_cumulative[np.maximum(left_indices, 0)], 0.0)
    right_cdf = np.where(right_indices >= 0, right_cumulative[np.maximum(right_indices, 0)], 0.0)
    return float(np.sum(np.abs(left_cdf - right_cdf) * np.diff(support)))


def _scaled_difference(numerator: float, scale: float) -> float:
    if scale > 0.0:
        return numerator / scale
    if numerator == 0.0:
        return 0.0
    return math.copysign(math.inf, numerator)


@dataclass(frozen=True)
class ContinuousShift:
    """Privacy-safe continuous shift effect sizes."""

    standardized_mean_difference: float
    median_difference_over_train_iqr: float
    wasserstein_over_train_iqr: float
    train_missing_rate: float
    test_missing_rate: float
    missingness_difference: float
    tier: EffectTier


def continuous_shift(
    train: Sequence[float | None],
    test: Sequence[float | None],
    *,
    train_weights: Sequence[float] | npt.NDArray[np.float64] | None = None,
    test_weights: Sequence[float] | npt.NDArray[np.float64] | None = None,
) -> ContinuousShift:
    """Compute SMD, median/IQR, W1/IQR, and missingness shift."""

    train_array = _numeric_values(train)
    test_array = _numeric_values(test)
    train_weight_array = _validated_weights(len(train_array), train_weights)
    test_weight_array = _validated_weights(len(test_array), test_weights)
    train_values, train_observed_weights, train_missing = _observed_numeric(
        train_array, train_weight_array
    )
    test_values, test_observed_weights, test_missing = _observed_numeric(
        test_array, test_weight_array
    )
    train_mean = float(np.dot(train_values, train_observed_weights))
    test_mean = float(np.dot(test_values, test_observed_weights))
    train_variance = float(np.dot((train_values - train_mean) ** 2, train_observed_weights))
    test_variance = float(np.dot((test_values - test_mean) ** 2, test_observed_weights))
    pooled_standard_deviation = math.sqrt(0.5 * (train_variance + test_variance))
    standardized_mean_difference = _scaled_difference(
        test_mean - train_mean, pooled_standard_deviation
    )
    train_q1 = _weighted_quantile(train_values, train_observed_weights, 0.25)
    train_median = _weighted_quantile(train_values, train_observed_weights, 0.50)
    train_q3 = _weighted_quantile(train_values, train_observed_weights, 0.75)
    test_median = _weighted_quantile(test_values, test_observed_weights, 0.50)
    train_iqr = train_q3 - train_q1
    median_difference = _scaled_difference(test_median - train_median, train_iqr)
    wasserstein = _wasserstein_one(
        train_values, train_observed_weights, test_values, test_observed_weights
    )
    wasserstein_scaled = _scaled_difference(wasserstein, train_iqr)
    return ContinuousShift(
        standardized_mean_difference=standardized_mean_difference,
        median_difference_over_train_iqr=median_difference,
        wasserstein_over_train_iqr=wasserstein_scaled,
        train_missing_rate=train_missing,
        test_missing_rate=test_missing,
        missingness_difference=test_missing - train_missing,
        tier=continuous_effect_tier(standardized_mean_difference),
    )


def suppress_count(count: int, *, minimum: int = DEFAULT_SUPPRESSION_K) -> int | None:
    """Return zero or a publishable count; suppress non-zero cells below k."""

    if count < 0:
        raise ValueError("count may not be negative")
    if minimum <= 0:
        raise ValueError("suppression minimum must be positive")
    if count == 0 or count >= minimum:
        return count
    return None


def iter_bayesian_bootstrap_weights(
    component_keys: Sequence[str],
    *,
    replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    batch_size: int = 256,
) -> Iterator[tuple[tuple[str, ...], npt.NDArray[np.float64]]]:
    """Yield deterministic Exp(1) protected-component weights in bounded batches."""

    if not component_keys or any(not key for key in component_keys):
        raise ShiftInputError("protected-component keys must be non-empty")
    if replicates <= 0 or batch_size <= 0:
        raise ShiftInputError("replicates and batch_size must be positive")
    components = tuple(sorted(set(component_keys)))
    generator = np.random.Generator(np.random.PCG64(seed))
    remaining = replicates
    while remaining:
        current_size = min(batch_size, remaining)
        weights = generator.exponential(1.0, size=(current_size, len(components)))
        weights /= weights.sum(axis=1, keepdims=True)
        yield components, weights
        remaining -= current_size
