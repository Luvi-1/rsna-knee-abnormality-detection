# Chunk 5 Run A source-manifest recovery incidents

Status: **recovery open; Chunk 5 not passed**

Date: 2026-08-10

## Summary

Implementation freeze `a5a44ac` and immutable bundle `7cf43...` reached private Run A and failed
closed with `source_manifest_version_mismatch`. The corrected freeze `e6e5b35` and bundle
`3a361...` passed the authenticated input gate, then Run A failed closed with
`source_manifest_input_invalid`. Both attempts stopped before DICOM preprocessing, QA generation,
or benchmarking. Run B was not started, and neither chain is completion evidence.

One mode-0600 ignored Run A failure log was retrieved locally for diagnosis and remains inside the
protected project boundary. Only fixed sanitized runner events were exposed outside that protected
metadata boundary. No DICOM, pixel, report, patient identifier, review row, or private medical
artifact was exported or added to this record.

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

## Impact

- Run A produced no admissible preprocessing, determinism, performance, or visual-QA evidence.
- Run B, comparison, review planning, human review, and finalization did not start.
- No Chunk 6 work, folds, weak labels, model training, inference, prediction, ensemble, or
  submission occurred.
- The failure happened before the expensive data-processing phase and preserved the private-data
  boundary.

## Correction

The two-file root-cause correction keeps the governance identity unchanged at the outer source
gate and authenticates the database producer identity separately from values already bound by the
immutable chain. The consumer now requires:

1. an exact lowercase code-commit representation;
2. equality with the full bound source-bundle hash;
3. the producer execution-ID derivation from that commit;
4. one common validated owner; and
5. exact content-derived source kernel and dataset references.

The authenticated producer tuple is included in the private source snapshot digest. The public and
source identity schemas do not expand, and no private identity is released.

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
typing, privacy, security, dependency, contract, and clean-tree checks. The final exact-set gate
must be repeated after this evidence update before another freeze.

## Remaining gates

1. Require the complete exact-set local gate over the final candidate bytes, then create a clean
   implementation-freeze commit and immutable private bundle.
2. Re-authenticate the private/offline/version-bound input chain.
3. Retry full Run A and validate it completely before starting Run B.
4. Complete independent Run B, deterministic comparison, benchmarks, private stratified human
   review, finalization, and disclosure-controlled validation.
5. Stop at the Chunk 5 gate; do not begin ontology, folds, labels, or model work.

Chunk 5 remains **FAIL / recovery pending** until every gate above succeeds.
