---
name: model-card-updater
description: Update the RSNA Knee model card from validated experiment evidence while preserving provenance, uncertainty, per-label performance, limitations, privacy, licensing, and research-only boundaries. Use after an evaluated experiment, promotion decision, material model change, or external-asset change and before any model handoff or release.
---

# Model Card Updater

## Trigger conditions

- A model finishes leakage-safe out-of-fold evaluation.
- A model is promoted, rejected, superseded, or materially changed.
- Its training data, labels, preprocessing, external assets, inference path, license, or intended use changes.

## Required inputs

- Current `MODEL_CARD.md`, experiment-registry record, and relevant decision/risk entries.
- Code commit, config hash, dependency lock, data-manifest, fold, preprocessing, label, and artifact versions.
- Out-of-fold macro AUC, all 12 label AUCs, uncertainty, runtime, memory, artifact size, and prediction correlations.
- Training/evaluation design, known failure evidence, intended use, restrictions, external-asset sources, and licenses.

## Procedure

1. Read the governing files and current model card; identify the model and exact evidence being updated.
2. Cross-check every metric and provenance value against the experiment registry and immutable artifacts.
3. Update architecture, inputs, labels and masks, training, evaluation, results, uncertainty, efficiency, and reproducibility sections using verified evidence only.
4. Record data limitations, weak-label uncertainty, leakage controls, subgroup gaps, failure modes, privacy constraints, license obligations, and the non-clinical research boundary.
5. Distinguish verified facts from hypotheses, pending checks, and unavailable evidence. Preserve prior model history rather than silently rewriting it.
6. State the promotion decision and rationale only when the scientific promotion gate is fully supported.
7. Review the diff for sensitive content and consistency with `DECISIONS.md`, `RISK_REGISTER.md`, `EXTERNAL_ASSETS.md`, and the registry.

## Forbidden actions

- Do not invent, round deceptively, cherry-pick, or omit required per-label and uncertainty evidence.
- Do not include patient identifiers, raw DICOMs, reports, predictions, credentials, private paths, or sensitive logs.
- Do not claim clinical validity, generalization beyond tested data, guaranteed placement, or expert ground truth for report-derived labels.
- Do not release a model, publish artifacts, or change validated experiment records through this skill.

## Outputs

- Updated `MODEL_CARD.md` with dated model identity, evidence, provenance, limitations, licensing, and decision status.
- Concise change summary and an explicit missing-evidence list.
- `PROMOTE`, `DO NOT PROMOTE`, or `PENDING` recommendation when requested and supported.

## Validation checks

- Reconcile all values with the registry and confirm the code/config/data/fold/preprocessing/label provenance chain.
- Require macro AUC, all 12 label AUCs, uncertainty, runtime, memory, size, and prediction-correlation evidence for promotion.
- Confirm intended use, non-clinical disclaimer, privacy boundary, external-asset license, limitations, and failure modes are present.
- Scan the diff for secrets, patient data, private artifacts, unsupported claims, and accidental deletion of model history.

## Failure behavior

Do not promote or publish. Leave disputed facts unchanged, mark the status `PENDING`, and list missing or conflicting evidence with its source. Require rerun or human resolution when provenance, metrics, licensing, or privacy cannot be verified.
