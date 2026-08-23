# Chunk 5 private-run and output-retrieval recovery incidents

Status: **r16 core provisionally approved for nonclinical research after independent exact-set
verification; frozen ordered validator remains failed; human visual QA not started**

Date: 2026-08-23

## R16 research-release disposition

R16's authenticated inputs, smoke, Run A, and Run B passed. Comparison v1 completed and its
deterministic summary passed, but the frozen workflow validator failed because its ordered
`kernel_sources` list was `[Run A, Run B]` while Kaggle returned the same exact two sources as
`[Run B, Run A]`. That failure remains immutable and is not relabelled.

One independent verifier now checks the sanitized source records as an exact duplicate-free set.
It requires exactly two unique entries, both roles, version 1 and exact code hashes, rejects every
extra/missing/duplicate source, and requires all other available comparison fields to pass. Reverse
and same-order lists pass; duplicate, missing, third-source, wrong-hash, and wrong-version fixtures
fail; repeated seeded permutations remain deterministic. Result:

```text
ordered_source_validator = FAIL
exact_duplicate_free_source_set_verifier = PASS
```

Under D-046, this is sufficient for provisional nonclinical Kaggle research use but not formal
Chunk 5 completion, submission readiness, or clinical use. R17 is cancelled because another full
A/B cycle would add no evidence for a nonsemantic API-order discrepancy. Human visual QA remains
mandatory and is being prepared as one on-demand private notebook without Run A/B/comparison
attachments or cohort-wide pre-rendering.

## Current r14 review-plan incident

R14 proved the complete core path: authenticated inputs and smoke passed, Run A completed in
7h21m20s, Run B in 6h36m06s, both full-run validators passed, and deterministic comparison passed.
Review-plan v1 then returned stable terminal `ERROR` before cohort replay. Its no-match session log
contained only the bounded producer events. The frozen failure consumer rejected those events
because it supported only core-run and smoke protocols; the minimal shared correction now validates
the exact review protocol and releases only `phase=review`, `code=input_discovery_invalid`.

The remaining producer defect is mount resolution. The frozen helper assumed only
`/kaggle/input/<slug>`, while Kaggle may use collision-safe `/kaggle/input/<owner>/<slug>`. The
recovery accepts exactly those two derived roots, requires exactly one, and retains all bounded
depth, entry-count, symlink, file-type, duplicate, and counterfeit-source gates. Focused and both
complete DICOM-QA suites pass with Ruff, format, mypy, and diff checks. R14 was terminalized failed;
human review remains not started, and no retry, v2, UI, finalizer, submission, or Chunk 6 action
occurred.
The official `2026-08-22T062926Z` snapshot records no material contract drift.
Exact staged tree `b9cf3ab0b5494e1bc85f1cd498b1108d1e7f20b0` passed the first complete 13-file
release gate with pytest 539/539 and all offline, static, configuration, contract, privacy,
dependency, and inventory checks. Release rule: only an identical complete rerun and final red-team
PASS on the fully restaged tree containing these governance bytes, with no later byte change, fixes
`complete_final_gate=PASS` and permits a new freeze or successor.

## Current r13 terminal checkpoint

