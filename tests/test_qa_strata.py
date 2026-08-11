from __future__ import annotations

from fractions import Fraction
from itertools import chain

import pytest

from rsna_knee.data import qa_strata as qa_strata_module
from rsna_knee.data.qa_strata import (
    MISSING_VALUE,
    QA_STRATUM_REGISTRY,
    CohortSelection,
    DimensionKind,
    DimensionRule,
    QAStrataError,
    Stratum,
    StudyStrata,
    coverage_ledger,
    require_complete_coverage,
    select_qa_cohort,
)


def _study(number: int, *memberships: tuple[str, str]) -> StudyStrata:
    return StudyStrata(
        study_key=f"{number:064x}",
        memberships=frozenset(Stratum(*item) for item in memberships),
    )


def _rule(
    dimension: str,
    *,
    quota: int = 1,
    explicit: bool = True,
) -> DimensionRule:
    return DimensionRule(
        dimension,
        DimensionKind.CATEGORICAL,
        weight=1,
        represented_quota=quota,
        require_explicit_value=explicit,
    )


def _select(
    studies: tuple[StudyStrata, ...],
    *,
    minimum_size: int,
    registry: tuple[DimensionRule, ...],
    manifest_version: str = "manifest-v1",
    selector_version: str = "selector-v1",
) -> CohortSelection:
    return select_qa_cohort(
        studies,
        minimum_size=minimum_size,
        manifest_version=manifest_version,
        registry=registry,
        selector_version=selector_version,
    )


def _slow_reference_selected_keys(
    studies: tuple[StudyStrata, ...],
    *,
    minimum_size: int,
    registry: tuple[DimensionRule, ...],
) -> tuple[str, ...]:
    """Recompute every score exactly as selector v3 did before the incremental optimization."""

    rules = {rule.dimension: rule for rule in registry}
    population: dict[Stratum, set[str]] = {}
    for study in studies:
        for item in study.memberships:
            population.setdefault(item, set()).add(study.study_key)
    quota = {
        item: min(rules[item.dimension].represented_quota, len(members))
        for item, members in population.items()
    }
    counts = dict.fromkeys(population, 0)
    selected: set[str] = set()

    def add(study: StudyStrata) -> None:
        selected.add(study.study_key)
        for item in study.memberships:
            counts[item] += 1

    while any(counts[item] < required for item, required in quota.items()):
        candidates = [
            study
            for study in studies
            if study.study_key not in selected
            and any(counts[item] < quota[item] for item in study.memberships)
        ]
        chosen = min(
            candidates,
            key=lambda study: (
                -sum(
                    (
                        Fraction(rules[item.dimension].weight, len(population[item]))
                        for item in study.memberships
                        if counts[item] < quota[item]
                    ),
                    start=Fraction(),
                ),
                study.study_key,
            ),
        )
        add(chosen)

    while len(selected) < minimum_size:
        remaining = [study for study in studies if study.study_key not in selected]
        chosen = min(
            remaining,
            key=lambda study: (
                -sum(
                    (
                        Fraction(
                            rules[item.dimension].weight,
                            len(population[item]) * (counts[item] + 1),
                        )
                        for item in study.memberships
                    ),
                    start=Fraction(),
                ),
                study.study_key,
            ),
        )
        add(chosen)
    return tuple(sorted(selected))


def test_registry_declares_every_required_dimension_and_explicit_missing_state() -> None:
    dimensions = {rule.dimension for rule in QA_STRATUM_REGISTRY}
    assert dimensions == {
        "additional_diagnostic_series",
        "assigned_diagnostic_slot",
        "bit_depth_category",
        "dicom_edge_case_subtype",
        "duplicate_handling",
        "field_strength",
        "laterality",
        "missing_diagnostic_slot",
        "multiple_series_per_slot",
        "organizer_physical_plane_relation",
        "organizer_plane",
        "photometric_interpretation",
        "physical_plane",
        "pipeline_case",
        "resolution_extreme",
        "retained_nonduplicate_abnormal_series",
        "scanner_manufacturer",
        "scanner_model",
        "site_domain_cluster",
        "slice_count_extreme",
        "slice_spacing_stratum",
        "slice_thickness_stratum",
        "source_manifest_quality_flag",
        "terminal_state",
        "transfer_syntax",
    }
    assert all(rule.require_explicit_value for rule in QA_STRATUM_REGISTRY)
    assert qa_strata_module.registry_sha256() == (
        "13829b49acec7ed2a3cb83cc862caaf3"  # pragma: allowlist secret
        "251ecbab9f1b11eca4061c0c9ae5acf3"  # pragma: allowlist secret
    )
    assert MISSING_VALUE == "missing"


