from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import replace
from math import cos, radians, sin, sqrt
from pathlib import Path

import numpy as np
import pydicom
import pytest
from numpy.typing import NDArray
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.encaps import encapsulate
from pydicom.uid import ExplicitVRLittleEndian, JPEG2000Lossless, MRImageStorage

import rsna_knee.dicom.audit as audit_module
from rsna_knee.dicom.audit import (
    DECODE_ROOT_CAUSE_TAXONOMY,
    DECODE_ROOT_CAUSE_VERSION,
    DICOM_ISSUE_DISPOSITION_VERSION,
    DICOM_ISSUE_POLICIES,
    DecodeRootCause,
    DicomAuditResult,
    DicomIssue,
    DicomIssueDisposition,
    DicomIssueScope,
    DicomResolutionState,
    OrderingBasis,
    SliceMetadata,
    _resize_bilinear,
    audit_dataset,
    audit_dicom,
    audit_series,
    canonical_decoded_pixel_sha256,
    classify_decode_root_cause,
    extract_metadata,
    gradient_magnitude,
    gradient_normalized_cross_correlation,
    normalized_cross_correlation,
    perceptual_hash,
    phash_hamming,
)

UIntImage = NDArray[np.uint16]
AXIAL_ORIENTATION = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


def test_every_dicom_issue_has_one_versioned_terminal_disposition() -> None:
    assert set(DICOM_ISSUE_POLICIES) == set(DicomIssue)
    assert {policy.version for policy in DICOM_ISSUE_POLICIES.values()} == {
        DICOM_ISSUE_DISPOSITION_VERSION
    }
    assert all(policy.terminal_effect == "quarantine" for policy in DICOM_ISSUE_POLICIES.values())
    assert DICOM_ISSUE_POLICIES[DicomIssue.UNREADABLE].scope is DicomIssueScope.FILE
    assert (
        DICOM_ISSUE_POLICIES[DicomIssue.UNREADABLE].disposition
        is DicomIssueDisposition.FILE_QUARANTINE
    )
    assert DICOM_ISSUE_POLICIES[DicomIssue.EMPTY_SERIES].scope is DicomIssueScope.SERIES
    assert (
        DICOM_ISSUE_POLICIES[DicomIssue.INSTANCE_FALLBACK].disposition
        is DicomIssueDisposition.SERIES_FALLBACK_QUARANTINE
    )
    assert (
        DICOM_ISSUE_POLICIES[DicomIssue.DECODE_FAILURE].default_resolution_state
        is DicomResolutionState.UNRESOLVED_BLOCKER
    )
    assert tuple(item.value for item in DecodeRootCause) == DECODE_ROOT_CAUSE_TAXONOMY


def _image(rows: int = 16, columns: int = 16) -> UIntImage:
    y, x = np.mgrid[:rows, :columns]
    return np.asarray(11 * x * x + 7 * y * y + 3 * x * y, dtype=np.uint16)


