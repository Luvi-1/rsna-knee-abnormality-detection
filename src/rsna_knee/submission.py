"""Submission schema validation without leaderboard side effects."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

from rsna_knee.competition_contract import load_competition_contract


class SubmissionValidationError(ValueError):
    """Raised when a submission violates the local contract."""


@dataclass(frozen=True)
class SubmissionSummary:
    rows: int


def validate_submission(path: Path, contract_config: Path) -> SubmissionSummary:
    """Validate exact columns, unique IDs, finite probabilities, and non-empty rows."""

    contract = load_competition_contract(contract_config)
    if path.name != contract.submission.filename:
        raise SubmissionValidationError(
            f"submission filename must be {contract.submission.filename}"
        )
    id_column = contract.targets.id_column
    labels = contract.targets.labels
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != contract.submission.columns:
            raise SubmissionValidationError("submission columns or order do not match the contract")
        for line_number, row in enumerate(reader, start=2):
            study_id = row[id_column].strip()
            if not study_id or study_id in seen:
                raise SubmissionValidationError(
                    f"invalid or duplicate study ID on line {line_number}"
                )
            seen.add(study_id)
            for label in labels:
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
