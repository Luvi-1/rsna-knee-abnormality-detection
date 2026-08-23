from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from rsna_knee.data import qa_strata
from rsna_knee.data import series_slots as slots

ROOT = Path(__file__).parents[1]


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


review = _load("_dicom_qa_on_demand_test", ROOT / "kaggle/dicom_qa/on_demand_review.py")
packager = _load(
    "_dicom_qa_on_demand_packager_test",
    ROOT / "scripts/package_dicom_qa_on_demand.py",
)


def _touch_entries(root: Path, entries: set[str], directories: set[str] | None = None) -> None:
    root.mkdir(parents=True)
    directories = directories or set()
    for name in entries:
        path = root / name
        if name in directories:
            path.mkdir()
        else:
            path.write_bytes(b"x")


def _mounts(tmp_path: Path, layout: str = "direct") -> tuple[Path, Any]:
    input_root = tmp_path / "input"
    input_root.mkdir()
    bundle_ref = "owner/frozen-bundle"
    source_ref = "owner/source-kernel"
    source_entries = tuple(sorted(review.SOURCE_REQUIRED_ENTRIES))
    if layout == "direct":
        bundle = input_root / "frozen-bundle"
        source = input_root / "source-kernel"
        competition = input_root / review.COMPETITION_SLUG
    elif layout == "owner":
        bundle = input_root / "owner/frozen-bundle"
        source = input_root / "owner/source-kernel"
        competition = input_root / review.COMPETITION_SLUG
    else:
        bundle = input_root / "datasets/owner/frozen-bundle"
        source = input_root / "notebooks/owner/source-kernel"
        competition = input_root / "competitions" / review.COMPETITION_SLUG
    _touch_entries(bundle, {"bundle-manifest.json"})
    _touch_entries(source, set(source_entries))
    _touch_entries(
        competition,
        set(review.COMPETITION_ENTRIES),
        {"train_series", "test_series"},
    )
    refs = review.InputRefs(bundle_ref, source_ref, source_entries)
    return input_root, refs


@pytest.mark.parametrize("layout", ["direct", "owner", "typed"])
def test_input_discovery_accepts_only_explicit_bounded_layouts(tmp_path: Path, layout: str) -> None:
    input_root, refs = _mounts(tmp_path, layout)
    train_root = next(input_root.rglob("train_series"))
    for index in range(review.MAX_ROOT_ENTRIES + 10):
        (train_root / f"study-{index:03d}").mkdir()

    roots = review.discover_inputs(input_root, refs)

    assert roots.bundle.name == "frozen-bundle"
    assert roots.source.name == "source-kernel"
    assert roots.competition.name == review.COMPETITION_SLUG


def test_input_discovery_accepts_competition_mount_metadata_but_checks_entry_types(
    tmp_path: Path,
) -> None:
    input_root, refs = _mounts(tmp_path, "typed")
    competition = input_root / "competitions" / review.COMPETITION_SLUG
    (competition / "dataset-metadata.json").write_bytes(b"{}")

    assert review.discover_inputs(input_root, refs).competition == competition

    (competition / "train_series").rmdir()
    (competition / "train_series").write_bytes(b"not-a-directory")
    with pytest.raises(review.OnDemandReviewError, match="input_root_invalid"):
        review.discover_inputs(input_root, refs)


def test_input_discovery_rejects_duplicate_unexpected_and_symlink_roots(
    tmp_path: Path,
) -> None:
    input_root, refs = _mounts(tmp_path)
    duplicate = input_root / "owner/frozen-bundle"
    _touch_entries(duplicate, {"bundle-manifest.json"})
    with pytest.raises(review.OnDemandReviewError, match="input_duplicate"):
        review.discover_inputs(input_root, refs)

    duplicate.rename(input_root / "owner/old-bundle")
    (input_root / "source-kernel/unexpected.txt").write_bytes(b"x")
    with pytest.raises(review.OnDemandReviewError, match="input_missing"):
        review.discover_inputs(input_root, refs)

    (input_root / "source-kernel/unexpected.txt").unlink()
    real = tmp_path / "real-source"
    (input_root / "source-kernel").rename(real)
    (input_root / "source-kernel").symlink_to(real, target_is_directory=True)
    with pytest.raises(review.OnDemandReviewError, match="input_symlink_rejected"):
        review.discover_inputs(input_root, refs)


