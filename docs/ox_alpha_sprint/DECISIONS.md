# OX Alpha Sprint Decisions

## D-S1. Isolated worktree over in-place edits

- Date: 2026-08-22. Base: d3771e7.
- Decision: new git worktree at ../kaggle-ox-alpha on branch ox-alpha/rsna-seven-day-acceleration.
- Reason: mission requires zero interference with active Chunk 5 chain.

## D-S2. Partial CLI contract refresh recorded honestly

- Date: 2026-08-22.
- Decision: create a STALE/PARTIAL snapshot rather than fabricating a clean refresh verdict.
- Reason: MCP transport rejected; CLI provided aggregate-safe facts only; rendered HTML is not
  fingerprint-comparable to canonical extraction pipeline.

## D-S3. CLI file listing incident disclosed immediately

- Date: 2026-08-22.
- Decision: stop further file listings; record exposure in snapshot and risk register.
- Reason: identifier-bearing paths entered internal transcript despite aggregate-only intent.

## D-S4. Reuse existing interfaces before writing new code

- Date: 2026-08-22.
- Decision: build on PreprocessingConfig, PrimarySeriesSlot, SeriesSlotAssignment,
  TransformationLedger, OutputProvenance rather than duplicating.
- Reason: proven tested interfaces exist in src/rsna_knee/dicom/pipeline.py and data/series_slots.py.
