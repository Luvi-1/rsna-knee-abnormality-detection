"""Contracts for screening public RSNA Knee inference baselines.

This module is deliberately network-free. It validates evidence collected from
official Kaggle metadata and prevents source-reported leaderboard scores from
being represented as project scores.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ContractError(ValueError):
    """Raised when a public-baseline record violates the evidence contract."""


class InferenceClassification(StrEnum):
    """Reproducibility class for a public candidate."""

    INFERENCE_AND_TRAINING_REPRODUCIBLE = "INFERENCE_AND_TRAINING_REPRODUCIBLE"
    INFERENCE_REPRODUCIBLE_TRAINING_OPAQUE = "INFERENCE_REPRODUCIBLE_TRAINING_OPAQUE"
    INFERENCE_BLOCKED = "INFERENCE_BLOCKED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


class LicenseClassification(StrEnum):
    """Actionable interpretation of the asset's actual terms."""

    PERMITS_COMPETITION_INFERENCE = "PERMITS_COMPETITION_INFERENCE"
    PERMITS_RESEARCH_ONLY = "PERMITS_RESEARCH_ONLY"
    NONCOMMERCIAL_ONLY = "NONCOMMERCIAL_ONLY"
    REDISTRIBUTION_RESTRICTED = "REDISTRIBUTION_RESTRICTED"
    CUSTOM_PERMISSION_REQUIRED = "CUSTOM_PERMISSION_REQUIRED"
    NO_ACTIONABLE_LICENSE = "NO_ACTIONABLE_LICENSE"
    CONFLICTING_TERMS = "CONFLICTING_TERMS"
    UNVERIFIED = "UNVERIFIED"


class ScoreType(StrEnum):
    """Source and meaning of a score."""

    SOURCE_REPORTED_PUBLIC_LB = "SOURCE_REPORTED_PUBLIC_LB"
    PROJECT_PUBLIC_LB = "PROJECT_PUBLIC_LB"
    PRIVATE_LB = "PRIVATE_LB"
    OOF = "OOF"
    PUBLIC_EXAMPLE_CONTRACT = "PUBLIC_EXAMPLE_CONTRACT"