Legacy Kaggle authentication was restored without exposing credential material. One bounded
authenticated check proved the exact r13 performance-smoke version 1 terminal `ERROR`. The corrected
strict validator returns `phase=performance_smoke`,
`code=throughput_projection_exceeds_budget`; exactly one smoke progress event localizes the failure
to the inner throughput gate. The append-only registry is terminal `failed`: input authentication
passed, and Run A, Run B, comparison, review-plan, and human review are `not_started`. No rerun,
splice, Run A, output publication, or downstream launch occurred. The then-latest contract snapshot was
`docs/competition_contract/2026-08-21T200304Z.md`; it records no material drift. Identity-verification
state is unavailable and fail closed. Exact 15-file tree
`afd8909a798d30fa9314fe6568768bca68fbda14` passed its complete D-015 gate with pytest 538/538 and
all recorded checks but is historical and superseded. After the governance bytes were restaged,
exact tree `e298964891b214bfbf4dc06725f2cde3b3bd3f74` failed the mandatory pytest rerun with one
failure and 537 passes because a manifest-runner test compared nondeterministic real wall-clock
`runtime.elapsed_seconds` (3 seconds versus 2). Production uses `ceil(monotonic - start)`, and its
validators intentionally accept an integer from zero through the configured maximum; production,
disclosure, and schema behavior remain correct. The minimal test-only correction reuses
`_validate_exact_aggregates` on the rerun, excludes only `runtime` from cross-run aggregate equality,
and retains exact table-hash, study-key, QA-byte, and audit-key equality. Focused 3/3 passed
repeatedly, the complete manifest-runner file passed 12/12, and Ruff check/format plus the scoped diff
check pass. The then-current r13 candidate was exactly 16 files: seven source/tests, eight governance files,
and the latest snapshot. Exact staged tree `22c80aaa8f30d47a21e1a43fc3e945ab831c79ea` passed its
first complete D-015 gate: locked offline `uv` lock/sync; full pytest 538/538 in 63.84 seconds;
isolated wheel build, offline install, and import of `rsna-knee 0.1.0`; Ruff PASS; 124 files formatted;
mypy over 25 package plus 16 trust-boundary files; valid configuration with the
established hash and synthetic submission `rows=2`; canonical contract schema valid, current
`contract_drift=no`, and generated schema bytes current; sensitive guard PASS; tracked MIME exact at
154 regular files plus the one exact `.agents/skills` symlink; `pip-audit` with no known
vulnerabilities; all pre-commit hooks PASS; full tracked detect-secrets PASS; and exact 16-file
inventory, no unstaged or untracked residue, and unchanged-tree PASS. This eight-file governance
reconciliation changes bytes, so one immediate fully restaged identical complete rerun and final
red-team remain required. Only PASS with no later byte change fixes `complete_final_gate=PASS`; any
failure invalidates the first-pass final-gate evidence and requires this record to be corrected.
Freeze, bundle, authenticated identity-absence proof, append-only registry preparation, and
successor smoke remain pending. Even after those prerequisites pass, authorization stops at one
fresh successor smoke; Run A requires authenticated smoke terminal/output validation and a fresh
decision.

## Summary

R13 exposed two independent local defects. First, the generic failure-log consumer did not recognize
the smoke producer's distinct closed event and phase protocol and masked a valid terminal failure as
`failure_log_completion_invalid`. Second, the now-visible failure occurred at an inner throughput
formula retained from the former monolithic smoke-plus-full-run kernel: after smoke moved to its own
3,600-second kernel, both admission sites still added sample elapsed time even though later Run A and
Run B receive the full 27,000-second budget and do not repeat that work. D-033 binds validation to the
producer state machine; D-034 removes only the stale leading term while preserving the projection,
reserve, deadlines, authentication, privacy, and fail-closed gates. Targeted tests and scoped static
checks pass. The 15-file gate PASS and failed restaged tree are historical. The first exact 16-file
gate passed, but the fully restaged identical complete rerun and final red-team remain pending.

Historical chronology follows.

Five historical private Run A attempts failed closed: source-manifest identity, source-schema
consumption, the former processing deadline, the superseded capped joint-material selector, and
private cohort-plan validation. Recovery iteration 7 then failed at comparison-output validation.
D-026 passed its complete gate with pytest 528/528, and recovery iteration 8 uses freeze `4958c4a`
and immutable bundle `09502a...`. Its private inputs, standalone smoke, and full-data Run A
authenticated and passed. Run B version 1 reached `COMPLETE` at 25,940 seconds; two independent
bounded read-only polls 71 seconds apart agreed, and the established authenticated validator
returned `dicom_qa_output_validation=PASS mode=workflow stage=run-b`. The protected registry row is
terminal `blocked`: input, smoke, Run A, and Run B are `passed`; comparison, `review_plan`, and
`human_review` are `not_started`; `completed_utc` is set; and integrity, foreign keys, and mode are
`PASS`.

Before comparison launch, frozen-source preflight found two independent P1 review-plan
producer/consumer contract defects. Comparison, review-plan materialization, UI/session creation,
human review, and finalization were not launched. Iteration 8 therefore remains evidence only for its
exact attained stages. Its Run B validator PASS is not Chunk 5 PASS or comparison, determinism, QA,
review, performance, or finalizer evidence. Because D-027 and D-028 change frozen source,
iteration-8 comparison and QA must never launch, and the chain cannot be spliced into iteration 9.

A later release-gate audit found the independent D-028 material-drift checker P1. Its minimal root
fix passed with D-027 in r9 freeze `1db805e` after the exact 529/529 gate.

Bundle `28457d...` passed all non-content checks but was rejected before upload: pinned upstream
`pydicom 3.0.2` contains aggregate 104 `.dcm` members and 188 standard DICM-preamble members. No r9
remote artifact exists. The protected r9 registry row is terminal `blocked`, every remote stage is
`not_started`, and the reason is `dependency_wheel_medical_payload_detected`.

