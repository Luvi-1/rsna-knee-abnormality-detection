from __future__ import annotations

import math

import numpy as np
import pytest

from rsna_knee.qa.duplicates import (
    DuplicateEdge,
    DuplicateInvariantError,
    EdgeDisposition,
    assert_hard_edges_within_components,
    assert_protected_edges_within_components,
    build_candidate_components,
    build_protected_components,
    canonical_endpoints,
    compare_phash_sequences,
    compare_reports,
    component_members,
    normalize_report,
    report_exact_digest,
)
from rsna_knee.qa.shift import (
    EffectTier,
    categorical_shift,
    continuous_shift,
    iter_bayesian_bootstrap_weights,
    study_equal_weights,
    suppress_count,
)


def test_protected_components_are_transitive_and_permutation_deterministic() -> None:
    edges = [
        DuplicateEdge("study-c", "study-b", "near-series", EdgeDisposition.HARD),
        DuplicateEdge("study-a", "study-b", "same-patient", EdgeDisposition.HARD),
        DuplicateEdge("study-d", "study-c", "candidate-report", EdgeDisposition.CANDIDATE),
    ]
    forward = build_protected_components(["study-d", "study-c", "study-b", "study-a"], edges)
    reverse = build_protected_components(
        reversed(["study-d", "study-c", "study-b", "study-a"]), reversed(edges)
    )
    assert forward == reverse
    assert component_members(forward) == (("study-a", "study-b", "study-c"), ("study-d",))
    assert forward["study-a"] == forward["study-c"]
    assert forward["study-d"] != forward["study-c"]
    assert canonical_endpoints("z", "a") == ("a", "z")


def test_hard_duplicate_edge_invariant_fails_closed() -> None:
    edge = DuplicateEdge("left", "right", "exact-pixel", EdgeDisposition.HARD)
    with pytest.raises(DuplicateInvariantError, match="crosses protected components"):
        assert_hard_edges_within_components([edge], {"left": "left", "right": "right"})
    with pytest.raises(DuplicateInvariantError, match="self-edges"):
        DuplicateEdge("same", "same", "bad", EdgeDisposition.HARD)


def test_soft_candidate_chain_never_collapses_hard_components() -> None:
    nodes = ["study-e", "study-d", "study-c", "study-b", "study-a"]
    edges = [
        DuplicateEdge("study-b", "study-a", "same-patient", EdgeDisposition.HARD),
        DuplicateEdge("study-c", "study-b", "near-series", EdgeDisposition.CANDIDATE),
        DuplicateEdge("study-e", "study-d", "exact-study", EdgeDisposition.HARD),
        DuplicateEdge("study-d", "study-c", "near-report", EdgeDisposition.CANDIDATE),
    ]

    hard_only = build_protected_components(nodes, edges, include_candidates=False)
    assert hard_only["study-b"] != hard_only["study-c"]
    compatibility = build_protected_components(nodes, edges, include_candidates=True)
    assert compatibility == hard_only
    assert component_members(hard_only) == (
        ("study-a", "study-b"),
        ("study-c",),
        ("study-d", "study-e"),
    )

    candidates = build_candidate_components(nodes, edges)
    permuted = build_candidate_components(reversed(nodes), reversed(edges))
    assert candidates == permuted
    assert component_members(candidates) == (
        ("study-a", "study-b", "study-c", "study-d", "study-e"),
    )
    assert all(candidates[edge.left] == candidates[edge.right] for edge in edges)
    assert_protected_edges_within_components(edges, candidates, include_candidates=True)


def test_conservative_edge_invariant_rejects_candidate_crossing() -> None:
    edge = DuplicateEdge("left", "right", "near-series", EdgeDisposition.CANDIDATE)
    with pytest.raises(DuplicateInvariantError, match="crosses protected components"):
        assert_protected_edges_within_components(
            [edge],
            {"left": "left", "right": "right"},
            include_candidates=True,
        )


def test_report_normalization_and_exact_digest_remove_numeric_variants() -> None:
    left = "  ACL tear measures 12.0 mm on 01/02/2026 at 09:30.  "
    right = "acl TEAR measures 8 mm on 03/04/2025 at 11:45."
    assert normalize_report(left) == ("acl tear measures <measurement:mm> on <date> at <time>.")
    assert report_exact_digest(left) == report_exact_digest(right)
    private_key = b"k" * 32
    assert report_exact_digest(left, key=private_key) == report_exact_digest(right, key=private_key)
    match = compare_reports(left, right)
    assert match.exact
    assert match.disposition is EdgeDisposition.CANDIDATE


def test_report_near_confirmation_and_nonmatch() -> None:
    base = " ".join(f"token{index}" for index in range(200))
    near_tokens = [f"token{index}" for index in range(200)]
    near_tokens[100] = "changed"
    near = " ".join(near_tokens)
    unrelated = " ".join(f"other{index}" for index in range(200))
    assert compare_reports(base, near).disposition is EdgeDisposition.CANDIDATE
    candidate_tokens = near_tokens.copy()
    candidate_tokens[101] = "also-changed"
    candidate = " ".join(candidate_tokens)
    assert compare_reports(base, candidate).disposition is EdgeDisposition.CANDIDATE
    assert compare_reports(base, unrelated).disposition is EdgeDisposition.NONE
    assert (
        compare_reports("short normal report", "short abnormal report").disposition
        is EdgeDisposition.NONE
    )


