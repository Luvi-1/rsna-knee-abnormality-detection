# Plans

This file records the continuous sequence of work. A historical chunk can have useful deliverables
while still requiring correction before cumulative merge. “Complete” below never means merged.

## Current r14 terminal checkpoint

R14 authenticated inputs, performance smoke, Run A, Run B, and deterministic comparison `PASS`.
Review-plan v1 is terminal failed before cohort replay with safely validated
`phase=review`, `code=input_discovery_invalid`. The recovery candidate adds the missing exact review
failure protocol and supports only Kaggle's direct or collision-safe owner-qualified derived mount,
requiring exactly one. Focused and complete DICOM-QA suites plus Ruff, format, mypy, and diff checks
pass. Next: update governance, run the complete exact staged gate and independent red-team, create a
new clean freeze and deterministic bundle, append a fresh registry successor, then repeat the
immutable private chain. Do not splice r14, create v2, launch UI, claim human review, submit, or
start Chunk 6.
The latest official snapshot is `docs/competition_contract/2026-08-22T062926Z.md` with no material
drift.
The first complete D-015 gate passed on exact 13-file tree
`b9cf3ab0b5494e1bc85f1cd498b1108d1e7f20b0` with pytest 539/539 and every recorded offline,
static, configuration, contract, privacy, dependency, and inventory check. Release rule: only an
identical complete gate and final red-team PASS on the fully restaged tree containing this paragraph,
with no later byte change, fixes `complete_final_gate=PASS` and permits a new freeze.

## Current r13 terminal checkpoint

Legacy Kaggle authentication was restored without credential exposure. Exact r13 performance-smoke
version 1 authenticated and is terminal `ERROR`; the corrected producer-bound validator returns
`phase=performance_smoke`, `code=throughput_projection_exceeds_budget`. The append-only registry is
terminal `failed`: input authentication passed and Run A, Run B, comparison, review-plan, and human
review are `not_started`. No rerun, splice, Run A, or downstream launch occurred. Exact 15-file tree
`afd8909a798d30fa9314fe6568768bca68fbda14` passed its complete D-015 gate with pytest 538/538 and
all recorded checks but is historical and superseded. After the governance bytes were restaged,
exact tree `e298964891b214bfbf4dc06725f2cde3b3bd3f74` failed the mandatory pytest rerun with one
failure and 537 passes because a manifest-runner test compared nondeterministic real wall-clock
`runtime.elapsed_seconds` (3 seconds versus 2). Production uses `ceil(monotonic - start)`, and the
validators intentionally accept an integer from zero through the configured maximum; production,
disclosure, and schema behavior remain correct. The minimal test-only correction reuses
`_validate_exact_aggregates` on the rerun, excludes only `runtime` from cross-run aggregate equality,
and retains exact table-hash, study-key, QA-byte, and audit-key equality. Focused 3/3 passed
repeatedly, the complete manifest-runner file passed 12/12, and Ruff check/format plus the scoped diff
check pass. The then-current r13 candidate was exactly 16 files: seven source/tests, eight governance files,
and `docs/competition_contract/2026-08-21T200304Z.md`. Exact staged tree
`22c80aaa8f30d47a21e1a43fc3e945ab831c79ea` passed its first complete D-015 gate: locked offline
`uv` lock/sync; full pytest 538/538 in 63.84 seconds; isolated wheel build, offline install, and
import of `rsna-knee 0.1.0`; Ruff PASS with 124 files formatted; mypy over 25 package plus 16 trust-
boundary files; valid configuration with the established hash and synthetic submission `rows=2`;
canonical contract schema valid, current `contract_drift=no`, and generated schema bytes current;
sensitive guard PASS; tracked MIME exact at 154 regular files plus the one exact `.agents/skills`
symlink; `pip-audit` with no known vulnerabilities; all pre-commit hooks PASS; full tracked detect-
secrets PASS; and exact 16-file inventory, no unstaged or untracked residue, and unchanged-tree PASS.
This eight-file governance reconciliation changes bytes, so one immediate fully restaged identical
complete rerun and final red-team remain required. Only PASS with no later byte change fixes
`complete_final_gate=PASS`; any failure invalidates the first-pass final-gate evidence and requires
this record to be corrected. Freeze, bundle, authenticated identity-absence proof, append-only
registry preparation, and successor smoke remain pending. Even after those prerequisites pass,
authorization stops at one fresh successor smoke; authenticated terminal/output validation and a
fresh decision are required before Run A.

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
- The latest live refresh at `2026-08-22T06:29:26Z` used the official Kaggle MCP first. The
  819,640-file / 819,635-DICOM / five-CSV aggregate inventory, deadlines, runtime, limits, entered
  state, and recorded Host clarification were unchanged with no material drift. Latest snapshot:
  `docs/competition_contract/2026-08-22T062926Z.md`.
- Host topic `733965` continues to permit compliant commercial LLM or external inference under
  the Rules, equal-access, and minimal-cost conditions and says report processing is not itself
  private sharing.
