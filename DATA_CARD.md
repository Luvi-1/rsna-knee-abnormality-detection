# Data Card

Status: the full private `manifest-v2` remediation audit completed in 10,092 seconds and its
schema-v2 sanitized output passed validation. The historical `manifest-v1` audit is preserved for
provenance but superseded for downstream use. Guarded history/ref cleanup and final complete
staged-candidate local gates passed; the private PR and hosted CI remain open.

## Source, scope, and license

- Competition: RSNA Knee Abnormality Detection.
- Canonical live inventory: 569.76 GB, 819,640 files, including 819,635 DICOM files and five CSV
  metadata files. These are official competition-level inventory facts, not released private audit
  counts.
- Types: DICOM and CSV under the competition rules and RSNA MIRA Dataset Research Use Agreement.
- Use is research/competition only. Redistribution, download-link sharing, re-identification,
  unauthorized access, clinical use, and unapproved public or commercial derived-artifact use are
  prohibited or fail closed pending written clarification.
- Full-data inspection must run only inside private Kaggle. Raw identifiers, paths, reports, pixels,
  patient-level metadata, private tables, row-level/private hashes, logs, and case-level DICOM
  findings must remain inside that boundary.

## Historical audit correction

The private `audit-0001-manifest` exercised the five intended levels: study, series, slice/file,
report, and label source. It cannot be used as current data-readiness evidence because:

- its v1 sanitized release independently suppressed related fields and allowed arithmetic
  reconstruction through published complements;
- `protected-groups-v1` mixed hard duplicate/repeat evidence with soft or overflow-candidate
  similarities;
- nonzero DICOM decode/quarantine findings had not received complete case-level root-cause and
  deterministic disposition review; and
- the final secret and remote-CI gates did not cover a complete cumulative release candidate.

The previous aggregate files and narrative counts are therefore superseded. This card does not
repeat their private result values. Their non-sensitive code, bundle, configuration, and artifact
hash provenance remains in `docs/experiments/audit-0001-manifest.md`.

## Validated remediation schema

- Manifest: `manifest-v2` (full private audit complete).
- Hard grouping: `protected-groups-v2` (full private recomputation complete).
- Labels: `official-labels-v1`; missing labels remain unknown, not negative.
- Preprocessing and folds: `unassigned`.

The v2 private schema retains reconciled entity tables, DICOM issue and disposition evidence, hard
protected components, separate soft candidate components, edge provenance, and private component
summaries. The public release boundary receives aggregates only and applies one joint disclosure
policy across every JSON and Markdown representation. The completed output reports
`coverage.complete: true`, `five_levels_reconciled: true`, `foreign_keys: true`,
`all_files_terminal: true`, `all_series_terminal: true`, and `private_artifacts_complete: true`.
Code, bundle, provenance, and artifact hashes are recorded in
`docs/experiments/audit-0002-manifest-remediation.md`.

## DICOM integrity status

The audit-specific DICOM disposition gate passed for the pinned v2 manifest without asserting that
every source object decoded. The approved tokens report `files_decode_failure:
below_threshold_nonzero`, `files_quarantined: below_threshold_nonzero`, and
`series_quarantined: below_threshold_nonzero`, together with:

- `unexplained_dicom_issues: zero`;
- `dicom_issue_dispositions_complete: true`;
- `files_unreadable: zero`, `series_fallback: zero`, and `path_header_mismatch: zero`; and
- complete file/series terminal accounting under the versioned private resolution gate.

The private producer gate rejects unresolved or recoverable-unsupported cases. No case identifier,
exception text, exact rare count, or case-level path is published. Any loader, decoder, schema, or
input change reopens this gate.

## Duplicate and leakage structure

The completed audit found nonzero hard duplicate evidence using only approved tokens:
`exact_pixel_groups: range_1220_1239`, `exact_series_groups: range_20_39`, and
`exact_study_groups: below_threshold_nonzero`; `exact_file_groups: zero`. These accepted hard
relations may make studies indivisible.

Soft candidate evidence remained separate. The release reports `candidate_edges:
range_8800_8819`, `near_series_candidate_space_overflow: true`,
`near_slice_study_pair_space_overflow: true`, and `near_slice_unresolved_study_pairs: zero`.
Weak near similarities, report/template candidates, label-vector similarities, and
approximation/overflow candidates did not automatically merge hard components. Every edge,
component statistic, and representative path remains private.

The representation is only a precursor to later fold construction. No fold exists, and no fold
feasibility, class balance, subgroup support, or leakage-free validation claim is currently
supported. The controlled structural status is `folds_assigned: false` and
`fold_feasibility: not_assessed`.

## Shift limitations

The visible test interface is example-only and low support, test reports are unavailable, and the
hidden scoring distribution is not evaluable. No hidden-test domain-shift claim is supported. Any
future safe aggregate comparison must meet the joint disclosure policy and minimum-support gates.

## Public schema

- `train.csv`: `StudyInstanceUID`, multilingual `Report`, and 12 partially populated binary targets.
- `train_series.csv`: study/series IDs, fluid sensitivity, fat suppression, and anatomical plane.
- `train_series/<StudyInstanceUID>/<SeriesInstanceUID>/<SOPInstanceUID>.dcm`: one slice per file.
- `PatientSex` is absent from the CSV interface. No DICOM tag may become a model dependency until it
  is verified on a scoring-equivalent test interface.

## Next evidence required

Guarded cleanup verifies that no active local or origin ref reaches the unsafe historical commit,
and the complete staged candidate passed all final local gates. Checkpoint 1 still requires the
cumulative private pull request and green GitHub-hosted CI. Preprocessing, folds, weak labels,
training, prediction, ensembles, and submission remain blocked.
