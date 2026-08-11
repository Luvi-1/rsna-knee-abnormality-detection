"""Versioned, deterministic private-cohort coverage planning.

Inputs and the detailed ledger stay inside the private Kaggle boundary.  This module emits no
logs and raises only fixed error codes, so study keys, stratum values, and prevalence cannot leak
through diagnostics.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from fractions import Fraction
from heapq import heapify, heappop, heappush
from typing import Final

QA_STRATUM_REGISTRY_VERSION: Final = "qa-stratum-registry-v1"
QA_COHORT_SELECTOR_VERSION: Final = "qa-cohort-selection-v3"
MISSING_VALUE: Final = "missing"
RARE_POPULATION_MAX: Final = 2


class QAStrataError(RuntimeError):
    """A stable, disclosure-safe cohort-planning failure."""


class DimensionKind(StrEnum):
    """Policy class used for weighting and private-ledger reasons."""

    CATEGORICAL = "categorical"
    STATE = "state"
    EXTREME = "extreme"
    QUALITY = "quality"
    EDGE_CASE = "edge_case"


@dataclass(frozen=True, order=True, slots=True)
class Stratum:
    """One normalized private membership token."""

    dimension: str
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.dimension or not self.value or "\n" in self.dimension or "\n" in self.value:
            raise QAStrataError("qa_stratum_token_invalid")


@dataclass(frozen=True, slots=True)
class DimensionRule:
    """Declarative rule for every represented value in one QA dimension."""

    dimension: str
    kind: DimensionKind
    weight: int
    represented_quota: int = 2
    require_explicit_value: bool = True

    def __post_init__(self) -> None:
        if (
            not self.dimension
            or "\n" in self.dimension
            or self.weight < 1
            or self.represented_quota < 1
        ):
            raise QAStrataError("qa_stratum_rule_invalid")


# Every observed value is mandatory.  Upstream code must bucket continuous values and represent
# missing scalar evidence with ``MISSING_VALUE`` rather than omitting the dimension.
QA_STRATUM_REGISTRY: Final[tuple[DimensionRule, ...]] = (
    DimensionRule("laterality", DimensionKind.CATEGORICAL, 6),
    DimensionRule("organizer_plane", DimensionKind.CATEGORICAL, 5),
    DimensionRule("physical_plane", DimensionKind.CATEGORICAL, 5),
    DimensionRule("organizer_physical_plane_relation", DimensionKind.STATE, 6),
    DimensionRule("assigned_diagnostic_slot", DimensionKind.CATEGORICAL, 5),
    DimensionRule("additional_diagnostic_series", DimensionKind.STATE, 4),
    DimensionRule("multiple_series_per_slot", DimensionKind.STATE, 4),
    DimensionRule("missing_diagnostic_slot", DimensionKind.STATE, 5),
    DimensionRule("retained_nonduplicate_abnormal_series", DimensionKind.STATE, 5),
    DimensionRule("duplicate_handling", DimensionKind.STATE, 5),
    DimensionRule("bit_depth_category", DimensionKind.CATEGORICAL, 4),
    DimensionRule("photometric_interpretation", DimensionKind.CATEGORICAL, 5),
    DimensionRule("transfer_syntax", DimensionKind.CATEGORICAL, 5),
    DimensionRule("slice_thickness_stratum", DimensionKind.EXTREME, 4),
    DimensionRule("slice_spacing_stratum", DimensionKind.EXTREME, 4),
    DimensionRule("resolution_extreme", DimensionKind.EXTREME, 4),
    DimensionRule("slice_count_extreme", DimensionKind.EXTREME, 4),
    DimensionRule("scanner_manufacturer", DimensionKind.CATEGORICAL, 3),
    DimensionRule("scanner_model", DimensionKind.CATEGORICAL, 3),
    DimensionRule("field_strength", DimensionKind.CATEGORICAL, 4),
    DimensionRule("site_domain_cluster", DimensionKind.CATEGORICAL, 4),
    DimensionRule("source_manifest_quality_flag", DimensionKind.QUALITY, 5),
    DimensionRule("terminal_state", DimensionKind.QUALITY, 6),
    DimensionRule("pipeline_case", DimensionKind.QUALITY, 5),
    DimensionRule("dicom_edge_case_subtype", DimensionKind.EDGE_CASE, 6),
)


@dataclass(frozen=True, slots=True)
class StudyStrata:
    """Opaque study key and its normalized, private stratum memberships."""

    study_key: str = field(repr=False)
    memberships: frozenset[Stratum] = field(repr=False)

    def __post_init__(self) -> None:
        if not self.study_key or "\n" in self.study_key:
            raise QAStrataError("qa_study_key_invalid")


@dataclass(frozen=True, slots=True)
class CoverageRow:
    """One row in the detailed private coverage ledger."""

    dimension: str
    value: str = field(repr=False)
    represented: bool
    population: int
    required_quota: int
    selected: int
    quota_met: bool
    reason: str
    selector_version: str


@dataclass(frozen=True, slots=True)
class CoverageLedger:
    """Detailed private evidence used to fail review planning closed."""

    rows: tuple[CoverageRow, ...] = field(repr=False)
    total_required_strata: int
    total_satisfied: int
    unsatisfied_strata: tuple[Stratum, ...] = field(repr=False)
    cohort_size: int
    all_required_represented_registry_values_satisfy_quotas: bool
    registry_version: str
    selector_version: str
    manifest_version: str


@dataclass(frozen=True, slots=True)
class CohortSelection:
    """Frozen private cohort plus authenticated aggregate coverage evidence."""

    selected_study_keys: tuple[str, ...] = field(repr=False)
    coverage: CoverageLedger = field(repr=False)
    cohort_sha256: str


def coverage_ledger(
    studies: Sequence[StudyStrata],
    selected_study_keys: Sequence[str],
    *,
    manifest_version: str,
    registry: Sequence[DimensionRule] = QA_STRATUM_REGISTRY,
    selector_version: str = QA_COHORT_SELECTOR_VERSION,
) -> CoverageLedger:
    """Audit an arbitrary selected cohort against every represented mandatory value."""

    rules = _validated_rules(registry)
    by_key = _validated_studies(studies, rules)
    selected = frozenset(selected_study_keys)
    if (
        not manifest_version
        or not selector_version
        or len(selected) != len(selected_study_keys)
        or not selected.issubset(by_key)
    ):
        raise QAStrataError("qa_coverage_identity_invalid")

    population = _population_members(studies)
    selected_counts = {
        stratum: sum(stratum in by_key[key].memberships for key in selected)
        for stratum in population
    }
    rows = tuple(
        CoverageRow(
            dimension=stratum.dimension,
            value=stratum.value,
            represented=True,
            population=len(members),
            required_quota=min(rules[stratum.dimension].represented_quota, len(members)),
            selected=selected_counts[stratum],
            quota_met=(
                selected_counts[stratum]
                >= min(rules[stratum.dimension].represented_quota, len(members))
            ),
            reason=_selection_reason(stratum, len(members), rules[stratum.dimension]),
            selector_version=selector_version,
        )
        for stratum, members in sorted(population.items())
    )
    unsatisfied = tuple(Stratum(row.dimension, row.value) for row in rows if not row.quota_met)
    satisfied = len(rows) - len(unsatisfied)
    return CoverageLedger(
        rows=rows,
        total_required_strata=len(rows),
        total_satisfied=satisfied,
        unsatisfied_strata=unsatisfied,
        cohort_size=len(selected),
        all_required_represented_registry_values_satisfy_quotas=bool(rows) and not unsatisfied,
        registry_version=QA_STRATUM_REGISTRY_VERSION,
        selector_version=selector_version,
        manifest_version=manifest_version,
    )


def require_complete_coverage(ledger: CoverageLedger) -> None:
    """Reject incomplete coverage without including private stratum details in the error."""

    if (
        not ledger.all_required_represented_registry_values_satisfy_quotas
        or ledger.unsatisfied_strata
    ):
        raise QAStrataError("qa_registry_coverage_incomplete")


def registry_sha256(registry: Sequence[DimensionRule] = QA_STRATUM_REGISTRY) -> str:
    """Return the canonical declarative-registry identity."""

    return hashlib.sha256(
        json.dumps(
            {
                "registry_version": QA_STRATUM_REGISTRY_VERSION,
                "rules": [
                    {
                        "dimension": rule.dimension,
                        "kind": rule.kind.value,
                        "weight": rule.weight,
                        "represented_quota": rule.represented_quota,
                        "require_explicit_value": rule.require_explicit_value,
                    }
                    for rule in registry
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def select_qa_cohort(
    studies: Sequence[StudyStrata],
    *,
    minimum_size: int,
    manifest_version: str,
    registry: Sequence[DimensionRule] = QA_STRATUM_REGISTRY,
    selector_version: str = QA_COHORT_SELECTOR_VERSION,
) -> CohortSelection:
    """Select all mandatory coverage first, then deterministically fill to the minimum size."""

    rules = _validated_rules(registry)
    by_key = _validated_studies(studies, rules)
    if minimum_size < 1 or len(by_key) < minimum_size or not manifest_version:
        raise QAStrataError("qa_selection_population_too_small")

    population = _population_members(studies)
    if not population:
        raise QAStrataError("qa_strata_not_represented")
    quota = {
        stratum: min(rules[stratum.dimension].represented_quota, len(members))
        for stratum, members in population.items()
    }
    counts = dict.fromkeys(population, 0)
    selected: set[str] = set()
    scores = {
        study.study_key: _coverage_score(study, counts, quota, population, rules)
        for study in studies
    }
    candidates = [(-score, study_key) for study_key, score in scores.items()]
    heapify(candidates)
    unsatisfied = len(quota)

    while unsatisfied:
        while candidates:
            negative_score, study_key = heappop(candidates)
            if study_key not in selected and negative_score == -scores[study_key]:
                break
        else:
            raise QAStrataError("qa_registry_coverage_impossible")
        if scores[study_key] <= 0:
            raise QAStrataError("qa_registry_coverage_impossible")
        chosen = by_key[study_key]
        newly_satisfied = tuple(
            item for item in chosen.memberships if counts[item] + 1 == quota[item]
        )
        _add_study(chosen, selected, counts)
        unsatisfied -= len(newly_satisfied)

        score_decrements: defaultdict[str, Fraction] = defaultdict(Fraction)
        for item in newly_satisfied:
            contribution = Fraction(rules[item.dimension].weight, len(population[item]))
            for member in population[item]:
                if member not in selected:
                    score_decrements[member] += contribution
        for member, decrement in score_decrements.items():
            scores[member] -= decrement
            heappush(candidates, (-scores[member], member))

    while len(selected) < minimum_size:
        remaining = [study for study in studies if study.study_key not in selected]
        if not remaining:
            raise QAStrataError("qa_selection_population_too_small")
        chosen = min(
            remaining,
            key=lambda study: (-_balance_score(study, counts, population, rules), study.study_key),
        )
        _add_study(chosen, selected, counts)

    selected_keys = tuple(sorted(selected))
    ledger = coverage_ledger(
        studies,
        selected_keys,
        manifest_version=manifest_version,
        registry=registry,
        selector_version=selector_version,
    )
    require_complete_coverage(ledger)
    return CohortSelection(
        selected_study_keys=selected_keys,
        coverage=ledger,
        cohort_sha256=_cohort_sha256(
            by_key,
            selected_keys,
            manifest_version=manifest_version,
            registry=registry,
            selector_version=selector_version,
        ),
    )


def _validated_rules(registry: Sequence[DimensionRule]) -> dict[str, DimensionRule]:
    rules = {rule.dimension: rule for rule in registry}
    if not rules or len(rules) != len(registry):
        raise QAStrataError("qa_stratum_registry_invalid")
    return rules


def _validated_studies(
    studies: Sequence[StudyStrata], rules: dict[str, DimensionRule]
) -> dict[str, StudyStrata]:
    by_key = {study.study_key: study for study in studies}
    if not studies or len(by_key) != len(studies):
        raise QAStrataError("qa_study_population_invalid")
    required_dimensions = {
        dimension for dimension, rule in rules.items() if rule.require_explicit_value
    }
    for study in studies:
        dimensions = {item.dimension for item in study.memberships}
        if not dimensions.issubset(rules):
            raise QAStrataError("qa_stratum_dimension_unregistered")
        if not required_dimensions.issubset(dimensions):
            raise QAStrataError("qa_stratum_explicit_state_missing")
    return by_key


def _population_members(studies: Sequence[StudyStrata]) -> dict[Stratum, set[str]]:
    members: dict[Stratum, set[str]] = {}
    for study in studies:
        for stratum in study.memberships:
            members.setdefault(stratum, set()).add(study.study_key)
    return members


def _coverage_score(
    study: StudyStrata,
    counts: dict[Stratum, int],
    quota: dict[Stratum, int],
    population: dict[Stratum, set[str]],
    rules: dict[str, DimensionRule],
) -> Fraction:
    return sum(
        (
            Fraction(rules[item.dimension].weight, len(population[item]))
            for item in study.memberships
            if counts[item] < quota[item]
        ),
        start=Fraction(),
    )


def _balance_score(
    study: StudyStrata,
    counts: dict[Stratum, int],
    population: dict[Stratum, set[str]],
    rules: dict[str, DimensionRule],
) -> Fraction:
    return sum(
        (
            Fraction(
                rules[item.dimension].weight,
                len(population[item]) * (counts[item] + 1),
            )
            for item in study.memberships
        ),
        start=Fraction(),
    )


def _add_study(study: StudyStrata, selected: set[str], counts: dict[Stratum, int]) -> None:
    selected.add(study.study_key)
    for item in study.memberships:
        counts[item] += 1


def _selection_reason(stratum: Stratum, population: int, rule: DimensionRule) -> str:
    if stratum.value == MISSING_VALUE:
        return "mandatory_represented_missing"
    if population == 1:
        return "mandatory_represented_singleton"
    if population <= RARE_POPULATION_MAX:
        return "mandatory_represented_rare"
    return f"mandatory_represented_{rule.kind.value}"


def _cohort_sha256(
    studies: dict[str, StudyStrata],
    selected_keys: tuple[str, ...],
    *,
    manifest_version: str,
    registry: Sequence[DimensionRule],
    selector_version: str,
) -> str:
    payload = {
        "domain": "rsna-knee-private-qa-cohort-v2",
        "manifest_version": manifest_version,
        "registry_version": QA_STRATUM_REGISTRY_VERSION,
        "registry_sha256": registry_sha256(registry),
        "selector_version": selector_version,
        "studies": [
            {
                "study_key": key,
                "strata": [
                    [item.dimension, item.value] for item in sorted(studies[key].memberships)
                ],
            }
            for key in selected_keys
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
