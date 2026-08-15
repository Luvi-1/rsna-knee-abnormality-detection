# Chunk 5 private-run and output-retrieval recovery incidents

Status: **recovery iteration 8 terminal blocked before comparison; Chunk 5 not passed**

Date: 2026-08-14

## Summary

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
fix has focused evidence and is included with D-027 in the r9 first complete release-gate PASS.
D-015 requires the immediate identical post-governance rerun; freeze/commit, bundle, and fresh
private chain remain pending.

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

## Internal transcript control incident

During diagnosis, one broad search crossed into ignored local artifacts and printed obsolete canary
sentinel strings, local artifact paths, commit and bundle hashes, and the public competition slug
into an internal tool transcript. It did not print credentials, key bytes, authentication tokens,
pixels, DICOM headers, reports, or patient, study, or series identifiers. The search was stopped
immediately. Nothing from it was added to the repository or user-facing output, and no external
write resulted. The next fresh bundle must rotate its canary and private identities; future searches
of ignored artifacts are limited to exact bounded allowlists and fixed sanitized output.

## Impact

- Iteration 8 produced authenticated input, smoke, completed Run A, and completed Run B workflow-
  output evidence. Its protected row is terminal `blocked` before comparison. The downstream chain
  is bounded stage evidence only and cannot be spliced into the replacement immutable chain. No
  accepted comparison, determinism, QA, performance, review, or finalizer evidence exists.
- Comparison and review planning did not start; UI/session creation, human review, and finalization
  did not start.
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
P0/P1. The correction is included in the r9 first complete release-gate PASS. A new immutable
freeze/commit, bundle, and full private chain remain pending.

D-028 smoke checks pass 6/6 and the combined focused set passes 155/155. Ruff check and format pass;
mypy passes across 25 source files and nine trust-boundary files; the independent current-source
check returns `contract_drift=no`; and the post-fix red-team returns PASS with no P0/P1. The r9 exact
16-file candidate passed its first complete release gate on staged tree
`ed3720d8159b1242a6b72cab13dec43a4406f25a`: pytest 529/529; isolated wheel
build/install/import; Ruff check and format; mypy over the package plus nine trust-boundary files;
pre-commit; secret and privacy checks; dependency audit; contract schema and current
`contract_drift=no`; exact inventory; and unchanged-tree checks. This governance reconciliation
changes that staged tree, so D-015 requires the main agent to restage and immediately rerun the
identical complete gate. If that rerun succeeds, the final release record is
`complete_final_gate=PASS`; any failure invalidates this record and must be corrected. The new
freeze/commit, immutable bundle, and fresh private chain remain pending.

The checkpoint relay could not connect to Chrome at this recovery boundary. No new reviewer
response or decision exists; the user's standing Chunk 5 authorization remains controlling.

## Remaining gates

1. Preserve iteration 8 only as a terminal `blocked` historical chain. Because D-027 and D-028
   change frozen source, never launch its comparison, review-plan, UI/session, human-review, or
   finalizer stages and never splice its passed stages into iteration 9.
2. Restage this governance reconciliation and immediately rerun the identical complete gate under
   D-015. A successful rerun fixes the final release record at `complete_final_gate=PASS`; any
   failure invalidates the record and must be corrected. Then create a clean iteration-9
   implementation freeze/commit and build a new immutable private bundle; do not reuse or splice
   recovery iteration 8.
3. Create and re-authenticate the replacement private/offline/version-bound dataset chain.
4. Require authenticated smoke estimates for the full pass and post-comparison preparation, then
   run and validate full Run A before starting independent Run B.
5. Compare exact manifests, deterministic metrics, and cohort plans, and validate retrieval through
   the D-026 exact-summary/optional-safe-log boundary. Only then run the existing review-plan
   kernel's identity-bound capacity gate, replay, double render, benchmarks, and plan materialization;
   require its D-027 artifact and automatic-event contracts.
6. Complete the unchanged private human review, finalization, and disclosure-controlled validation.
7. Stop at the Chunk 5 gate; do not begin ontology, folds, labels, or model work.

Chunk 5 remains **FAIL / recovery pending** until every gate above succeeds.
