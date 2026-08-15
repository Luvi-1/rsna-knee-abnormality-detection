# Status

Updated: 2026-08-14 (Chunk 5 iteration-8 terminal blocked; D-027/D-028 prefreeze recovery)

## Current checkpoint

- Branch: `feat/chunk-5-dicom-pipeline`, based on the unmerged Chunks 1-4 remediation branch.
- Objective: validate deterministic, physically grounded `dicom-model-v1` decoding,
  preprocessing, series-slot assignment, private visual QA, and runtime evidence without ontology,
  folds, labels, model training, prediction, ensemble, or submission work.
- Exit gate: Chunk 5 is **not passed**. It requires a newly gated iteration-9 implementation-freeze
  commit; an immutable private bundle bound to `audit-0002-manifest-remediation` / `manifest-v2`;
  two distinct complete private Kaggle executions over the entire authorized training set; an
  accepted exact deterministic comparison; and an authorized human review of at least 100 post-run
  studies selected without an arbitrary maximum until every required represented bounded-registry
  quota is met, including every eligible diagnostic series in those studies, with all nine fixed
  checks terminal and zero `BLOCK`.
- Private pixels, case details, identifiers, full manifests, review identities, cohort hashes,
  review rows, transform ledgers, and detailed performance artifacts remain inside Kaggle. Only
  explicitly allowlisted, disclosure-validated aggregates may leave that boundary.

## Truthful validation state

| State | Current evidence |
|---|---|
| Implemented | Recovery iteration 8 implements D-026 and preserves the frozen separation between two independent deterministic full passes and one later capacity-gated QA materialization. Frozen-source preflight then found two independent P1 plan-contract defects before comparison launch: the producer requires six QA artifacts and permits `orthogonal.png` only when renderable while the validator required exactly seven, and the automatic producer emits `dicom_qa_review_started` / four `dicom_qa_plan_progress` events / `dicom_qa_review_template_complete` while the validator expected generic run boundaries. The iteration-9 D-027 candidate binds the validator to the producer's exact required/allowed suffix sets and actual automatic event sequence. D-028 adds the six previously omitted operational contract sections to the existing `MATERIAL_SECTIONS` so mutation or removal cannot falsely yield `contract_drift=no`. Neither fix relaxes an existing trust boundary. |
| Locally tested | The D-026 candidate passed its complete exact-set gate with pytest 528/528 and produced iteration-8 freeze `4958c4a` and immutable bundle `09502a...`. D-027 and D-028 pass smoke 6/6, combined focused 155/155, and post-fix red-team PASS with no P0/P1. The r9 exact 16-file candidate then passed its first complete release gate on staged tree `ed3720d8159b1242a6b72cab13dec43a4406f25a`: pytest 529/529; isolated wheel build/install/import; Ruff check and format; mypy over the package plus nine trust-boundary files; pre-commit; secret and privacy checks; dependency audit; contract schema and current `contract_drift=no`; exact inventory; and unchanged-tree checks. This governance reconciliation changes that staged tree, so D-015 requires the main agent to restage and immediately rerun the identical complete gate. If that rerun succeeds, the final release record is `complete_final_gate=PASS`; any failure invalidates this record and must be corrected before freeze. |
| Executed privately on Kaggle | Iteration 8 authenticated and passed its private/offline/version-bound inputs, standalone smoke, full-data Run A, and full-data Run B. Run B version 1 reached `COMPLETE` at 25,940 seconds; two independent bounded read-only polls 71 seconds apart agreed, and the established authenticated validator returned `dicom_qa_output_validation=PASS mode=workflow stage=run-b`. The protected registry row is terminal `blocked`: input, smoke, Run A, and Run B are `passed`; comparison, `review_plan`, and `human_review` are `not_started`; `completed_utc` is set; and integrity, foreign keys, and mode are `PASS`. UI/session creation and finalization were not launched. |
| Remotely tested | Iteration 8 proves authenticated input, smoke, Run A, and Run B workflow-output validation only. It is not Chunk 5 PASS and proves no accepted comparison, determinism, QA materialization, benchmarks, visual correctness, review, performance, or finalizer result. Because D-027 and D-028 correct frozen source, iteration-8 comparison and QA must never launch; its terminal `blocked` row cannot be spliced into iteration 9. |
| Merge-ready | **No.** The iteration-9 freeze/commit, immutable bundle, full fresh authenticated private chain, accepted comparison, private QA materialization, human review, finalizer validation, push, and exact-head hosted CI remain pending. D-015's immediate identical post-governance rerun controls the final local release record. |
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
  next fresh bundle must rotate the canary and private identities, and future ignored-artifact
  searches must use exact bounded allowlists.

## Live competition contract

- The official Kaggle MCP refresh returned competition metadata, operational page bodies with all
  nine tracked hashes, the aggregate file summary, the entered-competition match, and the recorded
  organizer clarification topics.
