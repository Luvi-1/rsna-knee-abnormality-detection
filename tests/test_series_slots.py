from __future__ import annotations

from dataclasses import fields, replace
from hashlib import sha256
from itertools import permutations

import pytest

from rsna_knee.data.series_slots import (
    ADDITIONAL_OR_DUPLICATE_SLOT,
    PRIMARY_SLOT_ORDER,
    AnatomicalPlane,
    PlaneSource,
    PrimarySeriesSlot,
    QualityBlockReason,
    RetentionReason,
    SeriesCandidate,
    SeriesQuality,
    SeriesSlotAssignment,
    assign_series_slots,
    plane_from_image_orientation,
)


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _quality(
    *,
    slices: int = 24,
    coverage_mm: float = 92.0,
    pixel_spacing_mm: tuple[float, float] = (0.5, 0.5),
    spacing_cv: float = 0.01,
) -> SeriesQuality:
    return SeriesQuality(
        total_slices=slices,
        decoded_slices=slices,
        decode_failure_count=0,
        duplicate_slices=0,
        geometry_valid=True,
        spacing_regular=True,
        median_slice_spacing_mm=4.0,
        spacing_coefficient_of_variation=spacing_cv,
        pixel_spacing_mm=pixel_spacing_mm,
        physical_coverage_mm=coverage_mm,
    )


def _candidate(
    name: str,
    plane: AnatomicalPlane | str | None,
    fluid: bool | int | str | None,
    *,
    quality: SeriesQuality | None = None,
    iop: tuple[float, float, float, float, float, float] | None = None,
) -> SeriesCandidate:
    return SeriesCandidate(
        series_key=f"opaque-{name}",
        tie_break_key=_digest(name),
        organizer_plane=plane,
        organizer_fluid_sensitive=fluid,
        image_orientation_patient=iop,
        quality=quality or _quality(),
    )


def _primaries(result: SeriesSlotAssignment) -> dict[PrimarySeriesSlot, str | None]:
    selections = result.primary_slots
    return {
        selection.slot: (
            None if selection.primary is None else selection.primary.candidate.series_key
        )
        for selection in selections
    }


@pytest.mark.parametrize(
    ("plane", "fluid", "expected"),
    [
        (AnatomicalPlane.SAGITTAL, True, PrimarySeriesSlot.SAGITTAL_FLUID_SENSITIVE),
        (AnatomicalPlane.SAGITTAL, False, PrimarySeriesSlot.SAGITTAL_STRUCTURAL),
        (AnatomicalPlane.CORONAL, True, PrimarySeriesSlot.CORONAL_FLUID_SENSITIVE),
        (AnatomicalPlane.CORONAL, False, PrimarySeriesSlot.CORONAL_STRUCTURAL),
        (AnatomicalPlane.AXIAL, True, PrimarySeriesSlot.AXIAL_FLUID_SENSITIVE),
        (AnatomicalPlane.AXIAL, False, PrimarySeriesSlot.AXIAL_STRUCTURAL),
    ],
)
def test_each_primary_slot_uses_organizer_flags(
    plane: AnatomicalPlane, fluid: bool, expected: PrimarySeriesSlot
) -> None:
    candidate = _candidate(expected.value, plane, fluid)

    result = assign_series_slots((candidate,))

    assert _primaries(result)[expected] == candidate.series_key
    selected = next(item for item in result.primary_slots if item.slot is expected)
    assert selected.primary is not None
    assert selected.primary.plane_source is PlaneSource.ORGANIZER


def test_multiple_series_are_quality_ranked_and_extras_retain_original_slot() -> None:
    lower = _candidate(
        "lower",
        "sagittal",
        "yes",
        quality=_quality(coverage_mm=70.0, pixel_spacing_mm=(0.7, 0.7)),
    )
    higher = _candidate(
        "higher",
        "sagittal",
        1,
        quality=_quality(coverage_mm=110.0, pixel_spacing_mm=(0.4, 0.4)),
    )

    result = assign_series_slots((lower, higher))

    slot = PrimarySeriesSlot.SAGITTAL_FLUID_SENSITIVE
    assert _primaries(result)[slot] == higher.series_key
    assert len(result.additional_or_duplicate) == 1
    extra = result.additional_or_duplicate[0]
    assert extra.candidate == lower
    assert extra.original_slot is slot
    assert extra.reasons == (RetentionReason.DUPLICATE_SLOT,)


