"""Deterministic, private-only visual QA for already ordered MRI volumes.

The renderer deliberately accepts no identifiers, free text, source paths, or DICOM datasets.
Callers supply numeric volumes in verified physical slice order plus a small enum-only metadata
record. All returned filenames use local ordinals and all case-level artifacts must remain inside
the caller's authorized private directory.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from pathlib import Path
from typing import Final, cast

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

NumericVolume = NDArray[np.generic]
FloatVolume = NDArray[np.float64]
ByteImage = NDArray[np.uint8]

RENDERER_VERSION: Final = "private-qa-renderer-v1"
METADATA_SCHEMA_VERSION: Final = 1
REVIEW_LEDGER_SCHEMA_VERSION: Final = 1
CONTACT_GRID_SIZE: Final = 5
CONTACT_MAX_SLICES: Final = CONTACT_GRID_SIZE**2
ANIMATION_MAX_FRAMES: Final = 64
ANIMATION_FRAME_DURATION_MS: Final = 100
HISTOGRAM_BINS: Final = 256
TILE_PIXELS: Final = 256
TILE_GAP_PIXELS: Final = 4
HEADER_PIXELS: Final = 20
CAPTION_PIXELS: Final = 16
MIN_ORTHOGONAL_SLICES: Final = 8
MAX_THROUGH_PLANE_SPACING_RATIO: Final = 4.0
PNG_COMPRESS_LEVEL: Final = 9
MAX_CASE_ORDINAL: Final = 999_999
MAX_SERIES_ORDINAL: Final = 999


class QaPlane(StrEnum):
    """Fixed, non-identifying acquisition-plane vocabulary."""

    AXIAL = "axial"
    CORONAL = "coronal"
    SAGITTAL = "sagittal"
    OBLIQUE = "oblique"
    UNKNOWN = "unknown"


class QaSequence(StrEnum):
    """Fixed sequence-class vocabulary; never a free-text series description."""

    FLUID_SENSITIVE = "fluid_sensitive"
    NON_FLUID_SENSITIVE = "non_fluid_sensitive"
    UNKNOWN = "unknown"


class QaPresence(StrEnum):
    """Fixed presence vocabulary for safe categorical metadata."""

    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class QaPhotometric(StrEnum):
    """Supported monochrome pixel interpretations."""

    MONOCHROME1 = "monochrome1"
    MONOCHROME2 = "monochrome2"


class QaLaterality(StrEnum):
    """Fixed laterality vocabulary displayed without transforming pixels."""

    LEFT = "left"
    RIGHT = "right"
    BILATERAL = "bilateral"
    UNKNOWN = "unknown"


class QaDirection(StrEnum):
    """Fixed patient-direction labels for increasing displayed axes in LPS space."""

    LEFT = "left"
    RIGHT = "right"
    ANTERIOR = "anterior"
    POSTERIOR = "posterior"
    HEAD = "head"
    FEET = "feet"
    OBLIQUE = "oblique"
    UNKNOWN = "unknown"


class QaOrdering(StrEnum):
    """Ordering evidence required by this renderer."""

    PHYSICAL_GEOMETRY = "physical_geometry"


class QaResultCode(StrEnum):
    """Safe top-level completion vocabulary."""

    COMPLETE = "complete"


class QaErrorCode(StrEnum):
    """Sanitized fail-closed errors that contain no input values."""

    INVALID_VOLUME = "invalid_volume"
    UNSAFE_METADATA = "unsafe_metadata"
    PHYSICAL_ORDER_REQUIRED = "physical_order_required"
    INVALID_CONTACT_SELECTION = "invalid_contact_selection"
    OUTPUT_DIRECTORY_INVALID = "output_directory_invalid"
    ARTIFACT_EXISTS = "artifact_exists"
    ARTIFACT_WRITE_FAILED = "artifact_write_failed"


class OrthogonalStatus(StrEnum):
    """Fixed reason why physical-aspect orthogonal views were or were not rendered."""

    RENDERED = "rendered"
    INVALID_GEOMETRY = "suppressed_invalid_geometry"
    INCONSISTENT_GEOMETRY = "suppressed_inconsistent_geometry"
    THICK_SLICES = "suppressed_thick_slices"
    INSUFFICIENT_SLICES = "suppressed_insufficient_slices"


class QaArtifactKind(StrEnum):
    """Fixed private artifact vocabulary."""

    CONTACT_SHEET = "contact_sheet"
    ORTHOGONAL_VIEWS = "orthogonal_views"
    INTENSITY_HISTOGRAM = "intensity_histogram"
    SLICE_ANIMATION = "slice_animation"
    BEFORE_AFTER_COMPARISON = "before_after_comparison"
    REVIEW_LEDGER = "review_ledger"
    METADATA_SUMMARY = "metadata_summary"


class ReviewStatus(StrEnum):
    """Fixed review-row lifecycle."""

    PENDING_PRIVATE_REVIEW = "pending_private_review"
    COMPLETE = "complete"
    BLOCKED = "blocked"


class ReviewDecision(StrEnum):
    """Allowed values for each human-review check."""

    NOT_REVIEWED = "not_reviewed"
    PASS = "pass"
    BLOCK = "block"
    NOT_APPLICABLE = "not_applicable"


class ReviewCheck(StrEnum):
    """Fixed review dimensions; no notes or free-text fields are allowed."""

    SLICE_ORDER = "slice_order"
    ANATOMICAL_ORIENTATION = "anatomical_orientation"
    LATERALITY_PRESERVATION = "laterality_preservation"
    NO_UNINTENDED_MIRRORING = "no_unintended_mirroring"
    INTENSITY_POLARITY = "intensity_polarity"
    ANATOMY_NOT_CLIPPED = "anatomy_not_clipped"
    SEQUENCE_SLOT_ASSIGNMENT = "sequence_slot_assignment"
    PREPROCESSING_APPEARANCE = "preprocessing_appearance"
    DUPLICATE_MISSING_ABNORMAL_HANDLING = "duplicate_missing_abnormal_handling"


class QaRenderError(Exception):
    """A renderer failure whose message is always one fixed safe code."""

    def __init__(self, code: QaErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class QaGeometry:
    """Non-identifying geometry needed to gate and scale QA views."""

    row_spacing_mm: float | None
    column_spacing_mm: float | None
    slice_spacing_mm: float | None
    orientation_consistent: bool
    spacing_consistent: bool
    positions_monotonic: bool
    processed_row_spacing_mm: float | None = None
    processed_column_spacing_mm: float | None = None
    display_right_direction: QaDirection = QaDirection.UNKNOWN
    display_down_direction: QaDirection = QaDirection.UNKNOWN
    slice_advance_direction: QaDirection = QaDirection.UNKNOWN
    relative_slice_positions_mm: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class QaSafeMetadata:
    """Enum-only and numeric metadata accepted by the private renderer."""

    case_ordinal: int
    series_ordinal: int
    plane: QaPlane
    sequence: QaSequence
    fat_suppression: QaPresence
    photometric: QaPhotometric
    laterality: QaLaterality
    ordering: QaOrdering
    geometry: QaGeometry


@dataclass(frozen=True, slots=True)
class PrivateArtifact:
    """Checksum record suitable for a private artifact inventory."""

    kind: QaArtifactKind
    basename: str
    bytes: int
    sha256: str

    def as_payload(self) -> dict[str, object]:
        """Return a canonical JSON-compatible private inventory record."""

        return {
            "basename": self.basename,
            "bytes": self.bytes,
            "kind": self.kind.value,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class ReviewLedgerRow:
    """One identifier-free row to be completed inside the private environment."""

    case_ordinal: int
    series_ordinal: int
    status: ReviewStatus
    decisions: tuple[tuple[ReviewCheck, ReviewDecision], ...]

    def as_payload(self) -> dict[str, object]:
        """Return the fixed review schema and row without a notes field."""

        return {
            "row": {
                "case_ordinal": self.case_ordinal,
                "checks": {check.value: decision.value for check, decision in self.decisions},
                "series_ordinal": self.series_ordinal,
                "status": self.status.value,
            },
            "schema": review_ledger_schema(),
        }


@dataclass(frozen=True, slots=True)
class QaRenderResult:
    """Safe completion result; it never includes an input or output path."""

    code: QaResultCode
    orthogonal_status: OrthogonalStatus
    artifacts: tuple[PrivateArtifact, ...]
    review_row: ReviewLedgerRow


def review_ledger_schema() -> dict[str, object]:
    """Return the canonical enum-only private review-ledger schema."""

    return {
        "check_enum": [item.value for item in ReviewCheck],
        "decision_enum": [item.value for item in ReviewDecision],
        "fields": ["case_ordinal", "series_ordinal", "status", "checks"],
        "schema_version": REVIEW_LEDGER_SCHEMA_VERSION,
        "status_enum": [item.value for item in ReviewStatus],
    }


def physical_slice_indices(slice_count: int, maximum: int) -> tuple[int, ...]:
    """Select ordered, endpoint-preserving indices without floating-point rounding."""

    if (
        isinstance(slice_count, bool)
        or isinstance(maximum, bool)
        or not isinstance(slice_count, int)
        or not isinstance(maximum, int)
        or slice_count < 1
        or maximum < 1
    ):
        raise QaRenderError(QaErrorCode.INVALID_VOLUME)
    selected = min(slice_count, maximum)
    if selected == slice_count:
        return tuple(range(slice_count))
    if selected == 1:
        return (slice_count // 2,)
    denominator = selected - 1
    return tuple(
        (index * (slice_count - 1) + denominator // 2) // denominator for index in range(selected)
    )


def qa_direction_from_lps(vector: Sequence[float]) -> QaDirection:
    """Map a unit LPS direction to a fixed display label without guessing obliques."""

    try:
        values = tuple(float(value) for value in vector)
    except (TypeError, ValueError, OverflowError):
        raise QaRenderError(QaErrorCode.UNSAFE_METADATA) from None
    if len(values) != 3 or not all(math.isfinite(value) for value in values):
        raise QaRenderError(QaErrorCode.UNSAFE_METADATA)
    norm = math.sqrt(sum(value * value for value in values))
    if not 0.999 <= norm <= 1.001:
        raise QaRenderError(QaErrorCode.UNSAFE_METADATA)
    axis = max(range(3), key=lambda index: abs(values[index]))
    if abs(values[axis]) < 0.9:
        return QaDirection.OBLIQUE
    positive, negative = (
        (QaDirection.LEFT, QaDirection.RIGHT),
        (QaDirection.POSTERIOR, QaDirection.ANTERIOR),
        (QaDirection.HEAD, QaDirection.FEET),
    )[axis]
    return positive if values[axis] >= 0 else negative


def render_private_qa(
    source_volume: NumericVolume,
    preprocessed_volume: NumericVolume,
    *,
    metadata: QaSafeMetadata,
    output_dir: Path,
    contact_slice_indices: Sequence[int] | None = None,
) -> QaRenderResult:
    """Render one private case/series QA package from already ordered numeric volumes.

    The first dimension of both volumes must describe the same physical slice order. The function
    never reorders, reverses, transposes, rotates, or flips source slices. Orthogonal views are
    display-only center sections with physical aspect preserved; they never create an isotropic
    volume or imply through-plane detail.
    """

    source = _validated_volume(source_volume)
    processed = _validated_volume(preprocessed_volume)
    if source.shape[0] != processed.shape[0]:
        raise QaRenderError(QaErrorCode.INVALID_VOLUME)
    _validate_metadata(metadata)
    if not metadata.geometry.positions_monotonic:
        raise QaRenderError(QaErrorCode.PHYSICAL_ORDER_REQUIRED)
    contact_indices = _validated_contact_indices(contact_slice_indices, source.shape[0])
    animation_indices = physical_slice_indices(source.shape[0], ANIMATION_MAX_FRAMES)
    orthogonal_status = _orthogonal_status(source, metadata.geometry)
    relative_positions = _relative_positions(metadata.geometry, source.shape[0])

    prefix = f"case_{metadata.case_ordinal:06d}_series_{metadata.series_ordinal:03d}"
    source_bytes = _normalize_volume(source)
    processed_bytes = _normalize_volume(processed)
    row_spacing, column_spacing = _display_in_plane_spacing(metadata.geometry)

    payloads: list[tuple[QaArtifactKind, str, bytes]] = []
    payloads.append(
        (
            QaArtifactKind.CONTACT_SHEET,
            f"{prefix}_contact.png",
            _png_bytes(
                _annotate_geometry(
                    _contact_sheet(
                        source_bytes,
                        contact_indices,
                        relative_positions=relative_positions,
                        row_spacing=row_spacing,
                        column_spacing=column_spacing,
                    ),
                    metadata,
                )
            ),
        )
    )
    physical_aspect: tuple[Mapping[str, object], ...] = ()
    if orthogonal_status is OrthogonalStatus.RENDERED:
        orthogonal_image, physical_aspect = _orthogonal_views(
            source_bytes,
            cast(float, metadata.geometry.row_spacing_mm),
            cast(float, metadata.geometry.column_spacing_mm),
            cast(float, metadata.geometry.slice_spacing_mm),
            metadata.geometry,
        )
        payloads.append(
            (
                QaArtifactKind.ORTHOGONAL_VIEWS,
                f"{prefix}_orthogonal.png",
                _png_bytes(_annotate_geometry(orthogonal_image, metadata)),
            )
        )
    payloads.extend(
        (
            (
                QaArtifactKind.INTENSITY_HISTOGRAM,
                f"{prefix}_histogram.png",
                _png_bytes(_histogram_image(source, processed)),
            ),
            (
                QaArtifactKind.SLICE_ANIMATION,
                f"{prefix}_animation.gif",
                _gif_bytes(
                    tuple(
                        _annotate_geometry(
                            _letterbox(
                                source_bytes[index],
                                row_spacing=row_spacing,
                                column_spacing=column_spacing,
                            ),
                            metadata,
                            suffix=f"#{index:03d} +{relative_positions[index]:.3f}mm",
                        )
                        for index in animation_indices
                    )
                ),
            ),
            (
                QaArtifactKind.BEFORE_AFTER_COMPARISON,
                f"{prefix}_before_after.png",
                _png_bytes(
                    _annotate_geometry(
                        _before_after(
                            source_bytes[source.shape[0] // 2],
                            processed_bytes[processed.shape[0] // 2],
                            source_spacing=(row_spacing, column_spacing),
                            processed_spacing=_display_processed_spacing(metadata.geometry),
                        ),
                        metadata,
                    )
                ),
            ),
        )
    )

    review_row = _pending_review_row(metadata)
    review_payload = _canonical_json_bytes(review_row.as_payload())
    payloads.append((QaArtifactKind.REVIEW_LEDGER, f"{prefix}_review.json", review_payload))
    visual_records = tuple(
        _artifact_record(kind, basename, payload) for kind, basename, payload in payloads
    )
    metadata_payload = _canonical_json_bytes(
        _metadata_payload(
            metadata=metadata,
            source_shape=source.shape,
            processed_shape=processed.shape,
            contact_indices=contact_indices,
            animation_indices=animation_indices,
            relative_positions=relative_positions,
            orthogonal_status=orthogonal_status,
            physical_aspect=physical_aspect,
            artifacts=visual_records,
        )
    )
    payloads.append((QaArtifactKind.METADATA_SUMMARY, f"{prefix}_metadata.json", metadata_payload))
    all_records = tuple(
        _artifact_record(kind, basename, payload) for kind, basename, payload in payloads
    )
    _write_artifacts(output_dir, payloads)
    return QaRenderResult(
        code=QaResultCode.COMPLETE,
        orthogonal_status=orthogonal_status,
        artifacts=all_records,
        review_row=review_row,
    )


def _validated_volume(volume: NumericVolume) -> FloatVolume:
    array = np.asarray(volume)
    if (
        array.ndim != 3
        or any(dimension < 1 for dimension in array.shape)
        or not (
            np.issubdtype(array.dtype, np.integer)
            or np.issubdtype(array.dtype, np.floating)
            or np.issubdtype(array.dtype, np.bool_)
        )
    ):
        raise QaRenderError(QaErrorCode.INVALID_VOLUME)
    values = np.asarray(array, dtype=np.float64)
    if not bool(np.all(np.isfinite(values))):
        raise QaRenderError(QaErrorCode.INVALID_VOLUME)
    return values


def _validate_metadata(metadata: QaSafeMetadata) -> None:
    if not isinstance(metadata, QaSafeMetadata):
        raise QaRenderError(QaErrorCode.UNSAFE_METADATA)
    if (
        isinstance(metadata.case_ordinal, bool)
        or not isinstance(metadata.case_ordinal, int)
        or not 0 <= metadata.case_ordinal <= MAX_CASE_ORDINAL
        or isinstance(metadata.series_ordinal, bool)
        or not isinstance(metadata.series_ordinal, int)
        or not 0 <= metadata.series_ordinal <= MAX_SERIES_ORDINAL
        or not isinstance(metadata.plane, QaPlane)
        or not isinstance(metadata.sequence, QaSequence)
        or not isinstance(metadata.fat_suppression, QaPresence)
        or not isinstance(metadata.photometric, QaPhotometric)
        or not isinstance(metadata.laterality, QaLaterality)
        or metadata.ordering is not QaOrdering.PHYSICAL_GEOMETRY
        or not isinstance(metadata.geometry, QaGeometry)
    ):
        raise QaRenderError(QaErrorCode.UNSAFE_METADATA)
    geometry = metadata.geometry
    if any(
        not isinstance(value, bool)
        for value in (
            geometry.orientation_consistent,
            geometry.spacing_consistent,
            geometry.positions_monotonic,
        )
    ):
        raise QaRenderError(QaErrorCode.UNSAFE_METADATA)
    for value in (
        geometry.row_spacing_mm,
        geometry.column_spacing_mm,
        geometry.slice_spacing_mm,
        geometry.processed_row_spacing_mm,
        geometry.processed_column_spacing_mm,
    ):
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise QaRenderError(QaErrorCode.UNSAFE_METADATA)
    if not all(
        isinstance(value, QaDirection)
        for value in (
            geometry.display_right_direction,
            geometry.display_down_direction,
            geometry.slice_advance_direction,
        )
    ):
        raise QaRenderError(QaErrorCode.UNSAFE_METADATA)
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        for value in geometry.relative_slice_positions_mm
    ):
        raise QaRenderError(QaErrorCode.UNSAFE_METADATA)


def _relative_positions(geometry: QaGeometry, slice_count: int) -> tuple[float, ...]:
    positions = tuple(float(value) for value in geometry.relative_slice_positions_mm)
    if positions:
        if len(positions) != slice_count or any(
            left >= right for left, right in zip(positions, positions[1:], strict=False)
        ):
            raise QaRenderError(QaErrorCode.UNSAFE_METADATA)
        origin = positions[0]
        return tuple(value - origin for value in positions)
    spacing = geometry.slice_spacing_mm
    if spacing is None or spacing <= 0 or not geometry.spacing_consistent:
        raise QaRenderError(QaErrorCode.UNSAFE_METADATA)
    return tuple(index * float(spacing) for index in range(slice_count))


def _validated_contact_indices(provided: Sequence[int] | None, slice_count: int) -> tuple[int, ...]:
    if provided is None:
        return physical_slice_indices(slice_count, CONTACT_MAX_SLICES)
    values = tuple(provided)
    if (
        not values
        or len(values) > CONTACT_MAX_SLICES
        or any(isinstance(value, bool) or not isinstance(value, int) for value in values)
        or any(value < 0 or value >= slice_count for value in values)
        or any(left >= right for left, right in zip(values, values[1:], strict=False))
    ):
        raise QaRenderError(QaErrorCode.INVALID_CONTACT_SELECTION)
    return values


def _orthogonal_status(volume: FloatVolume, geometry: QaGeometry) -> OrthogonalStatus:
    if volume.shape[0] < MIN_ORTHOGONAL_SLICES:
        return OrthogonalStatus.INSUFFICIENT_SLICES
    spacings = (
        geometry.row_spacing_mm,
        geometry.column_spacing_mm,
        geometry.slice_spacing_mm,
    )
    if any(value is None or value <= 0 for value in spacings):
        return OrthogonalStatus.INVALID_GEOMETRY
    if not geometry.orientation_consistent or not geometry.spacing_consistent:
        return OrthogonalStatus.INCONSISTENT_GEOMETRY
    row_spacing, column_spacing, slice_spacing = cast(tuple[float, float, float], spacings)
    if slice_spacing / max(row_spacing, column_spacing) > MAX_THROUGH_PLANE_SPACING_RATIO:
        return OrthogonalStatus.THICK_SLICES
    return OrthogonalStatus.RENDERED


def _display_in_plane_spacing(geometry: QaGeometry) -> tuple[float, float]:
    row = geometry.row_spacing_mm
    column = geometry.column_spacing_mm
    if row is None or column is None or row <= 0 or column <= 0:
        return (1.0, 1.0)
    return (float(row), float(column))


def _display_processed_spacing(geometry: QaGeometry) -> tuple[float, float]:
    row = geometry.processed_row_spacing_mm
    column = geometry.processed_column_spacing_mm
    if row is None or column is None:
        return _display_in_plane_spacing(geometry)
    if row <= 0 or column <= 0:
        raise QaRenderError(QaErrorCode.UNSAFE_METADATA)
    return (float(row), float(column))


def _normalize_volume(volume: FloatVolume) -> ByteImage:
    minimum = float(np.min(volume))
    maximum = float(np.max(volume))
    if maximum <= minimum:
        return np.zeros(volume.shape, dtype=np.uint8)
    normalized = (volume - minimum) / (maximum - minimum)
    return np.asarray(np.rint(np.clip(normalized, 0.0, 1.0) * 255.0), dtype=np.uint8)


def _letterbox(
    image: ByteImage,
    *,
    row_spacing: float = 1.0,
    column_spacing: float = 1.0,
    tile_pixels: int = TILE_PIXELS,
) -> Image.Image:
    rows, columns = image.shape
    physical_height = float(rows) * row_spacing
    physical_width = float(columns) * column_spacing
    scale = min(tile_pixels / physical_height, tile_pixels / physical_width)
    height = max(1, min(tile_pixels, math.floor(physical_height * scale + 0.5)))
    width = max(1, min(tile_pixels, math.floor(physical_width * scale + 0.5)))
    source = Image.frombytes("L", (columns, rows), np.ascontiguousarray(image).tobytes())
    resized = source.resize((width, height), resample=Image.Resampling.BILINEAR)
    tile = Image.new("L", (tile_pixels, tile_pixels), color=0)
    tile.paste(resized, ((tile_pixels - width) // 2, (tile_pixels - height) // 2))
    return tile


def _contact_sheet(
    volume: ByteImage,
    indices: tuple[int, ...],
    *,
    relative_positions: tuple[float, ...],
    row_spacing: float,
    column_spacing: float,
) -> Image.Image:
    width = CONTACT_GRID_SIZE * TILE_PIXELS + (CONTACT_GRID_SIZE - 1) * TILE_GAP_PIXELS
    tile_height = TILE_PIXELS + CAPTION_PIXELS
    height = CONTACT_GRID_SIZE * tile_height + (CONTACT_GRID_SIZE - 1) * TILE_GAP_PIXELS
    sheet = Image.new("L", (width, height), color=0)
    for position, slice_index in enumerate(indices):
        row, column = divmod(position, CONTACT_GRID_SIZE)
        tile = _labeled_tile(
            _letterbox(
                volume[slice_index],
                row_spacing=row_spacing,
                column_spacing=column_spacing,
            ),
            f"#{slice_index:03d} +{relative_positions[slice_index]:.3f}mm",
        )
        sheet.paste(
            tile,
            (column * (TILE_PIXELS + TILE_GAP_PIXELS), row * (tile_height + TILE_GAP_PIXELS)),
        )
    return sheet


def _short_direction(direction: QaDirection) -> str:
    return {
        QaDirection.LEFT: "L",
        QaDirection.RIGHT: "R",
        QaDirection.ANTERIOR: "A",
        QaDirection.POSTERIOR: "P",
        QaDirection.HEAD: "H",
        QaDirection.FEET: "F",
        QaDirection.OBLIQUE: "OBL",
        QaDirection.UNKNOWN: "?",
    }[direction]


def _annotate_geometry(
    image: Image.Image, metadata: QaSafeMetadata, *, suffix: str = ""
) -> Image.Image:
    """Add a header outside anatomical pixels; never paint over the source image."""

    geometry = metadata.geometry
    laterality = {
        QaLaterality.LEFT: "L",
        QaLaterality.RIGHT: "R",
        QaLaterality.BILATERAL: "B",
        QaLaterality.UNKNOWN: "?",
    }[metadata.laterality]
    label = (
        f"LAT:{laterality} R:{_short_direction(geometry.display_right_direction)} "
        f"D:{_short_direction(geometry.display_down_direction)} "
        f"S:{_short_direction(geometry.slice_advance_direction)}"
    )
    if suffix:
        label = f"{label} {suffix}"
    annotated = Image.new(image.mode, (image.width, image.height + HEADER_PIXELS), color=0)
    annotated.paste(image, (0, HEADER_PIXELS))
    ImageDraw.Draw(annotated).text((4, 4), label, fill=255)
    return annotated


def _labeled_tile(image: Image.Image, label: str) -> Image.Image:
    tile = Image.new(image.mode, (image.width, image.height + CAPTION_PIXELS), color=0)
    tile.paste(image, (0, CAPTION_PIXELS))
    ImageDraw.Draw(tile).text((4, 2), label, fill=255)
    return tile


def _orthogonal_views(
    volume: ByteImage,
    row_spacing: float,
    column_spacing: float,
    slice_spacing: float,
    geometry: QaGeometry,
) -> tuple[Image.Image, tuple[Mapping[str, object], ...]]:
    slices, rows, columns = volume.shape
    native = volume[slices // 2]
    through_row = volume[:, rows // 2, :]
    through_column = volume[:, :, columns // 2]
    tiles = (
        _labeled_tile(
            _letterbox(native, row_spacing=row_spacing, column_spacing=column_spacing),
            "NATIVE R:"
            f"{_short_direction(geometry.display_right_direction)} D:"
            f"{_short_direction(geometry.display_down_direction)}",
        ),
        _labeled_tile(
            _letterbox(through_row, row_spacing=slice_spacing, column_spacing=column_spacing),
            "ROW CENTER R:"
            f"{_short_direction(geometry.display_right_direction)} D:"
            f"{_short_direction(geometry.slice_advance_direction)}",
        ),
        _labeled_tile(
            _letterbox(through_column, row_spacing=slice_spacing, column_spacing=row_spacing),
            "COLUMN CENTER R:"
            f"{_short_direction(geometry.display_down_direction)} D:"
            f"{_short_direction(geometry.slice_advance_direction)}",
        ),
    )
    canvas = Image.new(
        "L",
        (3 * TILE_PIXELS + 2 * TILE_GAP_PIXELS, TILE_PIXELS + CAPTION_PIXELS),
        color=0,
    )
    for index, tile in enumerate(tiles):
        canvas.paste(tile, (index * (TILE_PIXELS + TILE_GAP_PIXELS), 0))
    aspects: tuple[Mapping[str, object], ...] = (
        {
            "height_mm": _fixed_float(rows * row_spacing),
            "view": "native_center",
            "width_mm": _fixed_float(columns * column_spacing),
        },
        {
            "height_mm": _fixed_float(slices * slice_spacing),
            "view": "through_row_center",
            "width_mm": _fixed_float(columns * column_spacing),
        },
        {
            "height_mm": _fixed_float(slices * slice_spacing),
            "view": "through_column_center",
            "width_mm": _fixed_float(rows * row_spacing),
        },
    )
    return canvas, aspects


def _histogram_image(before: FloatVolume, after: FloatVolume) -> Image.Image:
    combined_minimum = min(float(np.min(before)), float(np.min(after)))
    combined_maximum = max(float(np.max(before)), float(np.max(after)))
    if combined_maximum <= combined_minimum:
        combined_minimum -= 0.5
        combined_maximum += 0.5
    value_range = (combined_minimum, combined_maximum)
    before_counts, _ = np.histogram(before, bins=HISTOGRAM_BINS, range=value_range)
    after_counts, _ = np.histogram(after, bins=HISTOGRAM_BINS, range=value_range)
    width, height, margin = 1024, 384, 48
    image = Image.new("RGB", (width, height), color=(0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.line((margin, height - margin, width - margin, height - margin), fill=(128, 128, 128))
    draw.line((margin, margin, margin, height - margin), fill=(128, 128, 128))
    maximum = max(int(np.max(before_counts)), int(np.max(after_counts)), 1)
    plot_width = width - 2 * margin
    plot_height = height - 2 * margin

    def points(counts: NDArray[np.int64]) -> list[tuple[int, int]]:
        return [
            (
                margin + index * (plot_width - 1) // (HISTOGRAM_BINS - 1),
                height - margin - int(count) * (plot_height - 1) // maximum,
            )
            for index, count in enumerate(counts)
        ]

    draw.line(points(before_counts), fill=(255, 96, 96), width=2)
    draw.line(points(after_counts), fill=(96, 224, 255), width=2)
    draw.text((margin + 4, 4), "SOURCE", fill=(255, 96, 96))
    draw.text((margin + 84, 4), "PREPROCESSED", fill=(96, 224, 255))
    return image


def _before_after(
    before: ByteImage,
    after: ByteImage,
    *,
    source_spacing: tuple[float, float],
    processed_spacing: tuple[float, float],
) -> Image.Image:
    before_tile = _labeled_tile(
        _letterbox(
            before,
            row_spacing=source_spacing[0],
            column_spacing=source_spacing[1],
        ),
        "SOURCE",
    )
    after_tile = _labeled_tile(
        _letterbox(
            after,
            row_spacing=processed_spacing[0],
            column_spacing=processed_spacing[1],
        ),
        "PREPROCESSED",
    )
    canvas = Image.new(
        "L", (2 * TILE_PIXELS + TILE_GAP_PIXELS, TILE_PIXELS + CAPTION_PIXELS), color=0
    )
    canvas.paste(before_tile, (0, 0))
    canvas.paste(after_tile, (TILE_PIXELS + TILE_GAP_PIXELS, 0))
    return canvas


def _png_bytes(image: Image.Image) -> bytes:
    clean = Image.frombytes(image.mode, image.size, image.tobytes())
    stream = BytesIO()
    clean.save(
        stream,
        format="PNG",
        optimize=False,
        compress_level=PNG_COMPRESS_LEVEL,
    )
    return stream.getvalue()


def _gif_bytes(frames: tuple[Image.Image, ...]) -> bytes:
    if not frames:
        raise QaRenderError(QaErrorCode.INVALID_VOLUME)
    palette = [channel for value in range(256) for channel in (value, value, value)]
    indexed: list[Image.Image] = []
    for frame in frames:
        clean = Image.frombytes("P", frame.size, frame.convert("L").tobytes())
        clean.putpalette(palette)
        indexed.append(clean)
    stream = BytesIO()
    indexed[0].save(
        stream,
        format="GIF",
        save_all=True,
        append_images=indexed[1:],
        duration=ANIMATION_FRAME_DURATION_MS,
        loop=0,
        disposal=2,
        optimize=False,
    )
    return stream.getvalue()


def _pending_review_row(metadata: QaSafeMetadata) -> ReviewLedgerRow:
    decisions = tuple((check, ReviewDecision.NOT_REVIEWED) for check in ReviewCheck)
    return ReviewLedgerRow(
        case_ordinal=metadata.case_ordinal,
        series_ordinal=metadata.series_ordinal,
        status=ReviewStatus.PENDING_PRIVATE_REVIEW,
        decisions=decisions,
    )


def _metadata_payload(
    *,
    metadata: QaSafeMetadata,
    source_shape: tuple[int, ...],
    processed_shape: tuple[int, ...],
    contact_indices: tuple[int, ...],
    animation_indices: tuple[int, ...],
    relative_positions: tuple[float, ...],
    orthogonal_status: OrthogonalStatus,
    physical_aspect: tuple[Mapping[str, object], ...],
    artifacts: tuple[PrivateArtifact, ...],
) -> dict[str, object]:
    geometry = metadata.geometry
    return {
        "animation": {
            "frame_duration_ms": ANIMATION_FRAME_DURATION_MS,
            "maximum_frames": ANIMATION_MAX_FRAMES,
            "slice_indices": list(animation_indices),
            "relative_positions_mm": [
                _fixed_float(relative_positions[index]) for index in animation_indices
            ],
        },
        "artifacts": [artifact.as_payload() for artifact in artifacts],
        "case_ordinal": metadata.case_ordinal,
        "contact_sheet": {
            "grid_columns": CONTACT_GRID_SIZE,
            "grid_rows": CONTACT_GRID_SIZE,
            "slice_indices": list(contact_indices),
            "relative_positions_mm": [
                _fixed_float(relative_positions[index]) for index in contact_indices
            ],
        },
        "fat_suppression": metadata.fat_suppression.value,
        "geometry": {
            "column_spacing_mm": _optional_fixed_float(geometry.column_spacing_mm),
            "display_down_direction": geometry.display_down_direction.value,
            "display_right_direction": geometry.display_right_direction.value,
            "orientation_consistent": geometry.orientation_consistent,
            "positions_monotonic": geometry.positions_monotonic,
            "row_spacing_mm": _optional_fixed_float(geometry.row_spacing_mm),
            "processed_column_spacing_mm": _optional_fixed_float(
                geometry.processed_column_spacing_mm
            ),
            "processed_row_spacing_mm": _optional_fixed_float(geometry.processed_row_spacing_mm),
            "slice_advance_direction": geometry.slice_advance_direction.value,
            "slice_spacing_mm": _optional_fixed_float(geometry.slice_spacing_mm),
            "spacing_consistent": geometry.spacing_consistent,
        },
        "histogram_bins": HISTOGRAM_BINS,
        "laterality": metadata.laterality.value,
        "ordering": metadata.ordering.value,
        "orthogonal": {
            "display_interpolation": "bilinear",
            "physical_aspect": list(physical_aspect),
            "status": orthogonal_status.value,
            "through_plane_isotropic_resampling": False,
        },
        "photometric": metadata.photometric.value,
        "plane": metadata.plane.value,
        "preprocessed_shape": list(processed_shape),
        "renderer_version": RENDERER_VERSION,
        "result": QaResultCode.COMPLETE.value,
        "schema_version": METADATA_SCHEMA_VERSION,
        "sequence": metadata.sequence.value,
        "series_ordinal": metadata.series_ordinal,
        "source_shape": list(source_shape),
    }


def _fixed_float(value: float) -> float:
    return round(float(value), 6)


def _optional_fixed_float(value: float | None) -> float | None:
    return None if value is None else _fixed_float(value)


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def _artifact_record(kind: QaArtifactKind, basename: str, payload: bytes) -> PrivateArtifact:
    return PrivateArtifact(
        kind=kind,
        basename=basename,
        bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _write_artifacts(
    output_dir: Path, payloads: Sequence[tuple[QaArtifactKind, str, bytes]]
) -> None:
    if not isinstance(output_dir, Path):
        raise QaRenderError(QaErrorCode.OUTPUT_DIRECTORY_INVALID)
    try:
        if output_dir.is_symlink():
            raise QaRenderError(QaErrorCode.OUTPUT_DIRECTORY_INVALID)
        output_dir.mkdir(parents=True, exist_ok=True)
        if not output_dir.is_dir() or output_dir.is_symlink():
            raise QaRenderError(QaErrorCode.OUTPUT_DIRECTORY_INVALID)
    except QaRenderError:
        raise
    except OSError:
        raise QaRenderError(QaErrorCode.OUTPUT_DIRECTORY_INVALID) from None
    targets = tuple(output_dir / basename for _, basename, _ in payloads)
    if any(target.exists() or target.is_symlink() for target in targets):
        raise QaRenderError(QaErrorCode.ARTIFACT_EXISTS)
    created: list[Path] = []
    try:
        for target, (_, _, payload) in zip(targets, payloads, strict=True):
            with target.open("xb") as handle:
                handle.write(payload)
            os.chmod(target, 0o600)
            created.append(target)
    except OSError:
        for target in created:
            with suppress(OSError):
                target.unlink()
        raise QaRenderError(QaErrorCode.ARTIFACT_WRITE_FAILED) from None
