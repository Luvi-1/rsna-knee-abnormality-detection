"""Deterministic, anatomy-preserving DICOM-to-model preprocessing.

This module deliberately retains native in-plane orientation.  The only orientation
canonicalization is ordering the slice axis toward the positive dominant LPS axis.  Raw paths,
UIDs, free text, and exception messages are never retained in results or errors.
"""

from __future__ import annotations

import hashlib
import json
import warnings
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
from math import acos, degrees, isfinite
from pathlib import Path
from typing import Final, Literal, cast

import numpy as np
import pydicom
from numpy.typing import NDArray
from pydicom.errors import InvalidDicomError

from rsna_knee.dicom.audit import (
    DUPLICATE_POSITION_TOLERANCE_MM,
    ORIENTATION_TOLERANCE_DEGREES,
    SPACING_ABSOLUTE_TOLERANCE_MM,
    SPACING_RELATIVE_TOLERANCE,
    DecodeRootCause,
    DicomAuditError,
    DicomIssue,
    OrderingBasis,
    SliceMetadata,
    _orientation_vectors,
    _resize_bilinear,
    canonical_decoded_pixel_sha256,
    classify_decode_root_cause,
    extract_metadata,
)

PREPROCESSING_VERSION: Final = "dicom-model-v1"
IN_PLANE_SPACING_ABSOLUTE_TOLERANCE_MM: Final = 1e-4
IN_PLANE_SPACING_RELATIVE_TOLERANCE: Final = 1e-4
REGULAR_AFFINE_ORIENTATION_TOLERANCE_DEGREES: Final = 0.05
REGULAR_AFFINE_DELTA_ABSOLUTE_TOLERANCE_MM: Final = 0.01
REGULAR_AFFINE_DELTA_RELATIVE_TOLERANCE: Final = 0.005

FloatImage = NDArray[np.float64]
FloatVolume = NDArray[np.float64]
ModelTensor = NDArray[np.float32]
Matrix4 = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]


class PipelineIssue(StrEnum):
    """Sanitized fail-closed pipeline failures."""

    FILE_READ = "file_read"
    CONTAINER_PARSE = "container_parse"
    METADATA_INVALID = "metadata_invalid"
    MULTI_FRAME_UNSUPPORTED = "multi_frame_unsupported"
    DECODER_UNAVAILABLE = "decoder_unavailable"
    TRANSFER_SYNTAX_UNSUPPORTED = "transfer_syntax_unsupported"
    PIXEL_DATA_INCONSISTENT = "pixel_data_inconsistent"
    PIXEL_DECODE = "pixel_decode"
    PYDICOM_WARNING = "pydicom_warning"
    DECODED_SHAPE_INVALID = "decoded_shape_invalid"
    NONFINITE_PIXELS = "nonfinite_pixels"
    BLANK_SLICE = "blank_slice"
    CONSTANT_SLICE = "constant_slice"
    EMPTY_SERIES = "empty_series"
    SERIES_METADATA_MISMATCH = "series_metadata_mismatch"
    PIXEL_SPACING_MISSING = "pixel_spacing_missing"
    PIXEL_SPACING_INCONSISTENT = "pixel_spacing_inconsistent"
    ORIENTATION_INVALID = "orientation_invalid"
    ORIENTATION_INCONSISTENT = "orientation_inconsistent"
    IMAGE_POSITION_INCONSISTENT = "image_position_inconsistent"
    PHYSICAL_POSITION_MISSING = "physical_position_missing"
    INSTANCE_FALLBACK_AMBIGUOUS = "instance_fallback_ambiguous"
    INSTANCE_FALLBACK_MODEL_BLOCKED = "instance_fallback_model_blocked"
    DUPLICATE_POSITION = "duplicate_position"
    DUPLICATE_DECODED_SLICE = "duplicate_decoded_slice"
    UNEVEN_SLICE_SPACING = "uneven_slice_spacing"
    REGULAR_AFFINE_UNPROVEN = "regular_affine_unproven"
    LATERALITY_INVALID = "laterality_invalid"
    LATERALITY_INCONSISTENT = "laterality_inconsistent"
    NORMALIZATION_COLLAPSED = "normalization_collapsed"
    PROVENANCE_INVALID = "provenance_invalid"


class NormalizationMode(StrEnum):
    """Supported per-series normalization policies."""

    MINMAX = "minmax"
    ZSCORE = "zscore"
    NONE = "none"


class PipelineError(Exception):
    """Bounded error that never includes paths, identifiers, pixels, or exception text."""

    def __init__(
        self,
        issue: PipelineIssue,
        *,
        stage: str,
        root_cause: str | None = None,
        exception_type: str | None = None,
    ) -> None:
        self.issue = issue
        self.stage = stage
        self.root_cause = root_cause
        self.exception_type = exception_type
        super().__init__(issue.value)


