"""Configurable label-source combination framework.

Combines rule labeler, classifier, template propagation, and organizer labels into
one four-state output with provenance. Rejects unsupported positives.
"""

from __future__ import annotations

from dataclasses import dataclass

LabelState = str  # "positive" | "negative" | "uncertain" | "not_mentioned"

_VALID_STATES = frozenset({"positive", "negative", "uncertain", "not_mentioned"})

# Source priority for conflict resolution. Higher wins.
_SOURCE_PRIORITY: dict[str, int] = {
    "organizer_label": 4,
    "human_report_review": 3,
    "rule_labeler": 2,
    "classifier": 1,
    "template_propagation": 0,
}


@dataclass(frozen=True, slots=True)
class LabelSource:
    source_type: str
    state: LabelState
    confidence: float
    evidence_summary: str  # sanitized; no raw report text


@dataclass(frozen=True, slots=True)
class CombinedLabel:
    target_column: str
    soft_probability: float
    label_state: LabelState
    mask_status: bool  # True = usable as supervision signal (not not_mentioned)
    confidence: float
    agreeing_sources: tuple[str, ...]
    conflicting_sources: tuple[str, ...]
    language: str
    ontology_version: str
    label_engine_version: str
    evidence_provenance: tuple[str, ...]


def combine_labels(
    target_column: str,
    sources: list[LabelSource],
    *,
    ontology_version: str = "provisional-v0",
    label_engine_version: str = "weak-v0",
    language: str = "en",
) -> CombinedLabel:
    """Combine label sources with configurable priority and agreement tracking."""
    if not sources:
        return CombinedLabel(
            target_column=target_column,
            soft_probability=0.0,
            label_state="not_mentioned",
            mask_status=False,
            confidence=1.0,
            agreeing_sources=(),
            conflicting_sources=(),
            language=language,
            ontology_version=ontology_version,
            label_engine_version=label_engine_version,
            evidence_provenance=(),
        )

    valid_sources = [s for s in sources if s.state in _VALID_STATES]
    if len(valid_sources) != len(sources):
        raise ValueError("invalid_label_state_in_source")

    # Sort by descending priority, then by descending confidence within same priority.
    sorted_sources = sorted(
        valid_sources, key=lambda s: (-_SOURCE_PRIORITY.get(s.source_type, -1), -s.confidence)
    )
    top = sorted_sources[0]

    agreeing = [s for s in sorted_sources if s.state == top.state]
    conflicting = [s for s in sorted_sources if s.state != top.state]

    # Soft probability from weighted vote of positive vs negative signals.
    pos_weight = sum(
        s.confidence * max(_SOURCE_PRIORITY.get(s.source_type, 0), 0)
        for s in valid_sources
        if s.state == "positive"
    )
    neg_weight = sum(
        s.confidence * max(_SOURCE_PRIORITY.get(s.source_type, 0), 0)
        for s in valid_sources
        if s.state == "negative"
    )
    total_weight = pos_weight + neg_weight
    soft_prob = pos_weight / total_weight if total_weight > 0 else 0.5

    return CombinedLabel(
        target_column=target_column,
        soft_probability=soft_prob,
        label_state=top.state,
        mask_status=(top.state != "not_mentioned"),
        confidence=top.confidence,
        agreeing_sources=tuple(s.source_type for s in agreeing),
        conflicting_sources=tuple(s.source_type for s in conflicting),
        language=language,
        ontology_version=ontology_version,
        label_engine_version=label_engine_version,
        evidence_provenance=tuple(s.evidence_summary for s in valid_sources),
    )
