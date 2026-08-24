"""Tests for model bundle packaging and output validation using temp files."""

from __future__ import annotations

import csv
import tarfile
import tempfile
from pathlib import Path

from package_model_bundle import package_bundle
from validate_model_output import validate_csv, validate_expected_keys

_VALID_HEADER = [
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


class TestPackageBundle:
    def test_creates_tar_with_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "model.yaml"
            config.write_text("model: baseline\n")
            out = Path(tmp) / "bundle.tar.gz"
            package_bundle(
                model_config_path=config,
                output_path=out,
                code_commit="abc123",
                config_hash="def456",
                preprocessing_version="v0",
            )
            with tarfile.open(out) as tar:
                names = tar.getnames()
                assert "provenance_manifest.json" in names
                assert "model_config.yaml" in names

    def test_deterministic_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "m.yaml"
            config.write_text("seed: 42\n")
            out = Path(tmp) / "b.tar.gz"
            package_bundle(
                model_config_path=config,
                output_path=out,
                code_commit="abc",
                config_hash="h",
                preprocessing_version="p",
            )
            manifest = Path(tmp) / "provenance_manifest.json"
            content1 = manifest.read_text()
            package_bundle(
                model_config_path=config,
                output_path=out,
                code_commit="abc",
                config_hash="h",
                preprocessing_version="p",
            )
            assert manifest.read_text() == content1


class TestValidateOutput:
    def _write(self, tmp: str, rows: list[list[str]]) -> Path:
        p = Path(tmp) / "preds.csv"
        with p.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(_VALID_HEADER)
            w.writerows(rows)
        return p

    def test_valid_csv_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, [["a" * 64] + ["0.5"] * 12])
            assert validate_csv(path) == []

    def test_missing_file_fails(self) -> None:
        assert validate_csv(Path("/nonexistent/preds.csv")) == ["file_not_found"]

    def test_bad_header_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.csv"
            p.write_text("wrong,columns\n")
            errors = validate_csv(p)
            assert "header_mismatch" in errors

    def test_out_of_range_value_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, [["a" * 64] + ["1.5"] + ["0.5"] * 11])
            assert any("out_of_range" in e for e in validate_csv(path))

    def test_invalid_study_key_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, [["short"] + ["0.5"] * 12])
            assert any("invalid_study_key" in e for e in validate_csv(path))

    def test_expected_keys_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, [["a" * 64] + ["0.5"] * 12])
            keys = Path(tmp) / "keys.txt"
            keys.write_text("a" * 64)
            assert validate_expected_keys(path, keys) == []

    def test_missing_key_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, [["a" * 64] + ["0.5"] * 12])
            keys = Path(tmp) / "keys.txt"
            keys.write_text("a" * 64 + "\n" + "b" * 64)
            errors = validate_expected_keys(path, keys)
            assert any("missing_keys" in e for e in errors)
