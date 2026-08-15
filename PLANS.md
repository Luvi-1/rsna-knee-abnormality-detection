# Plans

This file records the continuous sequence of work. A historical chunk can have useful deliverables
while still requiring correction before cumulative merge. “Complete” below never means merged.

## Chunk 1 - private repository operating system

Historical status: implementation delivered on a private feature branch; cumulative validation is
being repeated in Checkpoint 1.

Objective: establish an installable, dependency-locked, synthetic-tested private-repository
operating system without competition-data access or model training.

Delivered evidence:

- Private source-of-truth repository, `uv` lock, typed package and CLI, configuration and SQLite
  registry schemas, synthetic fixtures, CI workflow, governance files, and project-scoped skills.
- No competition data, report, checkpoint, prediction, model, or credential was intentionally
  committed.

Correction/gate outcome:

- The prior final secret-pass claim was made before the final tracked file set was included. Exact
  reviewed baseline entries and a detection regression now exist locally. The complete staged-tree,
  cumulative-diff, history, and generated-artifact checks passed. Hosted CI passed on cumulative
  release candidate `cc050a2`; later commits remain subject to the same gate.

## Chunk 2 - live competition contract

Historical status: contract captured and refreshed; no competition-data analysis or model work.

Objective: create one authoritative, machine-readable operating contract for the exact competition
before any data or modeling decision.

Delivered evidence:

- `docs/competition_contract/contract.yaml` is canonical and is loaded through
  `configs/competition.yaml` rather than duplicating targets or constraints in code.
- Rules, metric, schema, dates, notebook/runtime and submission limits, data interface, external
  assets, team/sharing constraints, licenses, and contradictions are recorded with conservative
  defaults.
- The latest live refresh at `2026-08-15T00:00:25Z` used the official Kaggle MCP first. All nine
  operational hashes, the 819,640-file / 819,635-DICOM / five-CSV aggregate inventory, deadlines,
  runtime, limits, entered state, and RSNA MIRA PDF were unchanged.
- Newly discovered Host topic `733965` permits compliant commercial LLM or external inference under
  the Rules, equal-access, and minimal-cost conditions and says report processing is not itself
  private sharing.
- The repository's stricter boundary remains unchanged: no raw DICOM pixels, radiology reports,
  patient-level metadata, identifiers, private competition code or data, or private artifacts may
  be sent to any external LLM, API, or service. Only recognized members of the same official Kaggle
  team may receive private competition code or data.

Open gates:

- Identity verification remains incomplete. Degenerate-label scorer behavior, exact retained DICOM
  tag names, and exact accelerator availability remain unresolved and fail closed.

## Chunk 3 - evidence-ranked research portfolio

Historical status: research portfolio delivered on a private feature branch; not merged.

Objective: rank label, validation, image, ensemble, contrarian, and efficiency hypotheses without
competition-data processing or model training.

Delivered evidence:

- Current official competition context, timestamped public landscape, structured source matrix,
  exactly 35 hypotheses, and five hard rejects.
- External assets remain blocked until provenance, version, identifier, license, checksum,
  equal-access, offline packaging, rule justification, and approval are complete.

Exit retained: no data processing, model, submission, notebook fork, public action, or external
asset use occurred in the chunk.

## Chunk 4 - full-data manifest and structural grouping audit

Current evidence: `audit-0001-manifest` is superseded. Its successor,
`audit-0002-manifest-remediation`, completed a full private CPU run in 10,092 seconds against
`manifest-v2` / `protected-groups-v2`. Downstream fold and model work remains blocked by the
remaining Checkpoint 1 release gates.

What remains valid as historical provenance:

- A private CPU audit executed with no preprocessing, folds, model, prediction, ensemble, or
  submission.
- Private artifacts were kept within the Kaggle boundary, and only an aggregate release set was
  retrieved.
- The run exposed real DICOM exception, bounded-candidate, disclosure, and governance-control gaps
  that now define Checkpoint 1 remediation.

Validated successor evidence:

- Complete five-level reconciliation, foreign-key integrity, and terminal file/series accounting.
- `unexplained_dicom_issues: zero` and `dicom_issue_dispositions_complete: true`; private case
  evidence was not exported.
- Hard protected components remained separate from soft candidate/overflow evidence, with
  `protected_graph_closed: true`; no folds were assigned and feasibility was not assessed.
