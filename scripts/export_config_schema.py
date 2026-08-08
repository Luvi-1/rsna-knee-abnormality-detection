"""Export the canonical experiment JSON Schema."""

from __future__ import annotations

import json
from pathlib import Path

from rsna_knee.config import ExperimentConfig


def main() -> None:
    target = Path("configs/experiment.schema.json")
    target.write_text(
        json.dumps(ExperimentConfig.model_json_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
