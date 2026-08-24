"""Focused tests for the real-data gate and its packaging."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys_path = Path(__file__).resolve().parents[1] / "kaggle" / "model_baseline"
sys.path.insert(0, str(sys_path))

import package_real_data_gate as packager  # noqa: E402
import real_data_gate as gate  # noqa: E402


class TestGroupedFolds:
    def test_deterministic_and_balanced(self) -> None:
        keys = [f"study-{i:03d}" for i in range(20)]
        rng = np.random.default_rng(7)
        labels = (rng.random((20, 12)) > 0.7).astype(np.float64)
        first = gate.assign_grouped_folds(keys, labels)
        second = gate.assign_grouped_folds(keys, labels)
        assert first == second
        sizes = [0] * gate.N_SPLITS
        for _key, fold in first[0].items():
            sizes[fold] += 1
        assert all(size >= 2 for size in sizes)

    def test_duplicate_key_rejected(self) -> None:
        with pytest.raises(gate.GateError, match="fold_shape_invalid"):
            gate.assign_grouped_folds(["a"], np.zeros((2, 12)))

    def test_zero_mass_round_robin(self) -> None:
        """Zero-mass studies spread across folds instead of collapsing into fold 0."""
        keys = [f"study-{i:02d}" for i in range(10)]
        labels = np.zeros((10, 12), dtype=np.float64)
        assignments, _ = gate.assign_grouped_folds(keys, labels)
        sizes: dict[int, int] = {}
        for fold in assignments.values():
            sizes[fold] = sizes.get(fold, 0) + 1
        assert all(sizes.get(fold, 0) >= 1 for fold in range(gate.N_SPLITS))


class TestRankAuc:
    def test_perfect_separation(self) -> None:
        truth = np.array([0.0, 0.0, 1.0, 1.0])
        scores = np.array([0.1, 0.2, 0.8, 0.9])
        assert gate.rank_auc(truth, scores) == 1.0

    def test_ties_give_half(self) -> None:
        truth = np.array([0.0, 1.0])
        scores = np.array([0.5, 0.5])
        assert gate.rank_auc(truth, scores) == 0.5

    def test_single_class_returns_none(self) -> None:
        truth = np.array([1.0, 1.0])
        scores = np.array([0.3, 0.6])
        assert gate.rank_auc(truth, scores) is None


class TestLinearProbe:
    def test_loss_decreases_on_separable_features(self) -> None:
        rng = np.random.default_rng(42)
        features = rng.normal(size=(40, 4))
        labels = ((features[:, 0] > 0).astype(float))[:, None]
        _, _, first, last = gate.fit_linear_probe(features, labels, epochs=100)
        assert np.isfinite(first) and np.isfinite(last)
        assert last < first

    def test_unknown_labels_are_masked_not_negative(self) -> None:
        rng = np.random.default_rng(42)
        features = rng.normal(size=(10, 4))
        labels = np.full((10, 1), np.nan)
        labels[:5, 0] = 0.0
        labels[5:, 0] = 1.0
        observed_probe = gate.fit_linear_probe(features, labels)[2:]
        masked_labels = labels.copy()
        masked_labels[9, 0] = np.nan
        masked_probe = gate.fit_linear_probe(features[:-1], masked_labels[:-1], epochs=50)[2:]
        assert observed_probe[0] != masked_probe[0]


class TestFoldFeasibility:
    def test_reports_support_and_degeneracy(self) -> None:
        keys = [f"k{i:02d}" for i in range(30)]
        labels = np.full((30, 12), np.nan)
        labels[:, 0] = 1.0  # ACL: all positive, never rare or degenerate
        labels[:, 1] = 0.0  # MCL: all negative -> fold-zero validation is degenerate
        result = gate.fold_feasibility(keys, labels)
        assert result["n_studies"] == 30
        assert sum(result["fold_sizes"]) == 30
        assert result["per_label_positives"]["ACL"] == 30
        assert result["per_label_known"]["ACL"] == 30
        assert "MCL" in result["val_fold_zero_degenerate_targets"]
        assert "ACL" not in result["rare_targets_under_10_positives"]


class TestReadStudyLabels:
    def _write_csv(self, path: Path, rows: list[list[str]]) -> None:
        header = ["StudyInstanceUID", "Report", *gate.TARGETS]
        lines = [",".join(header)]
        lines.extend(",".join(row) for row in rows)
        path.write_text("\n".join(lines), encoding="utf-8")

    def test_empty_cells_remain_nan(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "train.csv"
        self._write_csv(csv_path, [["uid-1", "report", "1", "", *([""] * 10)]])
        keys, matrix = gate.read_study_labels(csv_path)
        assert keys == ["uid-1"]
        assert matrix[0, 0] == 1.0
        assert bool(np.isnan(matrix[0, 1]))

    def test_wrong_header_rejected(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "train.csv"
        csv_path.write_text("StudyInstanceUID,Report\nuid-1,r\n", encoding="utf-8")
        with pytest.raises(gate.GateError, match="train_header_invalid"):
            gate.read_study_labels(csv_path)


class TestPackager:
    def test_package_writes_notebook_and_metadata(self, tmp_path: Path) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        output_root = tmp_path / "package-out"
        result = packager.package(repo_root, output_root, commit="a" * 40)
        assert output_root.exists()
        notebook = json.loads((output_root / packager.NOTEBOOK_FILE).read_bytes())
        metadata = json.loads((output_root / "kernel-metadata.json").read_bytes())
        assert notebook["nbformat"] == 4
        assert metadata["id"] == result["kernel_ref"]
        assert metadata["enable_internet"] is False
        assert metadata["competition_sources"] == ["rsna-knee-abnormality-detection"]
        assert len(metadata["dataset_sources"]) == 1

    def test_existing_output_rejected(self, tmp_path: Path) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        output_root = tmp_path / "pkg"
        packager.package(repo_root, output_root, commit="b" * 40)
        with pytest.raises(packager.PackagingError):
            packager.package(repo_root, output_root, commit="b" * 40)
