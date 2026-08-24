# Chunk 8 — Gold-set design

Date: 2026-08-22.

## Two review types

1. Human report-label review: a qualified reviewer reads the radiology report
   and assigns one of four states per target. This validates weak-label output
   but does not validate image-level interpretation.

2. Human direct-MRI review: a qualified reviewer examines the MRI series and
   assigns states based on imaging findings. This is the gold standard for
   model comparison but is slower and requires clinical expertise.

## Reviewer workflow

- Cases are presented in blinded order (study key only; no metadata that could
  bias the reviewer).
- Each case may receive double review for targets where the first reviewer's
  confidence is below a configurable threshold.
- Adjudication status tracks whether conflicting reviews have been resolved.
- All reviews are bound to ontology_version to prevent cross-version mixing.

## Untouched validation partition

A designated subset of studies is marked "untouched" and must never be used for:

- label-model training,
- architecture selection,
- ensemble weight fitting,
- threshold tuning,
- pseudo-label seed selection.

This partition exists to provide an unbiased final estimate. The annotation
database schema records the partition assignment so downstream code can enforce
the boundary programmatically.
