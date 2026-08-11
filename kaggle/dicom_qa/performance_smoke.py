"""Authenticated, smoke-only Kaggle entry point for the Chunk 5 DICOM pipeline.

This entry point exercises the production full-pass and post-comparison QA preparation paths on an
authenticated manifest sample, deletes all private sample artifacts, writes one privacy-safe
aggregate, and exits before any full-dataset or human review begins.
"""

from __future__ import annotations

import importlib.util
import math
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from itertools import islice
from pathlib import Path
from types import ModuleType
from typing import Any, Final, cast


def _find_runner_path(input_root: Path) -> Path:
    sibling = Path(__file__).with_name("run.py")
    if sibling.is_file() and not sibling.is_symlink():
        return sibling
    candidates: set[Path] = set()
    frontier = [input_root]
    for depth in range(4):
        next_frontier: list[Path] = []
        for directory in frontier:
            runner_path = directory / "qa_runner.py"
            manifest_path = directory / "bundle-manifest.json"
            if (
                runner_path.is_file()
                and not runner_path.is_symlink()
                and manifest_path.is_file()
                and not manifest_path.is_symlink()
            ):
                candidates.add(runner_path.resolve(strict=True))
            try:
                entries = list(islice(directory.iterdir(), 129))
            except OSError as error:
                raise RuntimeError("runner_discovery_failed") from error
            if len(entries) > 128:
                continue
            if depth < 3:
                next_frontier.extend(
                    entry for entry in entries if entry.is_dir() and not entry.is_symlink()
                )
        frontier = next_frontier
    if len(candidates) != 1:
        raise RuntimeError("runner_discovery_failed")
    return next(iter(candidates))


