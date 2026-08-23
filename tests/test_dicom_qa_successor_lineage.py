"""End-to-end synthetic-lineage regressions for the D-043 identity binding.

These tests reuse the exact fixture builders from the full-run suite so the successor
rehearsal cannot drift from the production validator semantics.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

ROOT = Path(__file__).parents[1]
FULL_RUN_PATH = ROOT / "tests" / "test_dicom_qa_full_run.py"


def _load_module(path: Path, name: str) -> ModuleType:
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner: Any = _load_module(ROOT / "kaggle" / "dicom_qa" / "run.py", "_lineage_runner")
full_run: Any = _load_module(FULL_RUN_PATH, "_lineage_full_run_helpers")


def _prepare_review(tmp_path: Path, fixture: SimpleNamespace) -> None:
    monkeypatch = pytest.MonkeyPatch()
    try:
        (tmp_path / "staging").mkdir()
        output = tmp_path / "review-output"
        monkeypatch.setattr(runner, "_decoder_preflight", lambda: None)
        monkeypatch.setattr(runner, "_read_series_rows", lambda _path: fixture.rows)
        monkeypatch.setattr(runner, "_preprocessing_config", lambda *_args: object())
        monkeypatch.setattr(runner, "_series_files", lambda *_args: (fixture.slice_path,))
        perf_values = iter((100.0, 101.0))
        cpu_values = iter((10.0, 14.0))
        rss_values = iter((1_000, 1_500))
        monkeypatch.setattr(runner.time, "perf_counter", lambda: next(perf_values))
        monkeypatch.setattr(runner, "_cpu_seconds", lambda: next(cpu_values))
        monkeypatch.setattr(runner, "_peak_rss_bytes", lambda: next(rss_values))
        artifact_suffixes = (
            "contact.png",
            "orthogonal.png",
            "histogram.png",
            "animation.gif",
            "before_after.png",
            "review.json",
            "metadata.json",
        )

        def fake_replay(**kwargs: Any) -> tuple[Any, ...]:
            case = kwargs["case_ordinal"]
            series = kwargs["series_ordinal"]
            first_output_dir = cast(Path, kwargs["first_output_dir"])
            records = []
            for suffix in artifact_suffixes:
                basename = f"case_{case:06d}_series_{series:03d}_{suffix}"
                payload = f"artifact-{case}-{series}-{suffix}".encode("ascii")
                (first_output_dir / basename).write_bytes(payload)
                records.append(
                    {
                        "basename": basename,
                        "bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
            ordered = SimpleNamespace(
                laterality="L",
                slices=(
                    SimpleNamespace(
                        metadata=SimpleNamespace(image_orientation=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0))
                    ),
                ),
            )
            return (
                fixture.reconstruction,
                fixture.reconstruction,
                fixture.quality,
                ordered,
                tuple(records),
                0.01,
            )

        monkeypatch.setattr(runner, "_replay_render_series", fake_replay)

        from rsna_knee.dicom import benchmark as benchmark_module

        def fake_benchmark(
            _paths: tuple[Path, ...],
            _config: object,
            _versions: object,
            *,
            iterations: int,
            worker_counts: tuple[int, ...],
            offline_bundle_verified: bool,
        ) -> Any:
            del worker_counts, offline_bundle_verified
            timing = benchmark_module.TimingSummary(0.01, 0.02, 0.03)
            return benchmark_module.BenchmarkReport(
                schema_version=1,
                iterations=iterations,
                slices_per_series=1,
                decode_time=timing,
                preprocessing_time=timing,
                representative_tensor_cache_bytes=1024,
                process_peak_rss_bytes=1024,
                peak_rss_increase_bytes=0,
                cpu_parallelism=(benchmark_module.WorkerTiming(1, 1, 1.0, 1.0, 1.0),),
                kaggle_compatibility=benchmark_module.KaggleCompatibility(
                    python_version="3.11.0",
                    platform_system="Linux",
                    platform_machine="x86_64",
                    cpu_count=1,
                    numpy_version="1.0",
                    pydicom_version="1.0",
                    python_supported=True,
                    linux_runtime_observed=True,
                    offline_bundle_verified=True,
                    kaggle_runtime_verified=True,
                    accelerator="cpu",
                    horizontal_flip=False,
                    through_plane_resampling=False,
                ),
                deterministic_replay=True,
            )

        monkeypatch.setattr(benchmark_module, "benchmark_dicom_pipeline", fake_benchmark)
        runner.prepare_private_review(
            cohort_plan_path=fixture.plan_path,
            competition_root=tmp_path,
            output_root=output,
            staging_parent=tmp_path / "staging",
            run_config=fixture.run_config,
            preprocessing_config_path=tmp_path / "preprocessing.yaml",
            full_manifest_path=fixture.manifest_path,
            full_metrics_path=fixture.metrics_path,
            comparison_proof_path=fixture.comparison_path,
            performance_smoke_summary_payload=fixture.smoke_payload,
            review_plan_ref="owner/review-plan-r16-rehearsal",
            review_plan_version=1,
            inference_limit_seconds=32_400,
            deadline_at=None,
        )
    finally:
        monkeypatch.undo()


def test_same_identity_lineage_passes_review_preparation(tmp_path: Path) -> None:
    fixture = full_run._stage_b_inputs(tmp_path)
    _prepare_review(tmp_path, fixture)
    output = tmp_path / "review-output"
    assert {item.name for item in output.iterdir()} == {
        "private_case_index.json",
        "private_artifact_inventory.json",
        "private-review",
        "sanitized_summary.json",
        "benchmark.md",
        "sanitized_artifact_inventory.json",
    }
    case = json.loads((output / "private_case_index.json").read_bytes())
    capacity_provenance = case["capacity_certificate"]["provenance"]
    assert capacity_provenance["git_commit"] == fixture.run_config["code_commit"]
    assert capacity_provenance["bundle_sha256"] == fixture.run_config["bundle_sha256"]
    summary = json.loads((output / "sanitized_summary.json").read_bytes())
    assert summary["provenance"]["git_commit"] == fixture.run_config["code_commit"]
    assert summary["provenance"]["bundle_sha256"] == fixture.run_config["bundle_sha256"]
    assert len(tuple((output / "private-review").iterdir())) == 700


def test_foreign_core_identity_fails_closed_like_d043_adapter(tmp_path: Path) -> None:
    fixture = full_run._stage_b_inputs(tmp_path)
    (tmp_path / "staging2").mkdir()
    old_core_commit = "d" * 40
    old_core_bundle = "e" * 64
    plan = json.loads(fixture.plan_payload)
    plan["provenance"]["git_commit"] = old_core_commit
    plan["provenance"]["bundle_sha256"] = old_core_bundle
    foreign_plan_payload = runner._canonical_json_bytes(plan)
    foreign_plan_path = tmp_path / "foreign_cohort_plan.json"
    foreign_plan_path.write_bytes(foreign_plan_payload)

    metrics = json.loads(fixture.metrics_path.read_bytes())
    metrics["qa_cohort_selection"]["cohort_plan_sha256"] = hashlib.sha256(
        foreign_plan_payload
    ).hexdigest()
    metrics["cohort_plan_sha256"] = hashlib.sha256(foreign_plan_payload).hexdigest()
    fixture.metrics_path.write_bytes(runner._canonical_json_bytes(metrics))
    fixture.comparison_path.write_bytes(
        full_run._private_comparison_payload(
            metrics, hashlib.sha256(foreign_plan_payload).hexdigest()
        )
    )

    with pytest.raises(Exception, match="private_cohort_plan_invalid"):
        runner.prepare_private_review(
            cohort_plan_path=foreign_plan_path,
            competition_root=tmp_path,
            output_root=tmp_path / "review-output",
            staging_parent=tmp_path / "staging2",
            run_config=fixture.run_config,
            preprocessing_config_path=tmp_path / "preprocessing.yaml",
            full_manifest_path=fixture.manifest_path,
            full_metrics_path=fixture.metrics_path,
            comparison_proof_path=fixture.comparison_path,
            performance_smoke_summary_payload=fixture.smoke_payload,
            review_plan_ref="owner/review-plan-r16-negative",
            review_plan_version=1,
            inference_limit_seconds=32_400,
            deadline_at=None,
        )
