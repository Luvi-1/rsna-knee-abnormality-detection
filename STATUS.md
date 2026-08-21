# Status

Updated: 2026-08-21 (Chunk 5 r13 terminal smoke recovery)

## Current checkpoint

- Branch: `feat/chunk-5-dicom-pipeline`, based on the unmerged Chunks 1-4 remediation branch.
- Objective: validate deterministic, physically grounded `dicom-model-v1` decoding,
  preprocessing, series-slot assignment, private visual QA, and runtime evidence without ontology,
  folds, labels, model training, prediction, ensemble, or submission work.
- Current authorization gate: Chunk 5 is **not passed**. R13 is terminal failed at performance smoke
  and cannot be resumed or spliced. The prior exact 15-file tree
  `afd8909a798d30fa9314fe6568768bca68fbda14` passed its complete D-015 gate but is now historical
  and superseded. After the governance bytes were restaged, exact tree
  `e298964891b214bfbf4dc06725f2cde3b3bd3f74` failed the mandatory pytest rerun with one failure and
  537 passes because a manifest-runner regression compared nondeterministic real wall-clock runtime.
  The minimal test-only correction is tracked. Exact 16-file staged tree
  `22c80aaa8f30d47a21e1a43fc3e945ab831c79ea` passed its first complete D-015 gate, but this eight-
  file governance reconciliation changes bytes. One immediate fully restaged identical complete
  rerun and final red-team remain required; no current `complete_final_gate=PASS` exists. Only PASS
  with no later byte change may authorize a clean freeze, deterministic bundle, authenticated
  identity-absence proof, and append-only registry preparation. Any rerun failure invalidates the
  first-pass final-gate evidence and requires this record to be corrected. Those prerequisites
  authorize only one fresh private, offline, version-bound successor smoke. Its authenticated
  terminal/output validation must pass and a fresh decision must be recorded before Run A; Run A,
  Run B, comparison, review-plan, human review, finalization, and Chunk 6 remain out of scope.
- Eventual Chunk 5 exit still requires two distinct complete private Kaggle executions over the
  entire authorized training set, accepted exact deterministic comparison, and authorized human
  review, but none of those later stages is authorized by this checkpoint.
- Private pixels, case details, identifiers, full manifests, review identities, cohort hashes,
  review rows, transform ledgers, and detailed performance artifacts remain inside Kaggle. Only
  explicitly allowlisted, disclosure-validated aggregates may leave that boundary.

## Current r13 terminal checkpoint

Legacy Kaggle authentication was restored without exposing credential material. One bounded,
authenticated check proved that the exact r13 performance-smoke version 1 is terminal `ERROR`.
The corrected strict failure-log validator binds the smoke producer's exact start, progress,
terminal, phase, and prefix-length state machine and returns
`phase=performance_smoke`, `code=throughput_projection_exceeds_budget`. The protected registry row
is terminal `failed`: input authentication is `passed`; performance smoke is failed; Run A, Run B,
comparison, review-plan, and human review are `not_started`. No r13 rerun, splice, Run A, downstream
launch, or public action occurred. The safe log contains exactly one smoke progress event, localizing
the failure to the inner throughput gate. The former monolithic smoke-plus-full-run formula survived
the later standalone-smoke split and double-counted sample elapsed time. The six-file source/test
correction preserves pre-smoke setup accounting, the conservative full-pass projection, the
3,600-second reserve, both deadlines, and all privacy/source gates while removing only that stale
leading term at both admission sites. Targeted tests and static checks pass. The complete exact
15-file staged tree `afd8909a798d30fa9314fe6568768bca68fbda14` passed the complete D-015 gate with
the recorded lock, build/import, static, pytest 538/538, configuration, contract, schema, privacy,
dependency, inventory, residue, and unchanged-tree checks. That result is historical and superseded.
After the governance bytes were restaged, exact tree
`e298964891b214bfbf4dc06725f2cde3b3bd3f74` failed the mandatory pytest rerun with one failure and
537 passes: `tests/test_manifest_runner.py` required two otherwise exact runs to report identical
`runtime.elapsed_seconds`, but the first measured 3 seconds and the rerun 2 seconds. Production uses
`ceil(monotonic - start)`, and the validators intentionally accept an integer from zero through the
configured maximum, so production, disclosure, and schema behavior remain correct. The minimal
test-only correction reuses the existing `_validate_exact_aggregates` on the rerun and compares all
aggregate sections except `runtime`, while retaining exact table-hash, study-key, QA-byte, and
audit-key equality. The focused target passed 3/3 repeatedly, the complete manifest-runner file
passed 12/12, and Ruff check/format plus the scoped diff check pass. Exact staged tree
`22c80aaa8f30d47a21e1a43fc3e945ab831c79ea` then passed the first complete 16-file D-015 gate:
locked offline `uv` lock/sync; full pytest 538/538 in 63.84 seconds; isolated wheel build, offline
install, and import of `rsna-knee 0.1.0`; Ruff PASS with 124 files formatted; mypy over 25 package
plus 16 trust-boundary files; valid configuration with the established hash and synthetic submission
`rows=2`; canonical contract schema valid, current `contract_drift=no`, and generated schema bytes
current; sensitive guard PASS; tracked MIME exact at 154 regular files plus the one exact
`.agents/skills` symlink; `pip-audit` with no known vulnerabilities; all pre-commit hooks PASS; full
tracked detect-secrets PASS; and exact 16-file inventory, no unstaged or untracked residue, and
unchanged-tree PASS. This governance reconciliation changes bytes, so D-015 requires one immediate
fully restaged identical complete rerun. Only PASS with no later byte change fixes
`complete_final_gate=PASS`; any failure invalidates the first-pass final-gate evidence and requires
this record to be corrected. Final red-team, freeze, bundle, identity-absence proof, registry
preparation, and fresh successor smoke remain pending, and Run A is not authorized.