R10 subsequently authenticated input, performance smoke, Run A, Run B, comparison, and the exact
review-plan source graph. Review-plan version 1 reached `ERROR`; two bounded read-only checks 93
seconds apart agreed, and the frozen privacy/canary failure validator passed with only
`input_discovery_invalid`. No review artifact, pixel, UI/session, human review, or finalizer stage was
accessed or created. The protected r10 registry row is terminal `failed`.

Mode-0600 ignored Run A failure logs were retrieved only under exact allowlists for diagnosis and
remain inside the protected project boundary. Only fixed sanitized runner events were exposed
outside that protected metadata boundary. No DICOM, pixel, report, patient identifier, review row,
or private medical artifact was exported or added to this record.

## First root cause

Chunk 4 has two legitimate identities with different purposes:

- the governance audit ID identifies the promoted, completed audit contract and registry row;
- the producer execution ID identifies the immutable manifest-producing run.

The private database stores the producer execution ID under the key `audit_id`. The Chunk 5
consumer compared that value with the governance audit constant. Both values were valid within
their own namespaces, but the comparison conflated them and deterministically triggered the
fail-closed error.

This was an identity-contract defect in the consumer, not evidence of manifest-version drift,
corrupt DICOM content, or a failed Chunk 4 audit.

## Second root cause

The authenticated Chunk 4 schema stores issue ownership in the shared `manifest_issue.entity_key`
column. The Chunk 5 consumer's study-level UNION arm queried a nonexistent `study_key` column,
which SQLite rejected and the privacy boundary correctly reduced to `source_manifest_input_invalid`.
The same compatibility audit found that `protected_component` intentionally includes singleton
rows; the unfiltered consumer query therefore mislabeled essentially every study as belonging to a
protected duplicate group.

This was a producer-consumer schema and semantics defect, not a damaged private artifact or DICOM
failure. Reproduction against the real producer schema succeeded after changing the issue field to
`entity_key` and positively allowing only `evidence_state='hard'` for protected duplicates.

## Third root cause

Run A `r3` exhausted the configured 21,600-second self-deadline before completing its full private
workflow. The authenticated fixed failure category establishes budget exhaustion during processing;
it does not establish which private series or case was in flight, and no such detail was retrieved.

Source review found avoidable repeated work in the production path. Every ephemeral NPY cache file
was forced to durable storage and then reread solely to calculate a checksum, even though the cache
is disposable and the canonical bytes can be hashed during their single write. Invariant installed-
package versions were also resolved once per processed series. The old safe log recorded only start
and terminal failure, so it could not distinguish full-pass quarters, cohort replay, or benchmarks.
These costs and the missing early throughput admission control were real implementation gaps, but
the failed run did not prove that removing them alone will make the next full run fit.

## Fourth root cause

The fourth Run A attempt completed its full-data pass, so the earlier processing bottleneck was not
the terminal cause. Its post-pass selector required coverage through a legacy joint-material
contract while also enforcing an arbitrary maximum study count. Those requirements could conflict,
and the runner correctly failed closed with `material_strata_coverage_impossible` instead of
silently dropping coverage. The failure produced no admissible Run A package.

The legacy joint-material census was also the wrong public abstraction: composite private values
can be high cardinality and do not form a bounded, interpretable semantic registry. In particular,
site-domain membership must be bucketed before it participates in required coverage. The failure
does not establish that a cohort satisfying bounded semantic quotas is impossible.

## Fifth root cause

Recovery iteration 6 authenticated the replacement input chain and passed the standalone smoke,
then Run A failed closed while producing its private cohort plan. The exact-reference failure log
was retrieved separately under the bounded allowlist and passed privacy classification; its fixed
classification was `phase=processing`, `code=private_cohort_plan_invalid`.

Source tracing found that the selected-study plan serializer copied every dimension carried by the
internal cohort record. That record intentionally retained legacy and diagnostic dimensions for
local computation, but the downstream plan contract permits exactly the frozen 25-dimension review
registry. The extra dimensions therefore crossed an internal schema boundary and the validator
correctly rejected the plan.

The same trace found a latent binding defect before the retry: small, median, and large
representative series were chosen from the global eligible population. They must be chosen only
from studies in the selected cohort so the later capacity certificate, benchmarks, and review plan
refer to one coherent cohort. This second defect was not used to reinterpret the remote failure; it
was corrected because the same source path made it directly observable.

## Sixth root cause

