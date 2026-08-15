from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]


def _load_validator() -> ModuleType:
    path = ROOT / "scripts/validate_dicom_qa_output.py"
    specification = importlib.util.spec_from_file_location("_performance_smoke_validator", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


validator = _load_validator()


def _identity() -> tuple[dict[str, Any], dict[str, Any]]:
    smoke_sha256 = "a" * 64
    policy_sha256 = "b" * 64
    bundle_sha256 = "c" * 64
    run_config = {
        "code_commit": "d" * 40,
        "bundle_sha256": bundle_sha256,
        "provenance": {
            "runner_sha256": "e" * 64,
            "performance_smoke_sha256": smoke_sha256,
            "performance_smoke_policy_sha256": policy_sha256,
            "preprocessing_config_sha256": "f" * 64,
            "preprocessing_version": "preprocessing-v1",
        },
        "runtime": {
            "internet": False,
            "accelerator": "cpu",
            "self_deadline_seconds": 27_000,
        },
        "privacy": {"canary": "RSNA_PRIVATE_CANARY_test"},
    }
    manifest = {
        "bundle_sha256": bundle_sha256,
        "performance_smoke": {
            "code_file": "performance_smoke.py",
            "sha256": smoke_sha256,
            "policy_file": "performance-smoke-policy.json",
            "policy_sha256": policy_sha256,
        },
    }
    return run_config, manifest


def _summary(run_config: dict[str, Any], manifest: dict[str, Any]) -> bytes:
    provenance = run_config["provenance"]
    smoke = manifest["performance_smoke"]
    return validator._canonical_json_bytes(
        {
            "schema_version": 1,
            "artifact_type": "dicom-qa-performance-smoke-sanitized-aggregate",
            "status": "pass",
            "full_run_started": False,
            "provenance": {
                "git_commit": run_config["code_commit"],
                "bundle_sha256": run_config["bundle_sha256"],
                "runner_sha256": provenance["runner_sha256"],
                "smoke_entrypoint_sha256": smoke["sha256"],
                "performance_smoke_policy_sha256": smoke["policy_sha256"],
                "preprocessing_config_sha256": provenance["preprocessing_config_sha256"],
                "preprocessing_version": provenance["preprocessing_version"],
                "source_manifest_version": "manifest-v2",
                "source_manifest_audit_id": "audit-0003-wheel-sanitization",
                "input_binding_sha256": "1" * 64,
            },
            "runtime": {
                "private_kernel": True,
                "internet": False,
                "accelerator": "cpu",
                "self_deadline_seconds": 3_600,
                "full_pass_budget_seconds": 27_000,
                "competition_cpu_limit_seconds": 32_400,
            },
            "performance": {
                "production_path_exercised": True,
                "post_comparison_preparation_path_exercised": True,
                "authenticated_sample": True,
                "admission_status": "pass",
                "smoke_elapsed_seconds_ceiling": 60,
                "projected_full_run_seconds_ceiling": 26_940,
                "qa_replay_render_seconds_per_series_ceiling": 3,
                "representative_benchmark_seconds_ceiling": 600,
                "review_artifacts_per_series_ceiling": 7,
                "review_artifact_bytes_per_series_power_of_two_mib_ceiling": 8,
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
    )


def _runner() -> SimpleNamespace:
    return SimpleNamespace(
        SELF_DEADLINE_SECONDS=27_000,
        _scan_downloadable=lambda _payload, _canary: None,
    )


def _privacy_runner() -> ModuleType:
    path = ROOT / "kaggle/dicom_qa/run.py"
    runner: ModuleType = validator._runner_module(
        hashlib.sha256(path.read_bytes()).hexdigest(), path
    )
    return runner


def _mock_smoke_download(
    monkeypatch: pytest.MonkeyPatch,
    summary: bytes,
    *,
    log: bytes | None = None,
    include_summary: bool = True,
    extra: bool = False,
) -> None:
    def download(arguments: tuple[str, ...], **_kwargs: Any) -> bytes:
        root = Path(arguments[arguments.index("--path") + 1])
        if include_summary:
            output = root / validator.PERFORMANCE_SMOKE_OUTPUT_DIRECTORY
            output.mkdir()
            (output / validator.PERFORMANCE_SMOKE_SUMMARY).write_bytes(summary)
        if log is not None:
            (root / "kernel.log").write_bytes(log)
        if extra:
            (root / "unexpected.txt").write_bytes(b"unexpected")
        return b""

    monkeypatch.setattr(validator, "_run_kaggle_cli", download)


def test_performance_smoke_summary_is_exact_and_never_allows_full_run() -> None:
    run_config, manifest = _identity()
    payload = _summary(run_config, manifest)
    validator._validate_performance_smoke_summary(
        payload,
        run_config=run_config,
        runner=_runner(),
        manifest=manifest,
    )

    altered = json.loads(payload)
    altered["full_run_started"] = True
    with pytest.raises(validator.OutputValidationError, match="performance_smoke_summary_invalid"):
        validator._validate_performance_smoke_summary(
            validator._canonical_json_bytes(altered),
            run_config=run_config,
            runner=_runner(),
            manifest=manifest,
        )


def test_performance_smoke_summary_rejects_stale_policy_or_input_binding() -> None:
    run_config, manifest = _identity()
    payload = json.loads(_summary(run_config, manifest))
    for mutation in ("policy", "input"):
        altered = json.loads(json.dumps(payload))
        if mutation == "policy":
            altered["provenance"]["performance_smoke_policy_sha256"] = "2" * 64
        else:
            altered["provenance"]["input_binding_sha256"] = "not-a-digest"
        with pytest.raises(validator.OutputValidationError):
            validator._validate_performance_smoke_summary(
                validator._canonical_json_bytes(altered),
                run_config=run_config,
                runner=_runner(),
                manifest=manifest,
            )


@pytest.mark.parametrize(
    ("field", "over_limit"),
    [
        ("qa_replay_render_seconds_per_series_ceiling", 3_601),
        ("representative_benchmark_seconds_ceiling", 3_660),
    ],
)
def test_performance_smoke_summary_caps_post_comparison_preparation_at_one_hour(
    field: str,
    over_limit: int,
) -> None:
    run_config, manifest = _identity()
    payload = json.loads(_summary(run_config, manifest))
    payload["performance"][field] = 3_600
    validator._validate_performance_smoke_summary(
        validator._canonical_json_bytes(payload),
        run_config=run_config,
        runner=_runner(),
        manifest=manifest,
    )

    payload["performance"][field] = over_limit
    with pytest.raises(validator.OutputValidationError, match="performance_smoke_summary_invalid"):
        validator._validate_performance_smoke_summary(
            validator._canonical_json_bytes(payload),
            run_config=run_config,
            runner=_runner(),
            manifest=manifest,
        )


def test_performance_smoke_listing_allows_only_summary_and_one_safe_log() -> None:
    valid = [
        {
            "name": "dicom-qa-performance-smoke/sanitized_performance_smoke.json",
            "size": 896,
        },
        {"name": "kernel.log", "size": 896},
    ]
    validator._validate_performance_smoke_listing((json.dumps(valid).encode(),))

    invalid = [*valid, {"name": "private.json", "size": 896}]
    with pytest.raises(validator.OutputValidationError, match="remote_name_not_allowed"):
        validator._validate_performance_smoke_listing((json.dumps(invalid).encode(),))


def test_performance_smoke_retrieval_allows_privacy_safe_wrapper_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_config, manifest = _identity()
    _mock_smoke_download(
        monkeypatch,
        _summary(run_config, manifest),
        log=b"Kernel run completed\n",
    )

    validator._retrieve_performance_smoke_summary(
        "test-owner/performance-smoke/1",
        run_config=run_config,
        runner=_privacy_runner(),
        manifest=manifest,
    )


@pytest.mark.parametrize(
    "log",
    [b"RSNA_PRIVATE_CANARY_test\n", b"PatientID=private\n"],
)
def test_performance_smoke_retrieval_rejects_sensitive_wrapper_log(
    monkeypatch: pytest.MonkeyPatch,
    log: bytes,
) -> None:
    run_config, manifest = _identity()
    _mock_smoke_download(monkeypatch, _summary(run_config, manifest), log=log)

    with pytest.raises(validator.OutputValidationError, match="performance_smoke_log_invalid"):
        validator._retrieve_performance_smoke_summary(
            "test-owner/performance-smoke/1",
            run_config=run_config,
            runner=_privacy_runner(),
            manifest=manifest,
        )


@pytest.mark.parametrize(("include_summary", "extra"), [(False, False), (True, True)])
def test_performance_smoke_retrieval_rejects_missing_summary_or_extra_file(
    monkeypatch: pytest.MonkeyPatch,
    include_summary: bool,
    extra: bool,
) -> None:
    run_config, manifest = _identity()
    _mock_smoke_download(
        monkeypatch,
        _summary(run_config, manifest),
        log=b"Kernel run completed\n",
        include_summary=include_summary,
        extra=extra,
    )

    with pytest.raises(
        validator.OutputValidationError,
        match="performance_smoke_output_layout_invalid",
    ):
        validator._retrieve_performance_smoke_summary(
            "test-owner/performance-smoke/1",
            run_config=run_config,
            runner=_privacy_runner(),
            manifest=manifest,
        )


def test_performance_smoke_authentication_is_v1_bound_and_race_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_config, manifest = _identity()
    ref = "test-owner/rsna-knee-dqa-smoke-ddddddd-cccccccccccc"
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        validator,
        "_assert_version_absent",
        lambda observed_ref, version: calls.append(("version", (observed_ref, version))),
    )
    monkeypatch.setattr(
        validator,
        "_kernel_status_complete",
        lambda observed_ref: calls.append(("status", observed_ref)),
    )

    def pull(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append(("pull", (args, kwargs)))
        return {"identity": "fixed"}

    monkeypatch.setattr(validator, "_pull_and_verify_exact_kernel", pull)
    monkeypatch.setattr(
        validator,
        "_authenticated_listing",
        lambda observed_ref, version: (
            json.dumps(
                [
                    {
                        "name": ("dicom-qa-performance-smoke/sanitized_performance_smoke.json"),
                        "size": 896,
                    }
                ]
            ).encode(),
        ),
    )
    monkeypatch.setattr(
        validator,
        "_retrieve_performance_smoke_summary",
        lambda observed_ref, **_kwargs: calls.append(("retrieve", observed_ref)),
    )

    validator._authenticate_performance_smoke_kernel(
        ref=ref,
        dataset_ref="test-owner/private-bundle",
        source_manifest_ref="test-owner/private-manifest",
        competition_slug="rsna-knee-competition",
        run_config=run_config,
        runner=_runner(),
        manifest=manifest,
    )

    assert [value for name, value in calls if name == "version"] == [(ref, 2), (ref, 2)]
    assert [value for name, value in calls if name == "status"] == [ref, ref]
    pulls = [value for name, value in calls if name == "pull"]
    assert len(pulls) == 2
    for args, kwargs in pulls:
        assert args[:4] == (ref, 1, "performance_smoke.py", "a" * 64)
        assert kwargs == {
            "expected_kernel_type": "script",
            "expected_dataset_sources": ["test-owner/private-bundle"],
            "expected_kernel_sources": ["test-owner/private-manifest"],
            "expected_competition_sources": ["rsna-knee-competition"],
        }
    assert ("retrieve", f"{ref}/1") in calls