- The repository's stricter boundary remains unchanged: no raw DICOM pixels, radiology reports,
  patient-level metadata, identifiers, private competition code or data, or private artifacts may
  be sent to any external LLM, API, or service. Only recognized members of the same official Kaggle
  team may receive private competition code or data.

Open gates:

- Identity-verification state is unavailable through the read-only official interface and therefore
  remains fail closed, not known incomplete. Degenerate-label scorer behavior, exact retained DICOM
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
`manifest-v2` / `protected-groups-v2`. That scientific evidence remains valid historically, but
D-029 supersedes audit-0002 as a reusable source root because the shared bundle helper admitted
dependency-wheel medical payloads. The sanitized audit-0003 successor supplied the authenticated
r10 source root; future consumers must reauthenticate it.
Downstream fold and model work remains blocked.

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
- `audit-0002-manifest-remediation` preserved as historical scientific evidence but superseded as a
  reusable source root; the sanitized audit-0003 successor supplied the authenticated r10 root.
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

Status: Chunk 5 recovery is active and not passed. Exact r13 performance-smoke version 1
authenticated and is terminal `ERROR`. Input authentication passed, the smoke failed with
`throughput_projection_exceeds_budget`, and every downstream stage remains `not_started`. Root-cause
tracing found that the smoke producer and generic failure-log consumer used different closed event
protocols, so the consumer masked otherwise valid smoke failures as
`failure_log_completion_invalid`. D-033 keeps one validator entry point, binds validation to the
first exact start event, enforces the matching terminal event, phase allowlist, ordered progress
prefix, and phase-specific prefix length, and rejects hybrid or impossible states. D-033 changes only
the validator and one regression. The 15-file PASS and failed restaged tree are historical and
superseded. Exact 16-file tree `22c80aaa8f30d47a21e1a43fc3e945ab831c79ea` passed its first
complete D-015 gate, but these governance bytes require the fully restaged identical complete rerun
and final red-team. The safe log contains one smoke progress event, localizing the
terminal failure to the inner throughput gate. Git history shows that the old monolithic smoke plus
full pass correctly charged sample time, but the later standalone-smoke split retained that term even
though Run A and Run B receive the full 27,000-second budget and do not repeat the sample. D-034
removes only the stale leading `elapsed +` at both sites while keeping setup accounting, full
projection, the 3,600-second reserve, deadlines, and every privacy/source gate. Targeted tests and
scoped static checks pass. Only the fully restaged identical complete rerun and final red-team may
fix `complete_final_gate=PASS`; afterward, a clean freeze, deterministic bundle,
authenticated identity-absence proof, append-only registry preparation, and fresh no-splice
successor smoke remain pending.
No r13 rerun, Run A, pixel, QA, human review, finalizer, or public action occurred. Run A requires
authenticated successor-smoke validation and a fresh decision; Chunk 5, downstream work, and
Chunk 6 remain blocked.
This work was explicitly authorized after the Chunks 1-4 checkpoint branch was established; pull
request #10 remains unmerged.

Objective: produce deterministic model tensors from heterogeneous MRI DICOM series with explicit
decode failures, physical IOP/IPP ordering, modality and photometric transforms, strict geometry
eligibility, laterality preservation, flexible sequence slots, complete provenance, private visual
QA, and measured Kaggle performance.

Local evidence:

The later Run A through finalizer bullets below describe the eventual scientific workflow only. They
are not authorized by the current checkpoint and require a fresh post-smoke decision.

- Four observed competition transfer-syntax families have synthetic decode regressions: Explicit
  and Implicit VR Little Endian, JPEG Lossless SV1, and JPEG 2000 Lossless.
- Synthetic coverage includes reversed InstanceNumber, oblique geometry, missing position and
  QA-only fallback, duplicates, uneven spacing, multiple bit depths and signed pixels, blank,
  constant, corrupt and truncated inputs, MONOCHROME1, laterality, optional channels, deterministic
  sampling, multiple series per slot, and missing slots.
- `audit-0002-manifest-remediation` / `manifest-v2` remains historical scientific evidence but is
  superseded as a reusable source root. The new root must come from completed
  `audit-0003-wheel-sanitization` / `manifest-v2`. Each full runner verifies the mounted source
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
  correction passed in r9 freeze `1db805e`; the later dependency-wheel content rejection is
  separate.
- D-028 found that `efficiency_prize`, `external_assets`, `team_and_sharing`, `license`,
  `winner_obligations`, and `ambiguities` were absent from the material-drift allowlist, so mutation
  or wholesale removal could yield `contract_drift=no`. The minimal fix adds them to the existing
  `MATERIAL_SECTIONS` and extends `tests/test_smoke.py` without a dependency or abstraction. Smoke
  passes 6/6; the combined focused set passes 155/155; Ruff/format, mypy over 25 source plus nine
  trust-boundary files, independent current-source `contract_drift=no`, and post-fix red-team PASS/no
  P0/P1 all pass. The correction passed in r9 freeze `1db805e`; the later dependency-wheel content
  rejection is separate.
