# Status

Updated: 2026-08-14 (Chunk 5 r9 dependency-wheel block; D-029/D-030 audit-0003 recovery)

## Current checkpoint

- Branch: `feat/chunk-5-dicom-pipeline`, based on the unmerged Chunks 1-4 remediation branch.
- Objective: validate deterministic, physically grounded `dicom-model-v1` decoding,
  preprocessing, series-slot assignment, private visual QA, and runtime evidence without ontology,
  folds, labels, model training, prediction, ensemble, or submission work.
- Exit gate: Chunk 5 is **not passed**. It requires a newly gated implementation freeze/commit after
  D-029 and D-030; a completed `audit-0003-wheel-sanitization` source audit; an immutable private DICOM-QA
  bundle bound to that validated audit output;
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
| Implemented | D-027 binds review-plan validation to producer contracts, D-028 covers every operational contract section, and D-029 uses one shared stdlib sanitizer in `package_manifest_bundle` to remove dependency-wheel medical payloads, regenerate `RECORD`, and validate other wheels fail closed. D-030 extends that same archive guard to the project wheel and adds one local deployment authenticator that directly reuses the existing DICOM-QA version-1 helpers. Before any network operation, every stage verifies the exact two-file local kernel and hash plus every wheel and `RECORD`, binds resolved dataset metadata to the exact bundle-manifest parent, and binds kernel metadata to its exact sibling kernel directory. Remote gates authenticate exact private dataset version-1 content and hashes, exact kernel version-1 code/source graph, stable listings, and before/after race snapshots. Status output is limited to `PENDING`, `RUNNING`, `COMPLETE`, or `ERROR`; the runbook uses a command-scoped token, protected logs, explicit `/1` references, and bracketed gates. No dependency, framework, or speculative abstraction was added. |
| Locally tested | The r9 candidate passed 529/529 and produced freeze `1db805e` / bundle `28457d...`, but final inspection rejected its dependency-wheel medical payloads before upload. The first r10 candidate then passed 530/530 on exact staged tree `5bea3c110e100e9ddd2d94c8b89c29e1f0ff82a0`; that gate is superseded. Subsequent preflight found and corrected the project-wheel, skippable wheel/`RECORD`, local-kernel upload, remote dataset/kernel version-1, fixed-output credential/status, and manifest-root trust gaps. The mismatched-root regression proves zero remote calls, and independent auth/runbook red-teams pass with no P0/P1. The first complete exact staged D-015 gate passed on tree `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260` over exactly 24 files: pytest 537/537; offline locked reinstall and lock; isolated wheel build/install/import; tracked MIME/symlink/sensitive guard; Ruff check/format; mypy over 25 package and 11 trust-boundary files; config/submission; contract schema and current `contract_drift=no`; schema bytes; pre-commit; detect-secrets; `pip-audit` with no vulnerabilities; and diff, inventory, and unchanged-tree checks. This governance reconciliation changes bytes, so D-015 requires an immediate identical fully restaged rerun; a PASS without further mutation fixes `complete_final_gate=PASS`. |
| Executed privately on Kaggle | Iteration 8 remains terminal `blocked` after authenticated input, smoke, Run A, and Run B workflow-output PASS; comparison and every review stage were not started. R9 never reached upload: no r9 remote artifact exists, and its protected registry row is terminal `blocked` with every remote stage `not_started` and reason `dependency_wheel_medical_payload_detected`. |
| Remotely tested | No r9 remote evidence exists. Iteration 8 remains bounded historical workflow evidence only, not Chunk 5 PASS or accepted comparison, determinism, QA, review, performance, or finalizer evidence. Neither r8 nor r9 may be reused or spliced into the fresh chain. |
| Merge-ready | **No.** The immediate identical fully restaged D-015 rerun, a new freeze/commit and sanitized manifest bundle, private `audit-0003-wheel-sanitization` execution, a new DICOM-QA bundle and full fresh authenticated chain, accepted comparison, QA, human review, finalizer validation, push, and exact-head hosted CI remain pending. Chunk 5 is not passed; all downstream and Chunk 6 work remains blocked. |
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
   so every downstream proof must come from a fresh immutable chain.
