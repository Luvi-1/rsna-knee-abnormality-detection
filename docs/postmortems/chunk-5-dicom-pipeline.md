# Chunk 5 private-run and output-retrieval recovery incidents

Status: **recovery open; Chunk 5 not passed**

Date: 2026-08-13

## Summary

Five historical private Run A attempts failed closed: source-manifest identity, source-schema
consumption, the former processing deadline, the superseded capped joint-material selector, and
private cohort-plan validation. D-025 then passed its complete gate and recovery iteration 7 used
freeze `e3c6334` and immutable bundle `5fe504...`. Its private inputs, standalone smoke, full-data
Run A, and independent full-data Run B all authenticated and passed. The comparison kernel reached
`COMPLETE` and its comparator producer was correct, but local workflow validation failed closed
with `comparison_output_layout_invalid`: Kaggle CLI 2.2.4 unconditionally retrieved one root
wrapper log while the validator required one total file. The append-only r7 row is terminal failed.
Review-plan materialization, UI/session creation, human review, and finalization were not started.

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

## Internal transcript control incident

During diagnosis, one broad search crossed into ignored local artifacts and printed obsolete canary
sentinel strings, local artifact paths, commit and bundle hashes, and the public competition slug
into an internal tool transcript. It did not print credentials, key bytes, authentication tokens,
pixels, DICOM headers, reports, or patient, study, or series identifiers. The search was stopped
immediately. Nothing from it was added to the repository or user-facing output, and no external
write resulted. The fresh bundle must rotate its canary and private identities; future searches of
ignored artifacts are limited to exact bounded allowlists and fixed sanitized output.

## Impact

- Iteration 7 produced authenticated completed Run A and Run B packages and a completed comparator
  producer. Its terminal-failed workflow is historical evidence only and cannot be spliced into the
  replacement immutable chain. No accepted comparison workflow, performance report, or visual-QA
  evidence exists.
- Review planning did not start; UI/session creation, human review, and finalization did not start.
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
failed at `comparison_output_layout_invalid`.

The smallest D-026 correction changes only the comparison-output validator and its regression file.
It requires the exact comparison-summary path and permits at most one root wrapper log under the
existing bounded-size and privacy-scan policy. Every extra entry, wrong path, symlink, special file,
oversized log, canary hit, or sensitive payload remains a hard failure. The comparator producer and
comparison semantics are unchanged. Focused checks, the complete exact-set gate, a new immutable
freeze/bundle, and the full private chain remain pending.

The checkpoint relay could not connect to Chrome at this recovery boundary. No new reviewer
response or decision exists; the user's standing Chunk 5 authorization remains controlling.

## Remaining gates

1. Run focused positive/adversarial checks and the complete exact-set gate over D-026, create a
   replacement clean implementation freeze, and build a new immutable private bundle; do not reuse
   or splice recovery iteration 7.
2. Create and re-authenticate the replacement private/offline/version-bound dataset chain.
3. Require authenticated smoke estimates for the full pass and post-comparison preparation, then
   run and validate full Run A before starting independent Run B.
4. Compare exact manifests, deterministic metrics, and cohort plans, and validate retrieval through
   the D-026 exact-summary/optional-safe-log boundary. Only then run the existing review-plan
   kernel's identity-bound capacity gate, replay, double render, benchmarks, and plan materialization.
5. Complete the unchanged private human review, finalization, and disclosure-controlled validation.
6. Stop at the Chunk 5 gate; do not begin ontology, folds, labels, or model work.

Chunk 5 remains **FAIL / recovery pending** until every gate above succeeds.