Recovery iteration 7 authenticated and passed its input chain, standalone smoke, full-data Run A,
and independent full-data Run B. The comparison kernel then reached `COMPLETE`; the comparator
producer and its deterministic comparison semantics were correct. The failure occurred after remote
execution, at the local output-retrieval boundary.

Kaggle CLI 2.2.4 unconditionally materialized one root wrapper log beside the requested comparison
summary. The validator required one total file, so it correctly failed closed with
`comparison_output_layout_invalid` rather than inspecting an unallowlisted layout. This was a
consumer retrieval-layout defect, not a deterministic mismatch, producer defect, DICOM failure, or
private-input authentication failure.

## Seventh root cause

Recovery iteration 8 passed its local gate, input authentication, standalone smoke, and full-data
Run A. During Run B execution, frozen-source preflight traced the downstream review-plan path and
found two independent consumer-contract defects before comparison launch.

The renderer/finalizer contract requires six artifacts for every review group and permits
`orthogonal.png` only when physical geometry supports that view. The remote-listing validator instead
required exactly seven artifacts, so a valid producer result without an orthogonal view would fail.
Separately, automatic materialization emits `dicom_qa_review_started`, the four frozen
`dicom_qa_plan_progress` events, and `dicom_qa_review_template_complete`; the local validator expected
generic full-run start and completion events. A valid automatic plan therefore could not pass its
consumer.

These were frozen producer/consumer contract defects, not evidence of a DICOM, determinism,
private-input, renderer, or privacy failure. Comparison and every review stage were blocked before
launch rather than spending additional compute on a chain that could not validate.

## Eighth root cause

The material-drift checker treated the core competition sections as material but omitted
`efficiency_prize`, `external_assets`, `team_and_sharing`, `license`, `winner_obligations`, and
`ambiguities`. A mutation or wholesale removal of any omitted section could therefore produce
`contract_drift=no`, despite changing legal, privacy, sharing, asset, eligibility, or delivery
obligations.

This was an incomplete fail-closed allowlist, not live contract drift. The independent current-source
check still returns `contract_drift=no`; the defect was that the checker could not prove that result
against all operational sections.

## Ninth root cause

The shared `package_manifest_bundle` path copied complete pinned dependency wheels into both the
manifest and DICOM-QA offline bundles. The r9 source candidate and every non-content bundle check
passed, but final content inspection found medical test payloads inside the upstream
`pydicom 3.0.2` wheel: aggregate 104 `.dcm` members and 188 members with the standard `DICM`
preamble. The bundle was rejected before upload.

This is a shared dependency-packaging trust-boundary defect, not private competition-data exposure
or remote execution. No r9 remote artifact exists. Because the same helper built the
`audit-0002-manifest-remediation` bundle, its scientific result remains historical evidence but its
bundle is superseded as a reusable source root.

## Tenth root cause

The first r10 candidate passed 530/530 on exact staged tree
`5bea3c110e100e9ddd2d94c8b89c29e1f0ff82a0`, but deployment preflight found that the
project wheel did not enter the shared medical-payload archive guard; remote stages could skip
wheel/`RECORD` validation; and the actual two-file local kernel upload was not exact-allowlisted and
hashed. Exact private dataset/kernel version-1 content, sources, listings, and race stability were
also incompletely authenticated. Raw status/private-reference-capable commands and an unscoped
credential path violated the fixed-output boundary.

A final root-trust check found that the initial authenticator could read dataset metadata and scan
wheels from a safe sibling directory distinct from the verified bundle-manifest root. This was a
local path-binding and remote-provenance authentication defect, not a remote mutation or private
medical-data exposure. That preflight finding was corrected before the later r10 remote chain. The
530/530 gate remains superseded.

## Eleventh root cause

The r10 review-plan kernel's source graph was exact, but `finalize_review.py` used one generic
basename walk across all of `/kaggle/input` before selecting a dataset or kernel source. The walk
entered the legitimate official `train_series` tree, whose study-directory population exceeds the
generic 4,096-entry discovery limit, and failed closed with `input_discovery_invalid` before any
private replay, rendering, or artifact creation.

This was a source-discovery scope defect, not missing input, source-graph drift, DICOM corruption, or
privacy leakage. D-031 limits base search to depth 1 and starts kernel-output search at the exact
derived mount while retaining the existing symlink, duplicate, count, file-type, and error gates.

## Twelfth root cause

