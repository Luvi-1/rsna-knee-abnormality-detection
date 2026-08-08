from __future__ import annotations

import csv
import json
import random
import sqlite3
from itertools import combinations
from pathlib import Path

import pytest

import rsna_knee.data.manifest as manifest_module
from rsna_knee.data.manifest import (
    ManifestAuditError,
    ReportFeatures,
    SeriesEvidence,
    SourceInventory,
    StudySource,
    _augment_source_inventory,
    _candidate_overflow_aggregate_fields,
    _dicom_issue_disposition_status,
    _exact_report_pair_counts,
    _finalize_report_template_components,
    _insert_issue,
    _label_copy_candidates_within_components,
    _near_series_edges,
    _near_slice_edges,
    _persist_altered_metadata_edges,
    _persist_exact_groups,
    _protected_components,
    _report_edges,
    _threshold_complete_entity_pairs,
    initialize_private_database,
    insert_source_placeholders,
    read_source_inventory,
    threshold_complete_hamming_pairs,
)
from rsna_knee.dicom.audit import (
    DECODE_ROOT_CAUSE_VERSION,
    DICOM_ISSUE_RESOLUTION_VERSION,
    DecodeRootCause,
    DicomResolutionState,
)
from rsna_knee.qa.duplicates import (
    DuplicateEdge,
    EdgeDisposition,
    build_candidate_components,
    build_protected_components,
)

ROOT = Path(__file__).parents[1]


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _insert_study(connection: sqlite3.Connection, study_key: str) -> None:
    connection.execute(
        """INSERT INTO study_manifest(
            study_key, split, source_row_count, patient_key_evidence, series_count,
            plane_availability, sequence_categories, total_slice_count, report_available,
            label_status, known_label_count, positive_label_count, negative_label_count,
            data_quality_flags, terminal_state) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (study_key, "train", 1, "missing", 1, "[]", "[]", 1, 0, "unlabeled", 0, 0, 0, "[]", "pass"),
    )


def _insert_series(connection: sqlite3.Connection, series_key: str, study_key: str) -> None:
    connection.execute(
        """INSERT INTO series_manifest(
            series_key, study_key, source_row_count, slice_count, missing_tag_flags,
            quality_score, localizer_likelihood, ordering_method, orientation_state,
            spacing_state, decode_state, near_fingerprint_version, terminal_state)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            series_key,
            study_key,
            1,
            1,
            "[]",
            100,
            0.0,
            "geometry",
            "valid",
            "valid",
            "pass",
            "phash-sequence-v1",
            "pass",
        ),
    )