def _write_dicom(
    path: Path,
    pixels: UIntImage | NDArray[np.uint16],
    *,
    position: tuple[float, float, float] | None = (0.0, 0.0, 0.0),
    orientation: tuple[float, float, float, float, float, float] | None = AXIAL_ORIENTATION,
    instance_number: int | None = 1,
    pixel_spacing: tuple[float, float] | None = (0.5, 0.5),
    bits_stored: int = 16,
    number_of_frames: int = 1,
    rescale_slope: float = 1.0,
    rescale_intercept: float = 0.0,
    pixel_bytes: bytes | None = None,
    omit_rows: bool = False,
) -> None:
    frame_shape = pixels.shape[-2:]
    uid = f"1.2.826.0.1.3680043.10.543.{abs(instance_number or 0) + 1}"
    file_meta = FileMetaDataset()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.MediaStorageSOPClassUID = MRImageStorage
    file_meta.MediaStorageSOPInstanceUID = uid
    file_meta.ImplementationClassUID = "1.2.826.0.1.3680043.10.543.99"

    dataset = FileDataset(None, {}, file_meta=file_meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = MRImageStorage
    dataset.SOPInstanceUID = uid
    dataset.Modality = "MR"
    if not omit_rows:
        dataset.Rows = int(frame_shape[0])
    dataset.Columns = int(frame_shape[1])
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.PixelRepresentation = 0
    dataset.BitsAllocated = 16
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
    dataset.RescaleSlope = rescale_slope
    dataset.RescaleIntercept = rescale_intercept
    if number_of_frames != 1:
        dataset.NumberOfFrames = number_of_frames
    dataset.PixelData = (
        pixel_bytes
        if pixel_bytes is not None
        else np.asarray(pixels, dtype="<u2").tobytes(order="C")
    )
    dataset.save_as(path, enforce_file_format=True)


def _metadata(result: DicomAuditResult) -> SliceMetadata:
    assert result.passed
    assert result.metadata is not None
    return result.metadata


def _audit_metadata(paths: Sequence[Path]) -> list[SliceMetadata]:
    return [_metadata(audit_dicom(path)) for path in paths]


def test_strict_read_rejects_corrupt_without_exposing_path(tmp_path: Path) -> None:
    path = tmp_path / "private-identifier.dcm"
    path.write_bytes(b"not a DICOM file")

    result = audit_dicom(path)

    assert result.issues == (DicomIssue.UNREADABLE,)
    assert result.diagnostics[0].root_cause_category == "invalid_dicom_container"
    assert result.metadata is None
    assert result.fingerprints is None
    assert path.name not in repr(result)


def test_generic_parse_value_error_remains_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "parser-edge.dcm"
    path.write_bytes(b"synthetic private payload")

    def parser_bug(*args: object, **kwargs: object) -> object:
        raise ValueError("private parser detail")

    monkeypatch.setattr(audit_module.pydicom, "dcmread", parser_bug)
    result = audit_dicom(path)

    assert result.issues == (DicomIssue.UNREADABLE,)
    assert result.diagnostics[0].root_cause_category == DecodeRootCause.UNEXPECTED_UNEXPLAINED.value
    assert result.diagnostics[0].resolution_state is DicomResolutionState.UNRESOLVED_BLOCKER
    assert result.diagnostics[0].exception_type == "builtins.ValueError"
    assert "private parser detail" not in repr(result)


def test_required_metadata_and_pixel_decode_fail_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.dcm"
    short_pixels = tmp_path / "short.dcm"
    _write_dicom(missing, _image(), omit_rows=True)
    _write_dicom(short_pixels, _image(), pixel_bytes=b"\0\0")

    missing_result = audit_dicom(missing)
    short_result = audit_dicom(short_pixels)

    assert missing_result.issues == (DicomIssue.MISSING_REQUIRED_METADATA,)
    assert short_result.issues == (DicomIssue.DECODE_FAILURE,)
    assert (
        short_result.diagnostics[0].root_cause_category
        == DecodeRootCause.UNCOMPRESSED_PIXEL_DATA_INCONSISTENCY.value
    )
    assert short_result.diagnostics[0].root_cause_version == DECODE_ROOT_CAUSE_VERSION
    assert (
        short_result.diagnostics[0].resolution_state
        is DicomResolutionState.EXCLUDED_UNUSABLE_SOURCE
    )


def test_decode_classifier_covers_fixed_data_and_software_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "classifier.dcm"
    _write_dicom(path, _image())
    dataset = pydicom.dcmread(path)
    metadata = extract_metadata(dataset)

    dataset.PixelData = b"\0\0"
    assert (
        classify_decode_root_cause(dataset, metadata)
        is DecodeRootCause.UNCOMPRESSED_PIXEL_DATA_INCONSISTENCY
    )
    dataset.PixelData = _image().astype("<u2").tobytes()

    class AvailableDecoder:
        is_available = True

    class MissingDecoder:
        is_available = False

    monkeypatch.setattr(audit_module, "get_decoder", lambda _: MissingDecoder())
    assert classify_decode_root_cause(dataset, metadata) is DecodeRootCause.DECODER_UNAVAILABLE
    unavailable = audit_dataset(dataset, raw_digest="0" * 64)
    assert unavailable.diagnostics[0].resolution_state is DicomResolutionState.UNRESOLVED_BLOCKER

    def unsupported_decoder(_: object) -> object:
        raise NotImplementedError

    monkeypatch.setattr(audit_module, "get_decoder", unsupported_decoder)
    assert (
        classify_decode_root_cause(dataset, metadata) is DecodeRootCause.UNSUPPORTED_TRANSFER_SYNTAX
    )
    unsupported = audit_dataset(dataset, raw_digest="0" * 64)
    assert unsupported.diagnostics[0].resolution_state is DicomResolutionState.UNRESOLVED_BLOCKER

    monkeypatch.setattr(audit_module, "get_decoder", lambda _: AvailableDecoder())
    dataset.file_meta.TransferSyntaxUID = JPEG2000Lossless
    assert (
        classify_decode_root_cause(dataset, metadata, RuntimeError("private text"))
        is DecodeRootCause.COMPRESSED_SOURCE_DECODE_INCONSISTENCY
    )
    dataset.PixelData = encapsulate([b"synthetic-encapsulated-frame"])
    assert (
        classify_decode_root_cause(dataset, metadata, RuntimeError("private text"))
        is DecodeRootCause.UNEXPECTED_UNEXPLAINED
    )
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.PixelData = _image().astype("<u2").tobytes()
    assert (
        classify_decode_root_cause(dataset, metadata, RuntimeError("private text"))
        is DecodeRootCause.UNEXPECTED_UNEXPLAINED
    )
    assert (
        classify_decode_root_cause(dataset, replace(metadata, number_of_frames=2))
        is DecodeRootCause.FRAME_METADATA_INCONSISTENCY
    )


def test_valid_uncompressed_preflight_decoder_error_remains_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "valid-preflight.dcm"
    _write_dicom(path, _image())
    dataset = pydicom.dcmread(path)

    def decoder_bug(_: object) -> np.ndarray:
        raise ValueError("private decoder detail")

    monkeypatch.setattr(type(dataset), "pixel_array", property(decoder_bug))
    result = audit_dataset(dataset, raw_digest="0" * 64)

    assert result.issues == (DicomIssue.DECODE_FAILURE,)
    assert result.diagnostics[0].root_cause_category == DecodeRootCause.UNEXPECTED_UNEXPLAINED.value
    assert result.diagnostics[0].resolution_state is DicomResolutionState.UNRESOLVED_BLOCKER
    assert result.diagnostics[0].exception_type == "builtins.ValueError"
    assert "private decoder detail" not in repr(result)


def test_pixel_decode_does_not_hide_memory_exhaustion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "memory.dcm"
    _write_dicom(path, _image())
    payload = path.read_bytes()
    dataset = pydicom.dcmread(path)

    def exhaust_memory(_: object) -> np.ndarray:
        raise MemoryError

    monkeypatch.setattr(type(dataset), "pixel_array", property(exhaust_memory))
    with pytest.raises(MemoryError):
        audit_dataset(dataset, raw_digest=hashlib.sha256(payload).hexdigest())


def test_multiframe_is_rejected_before_pixel_fingerprinting(tmp_path: Path) -> None:
    path = tmp_path / "multiframe.dcm"
    frames = np.stack([_image(), _image() + 1])
    _write_dicom(path, frames, number_of_frames=2)

    result = audit_dicom(path)

    assert result.issues == (DicomIssue.MULTI_FRAME,)
    assert result.metadata is not None
    assert result.fingerprints is None
    assert result.diagnostics[0].root_cause_category == DicomIssue.MULTI_FRAME.value
    assert result.diagnostics[0].resolution_state is DicomResolutionState.UNRESOLVED_BLOCKER
    assert (
        DICOM_ISSUE_POLICIES[DicomIssue.MULTI_FRAME].default_resolution_state
        is DicomResolutionState.UNRESOLVED_BLOCKER
    )


def test_invalid_instance_number_is_ignored_when_geometry_is_complete(tmp_path: Path) -> None:
    path = tmp_path / "geometry-authoritative.dcm"
    _write_dicom(path, _image())
    dataset = pydicom.dcmread(path)
    dataset["InstanceNumber"]._value = "not-an-integer"

    result = audit_dataset(dataset, raw_digest="0" * 64)

    assert result.passed
    assert result.metadata is not None
    assert result.metadata.instance_number is None


def test_perceptual_hash_can_be_deferred_for_full_inventory(tmp_path: Path) -> None:
    path = tmp_path / "deferred.dcm"
    _write_dicom(path, _image())

    deferred = audit_dicom(path, include_perceptual_hash=False)
    complete = audit_dicom(path)

    assert deferred.passed
    assert deferred.fingerprints is not None
    assert deferred.fingerprints.perceptual_hash is None
    assert complete.fingerprints is not None
    assert complete.fingerprints.perceptual_hash is not None
    assert deferred.fingerprints.raw_sha256 == complete.fingerprints.raw_sha256
    assert deferred.fingerprints.decoded_sha256 == complete.fingerprints.decoded_sha256


def test_audit_reads_each_source_file_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "single-read.dcm"
    _write_dicom(path, _image())
    original_open = Path.open
    opened = 0

    def tracked_open(self: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal opened
        if self == path:
            opened += 1
        return original_open(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "open", tracked_open)
    assert audit_dicom(path).passed
    assert opened == 1


def test_path_and_already_read_dataset_audits_match(tmp_path: Path) -> None:
    path = tmp_path / "shared-audit.dcm"
    _write_dicom(path, _image())
    payload = path.read_bytes()
    dataset = pydicom.dcmread(path, force=False)
    assert audit_dataset(dataset, raw_digest=hashlib.sha256(payload).hexdigest()) == audit_dicom(
        path
    )


def test_synthetic_jpeg2000_lossless_decodes_through_pinned_plugin(tmp_path: Path) -> None:
    path = tmp_path / "jpeg2000-lossless.dcm"
    pixels = _image(32, 32)
    _write_dicom(path, pixels)
    dataset = pydicom.dcmread(path)
    dataset.compress(JPEG2000Lossless)
    dataset.save_as(path, enforce_file_format=True)

    result = audit_dicom(path)

    assert result.passed
    assert result.fingerprints is not None
    assert result.fingerprints.decoded_sha256 == canonical_decoded_pixel_sha256(pixels)


def test_geometry_order_ignores_shuffled_filenames_and_reversed_instances(
    tmp_path: Path,
) -> None:
    specifications = [
        ("a-last-physically.dcm", 2.0, 1),
        ("m-first-physically.dcm", 0.0, 3),
        ("z-middle-physically.dcm", 1.0, 2),
    ]
    paths: list[Path] = []
    for name, position, instance in specifications:
        path = tmp_path / name
        _write_dicom(path, _image(), position=(0.0, 0.0, position), instance_number=instance)
        paths.append(path)

    paths.sort()
    result = audit_series(_audit_metadata(paths))

    assert result.passed
    assert result.ordering_basis is OrderingBasis.GEOMETRY
    assert result.ordered_indices == (1, 2, 0)
    assert result.projected_positions_mm == pytest.approx((0.0, 1.0, 2.0))
    assert result.median_spacing_mm == pytest.approx(1.0)


def test_oblique_geometry_uses_normal_projection(tmp_path: Path) -> None:
    root = 1.0 / sqrt(2.0)
    orientation = (root, root, 0.0, 0.0, 0.0, 1.0)
    normal = np.asarray((root, -root, 0.0))
    distances = (3.0, 1.0, 2.0)
    paths: list[Path] = []
    for index, distance in enumerate(distances):
        path = tmp_path / f"oblique-{index}.dcm"
        position = tuple(float(value) for value in normal * distance)
        _write_dicom(
            path,
            _image(),
            position=position,
            orientation=orientation,
            instance_number=10 - index,
        )
        paths.append(path)

    result = audit_series(_audit_metadata(paths))

    assert result.passed
    assert result.ordered_indices == (1, 2, 0)
    assert result.projected_positions_mm == pytest.approx((1.0, 2.0, 3.0))


def test_duplicate_positions_are_quarantined(tmp_path: Path) -> None:
    paths: list[Path] = []
    for index, position in enumerate((0.0, 0.005, 1.0)):
        path = tmp_path / f"duplicate-{index}.dcm"
        _write_dicom(path, _image(), position=(0.0, 0.0, position), instance_number=index)
        paths.append(path)

    result = audit_series(_audit_metadata(paths))

    assert not result.passed
    assert DicomIssue.DUPLICATE_POSITION in result.issues


def test_missing_positions_use_flagged_instance_fallback(tmp_path: Path) -> None:
    paths: list[Path] = []
    for index, instance in enumerate((3, 1, 2)):
        path = tmp_path / f"fallback-{index}.dcm"
        _write_dicom(path, _image(), position=None, instance_number=instance)
        paths.append(path)

    result = audit_series(_audit_metadata(paths))

    assert not result.passed
    assert result.ordering_basis is OrderingBasis.INSTANCE_NUMBER
    assert result.ordered_indices == (1, 2, 0)
    assert result.issues[-2:] == (
        DicomIssue.MISSING_GEOMETRY,
        DicomIssue.INSTANCE_FALLBACK,
    )


def test_missing_geometry_with_duplicate_instances_is_ambiguous(tmp_path: Path) -> None:
    paths: list[Path] = []
    for index in range(2):
        path = tmp_path / f"ambiguous-{index}.dcm"
        _write_dicom(path, _image(), position=None, instance_number=1)
        paths.append(path)

    result = audit_series(_audit_metadata(paths))

    assert result.ordering_basis is OrderingBasis.UNAVAILABLE
    assert result.ordered_indices == ()
    assert DicomIssue.AMBIGUOUS_INSTANCE_ORDER in result.issues


def test_invalid_and_drifting_orientation_are_quarantined(tmp_path: Path) -> None:
    invalid_path = tmp_path / "invalid-orientation.dcm"
    _write_dicom(
        invalid_path,
        _image(),
        orientation=(1.001, 0.0, 0.0, 0.0, 1.0, 0.0),
    )
    invalid = audit_series([_metadata(audit_dicom(invalid_path))])
    assert invalid.ordering_basis is OrderingBasis.UNAVAILABLE
    assert DicomIssue.INVALID_ORIENTATION in invalid.issues

    angle = radians(0.75)
    rotated = (cos(angle), sin(angle), 0.0, -sin(angle), cos(angle), 0.0)
    first = tmp_path / "orientation-first.dcm"
    second = tmp_path / "orientation-second.dcm"
    _write_dicom(first, _image(), position=(0.0, 0.0, 0.0), instance_number=1)
    _write_dicom(
        second,
        _image(),
        position=(0.0, 0.0, 1.0),
        orientation=rotated,
        instance_number=2,
    )
    drifting = audit_series(_audit_metadata([first, second]))
    assert DicomIssue.ORIENTATION_DRIFT in drifting.issues


def test_spacing_tolerance_drift_and_large_gap(tmp_path: Path) -> None:
    def series(name: str, positions: tuple[float, ...]) -> list[SliceMetadata]:
        paths: list[Path] = []
        for index, position in enumerate(positions):
            path = tmp_path / f"{name}-{index}.dcm"
            _write_dicom(
                path,
                _image(),
                position=(0.0, 0.0, position),
                instance_number=index,
            )
            paths.append(path)
        return _audit_metadata(paths)

    within_tolerance = audit_series(series("within", (0.0, 1.0, 2.09, 3.09)))
    drifting = audit_series(series("drift", (0.0, 1.0, 2.2, 3.2)))
    gap = audit_series(series("gap", (0.0, 1.0, 2.0, 4.0)))

    assert DicomIssue.SPACING_DRIFT not in within_tolerance.issues
    assert DicomIssue.SPACING_DRIFT in drifting.issues
    assert DicomIssue.LARGE_GAP in gap.issues


def test_dimension_in_plane_spacing_and_pixel_encoding_mismatches(tmp_path: Path) -> None:
    first = tmp_path / "consistent.dcm"
    dimensions = tmp_path / "dimensions.dcm"
    encoding = tmp_path / "encoding.dcm"
    _write_dicom(first, _image(), position=(0.0, 0.0, 0.0), instance_number=1)
    _write_dicom(
        dimensions,
        _image(rows=18),
        position=(0.0, 0.0, 1.0),
        instance_number=2,
        pixel_spacing=(0.75, 0.5),
    )
    _write_dicom(
        encoding,
        _image(),
        position=(0.0, 0.0, 2.0),
        instance_number=3,
        bits_stored=12,
    )

    result = audit_series(_audit_metadata([first, dimensions, encoding]))

    assert DicomIssue.DIMENSION_MISMATCH in result.issues
    assert DicomIssue.IN_PLANE_SPACING_DRIFT in result.issues
    assert DicomIssue.PIXEL_ENCODING_MISMATCH in result.issues


def test_exact_and_near_duplicate_fingerprints(tmp_path: Path) -> None:
    base = _image(rows=32, columns=32)
    near = base.copy()
    near[12:16, 14:18] += 3
    first = tmp_path / "first.dcm"
    exact = tmp_path / "exact.dcm"
    nearby = tmp_path / "near.dcm"
    _write_dicom(first, base, instance_number=1)
    _write_dicom(exact, base, position=(0.0, 0.0, 1.0), instance_number=2)
    _write_dicom(nearby, near, position=(0.0, 0.0, 2.0), instance_number=3)

    first_result = audit_dicom(first)
    exact_result = audit_dicom(exact)
    near_result = audit_dicom(nearby)
    assert first_result.fingerprints is not None
    assert exact_result.fingerprints is not None
    assert near_result.fingerprints is not None

    assert first_result.fingerprints.raw_sha256 == hashlib.sha256(first.read_bytes()).hexdigest()
    assert first_result.fingerprints.raw_sha256 != exact_result.fingerprints.raw_sha256
    assert first_result.fingerprints.decoded_sha256 == exact_result.fingerprints.decoded_sha256
    assert first_result.fingerprints.perceptual_hash == exact_result.fingerprints.perceptual_hash
    assert first_result.fingerprints.decoded_sha256 != near_result.fingerprints.decoded_sha256
    assert (
        phash_hamming(
            first_result.fingerprints.perceptual_hash,
            near_result.fingerprints.perceptual_hash,
        )
        <= 4
    )
    assert normalized_cross_correlation(base, near) > 0.999
    assert gradient_normalized_cross_correlation(base, near) > 0.99


def test_canonical_pixel_hash_normalizes_integer_dtype_and_endianness() -> None:
    image = _image()
    signed = image.astype("<i4")
    big_endian = image.astype(">u2")

    expected = canonical_decoded_pixel_sha256(image)
    canonical = np.ascontiguousarray(image.astype("<i8", copy=False))
    header = (
        b"rsna-knee-decoded-v1\0integer\0"
        + image.shape[0].to_bytes(8, "little")
        + image.shape[1].to_bytes(8, "little")
    )

    assert expected == hashlib.sha256(header + canonical.tobytes(order="C")).hexdigest()
    assert canonical_decoded_pixel_sha256(signed) == expected
    assert canonical_decoded_pixel_sha256(big_endian) == expected


def test_vectorized_bilinear_resize_matches_reference() -> None:
    image = _image(rows=17, columns=19).astype(np.float64)
    height, width = 7, 9
    target_x = np.linspace(0.0, float(image.shape[1] - 1), width)
    horizontal = np.stack([np.interp(target_x, np.arange(image.shape[1]), row) for row in image])
    target_y = np.linspace(0.0, float(image.shape[0] - 1), height)
    expected = np.stack(
        [np.interp(target_y, np.arange(image.shape[0]), column) for column in horizontal.T],
        axis=1,
    )

    np.testing.assert_allclose(
        _resize_bilinear(image, height, width), expected, rtol=0.0, atol=1e-12
    )


def test_rescale_aware_phash_and_similarity_helpers() -> None:
    image = _image(rows=32, columns=32)
    original = perceptual_hash(image)
    offset = perceptual_hash(image, rescale_slope=2.0, rescale_intercept=100.0)
    inverted = perceptual_hash(image, rescale_slope=-1.0)

    assert original == offset == "2a55805580548050"
    assert phash_hamming(original, inverted) >= 20
    assert normalized_cross_correlation(image, image) == pytest.approx(1.0)
    assert gradient_normalized_cross_correlation(image, image) == pytest.approx(1.0)
    assert gradient_magnitude(image).shape == image.shape


def test_phash_and_similarity_inputs_fail_with_sanitized_errors() -> None:
    with pytest.raises(ValueError, match="invalid_perceptual_hash"):
        phash_hamming("private-value", "0" * 16)
    with pytest.raises(ValueError, match="incompatible_images"):
        normalized_cross_correlation(_image(), _image(rows=8))