- Exactly five approved outputs passed the schema-v2 joint disclosure boundary. Only the four
  approved release artifacts are being persisted with governance; the inventory hash remains in
  the experiment provenance record.

Why the original exit assessment is withdrawn:

- The then-current sanitizer independently suppressed fields and allowed arithmetic reconstruction
  through related totals and complements.
- Weak/candidate/overflow relationships were allowed to affect the same protected components as
  hard duplicate/repeat evidence, so the v1 zero-crossing statement was not fold-feasibility proof.
- Nonzero DICOM exception cases had not received complete private root-cause and deterministic
  disposition review.
- The reported final secret gate did not cover the eventual committed file set, and remote CI had
  not validated the cumulative branch.

## Checkpoint 1 - Chunks 1-4 remediation

Status: private remediation execution, guarded history/ref cleanup, and complete staged-candidate
local gates passed on `checkpoint/chunks-1-4-remediated`. Private pull request #10 is open and
unmerged; hosted CI passed on release candidate `cc050a2`, and any successor must pass it again.

Objective: make Chunks 1-4 truthful, privacy-safe, reproducible, privately revalidated, and remotely
reviewable. Do not start Chunk 5.

Completed and validated so far:

- Narrow exact secret-baseline correction plus a regression that must still detect realistic token
  replacement.
- One central joint-disclosure boundary and output schema with arithmetic-reconstruction tests.
- `manifest-v2` / `protected-groups-v2` separation of hard protected components from soft
  candidates; no fold identifiers are created.
- Live contract refresh with no material drift.
- Full private `audit-0002-manifest-remediation` execution at commit
  `6fce3af8ba1cc85dacd6a29326f999bf5f5227ed`, completed in 10,092 seconds.
- Schema-v2 sanitized evidence with complete coverage, zero unexplained DICOM issues, complete
  dispositions, private hard/soft provenance checks, and five approved artifact hashes.
- `audit-0001-manifest` preserved as historical provenance and superseded for all downstream use.
- Guarded history/ref cleanup passed: the old feature ref now points to the clean history, the
  temporary unsafe branch is deleted, and no active local or origin ref reaches the unsafe commit.
- Final complete staged-candidate gates passed: locked install/package, 139/139 pytest, Ruff
  lint/format, strict mypy, pre-commit, secret/baseline comparison, sensitive-file guard,
  vulnerability audit, contract/config/submission checks, full-output validation, and four
  canonical byte comparisons.
- Private pull request #10 is open and unmerged; its hosted `quality` workflow passed on release
  candidate `cc050a21ab3386b501170d224ef57ef990a3753b`.

Retained release condition: the Checkpoint 1 candidate passed hosted CI at `cc050a2`; every
successor, including the eventual Chunk 5 candidate, must pass the same exact-head gate. Pull
request #10 remains unmerged.

## Checkpoint 1 handoff

No next chunk was inferred at that checkpoint. The user subsequently authorized Chunk 5
explicitly; fold construction, weak labels, training, prediction, ensembling, and submission remain
unauthorized.

## Chunk 5 - deterministic DICOM-to-model pipeline

Status: Chunk 5 recovery is active and not passed. D-026 passed its complete gate with pytest
528/528, and recovery iteration 8 uses freeze `4958c4a` and immutable bundle `09502a...`. Its private
version-1 inputs, standalone smoke, and full-data Run A authenticated and passed. Run B version 1
reached `COMPLETE` at 25,940 seconds; two independent bounded read-only polls 71 seconds apart
agreed, and the established authenticated validator returned
`dicom_qa_output_validation=PASS mode=workflow stage=run-b`. The protected registry row is terminal
`blocked`: input, smoke, Run A, and Run B are `passed`; comparison, `review_plan`, and `human_review`
are `not_started`; `completed_utc` is set; and integrity, foreign keys, and mode are `PASS`. Frozen-
source preflight had found two P1 review-plan producer/validator contract defects before comparison
launch. UI/session creation and finalization were not launched. This is not Chunk 5 PASS and proves
no comparison, determinism, QA, review, or performance result. D-027 defines the smallest two-file
fail-closed correction. D-028 closes an independent material-drift checker P1. Their focused checks
pass. The r9 exact 16-file candidate passed its first complete release gate on staged tree
`ed3720d8159b1242a6b72cab13dec43a4406f25a`: pytest 529/529; isolated wheel
build/install/import; Ruff check and format; mypy over the package plus nine trust-boundary files;
pre-commit; secret and privacy checks; dependency audit; contract schema and current
`contract_drift=no`; exact inventory; and unchanged-tree checks. This governance reconciliation
changes that staged tree, so D-015 requires the main agent to restage and immediately rerun the
identical complete gate. If that rerun succeeds, the final release record is
`complete_final_gate=PASS`; any failure invalidates this record and must be corrected. The
replacement freeze/commit, immutable bundle, full fresh private chain, comparison, QA, human review,
finalizer, and push remain pending.
This work was explicitly authorized after the Chunks 1-4 checkpoint branch was established; pull
request #10 remains unmerged.

