---
name: submission-red-team
description: Red-team a candidate RSNA Knee Kaggle submission for schema, provenance, leakage, reproducibility, quota, and scientific failure modes, producing a fail-closed go or no-go report. Use immediately before requesting approval to submit predictions or select a final submission; this skill never submits.
---

# Submission Red Team

## Trigger conditions

- A candidate prediction file is ready for possible Kaggle submission.
- A prior submission is being considered for final selection.
- Submission-generation or validation logic changes.

## Required inputs

- Current competition contract, rules, sample-submission schema, and submission ledger.
- Candidate artifact in its trusted execution environment plus its cryptographic hash.
- Code commit, config hash, dependency lock, data-manifest, fold, preprocessing, label, inference, and ensemble versions.
- Out-of-fold macro and all-label metrics, uncertainty, runtime, memory, size, and prediction-correlation evidence.

## Procedure

1. Re-verify live Kaggle schema, quota, deadline, final-selection, team, and submission rules using the official Kaggle MCP first, then the official CLI.
2. Validate exact column names and order, row count, identifier set and uniqueness, numeric types, finite values, allowed ranges, and deterministic serialization against the sample schema.
3. Trace the candidate to its immutable provenance and reproduce its aggregate manifest from the declared code and config.
4. Audit patient/study/duplicate grouping, fold-only fitting, missing-label masks, pseudo-label separation, thresholds, and ensemble weights for leakage.
5. Compare aggregate distributions and correlations with validated candidates; investigate suspicious constants, saturation, inversions, missing classes, or unexplained drift.
6. Verify inference runtime and resource margins, record remaining quota, and assess whether the experiment adds justified information rather than leaderboard probing.
7. Issue `GO` only when every mandatory check passes. Present the exact candidate hash and approval boundary before any submission action.

## Forbidden actions

- Do not submit, select finals, spend quota, accept rules, change teams, or self-approve an external action.
- Do not alter a candidate merely to make validation pass or optimize repeatedly against leaderboard feedback.
- Do not expose predictions, patient identifiers, raw DICOMs, reports, credentials, or private competition artifacts externally.
- Do not infer missing labels as negative or treat report-derived labels as expert ground truth.

## Outputs

- Signed-off red-team report with `GO` or `NO-GO`, candidate hash, quota snapshot, evidence, and blockers.
- Machine-readable check summary when the repository provides a schema.
- Exact human approval request for a `GO`; no submission action.

## Validation checks

- Pass schema, identifier, finiteness, range, duplicate, and deterministic-hash checks.
- Pass provenance completeness, leakage, synthetic validator regression, and runtime-margin checks.
- Reconcile the artifact with the experiment registry and submission ledger without exposing sensitive rows.
- Confirm no competition data, credentials, predictions, or private outputs are staged for Git.

## Failure behavior

Return `NO-GO`, preserve the candidate unchanged, and list exact failed checks with evidence and the smallest safe rerun or repair. If evidence is missing, rules are ambiguous, or hashes disagree, stop and require resolution rather than guessing.