The performance-smoke producer and the generic failure-log consumer implemented different closed
state machines. The producer emits smoke-specific start, progress, and failure events over `bundle`,
`authentication`, `performance_smoke`, and `output`; the consumer accepted only the generic full-run
events and phases. A caught and otherwise well-formed smoke failure therefore always collapsed to
`failure_log_completion_invalid`, hiding its safe phase and code.

D-033 keeps one validator entry point and selects the protocol only from the first exact start event.
It then requires that protocol's exact terminal event, phase allowlist, ordered progress prefix, and
phase-specific legal prefix length. Hybrid, reordered, extra, and wrong-phase logs remain rejected.
The exact authenticated r13 log now validates as `phase=performance_smoke`,
`code=throughput_projection_exceeds_budget`.

## Thirteenth root cause

The corrected log contains exactly one smoke progress event, which places r13's failure at the inner
throughput gate. Git history shows why: freeze `a36b053` ran the smoke sample and full pass inside the
same 27,000-second kernel, so `elapsed + projected_full_pass + reserve` correctly charged work already
spent from that shared budget. Freeze `01ea270` moved smoke to a standalone 3,600-second kernel and
removed it from Run A and Run B, but the old leading sample-time term remained in both admission
sites. The current run contract confirms that later full runs receive the full 27,000 seconds and do
not repeat the smoke sample.

D-034 removes only the stale leading `elapsed +` at both sites. It retains standalone pre-smoke setup
accounting, the conservative full-pass projection, the 3,600-second post-pass reserve, finite-value
checks, self and outer deadlines, source authentication, privacy controls, and the same fail-closed
error. This is a split-kernel accounting defect, not proof that a successor will fit; fresh smoke must
measure and may still reject it.

## Internal transcript control incident

During diagnosis, one broad search crossed into ignored local artifacts and printed obsolete canary
sentinel strings, local artifact paths, commit and bundle hashes, and the public competition slug
into an internal tool transcript. It did not print credentials, key bytes, authentication tokens,
pixels, DICOM headers, reports, or patient, study, or series identifiers. The search was stopped
immediately. Nothing from it was added to the repository or user-facing output, and no external
write resulted. The next fresh bundle must rotate its canary and private identities; future searches
of ignored artifacts are limited to exact bounded allowlists and fixed sanitized output.

## Impact

- R13 authenticated its exact input and then failed performance smoke before Run A. Its protected
  row is terminal `failed`; Run A, Run B, comparison, review-plan, and human review are
  `not_started`. No retry, stage splice, pixel access, QA artifact, UI/session, finalizer, submission,
  or public action occurred. The result is terminal smoke-failure evidence only.
- Iteration 8 produced authenticated input, smoke, completed Run A, and completed Run B workflow-
  output evidence. Its protected row is terminal `blocked` before comparison. The downstream chain
  is bounded stage evidence only and cannot be spliced into the replacement immutable chain. No
  accepted comparison, determinism, QA, performance, review, or finalizer evidence exists.
- Comparison and review planning did not start; UI/session creation, human review, and finalization
  did not start.
- R9 produced only local freeze `1db805e` and rejected bundle `28457d...`. Its registry row is
  terminal `blocked`, every remote stage is `not_started`, and no r9 remote artifact exists.
- Audit-0002 remains historical scientific evidence but cannot be reused as a source root. The new
  audit-0003 experiment and a full fresh DICOM-QA chain are required.
- R10 authenticated inputs, smoke, Run A, Run B, and comparison. Its review-plan version 1 failed
  safely before artifacts; the terminal failed chain is historical evidence only and supplies no QA,
  human-review, performance-finalizer, or Chunk 5 claim.
- No Chunk 6 work, folds, weak labels, model training, inference, prediction, ensemble, or
  submission occurred.
- All five historical Run A failures and the r7 comparison-workflow failure preserved the medical-
  data boundary; the third consumed the old processing budget before failing closed. The separate
  transcript incident exposed only operational metadata categories internally and requires the
  controls recorded above.

## Correction

The first two-file root-cause correction keeps the governance identity unchanged at the outer source
gate and authenticates the database producer identity separately from values already bound by the
immutable chain. The consumer now requires:

1. an exact lowercase code-commit representation;
2. equality with the full bound source-bundle hash;
3. the producer execution-ID derivation from that commit;
4. one common validated owner; and
5. exact content-derived source kernel and dataset references.

The authenticated producer tuple is included in the private source snapshot digest. The public and
source identity schemas do not expand, and no private identity is released.

The second correction queries the producer's shared `entity_key` field for study issues and admits
only `hard` protected components to the duplicate stratum. Freeze `60df41c` authenticated and passed
both source-manifest boundaries before the independent runtime failure.

