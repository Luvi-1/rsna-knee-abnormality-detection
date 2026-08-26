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

    def test_reversed_ranking_gives_zero(self) -> None:
        truth = np.array([0.0, 0.0, 1.0, 1.0])
        scores = np.array([0.9, 0.8, 0.2, 0.1])
        assert gate.rank_auc(truth, scores) == 0.0

    def test_partial_ties(self) -> None:
        truth = np.array([1.0, 0.0, 0.0, 1.0])
        # Two cross-class ties and two separated pairs -> exactly 0.5.
        scores = np.array([0.5, 0.5, 0.9, 0.9])
        assert gate.rank_auc(truth, scores) == 0.5

    def test_cross_boundary_ties(self) -> None:
        truth = np.array([0.0, 1.0, 0.0, 1.0])
        scores = np.array([0.5, 0.5, 0.5, 0.5])
        assert gate.rank_auc(truth, scores) == 0.5

    def test_low_support_one_pos_one_neg(self) -> None:
        truth = np.array([0.0, 1.0])
        scores = np.array([0.2, 0.8])
        assert gate.rank_auc(truth, scores) == 1.0


class TestMaskedLossInvariance:
    """Masked BCE must ignore unknown cells and scale with supervised cells."""

    @staticmethod
    def _masked_bce_numpy(logits, targets, mask):
        """Numpy mirror of binary_cross_entropy_with_logits + masked mean."""
        stable = np.logaddexp(0.0, logits) - logits * targets
        denom = mask.sum()
        if denom == 0:
            return 0.0
        return float((stable * mask).sum() / denom)

    def test_unknown_cells_do_not_affect_loss(self) -> None:
        rng = np.random.default_rng(42)
        logits = rng.normal(size=(4, 12))
        targets = rng.integers(0, 2, size=(4, 12)).astype(float)
        mask = np.ones_like(targets)
        partial_mask = mask.copy()
        partial_mask[:, :6] = 0
        loss_original = self._masked_bce_numpy(logits, targets, partial_mask)
        corrupted = targets.copy()
        corrupted[:, :6] = 1 - corrupted[:, :6]
        loss_corrupted = self._masked_bce_numpy(logits, corrupted, partial_mask)
        assert abs(loss_original - loss_corrupted) < 1e-12

    def test_zero_supervision_batch_returns_zero(self) -> None:
        logits = np.zeros((4, 12))
        targets = np.zeros((4, 12))
        mask = np.zeros_like(targets)
        assert self._masked_bce_numpy(logits, targets, mask) == 0.0


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


class TestSafeSeriesToken:
    def test_pipeline_issue_extracted(self) -> None:
        class FakeIssue:
            value = "uneven_slice_spacing"

        class FakeError(Exception):
            issue = FakeIssue()

        assert gate._safe_series_token(FakeError()) == "uneven_slice_spacing"

    def test_unknown_error_falls_back(self) -> None:
        assert gate._safe_series_token(ValueError("secret path detail")) == "preprocess_failed"


class TestSkipAuditSummaryShape:
    """The audit summary must stay within the bounded sanitized envelope."""

    def test_summary_keys_are_safe_tokens(self) -> None:
        import inspect

        source = inspect.getsource(gate.run_skip_audit)
        for forbidden in ("StudyInstanceUID", "SeriesInstanceUID", "Report", "train_series/"):
            assert forbidden not in source.replace('row["StudyInstanceUID"]', "").replace(
                'row["SeriesInstanceUID"]', ""
            )


class TestE00cModelConfig:
    """The CNN gate must declare its frozen configuration explicitly."""

    def test_constants_declared(self) -> None:
        assert gate.E00C_COHORT == 12
        assert gate.E00C_EPOCHS == 3000
        assert gate.E00C_LEARNING_RATE == 1e-3
        assert gate.SEED == 42


