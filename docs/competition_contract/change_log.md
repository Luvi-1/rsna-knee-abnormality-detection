# Competition Contract Change Log

## 2026-08-10T07:19:35Z

Chunk 5 recovery refresh before the replacement freeze, private bundle, and Run A retry:

- The authenticated official API returned exactly one entered competition match, the unchanged
  2026-10-22T23:59:00Z deadline, five submissions currently available, and zero submissions.
- All nine official competition-page content fingerprints and the incorporated MIRA PDF
  fingerprint still match the immediately previous snapshot and canonical contract exactly.
- The five official host clarification topics remain available.
- Rules, data interface, evaluation, timeline, runtime, submission/team limits, external-asset
  requirements, sharing restrictions, licensing, and winner obligations have no material drift.
- Identity verification remains unavailable from the API, so the last directly observed
  incomplete state continues to block submissions and prize eligibility, not the authorized
  private Chunk 5 preprocessing/QA compute.
- The replacement private Run A/Run B and human-QA preparation remain allowed under the existing
  privacy and fail-closed DICOM controls. No rules acceptance, submission, team action, data
  preview, compute launch, publication, or remote mutation occurred during this refresh.

## 2026-08-09T03:00:03Z

Chunk 5 preflight before deterministic DICOM preprocessing implementation and private QA:

- All nine official competition-page fingerprints and the incorporated MIRA PDF fingerprint
  still match the immediately previous snapshot and canonical contract exactly.
- The official API still reports one entered competition match, the final deadline at
  2026-10-22T23:59:00Z, and five submissions available now.
- The five official host clarification topics remain available and still cover CSV `PatientSex`
  removal, the unpublished 86-tag DICOM allowlist, full-notebook runtime, and unavailable test
  reports.
- Rules, data interface, evaluation, timeline, runtime, submission/team limits, external-asset
  requirements, sharing restrictions, licensing, and winner obligations have no material drift.
- Identity verification is not exposed by the API, so the last directly observed incomplete state
  remains the fail-closed submission and prize gate.
- Synthetic-local implementation and bounded private Kaggle QA/benchmarking are allowed under the
  existing privacy and fail-closed DICOM controls. No rules acceptance, submission, team action,
  data preview, compute launch, publication, or remote mutation occurred during this refresh.

## 2026-08-08T22:03:12Z

Checkpoint 1 remediation refresh before rebuilding and rerunning the private manifest audit:

- All nine official Kaggle page-content SHA-256 values and the incorporated MIRA PDF SHA-256
  still match the canonical contract exactly.
- The official API still reports the singular competition identity, notebook-only submissions,
  the 2026-10-22T23:59:00Z deadline, five submissions available now, and an unchanged root data
  inventory of 819,640 files: 819,635 DICOM files and five CSV files.
- The account remains entered. The API does not expose identity-verification state, so the last
  directly observed incomplete state remains the fail-closed submission and prize gate.
- Rules, data interface, metric, runtime, team and submission limits, external-asset rules,
  sharing constraints, licensing, and winner obligations have no material drift.
- No rules acceptance, submission, team action, data preview, or remote mutation occurred during
  the refresh.

## 2026-08-08T04:19:27Z

Pre-run revalidation for the private Chunk 4 manifest audit:

- All nine official Kaggle page-content SHA-256 values and the incorporated MIRA PDF SHA-256
  still match `contract.yaml` and `2026-08-08T025148Z.md` exactly.
- Rules, data interface, evaluation, timeline, offline runtime, submission/team limits,
  external-asset rules, sharing constraints, licensing, and winner obligations have no material
  drift.
- The account remains entered with rules already accepted. Identity verification remains
  incomplete, blocking submissions and prize eligibility but not this private aggregate-only CPU
  audit.
- No rules acceptance, submission, team action, data preview, or remote mutation occurred during
  the refresh.

## 2026-08-08T02:51:48Z

Compared with `2026-08-08.md` before the Chunk 4 full-data audit:

- All nine official Kaggle page-content SHA-256 values and the incorporated MIRA PDF SHA-256 are
  unchanged.
- Targets, metric, deadlines, runtime limits, submission limits, team size, data inventory,
  external-asset rules, sharing rules, license constraints, and winner obligations are unchanged.
- The authenticated account remains entered with rules already accepted; identity verification
  remains incomplete and blocks submissions/prize eligibility, not this private aggregate-only CPU
  manifest audit.
- No rules acceptance, submission, team action, data preview, or compute action occurred during the
  refresh.

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
