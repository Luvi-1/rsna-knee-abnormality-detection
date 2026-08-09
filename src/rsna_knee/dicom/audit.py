"""Privacy-safe DICOM integrity checks and deterministic image fingerprints.

The public results intentionally contain no paths, UIDs, free text, or raw metadata.  Callers keep
their own private file-to-result mapping inside the authorized environment.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
from math import acos, degrees, isfinite
from pathlib import Path
from string import hexdigits
from typing import Final, cast

import numpy as np
import pydicom
from numpy.typing import NDArray
from pydicom.dataset import Dataset
from pydicom.encaps import generate_frames
from pydicom.errors import InvalidDicomError
from pydicom.pixels.decoders.base import get_decoder
from pydicom.uid import UID

IOP_ORTHONORMAL_TOLERANCE: Final = 1e-4
ORIENTATION_TOLERANCE_DEGREES: Final = 0.5
DUPLICATE_POSITION_TOLERANCE_MM: Final = 0.01
SPACING_ABSOLUTE_TOLERANCE_MM: Final = 0.1
SPACING_RELATIVE_TOLERANCE: Final = 0.05
GAP_MULTIPLIER: Final = 1.5
PHASH_RESIZE: Final = 32
PHASH_LOW_FREQUENCY_SIZE: Final = 8

FloatImage = NDArray[np.float64]
NumericArray = NDArray[np.generic]


class DicomIssue(StrEnum):
    """Sanitized terminal and series-level integrity reasons."""

    UNREADABLE = "unreadable"
    MISSING_REQUIRED_METADATA = "missing_required_metadata"
    MISSING_PIXEL_DATA = "missing_pixel_data"
    INVALID_ORIENTATION = "invalid_orientation"
    INVALID_POSITION = "invalid_position"
    INVALID_INSTANCE_NUMBER = "invalid_instance_number"
    INVALID_PIXEL_ENCODING = "invalid_pixel_encoding"
    UNSUPPORTED_PIXEL_LAYOUT = "unsupported_pixel_layout"
    INVALID_PIXEL_SPACING = "invalid_pixel_spacing"
    INVALID_RESCALE = "invalid_rescale"
    MULTI_FRAME = "multi_frame"
    DECODE_FAILURE = "decode_failure"
    DECODED_DIMENSION_MISMATCH = "decoded_dimension_mismatch"
    EMPTY_SERIES = "empty_series"
    DIMENSION_MISMATCH = "dimension_mismatch"
    PIXEL_ENCODING_MISMATCH = "pixel_encoding_mismatch"
    MISSING_PIXEL_SPACING = "missing_pixel_spacing"
    IN_PLANE_SPACING_DRIFT = "in_plane_spacing_drift"
    MISSING_GEOMETRY = "missing_geometry"
    ORIENTATION_DRIFT = "orientation_drift"
    DUPLICATE_POSITION = "duplicate_position"
    SPACING_DRIFT = "spacing_drift"
    LARGE_GAP = "large_gap"
    INSTANCE_FALLBACK = "instance_fallback"
    AMBIGUOUS_INSTANCE_ORDER = "ambiguous_instance_order"
    INVALID_IMAGE = "invalid_image"


DICOM_ISSUE_DISPOSITION_VERSION: Final = "dicom-issue-disposition-v1"
DECODE_ROOT_CAUSE_VERSION: Final = "decode-root-cause-v1"
DICOM_ISSUE_RESOLUTION_VERSION: Final = "dicom-issue-resolution-v1"


class DicomIssueScope(StrEnum):
    """Manifest entity to which an integrity issue is assigned."""

    FILE = "file"
    SERIES = "series"


class DicomIssueDisposition(StrEnum):
    """Deterministic terminal handling for a DICOM integrity issue."""

    FILE_QUARANTINE = "file_quarantine"
    SERIES_QUARANTINE = "series_quarantine"
    SERIES_FALLBACK_QUARANTINE = "series_fallback_quarantine"


class DecodeRootCause(StrEnum):
    """Fixed private taxonomy for pixel-decoding failures."""

    DECODER_UNAVAILABLE = "decoder_unavailable"
    UNSUPPORTED_TRANSFER_SYNTAX = "unsupported_transfer_syntax"
    COMPRESSED_SOURCE_DECODE_INCONSISTENCY = "compressed_source_decode_inconsistency"
    UNCOMPRESSED_PIXEL_DATA_INCONSISTENCY = "uncompressed_pixel_data_inconsistency"
    FRAME_METADATA_INCONSISTENCY = "frame_metadata_inconsistency"
    UNEXPECTED_UNEXPLAINED = "unexpected_unexplained"


DECODE_ROOT_CAUSE_TAXONOMY: Final = tuple(item.value for item in DecodeRootCause)
_UNRESOLVED_ROOT_CAUSES: Final = frozenset(
    {
        DecodeRootCause.DECODER_UNAVAILABLE.value,
        DecodeRootCause.UNSUPPORTED_TRANSFER_SYNTAX.value,
        DecodeRootCause.UNEXPECTED_UNEXPLAINED.value,
        "dicom_parse_io_error",
        "file_read_io_error",
    }
)


class DicomResolutionState(StrEnum):
    """Private adjudication state for a terminal DICOM issue."""

    EXCLUDED_UNUSABLE_SOURCE = "excluded_unusable_source"
    UNRESOLVED_BLOCKER = "unresolved_blocker"


@dataclass(frozen=True, slots=True)
class DicomIssuePolicy:
    """Versioned private disposition attached to every emitted issue code."""

    scope: DicomIssueScope
    severity: str
    terminal_effect: str
    disposition: DicomIssueDisposition
    scope_impact: str
    default_root_cause: str
    default_resolution_state: DicomResolutionState
    resolution_version: str = DICOM_ISSUE_RESOLUTION_VERSION
    version: str = DICOM_ISSUE_DISPOSITION_VERSION


_FILE_ISSUES: Final = frozenset(
    {
        DicomIssue.UNREADABLE,
        DicomIssue.MISSING_REQUIRED_METADATA,
        DicomIssue.MISSING_PIXEL_DATA,
        DicomIssue.INVALID_ORIENTATION,
        DicomIssue.INVALID_POSITION,
        DicomIssue.INVALID_INSTANCE_NUMBER,
        DicomIssue.INVALID_PIXEL_ENCODING,
        DicomIssue.UNSUPPORTED_PIXEL_LAYOUT,
        DicomIssue.INVALID_PIXEL_SPACING,
        DicomIssue.INVALID_RESCALE,
        DicomIssue.MULTI_FRAME,
        DicomIssue.DECODE_FAILURE,
        DicomIssue.DECODED_DIMENSION_MISMATCH,
        DicomIssue.INVALID_IMAGE,
    }
)
_SERIES_ISSUES: Final = frozenset(set(DicomIssue) - _FILE_ISSUES)

DICOM_ISSUE_POLICIES: Final = {
    **{
        issue: DicomIssuePolicy(
            scope=DicomIssueScope.FILE,
            severity="error",
            terminal_effect="quarantine",
            disposition=DicomIssueDisposition.FILE_QUARANTINE,
            scope_impact="file_and_parent_series_quarantined",
            default_root_cause=(
                DecodeRootCause.UNEXPECTED_UNEXPLAINED.value
                if issue in {DicomIssue.UNREADABLE, DicomIssue.DECODE_FAILURE}
                else issue.value
            ),
            default_resolution_state=(
                DicomResolutionState.UNRESOLVED_BLOCKER
                if issue
                in {DicomIssue.UNREADABLE, DicomIssue.MULTI_FRAME, DicomIssue.DECODE_FAILURE}
                else DicomResolutionState.EXCLUDED_UNUSABLE_SOURCE
            ),
        )
        for issue in _FILE_ISSUES
    },
    **{
        issue: DicomIssuePolicy(
            scope=DicomIssueScope.SERIES,
            severity=("warning" if issue is DicomIssue.INSTANCE_FALLBACK else "error"),
            terminal_effect="quarantine",
            disposition=(
                DicomIssueDisposition.SERIES_FALLBACK_QUARANTINE
                if issue is DicomIssue.INSTANCE_FALLBACK
                else DicomIssueDisposition.SERIES_QUARANTINE
            ),
            scope_impact="series_and_parent_study_quarantined",
            default_root_cause=issue.value,
            default_resolution_state=DicomResolutionState.EXCLUDED_UNUSABLE_SOURCE,
        )
        for issue in _SERIES_ISSUES
    },
}

if frozenset(DICOM_ISSUE_POLICIES) != frozenset(DicomIssue):
    raise RuntimeError("dicom_issue_disposition_incomplete")


def dicom_issue_policy(issue: DicomIssue) -> DicomIssuePolicy:
    """Return the exhaustive, versioned disposition for ``issue``."""

    return DICOM_ISSUE_POLICIES[issue]


class OrderingBasis(StrEnum):
    """Evidence used to order a series."""

    GEOMETRY = "geometry"
    INSTANCE_NUMBER = "instance_number"
    UNAVAILABLE = "unavailable"


class DicomAuditError(Exception):
    """Exception whose text exposes only a sanitized issue code."""

    def __init__(self, issue: DicomIssue) -> None:
        self.issue = issue
        super().__init__(issue.value)


@dataclass(frozen=True, slots=True)
class SliceMetadata:
    """Non-identifying fields required for integrity and deterministic decoding."""

    rows: int
    columns: int
    samples_per_pixel: int
    photometric_interpretation: str
    pixel_representation: int
    bits_allocated: int
    bits_stored: int
    high_bit: int
    number_of_frames: int
    image_orientation: tuple[float, float, float, float, float, float] | None
    image_position: tuple[float, float, float] | None
    instance_number: int | None
    pixel_spacing: tuple[float, float] | None
    slice_thickness: float | None
    spacing_between_slices: float | None
    rescale_slope: float
    rescale_intercept: float

    @property
    def pixel_signature(self) -> tuple[int, str, int, int, int, int]:
        """Return the non-identifying fields that define stored-pixel interpretation."""

        return (
            self.samples_per_pixel,
            self.photometric_interpretation,
            self.pixel_representation,
            self.bits_allocated,
            self.bits_stored,
            self.high_bit,
        )


@dataclass(frozen=True, slots=True)
class PixelFingerprints:
    """Private fingerprints; never publish values derived from competition pixels."""

    raw_sha256: str
    decoded_sha256: str
    perceptual_hash: str | None


@dataclass(frozen=True, slots=True)
class DicomDiagnostic:
    """Sanitized private case detail; exception messages are never retained."""

    issue: DicomIssue
    root_cause_category: str
    root_cause_version: str
    resolution_state: DicomResolutionState
    resolution_version: str
    stage: str
    exception_type: str | None


@dataclass(frozen=True, slots=True)
class DicomAuditResult:
    """One file's sanitized terminal result."""

    metadata: SliceMetadata | None
    fingerprints: PixelFingerprints | None
    issues: tuple[DicomIssue, ...]
    diagnostics: tuple[DicomDiagnostic, ...] = ()

    @property
    def passed(self) -> bool:
        """Whether header validation and pixel decoding both succeeded."""

        return not self.issues and self.metadata is not None and self.fingerprints is not None