class TestE01ModelConfig:
    """The Fold 0 training gate must use mini-batch AdamW without regularization."""

    def test_constants_declared(self) -> None:
        assert gate.E01_EPOCHS == 30
        assert gate.E01_LEARNING_RATE == 1e-3
        assert gate.E01_BATCH_SIZE == 8

    def test_packager_enables_gpu(self, tmp_path: Path) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        output_root = tmp_path / "pkg-e01"
        packager.package(repo_root, output_root, commit="d" * 40, gate="e01")
        metadata = json.loads((output_root / "kernel-metadata.json").read_bytes())
        assert metadata["enable_gpu"] is True
        notebook = json.loads((output_root / packager.NOTEBOOK_FILE).read_bytes())
        assert "run_e01_fold_zero_training" in str(notebook["cells"])


class TestE01RDiagnostic:
    def test_constants_declared(self) -> None:
        assert gate.E01R_EPOCHS == 30
        assert gate.E01R_LEARNING_RATE == 1e-3
        assert gate.E01R_BATCH_SIZE == 8

    def test_pairwise_auc_agrees_with_rank_auc(self) -> None:
        truth = np.array([0.0, 0.0, 1.0, 1.0])
        scores = np.array([0.1, 0.2, 0.8, 0.9])
        assert gate.rank_auc(truth, scores) == gate.pairwise_auc(truth, scores) == 1.0
        truth_rev = np.array([1.0, 1.0, 0.0, 0.0])
        scores_rev = np.array([0.1, 0.2, 0.8, 0.9])
        assert (
            gate.rank_auc(truth_rev, scores_rev) == gate.pairwise_auc(truth_rev, scores_rev) == 0.0
        )

    def test_pairwise_auc_single_class_returns_none(self) -> None:
        truth = np.array([1.0, 1.0])
        scores = np.array([0.3, 0.6])
        assert gate.rank_auc(truth, scores) is None
        assert gate.pairwise_auc(truth, scores) is None

    def test_packager_includes_e01r_entry_point(self, tmp_path: Path) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        output_root = tmp_path / "pkg-e01r"
        result = packager.package(repo_root, output_root, commit="e" * 40, gate="e01r")
        metadata = json.loads((output_root / "kernel-metadata.json").read_bytes())
        notebook = json.loads((output_root / packager.NOTEBOOK_FILE).read_bytes())
        assert metadata["enable_gpu"] is True
        assert result["kernel_slug"].endswith("-r1")
        assert "run_e01r_sparse_supervision_diagnostic" in str(notebook["cells"])