@dataclass(frozen=True, slots=True)
class PreprocessingConfig:
    """Configuration whose canonical hash travels with every model tensor."""

    lower_percentile: float = 1.0
    upper_percentile: float = 99.0
    normalization: NormalizationMode = NormalizationMode.MINMAX
    sample_count: int | None = None
    local_contrast_channel: bool = False
    local_contrast_window: int = 7
    adjacent_slice_channels: bool = False
    difference_channel: bool = False
    resize_rows_columns: tuple[int, int] | None = None
    allow_instance_fallback_for_qa: bool = False

    def __post_init__(self) -> None:
        if (
            not isfinite(self.lower_percentile)
            or not isfinite(self.upper_percentile)
            or not 0.0 <= self.lower_percentile < self.upper_percentile <= 100.0
        ):
            raise ValueError("invalid_percentile_bounds")
        if self.sample_count is not None and self.sample_count < 1:
            raise ValueError("invalid_sample_count")
        if self.local_contrast_window < 3 or self.local_contrast_window % 2 == 0:
            raise ValueError("invalid_local_contrast_window")
        if self.resize_rows_columns is not None and any(
            dimension < 2 for dimension in self.resize_rows_columns
        ):
            raise ValueError("invalid_resize_shape")


@dataclass(frozen=True, slots=True)
class PipelineVersions:
    """Required provenance supplied by the private execution environment."""

    code_commit: str
    source_manifest_version: str
    preprocessing_version: str = PREPROCESSING_VERSION

    def __post_init__(self) -> None:
        if len(self.code_commit) != 40 or any(
            character not in "0123456789abcdef" for character in self.code_commit
        ):
            raise ValueError("invalid_code_commit")
        if not self.source_manifest_version or not self.preprocessing_version:
            raise ValueError("invalid_version")


@dataclass(frozen=True, slots=True)
class DecodedSlice:
    """One strictly decoded, nonconstant, identifier-free DICOM slice."""

    metadata: SliceMetadata
    pixels: FloatImage
    raw_checksum: str
    decoded_checksum: str
    model_pixel_checksum: str
    transfer_syntax: str
    laterality: str | None


@dataclass(frozen=True, slots=True)
class SeriesGeometry:
    """Physical geometry and quality facts for a deterministically ordered series."""

    ordering_basis: OrderingBasis
    canonical_slice_normal_lps: tuple[float, float, float] | None
    projected_positions_mm: tuple[float, ...]
    image_positions_lps: tuple[tuple[float, float, float], ...]
    pixel_spacing_row_column_mm: tuple[float, float]
    per_slice_pixel_spacing_row_column_mm: tuple[tuple[float, float], ...]
    in_plane_spacing_is_consistent: bool
    slice_spacings_mm: tuple[float, ...]
    median_slice_spacing_mm: float | None
    spacing_is_uneven: bool
    affine_lps_slice_row_column: Matrix4 | None
    affine_is_regular: bool
    affine_iop_is_consistent: bool
    affine_delta_is_consistent: bool
    duplicate_pixel_groups: tuple[tuple[int, ...], ...]


@dataclass(frozen=True, slots=True)
class TransformationLedger:
    """Private reconstruction ledger; input hashes must not be published."""

    ordered_input_checksums: tuple[str, ...]
    per_slice_rescale_slope_intercept: tuple[tuple[float, float], ...]
    per_slice_photometric_interpretation: tuple[str, ...]
    per_slice_monochrome1_inversion_applied: tuple[bool, ...]
    slice_axis_positive_dominant_lps: bool
    native_in_plane_pixels_preserved: bool
    horizontal_flip_applied: bool
    laterality_transform: Literal["none"]
    through_plane_resampling_applied: bool
    in_plane_resize_from_to: tuple[tuple[int, int], tuple[int, int]] | None


@dataclass(frozen=True, slots=True)
class OrderedSeries:
    """Decoded slices in canonical physical order or explicit QA-only fallback order."""

    slices: tuple[DecodedSlice, ...]
    geometry: SeriesGeometry
    ledger: TransformationLedger
    laterality: str | None
    slice_lateralities: tuple[str | None, ...]
    input_checksum: str
    model_eligible: bool


@dataclass(frozen=True, slots=True)
class OutputProvenance:
    """Version and checksum envelope stored with each preprocessing output."""

    code_commit: str
    configuration_hash: str
    dicom_library_versions: tuple[tuple[str, str], ...]
    preprocessing_version: str
    source_manifest_version: str
    input_checksum: str
    output_checksum: str


@dataclass(frozen=True, slots=True)
class PreprocessedSeries:
    """Model tensor plus the complete non-lossy transformation account."""

    tensor: ModelTensor
    channel_names: tuple[str, ...]
    sampled_ordered_indices: tuple[int, ...]
    sampled_projected_positions_mm: tuple[float, ...]
    geometry: SeriesGeometry
    ledger: TransformationLedger
    laterality: str | None
    clipping_values: tuple[float, float]
    normalization_statistics: tuple[float, float]
    output_pixel_spacing_row_column_mm: tuple[float, float]
    output_affine_lps_slice_row_column: Matrix4 | None
    provenance: OutputProvenance


