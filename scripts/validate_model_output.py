#!/usr/bin/env python3
"""Validate a prediction CSV against the competition schema without private data."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_EXPECTED_COLUMNS = [
    "study_key",
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
]


def validate_csv(path: Path) -> list[str]:
    """Return a list of validation errors (empty = valid)."""
    errors: list[str] = []
    if not path.exists():
        return ["file_not_found"]
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header != _EXPECTED_COLUMNS:
            errors.append("header_mismatch")
            return errors
        for i, row in enumerate(reader):
            if len(row) != len(_EXPECTED_COLUMNS):
                errors.append(f"row_{i}_column_count")
                continue
            key = row[0]
            if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
                errors.append(f"row_{i}_invalid_study_key")
            for col_idx, cell in enumerate(row[1:], start=1):
                try:
                    val = float(cell)
                    if not 0.0 <= val <= 1.0:
                        errors.append(f"row_{i}_col_{col_idx}_out_of_range")
                except ValueError:
                    errors.append(f"row_{i}_col_{col_idx}_not_numeric")
    return errors


def validate_expected_keys(path: Path, expected_keys_path: Path) -> list[str]:
    """Check that every expected study key is present exactly once."""
    base_errors = validate_csv(path)
    if base_errors:
        return base_errors

    if not expected_keys_path.exists():
        return ["expected_keys_file_not_found"]

    expected = set(expected_keys_path.read_text(encoding="utf-8").strip().splitlines())
    seen: list[str] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            if row:
                seen.append(row[0])

    from collections import Counter

    counts = Counter(seen)
    missing = expected - set(seen)
    extra = set(seen) - expected
    duplicated = {k for k, v in counts.items() if v > 1}

    errors: list[str] = []
    if missing:
        errors.append(f"missing_keys:{len(missing)}")
    if extra:
        errors.append(f"extra_keys:{len(extra)}")
    if duplicated:
        errors.append(f"duplicate_keys:{len(duplicated)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    args = parser.parse_args()

    errors = validate_csv(args.csv_path)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("valid", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
