# Chunk 5 Run A source-manifest and runtime recovery incidents

Status: **recovery open; Chunk 5 not passed**

Date: 2026-08-10

## Summary

Implementation freeze `a5a44ac` and immutable bundle `7cf43...` reached private Run A and failed
closed with `source_manifest_version_mismatch`. The corrected freeze `e6e5b35` and bundle
`3a361...` passed the authenticated input gate, then Run A failed closed with
`source_manifest_input_invalid`. Freeze `60df41c` and bundle `3dc575...` passed the authenticated
input gate and both corrected source-manifest boundaries; Run A `r3` then failed closed with
`self_deadline_exceeded` at 21,664 seconds during processing. Run B was not started. None of the
three chains is completion evidence.

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

## Impact

- No Run A produced admissible completed preprocessing, determinism, performance, or visual-QA
  evidence; `r3` processing was incomplete and cannot be promoted.
- Run B, comparison, review planning, human review, and finalization did not start.
- No Chunk 6 work, folds, weak labels, model training, inference, prediction, ensemble, or
  submission occurred.
- All failures preserved the private-data boundary; the third consumed the old six-hour processing
  budget before failing closed.

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

The later performance-recovery changes have focused regression evidence only. They invalidate the
prior exact-file gate. A new complete exact-set build, typing, privacy, security, dependency,
contract, and clean-tree gate is required before another freeze. Neither the local checks nor the
throughput projection is remote completion evidence.

## Remaining gates

1. Require the complete exact-set local gate over the performance-recovery candidate bytes, then
   create a clean implementation-freeze commit and immutable private bundle.
2. Re-authenticate the private/offline/version-bound input chain.
3. Require the authenticated throughput admission control, then retry full Run A and validate it
   completely before starting Run B.
4. Complete independent Run B, deterministic comparison, benchmarks, private stratified human
   review, finalization, and disclosure-controlled validation.
5. Stop at the Chunk 5 gate; do not begin ontology, folds, labels, or model work.

Chunk 5 remains **FAIL / recovery pending** until every gate above succeeds.