def _safe_exception_type(error: BaseException | None) -> str | None:
    if error is None:
        return None
    error_type = type(error)
    module = error_type.__module__
    qualified_name = error_type.__qualname__
    if (
        not module.replace(".", "").replace("_", "").isalnum()
        or not qualified_name.replace(".", "").replace("_", "").isalnum()
    ):
        return "builtins.Exception"
    return f"{module}.{qualified_name}"


def classified_dicom_failure(
    issue: DicomIssue,
    *,
    root_cause_category: str,
    stage: str,
    error: BaseException | None = None,
    metadata: SliceMetadata | None = None,
    resolution_state: DicomResolutionState | None = None,
) -> DicomAuditResult:
    """Build a terminal result containing only bounded, sanitized case detail."""

    return DicomAuditResult(
        metadata,
        None,
        (issue,),
        (
            DicomDiagnostic(
                issue=issue,
                root_cause_category=root_cause_category,
                root_cause_version=(
                    DECODE_ROOT_CAUSE_VERSION
                    if root_cause_category in DECODE_ROOT_CAUSE_TAXONOMY
                    else DICOM_ISSUE_DISPOSITION_VERSION
                ),
                resolution_state=resolution_state
                or (
                    DicomResolutionState.UNRESOLVED_BLOCKER
                    if root_cause_category in _UNRESOLVED_ROOT_CAUSES
                    else DicomResolutionState.EXCLUDED_UNUSABLE_SOURCE
                ),
                resolution_version=DICOM_ISSUE_RESOLUTION_VERSION,
                stage=stage,
                exception_type=_safe_exception_type(error),
            ),
        ),
    )