@dataclass(frozen=True, slots=True)
class AssetRecord:
    """One exact external input needed by a candidate."""

    resource: str
    version: str | None
    sha256: str | None
    public: bool
    available: bool
    license_classification: LicenseClassification
    inference_required: bool
    safe_load: bool
    exact_binding: bool
    notes: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> AssetRecord:
        return cls(
            resource=_required_text(value, "resource"),
            version=_optional_text(value.get("version")),
            sha256=_optional_text(value.get("sha256")),
            public=_required_bool(value, "public"),
            available=_required_bool(value, "available"),
            license_classification=LicenseClassification(
                _required_text(value, "license_classification")
            ),
            inference_required=_required_bool(value, "inference_required"),
            safe_load=_required_bool(value, "safe_load"),
            exact_binding=_required_bool(value, "exact_binding"),
            notes=str(value.get("notes", "")),
        )

    def blockers(self) -> tuple[str, ...]:
        """Return inference blockers for this asset."""

        if not self.inference_required:
            return ()

        blockers: list[str] = []
        if not self.available:
            blockers.append("unavailable")
        if not self.public:
            blockers.append("not_public")
        if not self.version:
            blockers.append("version_unpinned")
        if not self.exact_binding:
            blockers.append("file_binding_unresolved")
        if not self.sha256 or not is_sha256(self.sha256):
            blockers.append("checksum_unverified")
        if self.license_classification is not LicenseClassification.PERMITS_COMPETITION_INFERENCE:
            blockers.append(f"license:{self.license_classification.value}")
        if not self.safe_load:
            blockers.append("unsafe_or_unverified_load")
        return tuple(blockers)


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    """Evidence record for one immutable public notebook candidate."""

    candidate_id: str
    owner_slug: str
    version: int | None
    script_version_id: int | None
    source_score: float | None
    score_type: ScoreType
    runtime_seconds: float | None
    source_sha256: str | None
    output_sha256: str | None
    saved_version: bool
    public_access: bool
    exact_output_available: bool
    dynamic_test_discovery: bool
    accesses_test_reports: bool
    calls_submission_api: bool
    training_lineage_complete: bool
    source_url: str
    captured_at: str
    assets: tuple[AssetRecord, ...]
    notes: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> CandidateRecord:
        assets_raw = value.get("assets", [])
        if not isinstance(assets_raw, list):
            raise ContractError("assets must be a list")
        candidate = cls(
            candidate_id=_required_text(value, "candidate_id"),
            owner_slug=_required_text(value, "owner_slug"),
            version=_optional_int(value.get("version")),
            script_version_id=_optional_int(value.get("script_version_id")),
            source_score=_optional_float(value.get("source_score")),
            score_type=ScoreType(_required_text(value, "score_type")),
            runtime_seconds=_optional_float(value.get("runtime_seconds")),
            source_sha256=_optional_text(value.get("source_sha256")),
            output_sha256=_optional_text(value.get("output_sha256")),
            saved_version=_required_bool(value, "saved_version"),
            public_access=_required_bool(value, "public_access"),
            exact_output_available=_required_bool(value, "exact_output_available"),
            dynamic_test_discovery=_required_bool(value, "dynamic_test_discovery"),
            accesses_test_reports=_required_bool(value, "accesses_test_reports"),
            calls_submission_api=_required_bool(value, "calls_submission_api"),
            training_lineage_complete=_required_bool(value, "training_lineage_complete"),
            source_url=_required_text(value, "source_url"),
            captured_at=_required_text(value, "captured_at"),
            assets=tuple(AssetRecord.from_mapping(item) for item in assets_raw),
            notes=str(value.get("notes", "")),
        )
        candidate.validate()
        return candidate

    def validate(self) -> None:
        """Validate intrinsic candidate fields."""

        if "/" not in self.owner_slug:
            raise ContractError(f"{self.candidate_id}: owner_slug must be owner/slug")
        if self.version is not None and self.version < 1:
            raise ContractError(f"{self.candidate_id}: version must be positive")
        if self.script_version_id is not None and self.script_version_id < 1:
            raise ContractError(f"{self.candidate_id}: script_version_id must be positive")
        if self.source_score is not None and not 0.0 <= self.source_score <= 1.0:
            raise ContractError(f"{self.candidate_id}: score outside [0, 1]")
        if self.runtime_seconds is not None and self.runtime_seconds < 0.0:
            raise ContractError(f"{self.candidate_id}: runtime cannot be negative")
        for field_name, digest in (
            ("source_sha256", self.source_sha256),
            ("output_sha256", self.output_sha256),
        ):
            if digest is not None and not is_sha256(digest):
                raise ContractError(
                    f"{self.candidate_id}: {field_name} must be a 64-character SHA-256"
                )

    def inference_blockers(self) -> tuple[str, ...]:
        """Return all reasons the candidate is not ready for private reproduction."""

        blockers: list[str] = []
        if not self.public_access:
            blockers.append("source_not_public")
        if not self.saved_version:
            blockers.append("immutable_saved_version_missing")
        if self.version is None or self.script_version_id is None:
            blockers.append("exact_version_unpinned")
        if not self.source_sha256:
            blockers.append("source_checksum_unverified")
        if not self.exact_output_available or not self.output_sha256:
            blockers.append("public_reference_output_unverified")
        if not self.dynamic_test_discovery:
            blockers.append("dynamic_test_discovery_unverified")
        if self.accesses_test_reports:
            blockers.append("test_report_access")
        if self.calls_submission_api:
            blockers.append("submission_api_call_present")

        for asset in self.assets:
            for blocker in asset.blockers():
                blockers.append(f"asset:{asset.resource}:{blocker}")
        return tuple(dict.fromkeys(blockers))

    def classification(self) -> InferenceClassification:
        """Classify inference and training reproducibility."""

        if not self.public_access:
            return InferenceClassification.SOURCE_UNAVAILABLE
        if self.inference_blockers():
            return InferenceClassification.INFERENCE_BLOCKED
        if self.training_lineage_complete:
            return InferenceClassification.INFERENCE_AND_TRAINING_REPRODUCIBLE
        return InferenceClassification.INFERENCE_REPRODUCIBLE_TRAINING_OPAQUE

    def eligible_for_private_reproduction(self, minimum_score: float = 0.90) -> bool:
        """Return whether the candidate can be reproduced as an inference candidate."""

        return (
            self.source_score is not None
            and self.source_score >= minimum_score
            and self.score_type is ScoreType.SOURCE_REPORTED_PUBLIC_LB
            and self.classification()
            in {
                InferenceClassification.INFERENCE_AND_TRAINING_REPRODUCIBLE,
                InferenceClassification.INFERENCE_REPRODUCIBLE_TRAINING_OPAQUE,
            }
        )