def _safe_exception_type(error: BaseException) -> str:
    error_type = type(error)
    module = error_type.__module__
    name = error_type.__qualname__
    if not module.replace(".", "").replace("_", "").isalnum():
        return "builtins.Exception"
    if not name.replace(".", "").replace("_", "").isalnum():
        return "builtins.Exception"
    return f"{module}.{name}"


def _readonly(array: NDArray[np.generic]) -> None:
    array.setflags(write=False)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def preprocessing_config_hash(config: PreprocessingConfig) -> str:
    """Hash the complete validated preprocessing configuration."""

    return hashlib.sha256(_canonical_json(asdict(config))).hexdigest()


def _canonical_float_hash(array: FloatImage) -> str:
    values = np.ascontiguousarray(array, dtype="<f8")
    digest = hashlib.sha256()
    digest.update(_canonical_json({"dtype": "<f8", "shape": list(values.shape)}))
    digest.update(values.tobytes(order="C"))
    return digest.hexdigest()


def _laterality(dataset: pydicom.dataset.Dataset) -> str | None:
    values: list[str] = []
    for attribute in ("ImageLaterality", "Laterality"):
        raw = getattr(dataset, attribute, None)
        if raw is None or str(raw).strip() == "":
            continue
        value = str(raw).strip().upper()
        if value not in {"L", "R", "B", "U"}:
            raise PipelineError(PipelineIssue.LATERALITY_INVALID, stage="metadata_validation")
        values.append(value)
    if len(set(values)) > 1:
        raise PipelineError(PipelineIssue.LATERALITY_INCONSISTENT, stage="metadata_validation")
    return values[0] if values else None


def _decode_root_cause_error(root_cause: DecodeRootCause) -> PipelineError:
    issue = {
        DecodeRootCause.DECODER_UNAVAILABLE: PipelineIssue.DECODER_UNAVAILABLE,
        DecodeRootCause.UNSUPPORTED_TRANSFER_SYNTAX: PipelineIssue.TRANSFER_SYNTAX_UNSUPPORTED,
        DecodeRootCause.UNCOMPRESSED_PIXEL_DATA_INCONSISTENCY: (
            PipelineIssue.PIXEL_DATA_INCONSISTENT
        ),
        DecodeRootCause.COMPRESSED_SOURCE_DECODE_INCONSISTENCY: (
            PipelineIssue.PIXEL_DATA_INCONSISTENT
        ),
        DecodeRootCause.FRAME_METADATA_INCONSISTENCY: PipelineIssue.MULTI_FRAME_UNSUPPORTED,
        DecodeRootCause.UNEXPECTED_UNEXPLAINED: PipelineIssue.PIXEL_DECODE,
    }[root_cause]
    return PipelineError(issue, stage="decode_preflight", root_cause=root_cause.value)


