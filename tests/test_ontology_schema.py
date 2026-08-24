"""Tests for the provisional ontology and annotation-record schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO = Path(__file__).resolve().parent.parent
_ONTOLOGY_PATH = _REPO / "configs" / "ontology" / "ontology_provisional_v0.yaml"
_SCHEMA_PATH = _REPO / "schemas" / "annotation_record.schema.json"


def _load_ontology() -> dict[str, Any]:
    return yaml.safe_load(_ONTOLOGY_PATH.read_text())


EXPECTED_TARGETS = [
    "ACL",
    "MCL",
    "Medial Meniscus",
    "Lateral Meniscus",
    "Medial OA",
    "Lateral OA",
    "PF OA",
    "Effusion",
    "Synovitis",
    "Baker's",
    "Contusion",
    "Fracture",
]


class TestOntologyStructure:
    def test_file_exists(self) -> None:
        assert _ONTOLOGY_PATH.is_file()

    def test_schema_version_is_one(self) -> None:
        ontology = _load_ontology()
        assert ontology["schema_version"] == 1

    def test_status_is_provisional(self) -> None:
        ontology = _load_ontology()
        assert ontology["status"] == "provisional_not_expert_approved"

    def test_not_mentioned_is_never_negative(self) -> None:
        ontology = _load_ontology()
        policies = ontology["shared_policies"]
        assert policies["not_mentioned_is_negative"] is False
        assert policies["missing_label_semantics"] == "unknown_not_negative"

    def test_four_state_only(self) -> None:
        ontology = _load_ontology()
        assert ontology["shared_policies"]["four_state_only"] is True
        states = set(ontology["shared_states"].keys())
        assert states == {"positive", "negative", "uncertain", "not_mentioned"}

    def test_exactly_twelve_targets_matching_competition_columns(self) -> None:
        ontology = _load_ontology()
        columns = [t["column"] for t in ontology["targets"]]
        assert len(columns) == 12
        assert columns == EXPECTED_TARGETS

    @pytest.mark.parametrize("target", EXPECTED_TARGETS)
    def test_every_target_has_required_fields(self, target: str) -> None:
        ontology = _load_ontology()
        entry = next(t for t in ontology["targets"] if t["column"] == target)
        for field in (
            "clinical_concept",
            "positive_terms",
            "negative_terms",
            "uncertain_terms",
            "related_do_not_count",
            "ambiguity_notes",
            "laterality",
        ):
            assert field in entry, f"{target} missing {field}"
        assert len(entry["positive_terms"]) > 0
        assert len(entry["negative_terms"]) > 0
        assert len(entry["uncertain_terms"]) > 0

    def test_all_eleven_ambiguity_resolutions_present(self) -> None:
        ontology = _load_ontology()
        resolutions = ontology.get("ambiguity_resolutions", {})
        expected_keys = [
            "meniscal_degeneration_vs_tear",
            "postoperative_meniscal_morphology",
            "mucoid_acl_vs_injury",
            "acl_graft_vs_native_tear",
            "healed_chronic_mcl_change",
            "trace_physiologic_fluid_vs_effusion",
            "effusion_vs_synovitis",
            "bakers_cyst_vs_popliteal_abnormality",
            "traumatic_bone_contusion_vs_degenerative_edema",
            "acute_vs_healed_fracture",
            "insufficiency_stress_fracture",
            "cartilage_damage_vs_compartment_OA",
        ]
        for key in expected_keys:
            assert key in resolutions, f"missing ambiguity resolution: {key}"
            assert "decision" in resolutions[key]
            assert "rationale" in resolutions[key]


class TestAnnotationRecordSchema:
    @pytest.fixture()
    def schema(self) -> dict[str, Any]:
        return json.loads(_SCHEMA_PATH.read_text())  # type: ignore[no-any-return]

    def test_schema_is_valid_json_with_draft_2020(self, schema: dict[str, Any]) -> None:
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_required_fields_present(self, schema: dict[str, Any]) -> None:
        required = schema["required"]
        for field in ("record_id", "study_key", "target_column", "label_state", "source_type"):
            assert field in required

    def test_additional_properties_false(self, schema: dict[str, Any]) -> None:
        assert schema["additionalProperties"] is False

    def test_four_states_in_enum(self, schema: dict[str, Any]) -> None:
        state_prop = schema["properties"]["label_state"]
        assert set(state_prop["enum"]) == {"positive", "negative", "uncertain", "not_mentioned"}

    def test_target_column_matches_competition_targets(self, schema: dict[str, Any]) -> None:
        target_enum = schema["properties"]["target_column"]["enum"]
        assert target_enum == EXPECTED_TARGETS

    def test_record_id_pattern_rejects_uid_like_strings(self, schema: dict[str, Any]) -> None:
        pattern = schema["properties"]["record_id"]["pattern"]
        import re

        assert re.match(pattern, "ann_" + "a" * 32) is not None
        # A UID-like string must not match.
        assert re.match(pattern, "1.2.826.0.1.3680043") is None
