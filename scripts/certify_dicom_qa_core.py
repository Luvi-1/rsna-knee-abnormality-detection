"""Build and verify the Core Execution Certificate for an authenticated DICOM-QA core."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Final

CERTIFICATE_TYPE: Final = "rsna-knee-core-execution-certificate-v1"
CERTIFICATE_SCHEMA_VERSION: Final = 1
CORE_STAGE: Final = "comparison"
RUN_SUMMARY_BASENAME: Final = "sanitized_summary.json"
COMPARISON_PROOF_BASENAME: Final = "sanitized_determinism.json"
RUN_SUMMARY_MAX_BYTES: Final = 262_144
COMPARISON_PROOF_MAX_BYTES: Final = 32 * 1024
REQUIRED_PASSED_STAGES: Final = (
    "input_authentication",
    "performance_smoke",
    "run_a",
    "run_b",
    "comparison",
)
HEX_64_LENGTH: Final = 64

OutputFetcher = Callable[[str, str, int], bytes]
LiveAuthenticator = Callable[[str], None]


class CertificateError(Exception):
    """Raised when the core certificate cannot be built or verified."""


def _utc_now() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def _load_module(name: str, path: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise CertificateError("module_load_failed")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _require_mapping(value: object, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CertificateError(code)
    return value


def _require_hex64(value: object, code: str) -> str:
    if not isinstance(value, str) or len(value) != HEX_64_LENGTH:
        raise CertificateError(code)
    try:
        bytes.fromhex(value)
    except ValueError as error:
        raise CertificateError(code) from error
    return value


def _kaggle_executable() -> str:
    discovered = shutil.which("kaggle")
    if discovered is not None:
        return discovered
    for candidate in ("/opt/homebrew/bin/kaggle", "/usr/local/bin/kaggle"):
        if Path(candidate).exists():
            return candidate
    raise CertificateError("kaggle_cli_unavailable")


def _default_fetch_output(reference: str, pattern: str, maximum: int) -> bytes:
    with tempfile.TemporaryDirectory(prefix="rsna-knee-core-cert-") as temporary:
        root = Path(temporary)
        completed = subprocess.run(
            [
                _kaggle_executable(),
                "kernels",
                "output",
                reference,
                "--path",
                str(root),
                "--file-pattern",
                pattern,
                "--quiet",
            ],
            capture_output=True,
            timeout=300,
            check=False,
        )
        if completed.returncode != 0:
            raise CertificateError("kernel_output_download_failed")
        entries = list(root.rglob("*"))
        if any(not path.is_dir() and not path.is_file() for path in entries):
            raise CertificateError("kernel_output_layout_invalid")
        files = [path for path in entries if path.is_file() and not path.is_symlink()]
        target_match = re.compile(pattern)
        targets = [path for path in files if target_match.fullmatch(path.name) is not None]
        logs = [path for path in files if path.suffix == ".log"]
        if len(targets) != 1 or len(logs) > 1 or len(files) != len(targets) + len(logs):
            raise CertificateError("kernel_output_layout_invalid")
        payload = targets[0].read_bytes()
        if len(payload) > maximum:
            raise CertificateError("kernel_output_oversized")
        if any(path.stat().st_size > 2 * 1024 * 1024 for path in logs):
            raise CertificateError("kernel_output_oversized")
        return payload


def _fetch_and_scan(
    *,
    reference: str,
    basename: str,
    directory: str | None,
    maximum: int,
    canary: str,
    scanner: ModuleType,
    fetch: OutputFetcher,
) -> bytes:
    prefix = f"{directory}/" if directory else ""
    escaped = basename.replace(".", r"\.")
    pattern = rf"^({prefix})?{escaped}$"
    payload = fetch(reference, pattern, maximum)
    try:
        scanner._scan_downloadable(payload, canary)
    except Exception as error:
        raise CertificateError("privacy_scan_failed") from error
    return payload


def _validate_run_summary(payload: bytes, *, commit: str, bundle: str) -> None:
    try:
        summary = json.loads(payload)
    except json.JSONDecodeError as error:
        raise CertificateError("run_summary_invalid") from error
    summary = _require_mapping(summary, "run_summary_invalid")
    if (
        summary.get("artifact_type") != "dicom-qa-sanitized-core-aggregate"
        or summary.get("schema_version") != 1
        or summary.get("status") != "complete_pending_comparison"
    ):
        raise CertificateError("run_summary_invalid")
    provenance = _require_mapping(summary.get("provenance"), "run_summary_invalid")
    if provenance.get("git_commit") != commit or provenance.get("bundle_sha256") != bundle:
        raise CertificateError("run_summary_provenance_mismatch")
    pipeline = _require_mapping(summary.get("pipeline"), "run_summary_invalid")
    if (
        pipeline.get("all_series_terminal") is not True
        or pipeline.get("full_training_dataset_processed") is not True
        or pipeline.get("integrity_gate") != "pass"
        or pipeline.get("unresolved_blockers") != "zero"
    ):
        raise CertificateError("run_summary_pipeline_invalid")
    privacy = _require_mapping(summary.get("privacy"), "run_summary_invalid")
    downloaded_false = (
        privacy.get("downloaded_case_details") is False
        and privacy.get("downloaded_identifiers") is False
        and privacy.get("downloaded_paths") is False
        and privacy.get("downloaded_pixels") is False
    )
    if not downloaded_false or privacy.get("private_cohort_plan_remote_only") is not True:
        raise CertificateError("run_summary_privacy_invalid")


def _registry_row(registry_path: Path, chain_audit_id: str) -> tuple[dict[str, Any], str]:
    connection = sqlite3.connect(f"file:{registry_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM audit_runs WHERE audit_id = ?", (chain_audit_id,)
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise CertificateError("registry_row_missing")
    result = _require_mapping(json.loads(str(row["result_json"])), "registry_result_invalid")
    if result.get("terminal_reason") != "review_plan_input_discovery_invalid":
        raise CertificateError("registry_failure_shape_invalid")
    if (
        row["audit_kind"] != "dicom_preprocessing_integrity"
        or row["status"] != "failed"
        or result.get("human_review") != "not_started"
        or not str(result.get("review_plan", "")).startswith("failed_")
    ):
        raise CertificateError("registry_failure_shape_invalid")
    for stage in REQUIRED_PASSED_STAGES:
        if result.get(stage) != "passed":
            raise CertificateError(f"registry_stage_not_passed_{stage}")
    return result, str(row["created_utc"])


def build_certificate(
    *,
    repo_root: Path,
    chain_audit_id: str,
    registry_path: Path | None = None,
    fetch: OutputFetcher | None = None,
    live_authenticate: LiveAuthenticator | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Authenticate the frozen core end-to-end and emit its certificate payload."""
    bundle_root = repo_root / "artifacts/dicom-qa-bundle-d3771e7/dataset"
    registry_path = registry_path or repo_root / "artifacts/experiments.sqlite3"
    validator = _load_module(
        "_core_cert_validator", repo_root / "scripts/validate_dicom_qa_output.py"
    )
    run_config, runner, manifest = validator.load_verified_policy(
        bundle_root / "run-config.json",
        bundle_root / "bundle-manifest.json",
        expected_commit=str(run_config_value(bundle_root / "run-config.json", "code_commit")),
        expected_bundle=str(run_config_value(bundle_root / "run-config.json", "bundle_sha256")),
        runner_path=bundle_root / "qa_runner.py",
    )
    refs = validator._workflow_refs(run_config)
    dataset_ref = validator._bundle_dataset_ref(run_config)
    registry_result, registry_created = _registry_row(registry_path, chain_audit_id)
    if registry_result.get("bundle_sha256") != run_config["bundle_sha256"]:
        raise CertificateError("registry_bundle_mismatch")

    def default_authenticate(chain_audit_id: str) -> None:
        validator.validate_authenticated_workflow(
            expected_version=1,
            stage=CORE_STAGE,
            run_config=run_config,
            runner=runner,
            manifest=manifest,
            finalizer_source=bundle_root / "finalize_review.py",
        )

    authenticate = live_authenticate or default_authenticate
    authenticate(chain_audit_id)

    resolved_fetch = fetch or _default_fetch_output
    canary = str(_require_mapping(run_config["privacy"], "policy_invalid")["canary"])
    run_summaries: dict[str, bytes] = {}
    for role in ("run_a", "run_b"):
        run_summaries[role] = _fetch_and_scan(
            reference=refs[role],
            basename=RUN_SUMMARY_BASENAME,
            directory="dicom-qa-output",
            maximum=RUN_SUMMARY_MAX_BYTES,
            canary=canary,
            scanner=runner,
            fetch=resolved_fetch,
        )
        _validate_run_summary(
            run_summaries[role],
            commit=str(run_config["code_commit"]),
            bundle=str(run_config["bundle_sha256"]),
        )
    comparison_proof = _fetch_and_scan(
        reference=refs["comparison"],
        basename=COMPARISON_PROOF_BASENAME,
        directory="dicom_qa_comparison",
        maximum=COMPARISON_PROOF_MAX_BYTES,
        canary=canary,
        scanner=runner,
        fetch=resolved_fetch,
    )
    try:
        validator._validate_comparison_summary(comparison_proof)
    except validator.OutputValidationError as error:
        raise CertificateError("comparison_proof_invalid") from error

    provenance = _require_mapping(run_config["provenance"], "policy_invalid")
    selection = _require_mapping(run_config["selection"], "policy_invalid")
    input_identity = _require_mapping(run_config["input_identity"], "policy_invalid")
    official_competition = _require_mapping(
        input_identity["official_competition"], "policy_invalid"
    )
    source_manifest = _require_mapping(input_identity["source_manifest"], "policy_invalid")
    core_refs = [refs["performance_smoke"], refs["run_a"], refs["run_b"], refs["comparison"]]
    timestamp = now or _utc_now()
    certificate: dict[str, Any] = {
        "schema_version": CERTIFICATE_SCHEMA_VERSION,
        "certificate_type": CERTIFICATE_TYPE,
        "core_lineage_id": chain_audit_id,
        "core_status": "passed",
        "qa_adapter_status": "not_passed",
        "human_review_status": "not_started",
        "created_utc": timestamp,
        "competition_slug": _require_mapping(run_config["competition"], "policy_invalid")["slug"],
        "freeze_commit_sha256": run_config["code_commit"],
        "bundle_sha256": run_config["bundle_sha256"],
        "bundle_dataset_ref": dataset_ref,
        "source_input_snapshot": {
            "identity_source": official_competition["snapshot_identity_source"],
            "official_competition_contract_sha256": official_competition["contract_sha256"],
            "manifest_bundle_ref": source_manifest["bundle_dataset_ref"],
            "manifest_bundle_version": source_manifest["bundle_dataset_version"],
            "manifest_bundle_sha256": source_manifest["bundle_sha256"],
            "manifest_kernel_ref": source_manifest["kernel_ref"],
            "manifest_kernel_version": source_manifest["kernel_version"],
            "audit_id": source_manifest["audit_id"],
            "source_manifest_version": provenance["source_manifest_version"],
        },
        "preprocessing": {
            "version": provenance["preprocessing_version"],
            "renderer_version": provenance["renderer_version"],
            "config_sha256": provenance["preprocessing_config_sha256"],
            "schema_sha256": provenance["preprocessing_schema_sha256"],
        },
        "qa_registry_membership": selection,
        "runtime": run_config["runtime"],
        "stages": {
            "inputs": {
                "status": "passed",
                "input_identity_sha256": registry_result["input_identity_sha256"],
            },
            "performance_smoke": {
                "status": "passed",
                "kernel_ref": refs["performance_smoke"],
                "kernel_version": 1,
                "started_utc": registry_result["performance_smoke_started_utc"],
                "completed_utc": registry_result["performance_smoke_completed_utc"],
            },
            "run_a": {
                "status": "passed",
                "kernel_ref": refs["run_a"],
                "kernel_version": 1,
                "started_utc": registry_result["run_a_started_utc"],
                "validated_utc": registry_result["run_a_validated_utc"],
                "output_sha256": _sha256_hex(run_summaries["run_a"]),
            },
            "run_b": {
                "status": "passed",
                "kernel_ref": refs["run_b"],
                "kernel_version": 1,
                "started_utc": registry_result["run_b_started_utc"],
                "validated_utc": registry_result["run_b_validated_utc"],
                "output_sha256": _sha256_hex(run_summaries["run_b"]),
            },
            "comparison": {
                "status": "passed",
                "kernel_ref": refs["comparison"],
                "kernel_version": 1,
                "started_utc": registry_result["comparison_started_utc"],
                "completed_utc": registry_result["comparison_completed_utc"],
                "result_sha256": _sha256_hex(comparison_proof),
            },
        },
        "registry_evidence": {
            "audit_id": chain_audit_id,
            "created_utc": registry_created,
            "review_plan_failed_utc": registry_result["review_plan_completed_utc"],
            "terminal_reason": "review_plan_input_discovery_invalid",
            "predecessor_audit_id": registry_result.get("predecessor_audit_id"),
        },
        "validator": {
            "module_sha256": _sha256_hex(
                (repo_root / "scripts/validate_dicom_qa_output.py").read_bytes()
            ),
            "workflow_stage_authenticated": CORE_STAGE,
            "authenticated_kernel_refs": core_refs,
            "authenticated_utc": timestamp,
        },
    }
    certificate["certificate_payload_sha256"] = _sha256_hex(_canonical_bytes(certificate))
    return certificate


