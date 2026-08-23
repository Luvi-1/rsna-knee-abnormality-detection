# Status

Updated: 2026-08-23 (Chunk 5 r15 loop-breaker, live-certified core)

## Current r15 terminal checkpoint and certified-core policy

R15 is terminal `failed` at review-plan (`phase=review`,
`code=input_discovery_invalid`) with human review `not_started`. Its protected registry row
`preprocess-0001-dicom-pipeline-r15` records inputs, performance smoke, Run A, Run B, and
deterministic comparison all authenticated `passed`; live Kaggle confirms the A/B/comparison
kernels `COMPLETE` and the plan kernel `ERROR`. The r14 row remains preserved below. Under
decision **D-036**, passed cores from such chains may be bound into a Core Execution Certificate
and consumed by an independently versioned QA Adapter without rerunning A/B/comparison;
arbitrary splicing remains prohibited. The certifier
(`scripts/certify_dicom_qa_core.py`) and its tamper matrix
(`tests/test_core_execution_certificate.py`, 7/7 PASS offline) exist. Under decision **D-037**,
workflow authentication now loads the finalizer from the exact file sealed in the verified r15
bundle rather than the mutable working tree; the frozen hash remains absolute and all temporary
adapter-bypass scars were removed. Focused checks are now 77/77 PASS, full pytest is 575/575
exit 0 (zero failures), Ruff check/format and both strict mypy scopes PASS (25 source files,
3 trust-boundary files). The live end-to-end core certification PASSED at
2026-08-22T22:08:33Z with payload f7736e681f54dd9d2ae1ad7cd75a3a1208f7efec4967f6d3bdae99e81cbfa55d
and offline verify PASS; the certificate artifact is retained under
artifacts/dicom-qa-core-certificates/. The single authorized bounded mount-layout diagnostic
completed, proving modern Kaggle mounts inputs as competitions/<slug>,
datasets/<owner>/<slug>, and notebooks/<owner>/<slug>. Commit 0a5fc0e fixed certifier live-fetch
pattern matching; commit 1bdcc01 extended the resolver to all proven type-prefixed forms with
duplicate/symlink rejection and full regression coverage. The QA adapter freeze/bundle is the
next step. Chunk 5 is not passed. Submission, merge, publication,
and Chunk 6 remain blocked pending explicit human approval.

### r15 adapter remediation-two terminal update 2026-08-23

Remediation two is committed at `1c4fa7e594ece3752b32281ccc7c23d49814986f`, packaged as bundle
`fd8238f94ef1f91282b8a9d904c3a273e56e5499779a2b5700b920a1bf42b8cf`, and privately deployed once
as dataset `lavicheema/rsna-knee-dicom-qa-bundle-1c4fa7e-fd8238f94ef1` version 1 (`ready`). Its
runner is byte-identical to the certified producer
`5b71cbc3e36f862c41edfe93e55186bc46ed541b418de0c7325238b315b8bf4a`, the sealed finalizer contains
the intended core-reuse policy, and the retained Core Execution Certificate verifies PASS. The
single exact authenticated inputs validation failed closed locally with `review_identity_invalid`
before any remote launch: the validator still expects upstream refs from mutable run-config
`core_reuse`, while remediation two intentionally seals them in the finalizer. Live checks confirm
all four r15 upstream kernels remain COMPLETE and plan identity
`lavicheema/rsna-knee-dqa-plan-1c4fa7e-fd8238f94ef1` is absent. Under D-041 this third adapter
attempt is terminal; no fourth iteration is authorized without explicit human approval.

### r15 adapter validator correction 2026-08-23 (human-approved, in progress)

The operator approved exactly one validator-only correction under D-042. The output validator now
sources optional certified-core reuse from the authenticated sealed finalizer's
`CORE_REUSE_POLICY` instead of run-config, preserving every existing fail-closed policy check and
keeping downstream adapter identities fresh. Regression coverage proves sealed-policy agreement and
malformed-policy rejection. Complete local gate PASS on this change against d3d2d7c: Ruff
format/check (127 files), strict mypy src (25 files), strict mypy trust boundary (3 files), pytest
587 passed exit 0, sensitive-file guard, tracked secret scan, and git diff --check. No DICOM,
runner, finalizer, packaging, certified-core evidence, or remote state changed yet. Next gated
steps are one fresh bundle/deployment, one inputs validation, and one review-plan push; stop again
at the human visual-QA boundary.

### r15 adapter route terminal classification 2026-08-23 (D-043)

The corrected adapter committed at `533ae53d2899e190e97751d3018ad493faf2aa52`, packaged as bundle
`988a62aa6688f42d4defb56e9e3b2821dff64bde37db9995986a3aa078ae375d`, deployed once as dataset
`lavicheema/rsna-knee-dicom-qa-bundle-533ae53-988a62aa6688` v1 (`ready`), passed exact
authenticated inputs validation (`dicom_qa_output_validation=PASS mode=workflow stage=inputs`),
proved plan identity absent, then pushed review-plan v1 exactly once. Plan kernel
`lavicheema/rsna-knee-dqa-plan-533ae53-988a62aa6688` reached terminal `ERROR` in about 12.5s with
`phase=review code=private_cohort_plan_invalid` before any replay, rendering, or human review.
Root cause is proven static: the sealed certified runner's preparation path binds consumed core
artifacts' embedded provenance to the executing bundle identity; certified outputs permanently
carry the frozen r15 identity while any compliant fresh adapter carries a different content-derived
identity, so this gate cannot pass without changing certified runner semantics. Per the approved
bounds no further autonomous iteration occurred. Chunk 5 remains technically incomplete pending a
human decision: authorize a runner-semantics redesign plus recertification, schedule a fully gated
fresh successor chain, or park the effort.
## Historical r14 terminal checkpoint

