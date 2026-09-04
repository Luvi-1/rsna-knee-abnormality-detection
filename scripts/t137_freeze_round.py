"""Freeze a T137 round manifest and print the exact authorization request.

This utility is network-free and contains no submission functionality.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rsna_knee.targetwise_specialist.contracts import (
    ContractError,
    FrozenRound,
    authorization_request,
    parse_candidate,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Freeze a fail-closed T137 round manifest.")
    result.add_argument("--round-id", required=True)
    result.add_argument("--live-allowance", required=True, type=int)
    result.add_argument("--candidates", required=True, type=Path)
    result.add_argument("--output", required=True, type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    raw: Any = json.loads(args.candidates.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("candidates"), list):
        raise SystemExit("candidate file must contain a candidates array")

    try:
        candidates = tuple(parse_candidate(item) for item in raw["candidates"])
        round_manifest = FrozenRound(
            round_id=args.round_id,
            live_submission_allowance=args.live_allowance,
            candidates=candidates,
        )
        payload = round_manifest.canonical_payload()
        digest = round_manifest.sha256()
        request = authorization_request(round_manifest)
    except (ContractError, TypeError, ValueError) as exc:
        raise SystemExit(f"T137 round freeze failed: {exc}") from exc

    complete = {
        **payload,
        "manifest_sha256": digest,
        "authorization_present": False,
        "authorization_request": request,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(complete, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"round_id={round_manifest.round_id}")
    print(f"manifest_sha256={digest}")
    print(f"candidate_count={len(round_manifest.candidates)}")
    print(f"authorization_request={request}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
