# Validation Card

## Competition metric contract

- Canonical source: `docs/competition_contract/contract.yaml` through
  `configs/competition.yaml`.
- Primary metric: unweighted mean of all 12 per-label ROC AUC values in canonical label order.
- Degenerate-label behavior is not specified by the organizer. Local evaluation must require at
  least one positive and one negative for every target and fail closed otherwise.
- No threshold, transform, fold, label rule, or ensemble weight may be fit on validation rows.

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