- The live rules, data, evaluation, timeline, runtime, submission, external-asset, team, license,
  sharing, official discussion clarifications, and MIRA license were refreshed at
  `2026-08-15T00:00:25Z`.
- All nine operational hashes, the 819,640-file / 819,635-DICOM / five-CSV aggregate inventory,
  deadlines, runtime, limits, entered state, and RSNA MIRA PDF were unchanged. The unresolved
  contradictions and conservative defaults remain in `docs/competition_contract/contract.yaml`.
- Newly discovered Host topic `733965` permits compliant commercial LLM or external inference under
  the Rules, equal-access, and minimal-cost conditions and clarifies that report processing is not
  itself private sharing.
- The repository's stricter boundary remains unchanged: no raw DICOM pixels, radiology reports,
  patient-level metadata, identifiers, private competition code or data, or private artifacts may
  be sent to any external LLM, API, or service. Only recognized members of the same official Kaggle
  team may receive private competition code or data.
- The official interface confirms the account is entered but does not expose current identity-
  verification state, so submission and prize actions remain blocked. No team action, rules action,
  submission, public release, or model action occurred.
- The checkpoint relay could not connect to Chrome during this recovery boundary. No new reviewer
  response or decision exists; the user's standing Chunk 5 authorization remains controlling.

## Remaining checkpoint work

1. Preserve iteration 8 only as a terminal `blocked` historical chain. Do not launch its comparison,
   review-plan, UI/session, human-review, or finalizer stages; D-027 and D-028 change frozen source,
   so every downstream proof must come from a fresh iteration-9 immutable chain.
2. Complete the D-027 plan-contract and D-028 material-drift corrections. Require the producer's
   exact six mandatory artifacts, permit only the producer-declared optional `orthogonal.png`,
   validate the actual automatic start/progress/completion events, and reject every other entry,
   wrong path,
   duplicate, symlink, special file, oversized payload, canary hit, or sensitive content. Require
   drift sensitivity for mutation and wholesale removal of all operational contract sections.
   Restage this governance reconciliation and immediately rerun the identical complete gate under
   D-015; a successful rerun fixes the final record at `complete_final_gate=PASS`, while any failure
   invalidates the record and must be corrected. Then create a clean iteration-9 implementation
   freeze/commit and build a new immutable offline private bundle. Iteration-8 freeze `4958c4a`,
   bundle `09502a...`, and their
   terminal blocked chain must not be reused as current execution evidence. Bind the replacement
   cryptographically to the completed `audit-0002-manifest-remediation` source-manifest kernel and
   its private `manifest-v2` outputs; reject the superseded audit.
3. Authenticate private/offline/version-1 metadata, exact input versions, expected file listings,
   hashes, and version-2 absence before each execution.
4. Create and authenticate the replacement private version-1 dataset chain, rerun the authenticated
   pre-run smoke, and require separate conservative capacity estimates for
   the full-pass stage and the post-comparison replay/render/benchmark stage. Then run private Run A
   from the replacement bundle and validate its complete full pass and deterministic cohort plan
   before starting the distinct full private Run B kernel over the entire authorized training set.
   Every discovered study, series, and file must reconcile to an explicit terminal state; record
   complete private disposition evidence. Each run must also exactly reconcile
   train-series membership, `source_row_count`, organizer plane/fluid/fat flags, and every regular
   DICOM's keyed relative identity, byte size, and raw digest against authenticated `manifest-v2`.
5. Run the separate comparator and require byte-exact equality of the canonical manifests and
   cohort plans plus exact equality of every declared deterministic metric. Accept retrieval only
   through the D-026 exact-summary/optional-safe-log boundary. Investigate every mismatch; no
   unexplained mismatch or invalid local layout may pass.
6. In the existing review-plan kernel, authenticate the capacity certificate against the freeze,
   bundle, manifest, Run A, Run B, cohort plan, and renderer. Admit no work unless the physical
   file, byte, time, and disk gates fit. Replay each selected series, render twice, run the declared
   representative benchmarks once, and generate the bound private review plan. Selector v3 may
   exceed 100 studies when required; it has no arbitrary study maximum and may publish only
   `all_required_represented_registry_values_satisfy_quotas` for registry coverage.
7. Authenticate the safe private UI template, then have the authorized human use Chrome Copy & Edit
   to create a distinct private review-session version 1. The `START` gate must precede artifact
   access. The plan-bound private context must show plane, slot, retention, six-slot missing-mask,
   and ordinal sibling disposition evidence, and artifacts must resolve only under authenticated Run
   A. Review every eligible diagnostic series with the nine frozen checks and zero `BLOCK`.
8. Run the pinned private finalizer against the exact runs, comparison, plan, and completed session.
   Retrieve and validate only approved sanitized determinism plus `human_review_summary.json` and
   `final_performance_report.json`; exact review counts remain private.
9. Record actual identities, timing, memory, determinism, review completion, and remaining risks;
   run any required final exact-set gate, push only after approval, verify the clean synchronized
   branch and hosted CI, and stop. Do not start ontology, folds, labels, or model work.
