---
name: kaggle-intelligence-scout
description: Gather current, public, rule-compliant Kaggle competition intelligence with source and license provenance. Use when researching official updates, public notebooks, discussions, datasets, models, baselines, runtime patterns, or competitive hypotheses without making submissions or exposing private competition data.
---

# Kaggle Intelligence Scout

## Trigger conditions

- Run when current public Kaggle evidence is needed for a research question or planning decision.
- Run before adopting a public notebook, dataset, model, technique, or claimed benchmark.
- Run when public competition activity or organizer guidance may have changed.

## Required inputs

- Provide the competition slug and a bounded research question.
- State the allowed source types, recency window, and output location.
- Provide the current competition contract and external-asset policy.
- Provide official Kaggle MCP access or the official Kaggle CLI fallback.

## Procedure

1. Check the current competition contract and translate the question into explicit evidence fields.
2. Search with the official Kaggle MCP first; use the official CLI or public official pages only as fallback.
3. Prefer organizer material, then reproducible public notebooks and discussions. Record author, publication/update time, URL, version, and license where applicable.
4. Deduplicate sources and distinguish quoted facts, reproducible observations, author claims, and your inference.
5. Check every external asset for free/equal access, license, version, checksum availability, offline use, and winner-delivery compatibility.
6. Summarize actionable hypotheses without copying implementation wholesale or treating leaderboard scores as validation proof.

## Forbidden actions

- Do not submit, vote, comment, follow, fork, publish, accept rules, change teams, or consume paid resources.
- Do not download full competition data, raw DICOMs, or reports to the local machine.
- Do not upload competition data, patient metadata, report text, private outputs, or credentials to any external service.
- Do not use private competitor material, evade access controls, or present unverifiable claims as facts.

## Outputs

- Produce a dated research note with the question, search scope, evidence table, licenses, findings, uncertainties, and proposed tests.
- Produce a candidate external-asset entry only when all provenance fields are available.
- Return a one-line no-op when no verified evidence meets the scope.

## Validation checks

- Confirm each factual claim maps to a current source and retrieval date.
- Confirm each asset has access and license evidence or is explicitly blocked.
- Confirm facts, claims, and inferences are visibly separated.
- Confirm no private data, report text, credential, private URL, or external write appears.
- Confirm proposed hypotheses can be tested with leakage-safe validation.

## Failure behavior

- Stop after one bounded retry when the official source is unavailable.
- Report the unavailable source, stale fields, and the smallest safe manual check.
- Do not broaden scope, relax filters, or manufacture a recommendation to avoid an empty result.