The performance recovery writes each canonical NPY cache once while streaming its SHA-256, omits
durability work for the disposable cache, and caches invariant package-version provenance once per
process. It emits only a fixed safe phase/quarter sequence. Before the full pass, it processes at
most 120 studies from the existing authenticated priority-1 stratified source-manifest sample
through the same production series/cache/reconciliation path, then fails closed unless the sample
elapsed time plus the larger series- or file-scaled projection plus a 3,600-second post-pass reserve
fits. The new 27,000-second self-deadline leaves 1,800 seconds before the 28,800-second outer kill,
which remains 3,600 seconds below the verified 32,400-second competition ceiling.

That monolithic execution contract is superseded by D-023. Run A and Run B now each perform one
complete full-data pass and emit only a canonical manifest, deterministic metrics, and a
deterministic cohort plan. The comparator requires exact manifest and cohort-plan bytes plus exact
deterministic metrics. Only after exact comparison does the existing review-plan kernel authenticate
a capacity certificate bound to the freeze, bundle, manifest, both runs, cohort plan, and renderer,
then replay every selected series, render it twice, run the representative decode/preprocessing/
resource benchmarks once, and materialize the private plan. The pre-run smoke measures full-pass
and post-comparison preparation capacity separately. No new kernel or private data reference is
introduced; the UI and human-review contract are unchanged.

Selector v3 removes the arbitrary study maximum and uses exact deterministic incremental greedy
selection until every required represented value satisfies its quota across bounded semantic
registries. Site-domain values are limited to `missing`, `singleton`, `rare_2_4`,
`represented_5_19`, and `represented_20_plus`. Physical file, byte, time, and disk gates remain
fail closed. The only public registry-coverage claim is
`all_required_represented_registry_values_satisfy_quotas`; the legacy joint-material census and
coverage claim are removed.

D-026 admits only the exact comparison summary and at most one bounded, privacy-scanned root wrapper
log. Its complete iteration-8 gate passed without changing comparison semantics or accepting any
other output layout.

D-027 changes only `scripts/validate_dicom_qa_output.py` and
`tests/test_dicom_qa_packaging.py`. The validator binds to the finalizer's exact
`REQUIRED_SUFFIXES`/`ALLOWED_SUFFIXES`, requires all six mandatory artifacts, permits only the
optional orthogonal view, and retains every duplicate, extra-entry, wrong-path, symlink, special-
file, size, canary, and sensitive-content rejection. The automatic review-plan log must contain the
actual review start, four declared progress events, and template-completion event. The producer,
renderer, cohort, review, and privacy contracts are unchanged.

D-028 adds the six omitted section names to the existing `MATERIAL_SECTIONS` and extends the existing
`tests/test_smoke.py` coverage to mutate and wholly remove every material section. It adds no
dependency, helper layer, configuration surface, or abstraction.

D-033 changes only the existing failure-log validator and its packaging regression. It binds the
generic and performance-smoke producers to distinct exact start/progress/terminal events, phases,
ordered prefixes, and legal prefix lengths, without changing the CLI or weakening the existing
canonical, size, canary, sensitive-content, or failure-code gates.

D-034 removes the stale sample-time addition from the two existing throughput admission formulas and
updates only their existing boundary tests. It does not add a new budget, option, helper, dependency,
or abstraction. Standalone setup accounting, projected full-pass time, the 3,600-second reserve,
self/outer deadlines, authentication, privacy, and every existing failure gate remain intact.

## Verification to date

- 32 focused positive and adversarial tests passed.
- Ruff passed for the two changed files.
- Strict mypy passed for the two changed files.
- The exact 12-file staged replacement candidate passed the complete 404-test release gate,
  including isolated build, typing, privacy, security, dependency, contract, and clean-tree checks.

These are local recovery and release-candidate checks, not the Chunk 5 exit gate.

For the second incident, one real-schema regression proves both study-issue attribution and
singleton exclusion. All 33 focused full-run tests plus scoped Ruff and strict mypy pass. The exact
seven-file candidate also passed the complete 405-test release gate, including isolated build,
typing, privacy, security, dependency, contract, and clean-tree checks, producing freeze `60df41c`
and bundle `3dc575...`.

The exact 29-file staged D-023 two-stage candidate passed the complete final local gate: staged
inventory and clean-tree checks, locked offline reinstall/check, isolated Python 3.11 wheel
build/install/import, MIME checks, Ruff, strict mypy over 25 package and nine trust-boundary files,
pytest 507/507, CLI/config/submission/contract checks, all pre-commit hooks, full candidate secret and
sensitive-file checks, dependency audit with no known vulnerabilities, fresh contract drift, and
diff checks. Independent end-to-end and source-graph red-teams found no remaining P0/P1. No local
gate or smoke projection is remote completion evidence.

