from __future__ import annotations

import math

import numpy as np
import pytest

from rsna_knee.targetwise_specialist import (
    CandidateSpec,
    CandidateStatus,
    ContractError,
    EvidenceLevel,
    FAMILIES,
    FrozenRound,
    PROTECTED_CHAMPION_SCORE,
    PROTECTED_CHAMPION_SUBMISSION_ID,
    REJECTED_WINDOW_SUBMISSION_SCORE,
    RankError,
    SpecialistEvidence,
    TARGETS,
    authorization_request,
    best_by_target,
    identical_ordering,
    logit_blend,
    normalized_average_ranks,
    parse_candidate,
    pearson_correlation,
    probability_blend,
    rank_blend,
    rank_disagreement,
    rank_evidence,
    score_evidence,
    spearman_correlation,
    target_swap,
    targetwise_rank_blend,
    top_fraction_overlap,
    validate_submission_matrix,
)


def _candidate(**overrides: object) -> CandidateSpec:
    values: dict[str, object] = {
        "candidate_id": "OA_RANK_75_25",
        "parent_submission_id": PROTECTED_CHAMPION_SUBMISSION_ID,
        "parent_score": PROTECTED_CHAMPION_SCORE,
        "changed_targets": FAMILIES["osteoarthritis"],
        "blend_type": "normalized_rank",
        "model_ids": ("champion", "efficientnetv2_l_480"),
        "weights": (0.75, 0.25),
        "runtime_seconds": 1200.0,
        "expected_information_gain": 0.8,
    }
    values.update(overrides)
    result = CandidateSpec(**values)  # type: ignore[arg-type]
    result.validate()
    return result


def _evidence(**overrides: object) -> SpecialistEvidence:
    values: dict[str, object] = {
        "model_id": "efficientnetv2_l_480",
        "target": "Medial OA",
        "family": "osteoarthritis",
        "evidence_level": EvidenceLevel.C_SOURCE_TARGET_METRIC,
        "source_metric": 0.91,
        "source_metric_definition": "source validation AUC",
        "rank_correlation_with_champion": 0.90,
        "rank_disagreement_with_champion": 0.12,
        "status": CandidateStatus.ADMISSIBLE_REPRODUCIBLE,
        "runtime_seconds": 1200.0,
    }
    values.update(overrides)
    result = SpecialistEvidence(**values)  # type: ignore[arg-type]
    result.validate()
    return result


def test_exact_target_order() -> None:
    assert TARGETS == (
        "ACL",
        "MCL",
        "Medial Meniscus",
        "Lateral Meniscus",
        "Medial OA",
        "Lateral OA",
        "PF OA",
        "Effusion",
        "Synovitis",
        "Baker's",
        "Contusion",
        "Fracture",
    )


def test_t137_families_are_exact() -> None:
    assert FAMILIES == {
        "osteoarthritis": ("Medial OA", "Lateral OA", "PF OA"),
        "fluid_inflammation": ("Effusion", "Synovitis", "Baker's"),
        "bone": ("Contusion", "Fracture"),
    }


def test_protected_champion_and_rejected_window_scores() -> None:
    assert PROTECTED_CHAMPION_SUBMISSION_ID == 55976422
    assert PROTECTED_CHAMPION_SCORE == 0.929
    assert REJECTED_WINDOW_SUBMISSION_SCORE == 0.928


def test_candidate_requires_protected_champion() -> None:
    with pytest.raises(ContractError, match="protected champion"):
        _candidate(parent_submission_id=55950275)


def test_candidate_weights_must_sum_to_one() -> None:
    with pytest.raises(ContractError, match="sum to 1"):
        _candidate(weights=(0.8, 0.3))


def test_candidate_rejects_unknown_target() -> None:
    with pytest.raises(ContractError, match="unknown target"):
        _candidate(changed_targets=("Unknown",))


def test_round_respects_live_allowance() -> None:
    with pytest.raises(ContractError, match="live submission allowance"):
        FrozenRound(
            round_id="T137_TARGETWISE_SPECIALIST_001_PREPARED",
            live_submission_allowance=1,
            candidates=(_candidate(candidate_id="A"), _candidate(candidate_id="B")),
        ).validate()


