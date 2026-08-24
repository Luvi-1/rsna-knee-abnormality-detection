"""Deterministic rule-based labeler driven by the provisional ontology.

Applies positive/negative/uncertain term lists with negation scope, section priority,
and evidence-span extraction. No private data required; all tests use synthetic reports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from rsna_knee.labels.normalization import NormalizedReport, ReportSection

LabelState = Literal["positive", "negative", "uncertain"]


@dataclass(frozen=True, slots=True)
class TermMatch:
    term: str
    state: LabelState
    section: ReportSection
    span_start: int
    span_end: int


@dataclass(frozen=True, slots=True)
class RuleLabelResult:
    target_column: str
    label_state: LabelState | None  # None means not_mentioned
    confidence: float
    matches: tuple[TermMatch, ...]


# Negation cues that invert the scope of the following phrase within one sentence/clause.
_NEGATION_PATTERNS = [
    re.compile(r"\bno\b", re.IGNORECASE),
    re.compile(r"\bnot\s+(?:seen|demonstrated|identified|present)\b", re.IGNORECASE),
    re.compile(r"\bwithout\b", re.IGNORECASE),
    re.compile(r"\bfree of\b", re.IGNORECASE),
    re.compile(r"\babsent\b", re.IGNORECASE),
    re.compile(r"\bunremarkable\b", re.IGNORECASE),
]

_UNCERTAINTY_PREFIXES = [
    re.compile(r"\bpossible\b", re.IGNORECASE),
    re.compile(r"\bcannot\s+(?:exclude|rule\s+out)\b", re.IGNORECASE),
    re.compile(r"\bquestionable\b", re.IGNORECASE),
    re.compile(r"\bequivocal\b", re.IGNORECASE),
    re.compile(r"\bsuspect(?:ed)?\b", re.IGNORECASE),
    re.compile(r"\bprobable\b", re.IGNORECASE),
    re.compile(r"\blikely\b", re.IGNORECASE),
    re.compile(r"\bmay\s+represent\b", re.IGNORECASE),
]

# Impression overrides findings when they conflict.
_SECTION_PRIORITY: dict[ReportSection, int] = {
    ReportSection.IMPRESSION: 3,
    ReportSection.FINDINGS: 2,
    ReportSection.CLINICAL_HISTORY: 0,
    ReportSection.TECHNIQUE: 0,
    ReportSection.COMPARISON: 0,
    ReportSection.INDICATION: 0,
    ReportSection.OTHER: 1,
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[tuple[int, str]]:
    sentences: list[tuple[int, str]] = []
    pos = 0
    for part in _SENTENCE_SPLIT.split(text):
        stripped = part.strip()
        if stripped:
            offset = text.find(stripped, pos)
            sentences.append((offset, stripped))
            pos = offset + len(stripped)
    return sentences


def _detect_negation(sentence: str, match_start: int) -> bool:
    """Check whether any negation cue appears before the match in the same sentence."""
    prefix = sentence[:match_start]
    return any(pattern.search(prefix) for pattern in _NEGATION_PATTERNS)


def _detect_uncertainty(sentence: str, match_start: int) -> bool:
    prefix = sentence[:match_start]
    return any(pattern.search(prefix) for pattern in _UNCERTAINTY_PREFIXES)


def apply_rule_labeler(
    report: NormalizedReport,
    *,
    target_column: str,
    positive_terms: frozenset[str],
    negative_terms: frozenset[str],
    uncertain_terms: frozenset[str],
) -> RuleLabelResult:
    """Apply ontology-driven term matching to a normalized report for one target."""
    all_matches: list[TermMatch] = []
    for section_span in report.sections:
        sentences = _split_sentences(section_span.text)
        for sent_offset, sentence in sentences:
            lower_sentence = sentence.lower()
            term_sets: tuple[tuple[LabelState, frozenset[str]], ...] = (
                ("positive", positive_terms),
                ("negative", negative_terms),
                ("uncertain", uncertain_terms),
            )
            for state, terms in term_sets:
                for term in terms:
                    idx = lower_sentence.find(term.lower())
                    while idx != -1:
                        abs_start = section_span.start_offset + sent_offset + idx
                        abs_end = abs_start + len(term)
                        is_negated = _detect_negation(sentence, idx)
                        is_uncertain = _detect_uncertainty(sentence, idx)
                        effective_state: LabelState
                        if is_negated:
                            effective_state = "negative"
                        elif is_uncertain:
                            effective_state = "uncertain"
                        else:
                            effective_state = state
                        all_matches.append(
                            TermMatch(
                                term=term,
                                state=effective_state,
                                section=section_span.section,
                                span_start=abs_start,
                                span_end=abs_end,
                            )
                        )
                        idx = lower_sentence.find(term.lower(), idx + 1)

    if not all_matches:
        return RuleLabelResult(
            target_column=target_column, label_state=None, confidence=1.0, matches=()
        )

    # Resolve conflicts by section priority (impression > findings > other), then by latest match.
    priority_sorted = sorted(
        all_matches,
        key=lambda m: (_SECTION_PRIORITY.get(m.section, 0), m.span_start),
        reverse=True,
    )
    final_state = priority_sorted[0].state
    agreeing = sum(1 for m in priority_sorted if m.state == final_state)
    total = len(priority_sorted)
    confidence = agreeing / total if total > 0 else 0.5
    return RuleLabelResult(
        target_column=target_column,
        label_state=final_state,
        confidence=confidence,
        matches=tuple(all_matches),
    )