def _load_runner() -> ModuleType:
    path = _find_runner_path(Path(os.environ.get("KAGGLE_INPUT_ROOT", "/kaggle/input")))
    specification = importlib.util.spec_from_file_location(
        "_rsna_knee_dicom_qa_performance_runner", path
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("runner_load_failed")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


runner = _load_runner()

OUTPUT_DIRECTORY: Final = "dicom-qa-performance-smoke"
SUMMARY_FILENAME: Final = "sanitized_performance_smoke.json"
SUMMARY_MAX_BYTES: Final = 16 * 1024
SELF_DEADLINE_SECONDS: Final = 3_600
PROJECTION_QUANTUM_SECONDS: Final = 60
POLICY_ROLE: Final = "performance_smoke_policy"
POLICY_ARTIFACT_TYPE: Final = "dicom-qa-performance-smoke-policy"
SUMMARY_ARTIFACT_TYPE: Final = "dicom-qa-performance-smoke-sanitized-aggregate"


def _entrypoint_sha256() -> str:
    return str(runner._sha256_file(Path(__file__).resolve(strict=True)))


def expected_policy() -> dict[str, object]:
    """Return the exact policy document that the content-addressed bundle must carry."""

    return {
        "schema_version": 1,
        "artifact_type": POLICY_ARTIFACT_TYPE,
        "entrypoint": {
            "code_file": "performance_smoke.py",
            "sha256": _entrypoint_sha256(),
        },
        "kernel": {
            "is_private": True,
            "enable_internet": False,
            "enable_gpu": False,
            "enable_tpu": False,
            "self_deadline_seconds": SELF_DEADLINE_SECONDS,
            "full_run_allowed": False,
        },
        "output": {
            "directory": OUTPUT_DIRECTORY,
            "filename": SUMMARY_FILENAME,
            "kind": "sanitized_aggregate",
            "max_bytes": SUMMARY_MAX_BYTES,
        },
    }


def _validated_policy(path: Path) -> tuple[dict[str, object], str]:
    payload = runner._read_bounded(
        path,
        SUMMARY_MAX_BYTES,
        "performance_smoke_policy_invalid",
        allow_symlink=True,
    )
    policy = runner._json_object(payload, "performance_smoke_policy_invalid")
    if payload != runner._canonical_json_bytes(policy) or policy != expected_policy():
        raise runner.SafeRunError("performance_smoke_policy_invalid")
    return policy, str(runner._sha256_bytes(payload))


def _source_binding_payload(binding: Any) -> dict[str, str]:
    values = {
        "producer_code_commit": binding.producer_code_commit,
        "kernel_ref": binding.kernel_ref,
        "bundle_dataset_ref": binding.bundle_dataset_ref,
        "bundle_sha256": binding.bundle_sha256,
        "database_sha256": binding.database_sha256,
        "audit_key_sha256": binding.audit_key_sha256,
        "schema_sha256": binding.schema_sha256,
        "source_manifest_artifact_sha256": binding.source_manifest_artifact_sha256,
    }
    if any(not isinstance(value, str) or not value for value in values.values()):
        raise runner.SafeRunError("source_manifest_identity_invalid")
    return values


def _input_binding_sha256(
    *,
    run_config: Mapping[str, Any],
    binding: Any,
    observed_identity: Mapping[str, str],
    policy_sha256: str,
) -> str:
    payload = {
        "domain": "rsna-knee-dicom-qa-performance-smoke-input-binding-v1",
        "git_commit": run_config["code_commit"],
        "bundle_sha256": run_config["bundle_sha256"],
        "input_identity": run_config["input_identity"],
        "source_manifest_binding": _source_binding_payload(binding),
        "observed_source_manifest_identity": dict(sorted(observed_identity.items())),
        "preprocessing_config_sha256": cast(Mapping[str, Any], run_config["provenance"])[
            "preprocessing_config_sha256"
        ],
        "performance_smoke_policy_sha256": policy_sha256,
    }
    return str(runner._sha256_bytes(runner._canonical_json_bytes(payload)))


def _ceil_seconds(value: float) -> int:
    if not math.isfinite(value) or value <= 0:
        raise runner.SafeRunError("performance_smoke_result_invalid")
    return max(
        PROJECTION_QUANTUM_SECONDS,
        math.ceil(value / PROJECTION_QUANTUM_SECONDS) * PROJECTION_QUANTUM_SECONDS,
    )


def _preparation_seconds_ceiling(value: object, *, quantum: int = 1) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value <= 0
        or quantum < 1
    ):
        raise runner.SafeRunError("performance_smoke_result_invalid")
    # Two observed workloads of headroom keeps the admission gate conservative without
    # disclosing a private sample count.
    return max(quantum, math.ceil(float(value) * 2 / quantum) * quantum)


