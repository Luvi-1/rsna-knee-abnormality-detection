# Chunk 7 — Weak-label framework (synthetic-only)

Date: 2026-08-22.
Branch: ox-alpha/rsna-seven-day-acceleration.

## Objective

Build a deterministic, ontology-driven weak-label framework that can later run on
private reports only after the data gate opens. This chunk uses synthetic text
fixtures exclusively and produces no patient, study, or report artifacts.

## Scope delivered

- Report normalization: Unicode cleanup, whitespace collapse, and standard
  radiology section detection with source-text offsets.
- Rule labeler: ontology-driven term matching, sentence-scoped negation and
  uncertainty handling, section priority, evidence spans, and four-state output
  where absent evidence remains not_mentioned rather than negative.
- Source combiner: priority resolution for organizer, human-review, rule,
  classifier, and propagated sources; agreement/conflict tracking; confidence-
  weighted soft probability; explicit provenance versions.
- Strict JSON Schema at schemas/weak_label.schema.json for persisted records,
  including hashed study keys and the 12 competition targets.

## Evidence

Commands:

- PYTHONPATH=src uv run pytest tests/test_report_normalization.py
  tests/test_rule_labeler.py tests/test_weak_label_combiner.py
- PYTHONPATH=src uv run pytest
- uv run ruff check src/rsna_knee/labels
  tests/test_report_normalization.py tests/test_rule_labeler.py
  tests/test_weak_label_combiner.py
- uv run ruff format src/rsna_knee/labels
  tests/test_report_normalization.py tests/test_rule_labeler.py
  tests/test_weak_label_combiner.py
- uv run mypy src/rsna_knee/labels

Results: 31 targeted tests passed; full suite 595 passed in 20.64s;
Ruff check/format clean; strict mypy clean.

## Design decisions

- Section bodies are attached to a detected header whether or not that header
  ends its line, because normalized one-line headers are valid input.
- Uncertainty terms are matched as complete phrases so their prefixes are not
  independently downgraded before the full phrase is seen.
- Negation/uncertainty scope is deliberately sentence-local. Clause-level scope
  refinement is deferred until real failure modes justify it.
- Combiner confidence is source-agreement based; soft probability separately
  weights positive/negative votes by source priority and confidence. Unknown
  source types have no vote weight but remain visible as conflicts.

## Risks / limits

- Rule recall is bounded by the provisional ontology vocabulary; this package is
  a candidate label generator, not ground truth.
- No private reports were read, so real-world recall/precision is unmeasured.
- Human review remains mandatory before any derived label is treated as gold.
