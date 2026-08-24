"""Report normalization for weak-label extraction.

All operations are deterministic and produce no log output containing raw text.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class ReportSection(StrEnum):
    FINDINGS = "findings"
    IMPRESSION = "impression"
    INDICATION = "indication"
    TECHNIQUE = "technique"
    CLINICAL_HISTORY = "clinical_history"
    COMPARISON = "comparison"
    OTHER = "other"


SECTION_HEADERS: dict[str, ReportSection] = {
    "FINDINGS": ReportSection.FINDINGS,
    "IMPRESSION": ReportSection.IMPRESSION,
    "CONCLUSION": ReportSection.IMPRESSION,
    "INDICATION": ReportSection.INDICATION,
    "TECHNIQUE": ReportSection.TECHNIQUE,
    "CLINICAL HISTORY": ReportSection.CLINICAL_HISTORY,
    "HISTORY": ReportSection.CLINICAL_HISTORY,
    "COMPARISON": ReportSection.COMPARISON,
}

_WHITESPACE = re.compile(r"[\s\u00a0]+")
_HEADER_LINE = re.compile(r"^([A-Z][A-Z\s]{2,30}):", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class SectionSpan:
    section: ReportSection
    text: str
    start_offset: int
    end_offset: int


@dataclass(frozen=True, slots=True)
class NormalizedReport:
    sections: tuple[SectionSpan, ...]
    language: str  # ISO 639-1 code; interface only; actual detection is pluggable
    raw_length: int
    normalized_length: int


def normalize_unicode(text: str) -> str:
    """NFKC normalize and strip zero-width characters."""
    cleaned = unicodedata.normalize("NFKC", text)
    return "".join(c for c in cleaned if unicodedata.category(c) != "Cf")


def collapse_whitespace(text: str) -> str:
    """Collapse runs of whitespace to a single space, preserving paragraph breaks."""
    paragraphs = text.split("\n\n")
    collapsed = [_WHITESPACE.sub(" ", p).strip() for p in paragraphs]
    return "\n\n".join(p for p in collapsed if p)


def detect_sections(text: str) -> list[SectionSpan]:
    """Detect standard radiology report sections from header lines."""
    spans: list[SectionSpan] = []
    matches = list(_HEADER_LINE.finditer(text))
    if matches and matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            spans.append(SectionSpan(ReportSection.OTHER, preamble, 0, len(preamble)))
    if not matches:
        return [SectionSpan(ReportSection.OTHER, text, 0, len(text))]
    for i, match in enumerate(matches):
        header_text = match.group(1).strip().upper()
        section = SECTION_HEADERS.get(header_text, ReportSection.OTHER)
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        if body:
            spans.append(
                SectionSpan(
                    section=section,
                    text=body,
                    start_offset=body_start,
                    end_offset=body_end,
                )
            )
    return spans


def normalize_report(raw_text: str, *, language: str = "en") -> NormalizedReport:
    """Normalize a radiology report into sections without logging content."""
    unicode_cleaned = normalize_unicode(raw_text)
    collapsed = collapse_whitespace(unicode_cleaned)
    sections = tuple(detect_sections(collapsed))
    return NormalizedReport(
        sections=sections,
        language=language,
        raw_length=len(raw_text),
        normalized_length=len(collapsed),
    )
