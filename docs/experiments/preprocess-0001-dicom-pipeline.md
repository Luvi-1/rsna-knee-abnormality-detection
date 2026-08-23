# PREPROCESS-0001 — Deterministic DICOM-to-model pipeline

Status: **r14 inputs, performance smoke, Run A, Run B, and deterministic comparison authenticated
PASS; review-plan v1 terminal failed before replay with safely validated `phase=review`,
`code=input_discovery_invalid`; four-file recovery candidate passes focused and complete DICOM-QA
checks; complete release gate, fresh immutable successor, QA materialization, human review, and
finalizer remain pending; Chunk 5 not passed**.

Current r14 recovery addendum (2026-08-22): Run A completed in 7h21m20s and Run B in 6h36m06s;
both exact validators and the deterministic comparison validator passed. Review-plan v1 returned
stable terminal `ERROR` before cohort replay. A no-match retrieval preserved the privacy boundary.
The frozen failure consumer rejected the review producer protocol; the minimal correction now
recognizes the exact review start, ordered plan-progress prefix, and review-failed event and safely
classifies the retained log. Official Kaggle supports direct and collision-safe owner-qualified
mount roots; discovery now considers only those two exact derived roots and requires exactly one.
R14 is terminal failed with human review `not_started`; no v2, retry, UI, finalizer, submission, or
Chunk 6 action occurred.
Official snapshot `docs/competition_contract/2026-08-22T062926Z.md` records no material drift.
Exact staged tree `b9cf3ab0b5494e1bc85f1cd498b1108d1e7f20b0` passed the first complete 13-file
D-015 gate: pytest 539/539, offline build/install/import, Ruff/format, strict mypy, configuration and
submission, contract/schema/no-drift, generated schema, privacy/MIME/secrets, zero-vulnerability
dependency audit, exact inventory, and no residue. Release rule: only an identical complete rerun
and final red-team PASS on the fully restaged tree containing these governance bytes, with no later
byte change, fixes `complete_final_gate=PASS`. No successor freeze or bundle exists as of this
record.

Current recovery addendum (2026-08-21): legacy Kaggle authentication was restored without exposing
credential material. One bounded authenticated check proved the exact r13 performance-smoke version
1 terminal `ERROR`. The corrected strict validator binds the smoke producer's exact event and phase
state machine and exposes only the fixed safe failure classification above. Its one progress event
localizes failure to the inner throughput gate. The old monolithic admission formula survived the
standalone-smoke split and double-counted sample elapsed time; the correction removes only that stale
term while preserving setup accounting, full projection, reserve, deadlines, and privacy/source
gates. The registry is terminal
`failed`: input authentication passed; Run A, Run B, comparison, review-plan, and human review are
`not_started`. No rerun, splice, Run A, or downstream launch occurred. The historical candidate was
exactly 15 files: six source/tests, eight governance files, and
`docs/competition_contract/2026-08-21T200304Z.md`; identity-verification state is unavailable and
remains fail closed. Exact 15-file tree `afd8909a798d30fa9314fe6568768bca68fbda14` passed its
complete D-015 gate with pytest 538/538 and all recorded checks but is historical and superseded.
After the governance bytes were restaged, exact tree
`e298964891b214bfbf4dc06725f2cde3b3bd3f74` failed the mandatory pytest rerun with one failure and
537 passes because a manifest-runner test compared nondeterministic real wall-clock
`runtime.elapsed_seconds` (3 seconds versus 2). Production uses `ceil(monotonic - start)`, and its
validators intentionally accept an integer from zero through the configured maximum; production,
disclosure, and schema behavior remain correct. The minimal test-only correction reuses
`_validate_exact_aggregates` on the rerun, excludes only `runtime` from cross-run aggregate equality,
and retains exact table-hash, study-key, QA-byte, and audit-key equality. Focused 3/3 passed
repeatedly, the complete manifest-runner file passed 12/12, and Ruff check/format plus the scoped diff
check pass. The then-current r13 candidate was exactly 16 files: seven source/tests, eight governance files,
and the latest snapshot. Exact staged tree `22c80aaa8f30d47a21e1a43fc3e945ab831c79ea` passed its
first complete D-015 gate: locked offline `uv` lock/sync; full pytest 538/538 in 63.84 seconds;
isolated wheel build, offline install, and import of `rsna-knee 0.1.0`; Ruff PASS; 124 files formatted;
mypy over 25 package plus 16 trust-boundary files; valid configuration with the
established hash and synthetic submission `rows=2`; canonical contract schema valid, current
`contract_drift=no`, and generated schema bytes current; sensitive guard PASS; tracked MIME exact at
154 regular files plus the one exact `.agents/skills` symlink; `pip-audit` with no known
vulnerabilities; all pre-commit hooks PASS; full tracked detect-secrets PASS; and exact 16-file
inventory, no unstaged or untracked residue, and unchanged-tree PASS. This eight-file governance
reconciliation changes bytes, so one immediate fully restaged identical complete rerun and final
red-team remain required. Only PASS with no later byte change fixes `complete_final_gate=PASS`; any
failure invalidates the first-pass final-gate evidence and requires this record to be corrected.
Freeze, bundle, authenticated identity-absence proof, append-only registry preparation, and
successor smoke remain pending. Even after those prerequisites pass, authorization stops at one
fresh successor smoke; Run A requires authenticated smoke terminal/output validation and a fresh
decision.

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
| Code | `feat/chunk-5-dicom-pipeline`; r14 is terminal failed at review-plan after authenticated inputs, smoke, Run A, Run B, and comparison passed; the exact review-protocol and owner-qualified mount corrections are tracked; the fully restaged current recovery tree must pass the identical complete gate and final red-team |
| Source manifest | The sanitized audit-0003 successor remains the authenticated source root; audit-0002 remains historical scientific evidence only; any fresh successor must bind the exact source without splicing historical stages |
| Hard groups | `protected-groups-v2`; not used to construct folds |
| Labels | `official-labels-v1`; not consumed by preprocessing |
| Folds | `unassigned` |
| Preprocessing | `dicom-model-v1` |
| Model | None |
| Loss | Not applicable; no labels, optimization, or model exist |
| Augmentation | None |
| Seed | `20260809` |
| Compute estimate | After the exact release gate, repeat one immutable private successor chain: inputs, smoke, two complete independent full-data passes, comparison, and review-plan, authenticating each dependency before the next. Stop at human-only pixel QA. All stages retain the verified competition margin; no accelerator or paid external service. |
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
or spliced into a successor.

