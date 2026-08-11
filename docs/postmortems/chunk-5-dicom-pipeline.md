# Chunk 5 Run A source-manifest, runtime, and selector recovery incidents

Status: **recovery open; Chunk 5 not passed**

Date: 2026-08-11

## Summary

Four private Run A attempts failed closed. The first stopped at source-manifest identity, the second
at source-schema consumption, and the third at the former processing deadline. The fourth
authenticated its inputs and completed the full-data pass, then stopped with
`material_strata_coverage_impossible` in the superseded capped joint-material selector. Run B was
not started. None of the four chains is completion evidence, and every associated freeze and bundle
is superseded.

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

## Internal transcript control incident

During diagnosis, one broad search crossed into ignored local artifacts and printed obsolete canary
sentinel strings, local artifact paths, commit and bundle hashes, and the public competition slug
into an internal tool transcript. It did not print credentials, key bytes, authentication tokens,
pixels, DICOM headers, reports, or patient, study, or series identifiers. The search was stopped
immediately. Nothing from it was added to the repository or user-facing output, and no external
write resulted. The fresh bundle must rotate its canary and private identities; future searches of
ignored artifacts are limited to exact bounded allowlists and fixed sanitized output.

## Impact

- No Run A produced an admissible completed package, determinism comparison, performance report, or
  visual-QA evidence. The fourth attempt's full pass is operational evidence only because its run
  terminated at the selector.
- Run B and comparison did not start; review planning did not complete; human review and
  finalization did not start.
- No Chunk 6 work, folds, weak labels, model training, inference, prediction, ensemble, or
  submission occurred.
- All four run failures preserved the medical-data boundary; the third consumed the old processing
  budget before failing closed. The separate transcript incident exposed only operational metadata
  categories internally and requires the controls recorded above.

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

## Remaining gates

1. Run the complete exact-set gate over D-024, create a replacement clean implementation freeze,
   and build a new immutable private bundle; do not reuse recovery iteration 5.
2. Re-authenticate the private/offline/version-bound input chain.
3. Require authenticated smoke estimates for the full pass and post-comparison preparation, then
   run and validate full Run A before starting independent Run B.
4. Compare exact manifests, deterministic metrics, and cohort plans. Only then run the existing
   review-plan kernel's identity-bound capacity gate, replay, double render, benchmarks, and plan
   materialization.
5. Complete the unchanged private human review, finalization, and disclosure-controlled validation.
6. Stop at the Chunk 5 gate; do not begin ontology, folds, labels, or model work.

Chunk 5 remains **FAIL / recovery pending** until every gate above succeeds.
