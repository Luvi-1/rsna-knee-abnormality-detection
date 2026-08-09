from __future__ import annotations

import base64
import hashlib
import warnings
from math import sqrt
from pathlib import Path

import numpy as np
import pydicom
import pytest
from numpy.typing import NDArray
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.encaps import encapsulate
from pydicom.pixels.decoders.base import get_decoder
from pydicom.uid import (
    ExplicitVRLittleEndian,
    ImplicitVRLittleEndian,
    JPEG2000Lossless,
    JPEGLosslessSV1,
    MRImageStorage,
)

import rsna_knee.dicom.pipeline as pipeline_module
from rsna_knee.dicom.audit import OrderingBasis
from rsna_knee.dicom.pipeline import (
    NormalizationMode,
    PipelineError,
    PipelineIssue,
    PipelineVersions,
    PreprocessingConfig,
    decode_dicom,
    deterministic_slice_indices,
    dicom_to_model,
    load_series,
    preprocess_series,
    preprocessing_config_hash,
)

AXIAL = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
SAGITTAL = (0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
VERSIONS = PipelineVersions(
    code_commit="a" * 40,
    source_manifest_version="synthetic-manifest-v1",
)


def _gradient(rows: int = 6, columns: int = 7, *, offset: int = 0) -> NDArray[np.int16]:
    y, x = np.mgrid[:rows, :columns]
    return np.asarray(3 * y + 7 * x + offset, dtype=np.int16)


def _uid_for(path: Path) -> str:
    suffix = int(hashlib.sha256(str(path).encode()).hexdigest()[:14], 16)
    return f"1.2.826.0.1.3680043.10.543.{suffix}"


def _write_dicom(
    path: Path,
    pixels: NDArray[np.integer],
    *,
    position: tuple[float, float, float] | None = (0.0, 0.0, 0.0),
    orientation: tuple[float, float, float, float, float, float] | None = AXIAL,
    instance_number: int | None = 1,
    pixel_spacing: tuple[float, float] | None = (0.5, 0.75),
    bits_allocated: int = 16,
    bits_stored: int = 16,
    signed: bool = False,
    photometric: str = "MONOCHROME2",
    slope: float = 1.0,
    intercept: float = 0.0,
    laterality: str | None = "L",
    series_description: str = "PD FS",
    echo_time: float | None = 60.0,
    pixel_bytes: bytes | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    uid = _uid_for(path)
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
    dataset.PhotometricInterpretation = photometric
    dataset.PixelRepresentation = int(signed)
    dataset.BitsAllocated = bits_allocated
    dataset.BitsStored = bits_stored
    dataset.HighBit = bits_stored - 1
    if orientation is not None:
        dataset.ImageOrientationPatient = list(orientation)
    if position is not None:
        dataset.ImagePositionPatient = list(position)
    if instance_number is not None:
        dataset.InstanceNumber = instance_number
    if pixel_spacing is not None:
        dataset.PixelSpacing = list(pixel_spacing)
    dataset.SliceThickness = 1.0
    dataset.SpacingBetweenSlices = 1.0
    dataset.RescaleSlope = slope
    dataset.RescaleIntercept = intercept
    if laterality is not None:
        dataset.ImageLaterality = laterality
    dataset.SeriesDescription = series_description
    if echo_time is not None:
        dataset.EchoTime = echo_time
    if bits_allocated == 8:
        dtype = np.dtype("i1" if signed else "u1")
    elif bits_allocated == 16:
        dtype = np.dtype("<i2" if signed else "<u2")
    else:
        raise ValueError("unsupported_synthetic_bits")
    dataset.PixelData = (
        np.asarray(pixels, dtype=dtype).tobytes(order="C") if pixel_bytes is None else pixel_bytes
    )
    dataset.save_as(path, enforce_file_format=True)


def _series(
    root: Path,
    positions: tuple[float, ...],
    *,
    orientation: tuple[float, float, float, float, float, float] = AXIAL,
    instances: tuple[int, ...] | None = None,
    prefix: str = "slice",
    series_description: str = "PD FS",
    laterality: str | None = "L",
    pixel_spacing: tuple[float, float] = (0.5, 0.75),
) -> tuple[Path, ...]:
    paths: list[Path] = []
    for index, distance in enumerate(positions):
        path = root / f"{prefix}-{index}.dcm"
        normal = np.cross(np.asarray(orientation[:3]), np.asarray(orientation[3:]))
        position = tuple(float(value) for value in normal * distance)
        _write_dicom(
            path,
            _gradient(offset=10 * index),
            position=position,
            orientation=orientation,
            instance_number=(instances[index] if instances is not None else index + 1),
            laterality=laterality,
            series_description=series_description,
            pixel_spacing=pixel_spacing,
        )
        paths.append(path)
    return tuple(paths)


def test_strict_single_read_applies_rescale_and_monochrome1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "private-name.dcm"
    stored = np.asarray([[0, 1], [2, 3]], dtype=np.int16)
    _write_dicom(
        path,
        stored,
        slope=2.0,
        intercept=-1.0,
        photometric="MONOCHROME1",
    )
    original_read_bytes = Path.read_bytes
    calls = 0

    def counted_read_bytes(self: Path) -> bytes:
        nonlocal calls
        calls += 1
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)
    result = decode_dicom(path)

    assert calls == 1
    np.testing.assert_array_equal(result.pixels, [[1.0, -1.0], [-3.0, -5.0]])
    assert result.transfer_syntax == str(ExplicitVRLittleEndian)
    assert not result.pixels.flags.writeable


def test_monochrome1_uses_one_series_consistent_polarity_across_differing_ranges(
    tmp_path: Path,
) -> None:
    first = tmp_path / "mono1-first.dcm"
    second = tmp_path / "mono1-second.dcm"
    first_pixels = np.asarray([[0, 1], [2, 3]], dtype=np.int16)
    second_pixels = np.asarray([[10, 20], [30, 40]], dtype=np.int16)
    _write_dicom(
        first,
        first_pixels,
        position=(0.0, 0.0, 0.0),
        photometric="MONOCHROME1",
    )
    _write_dicom(
        second,
        second_pixels,
        position=(0.0, 0.0, 1.0),
        instance_number=2,
        photometric="MONOCHROME1",
    )

    ordered = load_series((second, first), PreprocessingConfig())

    np.testing.assert_array_equal(ordered.slices[0].pixels, -first_pixels.astype(np.float64))
    np.testing.assert_array_equal(ordered.slices[1].pixels, -second_pixels.astype(np.float64))


def test_preprocessing_ledger_preserves_ordered_per_slice_intensity_transforms(
    tmp_path: Path,
) -> None:
    first = tmp_path / "intensity-first.dcm"
    second = tmp_path / "intensity-second.dcm"
    _write_dicom(
        first,
        _gradient(),
        position=(0.0, 0.0, 0.0),
        photometric="MONOCHROME1",
    )
    first_dataset = pydicom.dcmread(first)
    del first_dataset.RescaleSlope
    del first_dataset.RescaleIntercept
    first_dataset.save_as(first, enforce_file_format=True)
    _write_dicom(
        second,
        _gradient(offset=1),
        position=(0.0, 0.0, 1.0),
        instance_number=2,
        slope=0.5,
        intercept=10.0,
        photometric="MONOCHROME1",
    )

    output = dicom_to_model((second, first), PreprocessingConfig(), VERSIONS)

    assert output.ledger.per_slice_rescale_slope_intercept == ((1.0, 0.0), (0.5, 10.0))
    assert output.ledger.per_slice_photometric_interpretation == (
        "MONOCHROME1",
        "MONOCHROME1",
    )
    assert output.ledger.per_slice_monochrome1_inversion_applied == (True, True)


def test_duplicate_detection_uses_intensity_transformed_pixels(tmp_path: Path) -> None:
    stored = _gradient()
    first = tmp_path / "same-stored-first.dcm"
    second = tmp_path / "same-stored-second.dcm"
    _write_dicom(first, stored, position=(0.0, 0.0, 0.0))
    _write_dicom(
        second,
        stored,
        position=(0.0, 0.0, 1.0),
        instance_number=2,
        slope=2.0,
        intercept=1.0,
    )

    ordered = load_series((first, second), PreprocessingConfig())

    assert ordered.slices[0].decoded_checksum == ordered.slices[1].decoded_checksum
    assert ordered.slices[0].model_pixel_checksum != ordered.slices[1].model_pixel_checksum
    assert ordered.geometry.duplicate_pixel_groups == ()
    assert ordered.model_eligible


@pytest.mark.parametrize(
    ("bits_allocated", "bits_stored", "signed", "values"),
    [
        (8, 8, False, [[0, 1], [127, 255]]),
        (16, 12, False, [[0, 1], [2047, 4095]]),
        (16, 16, True, [[-100, -1], [0, 200]]),
    ],
)
def test_different_bit_depths_and_signed_pixels_decode_exactly(
    tmp_path: Path,
    bits_allocated: int,
    bits_stored: int,
    signed: bool,
    values: list[list[int]],
) -> None:
    path = tmp_path / f"bits-{bits_allocated}-{bits_stored}-{signed}.dcm"
    pixels = np.asarray(values, dtype=np.int16)
    _write_dicom(
        path,
        pixels,
        bits_allocated=bits_allocated,
        bits_stored=bits_stored,
        signed=signed,
    )

    result = decode_dicom(path)

    np.testing.assert_array_equal(result.pixels, pixels.astype(np.float64))


@pytest.mark.parametrize(
    ("attribute", "value", "root_cause"),
    [
        ("PhotometricInterpretation", "RGB", "unsupported_pixel_layout"),
        ("BitsStored", 17, "invalid_pixel_encoding"),
        ("RescaleSlope", float("nan"), "invalid_rescale"),
    ],
)
def test_malformed_pixel_critical_metadata_fails_closed(
    tmp_path: Path, attribute: str, value: object, root_cause: str
) -> None:
    path = tmp_path / f"malformed-{attribute}.dcm"
    _write_dicom(path, _gradient())
    dataset = pydicom.dcmread(path)
    setattr(dataset, attribute, value)
    dataset.save_as(path, enforce_file_format=True)

    with pytest.raises(PipelineError) as raised:
        decode_dicom(path)

    assert raised.value.issue is PipelineIssue.METADATA_INVALID
    assert raised.value.stage == "metadata_validation"
    assert raised.value.root_cause == root_cause


def test_missing_transfer_syntax_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "missing-transfer-syntax.dcm"
    _write_dicom(path, _gradient())
    dataset = pydicom.dcmread(path)
    del dataset.file_meta.TransferSyntaxUID
    monkeypatch.setattr(pipeline_module.pydicom, "dcmread", lambda *_args, **_kwargs: dataset)

    with pytest.raises(PipelineError) as raised:
        decode_dicom(path)

    assert raised.value.issue is PipelineIssue.TRANSFER_SYNTAX_UNSUPPORTED
    assert raised.value.stage == "decode_preflight"
    assert raised.value.root_cause == "unsupported_transfer_syntax"


def test_jpeg2000_lossless_decodes_through_pinned_plugin(tmp_path: Path) -> None:
    path = tmp_path / "jpeg2000-lossless.dcm"
    pixels = _gradient(32, 32)
    _write_dicom(path, pixels)
    dataset = pydicom.dcmread(path)
    dataset.compress(JPEG2000Lossless)
    dataset.save_as(path, enforce_file_format=True)

    decoded = decode_dicom(path)

    assert decoded.transfer_syntax == str(JPEG2000Lossless)
    np.testing.assert_array_equal(decoded.pixels, pixels.astype(np.float64))


def test_implicit_vr_little_endian_round_trip_records_transfer_syntax(tmp_path: Path) -> None:
    path = tmp_path / "implicit-vr-little-endian.dcm"
    pixels = _gradient(8, 8)
    _write_dicom(path, pixels)
    dataset = pydicom.dcmread(path)
    dataset.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
    dataset.save_as(path, enforce_file_format=True)

    decoded = decode_dicom(path)

    assert decoded.transfer_syntax == str(ImplicitVRLittleEndian)
    np.testing.assert_array_equal(decoded.pixels, pixels.astype(np.float64))
    assert decoded.pixels.astype("<u2").tobytes() == pixels.astype("<u2").tobytes()


def test_jpeg_lossless_sv1_decodes_through_pinned_pylibjpeg_plugin(tmp_path: Path) -> None:
    path = tmp_path / "jpeg-lossless-sv1.dcm"
    pixels = np.arange(64, dtype=np.uint8).reshape(8, 8)
    _write_dicom(path, pixels, bits_allocated=8, bits_stored=8)
    dataset = pydicom.dcmread(path)
    # Synthetic ISO/IEC 10918-1 Process 14 SV1 frame for uint8 values 0..63,
    # generated once with libjpeg-turbo's lossless encoder; decoding uses only pinned packages.
    frame = base64.b64decode(
        "/9j/4AAQSkZJRgABAQAAAQABAAD/wwALCAAIAAgBAREA/8QAFgABAQEAAAAAAAAA"
        "AAAAAAAAAQQI/9oACAEBAAEAAM/qqtCqrQqq0KqtCqrQqq0KqtCqr//Z"
    )
    dataset.file_meta.TransferSyntaxUID = JPEGLosslessSV1
    dataset.PixelData = encapsulate([frame])
    dataset["PixelData"].is_undefined_length = True
    dataset.save_as(path, enforce_file_format=True)

    decoder = get_decoder(JPEGLosslessSV1)
    assert decoder.is_available
    assert "pylibjpeg" in decoder.available_plugins
    decoded = decode_dicom(path)

    assert decoded.transfer_syntax == str(JPEGLosslessSV1)
    np.testing.assert_array_equal(decoded.pixels, pixels.astype(np.float64))
    assert decoded.pixels.astype(np.uint8).tobytes() == pixels.tobytes()


def test_physical_order_overrides_reversed_instance_numbers(tmp_path: Path) -> None:
    paths = _series(tmp_path, (0.0, 1.0, 2.0), instances=(30, 20, 10))

    ordered = load_series(tuple(reversed(paths)), PreprocessingConfig())

    assert ordered.geometry.ordering_basis is OrderingBasis.GEOMETRY
    assert ordered.geometry.projected_positions_mm == (0.0, 1.0, 2.0)
    assert [float(item.pixels[0, 0]) for item in ordered.slices] == [0.0, 10.0, 20.0]


def test_oblique_geometry_uses_iop_cross_product_projection(tmp_path: Path) -> None:
    component = 1.0 / sqrt(2.0)
    orientation = (component, component, 0.0, 0.0, 0.0, 1.0)
    paths = _series(tmp_path, (4.0, 2.0, 3.0), orientation=orientation)

    ordered = load_series(paths, PreprocessingConfig())

    np.testing.assert_allclose(ordered.geometry.projected_positions_mm, (2.0, 3.0, 4.0))
    np.testing.assert_allclose(
        ordered.geometry.canonical_slice_normal_lps,
        (component, -component, 0.0),
    )


def test_invalid_and_inconsistent_orientation_fail_closed(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid-orientation.dcm"
    _write_dicom(
        invalid,
        _gradient(),
        orientation=(1.01, 0.0, 0.0, 0.0, 1.0, 0.0),
    )
    with pytest.raises(PipelineError) as invalid_error:
        load_series((invalid,), PreprocessingConfig())
    assert invalid_error.value.issue is PipelineIssue.ORIENTATION_INVALID

    first = tmp_path / "orientation-a.dcm"
    second = tmp_path / "orientation-b.dcm"
    angle = np.deg2rad(1.0)
    rotated = (
        float(np.cos(angle)),
        float(np.sin(angle)),
        0.0,
        float(-np.sin(angle)),
        float(np.cos(angle)),
        0.0,
    )
    _write_dicom(first, _gradient(), position=(0.0, 0.0, 0.0))
    _write_dicom(
        second,
        _gradient(offset=1),
        position=(0.0, 0.0, 1.0),
        orientation=rotated,
    )
    with pytest.raises(PipelineError) as drift_error:
        load_series((first, second), PreprocessingConfig())
    assert drift_error.value.issue is PipelineIssue.ORIENTATION_INCONSISTENT


def test_positive_dominant_axis_does_not_flip_native_pixels_or_laterality(
    tmp_path: Path,
) -> None:
    negative_axial = (-1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    paths = _series(tmp_path, (-2.0, -1.0, 0.0), orientation=negative_axial, laterality="R")
    source_pixels = {
        decoded.raw_checksum: decoded.pixels.copy()
        for decoded in (decode_dicom(path) for path in paths)
    }

    ordered = load_series(tuple(reversed(paths)), PreprocessingConfig())

    assert ordered.geometry.canonical_slice_normal_lps == (0.0, 0.0, 1.0)
    assert ordered.laterality == "R"
    assert ordered.slice_lateralities == ("R", "R", "R")
    assert ordered.ledger.horizontal_flip_applied is False
    assert ordered.ledger.laterality_transform == "none"
    for item in ordered.slices:
        np.testing.assert_array_equal(item.pixels, source_pixels[item.raw_checksum])


def test_numpy_slice_row_column_lps_affine_uses_correct_iop_axes(tmp_path: Path) -> None:
    paths = _series(tmp_path, (10.0, 12.0, 14.0), pixel_spacing=(2.0, 3.0))

    geometry = load_series(paths, PreprocessingConfig()).geometry

    assert geometry.affine_is_regular
    np.testing.assert_allclose(
        geometry.affine_lps_slice_row_column,
        (
            (0.0, 0.0, 3.0, 0.0),
            (0.0, 2.0, 0.0, 0.0),
            (2.0, 0.0, 0.0, 10.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
    )


def test_missing_position_fallback_is_explicit_qa_only_and_model_blocked(tmp_path: Path) -> None:
    first = tmp_path / "first.dcm"
    second = tmp_path / "second.dcm"
    _write_dicom(first, _gradient(offset=10), position=None, instance_number=2)
    _write_dicom(second, _gradient(), position=None, instance_number=1)

    with pytest.raises(PipelineError) as blocked:
        load_series((first, second), PreprocessingConfig())
    assert blocked.value.issue is PipelineIssue.PHYSICAL_POSITION_MISSING

    config = PreprocessingConfig(allow_instance_fallback_for_qa=True)
    ordered = load_series((first, second), config)
    assert ordered.geometry.ordering_basis is OrderingBasis.INSTANCE_NUMBER
    assert not ordered.model_eligible
    assert [float(item.pixels[0, 0]) for item in ordered.slices] == [0.0, 10.0]
    with pytest.raises(PipelineError) as model_blocked:
        preprocess_series(ordered, config, VERSIONS)
    assert model_blocked.value.issue is PipelineIssue.INSTANCE_FALLBACK_MODEL_BLOCKED


def test_duplicate_positions_block_but_duplicate_pixels_are_recorded(tmp_path: Path) -> None:
    same_position_a = tmp_path / "position-a.dcm"
    same_position_b = tmp_path / "position-b.dcm"
    _write_dicom(same_position_a, _gradient(), position=(0.0, 0.0, 1.0))
    _write_dicom(same_position_b, _gradient(offset=1), position=(0.0, 0.0, 1.0))
    with pytest.raises(PipelineError) as duplicate_position:
        load_series((same_position_a, same_position_b), PreprocessingConfig())
    assert duplicate_position.value.issue is PipelineIssue.DUPLICATE_POSITION

    duplicate_pixels = _gradient()
    first = tmp_path / "pixels-a.dcm"
    second = tmp_path / "pixels-b.dcm"
    _write_dicom(first, duplicate_pixels, position=(0.0, 0.0, 0.0))
    _write_dicom(second, duplicate_pixels, position=(0.0, 0.0, 1.0))
    ordered = load_series((first, second), PreprocessingConfig())
    assert ordered.geometry.duplicate_pixel_groups == ((0, 1),)
    assert not ordered.model_eligible
    with pytest.raises(PipelineError) as duplicate_decoded:
        preprocess_series(ordered, PreprocessingConfig(), VERSIONS)
    assert duplicate_decoded.value.issue is PipelineIssue.DUPLICATE_DECODED_SLICE
    assert duplicate_decoded.value.stage == "series_eligibility"


def test_uneven_spacing_is_preserved_and_not_fabricated_as_regular_affine(tmp_path: Path) -> None:
    paths = _series(tmp_path, (0.0, 1.0, 3.5))

    ordered = load_series(paths, PreprocessingConfig())
    geometry = ordered.geometry

    assert geometry.slice_spacings_mm == (1.0, 2.5)
    assert geometry.spacing_is_uneven
    assert geometry.affine_lps_slice_row_column is None
    assert not geometry.affine_is_regular
    assert not ordered.model_eligible
    with pytest.raises(PipelineError) as uneven:
        preprocess_series(ordered, PreprocessingConfig(), VERSIONS)
    assert uneven.value.issue is PipelineIssue.UNEVEN_SLICE_SPACING
    assert uneven.value.stage == "series_eligibility"


def test_in_plane_spacing_drift_is_preserved_and_model_blocked(tmp_path: Path) -> None:
    paths: list[Path] = []
    expected_spacings = ((0.5, 0.75), (0.5003, 0.75), (0.5, 0.75))
    for index, spacing in enumerate(expected_spacings):
        path = tmp_path / f"spacing-{index}.dcm"
        _write_dicom(
            path,
            _gradient(offset=index),
            position=(0.0, 0.0, float(index)),
            instance_number=index + 1,
            pixel_spacing=spacing,
        )
        paths.append(path)

    ordered = load_series(tuple(paths), PreprocessingConfig())

    assert ordered.geometry.per_slice_pixel_spacing_row_column_mm == expected_spacings
    assert not ordered.geometry.in_plane_spacing_is_consistent
    assert ordered.geometry.affine_lps_slice_row_column is None
    assert not ordered.model_eligible
    with pytest.raises(PipelineError) as drift:
        preprocess_series(ordered, PreprocessingConfig(), VERSIONS)
    assert drift.value.issue is PipelineIssue.PIXEL_SPACING_INCONSISTENT
    assert drift.value.stage == "series_eligibility"


def test_in_plane_position_drift_cannot_receive_a_false_regular_affine(tmp_path: Path) -> None:
    paths: list[Path] = []
    for index, position in enumerate(((0.0, 0.0, 0.0), (5.0, 0.0, 1.0), (10.0, 0.0, 2.0))):
        path = tmp_path / f"drift-{index}.dcm"
        _write_dicom(path, _gradient(offset=index), position=position)
        paths.append(path)

    with pytest.raises(PipelineError) as raised:
        load_series(tuple(paths), PreprocessingConfig())

    assert raised.value.issue is PipelineIssue.IMAGE_POSITION_INCONSISTENT


def test_regular_affine_requires_stricter_iop_and_delta_consistency(tmp_path: Path) -> None:
    angle = np.deg2rad(0.1)
    rotated = (
        float(np.cos(angle)),
        float(np.sin(angle)),
        0.0,
        float(-np.sin(angle)),
        float(np.cos(angle)),
        0.0,
    )
    iop_paths: list[Path] = []
    for index, orientation in enumerate((AXIAL, rotated, rotated)):
        path = tmp_path / f"strict-iop-{index}.dcm"
        _write_dicom(
            path,
            _gradient(offset=index),
            position=(0.0, 0.0, float(index)),
            orientation=orientation,
            instance_number=index + 1,
        )
        iop_paths.append(path)

    iop_series = load_series(tuple(iop_paths), PreprocessingConfig())

    assert iop_series.geometry.ordering_basis is OrderingBasis.GEOMETRY
    assert not iop_series.geometry.affine_iop_is_consistent
    assert iop_series.geometry.affine_delta_is_consistent
    assert not iop_series.geometry.affine_is_regular
    assert not iop_series.model_eligible

    delta_paths: list[Path] = []
    for index in range(3):
        path = tmp_path / f"strict-delta-{index}.dcm"
        _write_dicom(
            path,
            _gradient(offset=index),
            position=(0.02 * index, 0.0, float(index)),
            instance_number=index + 1,
        )
        delta_paths.append(path)

    delta_series = load_series(tuple(delta_paths), PreprocessingConfig())

    assert delta_series.geometry.affine_iop_is_consistent
    assert not delta_series.geometry.affine_delta_is_consistent
    assert not delta_series.geometry.affine_is_regular
    assert not delta_series.model_eligible
    with pytest.raises(PipelineError) as unproven:
        preprocess_series(delta_series, PreprocessingConfig(), VERSIONS)
    assert unproven.value.issue is PipelineIssue.REGULAR_AFFINE_UNPROVEN


def test_nonfinite_pixels_created_by_rescale_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "overflow.dcm"
    _write_dicom(path, _gradient(), slope=1e308)

    with pytest.raises(PipelineError) as raised:
        decode_dicom(path)

    assert raised.value.issue is PipelineIssue.NONFINITE_PIXELS
    assert raised.value.stage == "rescale_validation"


@pytest.mark.parametrize(
    ("pixels", "issue"),
    [
        (np.zeros((4, 4), dtype=np.int16), PipelineIssue.BLANK_SLICE),
        (np.full((4, 4), 7, dtype=np.int16), PipelineIssue.CONSTANT_SLICE),
    ],
)
def test_blank_and_constant_slices_fail_closed(
    tmp_path: Path, pixels: NDArray[np.int16], issue: PipelineIssue
) -> None:
    path = tmp_path / f"{issue}.dcm"
    _write_dicom(path, pixels)

    with pytest.raises(PipelineError) as raised:
        decode_dicom(path)

    assert raised.value.issue is issue
    assert path.name not in repr(raised.value)


def test_corrupt_and_truncated_inputs_report_sanitized_root_causes(tmp_path: Path) -> None:
    corrupt = tmp_path / "patient-looking-name.dcm"
    corrupt.write_bytes(b"not a dicom")
    with pytest.raises(PipelineError) as corrupt_error:
        decode_dicom(corrupt)
    assert corrupt_error.value.issue is PipelineIssue.CONTAINER_PARSE
    assert corrupt.name not in repr(corrupt_error.value)

    truncated = tmp_path / "truncated.dcm"
    _write_dicom(truncated, _gradient(), pixel_bytes=b"\0\1")
    with pytest.raises(PipelineError) as truncated_error:
        decode_dicom(truncated)
    assert truncated_error.value.issue is PipelineIssue.PIXEL_DATA_INCONSISTENT
    assert truncated_error.value.root_cause == "uncompressed_pixel_data_inconsistency"


def test_pydicom_read_warning_is_sanitized_and_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "private-read-warning.dcm"
    _write_dicom(path, _gradient())
    original_dcmread = pipeline_module.pydicom.dcmread

    def warned_read(*args: object, **kwargs: object) -> object:
        warnings.warn("private read warning text", UserWarning, stacklevel=2)
        return original_dcmread(*args, **kwargs)

    monkeypatch.setattr(pipeline_module.pydicom, "dcmread", warned_read)

    with pytest.raises(PipelineError) as raised:
        decode_dicom(path)

    assert raised.value.issue is PipelineIssue.PYDICOM_WARNING
    assert raised.value.stage == "container_parse_warning"
    assert "private read warning text" not in repr(raised.value)
    assert path.name not in repr(raised.value)


def test_pydicom_decode_warning_is_sanitized_and_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "private-decode-warning.dcm"
    _write_dicom(path, _gradient())
    dataset_type = type(pydicom.dcmread(path))
    original_pixel_array = dataset_type.pixel_array.fget
    assert original_pixel_array is not None

    def warned_pixel_array(self: object) -> NDArray[np.generic]:
        warnings.warn("private decode warning text", UserWarning, stacklevel=2)
        return np.asarray(original_pixel_array(self))

    monkeypatch.setattr(dataset_type, "pixel_array", property(warned_pixel_array))

    with pytest.raises(PipelineError) as raised:
        decode_dicom(path)

    assert raised.value.issue is PipelineIssue.PYDICOM_WARNING
    assert raised.value.stage == "pixel_decode_warning"
    assert "private decode warning text" not in repr(raised.value)
    assert path.name not in repr(raised.value)


def test_missing_pixel_spacing_and_conflicting_laterality_fail_closed(tmp_path: Path) -> None:
    missing_spacing = tmp_path / "missing-spacing.dcm"
    _write_dicom(missing_spacing, _gradient(), pixel_spacing=None)
    with pytest.raises(PipelineError) as missing:
        load_series((missing_spacing,), PreprocessingConfig())
    assert missing.value.issue is PipelineIssue.PIXEL_SPACING_MISSING

    left = tmp_path / "left.dcm"
    right = tmp_path / "right.dcm"
    _write_dicom(left, _gradient(), position=(0.0, 0.0, 0.0), laterality="L")
    _write_dicom(right, _gradient(offset=1), position=(0.0, 0.0, 1.0), laterality="R")
    with pytest.raises(PipelineError) as conflict:
        load_series((left, right), PreprocessingConfig())
    assert conflict.value.issue is PipelineIssue.LATERALITY_INCONSISTENT


def test_physical_sampling_channels_resize_and_versioned_provenance(tmp_path: Path) -> None:
    paths = _series(tmp_path, (0.0, 1.0, 2.0, 3.0, 4.0))
    config = PreprocessingConfig(
        lower_percentile=2.0,
        upper_percentile=98.0,
        normalization=NormalizationMode.ZSCORE,
        sample_count=3,
        local_contrast_channel=True,
        adjacent_slice_channels=True,
        difference_channel=True,
        resize_rows_columns=(4, 5),
    )

    output = dicom_to_model(paths, config, VERSIONS)

    assert output.tensor.shape == (3, 5, 4, 5)
    assert output.channel_names == (
        "base",
        "local_contrast",
        "previous",
        "next",
        "next_minus_previous",
    )
    assert output.sampled_ordered_indices == (0, 2, 4)
    assert output.sampled_projected_positions_mm == (0.0, 2.0, 4.0)
    assert output.ledger.in_plane_resize_from_to == ((6, 7), (4, 5))
    assert not output.ledger.native_in_plane_pixels_preserved
    assert not output.ledger.horizontal_flip_applied
    assert not output.ledger.through_plane_resampling_applied
    np.testing.assert_allclose(output.output_pixel_spacing_row_column_mm, (5 / 6, 1.125))
    assert output.output_affine_lps_slice_row_column is not None
    assert output.output_affine_lps_slice_row_column[2][0] == pytest.approx(2.0)
    assert output.provenance.configuration_hash == preprocessing_config_hash(config)
    assert output.provenance.code_commit == "a" * 40
    assert output.provenance.source_manifest_version == "synthetic-manifest-v1"
    assert output.provenance.preprocessing_version == "dicom-model-v1"
    assert {name for name, _ in output.provenance.dicom_library_versions} == {
        "numpy",
        "pydicom",
        "pylibjpeg",
        "pylibjpeg-libjpeg",
        "pylibjpeg-openjpeg",
    }
    assert all(value != "unavailable" for _, value in output.provenance.dicom_library_versions)
    assert len(output.provenance.input_checksum) == 64
    assert len(output.provenance.output_checksum) == 64
    assert not output.tensor.flags.writeable


def test_output_is_deterministic_across_repeated_and_reordered_inputs(tmp_path: Path) -> None:
    paths = _series(tmp_path, (0.0, 1.0, 2.0, 3.0))
    config = PreprocessingConfig(sample_count=3, lower_percentile=5.0, upper_percentile=95.0)

    first = dicom_to_model(paths, config, VERSIONS)
    repeated = dicom_to_model(paths, config, VERSIONS)
    reordered = dicom_to_model(tuple(reversed(paths)), config, VERSIONS)

    np.testing.assert_array_equal(first.tensor, repeated.tensor)
    np.testing.assert_array_equal(first.tensor, reordered.tensor)
    assert first.provenance == repeated.provenance == reordered.provenance
    assert first.ledger == repeated.ledger == reordered.ledger


def test_deterministic_physical_position_sampler_uses_lower_index_for_ties() -> None:
    assert deterministic_slice_indices((0.0, 2.0, 4.0), 5) == (0, 0, 1, 1, 2)
