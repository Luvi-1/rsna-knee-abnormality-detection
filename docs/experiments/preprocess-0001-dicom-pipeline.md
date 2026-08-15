# PREPROCESS-0001 — Deterministic DICOM-to-model pipeline

Status: **recovery iteration 8 inputs, smoke, Run A, and Run B passed; its protected row is terminal
`blocked` before comparison, and comparison and every review stage were not launched after two
frozen plan-contract P1s; the r9 D-027/D-028 exact 16-file candidate passed its first complete
release gate and D-015 requires the immediate identical post-governance rerun; fresh remote chain,
QA materialization, and visual review pending; Chunk 5 not passed**.

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
| Code | `feat/chunk-5-dicom-pipeline`; iteration-8 freeze `4958c4a` and bundle `09502a...` are superseded-pending by D-027/D-028; iteration-9 freeze/bundle pending |
| Source manifest | `audit-0002-manifest-remediation` / `manifest-v2`; superseded v1 rejected |
| Hard groups | `protected-groups-v2`; not used to construct folds |
| Labels | `official-labels-v1`; not consumed by preprocessing |
| Folds | `unassigned` |
| Preprocessing | `dicom-model-v1` |
| Model | None |
| Loss | Not applicable; no labels, optimization, or model exist |
| Augmentation | None |
| Seed | `20260809` |
| Compute estimate | Approval-gated private Kaggle CPU: one authenticated smoke with separate full-pass and post-comparison preparation estimates; two complete independent full-data passes; one later capacity-gated selected-series replay, double render, and representative 1/2/4/8-worker benchmark stage in the existing review-plan kernel; all stages retain the verified competition margin; no accelerator or paid external service |
| Expected information gain | Determine whether the full authorized input can be decoded and transformed with complete terminal accounting, byte-exact independent manifests and cohort plans, exact deterministic metrics, no systematic anatomical error in bound human review, and measured preprocessing costs compatible with the current runtime ceiling |
| Internet | Disabled |
| Training/inference/submission | Forbidden in this run |

## Registry state

The ignored private SQLite registry remains the authority for the experiment contract. Five
historical Run A rows are terminal failed and append-only: two stopped at source-manifest
boundaries, one at the former processing deadline, one after its full-data pass at the superseded
capped joint-material selector, and recovery iteration 6 at private cohort-plan validation. Recovery
iteration 7 is separately terminal failed at comparison-output validation.

D-026 passed its complete gate and produced iteration-8 freeze `4958c4a` / bundle `09502a...`.
Iteration 8 inputs, smoke, Run A, and Run B authenticated and passed. Run B version 1 reached
`COMPLETE` at 25,940 seconds; two independent bounded read-only polls 71 seconds apart agreed, and
the established authenticated validator returned
`dicom_qa_output_validation=PASS mode=workflow stage=run-b`. The protected registry row is
authoritatively terminal `blocked`: input, smoke, Run A, and Run B are `passed`; comparison,
`review_plan`, and `human_review` are `not_started`; `completed_utc` is set; and integrity, foreign
keys, and mode are `PASS`. UI/session creation and finalization were not launched. This is Run B
workflow-output validation only, not Chunk 5 PASS or comparison, determinism, QA, review,
performance, or finalizer evidence. Because D-027 and D-028 change frozen source, iteration-8
comparison and QA must never launch; the complete replacement immutable chain remains pending.

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
2. Run one authenticated pre-run smoke that exercises the production full-pass path and the post-
   comparison preparation path separately. Require conservative, independently recorded estimates
   for both stages before starting unusually large compute.
3. Execute distinct private Run A and Run B version-1 kernels. Each independently processes the
   entire authorized training set once, records every discovered study, series, and DICOM in exactly
   one terminal state, and emits a canonical manifest, deterministic metrics, and deterministic
   cohort plan. Each run exactly reconciles train-series membership, `source_row_count`, organizer
   `plane`, `fluid_sensitive`, and `fat_suppression` fields, plus every regular DICOM's keyed
   relative `file_key`, `file_size_bytes`, and `raw_file_exact_key` in authenticated `manifest-v2`.
4. Selector v3 uses exact incremental greedy selection with a minimum of 100 studies and no
   arbitrary study maximum. Continue until every required represented value quota is satisfied in
   bounded semantic registries, including bounded site-domain buckets. Do not compute or publish a
   legacy joint-material census. Physical file, byte, time, and disk gates fail closed. The only
   public registry-coverage token is
   `all_required_represented_registry_values_satisfy_quotas`.
5. Use the separate version-1 comparator to require byte-exact equality of both canonical manifests
   and cohort plans plus exact equality of deterministic metrics. Timing and resource fields are
   predeclared non-comparison fields; investigate every other mismatch.
