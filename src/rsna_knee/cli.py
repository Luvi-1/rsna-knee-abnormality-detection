"""Command-line entry point for approved competition workflows."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from rsna_knee.competition_contract import contract_error_summary
from rsna_knee.config import config_hash, load_experiment_config
from rsna_knee.submission import SubmissionValidationError, validate_submission

COMMANDS = (
    "audit",
    "preprocess",
    "label",
    "make-folds",
    "train",
    "evaluate",
    "infer",
    "ensemble",
    "validate-submission",
)
DEFERRED_COMMANDS = frozenset(COMMANDS) - {"audit", "validate-submission"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rsna-knee")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="validate an experiment contract")
    audit.add_argument("--config", type=Path, required=True)

    validate = subparsers.add_parser(
        "validate-submission", help="validate a submission CSV without submitting"
    )
    validate.add_argument("path", type=Path)
    validate.add_argument("--contract-config", type=Path, required=True)

    for command in sorted(DEFERRED_COMMANDS):
        subparsers.add_parser(command, help="reserved for an approved later chunk")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "audit":
        config = load_experiment_config(args.config)
        print(f"config_valid=yes config_hash={config_hash(config)}")
        return 0
    if args.command == "validate-submission":
        try:
            summary = validate_submission(args.path, args.contract_config)
        except SubmissionValidationError as error:
            print(f"submission_valid=no reason={error}", file=sys.stderr)
            return 2
        except (OSError, ValidationError) as error:
            print(
                f"submission_valid=no reason={contract_error_summary(error)}",
                file=sys.stderr,
            )
            return 2
        print(f"submission_valid=yes rows={summary.rows}")
        return 0
    print(f"{args.command} is gated until a later approved chunk", file=sys.stderr)
    return 2


def main() -> None:
    raise SystemExit(run())
