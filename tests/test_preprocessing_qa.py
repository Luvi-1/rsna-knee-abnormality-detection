from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import replace
from pathlib import Path
from typing import cast

import numpy as np
import pytest
from PIL import Image

from rsna_knee.qa.preprocessing import (
    ANIMATION_FRAME_DURATION_MS,
    ANIMATION_MAX_FRAMES,
    HEADER_PIXELS,
    HISTOGRAM_BINS,
    METADATA_SCHEMA_VERSION,
    RENDERER_VERSION,
    REVIEW_LEDGER_SCHEMA_VERSION,
    OrthogonalStatus,
    QaArtifactKind,
    QaDirection,
    QaErrorCode,
    QaGeometry,
    QaLaterality,
    QaOrdering,
    QaPhotometric,
    QaPlane,
    QaPresence,
    QaRenderError,
    QaResultCode,
    QaSafeMetadata,
    QaSequence,
    ReviewCheck,
    ReviewDecision,
    ReviewStatus,
    physical_slice_indices,
    qa_direction_from_lps,
    render_private_qa,
    review_ledger_schema,
)


def _volume(slices: int = 30, rows: int = 12, columns: int = 16) -> np.ndarray:
    slice_values = np.arange(slices, dtype=np.float32)[:, None, None] * 7.0
    row_values = np.arange(rows, dtype=np.float32)[None, :, None] * 2.0
    column_values = np.arange(columns, dtype=np.float32)[None, None, :]
    return np.asarray(slice_values + row_values + column_values, dtype=np.float32)


def _metadata(
    *,
    geometry: QaGeometry | None = None,
    case_ordinal: int = 12,
    series_ordinal: int = 3,
) -> QaSafeMetadata:
    return QaSafeMetadata(
        case_ordinal=case_ordinal,
        series_ordinal=series_ordinal,
        plane=QaPlane.SAGITTAL,
        sequence=QaSequence.FLUID_SENSITIVE,
        fat_suppression=QaPresence.PRESENT,
        photometric=QaPhotometric.MONOCHROME2,
        laterality=QaLaterality.LEFT,
        ordering=QaOrdering.PHYSICAL_GEOMETRY,
        geometry=geometry
        or QaGeometry(
            row_spacing_mm=0.5,
            column_spacing_mm=0.75,
            slice_spacing_mm=1.5,
            orientation_consistent=True,
            spacing_consistent=True,
            positions_monotonic=True,
            processed_row_spacing_mm=0.5,
            processed_column_spacing_mm=0.75,
            display_right_direction=QaDirection.LEFT,
            display_down_direction=QaDirection.POSTERIOR,
            slice_advance_direction=QaDirection.HEAD,
        ),
    )


def _artifact_path(output_dir: Path, suffix: str) -> Path:
    return output_dir / f"case_000012_series_003_{suffix}"


def _load_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="ascii")))


