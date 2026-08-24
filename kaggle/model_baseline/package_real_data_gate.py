#!/usr/bin/env python3
"""Package the private real-data modeling gate as one content-addressed Kaggle notebook."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Final

REF = re.compile(r"[a-z0-9][a-z0-9_-]{0,49}/[a-z0-9][a-z0-9_-]{0,99}")
HEX_40 = re.compile(r"[0-9a-f]{40}")
COMPETITION_SLUG = "rsna-knee-abnormality-detection"
BUNDLE_DATASET_REF = "lavicheema/rsna-knee-dicom-qa-bundle-da5b9c8-91ed07921059"
NOTEBOOK_FILE = "real_data_gate.ipynb"
GATE_ENTRY_POINTS: Final = {
    "e00_skip_audit": "run_skip_audit",
    "e00b": "run_e00b_memorization_gate",
    "e00c": "run_e00c_cnn_memorization_gate",
    "default": "run_real_data_gate",
}


class PackagingError(RuntimeError):
    """Fixed packaging failure."""


def _canonical_json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def _git_identity(repo_root):
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


def _notebook_payload(source, source_sha256, entry_point="run_e00b_memorization_gate"):
    invocation = "\n".join(
        (
            "import hashlib",
            "import sys",
            "import types",
            f"MODULE_SOURCE = {source!r}",
            f"EXPECTED_SOURCE_SHA256 = {source_sha256!r}",
            "if hashlib.sha256(MODULE_SOURCE.encode('utf-8')).hexdigest()"
            " != EXPECTED_SOURCE_SHA256:",
            "    raise RuntimeError('notebook_source_hash_mismatch')",
            "runtime_module = types.ModuleType('rsna_model_gate_runtime')",
            "runtime_module.__file__ = 'real_data_gate.py'",
            "sys.modules[runtime_module.__name__] = runtime_module",
            "exec(compile(MODULE_SOURCE, runtime_module.__file__, 'exec'),"
            " runtime_module.__dict__)",
            f"exit_code = runtime_module.{entry_point}()",
            "if exit_code != 0:",
            "    raise RuntimeError('real_data_gate_failed')",
        )
    )
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "id": "model-gate-overview",
                "metadata": {},
                "source": (
                    "# RSNA Knee real-data modeling gate\n"
                    "Private offline fold-feasibility and tiny-overfit proof. "
                    "Human QA remains PROVISIONAL_HUMAN_QA_PENDING. No submission is created."
                ),
            },
            {
                "cell_type": "code",
                "id": "model-gate-execution",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": invocation + "\n",
            },
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return _canonical_json_bytes(notebook)


def package(repo_root, output_root, commit=None, gate=None):
    """Package with the live clean-tree commit, or an explicit commit for tests."""
    if commit is not None and HEX_40.fullmatch(commit) is None:
        raise PackagingError("argument_invalid")
    entry_point = GATE_ENTRY_POINTS[gate or "default"]
    enable_gpu = gate == "e00c"
    if output_root.exists():
        raise PackagingError("output_root_exists")
    output_root.mkdir(parents=False)
    if commit is None:
        commit = _git_identity(repo_root)
    module_path = repo_root / "kaggle/model_baseline/real_data_gate.py"
    try:
        source = module_path.read_text(encoding="utf-8")
        compile(source, str(module_path), "exec")
    except (OSError, UnicodeError, SyntaxError) as error:
        raise PackagingError("gate_source_invalid") from error
    source_sha256 = hashlib.sha256(source.encode()).hexdigest()
    gate_suffix = "" if gate is None else f"-{gate.replace('_', '-')}"
    slug = f"rsna-knee-model-gate-{commit[:7]}-{source_sha256[:12]}{gate_suffix}"
    ref = f"lavicheema/{slug}"
    if REF.fullmatch(ref) is None:
        raise PackagingError("kernel_ref_invalid")
    (output_root / NOTEBOOK_FILE).write_bytes(
        _notebook_payload(source, source_sha256, entry_point=entry_point)
    )
    metadata = {
        "code_file": NOTEBOOK_FILE,
        "competition_sources": [COMPETITION_SLUG],
        "dataset_sources": [BUNDLE_DATASET_REF],
        "enable_gpu": enable_gpu,
        "enable_internet": False,
        "enable_tpu": False,
        "id": ref,
        "is_private": True,
        "kernel_type": "notebook",
        "keywords": [],
        "language": "python",
        "model_sources": [],
        "title": slug,
    }
    (output_root / "kernel-metadata.json").write_bytes(_canonical_json_bytes(metadata))
    return {"kernel_ref": ref, "kernel_slug": slug, "source_sha256": source_sha256}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--gate", choices=tuple(GATE_ENTRY_POINTS), default=None)
    args = parser.parse_args()
    result = package(args.repo_root, args.output_root, gate=args.gate)
    print(result["kernel_ref"], file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