2. Preserve r9 freeze `1db805e` / rejected bundle `28457d...` and its terminal `blocked` registry row
   as historical failure evidence only. No r9 remote artifact exists. Do not upload or reuse the
   bundle, splice either old chain, or delete any historical remote artifact.
3. Preserve the independent auth/runbook red-team PASS/no-P0/P1 results and first exact 24-file
   D-015 gate PASS on tree `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260`. Because this
   governance reconciliation changes bytes, immediately restage and rerun the identical complete
   gate; a PASS without further mutation fixes `complete_final_gate=PASS`. The earlier 530/530 gate
   on tree `5bea3c110e100e9ddd2d94c8b89c29e1f0ff82a0` remains superseded. Do not
   weaken runtime, metadata, license, offline, project/dependency-wheel, `RECORD`, local-kernel, or
   remote version-1 authentication.
4. Create the new freeze/commit and sanitized manifest bundle, then complete the private
   `audit-0003-wheel-sanitization` execution and validate its outputs before creating a DICOM-QA
   bundle bound to them.
   `audit-0002-manifest-remediation` remains historical scientific evidence but is superseded as a
   reusable source root because the same helper built its bundle.
5. Use only the D-030 command-scoped, fixed-output deployment gates. Before network access, bind
   dataset metadata to the exact verified bundle-manifest parent and kernel metadata to its exact
   sibling kernel directory; then authenticate private/offline dataset and kernel version 1, exact
   content/source/listing hashes, stable before/after snapshots, and version-2 absence. Keep
   protected logs and private references inside the approved boundary.
6. Create and authenticate the replacement private version-1 dataset chain, rerun the authenticated
   pre-run smoke, and require separate conservative capacity estimates for
   the full-pass stage and the post-comparison replay/render/benchmark stage. Then run private Run A
   from the replacement bundle and validate its complete full pass and deterministic cohort plan
   before starting the distinct full private Run B kernel over the entire authorized training set.
   Every discovered study, series, and file must reconcile to an explicit terminal state; record
   complete private disposition evidence. Each run must also exactly reconcile
   train-series membership, `source_row_count`, organizer plane/fluid/fat flags, and every regular
   DICOM's keyed relative identity, byte size, and raw digest against authenticated `manifest-v2`.
7. Run the separate comparator and require byte-exact equality of the canonical manifests and
   cohort plans plus exact equality of every declared deterministic metric. Accept retrieval only
   through the D-026 exact-summary/optional-safe-log boundary. Investigate every mismatch; no
   unexplained mismatch or invalid local layout may pass.
8. In the existing review-plan kernel, authenticate the capacity certificate against the freeze,
   bundle, manifest, Run A, Run B, cohort plan, and renderer. Admit no work unless the physical
   file, byte, time, and disk gates fit. Replay each selected series, render twice, run the declared
   representative benchmarks once, and generate the bound private review plan. Selector v3 may
   exceed 100 studies when required; it has no arbitrary study maximum and may publish only
   `all_required_represented_registry_values_satisfy_quotas` for registry coverage.
9. Authenticate the safe private UI template, then have the authorized human use Chrome Copy & Edit
   to create a distinct private review-session version 1. The `START` gate must precede artifact
   access. The plan-bound private context must show plane, slot, retention, six-slot missing-mask,
   and ordinal sibling disposition evidence, and artifacts must resolve only under authenticated Run
   A. Review every eligible diagnostic series with the nine frozen checks and zero `BLOCK`.
10. Run the pinned private finalizer against the exact runs, comparison, plan, and completed session.
   Retrieve and validate only approved sanitized determinism plus `human_review_summary.json` and
   `final_performance_report.json`; exact review counts remain private.
11. Record actual identities, timing, memory, determinism, review completion, and remaining risks;
   run any required final exact-set gate, push only after approval, verify the clean synchronized
   branch and hosted CI, and stop. Do not start ontology, folds, labels, or model work.
