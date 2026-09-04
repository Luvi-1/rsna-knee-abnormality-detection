"""Offline candidate ranking for the T137 specialist campaign."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from rsna_knee.targetwise_specialist.contracts import (
    CandidateStatus,
    EvidenceLevel,
    SpecialistEvidence,
)


_EVIDENCE_WEIGHT: dict[EvidenceLevel, float] = {
    EvidenceLevel.A_PROJECT_OOF: 1.00,
    EvidenceLevel.B_GROUPED_HELDOUT: 0.85,
    EvidenceLevel.C_SOURCE_TARGET_METRIC: 0.60,
    EvidenceLevel.D_CONTAMINATED_DIAGNOSTIC: 0.20,
    EvidenceLevel.E_SPECIALIZATION_OR_DIVERSITY: 0.15,
    EvidenceLevel.F_OVERALL_SOURCE_SCORE: 0.05,
}


@dataclass(frozen=True, slots=True)
class RankedEvidence:
    """Evidence record with a transparent heuristic score."""

    evidence: SpecialistEvidence
    heuristic_score: float
    reasons: tuple[str, ...]


def score_evidence(evidence: SpecialistEvidence) -> RankedEvidence:
    """Score one evidence record without pretending to predict leaderboard AUC."""

    evidence.validate()
    if evidence.status is not CandidateStatus.ADMISSIBLE_REPRODUCIBLE:
        return RankedEvidence(evidence=evidence, heuristic_score=float("-inf"), reasons=("blocked",))

    score = _EVIDENCE_WEIGHT[evidence.evidence_level]
    reasons: list[str] = [f"evidence={evidence.evidence_level.value}"]

    if evidence.source_metric is not None:
        score += 0.25 * (evidence.source_metric - 0.5) / 0.5
        reasons.append("source_metric_present")

    if evidence.rank_disagreement_with_champion is not None:
        score += 0.75 * evidence.rank_disagreement_with_champion
        reasons.append("rank_diversity")

    if evidence.rank_correlation_with_champion is not None:
        if evidence.rank_correlation_with_champion >= 0.995:
            score -= 1.0
            reasons.append("duplicate_like")
        elif evidence.rank_correlation_with_champion < 0.95:
            score += 0.10
            reasons.append("complementary_ranking")

    if evidence.runtime_seconds is not None:
        if evidence.runtime_seconds > 9 * 60 * 60:
            return RankedEvidence(
                evidence=evidence,
                heuristic_score=float("-inf"),
                reasons=tuple(reasons + ["runtime_blocked"]),
            )
        score -= min(evidence.runtime_seconds / (9 * 60 * 60), 1.0) * 0.10
        reasons.append("runtime_penalty")

    if not math.isfinite(score):
        raise ValueError("heuristic score must be finite for admissible evidence")
    return RankedEvidence(evidence=evidence, heuristic_score=score, reasons=tuple(reasons))


def rank_evidence(records: Iterable[SpecialistEvidence]) -> tuple[RankedEvidence, ...]:
    """Rank evidence deterministically, highest heuristic value first."""

    ranked = [score_evidence(item) for item in records]
    ranked.sort(
        key=lambda item: (
            -item.heuristic_score,
            item.evidence.family,
            item.evidence.target,
            item.evidence.model_id,
        )
    )
    return tuple(ranked)


def best_by_target(records: Iterable[SpecialistEvidence]) -> dict[str, RankedEvidence]:
    """Return the highest-ranked admissible record for each represented target."""

    best: dict[str, RankedEvidence] = {}
    for item in rank_evidence(records):
        if item.heuristic_score == float("-inf"):
            continue
        best.setdefault(item.evidence.target, item)
    return best