def decode_dicom(path: Path) -> DecodedSlice:
    """Read once, strictly parse once, preflight, decode once, and transform one DICOM."""

    try:
        payload = path.read_bytes()
    except OSError as error:
        raise PipelineError(
            PipelineIssue.FILE_READ,
            stage="file_read",
            exception_type=_safe_exception_type(error),
        ) from None
    raw_checksum = hashlib.sha256(payload).hexdigest()
    try:
        with warnings.catch_warnings(record=True) as read_warnings:
            warnings.simplefilter("always")
            dataset = pydicom.dcmread(BytesIO(payload), force=False)
    except MemoryError:
        raise
    except InvalidDicomError as error:
        raise PipelineError(
            PipelineIssue.CONTAINER_PARSE,
            stage="container_parse",
            exception_type=_safe_exception_type(error),
        ) from None
    except Exception as error:
        raise PipelineError(
            PipelineIssue.CONTAINER_PARSE,
            stage="container_parse",
            exception_type=_safe_exception_type(error),
        ) from None
    read_warning_seen = bool(read_warnings)
    read_warnings.clear()
    if read_warning_seen:
        raise PipelineError(PipelineIssue.PYDICOM_WARNING, stage="container_parse_warning")

    try:
        metadata = extract_metadata(dataset)
        laterality = _laterality(dataset)
    except PipelineError:
        raise
    except DicomAuditError as error:
        raise PipelineError(
            PipelineIssue.METADATA_INVALID,
            stage="metadata_validation",
            root_cause=error.issue.value,
        ) from None
    if metadata.number_of_frames != 1:
        raise PipelineError(
            PipelineIssue.MULTI_FRAME_UNSUPPORTED,
            stage="decode_preflight",
            root_cause=DicomIssue.MULTI_FRAME.value,
        )
    root_cause = classify_decode_root_cause(dataset, metadata)
    if root_cause is not None:
        raise _decode_root_cause_error(root_cause)

    try:
        with warnings.catch_warnings(record=True) as decode_warnings:
            warnings.simplefilter("always")
            decoded = np.asarray(dataset.pixel_array)
    except MemoryError:
        raise
    except Exception as error:
        root_cause = classify_decode_root_cause(dataset, metadata, error)
        if root_cause is None:
            root_cause = DecodeRootCause.UNEXPECTED_UNEXPLAINED
        pipeline_error = _decode_root_cause_error(root_cause)
        raise PipelineError(
            pipeline_error.issue,
            stage="pixel_decode",
            root_cause=root_cause.value,
            exception_type=_safe_exception_type(error),
        ) from None
    decode_warning_seen = bool(decode_warnings)
    decode_warnings.clear()
    if decode_warning_seen:
        raise PipelineError(PipelineIssue.PYDICOM_WARNING, stage="pixel_decode_warning")
    if decoded.ndim != 2 or decoded.shape != (metadata.rows, metadata.columns):
        raise PipelineError(PipelineIssue.DECODED_SHAPE_INVALID, stage="decoded_shape_validation")

    pixels = np.asarray(decoded, dtype=np.float64)
    if not bool(np.all(np.isfinite(pixels))):
        raise PipelineError(PipelineIssue.NONFINITE_PIXELS, stage="pixel_validation")
    with np.errstate(over="ignore", invalid="ignore"):
        pixels = pixels * metadata.rescale_slope + metadata.rescale_intercept
    if not bool(np.all(np.isfinite(pixels))):
        raise PipelineError(PipelineIssue.NONFINITE_PIXELS, stage="rescale_validation")
    if metadata.photometric_interpretation == "MONOCHROME1":
        with np.errstate(over="ignore", invalid="ignore"):
            pixels = -pixels
        if not bool(np.all(np.isfinite(pixels))):
            raise PipelineError(PipelineIssue.NONFINITE_PIXELS, stage="photometric_validation")
    if bool(np.all(pixels == 0.0)):
        raise PipelineError(PipelineIssue.BLANK_SLICE, stage="pixel_validation")
    if float(np.min(pixels)) == float(np.max(pixels)):
        raise PipelineError(PipelineIssue.CONSTANT_SLICE, stage="pixel_validation")
    pixels = np.ascontiguousarray(pixels, dtype=np.float64)
    _readonly(pixels)

    transfer_syntax = str(dataset.file_meta.TransferSyntaxUID)
    return DecodedSlice(
        metadata=metadata,
        pixels=pixels,
        raw_checksum=raw_checksum,
        decoded_checksum=canonical_decoded_pixel_sha256(cast(NDArray[np.generic], decoded)),
        model_pixel_checksum=_canonical_float_hash(pixels),
        transfer_syntax=transfer_syntax,
        laterality=laterality,
    )


def _aggregate_input_checksum(slices: Sequence[DecodedSlice]) -> str:
    return hashlib.sha256(
        _canonical_json({"raw_sha256": sorted(item.raw_checksum for item in slices)})
    ).hexdigest()


def _check_series_metadata(
    slices: Sequence[DecodedSlice],
) -> tuple[tuple[tuple[float, float], ...], bool]:
    first = slices[0].metadata
    if any(
        (item.metadata.rows, item.metadata.columns) != (first.rows, first.columns)
        for item in slices[1:]
    ) or any(item.metadata.pixel_signature != first.pixel_signature for item in slices[1:]):
        raise PipelineError(
            PipelineIssue.SERIES_METADATA_MISMATCH, stage="series_metadata_validation"
        )
    spacings = [item.metadata.pixel_spacing for item in slices]
    if any(spacing is None for spacing in spacings):
        raise PipelineError(PipelineIssue.PIXEL_SPACING_MISSING, stage="geometry_validation")
    parsed_spacings = cast(tuple[tuple[float, float], ...], tuple(spacings))
    reference = parsed_spacings[0]
    consistent = True
    for current in parsed_spacings[1:]:
        for expected, observed in zip(reference, current, strict=True):
            tolerance = max(
                IN_PLANE_SPACING_ABSOLUTE_TOLERANCE_MM,
                IN_PLANE_SPACING_RELATIVE_TOLERANCE * expected,
            )
            if abs(expected - observed) > tolerance:
                consistent = False
    return parsed_spacings, consistent


def _angle_degrees(left: NDArray[np.float64], right: NDArray[np.float64]) -> float:
    return degrees(acos(float(np.clip(np.dot(left, right), -1.0, 1.0))))


def _matrix4(
    slice_axis: NDArray[np.float64],
    row_axis: NDArray[np.float64],
    column_axis: NDArray[np.float64],
    origin: tuple[float, float, float],
) -> Matrix4:
    return cast(
        Matrix4,
        tuple(
            tuple(
                float(value)
                for value in (
                    slice_axis[coordinate],
                    row_axis[coordinate],
                    column_axis[coordinate],
                    origin[coordinate],
                )
            )
            for coordinate in range(3)
        )
        + ((0.0, 0.0, 0.0, 1.0),),
    )


