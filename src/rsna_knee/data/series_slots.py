"""Deterministic MRI series-slot assignment without free-text heuristics.

Organizer plane and fluid-sensitivity flags are authoritative when recognized and consistent with
validated ``ImageOrientationPatient``.  Physical plane conflicts are blocked, while a validated
orientation may recover a missing or malformed organizer plane.  Fluid sensitivity is never
inferred.  Critical quality failures remain explicit and cannot be hidden by ranking.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import inf, isfinite, sqrt
from typing import Final

from rsna_knee.dicom.audit import IOP_ORTHONORMAL_TOLERANCE


class AnatomicalPlane(StrEnum):
    """Supported diagnostic MRI planes."""

    SAGITTAL = "sagittal"
    CORONAL = "coronal"
    AXIAL = "axial"


class PrimarySeriesSlot(StrEnum):
    """The six primary plane-by-sequence slots."""

    SAGITTAL_FLUID_SENSITIVE = "sagittal_fluid_sensitive"
    SAGITTAL_STRUCTURAL = "sagittal_structural"
    CORONAL_FLUID_SENSITIVE = "coronal_fluid_sensitive"
    CORONAL_STRUCTURAL = "coronal_structural"
    AXIAL_FLUID_SENSITIVE = "axial_fluid_sensitive"
    AXIAL_STRUCTURAL = "axial_structural"


ADDITIONAL_OR_DUPLICATE_SLOT: Final = "additional_or_duplicate"
PRIMARY_SLOT_ORDER: Final = tuple(PrimarySeriesSlot)


class PlaneSource(StrEnum):
    """Evidence used for plane classification."""

    ORGANIZER = "organizer"
    IMAGE_ORIENTATION_PATIENT = "image_orientation_patient"


class QualityBlockReason(StrEnum):
    """Critical reasons a series cannot become a model-input primary."""

    NO_DECODABLE_SLICES = "no_decodable_slices"
    DECODE_FAILURE = "decode_failure"
    INVALID_GEOMETRY = "invalid_geometry"
    MISSING_PIXEL_SPACING = "missing_pixel_spacing"
    MISSING_SLICE_SPACING = "missing_slice_spacing"
    IRREGULAR_SLICE_SPACING = "irregular_slice_spacing"
    DUPLICATE_SLICES = "duplicate_slices"
    MISSING_PHYSICAL_COVERAGE = "missing_physical_coverage"


class RetentionReason(StrEnum):
    """Why a series was retained outside a primary slot."""

    UNKNOWN_PLANE = "unknown_plane"
    CONFLICTING_PLANE_METADATA = "conflicting_plane_metadata"
    UNKNOWN_FLUID_STATE = "unknown_fluid_state"
    BLOCKED_QUALITY = "blocked_quality"
    DUPLICATE_SLOT = "duplicate_slot"


@dataclass(frozen=True, slots=True)
class SeriesQualityComponents:
    """Transparent ranking components; no component can clear a block reason."""

    decode_fraction: float
    duplicate_fraction: float
    spacing_coefficient_of_variation: float | None
    in_plane_resolution_area_mm2: float | None
    physical_coverage_mm: float | None
    decoded_slices: int


@dataclass(frozen=True, slots=True)
class SeriesQuality:
    """Validated series evidence used for eligibility and deterministic ranking."""

    total_slices: int
    decoded_slices: int
    decode_failure_count: int
    duplicate_slices: int
    geometry_valid: bool
    spacing_regular: bool
    median_slice_spacing_mm: float | None
    spacing_coefficient_of_variation: float | None
    pixel_spacing_mm: tuple[float, float] | None
    physical_coverage_mm: float | None

    def __post_init__(self) -> None:
        if self.total_slices < 0:
            raise ValueError("total_slices_must_be_nonnegative")
        if self.decoded_slices < 0 or self.decode_failure_count < 0:
            raise ValueError("decode_counts_must_be_nonnegative")
        if self.decoded_slices + self.decode_failure_count != self.total_slices:
            raise ValueError("decode_counts_do_not_reconcile")
        if not 0 <= self.duplicate_slices <= self.decoded_slices:
            raise ValueError("duplicate_slice_count_invalid")
        _validate_optional_nonnegative(
            self.median_slice_spacing_mm, "median_slice_spacing_mm_invalid", positive=True
        )
        _validate_optional_nonnegative(
            self.spacing_coefficient_of_variation,
            "spacing_coefficient_of_variation_invalid",
        )
        _validate_optional_nonnegative(self.physical_coverage_mm, "physical_coverage_mm_invalid")
        if self.pixel_spacing_mm is not None and (
            len(self.pixel_spacing_mm) != 2
            or any(not isfinite(value) or value <= 0.0 for value in self.pixel_spacing_mm)
        ):
            raise ValueError("pixel_spacing_mm_invalid")

    @property
    def blocked_reasons(self) -> tuple[QualityBlockReason, ...]:
        """Return every critical reason, in fixed policy order."""

        reasons: list[QualityBlockReason] = []
        if self.decoded_slices == 0:
            reasons.append(QualityBlockReason.NO_DECODABLE_SLICES)
        if self.decode_failure_count:
            reasons.append(QualityBlockReason.DECODE_FAILURE)
        if not self.geometry_valid:
            reasons.append(QualityBlockReason.INVALID_GEOMETRY)
        if self.pixel_spacing_mm is None:
            reasons.append(QualityBlockReason.MISSING_PIXEL_SPACING)
        if self.decoded_slices > 1 and self.median_slice_spacing_mm is None:
            reasons.append(QualityBlockReason.MISSING_SLICE_SPACING)
        if not self.spacing_regular:
            reasons.append(QualityBlockReason.IRREGULAR_SLICE_SPACING)
        if self.duplicate_slices:
            reasons.append(QualityBlockReason.DUPLICATE_SLICES)
        if self.decoded_slices > 1 and (
            self.physical_coverage_mm is None or self.physical_coverage_mm <= 0.0
        ):
            reasons.append(QualityBlockReason.MISSING_PHYSICAL_COVERAGE)
        return tuple(reasons)

    @property
    def blocked(self) -> bool:
        """Whether the series is ineligible for a primary model-input slot."""

        return bool(self.blocked_reasons)

    @property
    def components(self) -> SeriesQualityComponents:
        """Expose each ranking component for audit and provenance."""

        decode_fraction = self.decoded_slices / self.total_slices if self.total_slices else 0.0
        duplicate_fraction = (
            self.duplicate_slices / self.decoded_slices if self.decoded_slices else 0.0
        )
        pixel_area = (
            None
            if self.pixel_spacing_mm is None
            else self.pixel_spacing_mm[0] * self.pixel_spacing_mm[1]
        )
        return SeriesQualityComponents(
            decode_fraction=decode_fraction,
            duplicate_fraction=duplicate_fraction,
            spacing_coefficient_of_variation=self.spacing_coefficient_of_variation,
            in_plane_resolution_area_mm2=pixel_area,
            physical_coverage_mm=self.physical_coverage_mm,
            decoded_slices=self.decoded_slices,
        )

    def ranking_key(self, tie_break_key: str) -> tuple[int, float, float, float, float, int, str]:
        """Return an ascending key with eligibility ahead of every quality component."""

        _validate_tie_break_key(tie_break_key)
        components = self.components
        return (
            int(self.blocked),
            -components.decode_fraction,
            (
                components.spacing_coefficient_of_variation
                if components.spacing_coefficient_of_variation is not None
                else inf
            ),
            (
                -components.physical_coverage_mm
                if components.physical_coverage_mm is not None
                else inf
            ),
            (
                components.in_plane_resolution_area_mm2
                if components.in_plane_resolution_area_mm2 is not None
                else inf
            ),
            -components.decoded_slices,
            tie_break_key,
        )


@dataclass(frozen=True, slots=True)
class SeriesCandidate:
    """Private series evidence accepted by the slot classifier.

    No filename, protocol name, or free-text description is accepted by this interface.
    ``tie_break_key`` must be an opaque lowercase SHA-256-style value.
    """

    series_key: str
    tie_break_key: str
    organizer_plane: AnatomicalPlane | str | None
    organizer_fluid_sensitive: bool | int | str | None
    image_orientation_patient: tuple[float, float, float, float, float, float] | None
    quality: SeriesQuality

    def __post_init__(self) -> None:
        if not self.series_key:
            raise ValueError("series_key_empty")
        _validate_tie_break_key(self.tie_break_key)


@dataclass(frozen=True, slots=True)
class ClassifiedSeries:
    """A series with its original primary-slot classification evidence."""

    candidate: SeriesCandidate
    original_slot: PrimarySeriesSlot
    plane_source: PlaneSource


@dataclass(frozen=True, slots=True)
class PrimarySlotSelection:
    """The optional usable primary selected for one fixed slot."""

    slot: PrimarySeriesSlot
    primary: ClassifiedSeries | None


@dataclass(frozen=True, slots=True)
class RetainedAdditionalSeries:
    """A non-primary series retained with slot and reason provenance."""

    candidate: SeriesCandidate
    original_slot: PrimarySeriesSlot | None
    plane_source: PlaneSource | None
    reasons: tuple[RetentionReason, ...]


@dataclass(frozen=True, slots=True)
class SeriesSlotAssignment:
    """Fixed-order primary slots, additional series, and six-slot missing mask."""

    primary_slots: tuple[PrimarySlotSelection, ...]
    additional_or_duplicate: tuple[RetainedAdditionalSeries, ...]
    missing_mask: tuple[bool, bool, bool, bool, bool, bool]


def assign_series_slots(candidates: tuple[SeriesCandidate, ...]) -> SeriesSlotAssignment:
    """Classify, rank, and retain a study's series deterministically."""

    tie_break_keys = [candidate.tie_break_key for candidate in candidates]
    if len(set(tie_break_keys)) != len(tie_break_keys):
        raise ValueError("duplicate_tie_break_key")

    grouped: dict[PrimarySeriesSlot, list[ClassifiedSeries]] = {
        slot: [] for slot in PRIMARY_SLOT_ORDER
    }
    additional: list[RetainedAdditionalSeries] = []
    for candidate in candidates:
        plane, plane_source, plane_conflict = _classify_plane(candidate)
        fluid_sensitive = _parse_fluid_sensitive(candidate.organizer_fluid_sensitive)
        classification_reasons: list[RetentionReason] = []
        if plane_conflict:
            classification_reasons.append(RetentionReason.CONFLICTING_PLANE_METADATA)
        elif plane is None:
            classification_reasons.append(RetentionReason.UNKNOWN_PLANE)
        if fluid_sensitive is None:
            classification_reasons.append(RetentionReason.UNKNOWN_FLUID_STATE)
        if plane is None or fluid_sensitive is None:
            additional.append(
                RetainedAdditionalSeries(
                    candidate=candidate,
                    original_slot=None,
                    plane_source=plane_source,
                    reasons=tuple(classification_reasons),
                )
            )
            continue
        if plane_source is None:
            raise RuntimeError("classified_plane_has_no_source")
        slot = _primary_slot(plane, fluid_sensitive)
        grouped[slot].append(ClassifiedSeries(candidate, slot, plane_source))

    selections: list[PrimarySlotSelection] = []
    for slot in PRIMARY_SLOT_ORDER:
        ranked = sorted(
            grouped[slot],
            key=lambda item: item.candidate.quality.ranking_key(item.candidate.tie_break_key),
        )
        usable = [item for item in ranked if not item.candidate.quality.blocked]
        primary = usable[0] if usable else None
        selections.append(PrimarySlotSelection(slot, primary))
        for item in ranked:
            if item is primary:
                continue
            reasons: list[RetentionReason] = []
            if item.candidate.quality.blocked:
                reasons.append(RetentionReason.BLOCKED_QUALITY)
            if primary is not None:
                reasons.append(RetentionReason.DUPLICATE_SLOT)
            additional.append(
                RetainedAdditionalSeries(
                    candidate=item.candidate,
                    original_slot=item.original_slot,
                    plane_source=item.plane_source,
                    reasons=tuple(reasons),
                )
            )

    additional.sort(
        key=lambda item: (
            PRIMARY_SLOT_ORDER.index(item.original_slot) if item.original_slot is not None else 6,
            item.candidate.quality.ranking_key(item.candidate.tie_break_key),
        )
    )
    primary_tuple = tuple(selections)
    missing = tuple(selection.primary is None for selection in primary_tuple)
    if len(missing) != 6:
        raise RuntimeError("primary_slot_count_invalid")
    return SeriesSlotAssignment(
        primary_slots=primary_tuple,
        additional_or_duplicate=tuple(additional),
        missing_mask=(missing[0], missing[1], missing[2], missing[3], missing[4], missing[5]),
    )


