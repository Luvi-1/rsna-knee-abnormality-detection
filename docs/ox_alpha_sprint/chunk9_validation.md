# Chunk 9 — Validation design

Date: 2026-08-22.

## Grouping semantics

- Hard groups (patient identity, repeated examination, exact duplicates) are
  enforced at fold construction time. No two members of a hard group may appear
  in different folds.
- Soft similarity evidence (template clustering, report embedding similarity)
  is tracked separately and never automatically promotes a study into a hard
  group. Promotion to hard-group status requires explicit human approval.

## Stratification dimensions

The greedy fold builder balances positive-label mass across folds. Additional
dimensions (language, site, manufacturer, field strength, plane, sequence, image
quality) can be added as weighted columns in the labels matrix once real cohort
definitions are available from authenticated data access.

## Leakage prevention

The following conditions cause an immediate failure:

- A patient crosses folds.
- An exact duplicate crosses folds.
- A hard group crosses folds.
- An OOF prediction was produced by a model trained on that study.
- Ensemble weights were fitted and evaluated on the same rows.
- Preprocessing statistics used validation or test data.
- Pseudo-labeled examples were not cross-fitted.

Tests in tests/test_grouped_folds.py and tests/test_oof_provenance.py cover
determinism, no-duplicate-study assignment, and bootstrap CI bounds using
synthetic inputs.