6. In the existing review-plan kernel, authenticate the capacity certificate against the freeze,
   bundle, manifest, Run A, Run B, cohort plan, and renderer before pixel decode. Replay every
   selected series, render each twice, run representative decode/preprocessing/resource benchmarks
   once, and materialize the private review plan. Measure total runtime, decode, preprocessing,
   slot, QA, and cache phases; peak memory; disk/cache size; CPU utilization; files/series/studies
   throughput; and representative 1/2/4/8-worker scaling where technically reasonable. Include
   every eligible diagnostic series from each selected study. No new kernel or data reference is
   introduced.
7. Use the authenticated private review plan and safe UI template. The authorized human uses
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
8. Run the version-1 finalizer against the exact Run A, Run B, comparator, plan, and completed review
   session. It authenticates the complete private identity chain, derives completion from the
   private ledger, writes the required aggregate private completion/attestation inside Kaggle,
   requires every check terminal and zero `BLOCK`, and releases only approved disclosure-controlled
   determinism plus `human_review_summary.json` and `final_performance_report.json`; exact review
   counts remain private.

## Current recovery evidence

- Three earlier Run A attempts failed closed at source identity, source schema, and the former
  processing deadline. Their append-only registry rows and exact diagnosis remain historical; all
  associated freezes and bundles are superseded.
- The fourth Run A attempt authenticated its inputs and completed the full-data pass, then failed
  closed with `material_strata_coverage_impossible`. Run B was not started. The failure came from
  the superseded selector's legacy joint-material coverage contract and arbitrary cap, so no
  admissible Run A package, deterministic comparison, benchmark, review plan, or human-review
  evidence exists.
- The designated checkpoint reviewer classified the checkpoint `REMEDIATION REQUIRED` and advised
  two independent full-pass outputs with deterministic cohort plans, exact three-artifact
  comparison, one later QA preparation in the existing review-plan kernel, selector coverage over
  bounded semantic registries with no arbitrary maximum, and an identity-bound capacity
  certificate. D-023 records the adopted design.
- The iteration-6 replacement candidate passed its complete local gate and produced freeze
  `1c4470e` plus immutable bundle `9e6be8...`. Its private version-1 inputs and standalone smoke
  authenticated and passed, proving the D-024 wrapper-log correction remotely. Run A then failed
  closed with the privacy-classified `private_cohort_plan_invalid` result.
- Root-cause tracing found that `SelectedStudy` propagated legacy/internal `CohortStudy` dimensions
  into a plan schema that permits exactly 25 registry dimensions. The same trace found a latent
  cohort-binding defect: representative series were chosen from all globally eligible series rather
  than the selected studies. The smallest two-file fix filters serialized dimensions through the
  existing exact registry, selects the cohort first, and restricts representative profiles to it.
  All 46 full-run tests, Ruff check/format, strict mypy on both files, and the diff check passed.
  D-025 then passed its complete exact-set gate and produced iteration-7 freeze `e3c6334` / bundle
  `5fe504...`.
- D-026 passed its complete exact-set gate with pytest 528/528 and produced iteration-8 freeze
  `4958c4a` / bundle `09502a...`. Its private inputs, standalone smoke, and full-data Run A
  authenticated and passed. Run B version 1 reached `COMPLETE` at 25,940 seconds; two independent
  bounded read-only polls 71 seconds apart agreed, and authenticated workflow-output validation
  passed. The protected registry row is terminal `blocked` before comparison.
- Before comparison launch, frozen-source preflight found that the finalizer requires six artifacts
  and permits `orthogonal.png` only when renderable while the validator required exactly seven. It
  also found that automatic materialization emits `dicom_qa_review_started`, four
  `dicom_qa_plan_progress` events, and `dicom_qa_review_template_complete`, while the validator
  expected generic run boundaries. Comparison, review-plan materialization, UI/session, human
  review, and finalization were not launched.
- D-027 changes only the shared output validator and its packaging regression file. It binds
  artifact validation to the finalizer's exact six required suffixes and sole optional orthogonal
  suffix, and validates the actual automatic event sequence while preserving all output-layout and
  privacy rejections. Focused checks pass 9/9, packaging passes 147/147, Ruff check and format pass,
  strict validator mypy passes, and an independent red-team returns PASS with no P0/P1. The
  correction is included in the r9 first complete release-gate PASS. The new freeze/commit, bundle,
  and full replacement remote chain remain pending; r8 results cannot be spliced into r9.
