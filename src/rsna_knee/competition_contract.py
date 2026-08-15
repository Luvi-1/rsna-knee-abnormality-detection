"""Canonical competition-contract loading and material drift detection."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

MATERIAL_SECTIONS = (
    "identity",
    "targets",
    "metric",
    "submission",
    "timeline",
    "runtime",
    "limits",
    "data",
    "efficiency_prize",
    "external_assets",
    "team_and_sharing",
    "license",
    "winner_obligations",
    "ambiguities",
    "evidence",
)


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ContractPointer(_ContractModel):
    schema_version: Literal[1]
    contract: str


class IdentityContract(_ContractModel):
    competition_id: int
    slug: str
    title: str
    identity_verification: Literal["complete", "incomplete_blocking"]


class TargetContract(_ContractModel):
    prediction_unit: Literal["study"]
    id_column: str
    labels: tuple[str, ...]


class MetricContract(_ContractModel):
    name: Literal["macro_roc_auc"]
    formula: str
    aggregation: Literal["unweighted"]
    degenerate_label_handling: Literal["unresolved_fail_closed"]


class SubmissionContract(_ContractModel):
    filename: str
    columns: tuple[str, ...]
    notebook_only: bool


class TimelineContract(_ContractModel):
    timezone: Literal["UTC"]
    start: str
    api_date_enabled: str
    entry_deadline: str
    team_merger_deadline: str
    final_submission_deadline: str
    winner_requirements_deadline: str


class RuntimeContract(_ContractModel):
    internet_enabled: bool
    cpu_limit_seconds: int
    gpu_limit_seconds: int
    accelerator_details: Literal["unresolved"]


class LimitsContract(_ContractModel):
    daily_submissions: int
    final_submissions: int
    max_team_size: int
    max_submission_size_mb: int


class FileRecord(_ContractModel):
    name: str
    bytes: int


class InventoryContract(_ContractModel):
    display_size: str
    total_files: int
    dicom_files: int
    csv_files: int
    root_directories: tuple[str, ...]
    metadata_files: tuple[FileRecord, ...]


class DataContract(_ContractModel):
    description_fingerprint: str
    inventory: InventoryContract
    train_csv_columns: tuple[str, ...]
    test_csv_columns: tuple[str, ...]
    series_csv_columns: tuple[str, ...]
    test_reports_available: bool
    official_label_coverage: str
    missing_label_semantics: Literal["unknown_not_negative"]
    train_studies: int
    train_series_rows: int


class CompetitionContract(_ContractModel):
    schema_version: Literal[1]
    retrieved_at_utc: str
    identity: IdentityContract
    targets: TargetContract
    metric: MetricContract
    submission: SubmissionContract
    timeline: TimelineContract
    runtime: RuntimeContract
    limits: LimitsContract
    data: DataContract

    @model_validator(mode="after")
    def validate_submission_schema(self) -> Self:
        if len(self.targets.labels) != 12 or len(set(self.targets.labels)) != 12:
            raise ValueError("the competition contract must contain 12 unique labels")
        expected = (self.targets.id_column, *self.targets.labels)
        if self.submission.columns != expected:
            raise ValueError("submission columns must equal the ID column followed by labels")
        if self.runtime.internet_enabled:
            raise ValueError("the canonical scoring runtime must remain offline")
        return self


def load_contract(path: Path) -> CompetitionContract:
    """Load the JSON-compatible YAML contract and validate its operational core."""

    return CompetitionContract.model_validate_json(path.read_text(encoding="utf-8"))


def load_competition_contract(
    config_path: Path,
) -> CompetitionContract:
    """Resolve the project pointer and load its single canonical contract."""

    pointer = ContractPointer.model_validate_json(config_path.read_text(encoding="utf-8"))
    return load_contract((config_path.parent / pointer.contract).resolve())


def contract_error_summary(error: OSError | ValidationError) -> str:
    """Describe a contract error without echoing input values or private paths."""

    if isinstance(error, OSError):
        return type(error).__name__
    fields = ",".join(
        f"{'.'.join(str(part) for part in item['loc'])}:{item['type']}"
        for item in error.errors(include_url=False, include_input=False)
    )
    return f"ValidationError[{fields}]"


def material_drift(expected: CompetitionContract, observed: CompetitionContract) -> tuple[str, ...]:
    """Return material top-level sections that changed."""

    expected_values = expected.model_dump(mode="json")
    observed_values = observed.model_dump(mode="json")
    return tuple(
        section
        for section in MATERIAL_SECTIONS
        if expected_values.get(section) != observed_values.get(section)
    )
