# PREPROCESS-0001 — Deterministic DICOM-to-model pipeline

Status: **r10 input, performance smoke, Run A, Run B, and comparison authenticated and passed;
review-plan v1 then failed safely with only `input_discovery_invalid`; r10 is terminal failed and
cannot be resumed or spliced; D-031 red-team, focused/static checks, and its first exact staged gate
pass, but the required identical restaged gate, a fresh r11 chain, QA materialization, human review, and finalizer remain pending; Chunk 5 not
passed**.

Current recovery addendum (2026-08-20): the no-drift contract refresh is frozen at
`2723ff4a1692d5d897234e67aba167c629017f9b`; replacement bundle
`efe087afd5bb8f5391213e359c52b88f5930975c837b813ee98affe3f1fb9921` passed local packaging and
verified-policy gates. Append-only r12 is `planned`, all remote stages are `not_started`, and no
r12 remote dataset, kernel, run, output, or pixel exists. The prior r11 candidate is historical;
no reuse or splice is permitted. The next safe action is a protected metadata-only derived
performance-smoke identity absence check before any version-1 push.

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
| Code | `feat/chunk-5-dicom-pipeline`; freeze `2723ff4`; r8/r9/r10 and the old r11 candidate are terminal historical evidence only; r12 replacement bundle is local and remote stages are not_started |
| Source manifest | The sanitized audit-0003 successor remains the authenticated source root; audit-0002 remains historical scientific evidence only; r12 must bind the exact source without splicing r10/r11 stages |
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

R9 freeze `1db805e` passed the exact 529/529 gate and bundle `28457d...` passed every non-content
check. Before upload, final content inspection found pinned upstream `pydicom 3.0.2` aggregate 104
`.dcm` members and 188 standard DICM-preamble members. The bundle was rejected; no r9 remote
artifact exists. The protected r9 registry row is terminal `blocked`, every remote stage is
`not_started`, and the reason is `dependency_wheel_medical_payload_detected`.

R10 input authentication, performance smoke, Run A, Run B, and exact comparison each passed. The
review-plan version-1 kernel then reached `ERROR`; two bounded read-only checks 93 seconds apart
agreed. The frozen privacy/canary failure validator passed and released only
`input_discovery_invalid`. No review artifact, pixel, UI/session, human review, or finalizer stage was
accessed or created. The protected r10 registry row is terminal `failed`; no r10 stage may be resumed
or spliced into r11.

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

1. Complete `audit-0003-wheel-sanitization`, then freeze one clean, dependency-locked, offline
   DICOM-QA bundle and authenticate its cryptographic binding to that audit's validated
   `manifest-v2` private source outputs. Audit-0002 may not be reused as the source root.
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
  correction passed in r9 freeze `1db805e`; the later dependency-wheel content rejection is
  separate.
- D-028 closes a separate material-drift checker P1. The checker omitted `efficiency_prize`,
  `external_assets`, `team_and_sharing`, `license`, `winner_obligations`, and `ambiguities`, so a
  mutation or wholesale removal could yield `contract_drift=no`. The minimal root fix adds those six
  names to the existing `MATERIAL_SECTIONS` and extends `tests/test_smoke.py`; it adds no dependency
  or abstraction. Smoke passes 6/6; the combined focused set passes 155/155; Ruff/format, mypy over
  25 source plus nine trust-boundary files, independent current-source `contract_drift=no`, and
  post-fix red-team PASS/no P0/P1 all pass. The correction passed in r9 freeze `1db805e`; the later
  dependency-wheel content rejection is separate.
- D-029 implements the sanitizer only in `scripts/package_manifest_bundle.py` and
  `tests/test_manifest_packaging.py`. The existing shared `package_manifest_bundle` path uses the
  standard library to remove the general test tree plus any `.dcm`, `.dicom`, or standard
  DICM-at-byte-128 member, regenerate wheel `RECORD` deterministically, validate every other wheel
  fail-closed, and preserve runtime modules, metadata, licenses, and offline preflight. The first
  r10 candidate passed on exact staged tree
  `5bea3c110e100e9ddd2d94c8b89c29e1f0ff82a0`: pytest 530/530; isolated wheel
  build/install/import; Ruff check/format; mypy over 25 source and nine trust-boundary files;
  audit/configuration/submission; contract schema and current `contract_drift=no`; pre-commit;
  privacy checks; `pip-audit`; exact inventory and unchanged-tree checks. D-030 preflight
  superseded that gate: the project wheel and skippable deployment stages were not under the shared
  wheel/`RECORD` guard; the local kernel lacked an exact two-file/hash upload allowlist; remote
  dataset/kernel version-1 content, sources, listings, and race stability were incompletely bound;
  status and credential paths were too broad; and safe sibling metadata/wheels could be accepted
  outside the verified bundle-manifest root.
