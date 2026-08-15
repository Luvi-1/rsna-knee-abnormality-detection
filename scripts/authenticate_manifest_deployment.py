"""Authenticate one private manifest-audit dataset and kernel deployment."""

from __future__ import annotations

import argparse
import hashlib
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from scripts import package_manifest_bundle as packager
from scripts import validate_dicom_qa_output as remote
from scripts import validate_manifest_output as output


class DeploymentAuthenticationError(RuntimeError):
    """A fixed deployment-authentication error without inspected contents."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _deployment_refs(
    *,
    run_config: Mapping[str, Any],
    dataset_metadata_path: Path,
    kernel_metadata_path: Path,
) -> tuple[str, str, str]:
    commit = run_config.get("code_commit")
    bundle = run_config.get("bundle_sha256")
    competition = run_config.get("competition")
    if (
        not isinstance(commit, str)
        or remote.HEX_40.fullmatch(commit) is None
        or not isinstance(bundle, str)
        or remote.HEX_64.fullmatch(bundle) is None
        or not isinstance(competition, dict)
        or not isinstance(competition.get("slug"), str)
    ):
        raise DeploymentAuthenticationError("deployment_identity_invalid")
    dataset_slug = f"rsna-knee-manifest-bundle-{commit[:7]}-{bundle[:12]}"
    kernel_slug = f"rsna-knee-manifest-audit-{commit[:7]}-{bundle[:12]}"
    dataset = output._json_object(
        dataset_metadata_path, output.MAX_POLICY_BYTES, "deployment_identity_invalid"
    )
    kernel = output._json_object(
        kernel_metadata_path, output.MAX_POLICY_BYTES, "deployment_identity_invalid"
    )
    dataset_ref = dataset.get("id")
    kernel_ref = kernel.get("id")
    if not isinstance(dataset_ref, str) or not isinstance(kernel_ref, str):
        raise DeploymentAuthenticationError("deployment_identity_invalid")
    dataset_owner, separator, observed_dataset_slug = dataset_ref.partition("/")
    kernel_owner, kernel_separator, observed_kernel_slug = kernel_ref.partition("/")
    expected_description = (
        "PRIVATE TEAM-ONLY offline code/configuration/Linux-wheel bundle. All rights reserved. "
        "Contains no competition data, DICOM pixels, reports, patient metadata, credentials, "
        "checkpoints, or predictions. Do not publish or share."
    )
    if (
        not separator
        or not kernel_separator
        or dataset_owner != kernel_owner
        or remote._validated_dataset_ref(dataset_ref) != (dataset_owner, dataset_slug)
        or observed_dataset_slug != dataset_slug
        or observed_kernel_slug != kernel_slug
        or dataset
        != {
            "title": dataset_slug,
            "id": dataset_ref,
            "licenses": [{"name": "other"}],
            "description": expected_description,
        }
        or kernel
        != {
            "id": kernel_ref,
            "title": kernel_slug,
            "code_file": "run.py",
            "language": "python",
            "kernel_type": "script",
            "is_private": True,
            "enable_gpu": False,
            "enable_tpu": False,
            "enable_internet": False,
            "machine_shape": "",
            "dataset_sources": [dataset_ref],
            "competition_sources": [competition["slug"]],
            "kernel_sources": [],
            "model_sources": [],
        }
    ):
        raise DeploymentAuthenticationError("deployment_identity_invalid")
    return dataset_ref, kernel_ref, cast(str, competition["slug"])


def authenticate_manifest_deployment(
    *,
    run_config: Mapping[str, Any],
    manifest: Mapping[str, Any],
    bundle_manifest_path: Path,
    dataset_metadata_path: Path,
    kernel_metadata_path: Path,
    stage: str,
) -> str | None:
    if stage not in {"local", "inputs", "status", "kernel", "complete"}:
        raise DeploymentAuthenticationError("deployment_stage_invalid")
    dataset_ref, kernel_ref, competition_slug = _deployment_refs(
        run_config=run_config,
        dataset_metadata_path=dataset_metadata_path,
        kernel_metadata_path=kernel_metadata_path,
    )
    try:
        dataset_root = bundle_manifest_path.parent.resolve(strict=True)
        kernel_root = kernel_metadata_path.parent.resolve(strict=True)
        if (
            bundle_manifest_path.name != "bundle-manifest.json"
            or dataset_metadata_path.name != "dataset-metadata.json"
            or dataset_metadata_path.parent.resolve(strict=True) != dataset_root
            or kernel_metadata_path.name != "kernel-metadata.json"
            or kernel_root != dataset_root.parent / "kernel"
        ):
            raise DeploymentAuthenticationError("deployment_identity_invalid")
    except OSError as error:
        raise DeploymentAuthenticationError("deployment_identity_invalid") from error
    kernel_record = manifest.get("kernel")
    if (
        not isinstance(kernel_record, dict)
        or kernel_record.get("code_file") != "run.py"
        or not isinstance(kernel_record.get("sha256"), str)
        or remote.HEX_64.fullmatch(cast(str, kernel_record["sha256"])) is None
    ):
        raise DeploymentAuthenticationError("deployment_identity_invalid")
    kernel_directory = kernel_metadata_path.parent
    try:
        kernel_entries = {path.name: path for path in kernel_directory.iterdir()}
    except OSError as error:
        raise DeploymentAuthenticationError("deployment_identity_invalid") from error
    if set(kernel_entries) != {"run.py", "kernel-metadata.json"}:
        raise DeploymentAuthenticationError("deployment_identity_invalid")
    kernel_payload = output._read_bounded(
        kernel_entries["run.py"], output.MAX_POLICY_BYTES, "deployment_identity_invalid"
    )
    if hashlib.sha256(kernel_payload).hexdigest() != kernel_record["sha256"]:
        raise DeploymentAuthenticationError("deployment_identity_invalid")

    wheels = sorted(dataset_metadata_path.parent.glob("*.whl"))
    if not wheels:
        raise DeploymentAuthenticationError("deployment_identity_invalid")
    for wheel in wheels:
        packager._validate_linux_wheel(wheel)
    if stage == "local":
        return None

    remote._supported_kaggle_cli_interpreter()
    if stage == "status":
        api_before = remote._authenticate_kernel_api_version(kernel_ref, 1)
        status = _kernel_status(kernel_ref)
        if api_before != remote._authenticate_kernel_api_version(kernel_ref, 1):
            raise DeploymentAuthenticationError("kernel_version_race")
        return status

    content = remote._bundle_dataset_content_policy(manifest)
    files = {name: size for name, (size, _digest) in content.items()}
    dataset_before = remote._authenticated_dataset_snapshot(dataset_ref, files)
    remote._authenticate_dataset_content(
        dataset_ref,
        content,
        deadline=time.monotonic() + remote.MAX_DATASET_CONTENT_SECONDS,
    )
    if stage == "inputs":
        if dataset_before != remote._authenticated_dataset_snapshot(dataset_ref, files):
            raise DeploymentAuthenticationError("dataset_version_race")
        return None

    api_before = remote._authenticate_kernel_api_version(kernel_ref, 1)
    if stage == "complete":
        remote._kernel_status_complete(kernel_ref)
    kernel_before = remote._pull_and_verify_exact_kernel(
        kernel_ref,
        1,
        "run.py",
        cast(str, kernel_record["sha256"]),
        expected_kernel_type="script",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=[],
        expected_competition_sources=[competition_slug],
    )
    if stage == "complete":
        output_policy = run_config.get("output_policy")
        private_policy = (
            output_policy.get("private_remote_only") if isinstance(output_policy, dict) else None
        )
        remote._validate_source_manifest_listing(
            remote._authenticated_listing(kernel_ref, 1),
            {"private_output_policy": private_policy},
        )
        remote._kernel_status_complete(kernel_ref)
    api_after = remote._authenticate_kernel_api_version(kernel_ref, 1)
    kernel_after = remote._pull_and_verify_exact_kernel(
        kernel_ref,
        1,
        "run.py",
        cast(str, kernel_record["sha256"]),
        expected_kernel_type="script",
        expected_dataset_sources=[dataset_ref],
        expected_kernel_sources=[],
        expected_competition_sources=[competition_slug],
    )
    dataset_after = remote._authenticated_dataset_snapshot(dataset_ref, files)
    if api_before != api_after or kernel_before != kernel_after:
        raise DeploymentAuthenticationError("kernel_version_race")
    if dataset_before != dataset_after:
        raise DeploymentAuthenticationError("dataset_version_race")
    return None


def _kernel_status(ref: str) -> str:
    payload = remote._run_kaggle_cli(("kernels", "status", ref), maximum=16 * 1024)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DeploymentAuthenticationError("kernel_status_invalid") from error
    match = re.fullmatch(re.escape(ref) + r' has status "([^"\r\n]+)"\s*', text)
    if match is None:
        raise DeploymentAuthenticationError("kernel_status_invalid")
    value = match.group(1)
    for status in ("PENDING", "RUNNING", "COMPLETE", "ERROR"):
        if value in {status.lower(), status, f"KernelWorkerStatus.{status}"}:
            return status
    raise DeploymentAuthenticationError("kernel_status_invalid")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-config", type=Path, required=True)
    parser.add_argument("--bundle-manifest", type=Path, required=True)
    parser.add_argument("--dataset-metadata", type=Path, required=True)
    parser.add_argument("--kernel-metadata", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-bundle", required=True)
    parser.add_argument(
        "--stage", choices=("local", "inputs", "status", "kernel", "complete"), required=True
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        run_config, _runner = output.load_verified_policy(
            args.run_config,
            args.bundle_manifest,
            expected_commit=args.expected_commit,
            expected_bundle=args.expected_bundle,
        )
        manifest = output._json_object(
            args.bundle_manifest, output.MAX_POLICY_BYTES, "bundle_manifest_invalid"
        )
        status = authenticate_manifest_deployment(
            run_config=run_config,
            manifest=manifest,
            bundle_manifest_path=args.bundle_manifest,
            dataset_metadata_path=args.dataset_metadata,
            kernel_metadata_path=args.kernel_metadata,
            stage=args.stage,
        )
    except (
        DeploymentAuthenticationError,
        output.OutputValidationError,
        packager.PackagingError,
    ) as error:
        print(f"manifest_deployment_authentication=FAIL code={error.code}")
        return 2
    except remote.OutputValidationError as error:
        print(f"manifest_deployment_authentication=FAIL code={error.code}")
        return 2
    except Exception:
        print("manifest_deployment_authentication=FAIL code=internal_error")
        return 2
    if status is not None:
        print(f"manifest_deployment_status={status}")
    else:
        print(f"manifest_deployment_authentication=PASS stage={args.stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
