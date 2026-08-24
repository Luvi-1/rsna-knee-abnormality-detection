"""Annotation partition isolation.

Study keys are opaque hashes. This module never receives or stores identifiers
that could link a study back to a patient.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Partition(StrEnum):
    DEV = "dev"
    HOLDOUT = "holdout"
    GOLD = "gold"


@dataclass(frozen=True, slots=True)
class AnnotationPartition:
    study_key: str
    partition: Partition


def assign_partition(study_key: str, *, dev_fraction: float = 0.8) -> Partition:
    """Deterministically assign a study to dev or holdout using a stable hash prefix."""
    if not 0.0 < dev_fraction < 1.0:
        raise ValueError("dev_fraction must be in (0, 1)")
    if len(study_key) != 64 or any(c not in "0123456789abcdef" for c in study_key):
        raise ValueError("study_key must be a 64-char hex hash")
    # First 8 hex chars = 32 bits of entropy; sufficient for a deterministic split.
    bucket = int(study_key[:8], 16) / 0xFFFFFFFF
    return Partition.DEV if bucket < dev_fraction else Partition.HOLDOUT


def validate_partition_isolation(
    records: list[AnnotationPartition],
    *,
    gold_keys: frozenset[str],
) -> None:
    """Raise if any gold key appears outside the gold partition."""
    for rec in records:
        expected = Partition.GOLD if rec.study_key in gold_keys else rec.partition
        if rec.partition == Partition.GOLD and rec.study_key not in gold_keys:
            raise ValueError("unauthorized_gold_assignment")
        if rec.partition != expected:
            raise ValueError("partition_isolation_violation")
