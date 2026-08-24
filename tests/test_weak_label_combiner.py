"""Tests for label-source combination using synthetic data only."""

from __future__ import annotations

import pytest

from rsna_knee.labels.combiner import LabelSource, combine_labels


def _src(st: str, confidence: float = 0.9, src_type: str = "rule_labeler") -> LabelSource:
    return LabelSource(
        source_type=src_type,
        state=st,
        confidence=confidence,
        evidence_summary="synthetic",
    )


class TestEmptySources:
    def test_empty_returns_not_mentioned_with_mask_false(self) -> None:
        result = combine_labels("Effusion", [])
        assert result.label_state == "not_mentioned"
        assert result.mask_status is False
        assert result.soft_probability == 0.0


class TestSingleSource:
    def test_single_positive(self) -> None:
        result = combine_labels("ACL", [_src("positive")])
        assert result.label_state == "positive"
        assert result.mask_status is True
        assert result.agreeing_sources == ("rule_labeler",)

    def test_single_negative(self) -> None:
        result = combine_labels("ACL", [_src("negative")])
        assert result.label_state == "negative"

    def test_not_mentioned_source_gives_mask_false(self) -> None:
        result = combine_labels("ACL", [_src("not_mentioned")])
        assert result.mask_status is False


class TestPriorityResolution:
    def test_organizer_beats_rule(self) -> None:
        sources = [_src("negative", src_type="organizer_label"), _src("positive")]
        result = combine_labels("ACL", sources)
        assert result.label_state == "negative"

    def test_human_review_beats_rule(self) -> None:
        sources = [_src("positive"), _src("negative", src_type="human_report_review")]
        result = combine_labels("ACL", sources)
        assert result.label_state == "negative"


class TestAgreementTracking:
    def test_agreeing_sources_listed(self) -> None:
        sources = [_src("positive"), _src("positive", src_type="classifier")]
        result = combine_labels("ACL", sources)
        assert set(result.agreeing_sources) == {"rule_labeler", "classifier"}
        assert result.conflicting_sources == ()

    def test_conflicting_sources_tracked(self) -> None:
        sources = [_src("positive"), _src("negative")]
        result = combine_labels("ACL", sources)
        assert len(result.conflicting_sources) >= 1
        assert len(result.agreeing_sources) >= 1


class TestSoftProbability:
    def test_all_positive_gives_high_soft_prob(self) -> None:
        sources = [_src("positive"), _src("positive", src_type="classifier")]
        result = combine_labels("ACL", sources)
        assert result.soft_probability > 0.8

    def test_mixed_sources_give_intermediate(self) -> None:
        sources = [_src("positive"), _src("negative", confidence=0.5)]
        result = combine_labels("ACL", sources)
        assert 0.3 < result.soft_probability < 0.9


class TestProvenance:
    def test_versions_bound_to_output(self) -> None:
        result = combine_labels(
            "ACL",
            [_src("positive")],
            ontology_version="provisional-v0",
            label_engine_version="weak-v0",
        )
        assert result.ontology_version == "provisional-v0"
        assert result.label_engine_version == "weak-v0"

    def test_invalid_state_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid_label_state"):
            combine_labels("ACL", [_src("garbage")])