@dataclass(frozen=True, slots=True)
class SeriesAuditResult:
    """Deterministic order and sanitized integrity findings for one private series."""

    ordered_indices: tuple[int, ...]
    ordering_basis: OrderingBasis
    projected_positions_mm: tuple[float, ...]
    median_spacing_mm: float | None
    issues: tuple[DicomIssue, ...]

    @property
    def passed(self) -> bool:
        """Whether geometry and all cross-slice invariants passed without fallback."""

        return not self.issues and self.ordering_basis is OrderingBasis.GEOMETRY


def raw_sha256(path: Path) -> str:
    """Hash exact file bytes without retaining the path or file contents."""

    digest = sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        raise DicomAuditError(DicomIssue.UNREADABLE) from None
    return digest.hexdigest()


def extract_metadata(dataset: Dataset) -> SliceMetadata:
    """Extract only integrity-relevant fields from a DICOM dataset."""

    rows = _required_int(dataset, "Rows")
    columns = _required_int(dataset, "Columns")
    samples_per_pixel = _required_int(dataset, "SamplesPerPixel")
    photometric = _required_str(dataset, "PhotometricInterpretation")
    pixel_representation = _required_int(dataset, "PixelRepresentation")
    bits_allocated = _required_int(dataset, "BitsAllocated")
    bits_stored = _required_int(dataset, "BitsStored")
    high_bit = _required_int(dataset, "HighBit")
    number_of_frames = _optional_int(
        dataset,
        "NumberOfFrames",
        default=1,
        invalid_issue=DicomIssue.MISSING_REQUIRED_METADATA,
    )
    if number_of_frames is None:
        raise DicomAuditError(DicomIssue.MISSING_REQUIRED_METADATA)

    if rows < 1 or columns < 1 or number_of_frames < 1:
        raise DicomAuditError(DicomIssue.MISSING_REQUIRED_METADATA)
    if samples_per_pixel != 1 or photometric not in {"MONOCHROME1", "MONOCHROME2"}:
        raise DicomAuditError(DicomIssue.UNSUPPORTED_PIXEL_LAYOUT)
    if (
        pixel_representation not in {0, 1}
        or bits_allocated not in {8, 16, 32, 64}
        or bits_stored < 1
        or bits_stored > bits_allocated
        or high_bit != bits_stored - 1
    ):
        raise DicomAuditError(DicomIssue.INVALID_PIXEL_ENCODING)
    if "PixelData" not in dataset:
        raise DicomAuditError(DicomIssue.MISSING_PIXEL_DATA)

    orientation = _optional_vector(dataset, "ImageOrientationPatient", 6)
    position = _optional_vector(dataset, "ImagePositionPatient", 3)
    try:
        instance_number = _optional_int(dataset, "InstanceNumber")
    except DicomAuditError as error:
        if (
            error.issue is not DicomIssue.INVALID_INSTANCE_NUMBER
            or orientation is None
            or position is None
        ):
            raise
        # Geometry is authoritative; malformed fallback metadata must not discard
        # an otherwise valid, geometry-orderable slice.
        instance_number = None
    pixel_spacing_values = _optional_vector(dataset, "PixelSpacing", 2)
    pixel_spacing = (
        cast(tuple[float, float], pixel_spacing_values)
        if pixel_spacing_values is not None
        else None
    )
    if pixel_spacing is not None and (pixel_spacing[0] <= 0 or pixel_spacing[1] <= 0):
        raise DicomAuditError(DicomIssue.INVALID_PIXEL_SPACING)

    rescale_slope = _optional_float(
        dataset, "RescaleSlope", default=1.0, invalid_issue=DicomIssue.INVALID_RESCALE
    )
    rescale_intercept = _optional_float(
        dataset, "RescaleIntercept", default=0.0, invalid_issue=DicomIssue.INVALID_RESCALE
    )
    if rescale_slope is None or rescale_intercept is None:
        raise DicomAuditError(DicomIssue.INVALID_RESCALE)
    if not isfinite(rescale_slope) or not isfinite(rescale_intercept):
        raise DicomAuditError(DicomIssue.INVALID_RESCALE)

    return SliceMetadata(
        rows=rows,
        columns=columns,
        samples_per_pixel=samples_per_pixel,
        photometric_interpretation=photometric,
        pixel_representation=pixel_representation,
        bits_allocated=bits_allocated,
        bits_stored=bits_stored,
        high_bit=high_bit,
        number_of_frames=number_of_frames,
        image_orientation=cast(tuple[float, float, float, float, float, float] | None, orientation),
        image_position=cast(tuple[float, float, float] | None, position),
        instance_number=instance_number,
        pixel_spacing=pixel_spacing,
        slice_thickness=_optional_float(dataset, "SliceThickness"),
        spacing_between_slices=_optional_float(dataset, "SpacingBetweenSlices"),
        rescale_slope=rescale_slope,
        rescale_intercept=rescale_intercept,
    )