def test_complete_package_has_fixed_outputs_checksums_and_safe_metadata(tmp_path: Path) -> None:
    source = _volume()
    processed = np.asarray(np.sqrt(source + 1.0), dtype=np.float32)

    result = render_private_qa(
        source,
        processed,
        metadata=_metadata(),
        output_dir=tmp_path,
    )

    expected = {
        QaArtifactKind.CONTACT_SHEET: "contact.png",
        QaArtifactKind.ORTHOGONAL_VIEWS: "orthogonal.png",
        QaArtifactKind.INTENSITY_HISTOGRAM: "histogram.png",
        QaArtifactKind.SLICE_ANIMATION: "animation.gif",
        QaArtifactKind.BEFORE_AFTER_COMPARISON: "before_after.png",
        QaArtifactKind.REVIEW_LEDGER: "review.json",
        QaArtifactKind.METADATA_SUMMARY: "metadata.json",
    }
    assert result.code is QaResultCode.COMPLETE
    assert result.orthogonal_status is OrthogonalStatus.RENDERED
    assert [
        (artifact.kind, artifact.basename.removeprefix("case_000012_series_003_"))
        for artifact in result.artifacts
    ] == list(expected.items())
    for artifact in result.artifacts:
        artifact_path = tmp_path / artifact.basename
        payload = artifact_path.read_bytes()
        assert artifact.bytes == len(payload)
        assert artifact.sha256 == hashlib.sha256(payload).hexdigest()
        assert stat.S_IMODE(artifact_path.stat().st_mode) == 0o600
        assert "/" not in artifact.basename

    expected_sizes = {
        "contact.png": (1296, 1396),
        "orthogonal.png": (776, 292),
        "histogram.png": (1024, 384),
        "before_after.png": (516, 292),
    }
    for suffix, expected_size in expected_sizes.items():
        with Image.open(_artifact_path(tmp_path, suffix)) as image:
            assert image.size == expected_size
            assert image.getexif() == {}
            assert getattr(image, "text", {}) == {}
            assert not {"comment", "exif", "icc_profile"} & image.info.keys()

    metadata_path = _artifact_path(tmp_path, "metadata.json")
    metadata_raw = metadata_path.read_bytes()
    metadata_payload = _load_json(metadata_path)
    assert metadata_raw == (
        json.dumps(
            metadata_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")
    assert metadata_payload["schema_version"] == METADATA_SCHEMA_VERSION
    assert metadata_payload["renderer_version"] == RENDERER_VERSION
    assert metadata_payload["histogram_bins"] == HISTOGRAM_BINS
    assert metadata_payload["laterality"] == QaLaterality.LEFT.value
    assert metadata_payload["source_shape"] == [30, 12, 16]
    assert metadata_payload["preprocessed_shape"] == [30, 12, 16]
    assert cast(dict[str, object], metadata_payload["contact_sheet"])["slice_indices"] == list(
        physical_slice_indices(30, 25)
    )
    orthogonal = cast(dict[str, object], metadata_payload["orthogonal"])
    assert orthogonal["status"] == OrthogonalStatus.RENDERED.value
    assert orthogonal["through_plane_isotropic_resampling"] is False
    assert orthogonal["physical_aspect"] == [
        {"height_mm": 6.0, "view": "native_center", "width_mm": 12.0},
        {"height_mm": 45.0, "view": "through_row_center", "width_mm": 12.0},
        {"height_mm": 45.0, "view": "through_column_center", "width_mm": 6.0},
    ]
    metadata_inventory = cast(list[dict[str, object]], metadata_payload["artifacts"])
    assert [item["kind"] for item in metadata_inventory] == [
        item.value for item in tuple(expected)[:-1]
    ]

    review_path = _artifact_path(tmp_path, "review.json")
    review_payload = _load_json(review_path)
    assert review_payload["schema"] == review_ledger_schema()
    assert cast(dict[str, object], review_payload["schema"])["schema_version"] == (
        REVIEW_LEDGER_SCHEMA_VERSION
    )
    review_row = cast(dict[str, object], review_payload["row"])
    assert review_row["status"] == ReviewStatus.PENDING_PRIVATE_REVIEW.value
    assert review_row.keys() == {"case_ordinal", "series_ordinal", "status", "checks"}
    assert review_row["checks"] == {
        check.value: ReviewDecision.NOT_REVIEWED.value for check in ReviewCheck
    }

    safe_json = (metadata_raw + review_path.read_bytes()).decode("ascii").lower()
    for forbidden in (
        "patient",
        "studyinstanceuid",
        "seriesinstanceuid",
        "sopinstanceuid",
        ".dcm",
        "scanner",
        "site_name",
        "report_text",
        "/users/",
    ):
        assert forbidden not in safe_json


def test_repeat_render_is_byte_identical_and_does_not_mutate_inputs(tmp_path: Path) -> None:
    source = _volume(31, 11, 15)
    processed = np.asarray(source * 1.25 + 3.0, dtype=np.float32)
    source_before = source.copy()
    processed_before = processed.copy()

    first = render_private_qa(
        source,
        processed,
        metadata=_metadata(),
        output_dir=tmp_path / "first",
        contact_slice_indices=(0, 7, 15, 23, 30),
    )
    second = render_private_qa(
        source,
        processed,
        metadata=_metadata(),
        output_dir=tmp_path / "second",
        contact_slice_indices=(0, 7, 15, 23, 30),
    )

    assert first == second
    assert np.array_equal(source, source_before)
    assert np.array_equal(processed, processed_before)
    for artifact in first.artifacts:
        assert (tmp_path / "first" / artifact.basename).read_bytes() == (
            tmp_path / "second" / artifact.basename
        ).read_bytes()
    metadata = _load_json(_artifact_path(tmp_path / "first", "metadata.json"))
    assert cast(dict[str, object], metadata["contact_sheet"])["slice_indices"] == [
        0,
        7,
        15,
        23,
        30,
    ]


def test_animation_has_fixed_physical_order_frame_selection_and_timing(tmp_path: Path) -> None:
    source = np.broadcast_to(
        np.arange(70, dtype=np.float32)[:, None, None],
        (70, 9, 13),
    ).copy()
    result = render_private_qa(
        source,
        source,
        metadata=_metadata(),
        output_dir=tmp_path,
    )

    assert result.code is QaResultCode.COMPLETE
    animation_path = _artifact_path(tmp_path, "animation.gif")
    with Image.open(animation_path) as animation:
        assert animation.n_frames == ANIMATION_MAX_FRAMES
        values: list[int] = []
        durations: list[int] = []
        for frame_index in range(animation.n_frames):
            animation.seek(frame_index)
            values.append(animation.convert("L").getpixel((128, 128)))
            durations.append(cast(int, animation.info["duration"]))
        assert values == sorted(values)
        assert values[0] == 0
        assert values[-1] == 255
        assert durations == [ANIMATION_FRAME_DURATION_MS] * ANIMATION_MAX_FRAMES
        assert not {"comment", "exif", "icc_profile"} & animation.info.keys()

    metadata = _load_json(_artifact_path(tmp_path, "metadata.json"))
    animation_summary = cast(dict[str, object], metadata["animation"])
    selected = physical_slice_indices(70, ANIMATION_MAX_FRAMES)
    assert animation_summary == {
        "frame_duration_ms": ANIMATION_FRAME_DURATION_MS,
        "maximum_frames": ANIMATION_MAX_FRAMES,
        "relative_positions_mm": [index * 1.5 for index in selected],
        "slice_indices": list(selected),
    }


@pytest.mark.parametrize(
    ("geometry", "slices", "expected_status"),
    (
        (
            QaGeometry(None, 0.5, 1.0, True, True, True),
            12,
            OrthogonalStatus.INVALID_GEOMETRY,
        ),
        (
            QaGeometry(0.5, 0.5, 1.0, False, True, True),
            12,
            OrthogonalStatus.INCONSISTENT_GEOMETRY,
        ),
        (
            QaGeometry(0.5, 0.5, 2.5, True, True, True),
            12,
            OrthogonalStatus.THICK_SLICES,
        ),
        (
            QaGeometry(0.5, 0.5, 1.0, True, True, True),
            7,
            OrthogonalStatus.INSUFFICIENT_SLICES,
        ),
    ),
)
def test_orthogonal_view_is_suppressed_when_geometry_is_not_meaningful(
    tmp_path: Path,
    geometry: QaGeometry,
    slices: int,
    expected_status: OrthogonalStatus,
) -> None:
    source = _volume(slices)

    result = render_private_qa(
        source,
        source,
        metadata=_metadata(geometry=geometry),
        output_dir=tmp_path,
    )

    assert result.orthogonal_status is expected_status
    assert QaArtifactKind.ORTHOGONAL_VIEWS not in {artifact.kind for artifact in result.artifacts}
    assert not _artifact_path(tmp_path, "orthogonal.png").exists()
    assert len(result.artifacts) == 6
    decisions = dict(result.review_row.decisions)
    assert decisions[ReviewCheck.ANATOMICAL_ORIENTATION] is ReviewDecision.NOT_REVIEWED
    assert decisions[ReviewCheck.LATERALITY_PRESERVATION] is ReviewDecision.NOT_REVIEWED
    assert decisions[ReviewCheck.ANATOMY_NOT_CLIPPED] is ReviewDecision.NOT_REVIEWED
    metadata = _load_json(_artifact_path(tmp_path, "metadata.json"))
    orthogonal = cast(dict[str, object], metadata["orthogonal"])
    assert orthogonal["status"] == expected_status.value
    assert orthogonal["physical_aspect"] == []


def test_native_slice_display_preserves_left_right_orientation(tmp_path: Path) -> None:
    source = np.zeros((8, 16, 16), dtype=np.float32)
    source[:, :, :4] = 10.0

    render_private_qa(
        source,
        source,
        metadata=_metadata(
            geometry=QaGeometry(1.0, 1.0, 1.0, True, True, True),
        ),
        output_dir=tmp_path,
    )

    with Image.open(_artifact_path(tmp_path, "contact.png")) as contact:
        grayscale = contact.convert("L")
        assert grayscale.getpixel((16, HEADER_PIXELS + 16 + 128)) == 255
        assert grayscale.getpixel((240, HEADER_PIXELS + 16 + 128)) == 0
    with Image.open(_artifact_path(tmp_path, "before_after.png")) as comparison:
        grayscale = comparison.convert("L")
        assert grayscale.getpixel((16, HEADER_PIXELS + 16 + 128)) == 255
        assert grayscale.getpixel((240, HEADER_PIXELS + 16 + 128)) == 0


def test_laterality_legend_is_visible_without_changing_anatomical_pixels(tmp_path: Path) -> None:
    source = _volume(8, 16, 16)
    left = render_private_qa(
        source,
        source,
        metadata=_metadata(),
        output_dir=tmp_path / "left",
    )
    right = render_private_qa(
        source,
        source,
        metadata=replace(_metadata(), laterality=QaLaterality.RIGHT),
        output_dir=tmp_path / "right",
    )

    left_contact = next(
        item for item in left.artifacts if item.kind is QaArtifactKind.CONTACT_SHEET
    )
    right_contact = next(
        item for item in right.artifacts if item.kind is QaArtifactKind.CONTACT_SHEET
    )
    assert left_contact.sha256 != right_contact.sha256
    with Image.open(tmp_path / "left" / left_contact.basename) as left_image:
        left_body = left_image.convert("L").crop(
            (0, HEADER_PIXELS, left_image.width, left_image.height)
        )
    with Image.open(tmp_path / "right" / right_contact.basename) as right_image:
        right_body = right_image.convert("L").crop(
            (0, HEADER_PIXELS, right_image.width, right_image.height)
        )
    assert left_body.tobytes() == right_body.tobytes()


def test_patient_directions_and_positions_are_fixed_and_validated(tmp_path: Path) -> None:
    assert qa_direction_from_lps((1.0, 0.0, 0.0)) is QaDirection.LEFT
    assert qa_direction_from_lps((-1.0, 0.0, 0.0)) is QaDirection.RIGHT
    diagonal = 2.0**-0.5
    assert qa_direction_from_lps((diagonal, diagonal, 0.0)) is QaDirection.OBLIQUE

    source = _volume(3)
    invalid = replace(
        _metadata(),
        geometry=replace(_metadata().geometry, relative_slice_positions_mm=(0.0, 2.0)),
    )
    with pytest.raises(QaRenderError, match=QaErrorCode.UNSAFE_METADATA.value):
        render_private_qa(source, source, metadata=invalid, output_dir=tmp_path)


def test_metadata_and_slice_order_validation_fail_with_only_safe_codes(tmp_path: Path) -> None:
    source = _volume()
    unsafe = replace(_metadata(), plane=cast(QaPlane, "patient_name"))
    with pytest.raises(QaRenderError) as unsafe_error:
        render_private_qa(source, source, metadata=unsafe, output_dir=tmp_path / "unsafe")
    assert unsafe_error.value.code is QaErrorCode.UNSAFE_METADATA
    assert str(unsafe_error.value) == QaErrorCode.UNSAFE_METADATA.value
    assert unsafe_error.value.__cause__ is None

    unordered = replace(
        _metadata(),
        geometry=replace(_metadata().geometry, positions_monotonic=False),
    )
    with pytest.raises(QaRenderError) as order_error:
        render_private_qa(source, source, metadata=unordered, output_dir=tmp_path / "unordered")
    assert order_error.value.code is QaErrorCode.PHYSICAL_ORDER_REQUIRED
    assert str(order_error.value) == QaErrorCode.PHYSICAL_ORDER_REQUIRED.value
    assert order_error.value.__cause__ is None

    with pytest.raises(QaRenderError) as selection_error:
        render_private_qa(
            source,
            source,
            metadata=_metadata(),
            output_dir=tmp_path / "selection",
            contact_slice_indices=(0, 5, 5),
        )
    assert selection_error.value.code is QaErrorCode.INVALID_CONTACT_SELECTION
    assert str(selection_error.value) == QaErrorCode.INVALID_CONTACT_SELECTION.value


def test_review_schema_is_fixed_enum_only() -> None:
    schema = review_ledger_schema()

    assert schema == {
        "check_enum": [item.value for item in ReviewCheck],
        "decision_enum": [item.value for item in ReviewDecision],
        "fields": ["case_ordinal", "series_ordinal", "status", "checks"],
        "schema_version": REVIEW_LEDGER_SCHEMA_VERSION,
        "status_enum": [item.value for item in ReviewStatus],
    }
    assert "notes" not in schema["fields"]
