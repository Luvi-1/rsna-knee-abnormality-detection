"""Tests for annotation partition isolation using synthetic hashed keys."""

from __future__ import annotations

import pytest

from rsna_knee.annotation.partitioning import (
    AnnotationPartition,
    Partition,
    assign_partition,
    validate_partition_isolation,
)

_DEV_KEY = "a" * 64
_HOLDOUT_KEY = "f" * 64
_GOLD_KEY = "b" * 64


class TestAssignPartition:
    def test_low_hash_goes_to_dev(self) -> None:
        assert assign_partition(_DEV_KEY) == Partition.DEV

    def test_high_hash_goes_to_holdout(self) -> None:
        assert assign_partition(_HOLDOUT_KEY) == Partition.HOLDOUT

    def test_deterministic_repeat_call(self) -> None:
        assert assign_partition(_DEV_KEY) == assign_partition(_DEV_KEY)

    def test_invalid_fraction_raises(self) -> None:
        with pytest.raises(ValueError, match="dev_fraction"):
            assign_partition(_DEV_KEY, dev_fraction=0.0)

    def test_invalid_key_raises(self) -> None:
        with pytest.raises(ValueError, match="study_key"):
            assign_partition("not-a-hash")


class TestPartitionIsolation:
    def test_gold_key_in_gold_partition_passes(self) -> None:
        records = [AnnotationPartition(study_key=_GOLD_KEY, partition=Partition.GOLD)]
        validate_partition_isolation(records, gold_keys=frozenset({_GOLD_KEY}))

    def test_unauthorized_gold_assignment_raises(self) -> None:
        records = [AnnotationPartition(study_key=_DEV_KEY, partition=Partition.GOLD)]
        with pytest.raises(ValueError, match="unauthorized_gold"):
            validate_partition_isolation(records, gold_keys=frozenset())

    def test_gold_key_outside_gold_raises(self) -> None:
        records = [AnnotationPartition(study_key=_GOLD_KEY, partition=Partition.DEV)]
        with pytest.raises(ValueError, match="isolation_violation"):
            validate_partition_isolation(records, gold_keys=frozenset({_GOLD_KEY}))