def audit_dicom(path: Path, *, include_perceptual_hash: bool = True) -> DicomAuditResult:
    """Strictly read and fingerprint one DICOM without returning identifiers or pixels."""

    try:
        payload = path.read_bytes()
    except OSError as error:
        return classified_dicom_failure(
            DicomIssue.UNREADABLE,
            root_cause_category="file_read_io_error",
            stage="file_read",
            error=error,
        )
    raw_digest = sha256(payload).hexdigest()

    try:
        dataset = pydicom.dcmread(BytesIO(payload), force=False)
    except MemoryError:
        raise
    except InvalidDicomError as error:
        return classified_dicom_failure(
            DicomIssue.UNREADABLE,
            root_cause_category="invalid_dicom_container",
            stage="container_parse",
            error=error,
        )
    except OSError as error:
        return classified_dicom_failure(
            DicomIssue.UNREADABLE,
            root_cause_category="dicom_parse_io_error",
            stage="container_parse",
            error=error,
        )
    except ValueError as error:
        return classified_dicom_failure(
            DicomIssue.UNREADABLE,
            root_cause_category=DecodeRootCause.UNEXPECTED_UNEXPLAINED.value,
            stage="container_parse",
            error=error,
        )
    except Exception as error:
        return classified_dicom_failure(
            DicomIssue.UNREADABLE,
            root_cause_category=DecodeRootCause.UNEXPECTED_UNEXPLAINED.value,
            stage="container_parse",
            error=error,
        )

    return audit_dataset(
        dataset,
        raw_digest=raw_digest,
        include_perceptual_hash=include_perceptual_hash,
    )


