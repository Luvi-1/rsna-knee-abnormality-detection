"""Discover and fingerprint high-scoring public RSNA Knee notebooks.

This command never submits to a competition. By default it only lists public
notebooks through the authenticated official Kaggle CLI. ``--pull-known`` may
pull the latest public source/output for known slugs into an ignored private
workspace; historical version pinning must still be verified separately.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

from rsna_knee.public_repro.score_first import (
    collect_pull_evidence,
    load_campaign,
    parse_kaggle_kernel_csv,
    prioritized_campaign,
    shortlist_listings,
)


DEFAULT_CONFIG = Path("configs/public_baseline/score_first_093.json")
DEFAULT_OUTPUT = Path("private_outputs/chunk4r/score_first_scan.json")
DEFAULT_PULL_ROOT = Path("private_outputs/chunk4r/score_first_pulls")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Screen public RSNA Knee notebooks without submitting anything."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--pull-root", type=Path, default=DEFAULT_PULL_ROOT)
    parser.add_argument("--minimum-score", type=float, default=0.93)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument(
        "--pull-known",
        action="store_true",
        help="Pull the latest source/output for configured slugs. This cannot pin older versions.",
    )
    return parser.parse_args(argv)


def run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run one sanitized CLI command and capture text output."""

    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not 0.0 <= args.minimum_score <= 1.0:
        raise SystemExit("--minimum-score must be within [0, 1]")
    if args.page_size < 1 or args.page_size > 100:
        raise SystemExit("--page-size must be between 1 and 100")

    campaign = prioritized_campaign(load_campaign(args.config))
    list_command = [
        "kaggle",
        "kernels",
        "list",
        "--competition",
        "rsna-knee-abnormality-detection",
        "--sort-by",
        "scoreDescending",
        "--page-size",
        str(args.page_size),
        "-v",
    ]
    listed = run_command(list_command)
    if listed.returncode != 0:
        sanitized_error = _sanitize_cli_error(listed.stderr or listed.stdout)
        raise SystemExit(f"Kaggle kernel listing failed: {sanitized_error}")

    listings = parse_kaggle_kernel_csv(listed.stdout)
    shortlist = shortlist_listings(listings, minimum_score=args.minimum_score)

    result: dict[str, Any] = {
        "schema_version": "score-first-scan-v1",
        "competition": "rsna-knee-abnormality-detection",
        "submission_performed": False,
        "minimum_score": args.minimum_score,
        "listing_count": len(listings),
        "shortlist": [
            {
                "ref": item.ref,
                "title": item.title,
                "score": item.score,
                "runtime_seconds": item.runtime_seconds,
                "version": item.version,
            }
            for item in shortlist
        ],
        "campaign": [
            {
                "candidate_id": item.candidate_id,
                "owner_slug": item.owner_slug,
                "required_version": item.required_version,
                "script_version_id": item.script_version_id,
                "source_reported_public_score": item.source_reported_public_score,
                "priority": item.priority,
                "status": item.status,
                "reason": item.reason,
            }
            for item in campaign
        ],
        "pulled_latest": [],
        "historical_version_warning": (
            "The official CLI pulls the latest source. A required historical version must be "
            "pinned through immutable Kaggle version evidence before reproduction."
        ),
    }

    if args.pull_known:
        for candidate in campaign:
            source_dir = args.pull_root / candidate.candidate_id / "source"
            output_dir = args.pull_root / candidate.candidate_id / "output"
            source_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            pull = run_command(
                [
                    "kaggle",
                    "kernels",
                    "pull",
                    candidate.owner_slug,
                    "-p",
                    str(source_dir),
                    "-m",
                ]
            )
            output = run_command(
                [
                    "kaggle",
                    "kernels",
                    "output",
                    candidate.owner_slug,
                    "-p",
                    str(output_dir),
                    "-q",
                ]
            )
            record: dict[str, Any] = {
                "candidate_id": candidate.candidate_id,
                "owner_slug": candidate.owner_slug,
                "required_version": candidate.required_version,
                "pull_returncode": pull.returncode,
                "output_returncode": output.returncode,
                "pull_error": _sanitize_cli_error(pull.stderr),
                "output_error": _sanitize_cli_error(output.stderr),
            }
            if pull.returncode == 0:
                evidence = collect_pull_evidence(
                    candidate.owner_slug,
                    source_dir,
                    output_dir,
                )
                record["evidence"] = evidence.to_json()
            result["pulled_latest"].append(record)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"score_first_scan={args.output}")
    print(f"listing_count={len(listings)}")
    print(f"score_qualified={len(shortlist)}")
    print("competition_submission_performed=false")
    return 0


def _sanitize_cli_error(value: str) -> str:
    """Return one bounded line without echoing environment or credential text."""

    if not value:
        return ""
    line = " ".join(value.split())
    lowered = line.lower()
    for marker in ("token", "authorization", "kaggle_key", "kaggle_username"):
        if marker in lowered:
            return "authentication or authorization failure; inspect locally"
    return line[:500]


if __name__ == "__main__":
    sys.exit(main())