Objective: produce deterministic model tensors from heterogeneous MRI DICOM series with explicit
decode failures, physical IOP/IPP ordering, modality and photometric transforms, strict geometry
eligibility, laterality preservation, flexible sequence slots, complete provenance, private visual
QA, and measured Kaggle performance.

Local evidence:

- Four observed competition transfer-syntax families have synthetic decode regressions: Explicit
  and Implicit VR Little Endian, JPEG Lossless SV1, and JPEG 2000 Lossless.
- Synthetic coverage includes reversed InstanceNumber, oblique geometry, missing position and
  QA-only fallback, duplicates, uneven spacing, multiple bit depths and signed pixels, blank,
  constant, corrupt and truncated inputs, MONOCHROME1, laterality, optional channels, deterministic
  sampling, multiple series per slot, and missing slots.
- The source root of trust is the completed `audit-0002-manifest-remediation` / `manifest-v2`
  private output. The superseded v1 audit is rejected. Each full runner verifies the mounted source
  database, schema, input snapshot, and private audit binding before processing, then exactly
  reconciles train-series membership, `source_row_count`, organizer plane/fluid/fat flags, and every
  regular DICOM's keyed relative identity, byte size, and raw digest.
- Distinct immutable Run A and Run B version-1 kernels use the same frozen bundle, configuration,
  competition input, and source-manifest input. Each independently processes the entire authorized
  training set and emits only the canonical full-pass manifest, deterministic metrics, and
  deterministic cohort plan. Every discovered study, series, and file receives an explicit
  terminal disposition.
- Selector v3 has a minimum review target but no arbitrary study maximum. Its exact incremental
  greedy selection continues until every required represented value quota is met across bounded
  semantic registries, including bounded site-domain buckets, subject only to fail-closed physical
  file, byte, time, and disk gates. It makes no legacy joint-material coverage claim. The only
  public registry-coverage token is `all_required_represented_registry_values_satisfy_quotas`.
- A separate comparator consumes both complete run outputs and requires byte-exact equality of the
  canonical manifests and cohort plans plus exact equality of deterministic metrics. Timing and
  resource observations are recorded separately and cannot mask a deterministic mismatch.
- After exact comparison, the existing review-plan kernel authenticates a capacity certificate
  bound to the freeze, bundle, manifest, both runs, cohort plan, and renderer. It then replays every
  selected series, renders each twice, runs representative decode/preprocessing/resource benchmarks
  once, and materializes the private review plan. No additional kernel or data reference is added.
- The review plan, identity, cohort hash, artifact hashes, rows, and decisions stay inside Kaggle.
  A safe UI template is copied and edited in Chrome to create a distinct private review session;
  its first operation is an explicit `START` gate. The human records only the frozen nine checks as
  `PASS`, `BLOCK`, or `NOT_APPLICABLE`. Each plan row binds and displays organizer/physical plane,
  assigned slot, retention reasons, the six-slot missing mask, and ordinal sibling
  slot/terminal/model-eligibility/retention/quality-block context. Artifacts resolve only under the
  authenticated Run A slug root.
- The private finalizer authenticates the exact run, comparison, plan, UI/session, bundle,
  preprocessing, source-manifest, and cohort identities. It derives completion from the private
  ledger and emits only `human_review_summary.json` and `final_performance_report.json` as the two
  final allowlisted release-safe outputs; exact review counts remain private.
- The exact 29-file staged D-023 candidate passed the complete final local gate: staged inventory
  and clean-tree checks, locked offline build/install, isolated wheel install/import, MIME checks,
  Ruff, strict typing, pytest 507/507, CLI/config/submission/contract, pre-commit, secrets,
  sensitive-file, dependency, fresh contract-drift, and diff checks. Independent end-to-end and
  source-graph red-teams found no remaining P0/P1.