def test_phash_sequences_choose_reverse_and_reject_hard_negative() -> None:
    sequence = tuple(1 << index for index in range(9))
    reversed_near = tuple(reversed(sequence))
    near = compare_phash_sequences(sequence, reversed_near)
    assert near.direction == "reverse"
    assert near.disposition is EdgeDisposition.HARD
    assert near.median_hamming == 0.0

    hard_negative = compare_phash_sequences(
        sequence, tuple(value ^ ((1 << 64) - 1) for value in sequence)
    )
    assert hard_negative.disposition is EdgeDisposition.NONE
    length_mismatch = compare_phash_sequences(sequence, sequence * 2)
    assert length_mismatch.disposition is EdgeDisposition.NONE

    hex_sequence = tuple(f"{value:016x}" for value in sequence)
    hex_match = compare_phash_sequences(hex_sequence, tuple(reversed(hex_sequence)))
    assert hex_match.direction == "reverse"
    assert hex_match.disposition is EdgeDisposition.HARD


def test_study_equal_weights_equalize_repeated_series() -> None:
    weights = study_equal_weights(["a", "a", "b"])
    assert np.allclose(weights, [0.25, 0.25, 0.5])
    assert math.isclose(float(weights.sum()), 1.0)


def test_categorical_shift_zero_unseen_and_effect_tiers() -> None:
    zero = categorical_shift(["a", "b", "a", "b"], ["b", "a", "b", "a"])
    assert zero.total_variation == pytest.approx(0.0)
    assert zero.sqrt_jensen_shannon == pytest.approx(0.0)
    assert zero.tier is EffectTier.NEGLIGIBLE

    unseen = categorical_shift(["a"] * 20, ["a"] * 15 + ["new"] * 5)
    assert unseen.unseen_test_mass == pytest.approx(0.25)
    assert unseen.total_variation == pytest.approx(0.25)
    assert unseen.tier is EffectTier.LARGE

    small = categorical_shift(["a"] * 95 + ["b"] * 5, ["a"] * 90 + ["b"] * 10)
    assert small.total_variation == pytest.approx(0.05)
    assert small.tier is EffectTier.SMALL


def test_continuous_shift_zero_small_and_large() -> None:
    baseline = [float(value) for value in range(100)]
    zero = continuous_shift(baseline, list(reversed(baseline)))
    assert zero.standardized_mean_difference == pytest.approx(0.0)
    assert zero.wasserstein_over_train_iqr == pytest.approx(0.0)
    assert zero.tier is EffectTier.NEGLIGIBLE

    small = continuous_shift(baseline, [value + 4.0 for value in baseline])
    assert 0.10 <= small.standardized_mean_difference < 0.20
    assert small.tier is EffectTier.SMALL

    large = continuous_shift(baseline, [value + 30.0 for value in baseline])
    assert large.standardized_mean_difference >= 0.50
    assert large.tier is EffectTier.LARGE


def test_missingness_suppression_and_bootstrap_are_deterministic() -> None:
    categorical = categorical_shift(["a", None], ["a", "a"])
    assert categorical.train_missing_rate == pytest.approx(0.5)
    assert categorical.missingness_difference == pytest.approx(-0.5)
    assert suppress_count(0) == 0
    assert suppress_count(19) is None
    assert suppress_count(20) == 20

    first_components, first_weights = next(
        iter_bayesian_bootstrap_weights(["component-b", "component-a"], replicates=2)
    )
    second_components, second_weights = next(
        iter_bayesian_bootstrap_weights(["component-a", "component-b"], replicates=2)
    )
    assert first_components == second_components == ("component-a", "component-b")
    assert np.array_equal(first_weights, second_weights)
    assert np.allclose(first_weights.sum(axis=1), 1.0)


def test_shift_metrics_are_permutation_deterministic() -> None:
    train_categories = ["a", "b", "a", None, "c"]
    train_category_weights = [0.1, 0.2, 0.3, 0.1, 0.3]
    order = [4, 2, 0, 3, 1]
    original_categorical = categorical_shift(
        train_categories,
        ["a", "b", "c"],
        train_weights=train_category_weights,
    )
    permuted_categorical = categorical_shift(
        [train_categories[index] for index in order],
        ["c", "a", "b"],
        train_weights=[train_category_weights[index] for index in order],
    )
    assert original_categorical == permuted_categorical

    train_numbers = [1.0, 3.0, 2.0, None, 4.0]
    train_number_weights = [0.1, 0.2, 0.3, 0.1, 0.3]
    original_continuous = continuous_shift(
        train_numbers,
        [1.5, 2.5, 3.5],
        train_weights=train_number_weights,
    )
    permuted_continuous = continuous_shift(
        [train_numbers[index] for index in order],
        [3.5, 1.5, 2.5],
        train_weights=[train_number_weights[index] for index in order],
    )
    assert original_continuous == permuted_continuous
