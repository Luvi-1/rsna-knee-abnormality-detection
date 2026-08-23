from __future__ import annotations

import importlib.util
import random
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify_dicom_qa_source_set.py"


def _load() -> ModuleType:
    specification = importlib.util.spec_from_file_location("_source_set_verifier", SCRIPT)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


verifier = _load()


def _source(role: str, suffix: str, digest: str) -> dict[str, object]:
    return {
        "role": role,
        "ref": f"test-owner/source-{suffix}",
        "version": 1,
        "code_sha256_bytes": list(bytes.fromhex(digest * 64)),
    }


def _evidence() -> dict[str, Any]:
    run_a = _source("run_a", "a", "a")
    run_b = _source("run_b", "b", "b")
    return {
        "schema_version": 1,
        "artifact_type": "r16-sanitized-source-set-evidence",
        "ordered_source_validator": "FAIL",
        "expected_sources": [run_a, run_b],
        "observed_sources": [deepcopy(run_b), deepcopy(run_a)],
        "deterministic_comparison": dict(verifier.DETERMINISTIC_FIELDS),
    }


def test_reverse_order_passes() -> None:
    verifier.verify_evidence(_evidence())


def test_duplicate_source_fails() -> None:
    value = _evidence()
    value["observed_sources"] = [value["observed_sources"][0]] * 2
    with pytest.raises(verifier.SourceSetError):
        verifier.verify_evidence(value)


def test_missing_source_fails() -> None:
    value = _evidence()
    value["observed_sources"] = value["observed_sources"][:1]
    with pytest.raises(verifier.SourceSetError):
        verifier.verify_evidence(value)


def test_unexpected_third_source_fails() -> None:
    value = _evidence()
    value["observed_sources"].append(_source("run_a", "unexpected", "c"))
    with pytest.raises(verifier.SourceSetError):
        verifier.verify_evidence(value)


def test_correct_names_with_wrong_hash_fail() -> None:
    value = _evidence()
    value["observed_sources"][0]["code_sha256_bytes"][0] = 0
    with pytest.raises(verifier.SourceSetError):
        verifier.verify_evidence(value)


def test_correct_hash_with_wrong_version_fails() -> None:
    value = _evidence()
    value["observed_sources"][0]["version"] = 2
    with pytest.raises(verifier.SourceSetError):
        verifier.verify_evidence(value)


def test_same_order_passes() -> None:
    value = _evidence()
    value["observed_sources"] = deepcopy(value["expected_sources"])
    verifier.verify_evidence(value)


def test_repeated_random_permutations_are_deterministic() -> None:
    generator = random.Random(20260823)
    value = _evidence()
    for _ in range(100):
        generator.shuffle(value["observed_sources"])
        verifier.verify_evidence(value)
