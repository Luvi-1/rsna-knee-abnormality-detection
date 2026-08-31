#!/usr/bin/env python3
"""Screen the frozen Chunk 4R public-candidate registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rsna_knee.public_repro import load_registry, registry_summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("configs/public_baseline/chunk4r_candidates.json"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    candidates = load_registry(args.registry)
    summary = registry_summary(candidates)
    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    # Exit 2 means the registry is valid but no candidate currently clears all
    # inference gates. It is a workflow decision, not a parser failure.
    return 0 if summary["selected_candidate_id"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