Recovery iteration 5 produced freeze `01ea270` and immutable bundle `4127dcc...`. The new private
version-1 input chain authenticated, and its standalone smoke reached `COMPLETE` in 35 minutes 5
seconds. Workflow validation then failed closed with `performance_smoke_output_layout_invalid`
before Run A. A bounded probe showed that official Kaggle CLI 2.2.4 always materializes one root
execution log beside the matched safe summary; the authenticated listing already allowed it, while
the local retrieval layout incorrectly required one file total. D-024 now permits at most that one
safe-pattern root log, reads at most 2 MiB, scans it with the bound canary and sensitive-data policy,
and rejects every other layout. Eleven focused tests, Ruff, formatting, strict mypy, and the
completed-smoke probe pass. The correction still requires a complete gate and new immutable chain.

Recovery iteration 6 completed that gate, producing freeze
`1c4470e8a9557141682a81737981271635db7fdc` and immutable bundle
`9e6be825c219f458c79fa1599feb82ace33d97dade441858fa53656820e6fda4`. Its replacement private
version-1 inputs authenticated and the standalone smoke passed. Run A version 1 then ended in
terminal `ERROR`; the separately classified bounded failure log returned
`phase=processing`, `code=private_cohort_plan_invalid`.

The smallest correction changes only the shared runner and its full-run regression file. It filters
serialized selected-study dimensions through the existing exact review registry, selects the
cohort before representative profiles, and restricts those profiles to selected study identifiers.
All 46 tests in `tests/test_dicom_qa_full_run.py`, Ruff check and format, strict mypy on the two
files, and the diff check passed. D-025 subsequently passed the complete exact-set gate, producing
iteration-7 freeze `e3c6334` and bundle `5fe504...`.

Iteration 7 private inputs, standalone smoke, Run A, and Run B authenticated and passed. The
comparison kernel completed with a correct producer, but the append-only workflow row is terminal
failed at `comparison_output_layout_invalid`. D-026 then passed its complete exact-set gate with
pytest 528/528 and produced iteration-8 freeze `4958c4a` and bundle `09502a...`.

Iteration 8 private inputs, standalone smoke, and full-data Run A authenticated and passed. Run B
version 1 reached `COMPLETE` at 25,940 seconds; two independent bounded read-only polls 71 seconds
apart agreed, and the established authenticated validator returned
`dicom_qa_output_validation=PASS mode=workflow stage=run-b`. The protected registry row is terminal
`blocked`: input, smoke, Run A, and Run B are `passed`; comparison, `review_plan`, and
`human_review` are `not_started`; `completed_utc` is set; and integrity, foreign keys, and mode are
`PASS`. UI/session creation and finalization were not launched. This is not Chunk 5 PASS or
comparison, determinism, QA, review, performance, or finalizer evidence.

The D-027 two-file correction passes focused checks 9/9 and the complete packaging file 147/147.
Ruff check and format pass, strict mypy passes for the validator, the pre-governance implementation
diff was exactly the two declared source/test files, and an independent red-team returns PASS with no
P0/P1. The correction passed in r9 freeze `1db805e`; the later dependency-wheel rejection is
separate.

D-028 smoke checks pass 6/6 and the combined focused set passes 155/155. Ruff check and format pass;
mypy passes across 25 source files and nine trust-boundary files; the independent current-source
check returns `contract_drift=no`; and the post-fix red-team returns PASS with no P0/P1. The
correction passed in r9 freeze `1db805e`; the later dependency-wheel rejection is separate.

D-029 implements one shared stdlib sanitizer in `scripts/package_manifest_bundle.py` and its
existing packaging regression. It removes the general test tree plus
any `.dcm`, `.dicom`, or standard DICM-at-byte-128 member, regenerates wheel `RECORD`
deterministically, validates every other wheel fail-closed, and preserves runtime modules,
metadata, licenses, and offline preflight. Existing DICOM-QA source-audit constants and fixtures are
rebound to audit-0003. The first r10 candidate passed on exact staged tree
`5bea3c110e100e9ddd2d94c8b89c29e1f0ff82a0`: pytest 530/530; isolated wheel
build/install/import; Ruff check/format; mypy over 25 source and nine trust-boundary files;
audit/configuration/submission; contract schema and current `contract_drift=no`; pre-commit;
privacy checks; `pip-audit`; exact inventory and unchanged-tree checks. D-030 preflight
superseded that gate.