def classify_decode_root_cause(
    dataset: Dataset,
    metadata: SliceMetadata,
    error: BaseException | None = None,
) -> DecodeRootCause | None:
    """Classify a decode failure without retaining exception text or pixels."""

    if metadata.number_of_frames != 1:
        return DecodeRootCause.FRAME_METADATA_INCONSISTENCY
    transfer_syntax_value = getattr(getattr(dataset, "file_meta", None), "TransferSyntaxUID", None)
    if transfer_syntax_value is None:
        return DecodeRootCause.UNSUPPORTED_TRANSFER_SYNTAX
    transfer_syntax = UID(str(transfer_syntax_value))
    if not transfer_syntax.is_valid or not transfer_syntax.is_transfer_syntax:
        return DecodeRootCause.UNSUPPORTED_TRANSFER_SYNTAX
    try:
        decoder = get_decoder(transfer_syntax)
    except (NotImplementedError, ValueError):
        return DecodeRootCause.UNSUPPORTED_TRANSFER_SYNTAX
    except Exception:
        return DecodeRootCause.UNEXPECTED_UNEXPLAINED
    if not decoder.is_available:
        return DecodeRootCause.DECODER_UNAVAILABLE

    if not transfer_syntax.is_compressed:
        expected_bytes = (
            metadata.rows
            * metadata.columns
            * metadata.samples_per_pixel
            * metadata.number_of_frames
            * metadata.bits_allocated
            // 8
        )
        actual_bytes = len(cast(bytes, dataset.PixelData))
        padded_bytes = expected_bytes + (expected_bytes % 2)
        if actual_bytes not in {expected_bytes, padded_bytes}:
            return DecodeRootCause.UNCOMPRESSED_PIXEL_DATA_INCONSISTENCY
    else:
        try:
            frame_lengths = tuple(
                len(frame)
                for frame in generate_frames(
                    cast(bytes, dataset.PixelData),
                    number_of_frames=metadata.number_of_frames,
                )
            )
        except (EOFError, ValueError):
            return DecodeRootCause.COMPRESSED_SOURCE_DECODE_INCONSISTENCY
        except Exception:
            return DecodeRootCause.UNEXPECTED_UNEXPLAINED
        if len(frame_lengths) != metadata.number_of_frames or any(
            length == 0 for length in frame_lengths
        ):
            return DecodeRootCause.COMPRESSED_SOURCE_DECODE_INCONSISTENCY

    if error is None:
        return None
    if isinstance(error, (ImportError, ModuleNotFoundError, NotImplementedError)):
        return DecodeRootCause.DECODER_UNAVAILABLE
    # Once byte-length/encapsulation preflight has passed, an arbitrary decoder
    # or parser exception is not deterministic evidence of source corruption.
    # Keep it unresolved until a narrow structural proof or software fix exists.
    return DecodeRootCause.UNEXPECTED_UNEXPLAINED


def audit_dataset(
    dataset: Dataset,
    *,
    raw_digest: str,
    include_perceptual_hash: bool = True,
) -> DicomAuditResult:
    """Audit one already-read private DICOM dataset without retaining pixels or identifiers."""

    if len(raw_digest) != 64 or any(character not in hexdigits for character in raw_digest):
        raise ValueError("invalid_raw_digest")

    try:
        metadata = extract_metadata(dataset)
    except DicomAuditError as error:
        return classified_dicom_failure(
            error.issue,
            root_cause_category=error.issue.value,
            stage="metadata_validation",
            error=error,
        )

    if metadata.number_of_frames != 1:
        return classified_dicom_failure(
            DicomIssue.MULTI_FRAME,
            root_cause_category=DicomIssue.MULTI_FRAME.value,
            stage="decode_preflight",
            metadata=metadata,
            resolution_state=DicomResolutionState.UNRESOLVED_BLOCKER,
        )

    preflight_root_cause = classify_decode_root_cause(dataset, metadata)
    if preflight_root_cause is not None:
        return classified_dicom_failure(
            DicomIssue.DECODE_FAILURE,
            root_cause_category=preflight_root_cause.value,
            stage="decode_preflight",
            metadata=metadata,
        )

    try:
        pixels = cast(NumericArray, np.asarray(dataset.pixel_array))
    except MemoryError:
        raise
    except Exception as error:
        root_cause = classify_decode_root_cause(dataset, metadata, error)
        if root_cause is None:
            root_cause = DecodeRootCause.UNEXPECTED_UNEXPLAINED
        return classified_dicom_failure(
            DicomIssue.DECODE_FAILURE,
            root_cause_category=root_cause.value,
            stage="pixel_decode",
            error=error,
            metadata=metadata,
        )
    if pixels.ndim != 2 or pixels.shape != (metadata.rows, metadata.columns):
        return classified_dicom_failure(
            DicomIssue.DECODED_DIMENSION_MISMATCH,
            root_cause_category=DecodeRootCause.FRAME_METADATA_INCONSISTENCY.value,
            stage="decoded_shape_validation",
            metadata=metadata,
        )

    try:
        fingerprints = PixelFingerprints(
            raw_sha256=raw_digest,
            decoded_sha256=canonical_decoded_pixel_sha256(pixels),
            perceptual_hash=(
                perceptual_hash(
                    pixels,
                    rescale_slope=metadata.rescale_slope,
                    rescale_intercept=metadata.rescale_intercept,
                )
                if include_perceptual_hash
                else None
            ),
        )
    except DicomAuditError as error:
        return classified_dicom_failure(
            error.issue,
            root_cause_category=error.issue.value,
            stage="fingerprint_validation",
            error=error,
            metadata=metadata,
        )
    except MemoryError:
        raise
    except Exception as error:
        return classified_dicom_failure(
            DicomIssue.DECODE_FAILURE,
            root_cause_category=DecodeRootCause.UNEXPECTED_UNEXPLAINED.value,
            stage="fingerprint_validation",
            error=error,
            metadata=metadata,
        )
    return DicomAuditResult(metadata, fingerprints, ())


