---
name: leakage-auditor
description: Detect patient, repeated-study, exact-duplicate, near-duplicate, report-template, fold, transformation, pseudo-label, checkpoint, and evaluation leakage in medical-imaging experiments. Use before accepting folds, preprocessing, labels, external assets, out-of-fold predictions, model comparisons, ensembles, or promotion evidence, and whenever their lineage changes.
---

# Leakage Auditor

## Trigger conditions

- Create or change a data manifest, grouping rule, duplicate rule, fold assignment, preprocessing step, or label pipeline.
- Review external assets, checkpoints, pseudo-labels, out-of-fold predictions, evaluation, ensembles, or promotion claims.
- Investigate unexpectedly strong validation results or train-validation distribution similarities.

## Required inputs

- Current competition contract, `VALIDATION_CARD.md`, `DECISIONS.md`, and applicable rules.
- Versioned manifest with opaque study identifiers, patient/group keys, repeated-study links, and exact and near-duplicate evidence.
- Fold assignments and generator configuration, including seed and code version.
- Transformation, label-rule, threshold, calibration, checkpoint, pseudo-label, prediction, and external-asset lineage.
- Aggregate cohort and fold counts; no raw pixels, reports, or identifying metadata.

## Procedure

1. Define the independent evaluation unit and required grouping keys before inspecting outcomes.
2. Test every train-validation pair for patient, repeated-study, exact-duplicate, near-duplicate, and report-template overlap.
3. Trace derived artifacts so alternate encodings, cached crops, labels, embeddings, or predictions cannot cross a group boundary unnoticed.
4. Verify that learned preprocessing, imputation, normalization, vocabularies, thresholds, calibration, ensembles, and pseudo-label rules are fit on training folds only.
5. Verify checkpoint and external-asset provenance against competition eligibility and pretraining-data overlap risks.
6. Prove that each out-of-fold prediction was made by a model that never trained on that study, its group, or a duplicate. Prove that no model pseudo-labeled a study it trained on.
7. Check that compared experiments use identical eligible rows, folds, label masks, and metric implementations unless differences are explicit.
8. Return `PASS`, `CONDITIONAL`, or `BLOCK` with overlap counts, rates, evidence, and remediation.

## Forbidden actions

- Upload, display, or transmit private images, reports, patient-level metadata, or private predictions.
- Declare leakage absent from aggregate fold sizes alone or from missing identifiers.
- Silently drop overlaps, relabel rows, regenerate folds, or tune duplicate thresholds using validation outcomes.
- Approve target-derived features, validation-fitted transforms, self-pseudo-labeling, or leaderboard-only evidence.
- Train, submit, change teams, accept rules, or publish assets as part of the audit.

## Outputs

- Versioned leakage report with manifest and fold versions, checks run, overlap counts and rates, lineage findings, and limitations.
- Explicit `PASS`, `CONDITIONAL`, or `BLOCK` decision plus the exact blocking paths and smallest safe remediation.
- Proposed updates to `VALIDATION_CARD.md`, `RISK_REGISTER.md`, or the experiment record when facts changed.

## Validation checks

- Reconcile manifest totals, fold totals, exclusions, and label-mask denominators.
- Check all fold pairs symmetrically and record the exact near-duplicate method, threshold, and version.
- Confirm deterministic fold regeneration from the recorded inputs, seed, and code version.
- Trace every out-of-fold prediction to a compatible training exclusion set and every transform to its fit scope.
- Confirm outputs contain only opaque identifiers where row-level evidence is essential; prefer aggregates.

## Failure behavior

- Return `BLOCK` when group keys, duplicate evidence, fold lineage, fit scope, or prediction lineage is absent or ambiguous.
- Stop and report only the category of exposure if sensitive material appears; do not echo its contents.
- Preserve uncertainty as a blocker. Never substitute an assumption for a leakage check or certify evidence that cannot be reproduced.
