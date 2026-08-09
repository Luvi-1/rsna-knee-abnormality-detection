# Sanitized-output disclosure policy

Policy: `joint-complementary-k20-v1`. The minimum publication cell remains 20.
This policy applies at the trusted Kaggle release boundary to `sanitized_summary.json`, all three
audit Markdown files, `sanitized_artifact_inventory.json`, `human_review_summary.json`, and
`final_performance_report.json` before any output is downloadable.

## Threat model

The former field-by-field rule hid a count from 1 through 19 but allowed related exact values to
remain public. The following relations can expose a hidden count through arithmetic:

| Relation | Reconstruction risk |
|---|---|
| `studies_total = train_studies + test_studies` | Exact total and train disclose a small test count. |
| `series_total = train_series + test_series` | Exact total and train disclose a small test count. |
| File total, terminal, decoded, failed, and quarantined counts | Exact totals or pass counts can disclose a rare failure count by subtraction. |
| Series total, geometry-pass, fallback, and quarantine counts | Exact totals and clean counts can disclose a rare quarantine count. |
| `official_cells = positive + negative + unknown + conflict` | Exact parent and siblings can disclose a rare nested label state. |
| `report_union = raw + normalized - overlap` | Inclusion-exclusion can disclose a rare report-pair count. |
| Candidate totals, overflow edges, and component counts | Nested or overlapping totals can disclose a rare component. |
| Any percentage with an exact denominator | Rounding or exact multiplication can disclose a rare numerator. |
| JSON plus Markdown copies | A value hidden in one file can be disclosed by another file. |
| Prior plus current snapshots | Two exact releases can disclose a rare change by differencing. |

Duplicate/nonduplicate, clean/excluded, and included/excluded complements are subject to the same
rule if later added. Artifact byte counts and hashes cover only canonical policy-controlled
documents; they do not encode a private count because all values from 1 through 19 share one token.

## Release representation

Every audit count, including totals and complements, is transformed centrally into exactly one of:

- `zero`
- `below_threshold_nonzero`, representing any integer from 1 through 19
- `at_or_above_threshold`, used for an exact complement whenever its group contains a
  below-threshold count or for an explicitly declared capped top band
- `range_L_U`, where `L` is a multiple of 20 and `U = L + 19`

No exact audit count or percentage is allowed. If a linked total, pass/fail, included/excluded, or
other complement group contains `below_threshold_nonzero`, every nonzero complement is widened to
`at_or_above_threshold`; this remains safe even when an exact public denominator exists elsewhere.
Runtime seconds and the public policy constants are not population counts and remain exact.
Fixed-width intervals protect counts outside rare complementary groups against snapshot
differencing. The JSON summary is the canonical representation; Markdown files must be
byte-for-byte canonical renderings of it, and the inventory must hash those exact renderings.

For Chunk 5, exact human-review counts remain only in the private completion. The release-safe
`reviewed_studies` field uses 20-wide ranges from 100 through 219; every value from 220 through the
private maximum of 240 is coalesced to `at_or_above_threshold`. `eligible_series_reviewed` uses a
20-wide range, `block_decisions` uses the standard count tokens and must be `zero` for exit, and
`represented_strata` exposes only `all_material_covered`. `final_performance_report.json` must repeat
the identical validated review tokens; it cannot expose a second, more precise representation.

The trusted validator rejects schema v1, exact numeric audit counts, percentages, malformed or
non-k=20 intervals, inconsistent complement intervals, cross-file differences, unexpected fields,
and any output that fails the existing identifier/path/report/pixel scans.

## Structural grouping reporting boundary

Checkpoint 1 creates no folds, so fold feasibility remains not assessed. The trusted leakage
document uses `Structural grouping checks`, never `Fold feasibility`, and must state both
`folds_assigned: false` and `fold_feasibility: not_assessed`. The disclosed
`future_fold_crossings` field is only a structural precondition carried by the manifest contract;
with no fold assignment it cannot certify balance, feasibility, or leakage-free validation. Those
claims require a later versioned fold artifact and the full leakage-auditor gate.

## DICOM disposition reporting boundary

The source-controlled policy has four fixed terminal disposition categories: known file issues are
`file_quarantine`; known series issues are `series_quarantine`; instance-order fallback is
`series_fallback_quarantine`; and an unrecognized file or series issue fails closed as
`unexplained_quarantine`. Low-information perceptual fingerprints have the separate nonterminal
`candidate_search_exclusion` disposition, scoped only to near-duplicate candidate discovery. These
category names and policy versions are public taxonomy, not observed data. Public output does not
state which root-cause code occurred or publish a count by category. Every actual issue remains
classified in the private manifest.

A generic decode failure is fail-closed as `unexpected_unexplained`; it cannot satisfy the public
gate until a fixed root cause and deterministic disposition are persisted privately.

The minimum public proof is therefore `dicom_issue_dispositions_complete: true` together with
`unexplained_dicom_issues: zero`. The first requires the fixed issue-code policy to be exhaustive,
versioned, and present on every private file/series issue record; the second proves that no actual
record used the fail-closed unexplained category. Publishing a per-category occurrence map would
expand the release surface and is forbidden until its totals, overlaps, and complements are added
to this joint disclosure model and its adversarial tests.

## Historical correction

The original schema-v1 aggregate snapshot used independent suppression and is not approved for
release because complementary exact values allowed rare-count differencing. Replacing the files at
HEAD does not remove that disclosure from the existing Git commit: the old file total and decoded
total alone reconstruct the private rare count. No HEAD-only policy can make that already-reachable
snapshot safe. Schema v2 supersedes it for future releases, but merge readiness remains blocked
until the current remediation mandate is completed with a clean replacement/squash of the result
commit and a guarded `--force-with-lease` update that leaves no active remote feature reference to
the schema-v1 snapshot. The coordinating workflow, not this disclosure-code subtask, performs and
verifies that exact history cleanup. A private full audit rerun also remains required for data
readiness and fresh provenance.

During contract refresh, a read-only official inventory pagination probe unintentionally emitted
deidentified DICOM UID paths into ephemeral internal tool output. The method was stopped
immediately. No preview, repository artifact, saved file, or user-facing output was created;
subsequent verification used aggregate root-tree fields only. Identifiers are never valid sanitized
output under either the scanner or this disclosure policy.
