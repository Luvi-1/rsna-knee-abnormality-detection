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
- The live contract refreshed through the official Kaggle MCP at `2026-08-13T19:20:34Z`. One
  explained data-description fingerprint change was already covered by the canonical semantics;
  identity verification and the recorded unresolved fields still fail closed.

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
staged-candidate local gates passed. Hosted CI passed for release candidate `cc050a2`; every
successor remains subject to the same exact-head gate.

## DICOM block

The pinned v2 DICOM disposition gate passed. The approved output reports
`unexplained_dicom_issues: zero`, `dicom_issue_dispositions_complete: true`,
`all_files_terminal: true`, and `all_series_terminal: true`. Decode and quarantine findings remain
represented only as `below_threshold_nonzero`; their root cause, resolution evidence, and scope
remain private. This result does not survive a loader, decoder, schema, or input change without a
new audit.

## Chunk 5 preprocessing gate

`dicom-model-v1` has synthetic evidence for strict decoding, observed transfer syntaxes,
IOP/IPP-based physical ordering, fail-closed geometry, laterality preservation, intensity handling,
deterministic sampling, flexible series slots, and repeated-output checks. Its orientation policy
canonicalizes the physical slice direction while preserving native in-plane pixels and performing
no horizontal flip.

An earlier staged candidate passed its then-current complete local gate and red-team, but later
source changes and the D-023 two-stage redesign invalidate that historical result. The fourth
private Run A attempt completed a full-data pass and then failed closed in the superseded capped
joint-material selector; it produced no admissible Run A package. Run B, comparison, QA
materialization, human review, and finalization did not occur. The exact 29-file staged D-023
candidate subsequently passed the complete final local gate, including pytest 507/507 and the
locked install/build, lint, format, typing, CLI/config/submission/contract, pre-commit, privacy,
dependency, contract-drift, diff, inventory, and clean-tree checks. Independent end-to-end/source-
graph red-teams found no remaining P0/P1.

Recovery iteration 6 exposed `private_cohort_plan_invalid`. Root-cause tracing showed that
`SelectedStudy` serialized legacy/internal dimensions outside the exact 25-dimension plan schema
and that representative series were chosen from the global eligible population rather than the
selected cohort. The smallest source/test fix filters dimensions through the existing exact
registry, selects the cohort before representative profiles, and restricts profiles to selected
studies. D-025 passed its focused checks and complete exact-set gate, producing iteration-7 freeze
`e3c6334` and immutable bundle `5fe504...`.

Recovery iteration 7 authenticated its private/offline/version-bound inputs and smoke. Independent
full-data Run A and Run B both authenticated and passed. The comparison kernel reached `COMPLETE`
and its comparator producer was correct, but local workflow validation failed closed with
`comparison_output_layout_invalid`: Kaggle CLI 2.2.4 unconditionally retrieved one root wrapper log
while the validator required one total file. The r7 append-only row is terminal failed. Review-plan
materialization, UI/session creation, human review, and finalization did not start. The planned
two-file D-026 correction requires the exact summary path, permits at most one size-bounded privacy-
scanned root log, and rejects every other entry, wrong path, symlink, special file, oversized log,
canary hit, or sensitive payload. Its focused checks, complete gate, replacement freeze/bundle, and
full remote chain remain required. The checkpoint relay could not connect to Chrome, so no new
reviewer decision exists; standing Chunk 5 authorization controls.

This is not yet promoted preprocessing evidence. The clean immutable candidate must authenticate
the completed private `audit-0002-manifest-remediation` / `manifest-v2` output and reject the
superseded audit. Distinct private version-1 Run A and Run B kernels must independently process the
entire authorized training set from the same bundle, preprocessing configuration, competition
input, and source-manifest input. Each produces a canonical full-pass manifest, deterministic
metrics, and a deterministic cohort plan without QA replay or rendering. Every discovered study,
series, and file must reconcile to an explicit terminal state. Each run must separately match
train-series membership, `source_row_count`, organizer plane/fluid/fat flags, and every regular
DICOM's keyed relative identity, byte size, and raw digest to authenticated `manifest-v2`, with zero
unexplained DICOM issue and zero unresolved recoverable transfer-syntax, ordering, or geometry
blocker.

A separate version-1 comparator must require byte-exact equality of the canonical manifests and
cohort plans plus exact equality of declared deterministic metrics. Timing and resource fields may
differ only where excluded by the frozen comparison contract; no tolerance may be invented after a
mismatch. Its summary must pass the D-026 exact-path/optional-safe-log retrieval boundary. Complete
private runtime, decode, preprocessing, cache, disk, peak-memory, CPU-scaling, and throughput
evidence is still required.

Selector v3 runs after each full pass with a minimum of 100 reviewable studies and no arbitrary
study maximum. Exact incremental greedy selection continues until every required represented value
quota is met across bounded semantic registries, including bounded site-domain buckets. The only
public registry-coverage token is `all_required_represented_registry_values_satisfy_quotas`; no
legacy joint-material census or coverage claim is accepted. After exact Run A/Run B comparison, the
existing review-plan kernel must authenticate the capacity certificate against the freeze, bundle,
manifest, both runs, cohort plan, and renderer before any pixel decode. Physical file, byte, time,
and disk limits fail closed. The kernel then replays every selected series, renders each twice, runs
the representative benchmarks once, and materializes the bound private plan. Every eligible
diagnostic series in each selected study must be reviewed. The exact canonical checks are:

1. `slice_order`
2. `anatomical_orientation`
3. `laterality_preservation`
4. `no_unintended_mirroring`
5. `intensity_polarity`
6. `anatomy_not_clipped`
7. `sequence_slot_assignment`
8. `preprocessing_appearance`
9. `duplicate_missing_abnormal_handling`

The human records only `PASS`, `BLOCK`, or `NOT_APPLICABLE`; every check must be terminal and any
`BLOCK` prevents exit. `NOT_APPLICABLE` is permitted only for
`duplicate_missing_abnormal_handling`, and every check must have at least one `PASS`. Each plan row
binds organizer/physical plane, assigned slot, retention reasons, the six-slot missing mask, and
ordinal sibling slot/terminal/model-eligibility/retention/quality-block context. The plan, review
identity, cohort hash, artifact hashes, rows, decisions, pixels, paths, and case details remain inside
Kaggle under
`private-dicom-qa-human-review-v2`.

The safe private UI template must be copied and edited in Chrome into a distinct private review
session version 1, with `START` as the first operation before artifact access. The pinned private
finalizer consumes the completed session directly and authenticates the exact source manifest,
bundle, preprocessing configuration, runs, comparison, cohort, UI parent, and kernel versions;
review artifacts resolve only under authenticated Run A. It may release only
`human_review_summary.json` and `final_performance_report.json` as the two final allowlisted
release-safe outputs, using disclosure-controlled review tokens while exact counts remain private.
A locally composed review attestation is neither required nor accepted. Iteration 7 provides
authenticated historical Run A/Run B and completed-producer evidence, but its terminal-failed chain
is not an accepted comparison, review, or finalizer result and cannot be spliced into iteration 8.
No folds exist and no fold-feasibility claim is made.

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
