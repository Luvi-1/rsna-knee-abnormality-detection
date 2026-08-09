"""Fail when tracked files look like data, secrets, private outputs, or large artifacts."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

BLOCKED_ROOTS = {
    "artifacts",
    "checkpoints",
    "data",
    "outputs",
    "private_outputs",
    "raw_reports",
    "reports",
    "wandb",
}
BLOCKED_NAMES = {
    ".env",
    ".netrc",
    "access_token",
    "audit_key.bin",
    "completed_review_ledger.json",
    "kaggle.json",
    "private_artifact_inventory.json",
    "private_case_index.json",
    "private_duplicate_groups.csv",
    "private_full_run_manifest.jsonl",
    "private_full_run_metrics.json",
    "private_human_review_completion.json",
    "private_preliminary_group_keys.csv",
    "private_qa_samples.csv",
    "private_review_plan.json",
    "private_run_comparison.json",
}
BLOCKED_SUFFIXES = {
    ".7z",
    ".ckpt",
    ".db",
    ".dcm",
    ".gif",
    ".h5",
    ".hdf5",
    ".jpeg",
    ".jpg",
    ".nii",
    ".npy",
    ".npz",
    ".onnx",
    ".parquet",
    ".png",
    ".pt",
    ".pth",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".webp",
    ".zip",
}
BLOCKED_DIRECTORY_SUFFIXES = {".zarr"}
BLOCKED_DIRECTORY_NAMES = {"private-review"}
BLOCKED_NAME_PATTERN = re.compile(
    r"case_[0-9]{6}_series_[0-9]{3}_(?:metadata|review)\.json\Z", re.IGNORECASE
)
MAX_TRACKED_BYTES = 10 * 1024 * 1024


def tracked_files() -> list[Path]:
    result = subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True)
    return [Path(raw.decode()) for raw in result.stdout.split(b"\0") if raw]


def violations(paths: list[Path]) -> list[str]:
    problems: list[str] = []
    for path in paths:
        if path.parts and path.parts[0] in BLOCKED_ROOTS:
            problems.append(f"blocked root: {path}")
        if any(part.lower() in BLOCKED_DIRECTORY_NAMES for part in path.parts):
            problems.append(f"blocked private output directory: {path}")
        if any(part.lower().endswith(tuple(BLOCKED_DIRECTORY_SUFFIXES)) for part in path.parts):
            problems.append(f"blocked artifact directory: {path}")
        if (
            path.name.lower() in BLOCKED_NAMES
            or BLOCKED_NAME_PATTERN.fullmatch(path.name)
            or path.suffix.lower() in BLOCKED_SUFFIXES
        ):
            problems.append(f"blocked file: {path}")
        if path.is_file() and path.stat().st_size > MAX_TRACKED_BYTES:
            problems.append(f"oversized tracked file: {path}")
    return problems


def main() -> None:
    problems = violations(tracked_files())
    if problems:
        raise SystemExit("\n".join(problems))
    print("sensitive_file_guard=PASS")


if __name__ == "__main__":
    main()
