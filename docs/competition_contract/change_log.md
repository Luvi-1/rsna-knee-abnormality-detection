# Competition Contract Change Log

## 2026-08-08

Compared with `2026-08-07T233859Z.md`:

- Added `contract.yaml` as the single machine-readable operational contract and
  `configs/competition.yaml` as its only project pointer.
- Target order, macro-AUC formula, deadlines, nine-hour CPU/GPU limits, daily/final submission
  limits, maximum team size, displayed data size, and total file count are unchanged.
- Replaced the prior narrative `train.csv` description with the verified current header: ID,
  report, and 12 targets. `PatientSex` is not in that CSV.
- Confirmed from a Competition Host that reports are unavailable in the scoring test interface.
- Added exact aggregate metadata-file byte sizes and current training study/series row counts.
- Formalized nine official-source contradictions as private GitHub issues #1–#9, each with a source
  authority and conservative default.
- Added fail-closed unknowns for degenerate-label scorer behavior, exact DICOM tag names, and exact
  accelerator hardware.
- Preserved the distinct public start and API activation timestamps without deriving deadlines from
  either field.
- Added page-content and MIRA PDF fingerprints and a material drift checker.
- Removed time-varying team/participant/submission counts from the operational contract; they are
  observations, not stable constraints.