def test_121_study_selection_is_deterministic_and_includes_right_singleton() -> None:
    registry = (_rule("laterality", quota=2),)
    studies = tuple(
        _study(number, ("laterality", "right" if number == 120 else "left"))
        for number in range(121)
    )

    first = _select(studies, minimum_size=120, registry=registry)
    second = _select(tuple(reversed(studies)), minimum_size=120, registry=registry)

    assert first.selected_study_keys == second.selected_study_keys
    assert first.cohort_sha256 == second.cohort_sha256
    assert f"{120:064x}" in first.selected_study_keys
    assert first.coverage.all_required_represented_registry_values_satisfy_quotas
    assert first.coverage.total_required_strata == 2
    assert first.coverage.total_satisfied == 2


@pytest.mark.parametrize(
    ("dimension", "rare_value", "common_value"),
    (
        ("laterality", "left", "right"),
        ("laterality", "right", "left"),
        ("laterality", "missing", "left"),
        ("organizer_plane", "axial", "sagittal"),
        ("physical_plane", "oblique", "sagittal"),
        ("organizer_physical_plane_relation", "conflict", "agreement"),
        ("multiple_series_per_slot", "present", "absent"),
        ("missing_diagnostic_slot", "present", "absent"),
        ("duplicate_handling", "duplicate_slot", "none"),
        ("transfer_syntax", "jpeg2000", "uncompressed_little_endian"),
        ("photometric_interpretation", "monochrome1", "monochrome2"),
        ("bit_depth_category", "other", "le_12"),
        ("slice_thickness_stratum", "gt_5", "le_3"),
        ("slice_spacing_stratum", "gt_5", "le_3"),
        ("resolution_extreme", "gt_512", "le_512"),
        ("slice_count_extreme", "one", "thirty_three_to_sixty_four"),
        ("terminal_state", "quality_blocked", "model_eligible"),
        ("scanner_manufacturer", "missing", "vendor_a"),
        ("scanner_model", "missing", "model_a"),
        ("field_strength", "missing", "le_3"),
        ("site_domain_cluster", "missing", "domain_a"),
        ("assigned_diagnostic_slot", "axial_structural", "sagittal_structural"),
        ("additional_diagnostic_series", "present", "absent"),
        ("retained_nonduplicate_abnormal_series", "present", "absent"),
        ("source_manifest_quality_flag", "remediated", "none"),
        ("pipeline_case", "recoverable", "clean"),
        ("dicom_edge_case_subtype", "orientation_oblique_sagittal", "none"),
        ("dicom_edge_case_subtype", "orientation_malformed", "none"),
        ("dicom_edge_case_subtype", "transfer_jpeg2000", "none"),
        ("dicom_edge_case_subtype", "photometric_monochrome1", "none"),
        ("dicom_edge_case_subtype", "bit_depth_other", "none"),
        ("dicom_edge_case_subtype", "quality_duplicate_slices", "none"),
        ("dicom_edge_case_subtype", "terminal_quality_blocked", "none"),
        ("dicom_edge_case_subtype", "remediated_decode_case", "none"),
    ),
)
def test_each_required_singleton_or_missing_value_is_mandatory(
    dimension: str,
    rare_value: str,
    common_value: str,
) -> None:
    registry = (_rule(dimension, quota=2),)
    rare = _study(100, (dimension, rare_value))
    studies = tuple([*(_study(number, (dimension, common_value)) for number in range(100)), rare])

    result = _select(studies, minimum_size=100, registry=registry)

    assert rare.study_key in result.selected_study_keys
    row = next(item for item in result.coverage.rows if item.value == rare_value)
    assert row.required_quota == 1
    assert row.selected == 1
    assert row.quota_met


def test_weighted_greedy_prefers_one_study_covering_multiple_mandatory_strata() -> None:
    registry = (_rule("plane", explicit=False), _rule("edge", explicit=False))
    shared = _study(1, ("plane", "conflict"), ("edge", "jpeg2000"))
    studies = (
        shared,
        _study(2, ("plane", "conflict")),
        _study(3, ("edge", "jpeg2000")),
    )

    result = _select(studies, minimum_size=1, registry=registry)

    assert result.selected_study_keys == (shared.study_key,)
    assert result.coverage.cohort_size == 1


def test_incremental_selector_matches_slow_reference_across_quota_transitions() -> None:
    registry = (
        DimensionRule("plane", DimensionKind.CATEGORICAL, weight=7, represented_quota=2),
        DimensionRule("site", DimensionKind.CATEGORICAL, weight=3, represented_quota=2),
        DimensionRule("edge", DimensionKind.EDGE_CASE, weight=11, represented_quota=2),
    )
    studies = tuple(
        _study(
            number,
            ("plane", ("axial", "coronal", "sagittal")[number % 3]),
            ("site", f"site-{number % 13:02d}"),
            (
                "edge",
                "singleton"
                if number == 71
                else "missing"
                if number in {5, 17}
                else f"common-{number % 4}",
            ),
        )
        for number in range(72)
    )

    result = _select(studies, minimum_size=28, registry=registry)

    assert result.selected_study_keys == _slow_reference_selected_keys(
        studies, minimum_size=28, registry=registry
    )


