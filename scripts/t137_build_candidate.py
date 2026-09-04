"""Build one private T137 targetwise rank-blend candidate.

This script does not call Kaggle APIs and cannot submit. It expects prediction
CSVs produced inside an approved private environment.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from rsna_knee.targetwise_specialist.blend import targetwise_rank_blend
from rsna_knee.targetwise_specialist.contracts import FAMILIES, TARGETS
from rsna_knee.targetwise_specialist.io import (
    load_prediction_csv,
    reconcile_identifier_order,
    write_prediction_csv,
)
from rsna_knee.targetwise_specialist.rank import (
    identical_ordering,
    rank_disagreement,
    spearman_correlation,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Build one report-free T137 targetwise rank-blend candidate."
    )
    result.add_argument("--champion", required=True, type=Path)
    result.add_argument("--challenger", required=True, type=Path)
    result.add_argument("--family", required=True, choices=sorted(FAMILIES))
    result.add_argument("--champion-weight", required=True, type=float)
    result.add_argument("--output", required=True, type=Path)
    result.add_argument("--audit-output", required=True, type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    if not 0.0 <= args.champion_weight <= 1.0:
        raise SystemExit("champion weight must be within [0, 1]")

    champion_ids, champion = load_prediction_csv(args.champion)
    challenger_ids, challenger_raw = load_prediction_csv(args.challenger)
    order = reconcile_identifier_order(champion_ids, challenger_ids)
    challenger = challenger_raw[order]

    targets = FAMILIES[args.family]
    target_indices = tuple(TARGETS.index(target) for target in targets)
    candidate = targetwise_rank_blend(
        champion,
        challenger,
        target_indices=target_indices,
        champion_weight=args.champion_weight,
    )
    write_prediction_csv(args.output, champion_ids, candidate)

    per_target: list[dict[str, object]] = []
    for target, index in zip(targets, target_indices, strict=True):
        champion_values = champion[:, index]
        challenger_values = challenger[:, index]
        per_target.append(
            {
                "target": target,
                "spearman": spearman_correlation(champion_values, challenger_values),
                "rank_disagreement": rank_disagreement(
                    champion_values, challenger_values
                ),
                "identical_ordering": identical_ordering(
                    champion_values, challenger_values
                ),
                "champion_std": float(np.std(champion_values)),
                "challenger_std": float(np.std(challenger_values)),
            }
        )

    audit = {
        "family": args.family,
        "changed_targets": list(targets),
        "row_count": int(champion.shape[0]),
        "target_count": int(champion.shape[1]),
        "champion_weight": args.champion_weight,
        "challenger_weight": 1.0 - args.champion_weight,
        "blend_type": "normalized_targetwise_rank",
        "identifier_sets_equal": True,
        "per_target": per_target,
        "submission_api_called": False,
        "reports_used": False,
        "network_used": False,
    }
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
