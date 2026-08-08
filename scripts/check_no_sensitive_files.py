"""Fail when tracked files look like data, secrets, private outputs, or large artifacts."""

from __future__ import annotations

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
BLOCKED_NAMES = {".env", ".netrc", "access_token", "kaggle.json"}
BLOCKED_SUFFIXES = {
    ".7z",
    ".ckpt",
    ".db",
    ".dcm",
    ".nii",
    ".onnx",
    ".parquet",
    ".pt",
    ".pth",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".zip",
}
MAX_TRACKED_BYTES = 10 * 1024 * 1024


def tracked_files() -> list[Path]:
    result = subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True)
    return [Path(raw.decode()) for raw in result.stdout.split(b"\0") if raw]


def violations(paths: list[Path]) -> list[str]:
    problems: list[str] = []
    for path in paths:
        if path.parts and path.parts[0] in BLOCKED_ROOTS:
            problems.append(f"blocked root: {path}")
        if path.name in BLOCKED_NAMES or path.suffix.lower() in BLOCKED_SUFFIXES:
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