def test_incremental_selector_is_permutation_invariant() -> None:
    registry = (
        DimensionRule("plane", DimensionKind.CATEGORICAL, weight=5, represented_quota=2),
        DimensionRule("site", DimensionKind.CATEGORICAL, weight=3, represented_quota=2),
    )
    studies = tuple(
        _study(
            number,
            ("plane", ("axial", "coronal", "sagittal")[number % 3]),
            ("site", f"site-{number % 9:02d}"),
        )
        for number in range(54)
    )
    baseline = _select(studies, minimum_size=24, registry=registry)
    permutations = (
        tuple(reversed(studies)),
        studies[::2] + studies[1::2],
        studies[::3] + studies[1::3] + studies[2::3],
    )

    for permuted in permutations:
        result = _select(permuted, minimum_size=24, registry=registry)
        assert result.selected_study_keys == baseline.selected_study_keys
        assert result.cohort_sha256 == baseline.cohort_sha256


def test_mandatory_represented_strata_grow_beyond_240_and_score_each_study_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = (_rule("dicom_edge_case_subtype"),)
    original = qa_strata_module._coverage_score
    calls = 0

    def counted_score(
        study: StudyStrata,
        counts: dict[Stratum, int],
        quota: dict[Stratum, int],
        population: dict[Stratum, set[str]],
        rules: dict[str, DimensionRule],
    ) -> Fraction:
        nonlocal calls
        calls += 1
        return original(study, counts, quota, population, rules)

    monkeypatch.setattr(qa_strata_module, "_coverage_score", counted_score)
    studies = tuple(
        _study(number, ("dicom_edge_case_subtype", f"edge-{number:03d}")) for number in range(301)
    )

    result = _select(studies, minimum_size=100, registry=registry)

    assert len(result.selected_study_keys) == 301
    assert result.coverage.cohort_size == 301
    assert result.coverage.total_required_strata == 301
    assert not result.coverage.unsatisfied_strata
    assert calls == len(studies)


def test_private_ledger_exposes_incomplete_coverage_and_gate_fails_closed() -> None:
    registry = (_rule("laterality"),)
    left = _study(1, ("laterality", "left"))
    right = _study(2, ("laterality", "right"))

    ledger = coverage_ledger(
        (left, right),
        (left.study_key,),
        manifest_version="manifest-v1",
        registry=registry,
        selector_version="selector-v1",
    )

    assert not ledger.all_required_represented_registry_values_satisfy_quotas
    assert ledger.total_required_strata == 2
    assert ledger.total_satisfied == 1
    assert ledger.unsatisfied_strata == (Stratum("laterality", "right"),)
    with pytest.raises(QAStrataError, match="^qa_registry_coverage_incomplete$"):
        require_complete_coverage(ledger)


def test_missing_values_are_mandatory_and_cannot_be_silently_omitted() -> None:
    registry = (_rule("scanner_manufacturer"),)
    represented_missing = _study(1, ("scanner_manufacturer", MISSING_VALUE))
    normal = _study(2, ("scanner_manufacturer", "vendor-a"))
    result = _select((represented_missing, normal), minimum_size=1, registry=registry)
    missing_row = next(row for row in result.coverage.rows if row.value == MISSING_VALUE)

    assert represented_missing.study_key in result.selected_study_keys
    assert missing_row.reason == "mandatory_represented_missing"
    with pytest.raises(QAStrataError, match="^qa_stratum_explicit_state_missing$"):
        _select((_study(3),), minimum_size=1, registry=registry)


def test_manifest_and_selector_versions_change_cohort_identity() -> None:
    registry = (_rule("laterality"),)
    studies = (_study(1, ("laterality", "left")),)

    base = _select(studies, minimum_size=1, registry=registry)
    new_manifest = _select(
        studies,
        minimum_size=1,
        registry=registry,
        manifest_version="manifest-v2",
    )
    new_selector = _select(
        studies,
        minimum_size=1,
        registry=registry,
        selector_version="selector-v2",
    )

    assert len({base.cohort_sha256, new_manifest.cohort_sha256, new_selector.cohort_sha256}) == 3


def test_every_ledger_row_has_the_versioned_required_schema() -> None:
    registry = (_rule("state", quota=2),)
    studies = tuple(
        chain(
            (_study(1, ("state", "singleton")),),
            (_study(number, ("state", "common")) for number in range(2, 5)),
        )
    )

    result = _select(studies, minimum_size=2, registry=registry)

    assert result.coverage.selector_version == "selector-v1"
    assert all(row.represented for row in result.coverage.rows)
    assert all(row.required_quota in {1, 2} for row in result.coverage.rows)
    assert all(row.quota_met for row in result.coverage.rows)
    assert {row.reason for row in result.coverage.rows} == {
        "mandatory_represented_categorical",
        "mandatory_represented_singleton",
    }