R13 exact input authentication passed, then performance-smoke version 1 reached terminal `ERROR`.
The corrected strict failure-log validator returns `phase=performance_smoke`,
`code=throughput_projection_exceeds_budget`. The protected r13 registry row is terminal `failed`;
Run A, Run B, comparison, review-plan, and human review are `not_started`. No r13 rerun, splice, Run
A, output publication, or downstream launch occurred. Exactly one safe smoke progress event precedes
the failure, placing it at the inner throughput gate rather than authentication or output.

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

This numbered plan records the scientific workflow. The standing authorization permits a fresh
immutable recovery chain after the exact release gate, with each stage authenticated before its
dependent stage. It stops at the human-only pixel QA boundary.

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
  and runbook red-teams pass with no P0/P1. The historical first complete exact 24-file D-015 gate
  passed on tree `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260` with pytest 537/537 and every recorded
  lock/build/import, static, configuration, contract, privacy, dependency, inventory, and
  unchanged-tree check. That result is superseded. The later 15-file PASS and failed restaged tree
  are also historical and superseded. The first exact 16-file gate passed, but these governance
  bytes require the fully restaged identical complete rerun and final red-team;
  `complete_final_gate=PASS` remains unset. Existing DICOM-QA source-audit
  constants and fixtures are rebound to audit-0003.
- D-031 records that the r10 source graphs were exact but the shared global basename walk entered the
  legitimate greater-than-4,096-study competition tree before source selection. The correction
  changes only `kaggle/dicom_qa/finalize_review.py` and its focused identity regression: base search
  stops at depth 1 and kernel search starts at the exact derived mount, preserving symlink,
  duplicate, count, file-type, and error gates. Independent red-team passes with no P0/P1; focused
  identity 41/41, boundary matrix 12/12, combined identity plus packaging 188/188, full development
  pytest 537/537, Ruff/format, strict finalizer mypy, and the scoped diff check pass. The historical
  first exact staged D-015 gate passed on tree `959f14e9422db9670d16683ba8effe681cf6641d`
  over exactly 10 files:
  locked offline reinstall/lock; isolated wheel build/install/import; tracked MIME/symlink and
  sensitive guards; Ruff/format; mypy over 25 package plus 11 trust-boundary files; pytest 537/537;
  config/synthetic-submission; protected current contract/schema and generated-schema byte checks;
  pre-commit/detect-secrets; `pip-audit` with no vulnerabilities; cached diff, exact inventory, and
  unchanged-tree PASS. That 10-file result is superseded. The later 15-file PASS and failed restaged
  tree are also historical and superseded. The first exact 16-file gate passed, but these governance
  bytes require the fully restaged identical complete rerun and final red-team;
  `complete_final_gate=PASS` remains unset.
