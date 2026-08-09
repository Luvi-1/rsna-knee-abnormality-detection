---
name: competition-contract-auditor
description: Audit and refresh the live RSNA Knee Kaggle competition contract from authoritative sources. Use before every work chunk and before submissions, team changes, external-asset use, public releases, or decisions affected by rules, deadlines, runtime, licenses, data handling, or eligibility.
---

# Competition Contract Auditor

## Trigger conditions

- Run at the start of every chunk.
- Run before any submission, team action, rules acceptance, external-asset approval, public release, or major compute commitment.
- Run when a deadline, rule, license, runtime limit, dataset contract, or account-eligibility state may have changed.

## Required inputs

- Provide the canonical competition slug.
- Provide the latest snapshot in `docs/competition_contract/`, if one exists.
- Provide access to the official Kaggle MCP or official Kaggle CLI and authoritative organizer pages.
- State the intended next action so the audit can identify its gates.

## Procedure

1. Read the latest snapshot without modifying it.
2. Query the official Kaggle MCP first; fall back to the official Kaggle CLI and official organizer pages.
3. Record retrieval time and source authority for rules, data, evaluation, timeline, runtime, submissions, external assets, teams, licenses, sharing, winner obligations, and account eligibility.
4. Compare each field with the prior snapshot. Separate confirmed changes, unchanged facts, discrepancies, and unknowns.
5. Create a new timestamped snapshot. Preserve prior snapshots.
6. State whether the intended action is allowed, approval-gated, or blocked, with the exact reason.

## Forbidden actions

- Do not accept rules, submit, select a final submission, create or merge a team, publish, delete remotely, or spend compute.
- Do not print credentials, environment-variable values, private URLs, or private competition artifacts.
- Do not infer a current fact from an old snapshot when live verification fails.
- Do not weaken a restriction because two sources disagree; retain the stricter interpretation until resolved.

## Outputs

- Produce one timestamped Markdown snapshot under `docs/competition_contract/`.
- Report source evidence, field-by-field changes, discrepancies, unresolved unknowns, and action gates.
- Return a concise pass, blocked, or stale verdict.

## Validation checks

- Confirm every contract category in the procedure is present or explicitly marked unknown.
- Confirm the snapshot has a UTC retrieval time and names authoritative sources.
- Confirm changes are compared against the immediately previous snapshot.
- Confirm no credential, private URL, patient data, raw report text, or private artifact appears.
- Confirm no external write occurred.

## Failure behavior

- Fail closed when live authoritative evidence is unavailable or contradictory.
- Preserve the previous snapshot, write no fabricated replacement, and report the exact missing evidence and safe retry path.
- Block the intended action when the unresolved field can affect legality, eligibility, privacy, runtime, or submission validity.