def test_fixed_selector_is_deterministic_has_no_max_and_keeps_representatives_inside() -> None:
    dimensions = tuple(rule.dimension for rule in qa_strata.QA_STRATUM_REGISTRY)
    studies = tuple(
        qa_strata.StudyStrata(
            f"study-{index:03d}",
            frozenset(
                {
                    qa_strata.Stratum(dimension, f"singleton-{index:03d}")
                    if dimension == "laterality"
                    else qa_strata.Stratum(dimension, "common")
                    for dimension in dimensions
                }
            ),
        )
        for index in range(101)
    )

    first = qa_strata.select_qa_cohort(studies, minimum_size=100, manifest_version="manifest-v2")
    second = qa_strata.select_qa_cohort(
        tuple(reversed(studies)), minimum_size=100, manifest_version="manifest-v2"
    )

    assert first == second
    assert len(first.selected_study_keys) == 101
    assert first.coverage.all_required_represented_registry_values_satisfy_quotas
    selected = set(first.selected_study_keys)
    for row in first.coverage.rows:
        representatives = {
            study.study_key
            for study in studies
            if study.study_key in selected
            and qa_strata.Stratum(row.dimension, row.value) in study.memberships
        }
        assert representatives <= selected
        assert len(representatives) == row.selected
        assert row.selected >= min(2, row.population)