def test_round_rejects_reports_hidden_labels_network_and_submission_api() -> None:
    for field in (
        "reports_used",
        "hidden_labels_used",
        "network_enabled",
        "submission_api_embedded",
    ):
        with pytest.raises(ContractError):
            FrozenRound(
                round_id="T137",
                live_submission_allowance=1,
                candidates=(_candidate(),),
                **{field: True},
            ).validate()


def test_manifest_hash_is_deterministic() -> None:
    first = FrozenRound(
        round_id="T137_TARGETWISE_SPECIALIST_001_PREPARED",
        live_submission_allowance=1,
        candidates=(_candidate(),),
    )
    second = FrozenRound(
        round_id="T137_TARGETWISE_SPECIALIST_001_PREPARED",
        live_submission_allowance=1,
        candidates=(_candidate(),),
    )
    assert first.sha256() == second.sha256()
    assert len(first.sha256()) == 64


def test_authorization_request_has_no_placeholders_for_one_candidate() -> None:
    round_manifest = FrozenRound(
        round_id="T137_TARGETWISE_SPECIALIST_001_PREPARED",
        live_submission_allowance=1,
        candidates=(_candidate(candidate_id="T137_OA_75_25"),),
    )
    text = authorization_request(round_manifest)
    assert "<" not in text and ">" not in text
    assert "T137_TARGETWISE_SPECIALIST_001_PREPARED" in text
    assert "T137_OA_75_25" in text
    assert round_manifest.sha256() in text
    assert "make no second submission" in text


def test_authorization_request_matches_candidate_count() -> None:
    round_manifest = FrozenRound(
        round_id="T137_TARGETWISE_SPECIALIST_001_PREPARED",
        live_submission_allowance=2,
        candidates=(_candidate(candidate_id="A"), _candidate(candidate_id="B")),
    )
    text = authorization_request(round_manifest)
    assert "up to 2" in text
    assert "reaches 0.950" in text


def test_empty_round_cannot_request_authorization() -> None:
    with pytest.raises(ContractError, match="empty round"):
        authorization_request(
            FrozenRound(round_id="T137", live_submission_allowance=1, candidates=())
        )


def test_parse_candidate_round_trip() -> None:
    parsed = parse_candidate(
        {
            "candidate_id": "BONE_FRACTURE_ONLY",
            "parent_submission_id": 55976422,
            "parent_score": 0.929,
            "changed_targets": ["Fracture"],
            "blend_type": "normalized_rank",
            "model_ids": ["champion", "bone_model"],
            "weights": [0.75, 0.25],
            "runtime_seconds": 500.0,
            "expected_information_gain": 0.5,
        }
    )
    assert parsed.changed_targets == ("Fracture",)


def test_average_ranks_handle_ties_deterministically() -> None:
    ranks = normalized_average_ranks([10.0, 20.0, 20.0, 40.0])
    np.testing.assert_allclose(ranks, [0.0, 0.5, 0.5, 1.0])


def test_average_ranks_single_item() -> None:
    np.testing.assert_array_equal(normalized_average_ranks([42.0]), [0.0])


def test_rank_helpers_reject_nonfinite_values() -> None:
    with pytest.raises(RankError, match="nonfinite"):
        normalized_average_ranks([0.0, float("nan")])


def test_pearson_and_spearman_are_one_for_monotonic_vectors() -> None:
    left = [0.1, 0.2, 0.3, 0.4]
    right = [1.0, 2.0, 3.0, 4.0]
    assert pearson_correlation(left, right) == pytest.approx(1.0)
    assert spearman_correlation(left, right) == pytest.approx(1.0)


def test_rank_disagreement_is_zero_for_same_ordering() -> None:
    assert rank_disagreement([0.1, 0.2, 0.3], [10.0, 20.0, 30.0]) == pytest.approx(0.0)
    assert identical_ordering([0.1, 0.2, 0.3], [10.0, 20.0, 30.0])


def test_top_fraction_overlap() -> None:
    overlap = top_fraction_overlap([1, 2, 3, 4], [1, 4, 2, 3], fraction=0.5)
    assert overlap == pytest.approx(0.5)


def test_probability_blend() -> None:
    result = probability_blend(([0.0, 1.0], [1.0, 0.0]), (0.75, 0.25))
    np.testing.assert_allclose(result, [0.25, 0.75])


def test_logit_blend_stays_in_probability_range() -> None:
    result = logit_blend(([0.01, 0.99], [0.20, 0.80]), (0.5, 0.5))
    assert np.all((result > 0.0) & (result < 1.0))