- The minimal D-030 correction extends the project-wheel guard and adds one deployment authenticator
  that directly reuses the existing DICOM-QA version-1 helpers. Before network access, every stage
  verifies the exact local two-file kernel/hash, all wheels/`RECORD`, dataset metadata under the
  exact bundle-manifest parent, and kernel metadata under its exact sibling kernel directory.
  Remote gates authenticate exact private dataset version-1 content/hashes, exact kernel version-1
  code/source graph, stable listings, and before/after race snapshots. The runbook emits only fixed
  authentication or `PENDING`/`RUNNING`/`COMPLETE`/`ERROR` tokens and uses a command-scoped token,
  protected logs, explicit `/1`, and bracketed gates. No dependency, framework, or abstraction was
  added. The mismatched-root regression proves zero remote calls, and independent authentication
  and runbook red-teams pass with no P0/P1. The first complete exact 24-file D-015 gate passed on
  tree `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260` with pytest 537/537 and every recorded
  lock/build/import, static, configuration, contract, privacy, dependency, inventory, and
  unchanged-tree check. This reconciliation changes bytes, so an immediate identical fully
  restaged rerun is required; its PASS fixes `complete_final_gate=PASS`. Existing DICOM-QA
  source-audit constants and fixtures are rebound to audit-0003.
- D-031 records that the r10 source graphs were exact but the shared global basename walk entered the
  legitimate greater-than-4,096-study competition tree before source selection. The correction
  changes only `kaggle/dicom_qa/finalize_review.py` and its focused identity regression: base search
  stops at depth 1 and kernel search starts at the exact derived mount, preserving symlink,
  duplicate, count, file-type, and error gates. Independent red-team passes with no P0/P1; focused
  identity 41/41, boundary matrix 12/12, combined identity plus packaging 188/188, full development
  pytest 537/537, Ruff/format, strict finalizer mypy, and the scoped diff check pass. The first exact
  staged D-015 gate passed on tree `959f14e9422db9670d16683ba8effe681cf6641d` over exactly 10 files:
  locked offline reinstall/lock; isolated wheel build/install/import; tracked MIME/symlink and
  sensitive guards; Ruff/format; mypy over 25 package plus 11 trust-boundary files; pytest 537/537;
  config/synthetic-submission; protected current contract/schema and generated-schema byte checks;
  pre-commit/detect-secrets; `pip-audit` with no vulnerabilities; cached diff, exact inventory, and
  unchanged-tree PASS. This governance reconciliation changes bytes, so one immediate identical
  fully restaged rerun must PASS to fix the final gate as passed; failure invalidates and must
  correct this record.
- The checkpoint relay could not connect to Chrome, so no new reviewer response or decision exists.
  The user's standing Chunk 5 authorization remains controlling.
- A broad search of ignored local artifacts printed obsolete canary sentinel strings, local
  artifact paths, commit and bundle hashes, and the public competition slug into an internal tool
  transcript. It printed no credentials, key bytes, authentication tokens, pixels, DICOM headers,
  reports, or patient, study, or series identifiers. The search stopped immediately; there was no
  repository or user-facing disclosure. The next fresh bundle must rotate its canary and private
  identities, and future ignored-artifact searches must use exact bounded allowlists.

## Private dataset pre-push gate

Before pushing or accepting any consuming kernel, D-030 must bind resolved dataset metadata to the
exact verified bundle-manifest parent and kernel metadata to its exact sibling kernel directory
before network access. Authenticated metadata must then show that every input and kernel is private,
offline, ready, at exact expected version 1, attached only to the frozen sources, and backed by a
complete exact-size/hash listing plus stable before/after snapshots. Version 2 must be absent. Extra or missing
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

## After r10 review-plan input-discovery failure

R8, r9, and r10 remain terminal historical evidence and must never resume or be spliced. R10 proves
the authenticated chain only through comparison; its review-plan failure produced no QA artifact or
pixel access. Preserve the first exact staged D-015 PASS as non-final evidence and run the immediate
identical fully restaged gate, then freeze a new r11 only after its PASS fixes
the final gate as passed. Execute every stage in that new bundle sequentially from input
authentication through review-plan, human
review, and finalization. Do not delete or reuse old remote artifacts or start ontology, folds,
labels, training, inference, or submission. Chunk 5, QA, all downstream work, and Chunk 6 remain
blocked.
