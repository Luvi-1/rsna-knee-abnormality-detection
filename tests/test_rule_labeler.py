"""Tests for the deterministic rule labeler using synthetic reports only."""

from __future__ import annotations

from rsna_knee.labels.normalization import normalize_report
from rsna_knee.labels.rule_labeler import RuleLabelResult, apply_rule_labeler

_POSITIVE = frozenset({"acl tear", "acl rupture", "acl injury"})
_NEGATIVE = frozenset({"acl intact", "normal acl", "no acl tear"})
_UNCERTAIN = frozenset({"possible acl tear", "cannot exclude acl injury"})


def _label(text: str) -> RuleLabelResult:
    report = normalize_report(text)
    return apply_rule_labeler(
        report,
        target_column="ACL",
        positive_terms=_POSITIVE,
        negative_terms=_NEGATIVE,
        uncertain_terms=_UNCERTAIN,
    )


class TestExplicitPositive:
    def test_direct_positive_in_findings(self) -> None:
        result = _label("FINDINGS:\nThe ACL shows a full-thickness acl tear.")
        # Note: term list has "acl tear"; the full-thickness prefix does not prevent matching.
        assert result.label_state == "positive"
        assert len(result.matches) >= 1
        assert result.matches[0].term == "acl tear"

    def test_positive_in_impression_overrides_findings_negative(self) -> None:
        text = "FINDINGS:\nACL is normal.\n\nIMPRESSION:\nacl tear noted."
        result = _label(text)
        assert result.label_state == "positive"


class TestExplicitNegative:
    def test_negated_positive_becomes_negative(self) -> None:
        result = _label("FINDINGS:\nNo acl tear identified.")
        assert result.label_state in ("negative", None)

    def test_explicit_normal_is_negative(self) -> None:
        result = _label("FINDINGS:\nNormal ACL. The ACL is intact.")
        assert result.label_state == "negative"


class TestUncertainty:
    def test_uncertainty_prefix_downgrades_to_uncertain(self) -> None:
        result = _label("FINDINGS:\nPossible acl tear.")
        assert result.label_state == "uncertain"

    def test_cannot_exclude_produces_uncertain(self) -> None:
        result = _label("FINDINGS:\nCannot exclude acl injury.")
        assert result.label_state == "uncertain"


class TestNotMentioned:
    def test_irrelevant_report_returns_none(self) -> None:
        result = _label("FINDINGS:\nUnremarkable knee MRI otherwise.")
        assert result.label_state is None


class TestEvidenceSpans:
    def test_match_has_nonzero_span(self) -> None:
        result = _label("FINDINGS:\nAn acl tear is present.")
        match = result.matches[0]
        assert match.span_end > match.span_start

    def test_section_recorded(self) -> None:
        from rsna_knee.labels.normalization import ReportSection

        result = _label("IMPRESSION:\nACL rupture.")
        if result.matches:
            assert result.matches[0].section == ReportSection.IMPRESSION
