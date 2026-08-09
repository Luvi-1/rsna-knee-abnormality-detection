# Domain shift audit

## Disclosure

- count_representation: zero-below-threshold-at-or-above-threshold-or-fixed-width-range
- cross_snapshot_protection: fixed-width-intervals
- interval_width: 20
- minimum_export_cell: 20
- percentages_published: false
- policy: joint-complementary-k20-v1

## Scope

- example_test_only: true
- mode: full
- source_context: train-plus-example-test

## Shift

- evaluation_scope: train-plus-example-test
- field_strength_t: suppressed_low_test_support
- in_plane_resolution_area_mm2: suppressed_low_test_support
- overall_missingness: suppressed_low_test_support
- patient_age_years: suppressed_low_test_support
- patient_sex: suppressed_low_test_support
- plane_availability: suppressed_low_test_support
- protocol_cluster: suppressed_low_test_support
- report_language: not_evaluable_test_reports_unavailable
- scanner_manufacturer: suppressed_low_test_support
- scanner_model: suppressed_low_test_support
- sequence_composition: suppressed_low_test_support
- series_description_vocabulary: suppressed_low_test_support
- site_domain_cluster: suppressed_low_test_support
- slice_thickness_mm: suppressed_low_test_support
- study_complexity_series_count: suppressed_low_test_support
- study_complexity_slice_count: suppressed_low_test_support

## Limitations

- hidden_test_evaluable: false

## Integrity

- all_files_terminal: true
- all_series_terminal: true
- dicom_issue_dispositions_complete: true
- five_levels_reconciled: true
- foreign_keys: true
- private_artifacts_complete: true
- protected_graph_closed: true
