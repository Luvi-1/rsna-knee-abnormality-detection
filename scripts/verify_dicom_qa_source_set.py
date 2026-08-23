from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

HEX_64: Final = re.compile(r"[0-9a-f]{64}\Z")
KERNEL_REF: Final = re.compile(r"[a-z0-9][a-z0-9_-]{0,49}/[a-z0-9][a-z0-9_-]{0,99}\Z")
SOURCE_ROLES: Final = frozenset({"run_a", "run_b"})
DETERMINISTIC_FIELDS: Final = {
    "comparison_code_hash_match": True,
    "comparison_output_inventory_match": True,
    "deterministic_summary_status": "PASS",
    "private": True,
    "internet_disabled": True,
    "comparison_version": 1,
    "before_after_source_metadata_stable": True,
    "every_other_available_comparison_field_passed": True,
}


class SourceSetError(RuntimeError):
    """Fixed failure with no source identity in its message."""


def _canonical_source(value: object) -> tuple[str, str, int, str]:
    if not isinstance(value, Mapping) or set(value) != {
        "role",
        "ref",
        "version",
        "code_sha256_bytes",
    }:
        raise SourceSetError("source_record_invalid")
    role = value.get("role")
    ref = value.get("ref")
    version = value.get("version")
    digest_bytes = value.get("code_sha256_bytes")
    if (
        role not in SOURCE_ROLES
        or not isinstance(ref, str)
        or KERNEL_REF.fullmatch(ref) is None
        or isinstance(version, bool)
        or version != 1
        or not isinstance(digest_bytes, list)
        or len(digest_bytes) != 32
        or any(
            isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 255
            for item in digest_bytes
        )
    ):
        raise SourceSetError("source_record_invalid")
    digest = bytes(cast(list[int], digest_bytes)).hex()
    if HEX_64.fullmatch(digest) is None:
        raise SourceSetError("source_record_invalid")
    return cast(str, role), ref, cast(int, version), digest


def _source_set(value: object) -> frozenset[tuple[str, str, int, str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise SourceSetError("source_count_invalid")
    records = tuple(_canonical_source(item) for item in value)
    if (
        len(set(records)) != 2
        or len({item[0] for item in records}) != 2
        or len({item[1] for item in records}) != 2
    ):
        raise SourceSetError("duplicate_source_invalid")
    return frozenset(records)


def verify_evidence(value: object) -> None:
    """Require one exact, duplicate-free Run A/Run B set; list order is nonsemantic."""

    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "artifact_type",
        "ordered_source_validator",
        "expected_sources",
        "observed_sources",
        "deterministic_comparison",
    }:
        raise SourceSetError("evidence_schema_invalid")
    comparison = value.get("deterministic_comparison")
    if (
        value.get("schema_version") != 1
        or value.get("artifact_type") != "r16-sanitized-source-set-evidence"
        or value.get("ordered_source_validator") != "FAIL"
        or not isinstance(comparison, Mapping)
        or dict(comparison) != DETERMINISTIC_FIELDS
        or _source_set(value.get("expected_sources")) != _source_set(value.get("observed_sources"))
    ):
        raise SourceSetError("source_set_verification_failed")


def _read_evidence(path: Path) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 64 * 1024:
            raise SourceSetError("evidence_file_invalid")
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SourceSetError("evidence_file_invalid") from error
    if not isinstance(value, dict):
        raise SourceSetError("evidence_file_invalid")
    return cast(dict[str, Any], value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    print("ordered_source_validator = FAIL")
    try:
        verify_evidence(_read_evidence(arguments.evidence))
    except SourceSetError:
        print("exact_duplicate_free_source_set_verifier = FAIL")
        return 2
    print("exact_duplicate_free_source_set_verifier = PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