def _artifact_mib_ceiling(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise runner.SafeRunError("performance_smoke_result_invalid")
    mib = max(1, math.ceil((value * 2) / 1024**2))
    ceiling = 1 << (mib - 1).bit_length()
    if ceiling > 256:
        raise runner.SafeRunError("performance_smoke_result_invalid")
    return ceiling


def _summary_payload(
    *,
    run_config: Mapping[str, Any],
    input_binding_sha256: str,
    policy_sha256: str,
    inference_limit_seconds: int,
    smoke_elapsed_seconds: float,
    projected_full_run_seconds: float,
    preparation: Mapping[str, float | int],
) -> bytes:
    artifact_count = preparation.get("review_artifacts")
    if (
        isinstance(artifact_count, bool)
        or not isinstance(artifact_count, int)
        or not 1 <= artifact_count <= 7
    ):
        raise runner.SafeRunError("performance_smoke_result_invalid")
    provenance = cast(Mapping[str, Any], run_config["provenance"])
    summary = {
        "schema_version": 1,
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "status": "pass",
        "full_run_started": False,
        "provenance": {
            "git_commit": run_config["code_commit"],
            "bundle_sha256": run_config["bundle_sha256"],
            "runner_sha256": provenance["runner_sha256"],
            "smoke_entrypoint_sha256": _entrypoint_sha256(),
            "performance_smoke_policy_sha256": policy_sha256,
            "preprocessing_config_sha256": provenance["preprocessing_config_sha256"],
            "preprocessing_version": provenance["preprocessing_version"],
            "source_manifest_version": runner.SOURCE_MANIFEST_VERSION,
            "source_manifest_audit_id": runner.SOURCE_MANIFEST_AUDIT_ID,
            "input_binding_sha256": input_binding_sha256,
        },
        "runtime": {
            "private_kernel": True,
            "internet": False,
            "accelerator": "cpu",
            "self_deadline_seconds": SELF_DEADLINE_SECONDS,
            "full_pass_budget_seconds": runner.SELF_DEADLINE_SECONDS,
            "competition_cpu_limit_seconds": inference_limit_seconds,
        },
        "performance": {
            "production_path_exercised": True,
            "post_comparison_preparation_path_exercised": True,
            "authenticated_sample": True,
            "admission_status": "pass",
            "smoke_elapsed_seconds_ceiling": _ceil_seconds(smoke_elapsed_seconds),
            "projected_full_run_seconds_ceiling": _ceil_seconds(projected_full_run_seconds),
            "qa_replay_render_seconds_per_series_ceiling": (
                _preparation_seconds_ceiling(preparation.get("qa_replay_render_seconds"))
            ),
            "representative_benchmark_seconds_ceiling": _preparation_seconds_ceiling(
                preparation.get("representative_benchmark_seconds"), quantum=60
            ),
            "review_artifacts_per_series_ceiling": 7,
            "review_artifact_bytes_per_series_power_of_two_mib_ceiling": (
                _artifact_mib_ceiling(preparation.get("review_artifact_bytes"))
            ),
        },
        "privacy": {
            "identifiers_emitted": False,
            "paths_emitted": False,
            "pixels_emitted": False,
            "reports_emitted": False,
            "private_resource_locators_emitted": False,
            "private_artifact_checksums_emitted": False,
        },
    }
    payload = cast(bytes, runner._canonical_json_bytes(summary))
    _validate_summary(
        payload,
        run_config=run_config,
        expected_input_binding_sha256=input_binding_sha256,
        expected_policy_sha256=policy_sha256,
        expected_inference_limit_seconds=inference_limit_seconds,
    )
    return payload


def _validate_summary(
    payload: bytes,
    *,
    run_config: Mapping[str, Any],
    expected_input_binding_sha256: str,
    expected_policy_sha256: str,
    expected_inference_limit_seconds: int,
) -> dict[str, Any]:
    summary = runner._json_object(payload, "performance_smoke_summary_invalid")
    provenance = cast(Mapping[str, Any], run_config["provenance"])
    expected_provenance = {
        "git_commit": run_config["code_commit"],
        "bundle_sha256": run_config["bundle_sha256"],
        "runner_sha256": provenance["runner_sha256"],
        "smoke_entrypoint_sha256": _entrypoint_sha256(),
        "performance_smoke_policy_sha256": expected_policy_sha256,
        "preprocessing_config_sha256": provenance["preprocessing_config_sha256"],
        "preprocessing_version": provenance["preprocessing_version"],
        "source_manifest_version": runner.SOURCE_MANIFEST_VERSION,
        "source_manifest_audit_id": runner.SOURCE_MANIFEST_AUDIT_ID,
        "input_binding_sha256": expected_input_binding_sha256,
    }
    expected_runtime = {
        "private_kernel": True,
        "internet": False,
        "accelerator": "cpu",
        "self_deadline_seconds": SELF_DEADLINE_SECONDS,
        "full_pass_budget_seconds": runner.SELF_DEADLINE_SECONDS,
        "competition_cpu_limit_seconds": expected_inference_limit_seconds,
    }
    privacy = {
        "identifiers_emitted": False,
        "paths_emitted": False,
        "pixels_emitted": False,
        "reports_emitted": False,
        "private_resource_locators_emitted": False,
        "private_artifact_checksums_emitted": False,
    }
    performance = summary.get("performance")
    if (
        payload != runner._canonical_json_bytes(summary)
        or set(summary)
        != {
            "schema_version",
            "artifact_type",
            "status",
            "full_run_started",
            "provenance",
            "runtime",
            "performance",
            "privacy",
        }
        or summary.get("schema_version") != 1
        or summary.get("artifact_type") != SUMMARY_ARTIFACT_TYPE
        or summary.get("status") != "pass"
        or summary.get("full_run_started") is not False
        or summary.get("provenance") != expected_provenance
        or summary.get("runtime") != expected_runtime
        or summary.get("privacy") != privacy
        or not isinstance(performance, dict)
        or set(performance)
        != {
            "production_path_exercised",
            "post_comparison_preparation_path_exercised",
            "authenticated_sample",
            "admission_status",
            "smoke_elapsed_seconds_ceiling",
            "projected_full_run_seconds_ceiling",
            "qa_replay_render_seconds_per_series_ceiling",
            "representative_benchmark_seconds_ceiling",
            "review_artifacts_per_series_ceiling",
            "review_artifact_bytes_per_series_power_of_two_mib_ceiling",
        }
        or performance.get("production_path_exercised") is not True
        or performance.get("post_comparison_preparation_path_exercised") is not True
        or performance.get("authenticated_sample") is not True
        or performance.get("admission_status") != "pass"
        or performance.get("review_artifacts_per_series_ceiling") != 7
    ):
        raise runner.SafeRunError("performance_smoke_summary_invalid")
    for key in ("smoke_elapsed_seconds_ceiling", "projected_full_run_seconds_ceiling"):
        value = performance.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < PROJECTION_QUANTUM_SECONDS
            or value % PROJECTION_QUANTUM_SECONDS
        ):
            raise runner.SafeRunError("performance_smoke_summary_invalid")
    replay_ceiling = performance.get("qa_replay_render_seconds_per_series_ceiling")
    benchmark_ceiling = performance.get("representative_benchmark_seconds_ceiling")
    artifact_mib_ceiling = performance.get(
        "review_artifact_bytes_per_series_power_of_two_mib_ceiling"
    )
    if (
        isinstance(replay_ceiling, bool)
        or not isinstance(replay_ceiling, int)
        or not 1 <= replay_ceiling <= SELF_DEADLINE_SECONDS
        or isinstance(benchmark_ceiling, bool)
        or not isinstance(benchmark_ceiling, int)
        or not PROJECTION_QUANTUM_SECONDS <= benchmark_ceiling <= SELF_DEADLINE_SECONDS
        or benchmark_ceiling % PROJECTION_QUANTUM_SECONDS
        or isinstance(artifact_mib_ceiling, bool)
        or not isinstance(artifact_mib_ceiling, int)
        or not 1 <= artifact_mib_ceiling <= 256
        or artifact_mib_ceiling & (artifact_mib_ceiling - 1)
    ):
        raise runner.SafeRunError("performance_smoke_summary_invalid")
    if (
        not isinstance(expected_inference_limit_seconds, int)
        or isinstance(expected_inference_limit_seconds, bool)
        or expected_inference_limit_seconds <= runner.SELF_DEADLINE_SECONDS
        or SELF_DEADLINE_SECONDS > runner.POST_FULL_PASS_RESERVE_SECONDS
    ):
        raise runner.SafeRunError("performance_smoke_summary_invalid")
    runner._scan_downloadable(
        payload, str(cast(Mapping[str, Any], run_config["privacy"])["canary"])
    )
    return cast(dict[str, Any], summary)


