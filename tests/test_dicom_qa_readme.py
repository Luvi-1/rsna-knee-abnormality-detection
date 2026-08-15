from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).parents[1]
README = ROOT / "kaggle/dicom_qa/README.md"
PACKAGER = ROOT / "scripts/package_dicom_qa_bundle.py"
MANIFEST_PACKAGER = ROOT / "scripts/package_manifest_bundle.py"
VALIDATOR = ROOT / "scripts/validate_dicom_qa_output.py"
PACKAGING_TEST = ROOT / "tests/test_dicom_qa_packaging.py"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _options(module: Any) -> set[str]:
    return {
        option
        for action in module._parser()._actions
        for option in action.option_strings
        if option.startswith("--")
    }


def test_runbook_matches_current_parsers_and_immutable_workflow(tmp_path: Path) -> None:
    text = README.read_text()
    normalized = " ".join(text.split())
    _load("package_manifest_bundle", MANIFEST_PACKAGER)
    packager = _load("_readme_packager", PACKAGER)
    validator = _load("_readme_validator", VALIDATOR)
    assert f'--path "$bundle_root/$directory" --timeout {packager.OUTER_KILL_SECONDS}' in text

    obsolete = (
        "--remote-kernel-version",
        "--review-template-kernel-version",
        "--review-kernel-version",
        "--expected-review-attestation-sha256",
        "completed_review_attestation.json",
        "same notebook",
        "orientation`\n3. `laterality",
        "photometric`",
        "physical_aspect`",
        "before_after`",
        "animation`",
        "metadata`",
    )
    assert not any(value in text for value in obsolete)

    required_in_order = (
        "audit-0003-wheel-sanitization",
        "validate_workflow_stage inputs",
        '--path "$bundle_root/performance-smoke-kernel" --timeout 4200',
        "validate_workflow_stage performance-smoke",
        "push_kernel_v1 kernel-a",
        "validate_workflow_stage run-a",
        "push_kernel_v1 kernel-b",
        "validate_workflow_stage run-b",
        "push_kernel_v1 comparison-kernel",
        "validate_workflow_stage comparison",
        "push_kernel_v1 review-plan-kernel",
        "validate_workflow_stage plan",
        "push_kernel_v1 review-ui-template-kernel",
        "validate_workflow_stage ui",
        "Choose **Copy & Edit**",
        "type exactly `START`",
        "`completed_review_ledger.json`",
        "validate_workflow_stage review",
        "push_kernel_v1 review-finalizer-kernel",
        "validate_workflow_stage final",
    )
    positions = [text.index(value) for value in required_in_order]
    assert positions == sorted(positions)

    checks = re.findall(r"^   [1-9]\. `([a-z_]+)`$", text, flags=re.MULTILINE)
    assert checks == list(packager.REVIEW_CHECKS)
    assert "`PASS`, `BLOCK`, or\n   `NOT_APPLICABLE`" in text
    assert "`N` is permitted only for `duplicate_missing_abnormal_handling`" in text
    assert "There is no global one-`PASS`-per-check shortcut" in text
    assert "when the UI says `CHECK_9_APPLICABLE=NO`" in text
    assert "`final_performance_report.json`" in text
    assert "entire authorized training set" in text
    assert "at least 100 studies" in text
    assert "every eligible diagnostic\n   series" in text
    assert "Any `BLOCK`" in text
    assert "local aggregate" not in text.lower()
    for value in (
        "Run A and Run B are deliberately core-only.",
        "`private_full_run_manifest.jsonl`",
        "`private_full_run_metrics.json`",
        "`private_cohort_plan.json`",
        "`run_private_remote_only`, `run_downloadable`,",
        "`review_private_remote_only`, `review_private_remote_patterns`, and `review_downloadable`",
        "`cohort_plan_byte_equality`",
        "The existing review-plan kernel is the only downstream QA-preparation stage",
        "performance-smoke v1, Run A v1, Run B v1, and comparison v1, in that order",
        "The `run-a` workflow gate reauthenticates the completed smoke v1",
        "safe progress sequence begins with `full_pass`",
        "`dicom_qa_plan_progress` sequence is exactly `cohort_replay` start/complete followed by",
        "its only competition source is the official competition",
        "It deliberately has no direct source-manifest kernel source",
        "owned by review-plan v1, never by Run A or Run B",
        "seven artifacts per series",
        "20,000-file cap",
        "fixed 600-second finalization reserve",
        "8 GiB total and 32 MiB per-file caps",
        "review-plan slug root",
        "each run's `sanitized_summary.json` and `sanitized_artifact_inventory.json`",
        "review-plan's `sanitized_summary.json`, `benchmark.md`, and",
    ):
        assert value in normalized
    for obsolete_claim in (
        "rehash the Run A artifacts",
        "under the authenticated Run A",
        "already-sanitized Run A measurements",
        "each run's `sanitized_summary.json`, `benchmark.md`",
    ):
        assert obsolete_claim not in normalized
    assert "`dicom_qa_output_validation=PASS mode=workflow stage=<stage>`" in text
    assert (
        "`dicom_qa_output_validation=PASS mode=workflow stage=final "
        "determinism=pass human_review=pass`" in text
    )
    workflow_stages = [
        "inputs",
        "performance-smoke",
        "run-a",
        "run-b",
        "comparison",
        "plan",
        "ui",
        "review",
        "final",
    ]
    assert (
        re.findall(r"^validate_workflow_stage ([a-z-]+)$", text, flags=re.MULTILINE)
        == workflow_stages
    )
    for value in (
        "`dataset/bundle-manifest.json`",
        "`run-config.json`",
        "`dataset-metadata.json`",
        "`kernel/run.py`",
        "`kernel-metadata.json`",
        "Kaggle CLI 2.2.4",
        "proving v2 absence",
        "pulling and hashing the exact v1 source",
        "bounded source-only v1 pulls before and after",
        "never retrieves notebook outputs",
        "`dataset/synthetic-preflight.json`",
        "`kaggle_runtime_execution` remains `pending_run_a`",
        "not target-runtime execution",
        "recomputes every declared size",
        "It never\ndownloads competition DICOMs",
        "`qa-stratum-registry-v1`",
        "`qa-cohort-selection-v3`",
        "minimum of 100 studies, not a maximum",
        "represented\nregistry-value quota `min(2, population)`",
    ):
        assert value in text
    assert "qa-material-strata-v1" not in text
    assert "material_stratum_policy_version" not in text
    assert "represented material stratum" not in text

    bash_blocks = re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL)
    package_flags = {
        flag
        for block in bash_blocks
        if "scripts/package_dicom_qa_bundle.py" in block
        for flag in re.findall(r"(?<![A-Za-z0-9])(--[a-z][a-z0-9-]+)", block)
    }
    validator_flags = {
        flag
        for block in bash_blocks
        if "scripts/validate_dicom_qa_output.py" in block
        for flag in re.findall(r"(?<![A-Za-z0-9])(--[a-z][a-z0-9-]+)", block)
    }
    assert package_flags == {
        "--repo-root",
        "--output",
        "--owner",
        "--workers",
        "--source-manifest-bundle-root",
        "--source-manifest-registry",
        "--source-manifest-audit-id",
    }
    assert package_flags <= _options(packager)
    assert validator_flags == {
        "--run-config",
        "--bundle-manifest",
        "--expected-commit",
        "--expected-bundle",
        "--workflow-kernel-version",
        "--workflow-stage",
    }
    assert validator_flags <= _options(validator)
    workflow_stage_action = next(
        action
        for action in validator._parser()._actions
        if "--workflow-stage" in action.option_strings
    )
    assert list(workflow_stage_action.choices) == workflow_stages

    fixture = _load("_readme_packaging_fixture", PACKAGING_TEST)
    bundle, result = fixture._assembled(tmp_path)
    generated = {path.name for path in bundle.iterdir()}
    documented = {name for name in generated if f"- `{name}`" in text}
    assert documented == generated
    review_plan = _load_json(bundle / "review-plan-kernel/kernel-metadata.json")
    assert review_plan["kernel_sources"] == [
        result["performance_smoke_ref"],
        result["run_a_ref"],
        result["run_b_ref"],
        result["comparison_ref"],
    ]
    assert review_plan["competition_sources"] == [packager.COMPETITION_SLUG]
    finalizer = _load_json(bundle / "review-finalizer-kernel/kernel-metadata.json")
    assert finalizer["kernel_sources"] == [
        result["run_a_ref"],
        result["run_b_ref"],
        result["comparison_ref"],
        result["review_plan_ref"],
        result["review_session_ref"],
    ]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    assert isinstance(payload, dict)
    return payload


def test_documented_kaggle_flags_exist_in_cli_224_help_without_network() -> None:
    version = subprocess.run(
        ["kaggle", "--version"],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    assert version.returncode == 0
    assert version.stdout.strip() == "Kaggle CLI 2.2.4"
    assert version.stdout.strip() in README.read_text()

    commands = {
        ("datasets", "create"): {"--path", "--dir-mode", "--quiet"},
        ("datasets", "download"): {"--file", "--path", "--force", "--quiet"},
        ("kernels", "push"): {"--path", "--timeout"},
    }
    for command, expected in commands.items():
        result = subprocess.run(
            ["kaggle", *command, "--help"],
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert expected <= set(re.findall(r"--[a-z][a-z-]+", result.stdout))
