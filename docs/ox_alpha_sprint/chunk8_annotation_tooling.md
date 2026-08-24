# Chunk 8 — Annotation partitioning and active-learning queue

Date: 2026-08-22.
Branch: ox-alpha/rsna-seven-day-acceleration.

## Objective

Provide deterministic study-key-to-partition assignment and an uncertainty-ranked
annotation queue so human review effort can be targeted without leaking gold or
holdout studies into development workflows. All test inputs are synthetic hashes;
no private identifiers are read or stored.

## Scope delivered

- src/rsna_knee/annotation/partitioning.py: stable hash-prefix dev/holdout split
  with strict key validation and a gold-partition isolation guard that rejects
  unauthorized gold assignments and cross-partition leakage of gold keys.
- src/rsna_knee/annotation/queue.py: deterministic active-learning queue ranked
  by descending uncertainty score with study-key tie-breaking.
- schemas/annotation_database.schema.json: strict container schema binding the
  ontology version, partition assignments, and annotation records together.

## Evidence

Commands:

- PYTHONPATH=src uv run pytest tests/test_annotation_partitioning.py
  tests/test_active_learning_queue.py
- uv run ruff check src/rsna_knee/annotation tests/test_annotation_partitioning.py
  tests/test_active_learning_queue.py
- uv run ruff format (same paths)
- uv run mypy src/rsna_knee/annotation

Results: 13 targeted tests passed; Ruff clean; strict mypy clean.

## Design decisions

- Partition assignment uses the first eight hex characters of the already-hashed
  study key mapped to a unit interval. This is deterministic across runs and
  avoids any dependence on insertion order or mutable state.
- Gold keys are held in a separate frozenset supplied by the caller. The guard
  fails closed on both unauthorized gold labels and gold keys placed outside the
  gold partition.
- The queue is a pure function with no persistence. Callers own storage and can
  regenerate it from updated uncertainty scores at any time.

## Risks / limits

- Hash-prefix splitting is uniform but does not enforce exact per-class balance;
  explicit stratification is deferred to the fold engine where labels exist.
- Queue ranking is single-objective (uncertainty only). Diversity sampling is
  intentionally omitted until real label distributions justify the complexity.
