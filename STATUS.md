# Status

Updated: 2026-08-10 (Chunk 5 Run A performance-recovery checkpoint)

## Current checkpoint

- Branch: `feat/chunk-5-dicom-pipeline`, based on the unmerged Chunks 1-4 remediation branch.
- Objective: validate deterministic, physically grounded `dicom-model-v1` decoding,
  preprocessing, series-slot assignment, private visual QA, and runtime evidence without ontology,
  folds, labels, model training, prediction, ensemble, or submission work.
- Exit gate: Chunk 5 is **not passed**. It requires a newly gated implementation-freeze commit; an
  immutable private bundle bound to `audit-0002-manifest-remediation` / `manifest-v2`; two distinct
  complete private Kaggle executions over the entire authorized training set; exact deterministic
  comparison; and an authorized human review of at least 100 post-run stratified studies and every
  eligible diagnostic series in those studies, with all nine fixed checks terminal and zero `BLOCK`.
- Private pixels, case details, identifiers, full manifests, review identities, cohort hashes,
  review rows, transform ledgers, and detailed performance artifacts remain inside Kaggle. Only
  explicitly allowlisted, disclosure-validated aggregates may leave that boundary.

## Truthful validation state

| State | Current evidence |
|---|---|
| Implemented | Core strict decode/geometry/preprocessing, six-slot assignment, private QA, benchmarks, full-run orchestration, distinct Run A/Run B packaging, exact comparison, cohort planning, private review finalization, and disclosure-controlled validation are implemented. The working-tree performance recovery streams the canonical NPY checksum during its single ephemeral write, caches invariant package-version provenance once per process, emits only a fixed safe phase sequence, runs an authenticated source-manifest-stratified fail-fast throughput projection before the full pass, and bounds execution at 27,000 seconds self / 28,800 seconds outer under the 32,400-second competition ceiling. Freezes `a5a44ac`, `e6e5b35`, and `60df41c` and bundles `7cf43...`, `3a361...`, and `3dc575...` are superseded-pending. |
| Locally tested | The source-schema correction's exact seven-file candidate passed the complete 405-test gate before freeze `60df41c`. The later performance-recovery working tree has focused regression evidence only. Its complete exact-file gate, clean freeze, immutable bundle, and authenticated private retry are pending; the prior gate does not cover these new bytes. |
| Executed privately on Kaggle | **Three Run A attempts are terminal failed.** The first reported `source_manifest_version_mismatch`; the second reported `source_manifest_input_invalid`; retry `r3` authenticated its inputs, entered processing, and failed closed with `self_deadline_exceeded` at 21,664 seconds. Run B was not started. No incomplete run satisfies the Chunk 5 exit gate. |
| Remotely tested | Freeze `60df41c` / bundle `3dc575...` passed the authenticated private/offline/version-1 input gate. Run A `r3` then exhausted the old 21,600-second self-deadline during processing; no completed full-pass evidence, deterministic comparison, accepted benchmark, review plan, or human review exists. |
| Merge-ready | **No.** A newly gated freeze and immutable bundle, successful Run A and Run B, comparison, human review, final remote validation, push, and exact-head hosted CI remain pending. |
| Merged into `main` | **No.** Merge is outside this checkpoint and requires explicit human approval. |

## Corrections to the prior status

- The prior status said the final secret scan passed. That statement covered a pre-final file set;
  the committed branch subsequently contained five provenance/content hashes that the high-entropy
  detector flagged. Manual review found no credential, token, private URL, patient identifier, or
  private competition artifact identifier in those five values. The narrow baseline correction and
  detection regression exist locally. The complete staged-tree, cumulative-diff, and generated-
  artifact checks now pass. Hosted CI passed on release candidate `cc050a2`; later commits remain
  subject to the same gate.
- The prior status said rare values could not be inferred. The old field-by-field suppression
  allowed a below-threshold value to be reconstructed from published complements. The old
  sanitized artifacts and all claims based on that release contract are superseded. The replacement
  uses one central, joint complementary-disclosure policy with qualitative/range tokens and
  adversarial arithmetic checks; the fresh private full-data release passed that boundary.