R14 is terminal `failed` at review-plan. Its exact authenticated inputs, performance smoke, Run A,
Run B, and deterministic comparison all passed. Run A completed in 7h21m20s; Run B completed in
6h36m06s; comparison proved the required deterministic artifacts equal. Review-plan v1 then
returned stable terminal `ERROR`. The retained no-match session log initially exposed a consumer
defect: the failure validator did not recognize the review producer's exact event protocol. The
minimal shared correction now validates that protocol and classifies the frozen failure as
`phase=review`, `code=input_discovery_invalid` without exposing private content. The failure occurred
before cohort replay. Official Kaggle supports both `/kaggle/input/<slug>` and collision-safe
`/kaggle/input/<owner>/<slug>` mounts; the recovery candidate accepts only those two exact derived
roots, requires exactly one, and preserves every shallow-search, symlink, duplicate, count, and
counterfeit-source rejection. Focused checks and the complete DICOM-QA identity/packaging suites
pass. No r14 retry, v2, UI, human review, finalizer, submission, or Chunk 6 action occurred. Chunk 5
remains not passed; a new fully gated immutable successor is required.
The latest official refresh is `docs/competition_contract/2026-08-22T062926Z.md` with no material
drift; it authorizes only the gated private Chunk 5 recovery.
Exact staged tree `b9cf3ab0b5494e1bc85f1cd498b1108d1e7f20b0` then passed the first complete
13-file D-015 gate: locked offline resolution/sync; pytest 539/539; isolated offline wheel
build/install/import; Ruff with 125 files formatted; strict mypy over 25 package and 16
trust-boundary files; configuration hash and synthetic submission rows=2; contract/schema/current
no-drift and generated-schema checks; sensitive/MIME/symlink guards; all pre-commit and full tracked
secret checks; zero-vulnerability dependency audit; exact inventory and residue checks. Release
rule: only an identical complete rerun and final red-team PASS on the fully restaged tree containing
these governance bytes, with no later byte change, fixes `complete_final_gate=PASS`. No clean
successor freeze exists as of this record.

## Historical pre-r14 checkpoint

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
| Implemented | D-033/D-034 retain the corrected smoke protocol and split-kernel budget formula. D-035 adds the exact review failure protocol and resolves only the direct or owner-qualified derived Kaggle mount, requiring one unambiguous source while preserving every privacy/provenance gate. |
| Locally tested | Exact 13-file trees `b9cf3ab0b5494e1bc85f1cd498b1108d1e7f20b0` and `9cd6d02cc9a3e8832477471ebb8b550963df091c` passed the complete offline gate with pytest 539/539, isolated wheel import, Ruff, format, strict mypy, configuration/contract checks, secret scans, zero known dependency vulnerabilities, and clean inventory/residue. The source-focused red-team passed 190/190 and found no code P0/P1; it blocked only the stale governance wording corrected here. This reconciliation must be fully restaged and pass the identical complete gate and final red-team with no later byte change. |
| Executed privately on Kaggle | R14 inputs, performance smoke, Run A, Run B, and deterministic comparison authenticated and passed. Review-plan v1 was stably terminal `ERROR` before replay and safely validated as `phase=review`, `code=input_discovery_invalid`; r14 is terminal failed and human review remains `not_started`. |
| Remotely tested | R14 proves the complete deterministic full-run and comparison path. It does not prove review-plan materialization, visual correctness, human review, finalization, or Chunk 5 PASS. Historical failed chains may not be resumed or spliced. |
| Merge-ready | **No.** This governance reconciliation must pass one fully restaged identical complete gate and final red-team with no later byte change. That PASS fixes `complete_final_gate=PASS` and authorizes only a clean successor freeze/bundle/registry preparation and fresh immutable recovery chain—not merge, submission, or Chunk 6. |
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
  `2026-08-22T06:29:26Z` with no material drift. The latest snapshot is
  `docs/competition_contract/2026-08-22T062926Z.md`.
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
- The 2026-08-22 refresh found no material contract drift; later participant activity in Host topic
  `733965` added no new authoritative rule text. Identity-verification state is unavailable through
  the read-only official interface and therefore remains fail closed, not known incomplete.
- The standing authorization permits the gated private Chunk 5 recovery chain, but never permits
  splicing r14, weakening privacy/provenance gates, submission, public release, or Chunk 6.

## Remaining checkpoint work

1. Preserve r14 and every earlier failed chain as terminal historical evidence. Do not resume,
   rerun, mutate, delete, or splice them.
2. Fully restage the current 13-file r14 recovery candidate and rerun the identical complete D-015
   gate plus final red-team. The prior exact trees are development evidence; only PASS on the tree
   containing this reconciliation, with no later byte change, fixes `complete_final_gate=PASS`.
3. Only after that exact PASS, create a clean freeze and deterministic bundle,
   prove authenticated identity absence, prepare the append-only registry, and run one fresh
   private/offline/version-1 successor performance smoke under every D-030
   root/content/source/listing/race and fixed-output gate. Do not splice historical evidence.
4. Authenticate and validate each successor stage before its dependent stage. Stop at the human-only
   pixel QA boundary. Do not start ontology, folds, labels, model work, submission, or Chunk 6.
