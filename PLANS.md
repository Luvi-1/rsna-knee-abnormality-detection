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
- The latest live refresh at `2026-08-13T19:20:34Z` used the official Kaggle MCP first. The current
  data-description fingerprint changed only for three organizer clarifications already enforced by
  the canonical contract; every other operational fingerprint and material gate was unchanged.

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

Status: Chunk 5 recovery is active and not passed. Recovery iteration 6 used freeze
`1c4470e8a9557141682a81737981271635db7fdc` and immutable bundle
`9e6be825c219f458c79fa1599feb82ace33d97dade441858fa53656820e6fda4`; its private version-1 inputs
authenticated and standalone smoke passed. Run A version 1 then reached terminal `ERROR`. A separate
bounded exact-reference failure-log classification passed with `phase=processing` and
`code=private_cohort_plan_invalid`. Run B, comparison, review-plan materialization, and human review
did not start. The minimal D-025 source/test correction is focused-green and now requires the
complete exact-set gate, replacement freeze/bundle/dataset chain, smoke retry, Run A, Run B,
comparison, human review, commit, and push.
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
- Recovery iteration 6 authenticated its new private inputs and passed the standalone smoke. Run A
  version 1 then failed closed at private cohort-plan validation. Root-cause tracing found that
  selected studies serialized legacy/internal dimensions outside the exact 25-dimension plan schema;
  the same trace found that representative series were selected globally rather than from the
  selected cohort. The two-file D-025 correction filters the existing dimension registry and binds
  representatives to selected studies. All 46 full-run tests, Ruff check/format, strict mypy on the
  two files, and the diff check pass; the complete gate remains pending.

Exit evidence still required:

1. A complete exact-set gate over D-025, then a clean replacement implementation-freeze identity
   under the approval already granted and a deterministic offline bundle cryptographically bound to
   `audit-0002-manifest-remediation` / `manifest-v2`.
2. Authenticated private, offline, exact-source, exact-version, exact-listing checks for the base
   dataset and every version-1 kernel; version 2 must be absent.
3. A passing authenticated smoke with separate conservative full-pass and post-comparison
   preparation estimates, followed by successful independent Run A and Run B over the entire
   authorized training set, complete terminal accounting, exact `manifest-v2` series/file/size/raw-
   digest reconciliation, deterministic cohort plans, and no unexplained DICOM or recoverable
   transfer-syntax blocker.
4. Byte-exact manifest and cohort-plan comparison, exact deterministic metrics, then a passing
   identity-bound physical capacity gate and one review-plan execution that supplies selected-series
   replay, double-render, decode, preprocessing, cache, peak-memory, CPU-scaling, disk, throughput,
   and runtime evidence.
5. At least 100 completed private human-reviewed studies, with selector v3 satisfying every required
   represented bounded-registry quota and including all eligible diagnostic series; all nine checks
   must be terminal with zero `BLOCK`.
6. Private finalization bound to the exact completed review-session identity and successful
   disclosure validation of the allowlisted sanitized aggregates.
7. Truthful final governance, complete staged gates, committed and pushed synchronized branch, and
   no ontology, fold, label, model, prediction, ensemble, inference, or submission work.