- D-029 fixes the shared root once in `package_manifest_bundle` with the standard library: remove
  the general test tree plus every `.dcm`, `.dicom`, or standard DICM-at-byte-128 member; regenerate
  wheel `RECORD` deterministically; validate every other wheel fail-closed; and preserve runtime,
  metadata, licenses, and offline preflight. The first r10 candidate passed on exact staged tree
  `5bea3c110e100e9ddd2d94c8b89c29e1f0ff82a0`: pytest 530/530; isolated wheel
  build/install/import; Ruff check/format; mypy over 25 source and nine trust-boundary files;
  audit/configuration/submission; contract schema and current `contract_drift=no`; pre-commit;
  privacy checks; `pip-audit`; exact inventory and unchanged-tree checks. That gate is now
  superseded by D-030 preflight findings.
- D-030 extends the same guard to the project wheel and adds one deployment authenticator that
  directly reuses the existing DICOM-QA version-1 helpers. Before network access, every stage checks
  the exact two-file local kernel/hash and all wheels/`RECORD`, binds dataset metadata to the exact
  bundle-manifest parent, and binds kernel metadata to its exact sibling kernel directory; remote gates prove exact private
  dataset version-1 content/hashes, exact kernel version-1 code/source graph, stable listings, and
  before/after race snapshots. Status is fixed to `PENDING`, `RUNNING`, `COMPLETE`, or `ERROR`; the
  runbook uses a command-scoped token, protected logs, explicit `/1`, and bracketed gates. No new
  dependency, framework, or abstraction was added. The mismatched-root regression proves zero
  remote calls. Independent auth/runbook red-teams pass with no P0/P1. The historical first complete
  exact 24-file D-015 gate passed on tree `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260` with pytest
  537/537 and all recorded checks. That result is superseded. The later 15-file PASS and failed
  restaged tree are also historical and superseded. The first exact 16-file gate passed, but these
  governance bytes require the fully restaged identical complete rerun and final red-team;
  `complete_final_gate=PASS` remains unset.
- D-031 records the r10 terminal review-plan failure. The source graphs authenticated correctly, but
  the shared global basename walk reached the legitimate greater-than-4,096-study competition tree
  before source selection. The two-file correction narrows the existing discovery helper to depth 1
  and exact derived kernel mounts without weakening symlink, duplicate, count, file, or error gates.
  Independent red-team passes with no P0/P1; focused identity 41/41, boundary matrix 12/12, combined
  identity plus packaging 188/188, full pytest 537/537, Ruff/format, strict finalizer mypy, and the
  scoped diff check pass. The historical first exact staged D-015 gate passed on tree
  `959f14e9422db9670d16683ba8effe681cf6641d` over exactly 10 files, including every locked-offline,
  isolated build/import, static, pytest, config/submission, protected-contract, schema-byte,
  pre-commit/secrets, vulnerability, cached-diff, inventory, and unchanged-tree check. That 10-file
  result is superseded. The later 15-file PASS and failed restaged tree are also historical and
  superseded. The first exact 16-file gate passed, but these governance bytes require the fully
  restaged identical complete rerun and final red-team; `complete_final_gate=PASS` remains unset.
- D-033 records the r13 terminal smoke failure and the producer/consumer state-machine mismatch. The
  existing validator now selects the generic or smoke protocol from the first exact start event and
  strictly checks its terminal event, phases, ordered progress prefix, and legal prefix length. Exact
  authenticated revalidation returns `phase=performance_smoke`,
  `code=throughput_projection_exceeds_budget`. This is terminal failure evidence, not permission to
  retry or launch Run A. The 15-file PASS and failed restaged tree are historical and superseded.
  The first exact 16-file gate and its later recovery requirements are historical and superseded by
  the r14 terminal checkpoint above.
- D-034 records the stale monolithic budget term exposed by that strict classification. The safe log
  has one progress event, proving the inner throughput gate failed. The standalone smoke no longer
  shares its sample work with a full run, so both admission sites now compare only projected full-pass
  time plus the unchanged 3,600-second reserve; pre-smoke setup accounting, deadlines, privacy, and
  source gates remain intact. Existing 3,801/3,799-second boundaries and the 4,320-second standalone
  ceiling pass targeted/static checks. Fresh successor smoke remains mandatory and may fail closed.
- Historical r13 note: the checkpoint relay could not connect to Chrome, and the then-current
  smoke-only checkpoint did not authorize Run A. The r14 authorization and outcome above supersede
  that operational boundary.

Exit evidence still required:

1. Preserve r14 and every earlier failed chain as terminal historical evidence; never resume,
   rerun, mutate, delete, or splice them.
2. Fully restage the current 13-file r14 recovery candidate and rerun the identical complete D-015
   gate plus final red-team. Only PASS on the tree containing this reconciliation, with no later
   byte change, fixes `complete_final_gate=PASS`.
3. Only after that exact PASS, complete a clean freeze, deterministic bundle,
   authenticated identity-absence proof, and append-only registry preparation, then run one fresh
   private/offline/version-bound successor smoke under every existing D-030 gate. No historical
   result substitutes for it.
4. Authenticate and validate every successor stage before its dependent stage, and stop at the
   human-only pixel QA boundary. Do not start ontology, folds, labels, model work, Chunk 6, or
   submission.
