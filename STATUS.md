# Status

Updated: 2026-08-11 (Chunk 5 two-stage recovery checkpoint)

## Current checkpoint

- Branch: `feat/chunk-5-dicom-pipeline`, based on the unmerged Chunks 1-4 remediation branch.
- Objective: validate deterministic, physically grounded `dicom-model-v1` decoding,
  preprocessing, series-slot assignment, private visual QA, and runtime evidence without ontology,
  folds, labels, model training, prediction, ensemble, or submission work.
- Exit gate: Chunk 5 is **not passed**. It requires a newly gated implementation-freeze commit; an
  immutable private bundle bound to `audit-0002-manifest-remediation` / `manifest-v2`; two distinct
  complete private Kaggle executions over the entire authorized training set; exact deterministic
  comparison; and an authorized human review of at least 100 post-run studies selected without an
  arbitrary maximum until every required represented bounded-registry quota is met, including every
  eligible diagnostic series in those studies, with all nine fixed checks terminal and zero `BLOCK`.
- Private pixels, case details, identifiers, full manifests, review identities, cohort hashes,
  review rows, transform ledgers, and detailed performance artifacts remain inside Kaggle. Only
  explicitly allowlisted, disclosure-validated aggregates may leave that boundary.

## Truthful validation state

| State | Current evidence |
|---|---|
| Implemented | The current working tree separates deterministic proof from QA materialization. Run A and Run B each perform one complete full-data pass and produce a canonical manifest, deterministic metrics, and a deterministic cohort plan. The comparator requires exact manifest and plan bytes plus exact deterministic metrics. The existing review-plan kernel then performs the capacity-gated selected-series replay, double rendering, representative benchmarks, and private plan materialization once. Selector v3 has no arbitrary study maximum. The smoke-output retriever now also accepts exactly the single root execution log that official Kaggle CLI 2.2.4 always downloads beside a matched safe summary, bounds it to 2 MiB, and scans it with the run canary and sensitive-data rules. |
| Locally tested | The exact 29-file D-023 freeze passed the complete 507-test local gate and independent red-team. The two-file smoke-layout correction then passed 11 focused tests, Ruff, formatting, strict mypy, diff checks, and a privacy-safe probe against the completed smoke. Because that correction postdates the freeze, its complete exact-set gate and replacement freeze remain pending. |
| Executed privately on Kaggle | **Four Run A attempts and recovery iteration 5 are terminal failed.** Recovery iteration 5 created freeze `01ea270`, immutable bundle `4127dcc...`, authenticated a new private version-1 input chain, and completed the standalone smoke in 35 minutes 5 seconds. Validation then failed closed with `performance_smoke_output_layout_invalid`; Run A and Run B were not started for that freeze. No failed attempt is Chunk 5 evidence. |
| Remotely tested | Recovery iteration 5 proved the new input binding and completed smoke execution, then exposed the CLI wrapper-log layout mismatch. The corrected retriever passed a bounded probe against that completed output, but policy requires a new fully gated freeze, bundle, dataset identity, and version-1 smoke retry before Run A. |
| Merge-ready | **No.** A newly gated replacement freeze and immutable bundle, authenticated smoke, successful Run A and Run B, comparison, human review, final remote validation, push, and exact-head hosted CI remain pending. |
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
- During the latest recovery, an over-broad search of ignored local artifacts printed obsolete
  canary sentinel strings, local artifact paths, commit and bundle hashes, and the public
  competition slug into an internal tool transcript. It printed no credentials, key bytes,
  authentication tokens, pixels, DICOM headers, reports, or patient, study, or series identifiers.
  The search stopped immediately; nothing was added to the repository or user-facing output. The
  fresh bundle must rotate the canary and private identities, and future ignored-artifact searches
  must use exact bounded allowlists.

## Live competition contract

- The official Kaggle MCP is configured but its tools were not exposed in this session, so the
  authenticated official Kaggle CLI/API fallback was used under the project tool order.
- The live rules, data, evaluation, timeline, runtime, submission, external-asset, team, license,
  sharing, official discussion clarifications, and MIRA license were refreshed at
  `2026-08-11T21:41:12Z`.
- The material contract payload and official-source fingerprints showed **no material drift** from
  the prior canonical contract. The unresolved contradictions and conservative defaults remain in
  `docs/competition_contract/contract.yaml`.
- Kaggle identity verification remains `incomplete_blocking`. The authenticated read-only refresh
  at `2026-08-11T21:41:12Z` confirmed zero submissions. No team action, rules action, public
  release, or model action occurred.

## Remaining checkpoint work

1. Create a new exact clean implementation-freeze commit from the completely gated 29-file staged
   candidate, then build the immutable offline private bundle. All earlier freezes and
   bundles remain superseded and must not be reused as current evidence. Bind the replacement
   cryptographically to the completed `audit-0002-manifest-remediation` source-manifest kernel and
   its private `manifest-v2` outputs; reject the superseded audit.
2. Authenticate private/offline/version-1 metadata, exact input versions, expected file listings,
   hashes, and version-2 absence before each execution.
3. Run the authenticated pre-run smoke and require separate conservative capacity estimates for
   the full-pass stage and the post-comparison replay/render/benchmark stage. Then run private Run A
   from the replacement bundle and validate its complete full pass and deterministic cohort plan
   before starting the distinct full private Run B kernel over the entire authorized training set.
   Every discovered study, series, and file must reconcile to an explicit terminal state; record
   complete private disposition evidence. Each run must also exactly reconcile
   train-series membership, `source_row_count`, organizer plane/fluid/fat flags, and every regular
   DICOM's keyed relative identity, byte size, and raw digest against authenticated `manifest-v2`.
4. Run the separate comparator and require byte-exact equality of the canonical manifests and
   cohort plans plus exact equality of every declared deterministic metric. Investigate every
   mismatch; no unexplained mismatch may pass.
5. In the existing review-plan kernel, authenticate the capacity certificate against the freeze,
   bundle, manifest, Run A, Run B, cohort plan, and renderer. Admit no work unless the physical
   file, byte, time, and disk gates fit. Replay each selected series, render twice, run the declared
   representative benchmarks once, and generate the bound private review plan. Selector v3 may
   exceed 100 studies when required; it has no arbitrary study maximum and may publish only
   `all_required_represented_registry_values_satisfy_quotas` for registry coverage.
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
