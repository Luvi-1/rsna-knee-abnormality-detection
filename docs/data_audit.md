# Data audit

## Disclosure

- count_representation: zero-below-threshold-at-or-above-threshold-or-fixed-width-range
- cross_snapshot_protection: fixed-width-intervals
- interval_width: 20
- minimum_export_cell: 20
- percentages_published: false
- policy: joint-complementary-k20-v1

## Scope

- example_test_only: true
- hidden_test_evaluable: false
- mode: full
- source_context: train-plus-example-test

## Coverage

- complete: true
- files_decoded: at_or_above_threshold
- files_quarantined: below_threshold_nonzero
- files_terminal: at_or_above_threshold
- files_total: at_or_above_threshold
- series_total: at_or_above_threshold
- studies_total: at_or_above_threshold
- test_series: below_threshold_nonzero
- test_studies: below_threshold_nonzero
- train_series: at_or_above_threshold
- train_studies: at_or_above_threshold

## Quality

- files_decode_failure: below_threshold_nonzero
- files_unreadable: zero
- path_header_mismatch: zero
- patient_group_missing: zero
- series_fallback: zero
- series_geometry_pass: at_or_above_threshold
- series_quarantined: below_threshold_nonzero
- unexplained_dicom_issues: zero

## Labels

- conflict_cells: zero
- negative_cells: range_440_459
- non_official_sources: zero
- official_cells: range_52880_52899
- official_only: true
- positive_cells: range_240_259
- unknown_cells: range_52180_52199

## Integrity

- all_files_terminal: true
- all_series_terminal: true
- dicom_issue_dispositions_complete: true
- five_levels_reconciled: true
- foreign_keys: true
- private_artifacts_complete: true
- protected_graph_closed: true

## Versions

- group_version: protected-groups-v2
- label_version: official-labels-v1
- manifest_version: manifest-v2
- preprocessing_version: unassigned

## Runtime

- elapsed_seconds: 10092
