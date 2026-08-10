# Chunk 5 Run A source-manifest identity incident

Status: **recovery open; Chunk 5 not passed**

Date: 2026-08-10

## Summary

Predecessor implementation freeze `a5a44ac` and immutable bundle `7cf43...` authenticated far
enough to launch private Run A. The run failed closed before DICOM preprocessing, QA generation, or
benchmarking with the sanitized code `source_manifest_version_mismatch`. Run B was not started.
The corrected replacement candidate passed its complete local gate, while the predecessor freeze
and bundle remain superseded-pending; neither predecessor artifact is completion evidence.

Only the fixed sanitized failure code left the private environment. No pixel, report, patient-level
metadata, identifier, path, private resource reference, detailed checksum, review row, or private
artifact was exported or added to this record.

## Root cause

Chunk 4 has two legitimate identities with different purposes:

- the governance audit ID identifies the promoted, completed audit contract and registry row;
- the producer execution ID identifies the immutable manifest-producing run.

The private database stores the producer execution ID under the key `audit_id`. The Chunk 5
consumer compared that value with the governance audit constant. Both values were valid within
their own namespaces, but the comparison conflated them and deterministically triggered the
fail-closed error.

This was an identity-contract defect in the consumer, not evidence of manifest-version drift,
corrupt DICOM content, or a failed Chunk 4 audit.

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

## Remaining gates

1. Create a replacement clean implementation-freeze commit and immutable private bundle.
2. Re-authenticate the private/offline/version-bound input chain.
3. Retry full Run A and validate it completely before starting Run B.
4. Complete independent Run B, deterministic comparison, benchmarks, private stratified human
   review, finalization, and disclosure-controlled validation.
5. Stop at the Chunk 5 gate; do not begin ontology, folds, labels, or model work.

Chunk 5 remains **FAIL / recovery pending** until every gate above succeeds.
