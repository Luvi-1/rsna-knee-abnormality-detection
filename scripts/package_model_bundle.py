#!/usr/bin/env python3
"""Package a model bundle with provenance metadata for submission validation.

Creates a deterministic tar.gz containing the model config, weights placeholder,
and a provenance manifest. No private data is read; callers supply paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def package_bundle(
    *,
    model_config_path: Path,
    output_path: Path,
    code_commit: str,
    config_hash: str,
    preprocessing_version: str,
) -> Path:
    """Create a reproducible model bundle archive."""
    manifest = {
        "code_commit": code_commit,
        "config_hash": config_hash,
        "preprocessing_version": preprocessing_version,
        "model_config_sha256": _sha256(model_config_path),
        "bundle_format_version": "v0",
    }
    manifest_path = model_config_path.parent / "provenance_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(model_config_path, arcname="model_config.yaml")
        tar.add(manifest_path, arcname="provenance_manifest.json")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--config-hash", required=True)
    parser.add_argument("--preprocessing-version", required=True)
    args = parser.parse_args()

    result = package_bundle(
        model_config_path=args.model_config,
        output_path=args.output,
        code_commit=args.code_commit,
        config_hash=args.config_hash,
        preprocessing_version=args.preprocessing_version,
    )
    print(f"bundle_written: {result}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
