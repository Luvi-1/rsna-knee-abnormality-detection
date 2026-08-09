---
name: kaggle-notebook-packager
description: Package a validated RSNA Knee experiment into a reproducible, offline Kaggle notebook bundle with pinned inputs, provenance, resource budgets, and synthetic-only preflight checks. Use when preparing or auditing a notebook, kernel metadata, dependency bundle, or execution command for Kaggle; do not use it to submit predictions.
---

# Kaggle Notebook Packager

## Trigger conditions

- Prepare code for a Kaggle notebook run, rerun, or handoff.
- Audit an existing notebook bundle for reproducibility, privacy, or runtime compliance.
- Produce Kaggle notebook metadata or documented upload/run commands.

## Required inputs

- Current `AGENTS.md`, `STATUS.md`, `DECISIONS.md`, `RISK_REGISTER.md`, and latest competition contract.
- Exact Git commit, locked dependency specification, experiment config, and package entry point.
- Versioned Kaggle input references and approved public external assets with licenses.
- Data-manifest, fold, preprocessing, and label versions; expected outputs and resource budget.

## Procedure

1. Re-verify live Kaggle notebook, runtime, internet, external-asset, sharing, and competition constraints using the official Kaggle MCP first, then the official CLI.
2. Require a clean, attributable code state and record the commit, config hash, dependency lock, input versions, and all artifact provenance.
3. Keep the notebook as a thin orchestrator over `src/rsna_knee`; include only files needed for the declared run.
4. Make all inputs explicit and immutable. Remove local paths, undeclared downloads, hidden state, and implicit notebook-cell ordering.
5. Set deterministic seeds where supported, bounded CPU/GPU/memory/disk use, structured aggregate logs, and a runtime margin below the live ceiling.
6. Run the packaged entry point against synthetic fixtures without network access and record the exact result.
7. Emit the bundle manifest, preflight report, and exact documented Kaggle upload/run commands. Stop before any remote write unless separately approved.

## Forbidden actions

- Do not include raw DICOMs, reports, patient metadata, credentials, tokens, checkpoints, predictions, or private outputs.
- Do not upload a notebook, start compute, accept rules, change a team, or submit predictions without the required human gate.
- Do not fetch undeclared assets at runtime, weaken tests to pass, or claim reproducibility without a clean synthetic preflight.
- Do not send competition artifacts to an LLM, Hugging Face, W&B, GitHub, or another external service.

## Outputs

- Minimal notebook bundle and metadata.
- Manifest containing code, config, dependency, input, fold, preprocessing, and label provenance.
- Synthetic preflight report, resource estimate, and documented local/Kaggle commands.

## Validation checks

- Confirm package installation/import, locked dependencies, valid notebook metadata, and one synthetic end-to-end smoke test.
- Confirm declared inputs resolve, outputs are bounded, the runtime budget has a safety margin, and no network is required.
- Scan the bundle and Git index for secrets, patient data, competition data, checkpoints, and prediction artifacts.
- Confirm every artifact records the required provenance fields.

## Failure behavior

Fail closed. Do not upload or run the package. Preserve existing artifacts, report the exact failing checks and evidence, and name the smallest safe remediation; never guess credentials, input versions, or rule interpretations.