- D-033 binds the generic and performance-smoke failure logs to separate closed protocols selected
  by the first exact start event. It enforces exact terminal event, phase allowlist, ordered progress
  prefix, and phase-specific prefix length and rejects mixed or impossible states. Exact r13
  revalidation yields the safe phase/code above.
- D-034 follows that one-progress-event evidence to the inner throughput gate. Freeze `a36b053`
  correctly charged sample elapsed time when smoke and full pass shared one 27,000-second kernel;
  freeze `01ea270` split smoke into a standalone 3,600-second kernel but retained the same leading
  term in both admission sites. The minimal correction removes only that stale `elapsed +`, retaining
  pre-smoke setup time, full projection, the 3,600-second reserve, finite checks, self/outer deadlines,
  authentication, and privacy gates. Existing 3,801/3,799-second boundaries and the 4,320-second
  standalone ceiling pass targeted tests and scoped static checks. The 15-file PASS and failed
  restaged tree and their recovery requirements are historical and superseded by the r14 terminal
  checkpoint above.
- Historical r13 note: the checkpoint relay could not connect to Chrome, and the then-current
  smoke-only checkpoint did not authorize Run A. The r14 authorization and outcome above supersede
  that operational boundary.
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

## D-046 r16 on-demand human-QA execution contract

- Experiment ID: `preprocess-0001-dicom-pipeline-r16-on-demand-qa-v1`.
- Hypothesis: the substantively validated frozen r16 preprocessing core can be placed before an
  authorized human reviewer without another A/B/comparison cycle by selecting the fixed private
  QA cohort from authenticated metadata, then decoding and rendering only the study the reviewer
  explicitly advances.
- One primary change: replace pre-rendered full-cohort QA materialization with one private,
  internet-disabled, version-1 notebook that builds a metadata-only cohort and renders one selected
  study on demand.
- Frozen controls: r16 bundle SHA-256
  `91ed079210592448664f52c1a24ce1a693275ef09fa350167712097ab97de40b`, frozen r16 runner and
  preprocessing bytes, `dicom-model-v1`, `manifest-v2`, QA selector v3, 25-dimension registry v1,
  represented-value quota `min(2, population)`, mandatory singleton coverage, minimum 100 studies
  with no maximum, original competition input, nine review checks, and exact human attestation.
- Data/label/fold/preprocessing versions: original authorized competition input; authenticated
  audit-0003 private manifest; labels and folds not accessed; preprocessing `dicom-model-v1`.
- Model/loss/augmentation: not applicable; no training, inference, thresholding, pseudo-labeling,
  or model promotion occurs.
- Determinism: selector v3 and its frozen registry determine the cohort; no random sampling or
  configurable seed is introduced by this notebook.
- Compute estimate: one bounded header-only metadata pass to construct the cohort during the batch
  readiness run; after `START`, one selected study at a time, one model preprocessing pass and one
  QA preprocessing pass per eligible series, one render per series, and immediate temporary-file
  cleanup. No full-cohort pixel pass or pre-render directory is permitted.
- Expected information gain: establish whether the fixed nine-check human protocol accepts every
  selected series while preserving r16 provenance, orientation, laterality, intensity, geometry,
  sequence-slot, duplicate/missing/abnormal handling, and preprocessing appearance.
- Promotion criterion: independent source-set verifier PASS with the original ordered failure
  preserved; complete local engineering gate PASS; authenticated fresh private/offline/CPU
  notebook v1 with exact three inputs and exact source hash; terminal `COMPLETE`; sanitized
  `human_review_ready` output; no private ledger and no human review started during batch execution.
- Kill criterion: any source/hash/version mismatch, duplicate/missing/unexpected input, symlink,
  unbounded discovery, cohort quota failure, selected-study source drift, second render, resume
  identity mismatch, private-output leak, notebook error, or evidence that automation crossed the
  `START` boundary. Any need to rerun A/B/comparison, create r17, train, submit, merge, publish, or
  begin Chunk 6 also stops the experiment.
- Runtime/cost and outcome: pending the one authorized private version-1 launch. Human decisions
  remain `NOT_STARTED`; submission is not approved and clinical use is prohibited.

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

## Historical r13 performance-smoke recovery

R13 remains terminal failed and must never resume, rerun, or be spliced. Its protocol, budget, and
manifest-runtime corrections are historical prerequisites already carried into r14. Current work is
the r14 review-plan recovery described above: fully restage its 13-file candidate, pass the identical
complete D-015 gate and final red-team with no later byte change, then create a clean immutable
successor and authenticate every stage in order. Do not reuse remote artifacts or start ontology,
folds, labels, training, inference, submission, or Chunk 6.
