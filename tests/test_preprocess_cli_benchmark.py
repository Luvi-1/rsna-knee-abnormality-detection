from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from pydantic import ValidationError
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage

from rsna_knee.cli import load_preprocessing_config, run
from rsna_knee.dicom.benchmark import benchmark_dicom_pipeline
from rsna_knee.dicom.pipeline import (
    NormalizationMode,
    PipelineVersions,
    PreprocessingConfig,
    preprocessing_config_hash,
)

ROOT = Path(__file__).parents[1]
VERSIONS = PipelineVersions(
    code_commit="a" * 40,
    source_manifest_version="synthetic-manifest-v1",
)


def _write_synthetic_slice(path: Path, *, index: int, position: float) -> None:
    y, x = np.mgrid[:8, :9]
    pixels: NDArray[np.uint16] = np.asarray(3 * y + 7 * x + 11 * index, dtype=np.uint16)
    uid = f"1.2.826.0.1.3680043.10.543.900{index}"
    file_meta = FileMetaDataset()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.MediaStorageSOPClassUID = MRImageStorage
    file_meta.MediaStorageSOPInstanceUID = uid
    file_meta.ImplementationClassUID = "1.2.826.0.1.3680043.10.543.99"
    dataset = FileDataset(None, {}, file_meta=file_meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = MRImageStorage
    dataset.SOPInstanceUID = uid
    dataset.Modality = "MR"
    dataset.Rows, dataset.Columns = pixels.shape
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.PixelRepresentation = 0
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    dataset.ImagePositionPatient = [0.0, 0.0, position]
    dataset.InstanceNumber = 100 - index
    dataset.PixelSpacing = [0.5, 0.75]
    dataset.SliceThickness = 1.0
    dataset.SpacingBetweenSlices = 1.0
    dataset.RescaleSlope = 1.0
    dataset.RescaleIntercept = 0.0
    dataset.ImageLaterality = "L"
    dataset.PixelData = pixels.astype("<u2").tobytes(order="C")
    dataset.save_as(path, enforce_file_format=True)


def _synthetic_series(root: Path, *, extensionless: bool = False) -> tuple[Path, ...]:
    root.mkdir()
    names = (
        ("z-slice", "a-slice", "m-slice")
        if extensionless
        else (
            "z-slice.dcm",
            "a-slice.dcm",
            "m-slice.dcm",
        )
    )
    paths = tuple(root / name for name in names)
    for index, path in enumerate(paths):
        _write_synthetic_slice(path, index=index, position=float(index))
    return paths


def test_checked_in_preprocessing_config_is_strict_and_anatomically_safe(
    tmp_path: Path,
) -> None:
    config_path = ROOT / "configs" / "preprocessing.v1.json"
    config = load_preprocessing_config(config_path)
    schema = json.loads((ROOT / "configs" / "preprocessing.v1.schema.json").read_text())

    assert len(preprocessing_config_hash(config)) == 64
    assert config.resize_rows_columns is None
    assert not config.allow_instance_fallback_for_qa
    assert schema["additionalProperties"] is False
    assert schema["properties"]["horizontal_flip"] == {"const": False}
    assert schema["properties"]["through_plane_resampling"] == {"const": False}

    hashes = {
        preprocessing_config_hash(candidate)
        for candidate in (
            config,
            replace(config, lower_percentile=2.0),
            replace(config, upper_percentile=98.0),
            replace(config, normalization=NormalizationMode.ZSCORE),
            replace(config, sample_count=23),
            replace(config, local_contrast_channel=True),
            replace(config, local_contrast_window=9),
            replace(config, adjacent_slice_channels=True),
            replace(config, difference_channel=True),
            replace(config, resize_rows_columns=(8, 9)),
            replace(config, allow_instance_fallback_for_qa=True),
        )
    }
    assert len(hashes) == 11

    unsafe = json.loads(config_path.read_text())
    unsafe["horizontal_flip"] = True
    unsafe["private_unknown"] = "must-not-echo"
    unsafe_path = tmp_path / "unsafe.json"
    unsafe_path.write_text(json.dumps(unsafe))
    with pytest.raises(ValidationError):
        load_preprocessing_config(unsafe_path)


def test_preprocess_cli_uses_physical_order_and_writes_private_aggregate_benchmark(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_directory = tmp_path / "private-series-name"
    _synthetic_series(input_directory)
    output_directory = tmp_path / "private-output-name"

    status = run(
        [
            "preprocess",
            "--config",
            str(ROOT / "configs" / "preprocessing.v1.json"),
            "--input-dir",
            str(input_directory),
            "--output-dir",
            str(output_directory),
            "--code-commit",
            "a" * 40,
            "--source-manifest-version",
            "synthetic-manifest-v1",
            "--benchmark",
            "--benchmark-iterations",
            "1",
            "--benchmark-workers",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert status == 0
    assert captured.out == "preprocess_status=complete\n"
    assert captured.err == ""
    assert input_directory.name not in captured.out
    assert output_directory.name not in captured.out
    assert sorted(path.name for path in output_directory.iterdir()) == [
        "benchmark.json",
        "metadata.json",
        "tensor.npy",
    ]

    tensor = np.load(output_directory / "tensor.npy", allow_pickle=False)
    metadata_text = (output_directory / "metadata.json").read_text()
    metadata = json.loads(metadata_text)
    benchmark = json.loads((output_directory / "benchmark.json").read_text())
    assert tensor.shape == (24, 1, 8, 9)
    assert metadata["provenance"]["configuration_hash"] == preprocessing_config_hash(
        load_preprocessing_config(ROOT / "configs" / "preprocessing.v1.json")
    )
    assert metadata["transformation_ledger"]["horizontal_flip_applied"] is False
    assert metadata["transformation_ledger"]["through_plane_resampling_applied"] is False
    assert metadata["sampled_projected_positions_mm"] == sorted(
        metadata["sampled_projected_positions_mm"]
    )
    assert metadata["sampled_projected_positions_mm"][0] == 0.0
    assert metadata["sampled_projected_positions_mm"][-1] == 2.0
    assert metadata["provenance"]["code_commit"] == "a" * 40
    assert metadata["provenance"]["source_manifest_version"] == "synthetic-manifest-v1"
    assert metadata["provenance"]["preprocessing_version"] == "dicom-model-v1"
    assert len(metadata["provenance"]["input_checksum"]) == 64
    assert len(metadata["provenance"]["output_checksum"]) == 64
    assert {name for name, _ in metadata["provenance"]["dicom_library_versions"]} == {
        "numpy",
        "pydicom",
        "pylibjpeg",
        "pylibjpeg-libjpeg",
        "pylibjpeg-openjpeg",
    }
    assert str(tmp_path) not in metadata_text
    assert "1.2.826.0.1.3680043" not in metadata_text
    assert benchmark["deterministic_replay"] is True
    assert benchmark["decode_time"]["median_seconds"] > 0.0
    assert benchmark["preprocessing_time"]["median_seconds"] > 0.0
    assert benchmark["representative_tensor_cache_bytes"] > tensor.nbytes
    assert benchmark["process_peak_rss_bytes"] > 0
    assert benchmark["peak_rss_increase_bytes"] >= 0
    assert benchmark["cpu_parallelism"][0]["workers"] == 1
    assert benchmark["kaggle_compatibility"]["offline_bundle_verified"] is False
    assert benchmark["kaggle_compatibility"]["kaggle_runtime_verified"] is False
    assert benchmark["kaggle_compatibility"]["horizontal_flip"] is False
    assert benchmark["kaggle_compatibility"]["through_plane_resampling"] is False
    assert benchmark["kaggle_compatibility"]["cpu_count"] >= 1
    assert str(tmp_path) not in json.dumps(benchmark)

    repeated_output = tmp_path / "repeat-output"
    assert (
        run(
            [
                "preprocess",
                "--config",
                str(ROOT / "configs" / "preprocessing.v1.json"),
                "--input-dir",
                str(input_directory),
                "--output-dir",
                str(repeated_output),
                "--code-commit",
                "a" * 40,
                "--source-manifest-version",
                "synthetic-manifest-v1",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (repeated_output / "tensor.npy").read_bytes() == (
        output_directory / "tensor.npy"
    ).read_bytes()
    assert json.loads((repeated_output / "metadata.json").read_text()) == metadata


def test_preprocess_cli_includes_extensionless_dicom_files(tmp_path: Path) -> None:
    input_directory = tmp_path / "series"
    _synthetic_series(input_directory, extensionless=True)

    assert (
        run(
            [
                "preprocess",
                "--config",
                str(ROOT / "configs" / "preprocessing.v1.json"),
                "--input-dir",
                str(input_directory),
                "--output-dir",
                str(tmp_path / "output"),
                "--code-commit",
                "a" * 40,
                "--source-manifest-version",
                "synthetic-manifest-v1",
            ]
        )
        == 0
    )


def test_preprocess_cli_rejects_symlinked_input_entries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_directory = tmp_path / "series"
    paths = _synthetic_series(input_directory)
    (input_directory / "linked-slice").symlink_to(paths[0])

    status = run(
        [
            "preprocess",
            "--config",
            str(ROOT / "configs" / "preprocessing.v1.json"),
            "--input-dir",
            str(input_directory),
            "--output-dir",
            str(tmp_path / "output"),
            "--code-commit",
            "a" * 40,
            "--source-manifest-version",
            "synthetic-manifest-v1",
        ]
    )

    assert status == 2
    assert capsys.readouterr().err == ("preprocess_status=failed reason=input_or_config_invalid\n")


def test_benchmark_rejects_unbounded_parameters_without_exposing_paths(tmp_path: Path) -> None:
    paths = _synthetic_series(tmp_path / "sensitive-name")
    with pytest.raises(ValueError, match="benchmark_iterations_invalid") as error:
        benchmark_dicom_pipeline(paths, PreprocessingConfig(), VERSIONS, iterations=21)
    assert str(tmp_path) not in str(error.value)


def test_preprocess_cli_sanitizes_invalid_config_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_directory = tmp_path / "sensitive-series"
    _synthetic_series(input_directory)
    invalid_config = tmp_path / "sensitive-config.json"
    invalid_config.write_text('{"private_unknown":"must-not-echo"}')

    status = run(
        [
            "preprocess",
            "--config",
            str(invalid_config),
            "--input-dir",
            str(input_directory),
            "--output-dir",
            str(tmp_path / "sensitive-output"),
            "--code-commit",
            "a" * 40,
            "--source-manifest-version",
            "synthetic-manifest-v1",
        ]
    )

    captured = capsys.readouterr()
    assert status == 2
    assert captured.out == ""
    assert captured.err == "preprocess_status=failed reason=input_or_config_invalid\n"
    assert "must-not-echo" not in captured.err
    assert str(tmp_path) not in captured.err