def order_series(
    slices: Sequence[DecodedSlice], *, allow_instance_fallback_for_qa: bool = False
) -> OrderedSeries:
    """Order by projected LPS position; unique InstanceNumber is QA-only fallback."""

    if not slices:
        raise PipelineError(PipelineIssue.EMPTY_SERIES, stage="series_validation")
    source_pixel_spacings, in_plane_spacing_consistent = _check_series_metadata(slices)
    lateralities = tuple(item.laterality for item in slices)
    known_lateralities = {value for value in lateralities if value is not None}
    if len(known_lateralities) > 1:
        raise PipelineError(PipelineIssue.LATERALITY_INCONSISTENT, stage="series_validation")
    laterality = next(iter(known_lateralities)) if len(known_lateralities) == 1 else None
    if any(value is None for value in lateralities):
        # Preserve missingness; do not infer missing slice laterality from neighbors.
        laterality = None
    geometry_available = all(
        item.metadata.image_orientation is not None and item.metadata.image_position is not None
        for item in slices
    )
    normal_tuple: tuple[float, float, float] | None = None
    positions: tuple[float, ...] = ()
    image_positions: tuple[tuple[float, float, float], ...] = ()
    spacings: tuple[float, ...] = ()
    median_spacing: float | None = None
    uneven = False
    affine: Matrix4 | None = None
    affine_regular = False
    affine_iop_consistent = False
    affine_delta_consistent = False

    if not geometry_available:
        if not allow_instance_fallback_for_qa:
            raise PipelineError(PipelineIssue.PHYSICAL_POSITION_MISSING, stage="series_ordering")
        instances = [item.metadata.instance_number for item in slices]
        if any(value is None for value in instances) or len(set(instances)) != len(instances):
            raise PipelineError(PipelineIssue.INSTANCE_FALLBACK_AMBIGUOUS, stage="series_ordering")
        order = sorted(
            range(len(slices)),
            key=lambda index: (cast(int, instances[index]), slices[index].raw_checksum),
        )
        basis = OrderingBasis.INSTANCE_NUMBER
    else:
        orientations = [
            cast(tuple[float, float, float, float, float, float], item.metadata.image_orientation)
            for item in slices
        ]
        vectors = [_orientation_vectors(value) for value in orientations]
        if any(value is None for value in vectors):
            raise PipelineError(PipelineIssue.ORIENTATION_INVALID, stage="series_ordering")
        valid_vectors = cast(
            list[tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]], vectors
        )
        reference_row, reference_column, reference_normal = valid_vectors[0]
        maximum_orientation_angle = 0.0
        for row, column, normal in valid_vectors[1:]:
            maximum_orientation_angle = max(
                maximum_orientation_angle,
                _angle_degrees(reference_row, row),
                _angle_degrees(reference_column, column),
                _angle_degrees(reference_normal, normal),
            )
            if maximum_orientation_angle > ORIENTATION_TOLERANCE_DEGREES:
                raise PipelineError(PipelineIssue.ORIENTATION_INCONSISTENT, stage="series_ordering")
        affine_iop_consistent = (
            maximum_orientation_angle <= REGULAR_AFFINE_ORIENTATION_TOLERANCE_DEGREES
        )
        canonical_normal = np.array(reference_normal, dtype=np.float64, copy=True)
        dominant_axis = int(np.argmax(np.abs(canonical_normal)))
        if canonical_normal[dominant_axis] < 0.0:
            canonical_normal *= -1.0
        normal_tuple = cast(tuple[float, float, float], tuple(float(v) for v in canonical_normal))
        source_positions = [
            cast(tuple[float, float, float], item.metadata.image_position) for item in slices
        ]
        source_projections = [
            float(np.dot(np.asarray(position, dtype=np.float64), canonical_normal))
            for position in source_positions
        ]
        order = sorted(
            range(len(slices)),
            key=lambda index: (source_projections[index], slices[index].raw_checksum),
        )
        positions = tuple(source_projections[index] for index in order)
        image_positions = tuple(source_positions[index] for index in order)
        differences = np.diff(np.asarray(positions, dtype=np.float64))
        if bool(np.any(differences <= DUPLICATE_POSITION_TOLERANCE_MM)):
            raise PipelineError(PipelineIssue.DUPLICATE_POSITION, stage="series_ordering")
        position_deltas = np.diff(np.asarray(image_positions, dtype=np.float64), axis=0)
        in_plane_deltas = position_deltas - differences[:, None] * canonical_normal[None, :]
        position_tolerances = np.maximum(
            SPACING_ABSOLUTE_TOLERANCE_MM,
            SPACING_RELATIVE_TOLERANCE * differences,
        )
        if bool(np.any(np.linalg.norm(in_plane_deltas, axis=1) > position_tolerances)):
            raise PipelineError(
                PipelineIssue.IMAGE_POSITION_INCONSISTENT,
                stage="series_ordering",
            )
        spacings = tuple(float(value) for value in differences)
        if spacings:
            median_spacing = float(np.median(differences))
            tolerance = max(
                SPACING_ABSOLUTE_TOLERANCE_MM,
                SPACING_RELATIVE_TOLERANCE * median_spacing,
            )
            uneven = bool(np.any(np.abs(differences - median_spacing) > tolerance))
            affine_delta_tolerance = max(
                REGULAR_AFFINE_DELTA_ABSOLUTE_TOLERANCE_MM,
                REGULAR_AFFINE_DELTA_RELATIVE_TOLERANCE * median_spacing,
            )
            expected_deltas = canonical_normal[None, :] * median_spacing
            affine_delta_consistent = bool(
                np.all(
                    np.linalg.norm(position_deltas - expected_deltas, axis=1)
                    <= affine_delta_tolerance
                )
            )
        if (
            median_spacing is not None
            and not uneven
            and in_plane_spacing_consistent
            and affine_iop_consistent
            and affine_delta_consistent
        ):
            pixel_spacing = source_pixel_spacings[order[0]]
            row_spacing, column_spacing = pixel_spacing
            affine = _matrix4(
                canonical_normal * median_spacing,
                reference_column * row_spacing,
                reference_row * column_spacing,
                image_positions[0],
            )
            affine_regular = True
        basis = OrderingBasis.GEOMETRY

    ordered = tuple(slices[index] for index in order)
    ordered_pixel_spacings = tuple(source_pixel_spacings[index] for index in order)
    pixel_spacing = ordered_pixel_spacings[0]
    ordered_lateralities = tuple(item.laterality for item in ordered)
    by_pixel: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(ordered):
        by_pixel[item.model_pixel_checksum].append(index)
    duplicate_groups = tuple(
        tuple(indices) for _, indices in sorted(by_pixel.items()) if len(indices) > 1
    )
    ledger = TransformationLedger(
        ordered_input_checksums=tuple(item.raw_checksum for item in ordered),
        per_slice_rescale_slope_intercept=tuple(
            (item.metadata.rescale_slope, item.metadata.rescale_intercept) for item in ordered
        ),
        per_slice_photometric_interpretation=tuple(
            item.metadata.photometric_interpretation for item in ordered
        ),
        per_slice_monochrome1_inversion_applied=tuple(
            item.metadata.photometric_interpretation == "MONOCHROME1" for item in ordered
        ),
        slice_axis_positive_dominant_lps=basis is OrderingBasis.GEOMETRY,
        native_in_plane_pixels_preserved=True,
        horizontal_flip_applied=False,
        laterality_transform="none",
        through_plane_resampling_applied=False,
        in_plane_resize_from_to=None,
    )
    geometry = SeriesGeometry(
        ordering_basis=basis,
        canonical_slice_normal_lps=normal_tuple,
        projected_positions_mm=positions,
        image_positions_lps=image_positions,
        pixel_spacing_row_column_mm=pixel_spacing,
        per_slice_pixel_spacing_row_column_mm=ordered_pixel_spacings,
        in_plane_spacing_is_consistent=in_plane_spacing_consistent,
        slice_spacings_mm=spacings,
        median_slice_spacing_mm=median_spacing,
        spacing_is_uneven=uneven,
        affine_lps_slice_row_column=affine,
        affine_is_regular=affine_regular,
        affine_iop_is_consistent=affine_iop_consistent,
        affine_delta_is_consistent=affine_delta_consistent,
        duplicate_pixel_groups=duplicate_groups,
    )
    return OrderedSeries(
        slices=ordered,
        geometry=geometry,
        ledger=ledger,
        laterality=laterality,
        slice_lateralities=ordered_lateralities,
        input_checksum=_aggregate_input_checksum(slices),
        model_eligible=(
            basis is OrderingBasis.GEOMETRY
            and in_plane_spacing_consistent
            and not uneven
            and not duplicate_groups
            and affine_regular
        ),
    )