@dataclass(frozen=True, slots=True)
class ClaimBoundary:
    """Prevent third-party scores from being described as project results."""

    owner_slug: str
    source_score: float
    source_score_type: ScoreType
    project_submission_performed: bool
    project_public_score: float | None = None
    project_private_score: float | None = None
    project_oof_score: float | None = None

    def validate(self) -> None:
        if self.source_score_type is not ScoreType.SOURCE_REPORTED_PUBLIC_LB:
            raise ContractError("source_score must be marked SOURCE_REPORTED_PUBLIC_LB")
        if not 0.0 <= self.source_score <= 1.0:
            raise ContractError("source_score outside [0, 1]")
        if not self.project_submission_performed and (
            self.project_public_score is not None or self.project_private_score is not None
        ):
            raise ContractError("project leaderboard scores require a project submission")

    def summary(self) -> str:
        self.validate()
        source = (
            f"{self.owner_slug} has a source-reported public leaderboard score "
            f"of {self.source_score:.3f}."
        )
        if not self.project_submission_performed:
            return source + " This project has not independently submitted or achieved that score."
        if self.project_public_score is None:
            return source + (
                " A project submission occurred, but no verified public score is recorded."
            )
        return source + f" The project independently verified {self.project_public_score:.3f}."


def select_highest_eligible(
    candidates: Iterable[CandidateRecord], minimum_score: float = 0.90
) -> CandidateRecord | None:
    """Select the highest-scoring inference-eligible candidate deterministically."""

    eligible = [
        candidate
        for candidate in candidates
        if candidate.eligible_for_private_reproduction(minimum_score)
    ]
    if not eligible:
        return None
    eligible.sort(
        key=lambda item: (
            -(item.source_score if item.source_score is not None else -1.0),
            item.runtime_seconds if item.runtime_seconds is not None else float("inf"),
            item.candidate_id,
        )
    )
    return eligible[0]


def load_registry(path: str | Path) -> tuple[CandidateRecord, ...]:
    """Load and validate a candidate registry."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("candidates"), list):
        raise ContractError("registry must contain a candidates list")
    candidates = tuple(CandidateRecord.from_mapping(item) for item in raw["candidates"])
    ids = [candidate.candidate_id for candidate in candidates]
    if len(ids) != len(set(ids)):
        raise ContractError("candidate_id values must be unique")
    return candidates


def registry_summary(candidates: Sequence[CandidateRecord]) -> dict[str, Any]:
    """Return a JSON-serializable screening summary."""

    selected = select_highest_eligible(candidates)
    return {
        "candidate_count": len(candidates),
        "eligible_count": sum(
            candidate.eligible_for_private_reproduction() for candidate in candidates
        ),
        "selected_candidate_id": selected.candidate_id if selected else None,
        "candidates": [
            {
                "candidate_id": candidate.candidate_id,
                "classification": candidate.classification().value,
                "source_score": candidate.source_score,
                "blockers": list(candidate.inference_blockers()),
            }
            for candidate in candidates
        ],
    }


def is_sha256(value: str) -> bool:
    """Return whether value is a canonical lower-case SHA-256 digest."""

    return bool(_SHA256_RE.fullmatch(value))


def _required_text(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ContractError(f"{key} must be a non-empty string")
    return item.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ContractError("optional text must be null or non-empty")
    return value.strip()


def _required_bool(value: Mapping[str, Any], key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise ContractError(f"{key} must be boolean")
    return item


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError("optional integer must be null or an integer")
    return value


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContractError("optional float must be null or numeric")
    return float(value)
