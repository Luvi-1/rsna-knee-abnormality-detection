# Validation Card

Hard-group version: `protected-groups-v2`; full private recomputation completed in
`audit-0002-manifest-remediation`.

Fold version: `unassigned`; no folds exist.

## Competition metric contract

- Canonical source: `docs/competition_contract/contract.yaml` through
  `configs/competition.yaml`.
- Primary metric: unweighted mean of all 12 per-label ROC AUC values in canonical order.
- Degenerate-label behavior is unresolved. Local evaluation must require at least one positive and
  one negative for every target and fail closed otherwise.
- No threshold, transform, fold, label rule, calibration, or ensemble weight may be fit on
  validation rows.
- The live contract refreshed at `2026-08-08T22:03:12Z` with no material drift. Identity
  verification and the recorded unresolved fields still fail closed.

## Correction to historical grouping evidence

The historical `protected-groups-v1` audit is not current validation evidence. It allowed hard
duplicate/repeat relations and weak/approximate/overflow candidate relations to affect the same
components. Its reported zero future crossing was a property of an overclosed v1 graph, not proof
that folds were feasible, balanced, assigned, or leakage-free.

`protected-groups-v2` defines:

- **Hard protected components:** accepted exact duplicate and confirmed repeat relations that later
  folds must keep indivisible.
- **Soft candidate components:** weak near, report/template, label-vector, or overflow/approximation
  relationships retained for private review and later stress testing; these IDs cannot be fold
  group IDs.
- **Private provenance:** every relationship edge, evidence kind, component summary, and
  representative review path remains inside Kaggle.

The v2 private audit reports `protected_graph_closed: true`, `cross_split_components: zero`, and
`protected_components: range_4400_4419`. Hard duplicate evidence includes
`exact_pixel_groups: range_1220_1239`, `exact_series_groups: range_20_39`, and
`exact_study_groups: below_threshold_nonzero`; `exact_file_groups: zero`.

Soft review evidence remained separate even though `candidate_edges: range_8800_8819`,
`near_series_candidate_space_overflow: true`, and
`near_slice_study_pair_space_overflow: true`. The private audit validated component distributions,
edge attribution, representative transitive paths, and `near_slice_unresolved_study_pairs: zero`
without exporting identifiers or paths. This establishes structural grouping integrity only:
`folds_assigned: false` and `fold_feasibility: not_assessed`.

## Disclosure boundary

The v1 sanitized output independently suppressed fields and allowed a rare value to be derived from
related totals. It is superseded. The completed replacement release uses
`joint-complementary-k20-v1`, controls linked counts jointly, publishes no percentages, emits only
validated qualitative/fixed-width-range tokens, and renders all five approved files from one
controlled object. The schema-v2 output, guarded history/ref cleanup, and final complete
staged-candidate local gates passed. Hosted CI remains pending.

## DICOM block

The pinned v2 DICOM disposition gate passed. The approved output reports
`unexplained_dicom_issues: zero`, `dicom_issue_dispositions_complete: true`,
`all_files_terminal: true`, and `all_series_terminal: true`. Decode and quarantine findings remain
represented only as `below_threshold_nonzero`; their root cause, resolution evidence, and scope
remain private. This result does not survive a loader, decoder, schema, or input change without a
new audit.

## Shift and subgroup limits

The example-test interface has insufficient support for a reliable domain comparison, its reports
are unavailable, and the hidden scoring set is not evaluable. No domain-stratification or
hidden-shift claim is supported, so R-019 remains open.

## Required future fold evidence

- Positive, negative, and unknown support for all 12 targets in every candidate fold.
- Component-indivisible hard patient/repeat/duplicate splits plus explicit soft-candidate stress
  tests and a fresh leakage audit.
- Bootstrap confidence intervals and permitted scanner/protocol/language subgroup checks.
- Runtime, peak memory, model size, prediction correlations, and manual report/MRI validation when
  applicable.
- Out-of-fold predictions for every promoted model; nested or held-out evidence for ensemble
  weights.

None of that future evidence exists in this checkpoint because no fold or model work is authorized.