- D-026 passed the complete iteration-8 gate with pytest 528/528 and produced freeze `4958c4a` /
  bundle `09502a...`. Inputs, smoke, Run A, and Run B authenticated and passed. Run B version 1
  reached `COMPLETE` at 25,940 seconds; two independent read-only polls 71 seconds apart agreed, and
  the authenticated workflow validator passed. The protected row is terminal `blocked` before
  comparison; this supplies no comparison, determinism, QA, review, performance, or Chunk 5 PASS
  evidence.
- Frozen-source preflight then found that the finalizer requires six QA artifacts and allows
  `orthogonal.png` only when renderable while the validator required exactly seven. It also found
  that automatic materialization emits `dicom_qa_review_started`, four
  `dicom_qa_plan_progress` events, and `dicom_qa_review_template_complete`, while the validator
  expected generic run boundaries. Comparison and every review stage were blocked before launch.
- The D-027 two-file candidate binds the validator to the producer's exact suffix and event
  contracts. Focused checks pass 9/9, the packaging file passes 147/147, Ruff check and format pass,
  strict validator mypy passes, and an independent red-team returns PASS with no P0/P1. The
  correction is included in the r9 first complete release-gate PASS; all replacement immutable-chain
  evidence remains pending.
- D-028 found that `efficiency_prize`, `external_assets`, `team_and_sharing`, `license`,
  `winner_obligations`, and `ambiguities` were absent from the material-drift allowlist, so mutation
  or wholesale removal could yield `contract_drift=no`. The minimal fix adds them to the existing
  `MATERIAL_SECTIONS` and extends `tests/test_smoke.py` without a dependency or abstraction. Smoke
  passes 6/6; the combined focused set passes 155/155; Ruff/format, mypy over 25 source plus nine
  trust-boundary files, independent current-source `contract_drift=no`, and post-fix red-team PASS/no
  P0/P1 all pass. The correction is included in the same r9 first complete release-gate PASS, with
  D-015's immediate identical post-governance rerun controlling the final
  `complete_final_gate=PASS` record.
- The checkpoint relay could not connect to Chrome. No new reviewer response or decision exists;
  the user's standing Chunk 5 authorization remains controlling.

Exit evidence still required:

1. Preserve iteration 8 only as a terminal `blocked` historical chain. Because D-027 and D-028
   change frozen source, never launch its comparison, review-plan, UI/session, human-review, or
   finalizer stages and never splice its passed stages into iteration 9.
2. Restage this governance reconciliation and immediately rerun the identical complete gate under
   D-015. A successful rerun fixes the final release record at `complete_final_gate=PASS`; any
   failure invalidates the record and must be corrected. Then create a clean iteration-9
   implementation-freeze/commit identity under the approval already granted and a
   deterministic offline bundle cryptographically bound to `audit-0002-manifest-remediation` /
   `manifest-v2`. The terminal blocked r8 chain cannot be spliced into the replacement.
3. Authenticated private, offline, exact-source, exact-version, exact-listing checks for the base
   dataset and every version-1 kernel; version 2 must be absent.
4. A passing authenticated smoke with separate conservative full-pass and post-comparison
   preparation estimates, followed by successful independent Run A and Run B over the entire
   authorized training set, complete terminal accounting, exact `manifest-v2` series/file/size/raw-
   digest reconciliation, deterministic cohort plans, and no unexplained DICOM or recoverable
   transfer-syntax blocker.
5. Byte-exact manifest and cohort-plan comparison and exact deterministic metrics, retrieved only
   through the D-026 exact-summary/optional-safe-log boundary; then a passing identity-bound physical
   capacity gate and one review-plan execution whose six mandatory artifacts, sole optional
   orthogonal view, and exact automatic event sequence pass D-027. It must supply selected-series
   replay, double-render, decode, preprocessing, cache, peak-memory, CPU-scaling, disk, throughput,
   and runtime evidence.
6. At least 100 completed private human-reviewed studies, with selector v3 satisfying every required
   represented bounded-registry quota and including all eligible diagnostic series; all nine checks
   must be terminal with zero `BLOCK`.
7. Private finalization bound to the exact completed review-session identity and successful
   disclosure validation of the allowlisted sanitized aggregates.
8. Truthful final governance, complete staged gates, committed and pushed synchronized branch, and
   no ontology, fold, label, model, prediction, ensemble, inference, or submission work.
