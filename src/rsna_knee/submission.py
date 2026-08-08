"""Submission schema validation without leaderboard side effects."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

LABELS = (
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
EXPECTED_COLUMNS = ("StudyInstanceUID", *LABELS)


class SubmissionValidationError(ValueError):
    """Raised when a submission violates the local contract."""


@dataclass(frozen=True)
class SubmissionSummary:
    rows: int


def validate_submission(path: Path) -> SubmissionSummary:
    """Validate exact columns, unique IDs, finite probabilities, and non-empty rows."""

    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
            raise SubmissionValidationError("submission columns or order do not match the contract")
        for line_number, row in enumerate(reader, start=2):
            study_id = row["StudyInstanceUID"].strip()
            if not study_id or study_id in seen:
                raise SubmissionValidationError(
                    f"invalid or duplicate study ID on line {line_number}"
                )
            seen.add(study_id)
            for label in LABELS:
                try:
                    value = float(row[label])
                except (TypeError, ValueError) as error:
                    raise SubmissionValidationError(
                        f"non-numeric {label} value on line {line_number}"
                    ) from error
                if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                    raise SubmissionValidationError(
                        f"out-of-range {label} value on line {line_number}"
                    )
    if not seen:
        raise SubmissionValidationError("submission has no prediction rows")
    return SubmissionSummary(rows=len(seen))
