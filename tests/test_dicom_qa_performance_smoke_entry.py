from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "kaggle/dicom_qa/performance_smoke.py"


def _load_entrypoint() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "_dicom_qa_performance_smoke_entry_test", ENTRYPOINT
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


smoke = _load_entrypoint()


class _Connection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _run_config() -> dict[str, Any]:
    return {
        "code_commit": "a" * 40,
        "bundle_sha256": "b" * 64,
        "workers": 2,
        "input_identity": {
            "official_competition": {"slug": smoke.runner.COMPETITION_SLUG},
            "source_manifest": {"audit_id": smoke.runner.SOURCE_MANIFEST_AUDIT_ID},
        },
        "provenance": {
            "runner_sha256": "c" * 64,
            "preprocessing_config_sha256": "d" * 64,
            "preprocessing_version": "dicom-model-v1",
        },
        "privacy": {"canary": "RSNA_PRIVATE_CANARY_TEST_ONLY"},
    }


def _binding(tmp_path: Path) -> Any:
    return smoke.runner.SourceManifestBinding(
        database_path=tmp_path / "private_manifest.sqlite3",
        audit_key_path=tmp_path / "audit_key.bin",
        producer_code_commit="e" * 40,
        kernel_ref="test-owner/private-source-kernel",
        bundle_dataset_ref="test-owner/private-source-bundle",
        bundle_sha256="f" * 64,
        database_sha256="1" * 64,
        audit_key_sha256="2" * 64,
        schema_sha256="3" * 64,
        source_manifest_artifact_sha256="4" * 64,
    )


def _patch_authenticated_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, _Connection]:
    row = smoke.runner.SeriesRow(
        study_uid="1.2.826.0.1.1001",
        series_uid="1.2.826.0.1.2001",
        fluid_sensitive="present",
        fat_suppression="absent",
        plane="sagittal",
    )
    connection = _Connection()
    reconciliation = SimpleNamespace(
        connection=connection,
        performance_sample_study_uids=(row.study_uid,),
        expected_series_count=10,
        expected_file_count=10,
    )
    observed = {
        "audit_id": smoke.runner.SOURCE_MANIFEST_AUDIT_ID,
        "manifest_version": smoke.runner.SOURCE_MANIFEST_VERSION,
        "source_manifest_artifact_sha256": "4" * 64,
        "official_input_snapshot_sha256": "5" * 64,
    }
    monkeypatch.setattr(smoke.runner, "_decoder_preflight", lambda: None)
    monkeypatch.setattr(smoke.runner, "_read_series_rows", lambda _path: (row,))
    monkeypatch.setattr(
        smoke.runner, "_discover_source_manifest_binding", lambda *_args: _binding(tmp_path)
    )
    monkeypatch.setattr(
        smoke.runner,
        "_load_source_manifest_facts",
        lambda *_args: ({row.study_uid: {}}, observed, reconciliation),
    )
    monkeypatch.setattr(smoke.runner, "_preprocessing_config", lambda *_args: object())
    monkeypatch.setattr(smoke.runner, "_series_files", lambda *_args: (tmp_path / "slice",))
    monkeypatch.setattr(smoke.runner, "_safe_event", lambda *_args, **_kwargs: None)
    return reconciliation, connection


