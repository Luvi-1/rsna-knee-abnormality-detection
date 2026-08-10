# PREPROCESS-0001 — Deterministic DICOM-to-model pipeline

Status: **Run A recovery in progress; complete replacement-candidate gate passed; private execution
and visual review not complete; Chunk 5 not passed**.

## Objective

Implement and validate `dicom-model-v1`, a deterministic, physically grounded MRI-series pipeline
that decodes heterogeneous DICOM safely, preserves laterality, records every geometric and intensity
transformation, and produces model-ready tensors without starting ontology, fold, or model work.

## Experiment contract

| Field | Frozen value |
|---|---|
| ID | `preprocess-0001-dicom-pipeline` |
| Hypothesis | Geometry-first ordering, explicit decode/intensity handling, and fixed physical-position sampling can produce byte-deterministic model inputs across heterogeneous MRI series without systematic ordering, orientation, or laterality errors. |
| Primary change | Add the first DICOM-to-model preprocessing version and its private QA runner. |
| Code | `feat/chunk-5-dicom-pipeline`; predecessor freeze `a5a44ac` is superseded-pending and the replacement freeze is not yet created |
| Source manifest | `audit-0002-manifest-remediation` / `manifest-v2`; superseded v1 rejected |
| Hard groups | `protected-groups-v2`; not used to construct folds |
| Labels | `official-labels-v1`; not consumed by preprocessing |
| Folds | `unassigned` |
| Preprocessing | `dicom-model-v1` |
| Model | None |
| Loss | Not applicable; no labels, optimization, or model exist |
| Augmentation | None |
| Seed | `20260809` |
| Compute estimate | Approval-gated private Kaggle CPU: two complete full-data runs, each bounded by a 21,600-second self-deadline and 23,400-second outer kill, plus representative 1/2/4/8-worker profiles where available; no accelerator or paid external service |
| Expected information gain | Determine whether the full authorized input can be decoded and transformed with complete terminal accounting, exact independent replay, no systematic anatomical error in stratified human review, and a measured preprocessing contribution compatible with the current runtime ceiling |
| Internet | Disabled |
| Training/inference/submission | Forbidden in this run |

## Registry state

The ignored private SQLite registry remains the authority for the experiment contract. Predecessor
freeze `a5a44ac` and bundle `7cf43...` reached private Run A but are superseded-pending after that run
failed early with the sanitized code `source_manifest_version_mismatch`. No successful run result or
completion time may be recorded from that attempt. Run B, comparison, human review, and attestation
remain `not_started`. The replacement freeze and bundle are pending after the complete local gate;
record actual results only after authenticated successful execution.

## Frozen controls

- The existing strict pydicom container, transfer-syntax, geometry, and failure taxonomy remains the
  shared decode boundary.
- `ImageOrientationPatient` plus `ImagePositionPatient` is authoritative for slice ordering.
  `InstanceNumber` is a flagged fallback and is blocked for model promotion by default. Filenames
  are never ordering evidence.
- DICOM LPS geometry is recorded explicitly. Slice direction is canonicalized by physical axis;
  native in-plane pixels are not horizontally flipped by default.
- Laterality is preserved as supplied and is never inferred from pixels, filenames, or side-specific
  labels. No medial/lateral transformation is authorized.
- Rescale slope/intercept precedes MONOCHROME1 inversion, series-level clipping, normalization, and
  optional channel construction.
- Only in-plane resizing may be configured. No through-plane interpolation or isotropic-detail
  fabrication is permitted.
- Private QA pixels, paths, identifiers, case diagnostics, checksums, and review rows remain inside
  the authorized Kaggle environment.

## Private QA and benchmark plan

1. Freeze one clean, dependency-locked, offline bundle and authenticate its cryptographic binding
   to the completed `audit-0002-manifest-remediation` / `manifest-v2` private source outputs.
2. Execute distinct private Run A and Run B version-1 kernels. Each starts from source, independently
   processes the entire authorized training set, and records every discovered study, series, and
   DICOM in exactly one terminal state together with private decode, order, slot, quality,
   normalization, sampling, transform, checksum, cache, and failure evidence. Each run also exactly
   reconciles train-series membership, `source_row_count`, and organizer `plane`, `fluid_sensitive`,
   and `fat_suppression` fields. Every regular DICOM must match its keyed relative `file_key`,
   `file_size_bytes`, and `raw_file_exact_key` in authenticated `manifest-v2`.
3. Use a separate version-1 comparator to require byte-exact equality of the canonical
   deterministic manifests and exact equality of deterministic aggregate metrics. Timing and
   resource fields are predeclared non-comparison fields; investigate every other mismatch.
4. Measure total runtime, decode, preprocessing, slot, QA, and cache phases; peak memory; disk/cache
   size; CPU utilization; files/series/studies throughput; and representative 1/2/4/8-worker scaling
   where technically reasonable without repeating the full dataset unnecessarily.
5. After the full pass, run `qa-cohort-selection-v2` across the complete eligible population.
   Select at least 100 reviewable studies and every materially represented available stratum, then
   include every eligible diagnostic series from each selected study. Generate contact sheets,
   physically meaningful orthogonal views, intensity histograms, slice-order animations, metadata
   summaries, and before/after panels privately.
