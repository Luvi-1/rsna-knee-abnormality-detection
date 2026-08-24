# Sprint postmortem

## What went well

- Isolated worktree kept the active Chunk 5 workspace untouched throughout.
- All 639 tests pass; strict mypy and Ruff clean across every new module.
- Every chunk has a dated doc recording objective, evidence, decisions, and risks.
- The experiment portfolio is ranked with clear priority rationale.
- Red team found real issues before any real data was touched.

## What was harder than expected

- Section detection initially required an exact end-of-line match for headers,
  which silently dropped the first section body on single-line normalized text.
- Import ordering between src/, scripts/, and tests/ required explicit
  PYTHONPATH management because scripts/ is not a package.
- The baseline model pooling bug was caught immediately by tests but cost a
  round-trip.

## What was skipped deliberately

- No torch/tensorflow dependency: the baseline is numpy-only by design.
- No subgroup metrics: deferred until real cohort definitions exist.
- No output validator expected-keys check: deferred until live Kaggle schema
  is confirmed against an authenticated submission.
- No diversity sampling in the active-learning queue.

## Process improvements for next sprint

1. Write the synthetic label-quality corpus before building any more rule
   vocabulary; it will catch coverage gaps that code review misses.
2. Add a CI-level check that runs PYTHONPATH=src:scripts pytest so import
   issues are caught before manual test runs.
3. Consider adding a lightweight integration test that exercises the full path
   from normalization through combiner to OOF writer on one synthetic report.