def test_entrypoint_calls_only_authenticated_production_smoke_and_cleans_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reconciliation, connection = _patch_authenticated_inputs(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []
    preparation_calls: list[dict[str, Any]] = []

    def production_smoke(**arguments: Any) -> None:
        calls.append(arguments)
        assert arguments["reconciliation"] is reconciliation
        assert arguments["budget_seconds"] == smoke.runner.SELF_DEADLINE_SECONDS - 120.0
        assert arguments["deadline_at"] == 3_600.0

    def forbidden(**_arguments: Any) -> None:
        pytest.fail("smoke entry point crossed into a full or QA run")

    def preparation_smoke(**arguments: Any) -> dict[str, float | int]:
        preparation_calls.append(arguments)
        assert arguments["sample_study_uids"] == reconciliation.performance_sample_study_uids
        return {
            "qa_replay_render_seconds": 1.2,
            "representative_benchmark_seconds": 61.0,
            "review_artifact_bytes": 600_000,
            "review_artifacts": 6,
        }

    monkeypatch.setattr(smoke.runner, "_run_performance_smoke", production_smoke)
    monkeypatch.setattr(smoke.runner, "_run_preparation_smoke", preparation_smoke)
    monkeypatch.setattr(smoke.runner, "_run_full_dataset_pass", forbidden)
    times = iter((0.0, 60.0))
    monkeypatch.setattr(smoke.time, "perf_counter", lambda: next(times))
    monkeypatch.setattr(smoke.time, "monotonic", lambda: 120.0)

    payload = smoke._run_authenticated_smoke(
        input_root=tmp_path,
        competition_root=tmp_path,
        cache_parent=tmp_path,
        run_config=_run_config(),
        preprocessing_config_path=tmp_path / "preprocessing.json",
        policy_sha256="6" * 64,
        inference_limit_seconds=32_400,
        admission_started_at=0.0,
        deadline_at=3_600.0,
    )

    summary = json.loads(payload)
    assert len(calls) == 1
    assert len(preparation_calls) == 1
    assert summary["status"] == "pass"
    assert summary["full_run_started"] is False
    assert summary["performance"] == {
        "admission_status": "pass",
        "authenticated_sample": True,
        "post_comparison_preparation_path_exercised": True,
        "production_path_exercised": True,
        "projected_full_run_seconds_ceiling": 4_320,
        "qa_replay_render_seconds_per_series_ceiling": 3,
        "representative_benchmark_seconds_ceiling": 180,
        "review_artifact_bytes_per_series_power_of_two_mib_ceiling": 2,
        "review_artifacts_per_series_ceiling": 7,
        "smoke_elapsed_seconds_ceiling": 60,
    }
    assert connection.closed is True
    assert not list(tmp_path.glob(".performance-smoke-private-cache-*"))


def test_failure_closes_manifest_and_removes_private_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, connection = _patch_authenticated_inputs(tmp_path, monkeypatch)

    def fail_after_cache_creation(**arguments: Any) -> None:
        cache_parent = arguments["cache_parent"]
        assert isinstance(cache_parent, Path)
        (cache_parent / "private-cache-fragment").write_bytes(b"private")
        raise smoke.runner.SafeRunError("performance_smoke_sample_invalid")

    monkeypatch.setattr(smoke.runner, "_run_performance_smoke", fail_after_cache_creation)
    monkeypatch.setattr(smoke.time, "perf_counter", lambda: 0.0)
    monkeypatch.setattr(smoke.time, "monotonic", lambda: 0.0)

    with pytest.raises(smoke.runner.SafeRunError, match="performance_smoke_sample_invalid"):
        smoke._run_authenticated_smoke(
            input_root=tmp_path,
            competition_root=tmp_path,
            cache_parent=tmp_path,
            run_config=_run_config(),
            preprocessing_config_path=tmp_path / "preprocessing.json",
            policy_sha256="6" * 64,
            inference_limit_seconds=32_400,
            admission_started_at=0.0,
            deadline_at=3_600.0,
        )

    assert connection.closed is True
    assert not list(tmp_path.glob(".performance-smoke-private-cache-*"))


def test_policy_and_summary_are_exact_and_fail_closed(
    tmp_path: Path,
) -> None:
    policy_path = tmp_path / "performance-smoke-policy.json"
    policy = smoke.expected_policy()
    policy_path.write_bytes(smoke.runner._canonical_json_bytes(policy))
    assert smoke._validated_policy(policy_path)[0] == policy

    altered_policy = {**policy, "unexpected": True}
    policy_path.write_bytes(smoke.runner._canonical_json_bytes(altered_policy))
    with pytest.raises(smoke.runner.SafeRunError, match="performance_smoke_policy_invalid"):
        smoke._validated_policy(policy_path)

    payload = smoke._summary_payload(
        run_config=_run_config(),
        input_binding_sha256="7" * 64,
        policy_sha256="6" * 64,
        inference_limit_seconds=32_400,
        smoke_elapsed_seconds=1.0,
        projected_full_run_seconds=4_000.0,
        preparation={
            "qa_replay_render_seconds": 1.0,
            "representative_benchmark_seconds": 60.0,
            "review_artifact_bytes": 1_000_000,
            "review_artifacts": 6,
        },
    )
    summary = json.loads(payload)
    summary["full_run_started"] = True
    with pytest.raises(smoke.runner.SafeRunError, match="performance_smoke_summary_invalid"):
        smoke._validate_summary(
            smoke.runner._canonical_json_bytes(summary),
            run_config=_run_config(),
            expected_input_binding_sha256="7" * 64,
            expected_policy_sha256="6" * 64,
            expected_inference_limit_seconds=32_400,
        )

    summary["full_run_started"] = False
    summary["performance"]["representative_benchmark_seconds_ceiling"] = 3_660
    with pytest.raises(smoke.runner.SafeRunError, match="performance_smoke_summary_invalid"):
        smoke._validate_summary(
            smoke.runner._canonical_json_bytes(summary),
            run_config=_run_config(),
            expected_input_binding_sha256="7" * 64,
            expected_policy_sha256="6" * 64,
            expected_inference_limit_seconds=32_400,
        )


def test_entrypoint_has_one_hour_deadline_and_no_full_run_call() -> None:
    assert smoke.SELF_DEADLINE_SECONDS == 3_600
    tree = ast.parse(ENTRYPOINT.read_text())
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "_run_performance_smoke" in called_attributes
    assert "_run_preparation_smoke" in called_attributes
    assert "_run_full_dataset_pass" not in called_attributes
    assert "_run_private_qa" not in called_attributes


def test_remote_entrypoint_discovers_the_bound_runner_from_the_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(smoke, "__file__", str(tmp_path / "kernel" / "performance_smoke.py"))
    bundle = tmp_path / "input" / "bundle"
    bundle.mkdir(parents=True)
    (bundle / "bundle-manifest.json").write_text("{}")
    runner_path = bundle / "qa_runner.py"
    runner_path.write_text("# bound runner")

    assert smoke._find_runner_path(tmp_path / "input") == runner_path
    second = tmp_path / "input" / "other"
    second.mkdir()
    (second / "bundle-manifest.json").write_text("{}")
    (second / "qa_runner.py").write_text("# ambiguous runner")
    with pytest.raises(RuntimeError, match="runner_discovery_failed"):
        smoke._find_runner_path(tmp_path / "input")


def test_remote_entrypoint_skips_wide_competition_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(smoke, "__file__", str(tmp_path / "kernel" / "performance_smoke.py"))
    bundle = tmp_path / "input" / "bundle"
    bundle.mkdir(parents=True)
    (bundle / "bundle-manifest.json").write_text("{}")
    runner_path = bundle / "qa_runner.py"
    runner_path.write_text("# bound runner")
    studies = tmp_path / "input" / "competition" / "train_series"
    studies.mkdir(parents=True)
    for index in range(129):
        (studies / f"study-{index:03d}").mkdir()

    assert smoke._find_runner_path(tmp_path / "input") == runner_path
