"""Compare a privacy-safe observed contract with the canonical snapshot."""

from __future__ import annotations

import argparse
from pathlib import Path

from pydantic import ValidationError

from rsna_knee.competition_contract import (
    contract_error_summary,
    load_contract,
    material_drift,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("observed", type=Path, help="fresh aggregate-only contract candidate")
    parser.add_argument(
        "--canonical",
        type=Path,
        default=Path("docs/competition_contract/contract.yaml"),
    )
    args = parser.parse_args()
    try:
        if args.observed.samefile(args.canonical):
            print("contract_valid=no reason=observed_not_independent")
            return 2
        changed = material_drift(load_contract(args.canonical), load_contract(args.observed))
    except (OSError, ValidationError) as error:
        print(f"contract_valid=no reason={contract_error_summary(error)}")
        return 2
    if changed:
        print(f"contract_drift=yes sections={','.join(changed)}")
        return 1
    print("contract_drift=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