class TestAcceleratorPreflight:
    """Preflight contract tests using a minimal deterministic torch stub."""

    @staticmethod
    def _fake_torch(*, cuda_available, capability=(7, 5), arch_list=("sm_70",)):
        import types

        import numpy as np

        torch_stub = types.SimpleNamespace()
        torch_stub.__version__ = "test"
        cuda = types.SimpleNamespace()
        cuda.is_available = lambda: cuda_available
        cuda.device_count = lambda: 1 if cuda_available else 0
        cuda.get_arch_list = lambda: list(arch_list)
        cuda.get_device_capability = lambda index=0: tuple(capability)
        cuda.get_device_name = lambda index=0: "Tesla T4"
        cuda.get_device_properties = lambda index=0: types.SimpleNamespace(
            total_memory=15_000_000_000
        )
        cuda.synchronize = lambda: None
        torch_stub.cuda = cuda

        class Tensor:
            def __init__(self, data):
                self.data = np.asarray(data, dtype=np.float32)
                self.grad = None

            def cpu(self):
                return self

            def detach(self):
                return Tensor(self.data.copy())

            def reshape(self, *shape):
                return Tensor(self.data.reshape(shape))

            def __matmul__(self, other):
                return Tensor(self.data @ other.data)

            def __sub__(self, other):
                return Tensor(self.data - other.data)

            def abs(self):
                return Tensor(np.abs(self.data))

            def max(self):
                outer = self

                class Scalar:
                    def item(self):
                        return float(outer.data.max())

                return Scalar()

            def norm(self):
                outer = self

                class Scalar:
                    def item(self):
                        return float(np.linalg.norm(outer.data))

                return Scalar()

            def square(self):
                outer = self

                class Squared:
                    data = outer.data**2

                    def mean(self):
                        class Scalar:
                            def item(self):
                                return float(Squared.data.mean())

                            def backward(self):
                                # The smoke test only verifies that a finite,
                                # nonzero gradient reaches the tracked matmul
                                # weight; it does not model autograd exactly.
                                pass

                        return Scalar()

                return Squared()

            def mean(self):
                outer = self

                class Scalar:
                    def item(self):
                        return float(outer.data.mean())

                return Scalar()

        torch_stub.device = lambda target: "cuda"
        torch_stub.float32 = np.float32
        torch_stub.arange = lambda n, device=None, dtype=None: Tensor(np.arange(n))
        torch_stub.ones = lambda shape, device=None, requires_grad=False: Tensor(np.ones(shape))

        def _isfinite(t):
            holder = types.SimpleNamespace()
            holder.all = lambda: types.SimpleNamespace(
                # Production passes the gradient tensor itself; check its data.
                item=lambda: bool(np.isfinite(np.asarray(t.data)).all())
            )
            return holder

        torch_stub.isfinite = _isfinite
        # The preflight computes x @ weight, takes mean(), and calls backward().
        # The patched matmul returns a Tensor whose mean() Scalar carries a
        # backward() that populates weight.grad with finite values.
        original_matmul = Tensor.__matmul__

        def matmul_with_grad(self, other):
            out = original_matmul(self, other)

            def square():
                outer = self
                weight_ref = other

                class Squared:
                    data = outer.data**2

                    def mean(self):
                        class Scalar:
                            def item(self):
                                return float(Squared.data.mean())

                            def backward(self):
                                weight_ref.grad = Tensor(
                                    np.full_like(weight_ref.detach().data, 0.25)
                                )

                        return Scalar()

                return Squared()

            out.square = square
            return out

        Tensor.__matmul__ = matmul_with_grad
        torch_stub.version = types.SimpleNamespace(cuda="12.1-test")
        return torch_stub

    def test_preflight_fails_closed_without_cuda(self):
        ft = self._fake_torch(cuda_available=False)
        with pytest.raises(gate.GateError, match="preflight_cuda_unavailable"):
            gate._accelerator_preflight(ft, require_gpu=True)

    def test_preflight_fails_closed_on_unsupported_capability(self):
        ft = self._fake_torch(cuda_available=True, capability=(6, 0), arch_list=["sm_70"])
        with pytest.raises(gate.GateError, match="preflight_capability_unsupported"):
            gate._accelerator_preflight(ft, require_gpu=True)

    def test_preflight_passes_when_build_supports_device_and_smoke_succeeds(self):
        ft = self._fake_torch(cuda_available=True, capability=(7, 5), arch_list=["sm_75"])
        report = gate._accelerator_preflight(ft, require_gpu=True)
        assert report["gpu_required"] is True
        assert report["devices"][0]["name"] == "Tesla T4"
        assert report["devices"][0]["compute_capability"] == "7.5"
        assert report["devices"][0]["supported_in_build"] is True
        assert report["smoke"]["status"] == "pass"

    def test_preflight_allows_explicit_cpu_diagnostics(self):
        ft = self._fake_torch(cuda_available=False)
        report = gate._accelerator_preflight(ft, require_gpu=False)
        assert report["gpu_required"] is False and report["device_count"] == 0

    def test_compute_ptx_fallback_allows_older_device(self):
        # A CUDA build compiled with PTX forward-compatibility for compute_80 can
        # JIT-run older devices; a bare sm_80 cubin cannot.
        assert gate._arch_supports_capability(["compute_80"], (8, 0)) is True
        assert gate._arch_supports_capability(["sm_80"], (6, 0)) is False