def audit_series(slices: Sequence[SliceMetadata]) -> SeriesAuditResult:
    """Order slices by geometry and quarantine inconsistent or fallback-only series."""

    if not slices:
        return SeriesAuditResult(
            (), OrderingBasis.UNAVAILABLE, (), None, (DicomIssue.EMPTY_SERIES,)
        )

    issues: list[DicomIssue] = []
    _check_cross_slice_metadata(slices, issues)
    geometry_available = all(
        item.image_orientation is not None and item.image_position is not None for item in slices
    )
    if not geometry_available:
        _append_issue(issues, DicomIssue.MISSING_GEOMETRY)
        instances = [item.instance_number for item in slices]
        if any(value is None for value in instances) or len(set(instances)) != len(instances):
            _append_issue(issues, DicomIssue.AMBIGUOUS_INSTANCE_ORDER)
            return SeriesAuditResult((), OrderingBasis.UNAVAILABLE, (), None, tuple(issues))
        ordered = tuple(sorted(range(len(slices)), key=lambda index: cast(int, instances[index])))
        _append_issue(issues, DicomIssue.INSTANCE_FALLBACK)
        return SeriesAuditResult(
            ordered,
            OrderingBasis.INSTANCE_NUMBER,
            (),
            None,
            tuple(issues),
        )

    orientations = [
        cast(tuple[float, float, float, float, float, float], item.image_orientation)
        for item in slices
    ]
    vectors = [_orientation_vectors(value) for value in orientations]
    if any(value is None for value in vectors):
        _append_issue(issues, DicomIssue.INVALID_ORIENTATION)
        return SeriesAuditResult((), OrderingBasis.UNAVAILABLE, (), None, tuple(issues))

    valid_vectors = cast(list[tuple[FloatImage, FloatImage, FloatImage]], vectors)
    reference_row, reference_column, reference_normal = valid_vectors[0]
    for row, column, normal in valid_vectors[1:]:
        angle = max(
            _angle_degrees(reference_row, row),
            _angle_degrees(reference_column, column),
            _angle_degrees(reference_normal, normal),
        )
        if angle > ORIENTATION_TOLERANCE_DEGREES:
            _append_issue(issues, DicomIssue.ORIENTATION_DRIFT)

    positions = [
        np.asarray(cast(tuple[float, float, float], item.image_position), dtype=np.float64)
        for item in slices
    ]
    if any(
        position.shape != (3,) or not bool(np.all(np.isfinite(position))) for position in positions
    ):
        _append_issue(issues, DicomIssue.INVALID_POSITION)
        return SeriesAuditResult((), OrderingBasis.UNAVAILABLE, (), None, tuple(issues))

    projections = [float(np.dot(position, reference_normal)) for position in positions]
    ordered = tuple(sorted(range(len(slices)), key=lambda index: (projections[index], index)))
    ordered_projections = tuple(projections[index] for index in ordered)
    median_spacing = _check_slice_spacing(ordered_projections, issues)
    return SeriesAuditResult(
        ordered,
        OrderingBasis.GEOMETRY,
        ordered_projections,
        median_spacing,
        tuple(issues),
    )


def canonical_decoded_pixel_sha256(pixels: NumericArray) -> str:
    """Hash decoded numeric values in a stable shape-aware little-endian representation."""

    array = np.asarray(pixels)
    if array.ndim != 2 or not bool(np.all(np.isfinite(array))):
        raise DicomAuditError(DicomIssue.INVALID_IMAGE)
    if np.issubdtype(array.dtype, np.integer) or np.issubdtype(array.dtype, np.bool_):
        canonical = np.ascontiguousarray(array.astype("<i8", copy=False))
        kind = b"integer"
    elif np.issubdtype(array.dtype, np.floating):
        canonical = np.ascontiguousarray(array.astype("<f8", copy=False))
        kind = b"float"
    else:
        raise DicomAuditError(DicomIssue.INVALID_IMAGE)
    header = (
        b"rsna-knee-decoded-v1\0"
        + kind
        + b"\0"
        + int(array.shape[0]).to_bytes(8, "little")
        + int(array.shape[1]).to_bytes(8, "little")
    )
    digest = sha256(header)
    digest.update(canonical.data)
    return digest.hexdigest()


def perceptual_hash(
    pixels: NumericArray,
    *,
    rescale_slope: float = 1.0,
    rescale_intercept: float = 0.0,
) -> str:
    """Return a deterministic 64-bit pHash using an 8x8 block with the DC bit cleared."""

    image = _as_float_image(pixels)
    if not isfinite(rescale_slope) or not isfinite(rescale_intercept):
        raise DicomAuditError(DicomIssue.INVALID_RESCALE)
    rescaled = image * rescale_slope + rescale_intercept
    minimum = float(np.min(rescaled))
    maximum = float(np.max(rescaled))
    if maximum > minimum:
        normalized = np.round((rescaled - minimum) / (maximum - minimum), decimals=12)
    else:
        normalized = np.zeros_like(rescaled)
    resized = _resize_bilinear(normalized, PHASH_RESIZE, PHASH_RESIZE)
    dct = _dct_matrix(PHASH_RESIZE)
    coefficients = dct @ resized @ dct.T
    low_frequency = coefficients[:PHASH_LOW_FREQUENCY_SIZE, :PHASH_LOW_FREQUENCY_SIZE].reshape(-1)
    ac_values = low_frequency[1:]
    coefficient_scale = float(np.max(np.abs(ac_values), initial=0.0))
    stability_epsilon = max(np.finfo(np.float64).eps, coefficient_scale * 1e-4)
    stable_ac = np.where(np.abs(ac_values) <= stability_epsilon, 0.0, ac_values)
    threshold = float(np.median(stable_ac))
    bits = np.zeros(PHASH_LOW_FREQUENCY_SIZE**2, dtype=np.uint8)
    bits[1:] = (stable_ac > threshold + stability_epsilon).astype(np.uint8)
    return np.packbits(bits, bitorder="big").tobytes().hex()


