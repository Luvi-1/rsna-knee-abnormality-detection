# Secret, disclosure, and history audit

Date: 2026-08-08

Scope: the clean replacement branch, the promoted schema-v2 aggregate release, the exact secret
baseline, and the remaining local and remote history references.

No credential value, private repository locator, report, patient or study identifier, medical
pixel, private grouping key, or private artifact identifier is reproduced in this record.

## Handling-control exceptions

During an earlier read-only remote-state check, the Git client printed the private repository
locator to transient terminal output. No credential, token, medical data, or write capability was
exposed, and the locator was not saved in the repository or copied into this record. Subsequent
checks compare sanitized fields and print fixed status tokens only.

During a separate read-only live-inventory check, an official API pagination response emitted
deidentified DICOM UID paths to transient internal tool output. The method was stopped immediately.
No identifier, preview, file, repository artifact, or user-facing output was created. Subsequent
inventory verification used only root-tree aggregate fields.

## Clean replacement and remaining history boundary

Clean replacement HEAD `6fce3af` does not reach the superseded schema-v1 result commit. The four
legacy result paths are absent from that HEAD and have zero commits in its ancestry:

- `docs/manifest_summary.json`
- `docs/data_audit.md`
- `docs/leakage_audit.md`
- `docs/domain_shift_audit.md`

The guarded history remediation is now complete for active references. The local Chunk 4 feature
branch, its remote-tracking reference, and the live private remote feature reference all point to
the clean replacement HEAD. The temporary preservation branch has been deleted. A fresh ancestry
audit found zero active local, remote-tracking, or other Git references that reach the superseded
result commit.

The coordinating workflow performed the approved guarded remote replacement and local reference
cleanup; this documentation update performed no reference or remote mutation. Active-reference
unreachability does not assert that every unreferenced loose object, local reflog entry, or remote
server retention copy has already been garbage-collected. It establishes the required operational
boundary: the superseded disclosure is no longer reachable from an active branch or tracked remote
reference.

## Promoted schema-v2 aggregate release

The four canonical documentation artifacts now come byte-for-byte from the locally downloaded,
fail-closed validated output for the pinned `6fce3af` bundle. The release uses schema version 2,
the joint complementary k=20 disclosure policy, fixed-width interval or qualitative count tokens,
and canonical JSON/Markdown derivation. It includes no raw identifiers, reports, pixels, private
tables, percentages, or patient metadata.

The manifest-output validator checked the pinned run configuration, bundle manifest, expected code
commit, expected bundle identity, downloadable-file allowlist, sanitized inventory, schemas,
cross-file rendering, disclosure vocabulary, and privacy scanner before promotion. Each canonical
file was then compared byte-for-byte with its validated downloaded source.

## Exact secret baseline

`.secrets.baseline` contains exactly two approved result paths:

- ten exact `Hex High Entropy String` records for the canonical competition contract; and
- five exact `Hex High Entropy String` records for the new schema-v2 manifest summary.

It contains no approval for either historical schema-v1 artifact, any Markdown report, or any
other path. Detector classes, entropy limits, verification policy, filters, and file scope remain
unchanged. The five new approvals were added only after each candidate was mapped to one named
provenance field and independently verified against the pinned source.

| Schema-v2 summary field | Independent verification | Classification |
|---|---|---|
| `competition_config_sha256` | Recomputed from the pinned competition configuration | Non-secret content provenance |
| `competition_contract_sha256` | Recomputed from the pinned canonical contract | Non-secret content provenance |
| `git_commit` | Matched to the run configuration, bundle manifest, clean HEAD, and an existing commit object | Repository code provenance |
| `manifest_schema_sha256` | Recomputed from the pinned manifest schema | Non-secret content provenance |
| `uv_lock_sha256` | Recomputed from the pinned dependency lock | Non-secret content provenance |

None is a credential, authentication token, signed or private URL, session identifier,
patient/study identifier, or private Kaggle artifact identifier.

## Historical five-candidate classification

The superseded schema-v1 summary also produced five high-entropy findings. They were previously
matched to the same five provenance classes without printing their values. Those classifications
remain audit evidence only; they are not baseline approvals. The unsafe historical summary had a
separate aggregate-disclosure defect, so classifying its provenance hashes as non-secrets never
made that release privacy-safe.

## Regression invariant

The focused secret regression uses an isolated temporary checkout and baseline copy. It:

1. scans both the canonical contract and schema-v2 summary with the exact repository settings;
2. requires the observed records to equal the complete baseline result map;
3. requires exactly ten contract records and five summary records;
4. confirms the real hook accepts both reviewed files; and
5. confirms a runtime-constructed, unbaselined GitHub-token shape is rejected without echoing its
   value.

No validation command may refresh or mutate the shared repository baseline. Every future summary
must repeat the field-level provenance verification before replacing its five exact approvals.

## Remaining gates

The schema-v2 release and governance files were committed and pushed in cumulative release
candidate `cc050a21ab3386b501170d224ef57ef990a3753b`. Private pull request #10 is open and unmerged,
and its hosted `quality` workflow passed on that exact candidate. This later documentation update
must pass the same local and hosted gates after it is committed. The active-reference history gate
remains passed, and merge remains pending explicit approval.