def _sample_shape(
    competition_root: Path,
    rows: Sequence[Any],
    reconciliation: Any,
) -> tuple[int, int]:
    sample_uids = set(reconciliation.performance_sample_study_uids)
    selected = [row for row in rows if row.study_uid in sample_uids]
    if not sample_uids or {row.study_uid for row in selected} != sample_uids:
        raise runner.SafeRunError("performance_smoke_sample_invalid")
    sample_files = sum(len(runner._series_files(competition_root, row)) for row in selected)
    if not selected or sample_files < 1:
        raise runner.SafeRunError("performance_smoke_sample_invalid")
    return len(selected), sample_files


def _run_authenticated_smoke(
    *,
    input_root: Path,
    competition_root: Path,
    cache_parent: Path,
    run_config: Mapping[str, Any],
    preprocessing_config_path: Path,
    policy_sha256: str,
    inference_limit_seconds: int,
    admission_started_at: float,
    deadline_at: float,
) -> bytes:
    from rsna_knee.data import series_slots as slots
    from rsna_knee.dicom import benchmark as benchmark_module
    from rsna_knee.dicom import pipeline
    from rsna_knee.qa import preprocessing as qa

    runner._decoder_preflight()
    rows = runner._read_series_rows(competition_root / "train_series.csv")
    input_identity = cast(Mapping[str, Any], run_config["input_identity"])
    binding = runner._discover_source_manifest_binding(
        input_root, cast(Mapping[str, object], input_identity["source_manifest"])
    )
    reconciliation: Any | None = None
    private_cache_parent: Path | None = None
    try:
        source_facts, observed_identity, reconciliation = runner._load_source_manifest_facts(
            binding, rows
        )
        del source_facts
        config = runner._preprocessing_config(preprocessing_config_path, pipeline)
        versions = pipeline.PipelineVersions(
            code_commit=str(run_config["code_commit"]),
            source_manifest_version=runner.SOURCE_MANIFEST_VERSION,
        )
        workers = run_config["workers"]
        if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 16:
            raise runner.SafeRunError("worker_count_invalid")
        sample_series, sample_files = _sample_shape(competition_root, rows, reconciliation)
        private_cache_parent = Path(
            tempfile.mkdtemp(prefix=".performance-smoke-private-cache-", dir=cache_parent)
        )
        pre_smoke_elapsed = time.monotonic() - admission_started_at
        admission_budget_seconds = runner.SELF_DEADLINE_SECONDS - pre_smoke_elapsed
        if (
            not math.isfinite(admission_budget_seconds)
            or admission_budget_seconds <= runner.POST_FULL_PASS_RESERVE_SECONDS
        ):
            raise runner.SafeRunError("throughput_projection_exceeds_budget")
        started = time.perf_counter()
        runner._safe_event(
            "dicom_qa_performance_smoke_progress", phase="performance_smoke", code="start"
        )
        runner._run_performance_smoke(
            competition_root=competition_root,
            rows=rows,
            reconciliation=reconciliation,
            pipeline_module=pipeline,
            slots_module=slots,
            config=config,
            versions=versions,
            workers=workers,
            cache_parent=private_cache_parent,
            budget_seconds=admission_budget_seconds,
            deadline_at=deadline_at,
        )
        elapsed = time.perf_counter() - started
        runner._safe_event(
            "dicom_qa_performance_smoke_progress", phase="performance_smoke", code="complete"
        )
        preparation = runner._run_preparation_smoke(
            competition_root=competition_root,
            rows=rows,
            sample_study_uids=reconciliation.performance_sample_study_uids,
            config=config,
            versions=versions,
            pipeline_module=pipeline,
            qa_module=qa,
            slots_module=slots,
            benchmark_module=benchmark_module,
            workers=workers,
            cache_parent=private_cache_parent,
            deadline_at=deadline_at,
        )
        projected_full_pass = elapsed * max(
            reconciliation.expected_series_count / sample_series,
            reconciliation.expected_file_count / sample_files,
        )
        projected_after_auth = elapsed + projected_full_pass + runner.POST_FULL_PASS_RESERVE_SECONDS
        projected_total = pre_smoke_elapsed + projected_after_auth
        if (
            not math.isfinite(projected_total)
            or projected_total <= 0
            or _ceil_seconds(projected_after_auth) > admission_budget_seconds
        ):
            raise runner.SafeRunError("throughput_projection_exceeds_budget")
        input_binding_sha256 = _input_binding_sha256(
            run_config=run_config,
            binding=binding,
            observed_identity=observed_identity,
            policy_sha256=policy_sha256,
        )
        return _summary_payload(
            run_config=run_config,
            input_binding_sha256=input_binding_sha256,
            policy_sha256=policy_sha256,
            inference_limit_seconds=inference_limit_seconds,
            smoke_elapsed_seconds=elapsed,
            projected_full_run_seconds=projected_total,
            preparation=preparation,
        )
    finally:
        if reconciliation is not None:
            reconciliation.connection.close()
        if private_cache_parent is not None:
            shutil.rmtree(private_cache_parent, ignore_errors=True)