def test_missing_series_mask_has_fixed_six_slot_order() -> None:
    candidate = _candidate("only", AnatomicalPlane.CORONAL, False)

    result = assign_series_slots((candidate,))

    assert tuple(PrimarySeriesSlot) == PRIMARY_SLOT_ORDER
    assert result.missing_mask == (True, True, True, False, True, True)
    assert ADDITIONAL_OR_DUPLICATE_SLOT == "additional_or_duplicate"


def test_unknown_flags_are_retained_and_fluid_state_is_never_guessed() -> None:
    unknown_both = _candidate("unknown-both", "not-a-plane", "possibly")
    known_plane = _candidate("unknown-fluid", AnatomicalPlane.AXIAL, "T2 bright")

    result = assign_series_slots((unknown_both, known_plane))

    assert all(result.missing_mask)
    extras = {item.candidate.series_key: item for item in result.additional_or_duplicate}
    assert extras[unknown_both.series_key].reasons == (
        RetentionReason.UNKNOWN_PLANE,
        RetentionReason.UNKNOWN_FLUID_STATE,
    )
    assert extras[known_plane.series_key].reasons == (RetentionReason.UNKNOWN_FLUID_STATE,)


def test_validated_iop_fallback_supports_cardinal_and_oblique_dominant_normals() -> None:
    axial = _candidate("axial-iop", None, True, iop=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0))
    # row x column = (0.8, 0.6, 0.0), a sagittal-dominant oblique normal.
    oblique = _candidate("oblique-iop", "malformed", False, iop=(0.0, 0.0, 1.0, 0.6, -0.8, 0.0))

    result = assign_series_slots((axial, oblique))

    assert _primaries(result)[PrimarySeriesSlot.AXIAL_FLUID_SENSITIVE] == axial.series_key
    assert _primaries(result)[PrimarySeriesSlot.SAGITTAL_STRUCTURAL] == oblique.series_key
    selected = [item.primary for item in result.primary_slots if item.primary is not None]
    assert all(item.plane_source is PlaneSource.IMAGE_ORIENTATION_PATIENT for item in selected)
    assert plane_from_image_orientation((1.0, 0.0, 0.0, 0.0, 1.0, 0.0)) is AnatomicalPlane.AXIAL
    assert plane_from_image_orientation((1.0, 0.0, 0.0, 1.0, 0.0, 0.0)) is None


def test_recognized_organizer_plane_conflicting_with_validated_iop_is_blocked() -> None:
    candidate = _candidate(
        "organizer-first",
        AnatomicalPlane.CORONAL,
        True,
        iop=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
    )

    result = assign_series_slots((candidate,))

    assert all(result.missing_mask)
    assert result.additional_or_duplicate[0].candidate == candidate
    assert result.additional_or_duplicate[0].original_slot is None
    assert result.additional_or_duplicate[0].plane_source is None
    assert result.additional_or_duplicate[0].reasons == (
        RetentionReason.CONFLICTING_PLANE_METADATA,
    )