D-030 extends the shared guard to the project wheel and adds one deployment authenticator that
directly reuses the existing DICOM-QA version-1 helpers. Before any network operation, every stage
validates the exact two-file local kernel/hash and all wheels/`RECORD`; dataset metadata must resolve
under the exact bundle-manifest parent, and kernel metadata under its exact sibling kernel
directory. Remote gates authenticate exact private dataset version-1 content/hashes, exact kernel
version-1 code/source graph, stable listings, and before/after race snapshots. Status is limited to
`PENDING`, `RUNNING`, `COMPLETE`, or `ERROR`; the runbook uses a command-scoped token, protected
logs, explicit `/1`, and bracketed gates. No dependency, framework, or new abstraction was added.
The mismatched-root regression proves zero remote calls, and independent authentication and
runbook red-teams pass with no P0/P1. The historical first complete exact 24-file D-015 gate passed
on tree
`cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260` with pytest 537/537 and every recorded
lock/build/import, static, configuration, contract, privacy, dependency, inventory, and
unchanged-tree check. That result is superseded. The later 15-file PASS and failed restaged tree are
also historical and superseded. The first exact 16-file gate passed, but these governance bytes
require the fully restaged identical complete rerun and final red-team;
`complete_final_gate=PASS` remains unset.

D-031 changes only `kaggle/dicom_qa/finalize_review.py` and its existing focused identity regression.
Base discovery stops at depth 1; kernel discovery starts beneath the exact derived kernel mount; and
the symlink, duplicate, count, file-type, and error gates remain unchanged. The focused identity
suite passes 41/41; boundary matrix 12/12; combined identity plus packaging 188/188; full development
pytest 537/537; Ruff check and format, strict finalizer mypy, and the scoped diff check pass. The
independent exact two-file red-team passes with no P0/P1. The historical first exact staged D-015
gate passed on tree `959f14e9422db9670d16683ba8effe681cf6641d` over exactly 10 files: locked offline reinstall/lock;
isolated wheel build/install/import; tracked MIME/symlink and sensitive guards; Ruff/format; mypy over
25 package plus 11 trust-boundary files; pytest 537/537; config/synthetic-submission; protected
current contract/schema and generated-schema byte checks; pre-commit/detect-secrets; `pip-audit` with
no vulnerabilities; cached diff, exact inventory, and unchanged-tree PASS. That 10-file result is
superseded. The later 15-file PASS and failed restaged tree are also historical and superseded. The
first exact 16-file gate passed, but these governance bytes require the fully restaged identical
complete rerun and final red-team; `complete_final_gate=PASS` remains unset.

D-033 strict validation accepts the exact r13 smoke protocol and returns only
`phase=performance_smoke`, `code=throughput_projection_exceeds_budget`; generic, hybrid, reordered,
extra, wrong-phase, and illegal-prefix cases remain rejected. The exact one-progress-event prefix
places the failure at the inner throughput gate.

D-034 targeted boundary tests pass at 3,801/3,799 seconds and the standalone projected ceiling is
4,320 seconds. Scoped static checks pass. The 15-file PASS is historical, and the failed restaged
tree exposed the separate test-only runtime-equality defect. That r13 recovery is historical and
superseded by the r14 terminal checkpoint above.

Historical r13 note: the checkpoint relay could not connect to Chrome, and the then-current
smoke-only checkpoint did not authorize Run A. The r14 authorization and outcome above supersede
that operational boundary.

## Remaining gates

1. Preserve r14 and every earlier failed chain as terminal historical evidence. Do not resume,
   rerun, mutate, delete, or splice them.
2. Fully restage the current 13-file r14 recovery candidate and rerun the identical complete D-015
   gate plus final red-team. Only PASS on the tree containing this reconciliation, with no later
   byte change, fixes `complete_final_gate=PASS`.
3. Only after that exact PASS, create the clean freeze and deterministic bundle,
   prove authenticated identity absence, prepare the append-only registry, and run one fresh
   private/offline/version-bound successor smoke through every D-030 fixed-output
   root/content/source/listing/race gate. Fresh smoke may still fail closed.
4. Authenticate and validate each successor stage before its dependent stage. Stop at the
   human-only pixel QA boundary. Do not start ontology, folds, labels, model work, Chunk 6, or
   submission.

Chunk 5 remains **FAIL / recovery pending** until every gate above succeeds.