- The prior `protected-groups-v1` result mixed strong duplicate/repeat evidence with weak or
  overflow-candidate similarities. Its zero-crossing statement did not establish fold feasibility.
  The completed v2 audit keeps hard protected components separate from soft review/stress
  candidates, preserves edge provenance privately, and reports `protected_graph_closed: true`.
  `folds_assigned: false` and `fold_feasibility: not_assessed` remain controlling.
- The prior DICOM status recorded nonzero decode/quarantine findings without a complete case-level
  root-cause and disposition audit. The v2 rerun still reports the approved
  `below_threshold_nonzero` token for decode failures and quarantined files/series, but now reports
  `unexplained_dicom_issues: zero`, `dicom_issue_dispositions_complete: true`, and terminal
  file/series accounting. Case detail remains private.

## Live competition contract

- The official Kaggle MCP is configured but its tools were not exposed in this session, so the
  authenticated official Kaggle CLI/API fallback was used under the project tool order.
- The live rules, data, evaluation, timeline, runtime, submission, external-asset, team, license,
  sharing, official discussion clarifications, and MIRA license were refreshed at
  `2026-08-10T07:19:35Z`.
- The material contract payload and official-source fingerprints showed **no material drift** from
  the prior canonical contract. The unresolved contradictions and conservative defaults remain in
  `docs/competition_contract/contract.yaml`.
- Kaggle identity verification remains `incomplete_blocking`. The authenticated read-only refresh
  at `2026-08-10T07:19:35Z` confirmed zero submissions. No team action, rules action, public
  release, or model action occurred.

## Remaining checkpoint work

1. Run the complete gate over the performance-recovery candidate, then create a new exact
   clean implementation-freeze commit and immutable offline private bundle.
   Freezes `a5a44ac`, `e6e5b35`, and `60df41c` and bundles `7cf43...`, `3a361...`, and `3dc575...`
   remain superseded-pending and must not be reused as current evidence. Bind the replacement
   cryptographically to the completed `audit-0002-manifest-remediation` source-manifest kernel and
   its private `manifest-v2` outputs; reject the superseded audit.
2. Authenticate private/offline/version-1 metadata, exact input versions, expected file listings,
   hashes, and version-2 absence before each execution.
3. Retry full private Run A from the replacement bundle. Require the authenticated stratified
   throughput sample to fit the projected full pass plus the 3,600-second post-pass reserve, then
   validate the complete run before starting Run B. Then run the distinct full private Run B kernel
   over the entire authorized training set.
   Every discovered study, series, and file must reconcile to an explicit terminal state; record
   complete private performance and disposition evidence. Each run must also exactly reconcile
   train-series membership, `source_row_count`, organizer plane/fluid/fat flags, and every regular
   DICOM's keyed relative identity, byte size, and raw digest against authenticated `manifest-v2`.
4. Run the separate comparator and require exact equality for every declared deterministic
   artifact and metric. Investigate every mismatch; no unexplained mismatch may pass.
5. Select `qa-cohort-selection-v2` only after the full pass, covering every materially represented
   available stratum and at least 100 reviewable studies. Generate the bound private review plan.
6. Authenticate the safe private UI template, then have the authorized human use Chrome Copy & Edit
   to create a distinct private review-session version 1. The `START` gate must precede artifact
   access. The plan-bound private context must show plane, slot, retention, six-slot missing-mask,
   and ordinal sibling disposition evidence, and artifacts must resolve only under authenticated Run
   A. Review every eligible diagnostic series with the nine frozen checks and zero `BLOCK`.
7. Run the pinned private finalizer against the exact runs, comparison, plan, and completed session.
   Retrieve and validate only approved sanitized determinism plus `human_review_summary.json` and
   `final_performance_report.json`; exact review counts remain private.
8. Record actual identities, timing, memory, determinism, review completion, and remaining risks;
   run any required final exact-set gate, push only after approval, verify the clean synchronized
   branch and hosted CI, and stop. Do not start ontology, folds, labels, or model work.