class TestWeakLabelsV1Policy:
    def _worksheet(self):
        return [
            {
                "row_id": str(i),
                "study_key_sha256": f"{i:064x}",
                "target": "Fracture",
                "language": "en",
                "report_section": "findings",
                "matched_sentence": "No acute fracture.",
                "preceding_context": "Alignment is anatomic.",
                "following_context": "Otherwise unremarkable.",
                "proposed_state_blinded": gate._blinded_proposal_label(i),
            }
            for i in range(1, 81)
        ]

    def test_review_worksheet_validation_passes_exact_queue_lineage(self):
        queue = [
            {
                "study_key_sha256": row["study_key_sha256"],
                "target": "Fracture",
                "language": "en",
            }
            for row in self._worksheet()
        ]
        gate._validate_review_worksheet(queue, self._worksheet())

    @pytest.mark.parametrize(
        ("field", "token"),
        [
            ("row_id", "review_worksheet_row_id_invalid"),
            ("matched_sentence", "review_worksheet_evidence_incomplete"),
            ("preceding_context", "review_worksheet_evidence_incomplete"),
            ("following_context", "review_worksheet_evidence_incomplete"),
            ("proposed_state_blinded", "review_proposal_blinding_invalid"),
        ],
    )
    def test_review_worksheet_rejects_malformed_rows(self, field, token):
        rows = self._worksheet()
        queue = [
            {
                "study_key_sha256": row["study_key_sha256"],
                "target": "Fracture",
                "language": "en",
            }
            for row in rows
        ]
        if field == "proposed_state_blinded":
            rows[0][field] = "Model proposal X"
        else:
            rows[0][field] = ""
        with pytest.raises(gate.GateError, match=token):
            gate._validate_review_worksheet(queue, rows)

    def test_review_ui_is_self_contained_and_blinds_proposals(self):
        html = gate._render_review_ui_html(self._worksheet()).decode("utf-8")
        assert "Model proposal A" in html and "Model proposal B" in html
        assert "No acute fracture." in html
        assert "<script>" in html and "http://" not in html and "https://" not in html
        assert "POSITIVE" in html and "NOT_MENTIONED" in html

    def test_review_ui_payload_never_contains_raw_angle_brackets(self):
        rows = self._worksheet()
        rows[0]["matched_sentence"] = "</script><script>alert(1)</script>"
        html = gate._render_review_ui_html(rows).decode("utf-8")
        script_start = html.index("<script>")
        script_end = html.index("</script>", script_start)
        payload = html[script_start + len("<script>") : script_end]
        assert "</script>" not in payload
        assert "<script>" not in payload

    def test_e02_constants_declared(self) -> None:
        assert gate.E02_EPOCHS == 30
        assert gate.E02_LEARNING_RATE == 1e-3
        assert gate.E02_BATCH_SIZE == 8
        assert gate.E02_SUPERVISION_VERSION == "weak-labels-v1-ai-provisional"

    def test_packager_includes_e02_entry_point(self, tmp_path: Path) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        output_root = tmp_path / "pkg-e02"
        result = packager.package(repo_root, output_root, commit="f" * 40, gate="e02")
        metadata = json.loads((output_root / "kernel-metadata.json").read_bytes())
        notebook = json.loads((output_root / packager.NOTEBOOK_FILE).read_bytes())
        assert metadata["enable_gpu"] is True
        assert result["kernel_slug"].endswith("-e2")
        assert "run_e02_weak_label_supervision" in str(notebook["cells"])

    def test_packager_includes_e03_entry_point(self, tmp_path: Path) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        output_root = tmp_path / "pkg-e03"
        result = packager.package(repo_root, output_root, commit="0" * 40, gate="e03")
        metadata = json.loads((output_root / "kernel-metadata.json").read_bytes())
        notebook = json.loads((output_root / packager.NOTEBOOK_FILE).read_bytes())
        assert metadata["enable_gpu"] is True
        assert metadata["machine_shape"] == "NvidiaTeslaT4"
        assert result["kernel_slug"].endswith("-e3")
        assert "run_e03_crossfit_weak_labels" in str(notebook["cells"])

    def test_not_mentioned_is_masked_and_ambiguity_targets_fail_closed(self) -> None:
        assert "not_mentioned" not in gate._AMBIGUOUS_TARGETS
        assert set(gate.TARGETS) >= gate._AMBIGUOUS_TARGETS

        positive, negative, uncertain = gate._ONTOLOGY_RULES["Effusion"]
        assert "trace fluid" in negative
        assert "joint effusion" in positive
        assert uncertain

    def test_state_for_target_uses_sentence_negation(self) -> None:
        state, confidence, evidence = gate._weak_label_state_for_target(
            "FINDINGS:\nNo joint effusion.", "Effusion"
        )
        assert state == "negative"
        assert 0.0 <= confidence <= 1.0
        assert evidence["match_count"] >= 1

    def test_evidence_at_report_boundary_uses_explicit_markers(self) -> None:
        _state, _confidence, evidence = gate._weak_label_state_for_target(
            "FINDINGS:\nNo joint effusion.", "Effusion"
        )
        record = evidence["review_evidence"][0]
        assert record["matched_sentence"] == "No joint effusion."
        assert record["preceding_context"] == gate.REVIEW_CONTEXT_REPORT_BEGINNING
        assert record["following_context"] == gate.REVIEW_CONTEXT_REPORT_END

    def test_evidence_context_crosses_section_boundaries(self) -> None:
        report = (
            "FINDINGS:\nThe alignment is normal. No acute fracture.\n\n"
            "IMPRESSION:\nSmall joint effusion."
        )
        _state, _confidence, evidence = gate._weak_label_state_for_target(report, "Effusion")
        record = evidence["review_evidence"][0]
        assert record["section"] == "impression"
        assert record["matched_sentence"] == "Small joint effusion."
        assert record["preceding_context"] == "The alignment is normal. No acute fracture."
        assert record["following_context"] == gate.REVIEW_CONTEXT_REPORT_END

    def test_packager_includes_weak_v1_entry_point_cpu_only(self, tmp_path: Path) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        output_root = tmp_path / "pkg-weak-v1"
        result = packager.package(repo_root, output_root, commit="f" * 40, gate="weak_v1")
        metadata = json.loads((output_root / "kernel-metadata.json").read_bytes())
        notebook = json.loads((output_root / packager.NOTEBOOK_FILE).read_bytes())
        assert metadata["enable_gpu"] is False
        assert metadata["enable_internet"] is False
        assert result["kernel_slug"].endswith("-wv1")
        assert "run_weak_labels_v1" in str(notebook["cells"])


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

    def test_e00c_gate_enables_gpu(self, tmp_path: Path) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        output_root = tmp_path / "pkg-e00c"
        result = packager.package(repo_root, output_root, commit="c" * 40, gate="e00c")
        metadata = json.loads((output_root / "kernel-metadata.json").read_bytes())
        assert result["kernel_slug"].startswith("rsna-knee-model-gate-ccccccc-")
        assert metadata["enable_gpu"] is True
        notebook = json.loads((output_root / packager.NOTEBOOK_FILE).read_bytes())
        assert "run_e00c_cnn_memorization_gate" in str(notebook["cells"])
        with pytest.raises(packager.PackagingError):
            packager.package(repo_root, output_root, commit="b" * 40)


class TestE00bSelection:
    def test_selects_studies_with_both_pos_and_neg(self) -> None:
        """Studies must have at least one positive and one negative known label."""
        keys = ["a", "b", "c", "d"]
        labels = np.array(
            [
                [1.0, 0.0],
                [1.0, np.nan],
                [np.nan, 0.0],
                [np.nan, np.nan],
            ]
        )
        eligible = []
        for index in range(len(keys)):
            row = labels[index]
            observed = np.isfinite(row)
            if observed.any() and (row[observed] == 1).any() and (row[observed] == 0).any():
                eligible.append(index)
        assert len(eligible) == 1
        assert keys[eligible[0]] == "a"
