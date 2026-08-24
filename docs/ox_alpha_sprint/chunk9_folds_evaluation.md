# Chunk 9 — Grouped folds and exact evaluation

Date: 2026-08-22.
Branch: ox-alpha/rsna-seven-day-acceleration.

## Objective

Provide leakage-resistant grouped fold construction and exact multi-label macro
AUC with bootstrap confidence intervals so that any later model comparison uses
a single, reproducible evaluation path. All test inputs are synthetic.

## Scope delivered

- src/rsna_knee/folds/grouped_multilabel.py: greedy positive-mass-balanced
  assignment of whole studies to folds; deterministic ordering and tie-breaking;
  duplicate-study-key rejection.
- src/rsna_knee/evaluation/metrics.py: tie-corrected rank-based ROC AUC per
  column plus macro averaging over all 12 targets (single-class columns return
  0.5 by convention).
- src/rsna_knee/evaluation/bootstrap.py: percentile bootstrap CI for macro AUC
  using a fixed seed for reproducibility.

## Evidence

Commands:

- PYTHONPATH=src uv run pytest tests/test_grouped_folds.py tests/test_metric.py
  tests/test_oof_provenance.py
- uv run ruff check src/rsna_knee/folds src/rsna_knee/evaluation (and test files)
- uv run ruff format (same paths)
- uv run mypy src/rsna_knee/folds src/rsna_knee/evaluation

Results: 15 targeted tests passed; Ruff clean; strict mypy clean.

## Design decisions

- Fold construction is greedy rather than exact because optimal multilabel
  stratification under group constraints is combinatorial; the greedy pass
  places the highest-positive-count studies first to reduce imbalance.
- AUC uses average ranks with tie correction so tied scores contribute 0.5,
  matching the competition metric definition.
- Bootstrap resamples at study level only, preserving within-study label
  correlation and avoiding artificial CI tightening.

## Risks / limits

- Greedy fold balance may be suboptimal for very rare labels; explicit rare-label
  audit should precede any promotion decision on those targets.
- No subgroup metrics are implemented yet; these are deferred until the real
  cohort definitions are available from authenticated data access.