def phash_hamming(left: str, right: str) -> int:
    """Return Hamming distance for two validated 64-bit hexadecimal pHashes."""

    allowed = set(hexdigits)
    if (
        len(left) != 16
        or len(right) != 16
        or any(character not in allowed for character in left)
        or any(character not in allowed for character in right)
    ):
        raise ValueError("invalid_perceptual_hash")
    return (int(left, 16) ^ int(right, 16)).bit_count()


def normalized_cross_correlation(left: NumericArray, right: NumericArray) -> float:
    """Compute finite zero-mean normalized cross correlation without exposing pixels."""

    left_image = _as_float_image(left)
    right_image = _as_float_image(right)
    if left_image.shape != right_image.shape:
        raise ValueError("incompatible_images")
    left_centered = left_image - float(np.mean(left_image))
    right_centered = right_image - float(np.mean(right_image))
    denominator = float(
        np.sqrt(np.sum(left_centered * left_centered) * np.sum(right_centered * right_centered))
    )
    if denominator == 0.0:
        return 1.0 if bool(np.array_equal(left_image, right_image)) else 0.0
    return float(np.clip(np.sum(left_centered * right_centered) / denominator, -1.0, 1.0))


def gradient_magnitude(image: NumericArray) -> FloatImage:
    """Return deterministic first-order gradient magnitude for a two-dimensional image."""

    values = _as_float_image(image)
    gradient_y = np.gradient(values, axis=0) if values.shape[0] > 1 else np.zeros_like(values)
    gradient_x = np.gradient(values, axis=1) if values.shape[1] > 1 else np.zeros_like(values)
    return cast(FloatImage, np.hypot(gradient_x, gradient_y))


def gradient_normalized_cross_correlation(left: NumericArray, right: NumericArray) -> float:
    """Compute NCC between deterministic gradient-magnitude images."""

    return normalized_cross_correlation(gradient_magnitude(left), gradient_magnitude(right))


def _required_int(dataset: Dataset, attribute: str) -> int:
    try:
        return int(getattr(dataset, attribute))
    except (AttributeError, TypeError, ValueError):
        raise DicomAuditError(DicomIssue.MISSING_REQUIRED_METADATA) from None


def _required_str(dataset: Dataset, attribute: str) -> str:
    try:
        value = str(getattr(dataset, attribute))
    except AttributeError:
        raise DicomAuditError(DicomIssue.MISSING_REQUIRED_METADATA) from None
    if not value:
        raise DicomAuditError(DicomIssue.MISSING_REQUIRED_METADATA)
    return value


def _optional_int(
    dataset: Dataset,
    attribute: str,
    *,
    default: int | None = None,
    invalid_issue: DicomIssue = DicomIssue.INVALID_INSTANCE_NUMBER,
) -> int | None:
    value = getattr(dataset, attribute, None)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise DicomAuditError(invalid_issue) from None


def _optional_float(
    dataset: Dataset,
    attribute: str,
    *,
    default: float | None = None,
    invalid_issue: DicomIssue = DicomIssue.MISSING_REQUIRED_METADATA,
) -> float | None:
    value = getattr(dataset, attribute, None)
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise DicomAuditError(invalid_issue) from None
    if not isfinite(parsed):
        raise DicomAuditError(invalid_issue)
    return parsed


def _optional_vector(dataset: Dataset, attribute: str, length: int) -> tuple[float, ...] | None:
    value = getattr(dataset, attribute, None)
    if value is None:
        return None
    try:
        parsed = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        raise DicomAuditError(_vector_issue(attribute)) from None
    if len(parsed) != length or not all(isfinite(item) for item in parsed):
        raise DicomAuditError(_vector_issue(attribute))
    return parsed


def _vector_issue(attribute: str) -> DicomIssue:
    if attribute == "ImageOrientationPatient":
        return DicomIssue.INVALID_ORIENTATION
    if attribute == "PixelSpacing":
        return DicomIssue.INVALID_PIXEL_SPACING
    return DicomIssue.INVALID_POSITION