- D-028 closes a separate material-drift checker P1. The checker omitted `efficiency_prize`,
  `external_assets`, `team_and_sharing`, `license`, `winner_obligations`, and `ambiguities`, so a
  mutation or wholesale removal could yield `contract_drift=no`. The minimal root fix adds those six
  names to the existing `MATERIAL_SECTIONS` and extends `tests/test_smoke.py`; it adds no dependency
  or abstraction. Smoke passes 6/6; the combined focused set passes 155/155; Ruff/format, mypy over
  25 source plus nine trust-boundary files, independent current-source `contract_drift=no`, and
  post-fix red-team PASS/no P0/P1 all pass. The r9 exact 16-file candidate passed its first complete
  release gate on staged tree `ed3720d8159b1242a6b72cab13dec43a4406f25a`: pytest 529/529;
  isolated wheel build/install/import; Ruff check and format; mypy over the package plus nine trust-
  boundary files; pre-commit; secret and privacy checks; dependency audit; contract schema and
  current `contract_drift=no`; exact inventory; and unchanged-tree checks. This governance
  reconciliation changes that staged tree, so D-015 requires the main agent to restage and
  immediately rerun the identical complete gate. If that rerun succeeds, the final release record
  is `complete_final_gate=PASS`; any failure invalidates this record and must be corrected.
- The checkpoint relay could not connect to Chrome, so no new reviewer response or decision exists.
  The user's standing Chunk 5 authorization remains controlling.
- A broad search of ignored local artifacts printed obsolete canary sentinel strings, local
  artifact paths, commit and bundle hashes, and the public competition slug into an internal tool
  transcript. It printed no credentials, key bytes, authentication tokens, pixels, DICOM headers,
  reports, or patient, study, or series identifiers. The search stopped immediately; there was no
  repository or user-facing disclosure. The next fresh bundle must rotate its canary and private
  identities, and future ignored-artifact searches must use exact bounded allowlists.

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
  raw-digest population, and match each other byte for byte for the canonical manifests and cohort
  plans and exactly for deterministic metrics.
- The performance report is complete and stays within the approved Kaggle runtime/memory limits.
- The authenticated smoke separately admits full-pass and post-comparison preparation capacity;
  both runs retain the complete safe progress sequence and competition margin, and the existing
  review-plan kernel passes its identity-bound physical file, byte, time, and disk gates. Projection
  alone is not runtime acceptance.
- At least 100 private studies have complete visual-review rows with no systematic ordering,
  orientation, inversion, laterality, clipping, or aspect error;
  `all_required_represented_registry_values_satisfy_quotas` is validated and every eligible series
  for each reviewed study is covered.
- Every private input and kernel passes authenticated ready/private/offline, exact-source,
  exact-version, exact-listing, and identity checks; the finalizer binds the completed private
  review session directly to the exact runs, comparison, plan, UI parent, cohort, preprocessing,
  bundle, and source manifest.
- Every private review group has the finalizer's exact six mandatory artifacts and no artifact other
  than the optional `orthogonal.png`; the safe log has the exact automatic review start, four plan-
  progress, and template-completion events.
- Sanitized outputs pass their exact allowlist and disclose no identifiers, pixels, paths, private
  checksums, rare categories, credentials, or private resource locators.

## Kill criteria

- Any unexplained DICOM case, unsupported recoverable syntax, ambiguous ordering, implicit
  horizontal flip, unrecorded geometry/intensity transform, checksum mismatch, nondeterministic
  repeat, private-output leak, systematic visual defect, or runtime-budget failure blocks
  `dicom-model-v1` and all downstream work.
- Any need to change labels, construct folds, train, infer, ensemble, or submit stops this chunk.

## After recovery iteration 8

Chunk 5 recovery continues through iteration 9. Iteration 8 authenticated and passed inputs, smoke,
full-data Run A, and full-data Run B. Run B version 1 reached `COMPLETE` at 25,940 seconds; two
independent bounded read-only polls 71 seconds apart agreed, and the validator returned
`dicom_qa_output_validation=PASS mode=workflow stage=run-b`. Its protected registry row is terminal
`blocked`, with comparison, `review_plan`, and `human_review` `not_started`, `completed_utc` set, and
integrity, foreign keys, and mode `PASS`. Frozen-source preflight blocked comparison and every
review stage before launch because the artifact-suffix and automatic-event contracts each contained
a P1 producer/consumer mismatch. This is not Chunk 5 PASS, comparison, determinism, QA, review,
performance, or finalizer evidence. Because D-027 and D-028 change source, iteration-8 comparison
and QA must never launch. Restage this governance reconciliation and immediately rerun the identical
complete gate under D-015; a successful rerun fixes the final record at
`complete_final_gate=PASS`, while any failure invalidates the record and must be corrected. Then
replace the freeze/commit, bundle, and private version-1 dataset chain and rerun the entire private
chain before recording downstream evidence. Do not start ontology, folds, labels, training,
inference, or submission.