def load_series(paths: Sequence[Path], config: PreprocessingConfig) -> OrderedSeries:
    """Decode each input exactly once, then produce a private ordered series."""

    return order_series(
        tuple(decode_dicom(path) for path in paths),
        allow_instance_fallback_for_qa=config.allow_instance_fallback_for_qa,
    )


def deterministic_slice_indices(
    positions_mm: Sequence[float], sample_count: int
) -> tuple[int, ...]:
    """Choose nearest slices to evenly spaced physical targets with stable lower-index ties."""

    if sample_count < 1 or not positions_mm:
        raise ValueError("invalid_sampling_request")
    positions = np.asarray(positions_mm, dtype=np.float64)
    if positions.ndim != 1 or not bool(np.all(np.isfinite(positions))):
        raise ValueError("invalid_positions")
    if bool(np.any(np.diff(positions) <= 0.0)):
        raise ValueError("positions_not_strictly_increasing")
    targets = np.linspace(float(positions[0]), float(positions[-1]), sample_count)
    return tuple(int(np.argmin(np.abs(positions - target))) for target in targets)


def _normalize_volume(
    volume: FloatVolume, config: PreprocessingConfig
) -> tuple[FloatVolume, tuple[float, float], tuple[float, float]]:
    lower, upper = (
        float(value)
        for value in np.percentile(
            volume,
            (config.lower_percentile, config.upper_percentile),
            method="linear",
        )
    )
    if not isfinite(lower) or not isfinite(upper) or upper <= lower:
        raise PipelineError(PipelineIssue.NORMALIZATION_COLLAPSED, stage="normalization")
    clipped = np.clip(volume, lower, upper)
    if config.normalization is NormalizationMode.MINMAX:
        center, scale = lower, upper - lower
        normalized = (clipped - center) / scale
    elif config.normalization is NormalizationMode.ZSCORE:
        center = float(np.mean(clipped, dtype=np.float64))
        scale = float(np.std(clipped, dtype=np.float64))
        if not isfinite(scale) or scale <= 0.0:
            raise PipelineError(PipelineIssue.NORMALIZATION_COLLAPSED, stage="normalization")
        normalized = (clipped - center) / scale
    else:
        center, scale = 0.0, 1.0
        normalized = clipped
    return (
        cast(FloatVolume, np.asarray(normalized, dtype=np.float64)),
        (lower, upper),
        (center, scale),
    )