def test_blocked_series_cannot_outscore_a_usable_primary() -> None:
    healthy = _candidate(
        "healthy",
        AnatomicalPlane.CORONAL,
        True,
        quality=_quality(slices=12, coverage_mm=45.0, pixel_spacing_mm=(0.8, 0.8)),
    )
    blocked_quality = replace(
        _quality(slices=80, coverage_mm=240.0, pixel_spacing_mm=(0.2, 0.2)),
        decoded_slices=79,
        decode_failure_count=1,
    )
    blocked = _candidate("blocked", AnatomicalPlane.CORONAL, True, quality=blocked_quality)

    result = assign_series_slots((blocked, healthy))

    slot = PrimarySeriesSlot.CORONAL_FLUID_SENSITIVE
    assert _primaries(result)[slot] == healthy.series_key
    extra = next(item for item in result.additional_or_duplicate if item.candidate == blocked)
    assert QualityBlockReason.DECODE_FAILURE in blocked.quality.blocked_reasons
    assert extra.reasons == (
        RetentionReason.BLOCKED_QUALITY,
        RetentionReason.DUPLICATE_SLOT,
    )


def test_all_blocked_series_leave_slot_missing_but_are_retained() -> None:
    blocked = _candidate(
        "all-blocked",
        AnatomicalPlane.SAGITTAL,
        False,
        quality=replace(_quality(), geometry_valid=False),
    )

    result = assign_series_slots((blocked,))

    slot_index = PRIMARY_SLOT_ORDER.index(PrimarySeriesSlot.SAGITTAL_STRUCTURAL)
    assert result.missing_mask[slot_index]
    assert _primaries(result)[PrimarySeriesSlot.SAGITTAL_STRUCTURAL] is None
    assert result.additional_or_duplicate[0].original_slot is PrimarySeriesSlot.SAGITTAL_STRUCTURAL
    assert result.additional_or_duplicate[0].reasons == (RetentionReason.BLOCKED_QUALITY,)


def test_assignment_is_permutation_deterministic() -> None:
    candidates = (
        _candidate("a", AnatomicalPlane.AXIAL, True, quality=_quality(coverage_mm=80.0)),
        _candidate("b", AnatomicalPlane.AXIAL, True, quality=_quality(coverage_mm=100.0)),
        _candidate("c", None, False, iop=(0.0, 1.0, 0.0, 0.0, 0.0, 1.0)),
        _candidate("d", None, None),
    )

    expected = assign_series_slots(candidates)

    assert all(assign_series_slots(tuple(order)) == expected for order in permutations(candidates))


def test_classifier_has_no_free_text_or_filename_inputs() -> None:
    field_names = {field.name for field in fields(SeriesCandidate)}
    assert field_names.isdisjoint(
        {"filename", "path", "series_description", "protocol_name", "sequence_name"}
    )
    filename_like_plane = _candidate("filename-like", "sagittal survey protocol.dcm", False)

    result = assign_series_slots((filename_like_plane,))

    assert all(result.missing_mask)
    assert result.additional_or_duplicate[0].reasons == (RetentionReason.UNKNOWN_PLANE,)


def test_quality_components_and_block_reasons_are_explicit() -> None:
    quality = SeriesQuality(
        total_slices=3,
        decoded_slices=2,
        decode_failure_count=1,
        duplicate_slices=1,
        geometry_valid=False,
        spacing_regular=False,
        median_slice_spacing_mm=None,
        spacing_coefficient_of_variation=None,
        pixel_spacing_mm=None,
        physical_coverage_mm=None,
    )

    assert quality.blocked_reasons == (
        QualityBlockReason.DECODE_FAILURE,
        QualityBlockReason.INVALID_GEOMETRY,
        QualityBlockReason.MISSING_PIXEL_SPACING,
        QualityBlockReason.MISSING_SLICE_SPACING,
        QualityBlockReason.IRREGULAR_SLICE_SPACING,
        QualityBlockReason.DUPLICATE_SLICES,
        QualityBlockReason.MISSING_PHYSICAL_COVERAGE,
    )
    assert quality.components.decode_fraction == pytest.approx(2 / 3)
    assert quality.components.duplicate_fraction == pytest.approx(0.5)


def test_duplicate_tie_break_keys_fail_instead_of_using_input_order() -> None:
    first = _candidate("same", AnatomicalPlane.AXIAL, False)
    second = replace(first, series_key="another-private-series")

    with pytest.raises(ValueError, match="duplicate_tie_break_key"):
        assign_series_slots((first, second))