def _classify_plane(
    candidate: SeriesCandidate,
) -> tuple[AnatomicalPlane | None, PlaneSource | None, bool]:
    organizer = _parse_organizer_plane(candidate.organizer_plane)
    derived = plane_from_image_orientation(candidate.image_orientation_patient)
    if organizer is not None and derived is not None and organizer is not derived:
        return None, None, True
    if organizer is not None:
        return organizer, PlaneSource.ORGANIZER, False
    if derived is not None:
        return derived, PlaneSource.IMAGE_ORIENTATION_PATIENT, False
    return None, None, False


def plane_from_image_orientation(
    orientation: tuple[float, float, float, float, float, float] | None,
) -> AnatomicalPlane | None:
    """Derive a plane from a validated, clearly dominant IOP slice normal."""

    if (
        orientation is None
        or len(orientation) != 6
        or not all(isfinite(value) for value in orientation)
    ):
        return None
    row = orientation[:3]
    column = orientation[3:]
    row_norm = sqrt(sum(value * value for value in row))
    column_norm = sqrt(sum(value * value for value in column))
    dot = sum(left * right for left, right in zip(row, column, strict=True))
    if (
        abs(row_norm - 1.0) > IOP_ORTHONORMAL_TOLERANCE
        or abs(column_norm - 1.0) > IOP_ORTHONORMAL_TOLERANCE
        or abs(dot) > IOP_ORTHONORMAL_TOLERANCE
    ):
        return None
    normal = (
        row[1] * column[2] - row[2] * column[1],
        row[2] * column[0] - row[0] * column[2],
        row[0] * column[1] - row[1] * column[0],
    )
    normal_norm = sqrt(sum(value * value for value in normal))
    if abs(normal_norm - 1.0) > IOP_ORTHONORMAL_TOLERANCE:
        return None
    magnitudes = tuple(abs(value / normal_norm) for value in normal)
    ordered_axes = sorted(range(3), key=lambda index: (-magnitudes[index], index))
    if magnitudes[ordered_axes[0]] - magnitudes[ordered_axes[1]] < 0.05:
        return None
    return (
        AnatomicalPlane.SAGITTAL,
        AnatomicalPlane.CORONAL,
        AnatomicalPlane.AXIAL,
    )[ordered_axes[0]]


def _parse_organizer_plane(value: AnatomicalPlane | str | None) -> AnatomicalPlane | None:
    if isinstance(value, AnatomicalPlane):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    try:
        return AnatomicalPlane(normalized)
    except ValueError:
        return None


def _parse_fluid_sensitive(value: bool | int | str | None) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value) if value in {0, 1} else None
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    return None


def _primary_slot(plane: AnatomicalPlane, fluid_sensitive: bool) -> PrimarySeriesSlot:
    sequence = "fluid_sensitive" if fluid_sensitive else "structural"
    return PrimarySeriesSlot(f"{plane.value}_{sequence}")


def _validate_optional_nonnegative(
    value: float | None, code: str, *, positive: bool = False
) -> None:
    if value is None:
        return
    if not isfinite(value) or value < 0.0 or (positive and value == 0.0):
        raise ValueError(code)


def _validate_tie_break_key(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("tie_break_key_must_be_lowercase_sha256")