def run_config_value(path: Path, key: str) -> object:
    config = _require_mapping(json.loads(path.read_text()), "run_config_invalid")
    if key not in config:
        raise CertificateError("run_config_invalid")
    return config[key]


def verify_certificate(certificate: dict[str, Any]) -> None:
    """Check structural invariants and payload integrity without network access."""
    certificate = _require_mapping(certificate, "certificate_unreadable")
    if (
        certificate.get("schema_version") != CERTIFICATE_SCHEMA_VERSION
        or certificate.get("certificate_type") != CERTIFICATE_TYPE
    ):
        raise CertificateError("certificate_header_invalid")
    if (
        certificate.get("core_status") != "passed"
        or certificate.get("qa_adapter_status") != "not_passed"
        or certificate.get("human_review_status") != "not_started"
    ):
        raise CertificateError("certificate_status_invalid")
    commit = certificate.get("freeze_commit_sha256")
    if not isinstance(commit, str) or len(commit) != 40:
        raise CertificateError("certificate_field_invalid")
    try:
        bytes.fromhex(commit)
    except ValueError as error:
        raise CertificateError("certificate_field_invalid") from error
    _require_hex64(certificate.get("bundle_sha256"), "certificate_field_invalid")
    stages = _require_mapping(certificate.get("stages"), "certificate_field_invalid")
    for name in ("inputs", "performance_smoke", "run_a", "run_b", "comparison"):
        stage = _require_mapping(stages.get(name), "certificate_field_invalid")
        if stage.get("status") != "passed":
            raise CertificateError("certificate_stage_not_passed")
        if name in {"run_a", "run_b"}:
            _require_hex64(stage.get("output_sha256"), "certificate_field_invalid")
            if stage.get("kernel_version") != 1:
                raise CertificateError("certificate_field_invalid")
        if name == "comparison":
            _require_hex64(stage.get("result_sha256"), "certificate_field_invalid")
            if stage.get("kernel_version") != 1:
                raise CertificateError("certificate_field_invalid")
    claimed = certificate.pop("certificate_payload_sha256", None)
    try:
        actual = _sha256_hex(_canonical_bytes(certificate))
    finally:
        certificate["certificate_payload_sha256"] = claimed
    if not isinstance(claimed, str) or claimed != actual:
        raise CertificateError("certificate_digest_mismatch")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    certify = commands.add_parser("certify")
    certify.add_argument("--repo-root", type=Path, required=True)
    certify.add_argument("--chain-audit-id", required=True)
    certify.add_argument("--registry", type=Path)
    certify.add_argument("--out", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--certificate", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "certify":
            certificate = build_certificate(
                repo_root=arguments.repo_root,
                chain_audit_id=arguments.chain_audit_id,
                registry_path=arguments.registry,
            )
            arguments.out.write_bytes(_canonical_bytes(certificate) + b"\n")
            print(
                f"core_execution_certificate=PASS chain={arguments.chain_audit_id} "
                + f"payload={certificate['certificate_payload_sha256']}"
            )
        else:
            certificate = _require_mapping(
                json.loads(arguments.certificate.read_text()), "certificate_unreadable"
            )
            verify_certificate(certificate)
            print("core_execution_certificate_verify=PASS")
    except CertificateError as error:
        print(f"core_execution_certificate=FAIL code={error}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
