"""Fail-closed contracts for the T137 targetwise specialist campaign.

This module is deliberately network-free and contains no Kaggle submission logic.
It operates only on aggregate metadata and prediction arrays supplied by a private
execution environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


TARGETS: tuple[str, ...] = (
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

FAMILIES: dict[str, tuple[str, ...]] = {
    "osteoarthritis": ("Medial OA", "Lateral OA", "PF OA"),
    "fluid_inflammation": ("Effusion", "Synovitis", "Baker's"),
    "bone": ("Contusion", "Fracture"),
}

PROTECTED_CHAMPION_SUBMISSION_ID = 55976422
PROTECTED_CHAMPION_SCORE = 0.929
REJECTED_WINDOW_SUBMISSION_SCORE = 0.928


class ContractError(ValueError):
    """Raised when a T137 campaign record violates a fail-closed contract."""


class EvidenceLevel(StrEnum):
    """Strength of target-level performance evidence."""

    A_PROJECT_OOF = "A_PROJECT_OOF"
    B_GROUPED_HELDOUT = "B_GROUPED_HELDOUT"
    C_SOURCE_TARGET_METRIC = "C_SOURCE_TARGET_METRIC"
    D_CONTAMINATED_DIAGNOSTIC = "D_CONTAMINATED_DIAGNOSTIC"
    E_SPECIALIZATION_OR_DIVERSITY = "E_SPECIALIZATION_OR_DIVERSITY"
    F_OVERALL_SOURCE_SCORE = "F_OVERALL_SOURCE_SCORE"


class CandidateStatus(StrEnum):
    """Technical status for a specialist model."""

    ADMISSIBLE_REPRODUCIBLE = "ADMISSIBLE_REPRODUCIBLE"
    BLOCKED_LICENSE = "BLOCKED_LICENSE"
    BLOCKED_ASSET = "BLOCKED_ASSET"
    BLOCKED_PROVENANCE = "BLOCKED_PROVENANCE"
    BLOCKED_SECURITY = "BLOCKED_SECURITY"
    BLOCKED_RUNTIME = "BLOCKED_RUNTIME"
    DUPLICATE = "DUPLICATE"
    LOW_EXPECTED_VALUE = "LOW_EXPECTED_VALUE"


@dataclass(frozen=True, slots=True)
class SpecialistEvidence:
    """One model-target evidence record used only for offline ranking."""

    model_id: str
    target: str
    family: str
    evidence_level: EvidenceLevel
    source_metric: float | None
    source_metric_definition: str
    rank_correlation_with_champion: float | None
    rank_disagreement_with_champion: float | None
    status: CandidateStatus
    runtime_seconds: float | None

    def validate(self) -> None:
        if self.target not in TARGETS:
            raise ContractError(f"unknown target: {self.target}")
        if self.family not in FAMILIES:
            raise ContractError(f"unknown T137 family: {self.family}")
        if self.target not in FAMILIES[self.family]:
            raise ContractError(f"{self.target} is not in family {self.family}")
        for name, value in (
            ("source_metric", self.source_metric),
            ("rank_correlation_with_champion", self.rank_correlation_with_champion),
            ("rank_disagreement_with_champion", self.rank_disagreement_with_champion),
        ):
            if value is not None and not math.isfinite(value):
                raise ContractError(f"{name} must be finite when present")
        if self.source_metric is not None and not 0.0 <= self.source_metric <= 1.0:
            raise ContractError("source_metric must be within [0, 1]")
        if self.rank_correlation_with_champion is not None and not (
            -1.0 <= self.rank_correlation_with_champion <= 1.0
        ):
            raise ContractError("rank correlation must be within [-1, 1]")
        if self.rank_disagreement_with_champion is not None and not (
            0.0 <= self.rank_disagreement_with_champion <= 1.0
        ):
            raise ContractError("rank disagreement must be within [0, 1]")
        if self.runtime_seconds is not None and self.runtime_seconds < 0:
            raise ContractError("runtime cannot be negative")


@dataclass(frozen=True, slots=True)
class CandidateSpec:
    """One frozen targetwise challenger candidate."""

    candidate_id: str
    parent_submission_id: int
    parent_score: float
    changed_targets: tuple[str, ...]
    blend_type: str
    model_ids: tuple[str, ...]
    weights: tuple[float, ...]
    runtime_seconds: float
    expected_information_gain: float

    def validate(self) -> None:
        if not self.candidate_id.strip():
            raise ContractError("candidate_id cannot be empty")
        if self.parent_submission_id != PROTECTED_CHAMPION_SUBMISSION_ID:
            raise ContractError("T137 candidates must descend from protected champion 55976422")
        if self.parent_score != PROTECTED_CHAMPION_SCORE:
            raise ContractError("T137 parent score must be the protected 0.929 champion")
        if not self.changed_targets:
            raise ContractError("candidate must change at least one target")
        if len(set(self.changed_targets)) != len(self.changed_targets):
            raise ContractError("changed_targets must be unique")
        if any(target not in TARGETS for target in self.changed_targets):
            raise ContractError("candidate contains an unknown target")
        if not self.model_ids:
            raise ContractError("candidate must include at least one model")
        if len(self.model_ids) != len(self.weights):
            raise ContractError("model_ids and weights must have equal length")
        if any(weight < 0.0 or not math.isfinite(weight) for weight in self.weights):
            raise ContractError("weights must be finite and nonnegative")
        if not math.isclose(sum(self.weights), 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ContractError("weights must sum to 1")
        if self.runtime_seconds < 0 or not math.isfinite(self.runtime_seconds):
            raise ContractError("runtime must be finite and nonnegative")
        if not math.isfinite(self.expected_information_gain):
            raise ContractError("expected_information_gain must be finite")


@dataclass(frozen=True, slots=True)
class FrozenRound:
    """A submission manifest prepared offline; it is never authorization itself."""

    round_id: str
    live_submission_allowance: int
    candidates: tuple[CandidateSpec, ...]
    reports_used: bool = False
    hidden_labels_used: bool = False
    network_enabled: bool = False
    submission_api_embedded: bool = False

    def validate(self) -> None:
        if not self.round_id.strip():
            raise ContractError("round_id cannot be empty")
        if self.live_submission_allowance < 0:
            raise ContractError("live_submission_allowance cannot be negative")
        if len(self.candidates) > 3:
            raise ContractError("T137 may freeze at most three candidates")
        if len(self.candidates) > self.live_submission_allowance:
            raise ContractError("candidate count exceeds live submission allowance")
        ids = [candidate.candidate_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ContractError("candidate IDs must be unique")
        for candidate in self.candidates:
            candidate.validate()
        if self.reports_used:
            raise ContractError("T137 cannot use reports")
        if self.hidden_labels_used:
            raise ContractError("T137 cannot use hidden labels")
        if self.network_enabled:
            raise ContractError("T137 inference must remain offline")
        if self.submission_api_embedded:
            raise ContractError("submission API calls cannot be embedded")

    def canonical_payload(self) -> dict[str, Any]:
        self.validate()
        return {
            "round_id": self.round_id,
            "live_submission_allowance": self.live_submission_allowance,
            "candidates": [
                {
                    "candidate_id": item.candidate_id,
                    "parent_submission_id": item.parent_submission_id,
                    "parent_score": item.parent_score,
                    "changed_targets": list(item.changed_targets),
                    "blend_type": item.blend_type,
                    "model_ids": list(item.model_ids),
                    "weights": list(item.weights),
                    "runtime_seconds": item.runtime_seconds,
                    "expected_information_gain": item.expected_information_gain,
                }
                for item in self.candidates
            ],
            "reports_used": self.reports_used,
            "hidden_labels_used": self.hidden_labels_used,
            "network_enabled": self.network_enabled,
            "submission_api_embedded": self.submission_api_embedded,
        }

    def sha256(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def authorization_request(round_manifest: FrozenRound) -> str:
    """Generate an exact, placeholder-free authorization request."""

    round_manifest.validate()
    count = len(round_manifest.candidates)
    if count == 0:
        raise ContractError("cannot request authorization for an empty round")
    digest = round_manifest.sha256()
    if count == 1:
        candidate_id = round_manifest.candidates[0].candidate_id
        return (
            "I authorize one Kaggle competition submission for campaign round "
            f"{round_manifest.round_id}, limited to candidate {candidate_id} in manifest {digest}. "
            "Keep all resources private, record the result, make no second submission, "
            "and stop after the score."
        )
    return (
        f"I authorize up to {count} Kaggle competition submissions for campaign round "
        f"{round_manifest.round_id}, limited to the predeclared candidates in {digest}. "
        "Keep all resources private, record every result, stop immediately if a score "
        "reaches 0.950, and make no other submissions."
    )


def parse_candidate(value: Mapping[str, Any]) -> CandidateSpec:
    """Parse one candidate from a JSON-compatible mapping."""

    changed_raw = value.get("changed_targets")
    model_raw = value.get("model_ids")
    weights_raw = value.get("weights")
    if not isinstance(changed_raw, Sequence) or isinstance(changed_raw, (str, bytes)):
        raise ContractError("changed_targets must be an array")
    if not isinstance(model_raw, Sequence) or isinstance(model_raw, (str, bytes)):
        raise ContractError("model_ids must be an array")
    if not isinstance(weights_raw, Sequence) or isinstance(weights_raw, (str, bytes)):
        raise ContractError("weights must be an array")
    candidate = CandidateSpec(
        candidate_id=str(value.get("candidate_id", "")),
        parent_submission_id=int(value.get("parent_submission_id", 0)),
        parent_score=float(value.get("parent_score", float("nan"))),
        changed_targets=tuple(str(item) for item in changed_raw),
        blend_type=str(value.get("blend_type", "")),
        model_ids=tuple(str(item) for item in model_raw),
        weights=tuple(float(item) for item in weights_raw),
        runtime_seconds=float(value.get("runtime_seconds", float("nan"))),
        expected_information_gain=float(
            value.get("expected_information_gain", float("nan"))
        ),
    )
    candidate.validate()
    return candidate