def _box_local_contrast(image: FloatImage, window: int) -> FloatImage:
    radius = window // 2
    padded = np.pad(image, radius, mode="edge")
    integral = np.pad(np.cumsum(np.cumsum(padded, axis=0), axis=1), ((1, 0), (1, 0)))
    height, width = image.shape
    sums = (
        integral[window : window + height, window : window + width]
        - integral[:height, window : window + width]
        - integral[window : window + height, :width]
        + integral[:height, :width]
    )
    return image - sums / float(window * window)


def _resize_volume(volume: FloatVolume, shape: tuple[int, int] | None) -> FloatVolume:
    if shape is None or volume.shape[1:] == shape:
        return volume
    return cast(
        FloatVolume,
        np.stack([_resize_bilinear(image, *shape) for image in volume], axis=0),
    )


def _resized_spacing(
    spacing: tuple[float, float], source: tuple[int, int], target: tuple[int, int]
) -> tuple[float, float]:
    return tuple(
        original_spacing * (source_size - 1) / (target_size - 1)
        for original_spacing, source_size, target_size in zip(spacing, source, target, strict=True)
    )  # type: ignore[return-value]


def _output_affine(
    series: OrderedSeries,
    spacing: tuple[float, float],
    selected: tuple[int, ...],
) -> Matrix4 | None:
    geometry = series.geometry
    if (
        geometry.canonical_slice_normal_lps is None
        or not geometry.image_positions_lps
        or len(selected) < 2
    ):
        return None
    selected_positions = np.asarray(
        [geometry.projected_positions_mm[index] for index in selected], dtype=np.float64
    )
    differences = np.diff(selected_positions)
    if bool(np.any(differences <= DUPLICATE_POSITION_TOLERANCE_MM)):
        return None
    slice_spacing = float(np.median(differences))
    tolerance = max(
        REGULAR_AFFINE_DELTA_ABSOLUTE_TOLERANCE_MM,
        REGULAR_AFFINE_DELTA_RELATIVE_TOLERANCE * slice_spacing,
    )
    if bool(np.any(np.abs(differences - slice_spacing) > tolerance)):
        return None
    orientation = cast(
        tuple[float, float, float, float, float, float],
        series.slices[0].metadata.image_orientation,
    )
    return _matrix4(
        np.asarray(geometry.canonical_slice_normal_lps) * slice_spacing,
        np.asarray(orientation[3:]) * spacing[0],
        np.asarray(orientation[:3]) * spacing[1],
        geometry.image_positions_lps[selected[0]],
    )


def _output_checksum(tensor: ModelTensor, metadata: object) -> str:
    canonical = np.ascontiguousarray(tensor, dtype="<f4")
    digest = hashlib.sha256()
    digest.update(
        _canonical_json({"dtype": "<f4", "shape": list(canonical.shape), "metadata": metadata})
    )
    digest.update(canonical.tobytes(order="C"))
    return digest.hexdigest()


@lru_cache(maxsize=1)
def _runtime_library_versions() -> tuple[tuple[str, str], ...]:
    package_names = (
        "numpy",
        "pydicom",
        "pylibjpeg",
        "pylibjpeg-libjpeg",
        "pylibjpeg-openjpeg",
    )
    versions: list[tuple[str, str]] = []
    for package_name in package_names:
        try:
            package_version = version(package_name)
        except PackageNotFoundError:
            package_version = "unavailable"
        versions.append((package_name, package_version))
    return tuple(versions)


