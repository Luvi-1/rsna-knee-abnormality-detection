"""Run one identifier-free DICOM production-path preflight from an installed project wheel."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path


def _block_network(event: str, _arguments: tuple[object, ...]) -> None:
    if event.startswith(("socket.", "http.client.", "urllib.Request")):
        raise RuntimeError("network_disabled")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    return parser


def _run(site_root: Path, config_path: Path, code_commit: str) -> dict[str, object]:
    if re.fullmatch(r"[0-9a-f]{40}", code_commit) is None:
        raise ValueError("code_commit_invalid")
    site_root = site_root.resolve(strict=True)
    config_path = config_path.resolve(strict=True)
    if not site_root.is_dir() or not config_path.is_file():
        raise ValueError("preflight_input_invalid")
    sys.path.insert(0, str(site_root))
    sys.addaudithook(_block_network)

    import numpy as np
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import UID, ExplicitVRLittleEndian, MRImageStorage

    import rsna_knee
    from rsna_knee.cli import load_preprocessing_config
    from rsna_knee.dicom.audit import OrderingBasis
    from rsna_knee.dicom.pipeline import (
        PipelineVersions,
        dicom_to_model,
        preprocessing_config_hash,
    )

    package_path = Path(rsna_knee.__file__).resolve(strict=True)
    if not package_path.is_relative_to(site_root):
        raise RuntimeError("project_wheel_not_loaded")

    config = load_preprocessing_config(config_path)
    versions = PipelineVersions(
        code_commit=code_commit,
        source_manifest_version="synthetic-preflight-v1",
    )
    with tempfile.TemporaryDirectory(prefix="rsna-knee-dicom-preflight-") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        paths: list[Path] = []
        y, x = np.mgrid[:8, :9]
        for index in range(3):
            path = root / f"slice-{index}.dcm"
            uid = UID(f"1.2.826.0.1.3680043.10.543.20260809{index + 1}")
            file_meta = FileMetaDataset()
            file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
            file_meta.MediaStorageSOPClassUID = MRImageStorage
            file_meta.MediaStorageSOPInstanceUID = uid
            file_meta.ImplementationClassUID = UID("1.2.826.0.1.3680043.10.543.202608099")
            dataset = FileDataset("", {}, file_meta=file_meta, preamble=b"\0" * 128)
            dataset.SOPClassUID = MRImageStorage
            dataset.SOPInstanceUID = uid
            dataset.Modality = "MR"
            dataset.Rows = 8
            dataset.Columns = 9
            dataset.SamplesPerPixel = 1
            dataset.PhotometricInterpretation = "MONOCHROME1"
            dataset.PixelRepresentation = 0
            dataset.BitsAllocated = 16
            dataset.BitsStored = 12
            dataset.HighBit = 11
            dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
            dataset.ImagePositionPatient = [0.0, 0.0, float(index)]
            dataset.InstanceNumber = 3 - index
            dataset.PixelSpacing = [0.5, 0.75]
            dataset.SliceThickness = 1.0
            dataset.SpacingBetweenSlices = 1.0
            dataset.RescaleSlope = 2.0
            dataset.RescaleIntercept = -100.0
            dataset.ImageLaterality = "L"
            pixels = np.asarray(3 * y + 7 * x + 40 * index + 1, dtype="<u2")
            dataset.PixelData = pixels.tobytes(order="C")
            dataset.save_as(path, enforce_file_format=True)
            path.chmod(0o600)
            paths.append(path)

        first = dicom_to_model((paths[1], paths[2], paths[0]), config, versions)
        second = dicom_to_model((paths[2], paths[0], paths[1]), config, versions)

    deterministic = (
        np.array_equal(first.tensor, second.tensor)
        and first.provenance == second.provenance
        and first.sampled_ordered_indices == second.sampled_ordered_indices
        and first.sampled_projected_positions_mm == second.sampled_projected_positions_mm
    )
    physical_ordering = (
        first.geometry.ordering_basis is OrderingBasis.GEOMETRY
        and first.geometry.projected_positions_mm == (0.0, 1.0, 2.0)
        and first.geometry.pixel_spacing_row_column_mm == (0.5, 0.75)
        and first.geometry.slice_spacings_mm == (1.0, 1.0)
        and first.geometry.affine_is_regular
        and first.sampled_ordered_indices[0] == 0
        and first.sampled_ordered_indices[-1] == 2
        and float(np.mean(first.tensor[0])) > float(np.mean(first.tensor[-1]))
    )
    rescale_and_monochrome1 = (
        first.ledger.per_slice_rescale_slope_intercept == ((2.0, -100.0),) * 3
        and first.ledger.per_slice_photometric_interpretation == ("MONOCHROME1",) * 3
        and first.ledger.per_slice_monochrome1_inversion_applied == (True,) * 3
    )
    provenance_complete = (
        first.provenance.code_commit == code_commit
        and first.provenance.configuration_hash == preprocessing_config_hash(config)
        and first.provenance.preprocessing_version == "dicom-model-v1"
        and first.provenance.source_manifest_version == "synthetic-preflight-v1"
        and re.fullmatch(r"[0-9a-f]{64}", first.provenance.input_checksum) is not None
        and re.fullmatch(r"[0-9a-f]{64}", first.provenance.output_checksum) is not None
        and {name for name, _version in first.provenance.dicom_library_versions}
        == {
            "numpy",
            "pydicom",
            "pylibjpeg",
            "pylibjpeg-libjpeg",
            "pylibjpeg-openjpeg",
        }
        and all(
            version != "unavailable" for _name, version in first.provenance.dicom_library_versions
        )
    )
    checks = {
        "deterministic_replay": deterministic,
        "laterality_preserved": first.laterality == "L" and second.laterality == "L",
        "native_in_plane_preserved": first.ledger.native_in_plane_pixels_preserved,
        "no_horizontal_flip": not first.ledger.horizontal_flip_applied,
        "host_offline_execution": True,
        "physical_ordering": physical_ordering,
        "provenance_complete": provenance_complete,
        "rescale_and_monochrome1": rescale_and_monochrome1,
        "reversed_instance_numbers_ignored": physical_ordering,
        "through_plane_not_resampled": not first.ledger.through_plane_resampling_applied,
    }
    if not all(checks.values()) or first.ledger.laterality_transform != "none":
        raise RuntimeError("synthetic_preflight_failed")
    return {
        "schema_version": 1,
        "artifact_type": "dicom-qa-packaged-synthetic-preflight",
        "status": "pass",
        "preprocessing_version": "dicom-model-v1",
        "source_manifest_version": "synthetic-preflight-v1",
        "validation_scope": {
            "host_native_locked_dependencies": True,
            "kaggle_runtime_execution": "pending_run_a",
            "linux_cp311_cp312_wheelhouse_resolved": True,
            "production_project_wheel_executed": True,
            "target_linux_binaries_executed_locally": False,
        },
        "checks": checks,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = _run(args.site_root, args.config, args.code_commit)
        payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    except Exception:
        sys.stderr.write("synthetic_preflight=FAIL\n")
        return 2
    sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
