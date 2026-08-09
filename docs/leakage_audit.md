# Leakage audit

## Disclosure

- count_representation: zero-below-threshold-at-or-above-threshold-or-fixed-width-range
- cross_snapshot_protection: fixed-width-intervals
- interval_width: 20
- minimum_export_cell: 20
- percentages_published: false
- policy: joint-complementary-k20-v1

## Duplicates

- altered_metadata_groups: range_20_39
- candidate_edges: range_8800_8819
- exact_file_groups: zero
- exact_pixel_groups: range_1220_1239
- exact_report_normalized_pairs: range_980_999
- exact_report_overlap_pairs: range_940_959
- exact_report_raw_pairs: range_940_959
- exact_report_union_pairs: range_980_999
- exact_series_groups: range_20_39
- exact_study_groups: below_threshold_nonzero
- label_copy_candidates: below_threshold_nonzero
- near_report_candidate_pair_count_lower_bound: zero
- near_report_candidate_space_overflow: false
- near_report_edges: zero
- near_report_overflow_study_edges: zero
- near_series_candidate_pair_count_lower_bound: range_1000000_1000019
- near_series_candidate_space_overflow: true
- near_series_edges: zero
- near_series_overflow_study_edges: range_4400_4419
- near_slice_edges: range_330340_330359
- near_slice_edges_suppressed: range_1712200_1712219
- near_slice_groups: range_63300_63319
- near_slice_overflow_study_edges: range_4340_4359
- near_slice_study_pair_count_lower_bound: range_250000_250019
- near_slice_study_pair_space_overflow: true
- near_slice_unresolved_study_pairs: zero
- raw_container_variation_groups: range_1180_1199

## Protected components

- cross_split_components: zero
- protected_components: range_4400_4419

## Structural grouping checks

- fold_feasibility: not_assessed
- folds_assigned: false
- future_fold_crossings: zero

## Integrity

- all_files_terminal: true
- all_series_terminal: true
- dicom_issue_dispositions_complete: true
- five_levels_reconciled: true
- foreign_keys: true
- private_artifacts_complete: true
- protected_graph_closed: true