def preprocess_series(
    series: OrderedSeries,
    config: PreprocessingConfig,
    versions: PipelineVersions,
) -> PreprocessedSeries:
    """Create a deterministic model tensor without in-plane flips or through-plane resampling."""

    if series.geometry.duplicate_pixel_groups:
        raise PipelineError(PipelineIssue.DUPLICATE_DECODED_SLICE, stage="series_eligibility")
    if series.geometry.spacing_is_uneven:
        raise PipelineError(PipelineIssue.UNEVEN_SLICE_SPACING, stage="series_eligibility")
    if not series.geometry.in_plane_spacing_is_consistent:
        raise PipelineError(PipelineIssue.PIXEL_SPACING_INCONSISTENT, stage="series_eligibility")
    if series.geometry.ordering_basis is not OrderingBasis.GEOMETRY:
        raise PipelineError(
            PipelineIssue.INSTANCE_FALLBACK_MODEL_BLOCKED, stage="model_preprocessing"
        )
    if not series.geometry.affine_is_regular:
        raise PipelineError(PipelineIssue.REGULAR_AFFINE_UNPROVEN, stage="series_eligibility")
    if not series.model_eligible:
        raise RuntimeError("model_eligibility_invariant")
    volume = cast(FloatVolume, np.stack([item.pixels for item in series.slices], axis=0))
    normalized, clipping, normalization = _normalize_volume(volume, config)
    source_shape = cast(tuple[int, int], tuple(int(value) for value in normalized.shape[1:]))
    target_shape = config.resize_rows_columns or source_shape
    model_volume = _resize_volume(normalized, config.resize_rows_columns)
    sample_count = config.sample_count or len(series.slices)
    selected = deterministic_slice_indices(series.geometry.projected_positions_mm, sample_count)

    channel_names = ["base"]
    if config.local_contrast_channel:
        channel_names.append("local_contrast")
    if config.adjacent_slice_channels:
        channel_names.extend(("previous", "next"))
    if config.difference_channel:
        channel_names.append("next_minus_previous")
    samples: list[NDArray[np.float64]] = []
    for index in selected:
        previous = model_volume[max(0, index - 1)]
        base = model_volume[index]
        following = model_volume[min(len(model_volume) - 1, index + 1)]
        channels: list[FloatImage] = [base]
        if config.local_contrast_channel:
            channels.append(_box_local_contrast(base, config.local_contrast_window))
        if config.adjacent_slice_channels:
            channels.extend((previous, following))
        if config.difference_channel:
            channels.append(cast(FloatImage, following - previous))
        samples.append(np.stack(channels, axis=0))
    tensor = np.ascontiguousarray(np.stack(samples, axis=0), dtype=np.float32)
    _readonly(tensor)

    output_spacing = _resized_spacing(
        series.geometry.pixel_spacing_row_column_mm, source_shape, target_shape
    )
    output_affine = _output_affine(series, output_spacing, selected)
    resize_record = None if target_shape == source_shape else (source_shape, target_shape)
    ledger = TransformationLedger(
        ordered_input_checksums=series.ledger.ordered_input_checksums,
        per_slice_rescale_slope_intercept=series.ledger.per_slice_rescale_slope_intercept,
        per_slice_photometric_interpretation=series.ledger.per_slice_photometric_interpretation,
        per_slice_monochrome1_inversion_applied=(
            series.ledger.per_slice_monochrome1_inversion_applied
        ),
        slice_axis_positive_dominant_lps=True,
        native_in_plane_pixels_preserved=resize_record is None,
        horizontal_flip_applied=False,
        laterality_transform="none",
        through_plane_resampling_applied=False,
        in_plane_resize_from_to=resize_record,
    )
    configuration_hash = preprocessing_config_hash(config)
    library_versions = _runtime_library_versions()
    checksum_metadata = {
        "channels": channel_names,
        "selected": selected,
        "selected_positions_mm": [series.geometry.projected_positions_mm[i] for i in selected],
        "geometry": asdict(series.geometry),
        "ledger": asdict(ledger),
        "laterality": series.laterality,
        "clipping": clipping,
        "normalization": normalization,
        "output_spacing": output_spacing,
        "output_affine": output_affine,
        "code_commit": versions.code_commit,
        "configuration_hash": configuration_hash,
        "libraries": library_versions,
        "preprocessing_version": versions.preprocessing_version,
        "source_manifest_version": versions.source_manifest_version,
        "input_checksum": series.input_checksum,
    }
    output_checksum = _output_checksum(tensor, checksum_metadata)
    provenance = OutputProvenance(
        code_commit=versions.code_commit,
        configuration_hash=configuration_hash,
        dicom_library_versions=library_versions,
        preprocessing_version=versions.preprocessing_version,
        source_manifest_version=versions.source_manifest_version,
        input_checksum=series.input_checksum,
        output_checksum=output_checksum,
    )
    return PreprocessedSeries(
        tensor=tensor,
        channel_names=tuple(channel_names),
        sampled_ordered_indices=selected,
        sampled_projected_positions_mm=tuple(
            series.geometry.projected_positions_mm[index] for index in selected
        ),
        geometry=series.geometry,
        ledger=ledger,
        laterality=series.laterality,
        clipping_values=clipping,
        normalization_statistics=normalization,
        output_pixel_spacing_row_column_mm=output_spacing,
        output_affine_lps_slice_row_column=output_affine,
        provenance=provenance,
    )


def dicom_to_model(
    paths: Sequence[Path], config: PreprocessingConfig, versions: PipelineVersions
) -> PreprocessedSeries:
    """Convenience boundary that decodes once and preprocesses once."""

    return preprocess_series(load_series(paths, config), config, versions)
