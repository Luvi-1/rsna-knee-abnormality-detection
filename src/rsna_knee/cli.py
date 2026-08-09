"""Command-line entry point for approved competition workflows."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, ValidationError

from rsna_knee.competition_contract import contract_error_summary
from rsna_knee.config import config_hash, load_experiment_config
from rsna_knee.dicom.benchmark import BenchmarkReport, benchmark_dicom_pipeline
from rsna_knee.dicom.pipeline import (
    PREPROCESSING_VERSION,
    NormalizationMode,
    PipelineError,
    PipelineVersions,
    PreprocessedSeries,
    PreprocessingConfig,
    dicom_to_model,
)
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
DEFERRED_COMMANDS = frozenset(COMMANDS) - {"audit", "preprocess", "validate-submission"}


class _PreprocessingFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    preprocessing_version: Literal["dicom-model-v1"]
    lower_percentile: float
    upper_percentile: float
    normalization: Literal["minmax", "zscore", "none"]
    sample_count: int | None
    local_contrast_channel: bool
    local_contrast_window: int
    adjacent_slice_channels: bool
    difference_channel: bool
    resize_rows_columns: tuple[int, int] | None
    allow_instance_fallback_for_qa: bool
    horizontal_flip: Literal[False]
    through_plane_resampling: Literal[False]

    def pipeline_config(self) -> PreprocessingConfig:
        return PreprocessingConfig(
            lower_percentile=self.lower_percentile,
            upper_percentile=self.upper_percentile,
            normalization=NormalizationMode(self.normalization),
            sample_count=self.sample_count,
            local_contrast_channel=self.local_contrast_channel,
            local_contrast_window=self.local_contrast_window,
            adjacent_slice_channels=self.adjacent_slice_channels,
            difference_channel=self.difference_channel,
            resize_rows_columns=self.resize_rows_columns,
            allow_instance_fallback_for_qa=self.allow_instance_fallback_for_qa,
        )


def load_preprocessing_config(path: Path) -> PreprocessingConfig:
    """Load all hashed parameters; fixed version/safety policy travels separately."""

    parsed = _PreprocessingFile.model_validate_json(path.read_bytes())
    if parsed.preprocessing_version != PREPROCESSING_VERSION:
        raise ValueError("preprocessing_version_mismatch")
    return parsed.pipeline_config()


def _input_paths(input_directory: Path) -> tuple[Path, ...]:
    if input_directory.is_symlink() or not input_directory.is_dir():
        raise ValueError("input_directory_invalid")
    entries = tuple(input_directory.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise ValueError("input_directory_contains_unsupported_entry")
    paths = tuple(sorted(entries, key=lambda path: path.name))
    if not paths:
        raise ValueError("input_directory_empty")
    return paths


def _output_metadata(result: PreprocessedSeries) -> dict[str, object]:
    return {
        "schema_version": 1,
        "tensor": {
            "file": "tensor.npy",
            "shape": list(result.tensor.shape),
            "dtype": str(result.tensor.dtype),
        },
        "channel_names": result.channel_names,
        "sampled_ordered_indices": result.sampled_ordered_indices,
        "sampled_projected_positions_mm": result.sampled_projected_positions_mm,
        "geometry": asdict(result.geometry),
        "transformation_ledger": asdict(result.ledger),
        "laterality": result.laterality,
        "clipping_values": result.clipping_values,
        "normalization_statistics": result.normalization_statistics,
        "output_pixel_spacing_row_column_mm": result.output_pixel_spacing_row_column_mm,
        "output_affine_lps_slice_row_column": result.output_affine_lps_slice_row_column,
        "provenance": asdict(result.provenance),
    }


def _canonical_json(payload: object) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def _write_preprocessed_output(
    output_directory: Path,
    result: PreprocessedSeries,
    benchmark: BenchmarkReport | None,
) -> None:
    if output_directory.exists():
        raise ValueError("output_directory_exists")
    output_parent = output_directory.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".rsna-knee-preprocess-", dir=output_parent) as name:
        temporary = Path(name)
        temporary.chmod(0o700)
        tensor_path = temporary / "tensor.npy"
        metadata_path = temporary / "metadata.json"
        with tensor_path.open("wb") as stream:
            np.save(stream, result.tensor, allow_pickle=False)
        metadata_path.write_bytes(_canonical_json(_output_metadata(result)))
        tensor_path.chmod(0o600)
        metadata_path.chmod(0o600)
        if benchmark is not None:
            benchmark_path = temporary / "benchmark.json"
            benchmark_path.write_bytes(_canonical_json(benchmark.to_dict()))
            benchmark_path.chmod(0o600)
        temporary.rename(output_directory)
    os.chmod(output_directory, 0o700)


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

    preprocess = subparsers.add_parser(
        "preprocess", help="create one private model-ready series artifact"
    )
    preprocess.add_argument("--config", type=Path, required=True)
    preprocess.add_argument("--input-dir", type=Path, required=True)
    preprocess.add_argument("--output-dir", type=Path, required=True)
    preprocess.add_argument("--code-commit", required=True)
    preprocess.add_argument("--source-manifest-version", required=True)
    preprocess.add_argument("--benchmark", action="store_true")
    preprocess.add_argument("--benchmark-iterations", type=int, default=3)
    preprocess.add_argument("--benchmark-workers", type=int, nargs="+", default=[1, 2])

    for command in sorted(DEFERRED_COMMANDS):
        subparsers.add_parser(command, help="reserved for an approved later chunk")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "audit":
        experiment_config = load_experiment_config(args.config)
        print(f"config_valid=yes config_hash={config_hash(experiment_config)}")
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
    if args.command == "preprocess":
        try:
            input_directory = Path(args.input_dir)
            output_directory = Path(args.output_dir)
            if output_directory.resolve(strict=False).is_relative_to(
                input_directory.resolve(strict=False)
            ):
                raise ValueError("output_inside_input")
            preprocessing_config = load_preprocessing_config(Path(args.config))
            paths = _input_paths(input_directory)
            versions = PipelineVersions(
                code_commit=str(args.code_commit),
                source_manifest_version=str(args.source_manifest_version),
            )
            result = dicom_to_model(paths, preprocessing_config, versions)
            benchmark = (
                benchmark_dicom_pipeline(
                    paths,
                    preprocessing_config,
                    versions,
                    iterations=int(args.benchmark_iterations),
                    worker_counts=tuple(int(value) for value in args.benchmark_workers),
                )
                if bool(args.benchmark)
                else None
            )
            _write_preprocessed_output(output_directory, result, benchmark)
        except PipelineError as error:
            print(
                f"preprocess_status=failed reason={error.issue.value} stage={error.stage}",
                file=sys.stderr,
            )
            return 2
        except (OSError, UnicodeError, RuntimeError, ValueError, ValidationError):
            print("preprocess_status=failed reason=input_or_config_invalid", file=sys.stderr)
            return 2
        print("preprocess_status=complete")
        return 0
    print(f"{args.command} is gated until a later approved chunk", file=sys.stderr)
    return 2


def main() -> None:
    raise SystemExit(run())