def test_frozen_runner_hash_is_checked_before_import(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    runner = tmp_path / "runner.py"
    runner.write_text(f"open({str(marker)!r}, 'w').write('bad')\n", encoding="utf-8")
    expected = "a" * 64
    manifest = {
        "bundle_sha256": "b" * 64,
        "files": [
            {
                "role": "runner_source",
                "path": "runner.py",
                "sha256": expected,
            }
        ],
    }
    (tmp_path / "bundle-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    roots = review.InputRoots(tmp_path, tmp_path, tmp_path)

    with pytest.raises(review.OnDemandReviewError, match="runner_source_hash_mismatch"):
        review._frozen_runtime(roots, "b" * 64, expected)

    assert not marker.exists()


def test_cohort_laterality_read_is_header_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "slice"
    source.write_bytes(b"header")
    observed: dict[str, Any] = {}

    def dcmread(path: Path, **kwargs: Any) -> object:
        observed.update({"path": path, **kwargs})
        return object()

    monkeypatch.setitem(sys.modules, "pydicom", SimpleNamespace(dcmread=dcmread))
    runner = SimpleNamespace(_series_files=lambda *_args: (source,))
    pipeline = SimpleNamespace(_laterality=lambda _dataset: "L")

    assert review._laterality(runner, pipeline, tmp_path, object()) == "left"
    assert observed == {
        "path": source,
        "stop_before_pixels": True,
        "specific_tags": ["ImageLaterality", "Laterality"],
        "force": False,
    }


def _quality() -> slots.SeriesQuality:
    return slots.SeriesQuality(
        total_slices=3,
        decoded_slices=3,
        decode_failure_count=0,
        duplicate_slices=0,
        geometry_valid=True,
        spacing_regular=True,
        median_slice_spacing_mm=3.0,
        spacing_coefficient_of_variation=0.0,
        pixel_spacing_mm=(0.5, 0.5),
        physical_coverage_mm=6.0,
    )


def test_actual_processing_is_scoped_to_requested_study() -> None:
    orientation = (0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
    ordered = SimpleNamespace(
        model_eligible=True,
        slices=[SimpleNamespace(metadata=SimpleNamespace(image_orientation=orientation))],
    )
    decoded = (SimpleNamespace(metadata=SimpleNamespace(image_orientation=orientation)),)
    calls: list[str] = []

    class SeriesRow:
        def __init__(self, **values: str) -> None:
            self.__dict__.update(values)

    def files(_root: Path, row: Any) -> tuple[Path, ...]:
        calls.append(row.series_uid)
        return (Path("one"), Path("two"), Path("three"))

    runner = SimpleNamespace(
        SeriesRow=SeriesRow,
        _series_files=files,
        _decode_order_pass=lambda *_args, **_kwargs: SimpleNamespace(
            ordered=ordered,
            decoded=decoded,
            decode_failures=(),
            order_failure=None,
            file_raw_checksums=("a" * 64,) * 3,
        ),
        _reconcile_source_manifest_series_files=lambda *_args, **_kwargs: 3,
        _quality=lambda **_kwargs: _quality(),
        _slot_assignment_by_series=lambda assignment: {
            selection.primary.candidate.series_key: (
                selection.slot.value,
                selection.primary.original_slot.value,
                (),
            )
            for selection in assignment.primary_slots
            if selection.primary is not None
        },
    )
    plan_study = {
        "study_uid": "1.2.3.4",
        "all_series": [
            {
                "series_ordinal": 0,
                "series_uid": "1.2.3.4.0",
                "fluid_sensitive": "absent",
                "fat_suppression": "absent",
                "plane": "axial",
                "slot": "additional_or_duplicate",
                "original_slot": "axial_structural",
                "retention_reasons": [],
                "terminal_state": "quality_blocked",
                "model_eligible": False,
            },
            {
                "series_ordinal": 1,
                "series_uid": "1.2.3.4.5",
                "fluid_sensitive": "present",
                "fat_suppression": "present",
                "plane": "sagittal",
                "slot": "sagittal_fluid_sensitive",
                "original_slot": "sagittal_fluid_sensitive",
                "retention_reasons": [],
                "terminal_state": "model_eligible",
                "model_eligible": True,
            },
        ],
        "eligible_series": [
            {
                "review_index": 0,
                "series_ordinal": 1,
                "series_uid": "1.2.3.4.5",
            }
        ],
    }

    states = review._actual_study_states(
        runner=runner,
        slots=slots,
        pipeline=object(),
        competition_root=Path("competition"),
        plan_study=plan_study,
        reconciliation=object(),
    )

    assert len(states) == 1
    assert calls == ["1.2.3.4.5"]


ATTESTATION = (
    "I ATTEST THAT I AM AN AUTHORIZED HUMAN REVIEWER, I PERSONALLY INSPECTED EVERY "
    "DISPLAYED PRIVATE ARTIFACT, AND NO LLM OR BROWSER AUTOMATION VIEWED THE PRIVATE ARTIFACTS."
)
CHECKS = (
    "slice_order",
    "anatomical_orientation",
    "laterality_preservation",
    "no_unintended_mirroring",
    "intensity_polarity",
    "anatomy_not_clipped",
    "sequence_slot_assignment",
    "preprocessing_appearance",
    "duplicate_missing_abnormal_handling",
)


def _ui() -> Any:
    return SimpleNamespace(
        REVIEW_CHECKS=CHECKS,
        DECISION_CODES={"P": "PASS", "B": "BLOCK", "N": "NOT_APPLICABLE"},
        NOT_APPLICABLE_CHECKS=frozenset({"duplicate_missing_abnormal_handling"}),
        REVIEW_GUIDANCE=tuple((check, "fixed guidance") for check in CHECKS),
        HUMAN_ATTESTATION_STATEMENT=ATTESTATION,
    )


def _plan() -> dict[str, Any]:
    context = {"check_9_applicable": False}
    return {
        "schema_version": 1,
        "artifact_type": "private-dicom-qa-on-demand-plan",
        "status": "pending_private_human_review",
        "identity": {
            "review_bundle_id": "a" * 64,
            "preprocessing_version": "dicom-model-v1",
            "cohort_hash": "b" * 64,
            "registry_version": "qa-stratum-registry-v1",
        },
        "total_studies": 1,
        "total_eligible_series": 1,
        "studies": [
            {
                "review_study_index": 0,
                "study_uid": "1.2.3.4",
                "all_series": [{"series_uid": "1.2.3.4.5"}],
                "eligible_series": [
                    {
                        "review_index": 0,
                        "series_ordinal": 0,
                        "series_uid": "1.2.3.4.5",
                        "review_context": context,
                    }
                ],
            }
        ],
    }


def test_interactive_path_renders_once_checkpoints_attests_and_cleans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan()
    ui = _ui()
    review._ACTIVE_REVIEW_UI = ui
    review._checkpoint(tmp_path / review.PLAN_BASENAME, plan, review.MAX_PRIVATE_JSON_BYTES)
    rendered: list[Path] = []

    def render(**kwargs: Any) -> list[Path]:
        output = kwargs["output_dir"] / "artifact.png"
        output.write_bytes(b"private")
        rendered.append(output)
        return [output]

    answers = iter(("NEXT", "PPPPPPPPN", ATTESTATION))
    times = iter(
        (
            "2020-01-01T00:00:00Z",
            "2020-01-01T00:00:01Z",
            "2020-01-01T00:00:02Z",
            "2020-01-01T00:00:03Z",
        )
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr(review, "_utc_now", lambda: next(times, "2020-01-01T00:00:03Z"))
    monkeypatch.setattr(review, "_actual_study_states", lambda **_kwargs: [{"series_ordinal": 0}])
    monkeypatch.setattr(review, "_render_one", render)
    runner = SimpleNamespace(
        _preprocessing_config=lambda *_args: object(),
        SOURCE_MANIFEST_VERSION="manifest-v2",
    )
    pipeline = SimpleNamespace(PipelineVersions=lambda **values: SimpleNamespace(**values))

    ledger_path = review._interactive_review(
        runner=runner,
        review_ui=ui,
        slots=object(),
        pipeline=pipeline,
        qa=object(),
        competition_root=tmp_path,
        working_root=tmp_path,
        run_config={"code_commit": "c" * 40},
        paths={"preprocessing_config": tmp_path / "config"},
        plan=plan,
        reconciliation=object(),
    )

    ledger = review._read_json(ledger_path)
    summary = review._read_json(tmp_path / review.SUMMARY_BASENAME)
    assert len(rendered) == 1
    assert not rendered[0].exists()
    assert not list(tmp_path.glob(".review-study-*"))
    assert ledger["status"] == "complete"
    assert ledger["human_attestation"]["statement"] == ATTESTATION
    assert summary["status"] == "pass"
    assert summary["blocking_decisions"] == "zero"


def test_resume_rejects_identity_timestamp_and_na_mismatch() -> None:
    plan = _plan()
    review._ACTIVE_REVIEW_UI = _ui()
    ledger = review._new_ledger(plan, "c" * 64)
    review._validate_resume(ledger, plan, "c" * 64)

    changed = json.loads(json.dumps(plan))
    changed["identity"]["cohort_hash"] = "d" * 64
    with pytest.raises(review.OnDemandReviewError, match="resume_invalid"):
        review._validate_resume(ledger, changed, "c" * 64)

    future = json.loads(json.dumps(ledger))
    future["started_at_utc"] = "2999-01-01T00:00:00Z"
    with pytest.raises(review.OnDemandReviewError, match="resume_invalid"):
        review._validate_resume(future, plan, "c" * 64)

    ledger["series"][0]["completion_state"] = "complete"
    ledger["series"][0]["reviewed_at_utc"] = ledger["started_at_utc"]
    ledger["series"][0]["decisions"] = dict.fromkeys(CHECKS, "PASS")
    ledger["series"][0]["decisions"]["slice_order"] = "NOT_APPLICABLE"
    ledger["last_completed_review_index"] = 0
    ledger["studies"][0].update(
        {
            "series_complete": 1,
            "completion_state": "complete",
            "completed_at_utc": ledger["started_at_utc"],
        }
    )
    with pytest.raises(review.OnDemandReviewError, match="resume_invalid"):
        review._validate_resume(ledger, plan, "c" * 64)

    ledger["series"][0]["decisions"]["slice_order"] = "PASS"
    ledger["status"] = "complete"
    ledger["completed_at_utc"] = ledger["started_at_utc"]
    ledger["human_attestation"] = {
        "statement": ATTESTATION,
        "authorized_human_reviewer": True,
        "direct_visual_review": True,
        "no_llm_or_browser_automation_pixel_access": True,
        "attested_at_utc": ledger["started_at_utc"],
    }
    with pytest.raises(review.OnDemandReviewError, match="resume_invalid"):
        review._validate_resume(ledger, plan, "c" * 64)


def test_sanitized_output_rejects_identifiers_paths_and_comments(tmp_path: Path) -> None:
    valid = {"status": "human_review_ready", "cohort_hash": "a" * 64}
    review._write_sanitized(tmp_path / "valid.json", valid)
    assert (tmp_path / "valid.json").is_file()

    for unsafe in (
        {"study_uid": "hidden"},
        {"value": "1.2.840.10008.1"},
        {"value": "/kaggle/input/private"},
        {"comments": "private"},
    ):
        with pytest.raises(review.OnDemandReviewError, match="sanitized_output_invalid"):
            review._write_sanitized(tmp_path / "unsafe.json", unsafe)


def test_readiness_remains_pre_start_without_a_review_ledger(tmp_path: Path) -> None:
    plan = _plan()
    plan["identity"].update(
        {
            "selector_version": "qa-cohort-selection-v3",
            "selector_sha256": "c" * 64,
            "registry_sha256": "d" * 64,
            "notebook_source_sha256": "e" * 64,
        }
    )
    plan["total_studies"] = 100
    plan["total_eligible_series"] = 100

    review._write_sanitized(tmp_path / review.READINESS_BASENAME, review._readiness(plan))

    assert review._read_json(tmp_path / review.READINESS_BASENAME)["human_review_status"] == (
        "not_started"
    )
    assert not (tmp_path / review.LEDGER_BASENAME).exists()


@pytest.mark.parametrize(
    "error_type", [EOFError, type("StdinNotImplementedError", (Exception,), {})]
)
def test_batch_stdin_unavailable_stops_before_start(
    monkeypatch: pytest.MonkeyPatch, error_type: type[BaseException]
) -> None:
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt="": (_ for _ in ()).throw(error_type()),
    )

    assert review._pre_start_input("START: ") is None


def test_packaged_notebook_attests_embedded_source_hash() -> None:
    source = (
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True)\n"
        "class EmbeddedIdentity:\n"
        "    value: str\n"
        "def run_on_demand_review(**kwargs):\n"
        "    return 0 if EmbeddedIdentity('ok').value == 'ok' else 2\n"
    )
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    payload = packager._notebook_payload(
        source=source,
        source_sha256=source_hash,
        bundle_ref="owner/frozen-bundle",
        source_ref="owner/source-kernel",
        bundle_sha256="a" * 64,
        runner_sha256="b" * 64,
    )
    notebook = json.loads(payload)
    code = notebook["cells"][1]["source"]

    assert notebook["nbformat"] == 4
    assert source_hash in code
    assert "expected_runner_sha256" in code
    assert "run_on_demand_review" in code
    assert all(isinstance(cell["source"], str) for cell in notebook["cells"])
    assert payload == packager._canonical_json_bytes(notebook)
    exec(compile(code, "packaged-on-demand-test.ipynb", "exec"), {})
