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

## Chunk 5 staged release surfaces

Run A and Run B are core-only releases. Their private output allowlist is exactly
`private_full_run_manifest.jsonl`, `private_full_run_metrics.json`, and
`private_cohort_plan.json`. Their downloadable allowlist is exactly `sanitized_summary.json` and
`sanitized_artifact_inventory.json`; the latter inventories only the canonical safe summary. The
safe core summary may disclose fixed completion/integrity/coverage booleans, version labels,
quantized throughput tokens, bounded runtime/resource measurements, and the public competition
limit. It must not disclose cohort contents or hashes, case or stratum counts, a case index,
artifact inventory, review rows, QA images, representative-case details, or post-comparison
benchmark results.

The comparator authenticates the private outputs but releases only the fixed schema-v1 aggregate
with `status: pass`, `independent_runs_compared: true`,
`exact_manifest_byte_equality: true`, `deterministic_metrics_equal: true`,
`cohort_plan_byte_equality: true`, `unresolved_mismatches: zero`, and
`private_case_details_downloaded: false`. It does not compare or disclose a QA artifact inventory,
because no QA artifacts exist in either core run. It does not release cohort hashes, counts, rows,
or timing/resource equality claims.

The authenticated performance-smoke aggregate may additionally expose only a conservative
whole-second per-series QA replay/render ceiling, a 60-second-quantized representative benchmark
ceiling, the fixed seven-artifact-per-series policy constant, and a power-of-two MiB ceiling for
per-series review artifacts. Those are resource-certificate bounds, not observed cohort counts or
identities.

The private review-plan stage owns selected-cohort replay, double rendering, private case and
artifact inventories, `private-review/`, representative decode/preprocessing and CPU-scaling
benchmarks, RAM/cache measurements, and `private_review_plan.json`. Its only downloadable files are
the post-comparison `sanitized_summary.json`, canonical `benchmark.md`, and their
`sanitized_artifact_inventory.json`. The trusted validator may retrieve those three safe files only
after authenticating the exact private/offline version-1 source graph and private output listing.
The UI and finalizer consume review-plan artifacts in place; they must never cause any private plan,
case row, identifier, path, image, pixel, ledger, or artifact hash to cross the Kaggle boundary.

For Chunk 5, exact human-review counts remain only in the private completion. The release-safe
`reviewed_studies` and `eligible_series_reviewed` fields use 20-wide ranges; the selector has a
minimum of 100 studies and no policy maximum. `block_decisions` uses the standard count tokens and
must be `zero` for exit, and `represented_strata` exposes only
`all_required_represented_registry_values_satisfy_quotas`.
`final_performance_report.json` must repeat the identical validated review tokens; it cannot expose
a second, more precise representation.

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