def _insert_slice(
    connection: sqlite3.Connection,
    file_key: str,
    study_key: str,
    series_key: str,
    fingerprint: str,
    *,
    raw_key: str | None = None,
    decoded_key: str | None = None,
    position: str | None = None,
) -> None:
    connection.execute(
        """INSERT INTO slice_file_manifest(
            file_key, study_key, series_key, file_size_bytes, rows, columns,
            raw_file_exact_key, decoded_pixel_exact_key, near_slice_fingerprint,
            image_position_patient, decode_state, missing_tag_flags, terminal_state)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            file_key,
            study_key,
            series_key,
            1,
            8,
            8,
            raw_key,
            decoded_key,
            fingerprint,
            position,
            "pass",
            "[]",
            "pass",
        ),
    )


def test_hard_groups_and_soft_candidate_clusters_are_persisted_separately(
    tmp_path: Path,
) -> None:
    connection = initialize_private_database(tmp_path / "components.sqlite3", {})
    try:
        for suffix in ("a", "b", "c", "d"):
            study_key = f"study-{suffix}"
            series_key = f"series-{suffix}"
            _insert_study(connection, study_key)
            _insert_series(connection, series_key, study_key)
            _insert_slice(connection, f"file-{suffix}", study_key, series_key, suffix * 16)
        edges = [
            DuplicateEdge("study-a", "study-b", "exact-study", EdgeDisposition.HARD),
            DuplicateEdge("study-b", "study-c", "same-patient", EdgeDisposition.HARD),
            DuplicateEdge("study-c", "study-d", "near-report", EdgeDisposition.CANDIDATE),
        ]

        hard_components, crossings = _protected_components(connection, edges, b"p" * 32)

        assert crossings == 0
        assert hard_components["study-a"] == hard_components["study-b"]
        assert hard_components["study-b"] == hard_components["study-c"]
        assert hard_components["study-c"] != hard_components["study-d"]
        assert connection.execute(
            "SELECT COUNT(DISTINCT component_key),COUNT(*) FROM protected_component"
        ).fetchone() == (2, 4)
        assert connection.execute(
            """SELECT COUNT(DISTINCT component_key),COUNT(DISTINCT hard_component_key),COUNT(*)
                FROM candidate_component"""
        ).fetchone() == (1, 2, 4)
        assert connection.execute(
            """SELECT component_kind,member_count,hard_edge_count,candidate_edge_count
                FROM duplicate_component_summary
                ORDER BY component_kind,member_count"""
        ).fetchall() == [
            ("hard-protected", 1, 0, 0),
            ("hard-protected", 3, 2, 0),
            ("legacy-v1-all-evidence", 4, 2, 1),
            ("soft-candidate", 4, 2, 1),
        ]
        assert connection.execute(
            """SELECT edge_kind,decision,evidence_count,
                    left_hard_component_key=right_hard_component_key,
                    soft_component_key IS NOT NULL
                FROM duplicate_component_edge ORDER BY edge_kind"""
        ).fetchall() == [
            ("exact-study", "hard", 1, 1, 1),
            ("near-report", "candidate", 1, 0, 1),
            ("same-patient", "hard", 1, 1, 1),
        ]
        assert connection.execute(
            """SELECT COUNT(*) FROM duplicate_component_summary
                WHERE representative_file_key IS NOT NULL"""
        ).fetchone() == (4,)
    finally:
        connection.close()


def test_private_largest_component_review_validates_paths_and_edge_attribution(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    secret = b"r" * 32
    connection = initialize_private_database(tmp_path / "review.sqlite3", {})
    paths_by_file: dict[str, str] = {}
    try:
        for suffix in ("a", "b", "c"):
            relative_path = f"train_series/study-{suffix}/series-{suffix}/slice.dcm"
            path = input_root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic")
            file_key = manifest_module.opaque_key(secret, "file", relative_path)
            paths_by_file[file_key] = relative_path
            _insert_study(connection, f"study-{suffix}")
            _insert_series(connection, f"series-{suffix}", f"study-{suffix}")
            _insert_slice(
                connection,
                file_key,
                f"study-{suffix}",
                f"series-{suffix}",
                suffix * 16,
            )
        edges = [
            DuplicateEdge("study-a", "study-b", "same-patient", EdgeDisposition.HARD),
            DuplicateEdge("study-b", "study-c", "near-report", EdgeDisposition.CANDIDATE),
        ]

        _protected_components(
            connection,
            edges,
            secret,
            representative_paths=paths_by_file,
            input_root=input_root,
        )

        private_run = dict(connection.execute("SELECT key,value FROM manifest_run"))
        assert private_run["grouping_representative_review_status"] == "complete"
        assert private_run["grouping_representative_review_version"] == "component-review-v1"
        hard_distribution = json.loads(private_run["component_distribution:hard-protected"])
        assert hard_distribution == {
            "algorithm_version": "protected-groups-v2",
            "component_count": 2,
            "corpus_study_count": 3,
            "largest_component_study_proportion": pytest.approx(2 / 3),
            "member_count_max": 2,
            "member_count_median": 1.5,
            "member_count_min": 1,
            "member_count_p90": 2,
            "member_count_p95": 2,
            "member_count_p99": 2,
            "study_count": 3,
            "top_component_study_count": 3,
            "top_component_study_proportion": 1.0,
            "top_component_target_limit": 5,
        }
        hard_targets = json.loads(private_run["largest_component_review_targets:hard-protected"])
        assert hard_targets[0]["representative_path_verified"] is True
        assert hard_targets[0]["connectivity_verified"] is True
        assert hard_targets[0]["study_proportion"] == pytest.approx(2 / 3)
        assert hard_targets[0]["transitive_edge_path"] == [
            {
                "decision": "hard",
                "edge_kind": "same-patient",
                "evidence_count": 1,
                "left_study_key": "study-a",
                "right_study_key": "study-b",
            }
        ]
        assert hard_targets[0]["edge_type_attribution"] == [
            {"decision": "hard", "edge_kind": "same-patient", "evidence_count": 1}
        ]
        soft_targets = json.loads(private_run["largest_component_review_targets:soft-candidate"])
        assert any(
            item["decision"] == "candidate" and item["edge_kind"] == "near-report"
            for item in soft_targets[0]["edge_type_attribution"]
        )
        legacy_distribution = json.loads(
            private_run["component_distribution:legacy-v1-all-evidence"]
        )
        assert legacy_distribution["algorithm_version"] == "protected-groups-v1-reconstruction-v1"
        assert legacy_distribution["component_count"] == 1
        assert legacy_distribution["study_count"] == 3
        legacy_targets = json.loads(
            private_run["largest_component_review_targets:legacy-v1-all-evidence"]
        )
        assert [edge["decision"] for edge in legacy_targets[0]["transitive_edge_path"]] == [
            "hard",
            "candidate",
        ]
    finally:
        connection.close()


def test_legacy_v1_distribution_includes_singletons_and_traces_long_weak_chain(
    tmp_path: Path,
) -> None:
    connection = initialize_private_database(tmp_path / "legacy.sqlite3", {})
    try:
        for suffix in ("a", "b", "c", "d", "e"):
            study_key = f"study-{suffix}"
            series_key = f"series-{suffix}"
            _insert_study(connection, study_key)
            _insert_series(connection, series_key, study_key)
            _insert_slice(connection, f"file-{suffix}", study_key, series_key, suffix * 16)
        edges = [
            DuplicateEdge("study-a", "study-b", "near-report", EdgeDisposition.CANDIDATE),
            DuplicateEdge("study-b", "study-c", "near-report", EdgeDisposition.CANDIDATE),
            DuplicateEdge("study-c", "study-d", "near-report", EdgeDisposition.CANDIDATE),
        ]

        hard_components, crossings = _protected_components(connection, edges, b"l" * 32)

        assert crossings == 0
        assert len(set(hard_components.values())) == 5
        assert connection.execute(
            "SELECT COUNT(DISTINCT component_key),COUNT(*) FROM candidate_component"
        ).fetchone() == (1, 4)
        private_run = dict(connection.execute("SELECT key,value FROM manifest_run"))
        legacy_distribution = json.loads(
            private_run["component_distribution:legacy-v1-all-evidence"]
        )
        assert legacy_distribution == {
            "algorithm_version": "protected-groups-v1-reconstruction-v1",
            "component_count": 2,
            "corpus_study_count": 5,
            "largest_component_study_proportion": 0.8,
            "member_count_max": 4,
            "member_count_median": 2.5,
            "member_count_min": 1,
            "member_count_p90": 4,
            "member_count_p95": 4,
            "member_count_p99": 4,
            "study_count": 5,
            "top_component_study_count": 5,
            "top_component_study_proportion": 1.0,
            "top_component_target_limit": 5,
        }
        legacy_targets = json.loads(
            private_run["largest_component_review_targets:legacy-v1-all-evidence"]
        )
        assert [target["member_count"] for target in legacy_targets] == [4, 1]
        assert [target["study_proportion"] for target in legacy_targets] == [0.8, 0.2]
        assert [
            (edge["left_study_key"], edge["right_study_key"], edge["decision"])
            for edge in legacy_targets[0]["transitive_edge_path"]
        ] == [
            ("study-a", "study-b", "candidate"),
            ("study-b", "study-c", "candidate"),
            ("study-c", "study-d", "candidate"),
        ]
        assert legacy_targets[1]["transitive_edge_path"] == []
        soft_distribution = json.loads(private_run["component_distribution:soft-candidate"])
        assert soft_distribution["component_count"] == 1
        assert soft_distribution["study_count"] == 4
        assert soft_distribution["corpus_study_count"] == 5
        assert soft_distribution["largest_component_study_proportion"] == 0.8
    finally:
        connection.close()


def test_manifest_dicom_issue_rows_are_versioned_and_unexplained_fail_closed(
    tmp_path: Path,
) -> None:
    connection = initialize_private_database(tmp_path / "issues.sqlite3", {})
    try:
        _insert_issue(connection, "file", "file-a", "unreadable")
        _insert_issue(connection, "file", "file-b", "path_header_identity_mismatch")
        _insert_issue(
            connection,
            "file",
            "file-c",
            "decode_failure",
            root_cause_category="compressed_source_decode_inconsistency",
            resolution_status="excluded_unusable_source",
            resolution_version="dicom-issue-resolution-v1",
            private_details={
                "stage": "pixel_decode",
                "exception_type": "builtins.ValueError",
            },
        )
        _insert_issue(connection, "series", "series-a", "instance_fallback")
        _insert_issue(connection, "series", "series-b", "empty_series")
        _insert_issue(connection, "series", "series-c", "unexpected_synthetic_issue")

        assert connection.execute(
            """SELECT entity_level,issue_code,severity,terminal_effect,disposition,
                    disposition_version,root_cause_category,root_cause_version,
                    resolution_status,resolution_version,scope_impact,private_details
                FROM manifest_issue ORDER BY entity_level,entity_key"""
        ).fetchall() == [
            (
                "file",
                "unreadable",
                "error",
                "quarantine",
                "file_quarantine",
                "dicom-issue-disposition-v1",
                "unexpected_unexplained",
                "decode-root-cause-v1",
                "unresolved_blocker",
                "dicom-issue-resolution-v1",
                "file_and_parent_series_quarantined",
                "{}",
            ),
            (
                "file",
                "path_header_identity_mismatch",
                "error",
                "quarantine",
                "file_quarantine",
                "manifest-issue-disposition-v1",
                "path_header_identity_mismatch",
                "manifest-issue-disposition-v1",
                "excluded_unusable_source",
                "manifest-issue-disposition-v1",
                "file_and_parent_series_quarantined",
                "{}",
            ),
            (
                "file",
                "decode_failure",
                "error",
                "quarantine",
                "file_quarantine",
                "dicom-issue-disposition-v1",
                "compressed_source_decode_inconsistency",
                "decode-root-cause-v1",
                "excluded_unusable_source",
                "dicom-issue-resolution-v1",
                "file_and_parent_series_quarantined",
                '{"exception_type":"builtins.ValueError","stage":"pixel_decode"}',
            ),
            (
                "series",
                "instance_fallback",
                "warning",
                "quarantine",
                "series_fallback_quarantine",
                "dicom-issue-disposition-v1",
                "instance_fallback",
                "dicom-issue-disposition-v1",
                "excluded_unusable_source",
                "dicom-issue-resolution-v1",
                "series_and_parent_study_quarantined",
                "{}",
            ),
            (
                "series",
                "empty_series",
                "error",
                "quarantine",
                "series_quarantine",
                "dicom-issue-disposition-v1",
                "empty_series",
                "dicom-issue-disposition-v1",
                "excluded_unusable_source",
                "dicom-issue-resolution-v1",
                "series_and_parent_study_quarantined",
                "{}",
            ),
            (
                "series",
                "unexpected_synthetic_issue",
                "error",
                "quarantine",
                "unexplained_quarantine",
                "manifest-issue-disposition-v1",
                "unexpected_unexplained",
                "manifest-issue-disposition-v1",
                "unresolved_blocker",
                "dicom-issue-resolution-v1",
                "file_or_series_quarantined_pending_private_investigation",
                "{}",
            ),
        ]
        assert _dicom_issue_disposition_status(connection) == (2, False)
        connection.execute(
            """DELETE FROM manifest_issue
                WHERE root_cause_category='unexpected_unexplained'"""
        )
        assert _dicom_issue_disposition_status(connection) == (0, True)
    finally:
        connection.close()


def test_recoverable_decoder_failures_block_completion_until_the_issue_is_absent(
    tmp_path: Path,
) -> None:
    connection = initialize_private_database(tmp_path / "decoder-blockers.sqlite3", {})
    try:
        for file_key, root_cause in (
            ("file-decoder", DecodeRootCause.DECODER_UNAVAILABLE.value),
            ("file-syntax", DecodeRootCause.UNSUPPORTED_TRANSFER_SYNTAX.value),
        ):
            _insert_issue(
                connection,
                "file",
                file_key,
                "decode_failure",
                root_cause_category=root_cause,
                root_cause_version=DECODE_ROOT_CAUSE_VERSION,
                resolution_status=DicomResolutionState.UNRESOLVED_BLOCKER.value,
                resolution_version=DICOM_ISSUE_RESOLUTION_VERSION,
            )

        assert _dicom_issue_disposition_status(connection) == (2, False)
        assert connection.execute(
            "SELECT DISTINCT resolution_status FROM manifest_issue"
        ).fetchall() == [(DicomResolutionState.UNRESOLVED_BLOCKER.value,)]

        # A supported/fixed decoder produces no current issue; it is never relabeled
        # as corrupt source data merely to satisfy the completion gate.
        connection.execute("DELETE FROM manifest_issue")
        assert _dicom_issue_disposition_status(connection) == (0, True)
    finally:
        connection.close()


def test_synthesized_sources_never_receive_official_labels(tmp_path: Path) -> None:
    labels = ("label-a", "label-b", "label-c")
    for split in ("train", "test"):
        (tmp_path / f"{split}_series").mkdir()
    _write_csv(
        tmp_path / "train.csv",
        ["StudyInstanceUID", "Report", *labels],
        [["official-study", "report", "1", "", "0"]],
    )
    _write_csv(tmp_path / "test.csv", ["StudyInstanceUID"], [["test-study"]])
    series_header = [
        "StudyInstanceUID",
        "SeriesInstanceUID",
        "Fluid_Sensitive",
        "Fat_Suppression",
        "Anatomical_Plane",
    ]
    _write_csv(
        tmp_path / "train_series.csv",
        series_header,
        [
            ["official-study", "official-series", "true", "true", "sagittal"],
            ["series-only-study", "series-only-series", "true", "false", "coronal"],
        ],
    )
    _write_csv(
        tmp_path / "test_series.csv",
        series_header,
        [["test-study", "test-series", "false", "false", "axial"]],
    )
    orphan = tmp_path / "train_series" / "file-only-study" / "file-only-series"
    orphan.mkdir(parents=True)
    (orphan / "slice.dcm").write_bytes(b"synthetic")

    inventory = read_source_inventory(tmp_path, labels)
    assert len(_augment_source_inventory(tmp_path, inventory, None)) == 1
    connection = initialize_private_database(tmp_path / "manifest.sqlite3", {})
    try:
        insert_source_placeholders(connection, inventory, b"s" * 32)
        assert connection.execute("SELECT COUNT(*) FROM label_source_manifest").fetchone() == (3,)
        assert connection.execute(
            """SELECT COUNT(*) FROM label_source_manifest lm
                JOIN study_manifest sm ON sm.study_key=lm.study_key
                WHERE sm.source_row_count=0"""
        ).fetchone() == (0,)
    finally:
        connection.close()


def test_threshold_complete_hamming_recall_and_determinism() -> None:
    left = "0000000000000000"
    adversarial = "0001000100010001"  # one changed bit in every old 16-bit band
    outside = "ffffffffffffffff"
    expected = ((left, adversarial, 4),)
    assert threshold_complete_hamming_pairs([outside, adversarial, left], 4) == expected
    assert threshold_complete_hamming_pairs([left, adversarial, outside, left], 4) == expected

    generator = random.Random(0)
    random_values = {f"{generator.getrandbits(64):016x}" for _ in range(256)}
    boundary = 0xA5A5A5A5A5A5A5A5
    random_values.update(
        (
            f"{boundary:016x}",
            f"{boundary ^ ((1 << 8) - 1):016x}",
            f"{boundary ^ ((1 << 16) - 1):016x}",
        )
    )
    ordered = sorted(random_values)
    for radius in (0, 4, 8, 16):
        brute_force = tuple(
            (left_value, right_value, (int(left_value, 16) ^ int(right_value, 16)).bit_count())
            for left_value, right_value in combinations(ordered, 2)
            if (int(left_value, 16) ^ int(right_value, 16)).bit_count() <= radius
        )
        inputs = [*reversed(ordered), ordered[-1].upper(), ordered[-1]]
        assert threshold_complete_hamming_pairs(inputs, radius) == brute_force


def test_entity_candidates_preserve_exact_under_cap_pairs() -> None:
    plan = _threshold_complete_entity_pairs(
        {
            "0000000000000000": ["entity-b", "entity-a"],
            "0000000000000001": ["entity-c", "entity-b"],
        },
        maximum_distance=1,
        maximum_pairs=4,
    )
    assert plan.pairs == (
        ("entity-a", "entity-b"),
        ("entity-a", "entity-c"),
        ("entity-b", "entity-c"),
    )
    assert plan.overflow_components == ()
    assert plan.candidate_pair_upper_bound == 6
    assert plan.overflowed is False


def test_entity_candidates_deduplicate_overlap_before_cap_decision() -> None:
    plan = _threshold_complete_entity_pairs(
        {
            "0000000000000000": ["entity-a", "entity-b"],
            "0000000000000001": ["entity-b", "entity-a"],
        },
        maximum_distance=1,
        maximum_pairs=1,
    )
    assert plan.pairs == (("entity-a", "entity-b"),)
    assert plan.overflow_components == ()
    assert plan.candidate_pair_upper_bound == 6
    assert plan.overflowed is False


def test_entity_candidate_overflow_is_component_only_and_permutation_stable() -> None:
    forward = _threshold_complete_entity_pairs(
        {
            "AAAAAAAAAAAAAAAA": ["entity-b", "entity-a"],
            "aaaaaaaaaaaaaaaa": ["entity-c"],
            "aaaaaaaaaaaaaaab": ["entity-d"],
        },
        maximum_distance=1,
        maximum_pairs=2,
    )
    reverse = _threshold_complete_entity_pairs(
        {
            "aaaaaaaaaaaaaaab": ["entity-d"],
            "aaaaaaaaaaaaaaaa": ["entity-c"],
            "AAAAAAAAAAAAAAAA": ["entity-a", "entity-b"],
        },
        maximum_distance=1,
        maximum_pairs=2,
    )
    assert forward == reverse
    assert forward.pairs == ()
    assert forward.overflow_components == (("entity-a", "entity-b", "entity-c", "entity-d"),)
    assert forward.candidate_pair_upper_bound == 6
    assert forward.overflowed is True


def test_report_templates_are_transitive_and_permutation_deterministic(tmp_path: Path) -> None:
    def build(path: Path, reverse: bool) -> tuple[list[str], tuple[int, int, int, int]]:
        connection = initialize_private_database(path, {})
        studies = ["study-a", "study-b", "study-c"]
        if reverse:
            studies.reverse()
        for study in studies:
            _insert_study(connection, study)
        report_rows = [
            ("report-a", "study-a", "raw-x", "normalized-x"),
            ("report-b", "study-b", "raw-x", "normalized-x"),
            ("report-c", "study-c", "raw-y", "normalized-x"),
        ]
        if reverse:
            report_rows.reverse()
        for report_key, study_key, raw_key, normalized_key in report_rows:
            connection.execute(
                """INSERT INTO report_manifest VALUES(
                    ?,?,1,'present','valid',1,1,'latin',NULL,'resolved',?,?,NULL,
                    NULL,'none','pass')""",
                (report_key, study_key, raw_key, normalized_key),
            )
        edges = [
            ("report-a", "report-b", "report", "exact-report-raw", "candidate"),
            ("study-b", "study-c", "study", "near-report", "candidate"),
        ]
        if reverse:
            edges.reverse()
        for left, right, level, kind, decision in edges:
            connection.execute(
                "INSERT INTO duplicate_edge VALUES(?,?,?,?,?,'duplicate-audit-v2','{}')",
                (left, right, level, kind, decision),
            )
        assert _finalize_report_template_components(connection, secret=b"t" * 32) == 1
        keys = [
            row[0]
            for row in connection.execute(
                "SELECT template_group_key FROM report_manifest ORDER BY study_key"
            )
        ]
        counts = _exact_report_pair_counts(connection)
        connection.close()
        return keys, counts

    forward = build(tmp_path / "forward.sqlite3", False)
    reverse = build(tmp_path / "reverse.sqlite3", True)
    assert forward == reverse
    assert len(set(forward[0])) == 1
    assert forward[1] == (1, 3, 1, 3)


def test_metadata_variation_and_label_copy_stay_scoped(tmp_path: Path) -> None:
    connection = initialize_private_database(tmp_path / "manifest.sqlite3", {})
    try:
        for study in ("study-a", "study-b", "study-c"):
            _insert_study(connection, study)
            _insert_series(connection, f"series-{study[-1]}", study)
        _insert_slice(
            connection,
            "file-a",
            "study-a",
            "series-a",
            "1" * 16,
            raw_key="raw-a",
            decoded_key="pixels",
            position="[0,0,0]",
        )
        _insert_slice(
            connection,
            "file-b",
            "study-b",
            "series-b",
            "1" * 16,
            raw_key="raw-b",
            decoded_key="pixels",
            position="[0,0,0]",
        )
        _insert_slice(
            connection,
            "file-c",
            "study-c",
            "series-c",
            "1" * 16,
            raw_key="raw-c",
            decoded_key="pixels",
            position="[0,0,1]",
        )
        metadata = _persist_altered_metadata_edges(connection, b"m" * 32, [])
        assert metadata.raw_container_variation_groups == 1
        assert metadata.altered_metadata_groups == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM duplicate_edge WHERE edge_kind='raw-container-variation-file'"
        ).fetchone() == (1,)
        altered = connection.execute(
            """SELECT left_key, right_key FROM duplicate_edge
                WHERE edge_kind='altered-metadata-file'"""
        ).fetchall()
        assert altered and all(set(pair) != {"file-a", "file-b"} for pair in altered)

        for study in ("study-a", "study-b", "study-c"):
            for index, state in enumerate(("positive", "unknown", "negative")):
                connection.execute(
                    """INSERT INTO label_source_manifest VALUES(
                        ?,?,'target','official','v1',?,NULL,NULL,'organizer','valid')""",
                    (study, index, state),
                )
        before = list(
            connection.execute(
                "SELECT study_key,target_index,label_state FROM label_source_manifest ORDER BY 1,2"
            )
        )
        copies = _label_copy_candidates_within_components(
            connection,
            component_keys={
                "study-a": "component-ab",
                "study-b": "component-ab",
                "study-c": "singleton-c",
            },
            target_count=3,
            secret=b"l" * 32,
        )
        assert copies == 1
        assert connection.execute(
            "SELECT left_key,right_key FROM duplicate_edge WHERE edge_kind='label-copy-candidate'"
        ).fetchall() == [("study-a", "study-b")]
        after = list(
            connection.execute(
                "SELECT study_key,target_index,label_state FROM label_source_manifest ORDER BY 1,2"
            )
        )
        assert after == before
    finally:
        connection.close()


def test_common_blank_is_excluded_and_large_nonblank_group_is_linear(tmp_path: Path) -> None:
    connection = initialize_private_database(tmp_path / "manifest.sqlite3", {})
    try:
        for index in range(129):
            for prefix, fingerprint in (("blank", "0" * 16), ("image", "0" * 15 + "1")):
                study = f"{prefix}-study-{index:03d}"
                series = f"{prefix}-series-{index:03d}"
                file_key = f"{prefix}-file-{index:03d}"
                _insert_study(connection, study)
                _insert_series(connection, series, study)
                _insert_slice(connection, file_key, study, series, fingerprint)
        schema = json.loads((ROOT / "configs/manifest_schema.yaml").read_text())
        study_edges = []
        summary = _near_slice_edges(
            connection,
            schema=schema,
            secret=b"p" * 32,
            study_edges=study_edges,
        )
        assert summary.groups == 1
        assert summary.persisted_edges == 128
        assert summary.suppressed_edges == 8128
        assert summary.promoted_study_edges == 128
        assert summary.unresolved_study_pairs == 0
        assert len(study_edges) == 128
        assert connection.execute(
            """SELECT COUNT(*) FROM manifest_issue
                WHERE issue_code='low_information_perceptual_fingerprint'"""
        ).fetchone() == (129,)
    finally:
        connection.close()


def test_near_slice_rejects_missing_decoded_fingerprint(tmp_path: Path) -> None:
    connection = initialize_private_database(tmp_path / "manifest.sqlite3", {})
    try:
        _insert_study(connection, "study")
        _insert_series(connection, "series", "study")
        _insert_slice(connection, "file", "study", "series", "1" * 16)
        connection.execute(
            "UPDATE slice_file_manifest SET near_slice_fingerprint=NULL WHERE file_key='file'"
        )
        schema = json.loads((ROOT / "configs/manifest_schema.yaml").read_text())
        with pytest.raises(ManifestAuditError, match="decoded_slice_fingerprint_missing"):
            _near_slice_edges(
                connection,
                schema=schema,
                secret=b"p" * 32,
                study_edges=[],
            )
    finally:
        connection.close()


def test_near_slice_study_pair_overflow_uses_one_conservative_forest(
    tmp_path: Path,
) -> None:
    slices = (
        ("study-a", "series-a-1", "file-a-1", "0000000000000001"),
        ("study-b", "series-b", "file-b", "0000000000000003"),
        ("study-a", "series-a-2", "file-a-2", "fffffffffffffffe"),
        ("study-c", "series-c", "file-c", "fffffffffffffffc"),
    )

    def run(path: Path, rows: tuple[tuple[str, str, str, str], ...]) -> tuple[object, ...]:
        connection = initialize_private_database(path, {})
        try:
            for study in ("study-a", "study-b", "study-c"):
                _insert_study(connection, study)
            for study, series, file_key, fingerprint in rows:
                _insert_series(connection, series, study)
                _insert_slice(connection, file_key, study, series, fingerprint)
            schema = json.loads((ROOT / "configs/manifest_schema.yaml").read_text())
            schema["dicom"]["near_slice_maximum_study_pairs"] = 1
            study_edges = []
            summary = _near_slice_edges(
                connection,
                schema=schema,
                secret=b"s" * 32,
                study_edges=study_edges,
            )
            persisted = connection.execute(
                """SELECT left_key,right_key,edge_kind,decision,private_metrics
                    FROM duplicate_edge WHERE entity_level='study'
                    ORDER BY left_key,right_key,edge_kind"""
            ).fetchall()
            issues = connection.execute(
                """SELECT entity_key,issue_code FROM manifest_issue
                    WHERE issue_code='near_slice_study_pair_space_overflow'
                    ORDER BY entity_key"""
            ).fetchall()
            metric_keys = (
                "near_slice_study_pair_space_overflow",
                "near_slice_study_pair_limit",
                "near_slice_study_pair_count_lower_bound",
                "near_slice_overflow_fingerprint_components",
                "near_slice_overflow_study_components",
                "near_slice_overflow_study_edges",
            )
            metrics = dict(
                connection.execute(
                    """SELECT key,value FROM manifest_run
                        WHERE key IN (?,?,?,?,?,?) ORDER BY key""",
                    metric_keys,
                ).fetchall()
            )
            exported = _candidate_overflow_aggregate_fields(connection, 20)
            component_keys, crossings = _protected_components(connection, study_edges, b"p" * 32)
            component_counts = (
                connection.execute(
                    "SELECT COUNT(DISTINCT component_key) FROM protected_component"
                ).fetchone()[0],
                connection.execute(
                    "SELECT COUNT(DISTINCT component_key) FROM candidate_component"
                ).fetchone()[0],
                connection.execute("SELECT COUNT(*) FROM duplicate_component_edge").fetchone()[0],
            )
            return (
                summary,
                persisted,
                issues,
                metrics,
                exported,
                component_keys,
                crossings,
                component_counts,
            )
        finally:
            connection.close()

    forward = run(tmp_path / "forward.sqlite3", slices)
    reverse = run(tmp_path / "reverse.sqlite3", tuple(reversed(slices)))
    assert forward == reverse
    summary, persisted, issues, metrics, exported, component_keys, crossings, counts = forward
    assert summary.groups == 2
    assert summary.persisted_edges == 2
    assert summary.suppressed_edges == 0
    assert summary.promoted_study_edges == 2
    assert persisted == [
        (
            "study-a",
            "study-b",
            "near-slice-study-space-overflow-block",
            "candidate",
            '{"discovery":"threshold_complete_component_fallback",'
            '"reason":"study_pair_limit_exceeded"}',
        ),
        (
            "study-b",
            "study-c",
            "near-slice-study-space-overflow-block",
            "candidate",
            '{"discovery":"threshold_complete_component_fallback",'
            '"reason":"study_pair_limit_exceeded"}',
        ),
    ]
    assert issues == [
        ("study-a", "near_slice_study_pair_space_overflow"),
        ("study-b", "near_slice_study_pair_space_overflow"),
        ("study-c", "near_slice_study_pair_space_overflow"),
    ]
    assert metrics == {
        "near_slice_overflow_fingerprint_components": "2",
        "near_slice_overflow_study_components": "1",
        "near_slice_overflow_study_edges": "2",
        "near_slice_study_pair_count_lower_bound": "2",
        "near_slice_study_pair_limit": "1",
        "near_slice_study_pair_space_overflow": "true",
    }
    assert exported == {
        "near_slice_study_pair_space_overflow": True,
        "near_slice_study_pair_count_lower_bound": 2,
        "near_slice_overflow_study_edges": "suppressed",
        "near_series_candidate_space_overflow": False,
        "near_series_candidate_pair_count_lower_bound": 0,
        "near_series_overflow_study_edges": 0,
        "near_report_candidate_space_overflow": False,
        "near_report_candidate_pair_count_lower_bound": 0,
        "near_report_overflow_study_edges": 0,
    }
    assert crossings == 0
    assert len(set(component_keys.values())) == 3
    assert counts == (3, 1, 2)


def test_near_slice_under_cap_keeps_direct_low_evidence_classification(
    tmp_path: Path,
) -> None:
    connection = initialize_private_database(tmp_path / "manifest.sqlite3", {})
    try:
        for study, series, file_key, fingerprint in (
            ("study-a", "series-a", "file-a", "0000000000000001"),
            ("study-b", "series-b", "file-b", "0000000000000003"),
        ):
            _insert_study(connection, study)
            _insert_series(connection, series, study)
            _insert_slice(connection, file_key, study, series, fingerprint)
        schema = json.loads((ROOT / "configs/manifest_schema.yaml").read_text())
        schema["dicom"]["near_slice_maximum_study_pairs"] = 2
        study_edges = []
        summary = _near_slice_edges(
            connection,
            schema=schema,
            secret=b"s" * 32,
            study_edges=study_edges,
        )
        assert summary.promoted_study_edges == 1
        edge = connection.execute(
            """SELECT edge_kind,decision,private_metrics FROM duplicate_edge
                WHERE entity_level='study'"""
        ).fetchone()
        assert edge[:2] == ("near-slice-low-evidence", "candidate")
        assert json.loads(edge[2]) == {
            "distinct_series_pairs_lower_bound": 1,
            "distinct_series_pairs_saturated": False,
            "matching_slice_pairs": 1,
            "minimum_distinct_series_pairs": 2,
            "minimum_matching_slice_pairs": 3,
        }
        assert connection.execute(
            """SELECT COUNT(*) FROM manifest_run
                WHERE key='near_slice_study_pair_space_overflow'"""
        ).fetchone() == (0,)
    finally:
        connection.close()


def test_near_slice_series_pair_witnesses_saturate_at_promotion_threshold(
    tmp_path: Path,
) -> None:
    connection = initialize_private_database(tmp_path / "manifest.sqlite3", {})
    try:
        for study in ("study-a", "study-b"):
            _insert_study(connection, study)
            for index in range(2):
                series = f"series-{study[-1]}-{index}"
                _insert_series(connection, series, study)
                _insert_slice(
                    connection,
                    f"file-{study[-1]}-{index}",
                    study,
                    series,
                    "1" * 16,
                )
        schema = json.loads((ROOT / "configs/manifest_schema.yaml").read_text())
        schema["dicom"]["near_slice_maximum_study_pairs"] = 20
        _near_slice_edges(
            connection,
            schema=schema,
            secret=b"s" * 32,
            study_edges=[],
        )
        kind, metrics_json = connection.execute(
            """SELECT edge_kind,private_metrics FROM duplicate_edge
                WHERE entity_level='study'"""
        ).fetchone()
        assert kind == "near-slice-study"
        metrics = json.loads(metrics_json)
        assert metrics["matching_slice_pairs"] == 4
        assert metrics["distinct_series_pairs_lower_bound"] == 2
        assert metrics["distinct_series_pairs_saturated"] is True
    finally:
        connection.close()


def test_blank_series_fingerprints_do_not_expand_candidates(tmp_path: Path) -> None:
    connection = initialize_private_database(tmp_path / "manifest.sqlite3", {})
    try:
        schema = json.loads((ROOT / "configs/manifest_schema.yaml").read_text())
        schema["dicom"]["near_series_maximum_candidate_pairs"] = 10
        evidence = tuple(
            SeriesEvidence(
                series_key=f"series-{index}",
                study_key=f"study-{index}",
                split="train",
                plane=None,
                rows=8,
                columns=8,
                exact_key=None,
                phashes=("0" * 16,) * 5,
                sample_paths=(),
                sample_file_keys=(),
            )
            for index in range(6)
        )
        assert _near_series_edges(connection, evidence, schema, []) == (0, 0, 0)
    finally:
        connection.close()


def test_series_overflow_chains_connect_studies_across_entity_components(
    tmp_path: Path,
) -> None:
    first_fingerprint = "1" * 16
    second_fingerprint = "e" * 16
    evidence = (
        SeriesEvidence(
            series_key="series-a-1",
            study_key="study-a",
            split="train",
            plane=None,
            rows=8,
            columns=8,
            exact_key=None,
            phashes=(first_fingerprint,) * 5,
            sample_paths=(),
            sample_file_keys=(),
        ),
        SeriesEvidence(
            series_key="series-b",
            study_key="study-b",
            split="train",
            plane=None,
            rows=8,
            columns=8,
            exact_key=None,
            phashes=(first_fingerprint,) * 5,
            sample_paths=(),
            sample_file_keys=(),
        ),
        SeriesEvidence(
            series_key="series-a-2",
            study_key="study-a",
            split="train",
            plane=None,
            rows=8,
            columns=8,
            exact_key=None,
            phashes=(second_fingerprint,) * 5,
            sample_paths=(),
            sample_file_keys=(),
        ),
        SeriesEvidence(
            series_key="series-c",
            study_key="study-c",
            split="train",
            plane=None,
            rows=8,
            columns=8,
            exact_key=None,
            phashes=(second_fingerprint,) * 5,
            sample_paths=(),
            sample_file_keys=(),
        ),
    )

    def run(path: Path, items: tuple[SeriesEvidence, ...]) -> tuple[object, ...]:
        connection = initialize_private_database(path, {})
        try:
            for study in ("study-a", "study-b", "study-c"):
                _insert_study(connection, study)
            schema = json.loads((ROOT / "configs/manifest_schema.yaml").read_text())
            schema["dicom"]["near_series_maximum_candidate_pairs"] = 1
            study_edges = []
            counts = _near_series_edges(connection, items, schema, study_edges)
            persisted = connection.execute(
                """SELECT left_key,right_key,edge_kind,decision,private_metrics
                    FROM duplicate_edge ORDER BY left_key,right_key"""
            ).fetchall()
            issues = connection.execute(
                """SELECT entity_key,issue_code FROM manifest_issue
                    ORDER BY entity_key,issue_code"""
            ).fetchall()
            metrics = connection.execute(
                """SELECT key,value FROM manifest_run
                    WHERE key LIKE 'near_series_%' ORDER BY key"""
            ).fetchall()
            hard_components = build_protected_components(
                ("study-a", "study-b", "study-c"), study_edges
            )
            candidate_components = build_candidate_components(
                ("study-a", "study-b", "study-c"), study_edges
            )
            exported = _candidate_overflow_aggregate_fields(connection, 20)
            return (
                counts,
                persisted,
                issues,
                metrics,
                hard_components,
                candidate_components,
                exported,
            )
        finally:
            connection.close()

    forward = run(tmp_path / "forward.sqlite3", evidence)
    reverse = run(tmp_path / "reverse.sqlite3", tuple(reversed(evidence)))
    assert forward == reverse
    counts, persisted, issues, metrics, hard_components, candidate_components, exported = forward
    assert counts == (0, 0, 2)
    assert [(row[0], row[1]) for row in persisted] == [
        ("study-a", "study-b"),
        ("study-b", "study-c"),
    ]
    assert all(row[2:4] == ("near-series-overflow-block", "candidate") for row in persisted)
    assert all(
        json.loads(row[4])
        == {
            "discovery": "threshold_complete_component_fallback",
            "reason": "candidate_pair_upper_bound_exceeded",
        }
        for row in persisted
    )
    assert issues == [
        ("study-a", "near_series_candidate_space_overflow"),
        ("study-b", "near_series_candidate_space_overflow"),
        ("study-c", "near_series_candidate_space_overflow"),
    ]
    assert dict(metrics) == {
        "near_series_candidate_pair_count_lower_bound": "2",
        "near_series_candidate_pair_limit": "1",
        "near_series_candidate_pair_upper_bound": "2",
        "near_series_candidate_space_overflow": "true",
        "near_series_overflow_entity_components": "2",
        "near_series_overflow_study_components": "1",
        "near_series_overflow_study_edges": "2",
    }
    assert len(set(hard_components.values())) == 3
    assert len(set(candidate_components.values())) == 1
    assert exported == {
        "near_slice_study_pair_space_overflow": False,
        "near_slice_study_pair_count_lower_bound": 0,
        "near_slice_overflow_study_edges": 0,
        "near_series_candidate_space_overflow": True,
        "near_series_candidate_pair_count_lower_bound": 2,
        "near_series_overflow_study_edges": "suppressed",
        "near_report_candidate_space_overflow": False,
        "near_report_candidate_pair_count_lower_bound": 0,
        "near_report_overflow_study_edges": 0,
    }


def test_near_series_confirmation_preserves_memory_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = SeriesEvidence(
        series_key="series",
        study_key="study",
        split="train",
        plane=None,
        rows=8,
        columns=8,
        exact_key=None,
        phashes=("1" * 16,) * 5,
        sample_paths=(Path("synthetic.dcm"),),
        sample_file_keys=("file",),
    )

    def exhaust_memory(_: Path) -> object:
        raise MemoryError

    monkeypatch.setattr(manifest_module, "_load_pixel_array", exhaust_memory)
    schema = json.loads((ROOT / "configs/manifest_schema.yaml").read_text())
    with pytest.raises(MemoryError):
        manifest_module._confirm_near_series(
            evidence,
            evidence,
            direction="forward",
            schema=schema,
        )


def test_exact_report_group_is_collapsed_before_candidate_expansion(tmp_path: Path) -> None:
    connection = initialize_private_database(tmp_path / "manifest.sqlite3", {})
    try:
        studies = {
            f"train:raw-{index}": StudySource(
                raw_study_id=f"raw-{index}", split="train", report="same report text"
            )
            for index in range(6)
        }
        inventory = SourceInventory(studies, {}, (), 6, 0, 0, 0)
        study_keys = {qualified: f"study-{index}" for index, qualified in enumerate(studies)}
        reports = {
            qualified: ReportFeatures(
                presence_state="present",
                unicode_state="valid",
                character_count=16,
                token_count=20,
                script_bucket="latin",
                language_code="en",
                language_state="resolved",
                raw_text_exact_key="raw-key",
                canonical_text_exact_key="canonical-key",
                near_report_fingerprint="1" * 16,
            )
            for qualified in studies
        }
        schema = json.loads((ROOT / "configs/manifest_schema.yaml").read_text())
        schema["reports"]["maximum_candidate_pairs"] = 10
        assert _report_edges(connection, inventory, study_keys, reports, schema, []) == (0, 0, 0)
    finally:
        connection.close()


def test_report_overflow_persists_only_protective_study_chain(tmp_path: Path) -> None:
    connection = initialize_private_database(tmp_path / "manifest.sqlite3", {})
    try:
        studies = {
            f"train:raw-{index}": StudySource(
                raw_study_id=f"raw-{index}",
                split="train",
                report="synthetic report " + "word " * 20,
            )
            for index in range(4)
        }
        study_keys = {qualified: f"study-{index}" for index, qualified in enumerate(studies)}
        for study_key in study_keys.values():
            _insert_study(connection, study_key)
        inventory = SourceInventory(studies, {}, (), 4, 0, 0, 0)
        reports = {
            qualified: ReportFeatures(
                presence_state="present",
                unicode_state="valid",
                character_count=64,
                token_count=20,
                script_bucket="latin",
                language_code="en",
                language_state="resolved",
                raw_text_exact_key=f"raw-key-{index}",
                canonical_text_exact_key=f"canonical-key-{index}",
                near_report_fingerprint="1" * 16,
            )
            for index, qualified in enumerate(studies)
        }
        schema = json.loads((ROOT / "configs/manifest_schema.yaml").read_text())
        schema["reports"]["maximum_candidate_pairs"] = 2
        study_edges = []
        assert _report_edges(
            connection,
            inventory,
            study_keys,
            reports,
            schema,
            study_edges,
        ) == (0, 0, 3)
        persisted = connection.execute(
            """SELECT left_key,right_key,edge_kind,decision FROM duplicate_edge
                ORDER BY left_key,right_key"""
        ).fetchall()
        assert persisted == [
            ("study-0", "study-1", "near-report-overflow-block", "candidate"),
            ("study-1", "study-2", "near-report-overflow-block", "candidate"),
            ("study-2", "study-3", "near-report-overflow-block", "candidate"),
        ]
        assert connection.execute(
            """SELECT COUNT(*) FROM manifest_issue
                WHERE issue_code='near_report_candidate_space_overflow'"""
        ).fetchone() == (4,)
        metrics = dict(
            connection.execute(
                """SELECT key,value FROM manifest_run
                    WHERE key LIKE 'near_report_%' ORDER BY key"""
            ).fetchall()
        )
        assert metrics == {
            "near_report_candidate_pair_count_lower_bound": "3",
            "near_report_candidate_pair_limit": "2",
            "near_report_candidate_pair_upper_bound": "6",
            "near_report_candidate_space_overflow": "true",
            "near_report_overflow_entity_components": "1",
            "near_report_overflow_study_components": "1",
            "near_report_overflow_study_edges": "3",
        }
        hard_components = build_protected_components(study_keys.values(), study_edges)
        candidate_components = build_candidate_components(study_keys.values(), study_edges)
        assert len(set(hard_components.values())) == 4
        assert len(set(candidate_components.values())) == 1
        assert _candidate_overflow_aggregate_fields(connection, 20) == {
            "near_slice_study_pair_space_overflow": False,
            "near_slice_study_pair_count_lower_bound": 0,
            "near_slice_overflow_study_edges": 0,
            "near_series_candidate_space_overflow": False,
            "near_series_candidate_pair_count_lower_bound": 0,
            "near_series_overflow_study_edges": 0,
            "near_report_candidate_space_overflow": True,
            "near_report_candidate_pair_count_lower_bound": 3,
            "near_report_overflow_study_edges": "suppressed",
        }
    finally:
        connection.close()


def test_report_exact_representatives_and_overflow_share_one_soft_candidate_component(
    tmp_path: Path,
) -> None:
    connection = initialize_private_database(tmp_path / "manifest.sqlite3", {})
    try:
        studies = {
            f"train:raw-{index}": StudySource(
                raw_study_id=f"raw-{index}",
                split="train",
                report=f"synthetic report {index} " + "word " * 20,
            )
            for index in range(6)
        }
        inventory = SourceInventory(studies, {}, (), 6, 0, 0, 0)
        study_keys = {qualified: f"study-{index}" for index, qualified in enumerate(studies)}
        reports: dict[str, ReportFeatures] = {}
        for index, qualified in enumerate(studies):
            study_key = study_keys[qualified]
            _insert_study(connection, study_key)
            canonical_key = f"canonical-{index // 2}"
            features = ReportFeatures(
                presence_state="present",
                unicode_state="valid",
                character_count=64,
                token_count=20,
                script_bucket="latin",
                language_code="en",
                language_state="resolved",
                raw_text_exact_key=f"raw-{index}",
                canonical_text_exact_key=canonical_key,
                near_report_fingerprint="1" * 16,
            )
            reports[qualified] = features
            connection.execute(
                """INSERT INTO report_manifest(
                    report_key,study_key,source_row_count,presence_state,unicode_state,
                    character_count,token_count,script_bucket,language_code,language_state,
                    raw_text_exact_key,canonical_text_exact_key,near_report_fingerprint,
                    template_group_key,template_match_kind,terminal_state)
                    VALUES(?,?,1,'present','valid',64,20,'latin','en','resolved',?,?,?,
                        NULL,'none','pass')""",
                (
                    f"report-{index}",
                    study_key,
                    features.raw_text_exact_key,
                    canonical_key,
                    features.near_report_fingerprint,
                ),
            )

        study_edges = []
        assert (
            _persist_exact_groups(
                connection,
                table="report_manifest",
                entity_column="report_key",
                study_column="study_key",
                digest_column="canonical_text_exact_key",
                entity_level="report",
                kind="exact-report-normalized",
                secret=b"e" * 32,
                study_edges=study_edges,
            )
            == 3
        )
        schema = json.loads((ROOT / "configs/manifest_schema.yaml").read_text())
        schema["reports"]["maximum_candidate_pairs"] = 2
        assert _report_edges(
            connection,
            inventory,
            study_keys,
            reports,
            schema,
            study_edges,
        ) == (0, 0, 2)
        assert _finalize_report_template_components(connection, secret=b"t" * 32) == 1
        component_keys, crossings = _protected_components(connection, study_edges, b"p" * 32)

        assert crossings == 0
        assert len(set(component_keys.values())) == 6
        assert connection.execute(
            """SELECT DISTINCT decision FROM duplicate_edge
                WHERE edge_kind LIKE '%report%' ORDER BY decision"""
        ).fetchall() == [("candidate",)]
        assert connection.execute(
            "SELECT COUNT(DISTINCT template_group_key) FROM report_manifest"
        ).fetchone() == (1,)
        assert connection.execute(
            """SELECT COUNT(*) FROM report_manifest
                WHERE template_match_kind='exact-report-normalized+near-report-overflow-block'"""
        ).fetchone() == (6,)
        assert connection.execute(
            "SELECT COUNT(DISTINCT component_key),COUNT(*) FROM protected_component"
        ).fetchone() == (6, 6)
        assert connection.execute(
            "SELECT COUNT(DISTINCT component_key),COUNT(*) FROM candidate_component"
        ).fetchone() == (1, 6)
        assert connection.execute(
            """SELECT component_kind,COUNT(*) FROM duplicate_component_summary
                GROUP BY component_kind ORDER BY component_kind"""
        ).fetchall() == [
            ("hard-protected", 6),
            ("legacy-v1-all-evidence", 1),
            ("soft-candidate", 1),
        ]
    finally:
        connection.close()