def _check_cross_slice_metadata(slices: Sequence[SliceMetadata], issues: list[DicomIssue]) -> None:
    if len({(item.rows, item.columns) for item in slices}) != 1:
        _append_issue(issues, DicomIssue.DIMENSION_MISMATCH)
    if len({item.pixel_signature for item in slices}) != 1:
        _append_issue(issues, DicomIssue.PIXEL_ENCODING_MISMATCH)
    spacings = [item.pixel_spacing for item in slices]
    if any(spacing is None for spacing in spacings):
        _append_issue(issues, DicomIssue.MISSING_PIXEL_SPACING)
        return
    reference = cast(tuple[float, float], spacings[0])
    for spacing in spacings[1:]:
        current = cast(tuple[float, float], spacing)
        for expected, observed in zip(reference, current, strict=True):
            tolerance = max(
                SPACING_ABSOLUTE_TOLERANCE_MM,
                SPACING_RELATIVE_TOLERANCE * abs(expected),
            )
            if abs(expected - observed) > tolerance:
                _append_issue(issues, DicomIssue.IN_PLANE_SPACING_DRIFT)


def _orientation_vectors(
    orientation: tuple[float, float, float, float, float, float],
) -> tuple[FloatImage, FloatImage, FloatImage] | None:
    values = np.asarray(orientation, dtype=np.float64)
    row = values[:3]
    column = values[3:]
    row_norm = float(np.linalg.norm(row))
    column_norm = float(np.linalg.norm(column))
    dot = float(np.dot(row, column))
    if (
        abs(row_norm - 1.0) > IOP_ORTHONORMAL_TOLERANCE
        or abs(column_norm - 1.0) > IOP_ORTHONORMAL_TOLERANCE
        or abs(dot) > IOP_ORTHONORMAL_TOLERANCE
    ):
        return None
    normal = cast(FloatImage, np.cross(row, column))
    normal_norm = float(np.linalg.norm(normal))
    if abs(normal_norm - 1.0) > IOP_ORTHONORMAL_TOLERANCE:
        return None
    return row / row_norm, column / column_norm, normal / normal_norm


def _angle_degrees(left: FloatImage, right: FloatImage) -> float:
    cosine = float(np.clip(np.dot(left, right), -1.0, 1.0))
    return degrees(acos(cosine))


def _check_slice_spacing(
    ordered_projections: tuple[float, ...], issues: list[DicomIssue]
) -> float | None:
    if len(ordered_projections) < 2:
        return None
    differences = np.diff(np.asarray(ordered_projections, dtype=np.float64))
    if bool(np.any(differences <= DUPLICATE_POSITION_TOLERANCE_MM)):
        _append_issue(issues, DicomIssue.DUPLICATE_POSITION)
    positive = differences[differences > DUPLICATE_POSITION_TOLERANCE_MM]
    if positive.size == 0:
        return None
    median = float(np.median(positive))
    tolerance = max(
        SPACING_ABSOLUTE_TOLERANCE_MM,
        SPACING_RELATIVE_TOLERANCE * median,
    )
    if bool(np.any(np.abs(positive - median) > tolerance)):
        _append_issue(issues, DicomIssue.SPACING_DRIFT)
    if bool(np.any(positive > GAP_MULTIPLIER * median)):
        _append_issue(issues, DicomIssue.LARGE_GAP)
    return median


def _append_issue(issues: list[DicomIssue], issue: DicomIssue) -> None:
    if issue not in issues:
        issues.append(issue)


def _as_float_image(image: NumericArray) -> FloatImage:
    array = np.asarray(image)
    if array.ndim != 2:
        raise DicomAuditError(DicomIssue.INVALID_IMAGE)
    values = cast(FloatImage, np.asarray(array, dtype=np.float64))
    if not bool(np.all(np.isfinite(values))):
        raise DicomAuditError(DicomIssue.INVALID_IMAGE)
    return values


def _resize_bilinear(image: FloatImage, height: int, width: int) -> FloatImage:
    source_height, source_width = image.shape
    target_y = np.linspace(0.0, float(source_height - 1), height)
    target_x = np.linspace(0.0, float(source_width - 1), width)
    lower_y = np.floor(target_y).astype(np.intp)
    lower_x = np.floor(target_x).astype(np.intp)
    upper_y = np.minimum(lower_y + 1, source_height - 1)
    upper_x = np.minimum(lower_x + 1, source_width - 1)
    weight_y = (target_y - lower_y)[:, None]
    weight_x = (target_x - lower_x)[None, :]
    top = (
        image[lower_y[:, None], lower_x[None, :]] * (1.0 - weight_x)
        + image[lower_y[:, None], upper_x[None, :]] * weight_x
    )
    bottom = (
        image[upper_y[:, None], lower_x[None, :]] * (1.0 - weight_x)
        + image[upper_y[:, None], upper_x[None, :]] * weight_x
    )
    return cast(FloatImage, top * (1.0 - weight_y) + bottom * weight_y)


@lru_cache(maxsize=4)
def _dct_matrix(size: int) -> FloatImage:
    rows = np.arange(size, dtype=np.float64)[:, None]
    columns = np.arange(size, dtype=np.float64)[None, :]
    matrix = np.cos(np.pi * (2.0 * columns + 1.0) * rows / (2.0 * size))
    matrix[0] *= np.sqrt(1.0 / size)
    matrix[1:] *= np.sqrt(2.0 / size)
    return cast(FloatImage, matrix)
