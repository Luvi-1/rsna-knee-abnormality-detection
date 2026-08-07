# Validation Card

Version: unassigned; no folds exist.

## Primary metric

Macro average of 12 per-label ROC AUC values, matching Kaggle evaluation.

## Required evidence

- All 12 AUCs and macro AUC.
- Positive/negative/unknown counts by fold.
- Bootstrap confidence intervals.
- Site/scanner/protocol/sex/language subgroups when permitted and statistically meaningful.
- Runtime, peak memory, model size, and prediction correlations.
- Manual report-label validation and permitted MRI review results.

## Split invariants

- Group patients, repeated studies, exact and near duplicates, and report templates before splitting.
- Fit preprocessing statistics, weak-label rules, thresholds, calibration, ensemble weights, and pseudo-label logic without validation leakage.
- Every promoted model emits out-of-fold predictions.
- Ensemble weights use nested or held-out OOF evidence, never the same examples used to fit them.

## Open gate

The available patient/repeat grouping keys are not yet established. No fold design is valid until a privacy-safe Kaggle metadata audit resolves them.
