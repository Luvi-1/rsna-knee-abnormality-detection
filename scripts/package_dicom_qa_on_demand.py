#!/usr/bin/env python3
"""Package the private r16 on-demand review as one content-addressed Kaggle notebook."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

REF = re.compile(r"[a-z0-9][a-z0-9_-]{0,49}/[a-z0-9][a-z0-9_-]{0,99}\Z")
HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
COMPETITION_SLUG: Final = "rsna-knee-abnormality-detection"
EXPECTED_SOURCE_DATASET_REF: Final = "lavicheema/rsna-knee-qa-source-artifacts-da5b9c8-r2"
NOTEBOOK_FILE: Final = "on_demand_review.ipynb"


class PackagingError(RuntimeError):
    """Fixed packaging failure."""


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, json.JSONDecodeError) as error:
        raise PackagingError("input_invalid") from error
    if not isinstance(value, dict):
        raise PackagingError("input_invalid")
    return value


def _record(manifest: Mapping[str, Any], role: str) -> Mapping[str, Any]:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise PackagingError("bundle_manifest_invalid")
    matches = [
        item
        for item in cast(list[object], files)
        if isinstance(item, dict) and item.get("role") == role
    ]
    if len(matches) != 1:
        raise PackagingError("bundle_manifest_invalid")
    return cast(Mapping[str, Any], matches[0])


def _git_identity(repo_root: Path) -> str:
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise PackagingError("git_identity_invalid") from error
    if status.stdout or HEX_40.fullmatch(commit) is None:
        raise PackagingError("git_tree_not_clean")
    return commit


def _notebook_payload(
    *,
    source: str,
    source_sha256: str,
    bundle_ref: str,
    source_dataset_ref: str,
    bundle_sha256: str,
    runner_sha256: str,
) -> bytes:
    invocation = "\n".join(
        (
            "import hashlib",
            "import sys",
            "import types",
            f"MODULE_SOURCE = {source!r}",
            f"EXPECTED_SOURCE_SHA256 = {source_sha256!r}",
            "if hashlib.sha256(MODULE_SOURCE.encode('utf-8')).hexdigest() != "
            "EXPECTED_SOURCE_SHA256:",
            "    raise RuntimeError('notebook_source_hash_mismatch')",
            "runtime_module = types.ModuleType('chunk5_on_demand_runtime')",
            "runtime_module.__file__ = 'on_demand_review.py'",
            "sys.modules[runtime_module.__name__] = runtime_module",
            "exec(compile(MODULE_SOURCE, runtime_module.__file__, 'exec'), "
            "runtime_module.__dict__)",
            "exit_code = runtime_module.run_on_demand_review(",
            f"    bundle_dataset_ref={bundle_ref!r},",
            f"    source_dataset_ref={source_dataset_ref!r},",
            f"    expected_bundle_sha256={bundle_sha256!r},",
            f"    expected_runner_sha256={runner_sha256!r},",
            "    notebook_source_sha256=EXPECTED_SOURCE_SHA256,",
            ")",
            "if exit_code != 0:",
            "    raise RuntimeError('on_demand_review_failed')",
        )
    )
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "id": "chunk5-overview",
                "metadata": {},
                "source": (
                    "# Chunk 5 private on-demand DICOM QA\n"
                    "Private, offline, research-only human review. Stop all automation before "
                    "typing `START`.\n"
                ),
            },
            {
                "cell_type": "code",
                "id": "chunk5-on-demand-review",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": invocation + "\n",
            },
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return _canonical_json_bytes(notebook)


def package(
    *,
    repo_root: Path,
    bundle_root: Path,
    bundle_ref: str,
    output_root: Path,
) -> dict[str, str]:
    if REF.fullmatch(bundle_ref) is None or output_root.exists():
        raise PackagingError("argument_invalid")
    commit = _git_identity(repo_root)
    module_path = repo_root / "kaggle/dicom_qa/on_demand_review.py"
    manifest = _json(bundle_root / "bundle-manifest.json")
    run_record = _record(manifest, "run_config")
    runner_record = _record(manifest, "runner_source")
    wheel_record = _record(manifest, "project_wheel")
    bundle_sha256 = manifest.get("bundle_sha256")
    if (
        HEX_64.fullmatch(str(bundle_sha256)) is None
        or not isinstance(run_record.get("path"), str)
        or not isinstance(runner_record.get("path"), str)
        or not isinstance(runner_record.get("sha256"), str)
        or HEX_64.fullmatch(cast(str, runner_record["sha256"])) is None
        or not isinstance(wheel_record.get("path"), str)
    ):
        raise PackagingError("bundle_manifest_invalid")
    runner_path = bundle_root / cast(str, runner_record["path"])
    if _sha256_file(runner_path) != runner_record["sha256"]:
        raise PackagingError("runner_source_hash_mismatch")
    run_config = _json(bundle_root / cast(str, run_record["path"]))
    producer_ref = run_config.get("input_identity", {}).get("source_manifest", {}).get("kernel_ref")
    owner = run_config.get("deployment", {}).get("owner")
    if REF.fullmatch(str(producer_ref)) is None or not isinstance(owner, str):
        raise PackagingError("source_identity_invalid")
    try:
        source = module_path.read_text(encoding="utf-8")
        source_sha256 = hashlib.sha256(source.encode()).hexdigest()
        wheel_path = bundle_root / cast(str, wheel_record["path"])
        with zipfile.ZipFile(wheel_path) as archive:
            selector_sha256 = hashlib.sha256(
                archive.read("rsna_knee/data/qa_strata.py")
            ).hexdigest()
    except (OSError, UnicodeError, KeyError, zipfile.BadZipFile) as error:
        raise PackagingError("source_invalid") from error
    slug = f"rsna-knee-dqa-ondemand-{commit[:7]}-{source_sha256[:12]}"
    ref = f"{owner}/{slug}"
    if REF.fullmatch(ref) is None:
        raise PackagingError("kernel_ref_invalid")
    notebook_payload = _notebook_payload(
        source=source,
        source_sha256=source_sha256,
        bundle_ref=bundle_ref,
        source_dataset_ref=EXPECTED_SOURCE_DATASET_REF,
        bundle_sha256=cast(str, bundle_sha256),
        runner_sha256=cast(str, runner_record["sha256"]),
    )
    metadata = {
        "id": ref,
        "title": slug,
        "code_file": NOTEBOOK_FILE,
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": False,
        "enable_tpu": False,
        "enable_internet": False,
        "keywords": [],
        "dataset_sources": [bundle_ref, EXPECTED_SOURCE_DATASET_REF],
        "competition_sources": [COMPETITION_SLUG],
        "model_sources": [],
    }
    output_root.mkdir(parents=True)
    (output_root / NOTEBOOK_FILE).write_bytes(notebook_payload)
    (output_root / "kernel-metadata.json").write_bytes(_canonical_json_bytes(metadata))
    return {
        "kernel_ref": ref,
        "code_file": NOTEBOOK_FILE,
        "notebook_sha256": hashlib.sha256(notebook_payload).hexdigest(),
        "notebook_source_sha256": source_sha256,
        "selector_sha256": selector_sha256,
        "bundle_sha256": cast(str, bundle_sha256),
        "runner_sha256": cast(str, runner_record["sha256"]),
        "bundle_dataset_ref": bundle_ref,
        "source_dataset_ref": EXPECTED_SOURCE_DATASET_REF,
        "source_producer_kernel_ref": cast(str, producer_ref),
        "git_commit": commit,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--bundle-ref", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = package(
            repo_root=args.repo_root.resolve(strict=True),
            bundle_root=args.bundle_root.resolve(strict=True),
            bundle_ref=args.bundle_ref,
            output_root=args.output_root,
        )
    except PackagingError as error:
        print(f"on_demand_package=FAIL code={error}")
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