6. Create the authenticated private review plan and safe UI template. The authorized human uses
   Chrome Copy & Edit to create a distinct private review-session version 1, enters `START` before
   any artifact access, and records the frozen checks `slice_order`, `anatomical_orientation`,
   `laterality_preservation`, `no_unintended_mirroring`, `intensity_polarity`,
   `anatomy_not_clipped`, `sequence_slot_assignment`, `preprocessing_appearance`, and
   `duplicate_missing_abnormal_handling` as `PASS`, `BLOCK`, or `NOT_APPLICABLE`. Codex must not
   view or receive private pixels, rows, paths, identifiers, hashes, or the detailed ledger. Before
   deciding, the human sees plan-bound `organizer_plane`, `physical_plane`, `assigned_slot`,
   `retention_reasons`, the six-boolean `missing_series_mask`, and ordinal-ordered `sibling_series`
   records with `series_ordinal`, `slot`, `terminal_state`, `model_eligible`, `retention_reasons`, and
   `quality_blocked_reasons`; artifacts resolve only under authenticated Run A.
7. Run the version-1 finalizer against the exact Run A, Run B, comparator, plan, and completed review
   session. It authenticates the complete private identity chain, derives completion from the
   private ledger, writes the required aggregate private completion/attestation inside Kaggle,
   requires every check terminal and zero `BLOCK`, and releases only approved disclosure-controlled
   determinism plus `human_review_summary.json` and `final_performance_report.json`; exact review
   counts remain private.

## Current recovery evidence

- The predecessor implementation freeze was `a5a44ac`, with immutable bundle identity recorded only
  as the sanitized prefix `7cf43...`. Both are superseded-pending because source code changed after
  the failed attempt; they cannot support a Chunk 5 pass.
- Private Run A stopped before DICOM preprocessing, QA generation, and benchmarking with the fixed
  sanitized code `source_manifest_version_mismatch`. Run B was not started. No private image,
  identifier, path, report, detailed hash, or resource reference left Kaggle.
- Root cause was a namespace conflation: the promoted governance audit ID and the source producer's
  execution ID were both represented by the name `audit_id`, and the consumer compared the database
  producer value with the governance constant.
- The two-file correction preserves the outer governance identity while authenticating the producer
  tuple through the already bound code commit, full source-bundle hash, producer-ID derivation,
  common owner, and exact derived source references. It passed 32 focused tests plus Ruff and strict
  mypy. The exact 12-file staged replacement candidate then passed the complete 404-test, isolated-
  wheel, typing, privacy, security, dependency, contract, and clean-tree gate.
- A new clean freeze and immutable bundle, input authentication, and a fresh Run A retry remain
  pending. Run B, comparison, visual review, finalization, push, and hosted CI remain pending.

## Private dataset pre-push gate

Before pushing or accepting any consuming kernel, authenticated metadata must show that every input
and kernel is private, offline, ready, at exact expected version 1, attached only to the frozen
sources, and backed by a complete exact-size/hash listing. Version 2 must be absent. Extra or missing
files, unavailable sizes, ambiguous pagination, a changed version, an unexpected source, a public
state, internet access, a symlink/path escape, or any identity mismatch blocks execution. Private
resource references, URLs, identifiers, hashes, and paths remain in ignored mode-0600 state or
inside Kaggle and never enter repository documents or command output.

## Promotion criteria

- Every required synthetic fixture and existing regression passes.
- Every input study, series, and DICOM reaches an explicit terminal state; unexpected decoder,
  parser, geometry, or provenance states fail closed.
- Both independent full private runs cover the entire authorized training set, reconcile all
  discovered entities to terminal states, exactly match the authenticated source series/file/size/
  raw-digest population, and match each other for every declared deterministic artifact and
  aggregate.
- The performance report is complete and stays within the approved Kaggle runtime/memory limits.
- At least 100 private studies have complete visual-review rows with no systematic ordering,
  orientation, inversion, laterality, clipping, or aspect error; every represented material stratum
  and every eligible series for each reviewed study is covered.
- Every private input and kernel passes authenticated ready/private/offline, exact-source,
  exact-version, exact-listing, and identity checks; the finalizer binds the completed private
  review session directly to the exact runs, comparison, plan, UI parent, cohort, preprocessing,
  bundle, and source manifest.
- Sanitized outputs pass their exact allowlist and disclose no identifiers, pixels, paths, private
  checksums, rare categories, credentials, or private resource locators.

## Kill criteria

- Any unexplained DICOM case, unsupported recoverable syntax, ambiguous ordering, implicit
  horizontal flip, unrecorded geometry/intensity transform, checksum mismatch, nondeterministic
  repeat, private-output leak, systematic visual defect, or runtime-budget failure blocks
  `dicom-model-v1` and all downstream work.
- Any need to change labels, construct folds, train, infer, ensemble, or submit stops this chunk.

## After attempted Run A

Recovery pending. Run A failed closed before preprocessing with the sanitized source-manifest
identity error; Run B was not started. No successful runtime result, Run A/Run B comparison, QA image
review, completed review session, human attestation, or finalizer result is claimed. The incident is
recorded in `docs/postmortems/chunk-5-dicom-pipeline.md`. Record replacement identities and actual
results only after the new freeze/bundle, authenticated retry, independent Run B, comparison, and
review. Do not start ontology, folds, labels, training, inference, or submission.