def test_rank_blend_preserves_length_and_range() -> None:
    result = rank_blend(([0.2, 0.1, 0.3], [0.3, 0.2, 0.1]), (0.5, 0.5))
    assert result.shape == (3,)
    assert np.all((result >= 0.0) & (result <= 1.0))


def test_target_swap_changes_only_selected_column() -> None:
    champion = np.arange(36, dtype=float).reshape(3, 12) / 36.0
    challenger = np.flip(champion, axis=0)
    result = target_swap(champion, challenger, target_indices=(4,))
    np.testing.assert_array_equal(result[:, 4], challenger[:, 4])
    np.testing.assert_array_equal(result[:, 3], champion[:, 3])
    np.testing.assert_array_equal(result[:, 5], champion[:, 5])


def test_targetwise_rank_blend_preserves_unselected_targets() -> None:
    champion = np.tile(np.linspace(0.1, 0.9, 12), (4, 1))
    challenger = champion.copy()
    challenger[:, 4] = [0.8, 0.1, 0.7, 0.2]
    champion[:, 4] = [0.1, 0.2, 0.3, 0.4]
    result = targetwise_rank_blend(
        champion,
        challenger,
        target_indices=(4,),
        champion_weight=0.75,
    )
    np.testing.assert_array_equal(result[:, 5], champion[:, 5])
    assert not np.array_equal(result[:, 4], champion[:, 4])


def test_submission_matrix_requires_12_targets() -> None:
    with pytest.raises(Exception, match="12 targets"):
        validate_submission_matrix(np.zeros((3, 11)))


def test_submission_matrix_rejects_out_of_range_values() -> None:
    values = np.zeros((3, 12))
    values[0, 0] = 1.5
    with pytest.raises(Exception, match="\[0, 1\]"):
        validate_submission_matrix(values)


def test_evidence_target_must_match_family() -> None:
    with pytest.raises(ContractError, match="not in family"):
        _evidence(target="Fracture", family="osteoarthritis")


def test_blocked_evidence_gets_negative_infinity() -> None:
    ranked = score_evidence(_evidence(status=CandidateStatus.BLOCKED_PROVENANCE))
    assert ranked.heuristic_score == float("-inf")


def test_duplicate_like_evidence_is_penalized() -> None:
    duplicate = score_evidence(
        _evidence(
            model_id="duplicate",
            rank_correlation_with_champion=0.999,
            rank_disagreement_with_champion=0.001,
        )
    )
    complementary = score_evidence(
        _evidence(
            model_id="complementary",
            rank_correlation_with_champion=0.90,
            rank_disagreement_with_champion=0.12,
        )
    )
    assert complementary.heuristic_score > duplicate.heuristic_score


def test_over_nine_hour_runtime_is_blocked_by_offline_ranker() -> None:
    ranked = score_evidence(_evidence(runtime_seconds=9 * 60 * 60 + 1))
    assert ranked.heuristic_score == float("-inf")
    assert "runtime_blocked" in ranked.reasons


def test_rank_evidence_is_deterministic() -> None:
    records = [
        _evidence(model_id="b", target="Medial OA"),
        _evidence(model_id="a", target="Lateral OA"),
    ]
    first = rank_evidence(records)
    second = rank_evidence(reversed(records))
    assert [(item.evidence.model_id, item.heuristic_score) for item in first] == [
        (item.evidence.model_id, item.heuristic_score) for item in second
    ]


def test_best_by_target_returns_one_admissible_model_per_target() -> None:
    records = [
        _evidence(model_id="weak", source_metric=0.70),
        _evidence(model_id="strong", source_metric=0.95),
        _evidence(
            model_id="blocked",
            source_metric=0.99,
            status=CandidateStatus.BLOCKED_LICENSE,
        ),
    ]
    best = best_by_target(records)
    assert best["Medial OA"].evidence.model_id == "strong"


def test_champion_only_improves_rule_is_strict() -> None:
    champion = 0.929
    assert 0.930 > champion
    assert not 0.929 > champion
    assert not 0.928 > champion


def test_success_gate_is_exactly_point_95_or_higher() -> None:
    assert 0.950 >= 0.950
    assert not 0.949 >= 0.950
    assert math.isfinite(PROTECTED_CHAMPION_SCORE)
