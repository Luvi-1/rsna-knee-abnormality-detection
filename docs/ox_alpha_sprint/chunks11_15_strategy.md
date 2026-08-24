# Chunks 11–15 — Strategy overview

Date: 2026-08-22.

## Chunk 11 — Packaging and validation (DONE)

Bundle packaging with provenance manifest and CSV output validator. This is the
gate that prevents malformed submissions from reaching Kaggle quota.

## Chunk 12 — Notebook scaffold (DONE)

Thin synthetic-only notebook proving the pipeline plumbing end-to-end. Real-data
notebooks will follow the same pattern but require authenticated data access.

## Chunk 13 — Label quality audit on synthetic fixtures (NEXT)

- Run the weak-label framework against the ontology's 12 targets using a
  hand-built corpus of ~50 synthetic reports covering all four states per target.
- Measure rule recall/precision against known ground truth; flag any target where
  recall < 0.9 for human review before real data is touched.
- Deliverable: docs/ox_alpha_sprint/label_quality_audit.md with per-target table.

## Chunk 14 — Experiment portfolio execution plan (PENDING)

- Select top 5 experiments from the ranked portfolio that are runnable on Kaggle
  within 9-hour inference ceiling.
- For each: write experiment contract, estimate compute, define promotion and
  kill criteria, identify which fold version and label version it depends on.
- No compute is spent until all five contracts are reviewed together.

## Chunk 15 — Red team and final gate (BLOCKING)

- Independent adversarial review of every module written in chunks 7–12.
- Full gate suite: pytest, Ruff check/format, mypy strict, secret scan,
  dependency audit, sensitive-file guard.
- Verify no private data was read at any point; confirm all test inputs are
  synthetic or public metadata only.
- Produce FINAL_HANDOFF.md with objective, evidence, decisions, risks, and the
  single recommended next chunk for the active workspace owner.
