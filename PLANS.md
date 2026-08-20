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
- The latest live refresh at `2026-08-20T08:02:22Z` used the official Kaggle MCP first. All nine
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

Status: Chunk 5 recovery is active and not passed. R10 exact inputs, performance smoke, Run A, Run B,
and comparison authenticated and passed. Review-plan version 1 then reached `ERROR`; two bounded
read-only checks 93 seconds apart agreed, and the frozen privacy/canary failure validator passed with
only `input_discovery_invalid`. The exact source graph was correct. The shared automatic basename
walk entered the legitimate greater-than-4,096-study competition tree before source selection and
failed closed. No review-plan artifact, pixel, UI/session, human review, or finalizer stage was
accessed or created; the r10 registry is terminal `failed`. D-031 makes the minimal two-file repair:
depth-1 base discovery plus exact derived kernel-mount discovery while preserving every symlink,
duplicate, count, file-type, and error gate. Independent red-team passes with no P0/P1; focused
identity 41/41, boundary matrix 12/12, combined identity plus packaging 188/188, full development
pytest 537/537, Ruff/format, strict finalizer mypy, and the scoped diff check pass. The first exact
staged D-015 gate passed on tree `959f14e9422db9670d16683ba8effe681cf6641d` over exactly 10 files;
the full locked-offline, isolated-build/import, static, pytest, config/submission, protected-contract,
schema-byte, pre-commit/secrets, vulnerability, cached-diff, inventory, and unchanged-tree checks
passed. Governance changes bytes, so one immediate identical restaged rerun must PASS to fix
the final gate as passed; failure invalidates this record. A new immutable r11 no-splice chain is required; Chunk 5, QA, downstream work, and Chunk 6
remain blocked.
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
  remote calls. Independent auth/runbook red-teams pass with no P0/P1. The first complete exact
  24-file D-015 gate passed on tree `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260` with pytest
  537/537 and all recorded checks. This reconciliation changes bytes, so an immediate identical
  fully restaged rerun is required; its PASS fixes `complete_final_gate=PASS`.
- D-031 records the r10 terminal review-plan failure. The source graphs authenticated correctly, but
  the shared global basename walk reached the legitimate greater-than-4,096-study competition tree
  before source selection. The two-file correction narrows the existing discovery helper to depth 1
  and exact derived kernel mounts without weakening symlink, duplicate, count, file, or error gates.
  Independent red-team passes with no P0/P1; focused identity 41/41, boundary matrix 12/12, combined
  identity plus packaging 188/188, full pytest 537/537, Ruff/format, strict finalizer mypy, and the
  scoped diff check pass. The first exact staged D-015 gate passed on tree
  `959f14e9422db9670d16683ba8effe681cf6641d` over exactly 10 files, including every locked-offline,
  isolated build/import, static, pytest, config/submission, protected-contract, schema-byte,
  pre-commit/secrets, vulnerability, cached-diff, inventory, and unchanged-tree check. These
  governance bytes require one immediate identical restaged rerun; PASS fixes
  the final gate as passed, while failure invalidates this record.
- The checkpoint relay could not connect to Chrome. No new reviewer response or decision exists;
  the user's standing Chunk 5 authorization remains controlling.

Exit evidence still required:

1. Preserve r8, r9, and r10 only as terminal historical evidence; never resume, mutate, delete, or
   splice their stages into r11.
2. Preserve the first exact staged D-015 PASS on tree `959f14e9422db9670d16683ba8effe681cf6641d`
   as non-final evidence, immediately rerun the identical restaged gate, and freeze a new immutable
   r11 bundle only after its PASS fixes the final gate as passed.
3. Execute r11 sequentially from authenticated inputs through smoke, independent Run A and Run B,
   and byte-exact comparison under every existing D-030 gate; no r10 result substitutes for an r11
   stage.
4. Require a passing identity-bound physical
   capacity gate and one review-plan execution whose six mandatory artifacts, sole optional
   orthogonal view, and exact automatic event sequence pass D-027. It must supply selected-series
   replay, double-render, decode, preprocessing, cache, peak-memory, CPU-scaling, disk, throughput,
   and runtime evidence.
5. At least 100 completed private human-reviewed studies, with selector v3 satisfying every required
   represented bounded-registry quota and including all eligible diagnostic series; all nine checks
   must be terminal with zero `BLOCK`.
6. Private finalization bound to the exact completed review-session identity and successful
   disclosure validation of the allowlisted sanitized aggregates.
7. Truthful final governance, complete staged gates, committed and pushed synchronized branch, and
   no ontology, fold, label, model, prediction, ensemble, inference, or submission work.
