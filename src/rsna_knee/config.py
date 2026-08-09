"""Typed experiment configuration and stable hashing."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Reject unknown fields so configuration drift fails closed."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ExperimentIdentity(StrictModel):
    id: str = Field(pattern=r"^exp-[a-z0-9][a-z0-9-]*$")
    hypothesis: str = Field(min_length=1)
    primary_change: str = Field(min_length=1)
    frozen_controls: list[str] = Field(min_length=1)
    seed: int = Field(ge=0)


class VersionRefs(StrictModel):
    data_manifest: str = Field(min_length=1)
    labels: str = Field(min_length=1)
    folds: str = Field(min_length=1)
    preprocessing: str = Field(min_length=1)


class ModelSpec(StrictModel):
    name: str = Field(min_length=1)
    parameters: dict[str, str | int | float | bool] = Field(default_factory=dict)


class TrainingSpec(StrictModel):
    epochs: int = Field(gt=0)
    batch_size: int = Field(gt=0)
    learning_rate: float = Field(gt=0)
    loss: str = Field(min_length=1)
    augmentation: list[str]
    deterministic: bool = True


class EvaluationSpec(StrictModel):
    primary_metric: Literal["macro_roc_auc"]
    labels: list[str] = Field(min_length=12, max_length=12)


class ComputeSpec(StrictModel):
    accelerator: Literal["cpu", "gpu"]
    estimated_minutes: int = Field(gt=0)
    max_inference_minutes: int = Field(gt=0, le=540)
    safety_margin_minutes: int = Field(ge=30)

    @model_validator(mode="after")
    def preserve_runtime_margin(self) -> ComputeSpec:
        if self.max_inference_minutes + self.safety_margin_minutes > 540:
            raise ValueError("inference runtime plus safety margin must not exceed 540 minutes")
        return self


class ExperimentGate(StrictModel):
    expected_information_gain: str = Field(min_length=1)
    promotion_criterion: str = Field(min_length=1)
    kill_criterion: str = Field(min_length=1)


class ExperimentConfig(StrictModel):
    experiment: ExperimentIdentity
    versions: VersionRefs
    model: ModelSpec
    training: TrainingSpec
    evaluation: EvaluationSpec
    compute: ComputeSpec
    gate: ExperimentGate


def load_experiment_config(path: Path) -> ExperimentConfig:
    """Load and validate a TOML experiment contract."""

    with path.open("rb") as stream:
        return ExperimentConfig.model_validate(tomllib.load(stream))


def config_hash(config: ExperimentConfig) -> str:
    """Return a deterministic SHA-256 over the validated configuration."""

    payload = json.dumps(config.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