## Truthful validation state

| State | Current evidence |
|---|---|
| Implemented | D-033 binds failure validation to the producer's closed generic or smoke protocol without changing the CLI. D-034 removes only the stale leading sample `elapsed +` at both throughput admission sites after smoke became standalone; pre-smoke setup, full projection, 3,600-second reserve, self/outer deadlines, privacy, source authentication, and fail-closed behavior remain unchanged. |
| Locally tested | The corrected validator safely classified exact r13 as `phase=performance_smoke`, `code=throughput_projection_exceeds_budget`; its one progress event localizes the failure to the inner gate. Targeted protocol tests, 3,801/3,799-second budget boundaries, and the 4,320-second standalone ceiling pass. The prior 15-file PASS and failed restaged tree are historical. The minimal test-only correction passed focused 3/3 repeatedly and the manifest-runner file 12/12. Exact 16-file tree `22c80aaa8f30d47a21e1a43fc3e945ab831c79ea` passed the first complete D-015 gate with pytest 538/538 in 63.84 seconds and every recorded check. These governance byte changes require one identical fully restaged complete rerun and final red-team. |
| Executed privately on Kaggle | Exact r13 performance-smoke version 1 authenticated and reached terminal `ERROR`. Input authentication passed; performance smoke failed; Run A, Run B, comparison, review-plan, and human review remain `not_started`. No rerun, splice, downstream launch, output publication, or human QA occurred. |
| Remotely tested | R13 proves only authenticated input and the terminal smoke failure. The budget projection blocks full compute, determinism, QA materialization, visual correctness, human review, performance finalization, and Chunk 5 PASS. Historical r8-r12 evidence may not be resumed or spliced. |
| Merge-ready | **No.** The first complete 16-file gate passed, but these governance bytes invalidate a final-gate claim until the fully restaged identical complete rerun and final red-team pass with no later byte change. `complete_final_gate=PASS` remains unset. Even then, only a gated fresh successor smoke is in scope; Run A and every downstream stage require authenticated smoke validation and a fresh decision. |
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

- The official Kaggle MCP refresh returned competition metadata, the same operational pages, the
  aggregate file summary, the entered-competition match, and the recorded organizer clarification
  topics.
- The live rules, data, evaluation, timeline, runtime, submission, external-asset, team, license,
  sharing, official discussion clarifications, and MIRA license were refreshed at
  `2026-08-21T20:03:04Z` with no material drift. The latest snapshot is
  `docs/competition_contract/2026-08-21T200304Z.md`.
- The 819,640-file / 819,635-DICOM / five-CSV aggregate inventory, deadlines, runtime, limits, and
  entered state remain unchanged. The unresolved contradictions and conservative defaults remain in
  `docs/competition_contract/contract.yaml`.
- Host topic `733965` continues to permit compliant commercial LLM or external inference under
  the Rules, equal-access, and minimal-cost conditions and clarifies that report processing is not
  itself private sharing.
- The repository's stricter boundary remains unchanged: no raw DICOM pixels, radiology reports,
  patient-level metadata, identifiers, private competition code or data, or private artifacts may
  be sent to any external LLM, API, or service. Only recognized members of the same official Kaggle
  team may receive private competition code or data.
- The official interface confirms the account is entered but does not expose current identity-
  verification state, so submission and prize actions remain blocked. No team action, rules action,
  submission, public release, or model action occurred.
- The 2026-08-21 refresh found no material contract drift; later participant activity in Host topic
  `733965` added no new authoritative rule text. Identity-verification state is unavailable through
  the read-only official interface and therefore remains fail closed, not known incomplete.
- The checkpoint relay could not connect to Chrome during this recovery boundary. No new reviewer
  response or decision exists. The standing Chunk 5 authorization is bounded by the latest
  smoke-only checkpoint and does not authorize Run A.

## Remaining checkpoint work

1. Preserve r13 as terminal failed evidence. Do not resume, rerun, mutate, delete, or splice it; Run A
   and every downstream stage remain `not_started`.
2. Fully restage exactly the current 16-file candidate—seven source/tests, these eight governance
   files, and `docs/competition_contract/2026-08-21T200304Z.md`—then rerun the identical complete
   D-015 gate and final red-team. The first PASS on tree
   `22c80aaa8f30d47a21e1a43fc3e945ab831c79ea` is valid development evidence, but these governance
   byte changes prevent `complete_final_gate=PASS`; only the rerun's PASS with no later byte change
   fixes it. Any failure invalidates the first-pass final-gate evidence and requires the record to be
   corrected. The older 10-file, 24-file, and 15-file results remain historical and superseded.
3. Only after that rerun and final red-team PASS, create a clean freeze and deterministic bundle,
   prove authenticated identity absence, prepare the append-only registry, and run one fresh
   private/offline/version-1 successor performance smoke under every D-030
   root/content/source/listing/race and fixed-output gate. Do not splice historical evidence.
4. Authenticate and validate the successor smoke's terminal state and allowlisted output, then stop.
   Record a fresh decision before Run A. Do not start Run A, Run B, comparison, review-plan, UI,
   human review, finalization, ontology, folds, labels, model work, or Chunk 6 under this checkpoint.