def main() -> int:
    phase = "bundle"
    started = time.monotonic()
    runtime_root: Path | None = None
    staging_root: Path | None = None
    package_root = "rsna_knee"
    displaced_modules: dict[str, ModuleType] = {}
    runtime_modules_active = False
    try:
        runner._safe_event("dicom_qa_performance_smoke_started")
        input_root = Path(os.environ.get("KAGGLE_INPUT_ROOT", "/kaggle/input"))
        working_root = Path(os.environ.get("KAGGLE_WORKING_ROOT", "/kaggle/working"))
        output_root = working_root / OUTPUT_DIRECTORY
        if output_root.exists():
            raise runner.SafeRunError("output_exists")
        bundle_root, manifest = runner._find_bundle(input_root)
        records = runner._validated_records(bundle_root, manifest)
        run_config, paths, dependencies = runner._verify_run_config(bundle_root, manifest, records)
        policy_path = paths.get(POLICY_ROLE)
        if not isinstance(policy_path, Path):
            raise runner.SafeRunError("performance_smoke_policy_missing")
        _, policy_sha256 = _validated_policy(policy_path)
        inference_limit_seconds = runner._competition_cpu_limit_seconds(
            paths["competition_contract"]
        )
        competition_root = runner._find_competition_root(input_root)
        deadline_at = started + SELF_DEADLINE_SECONDS
        phase = "authentication"
        with runner._enforce_self_deadline(deadline_at - time.monotonic()):
            runtime_root = runner._install_offline_runtime(
                bundle_root, paths["project_wheel"], dependencies
            )
            sys.path.insert(0, str(runtime_root))
            displaced_modules = {
                name: module
                for name, module in tuple(sys.modules.items())
                if name == package_root or name.startswith(f"{package_root}.")
            }
            for name in displaced_modules:
                del sys.modules[name]
            runtime_modules_active = True
            staging_root = Path(
                tempfile.mkdtemp(prefix=".dicom-qa-performance-smoke-", dir=working_root)
            )
            scratch = staging_root / "scratch"
            scratch.mkdir(mode=0o700)
            phase = "performance_smoke"
            with runner._silence_process_output():
                summary_payload = _run_authenticated_smoke(
                    input_root=input_root,
                    competition_root=competition_root,
                    cache_parent=scratch,
                    run_config=run_config,
                    preprocessing_config_path=paths["preprocessing_config"],
                    policy_sha256=policy_sha256,
                    inference_limit_seconds=inference_limit_seconds,
                    admission_started_at=started,
                    deadline_at=deadline_at,
                )
            shutil.rmtree(scratch, ignore_errors=True)
            phase = "output"
            runner._write_new(
                staging_root / SUMMARY_FILENAME,
                summary_payload,
                maximum=SUMMARY_MAX_BYTES,
            )
            staging_root.rename(output_root)
            staging_root = None
        runner._safe_event("dicom_qa_performance_smoke_complete")
        return 0
    except runner.SafeRunError as error:
        runner._safe_event("dicom_qa_performance_smoke_failed", phase=phase, code=error.code)
        return 2
    except runner._DeadlineExceeded:
        runner._safe_event(
            "dicom_qa_performance_smoke_failed",
            phase=phase,
            code="self_deadline_exceeded",
        )
        return 2
    except BaseException:
        runner._safe_event("dicom_qa_performance_smoke_failed", phase=phase, code="internal_error")
        return 2
    finally:
        if staging_root is not None:
            shutil.rmtree(staging_root, ignore_errors=True)
        if runtime_modules_active:
            for name in tuple(sys.modules):
                if name == package_root or name.startswith(f"{package_root}."):
                    del sys.modules[name]
            sys.modules.update(displaced_modules)
        if runtime_root is not None:
            runtime_text = str(runtime_root)
            if runtime_text in sys.path:
                sys.path.remove(runtime_text)
            shutil.rmtree(runtime_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
