# Validation Card

Hard-group version: `protected-groups-v2`; `audit-0002-manifest-remediation` remains historical
scientific evidence only. The sanitized audit-0003 successor supplied the authenticated private
source root. R13 is terminal failed at performance smoke and cannot be resumed or spliced.

Fold version: `unassigned`; no folds exist.

## Current r13 terminal checkpoint

Legacy Kaggle authentication was restored without credential exposure. Exact r13 performance-smoke
version 1 authenticated and is terminal `ERROR`. The corrected strict failure validator returns
`phase=performance_smoke`, `code=throughput_projection_exceeds_budget`. The append-only registry is
terminal `failed`: input authentication passed, and Run A, Run B, comparison, review-plan, and human
review are `not_started`. No rerun, splice, Run A, output retrieval, or downstream launch occurred.
The safe log's one progress event localizes failure to the inner throughput gate. Exact 15-file tree
`afd8909a798d30fa9314fe6568768bca68fbda14` passed its complete D-015 gate with pytest 538/538 and
all recorded checks but is historical and superseded. After the governance bytes were restaged,
exact tree `e298964891b214bfbf4dc06725f2cde3b3bd3f74` failed the mandatory pytest rerun with one
failure and 537 passes because a manifest-runner test compared nondeterministic real wall-clock
`runtime.elapsed_seconds` (3 seconds versus 2). Production uses `ceil(monotonic - start)`, and its
validators intentionally accept an integer from zero through the configured maximum; production,
disclosure, and schema behavior remain correct. The minimal test-only correction reuses
`_validate_exact_aggregates` on the rerun, excludes only `runtime` from cross-run aggregate equality,
and retains exact table-hash, study-key, QA-byte, and audit-key equality. Focused 3/3 passed
repeatedly, the complete manifest-runner file passed 12/12, and Ruff check/format plus the scoped diff
check pass. The current candidate is exactly 16 files: seven source/tests, eight governance files,
and `docs/competition_contract/2026-08-21T200304Z.md`. Exact staged tree
`22c80aaa8f30d47a21e1a43fc3e945ab831c79ea` passed its first complete D-015 gate: locked offline
`uv` lock/sync; full pytest 538/538 in 63.84 seconds; isolated wheel build, offline install, and
import of `rsna-knee 0.1.0`; Ruff PASS with 124 files formatted; mypy over 25 package plus 16 trust-
boundary files; valid configuration with the established hash and synthetic submission `rows=2`;
canonical contract schema valid, current `contract_drift=no`, and generated schema bytes current;
sensitive guard PASS; tracked MIME exact at 154 regular files plus the one exact `.agents/skills`
symlink; `pip-audit` with no known vulnerabilities; all pre-commit hooks PASS; full tracked detect-
secrets PASS; and exact 16-file inventory, no unstaged or untracked residue, and unchanged-tree PASS.
This eight-file governance reconciliation changes bytes, so one immediate fully restaged identical
complete rerun and final red-team remain required. Only PASS with no later byte change fixes
`complete_final_gate=PASS`; any failure invalidates the first-pass final-gate evidence and requires
this record to be corrected. Freeze, bundle, authenticated identity-absence proof, append-only
registry preparation, and successor smoke remain pending. Even after those prerequisites pass,
authorization stops at one fresh successor smoke; Run A requires authenticated smoke terminal/output
validation and a fresh decision.

## Competition metric contract

- Canonical source: `docs/competition_contract/contract.yaml` through
  `configs/competition.yaml`.
- Primary metric: unweighted mean of all 12 per-label ROC AUC values in canonical order.
- Degenerate-label behavior is unresolved. Local evaluation must require at least one positive and
  one negative for every target and fail closed otherwise.
- No threshold, transform, fold, label rule, calibration, or ensemble weight may be fit on
  validation rows.
- The live contract refreshed through the official Kaggle MCP at `2026-08-21T20:03:04Z`. The
  819,640-file / 819,635-DICOM / five-CSV aggregate inventory, deadlines, runtime, limits, entered
  state, and recorded Host clarification were unchanged with no material drift. Latest snapshot:
  `docs/competition_contract/2026-08-21T200304Z.md`. Identity-verification state is unavailable
  through the read-only official interface and remains fail closed, not known incomplete.
- Host topic `733965` permits compliant commercial LLM or external inference under the Rules,
  equal-access, and minimal-cost conditions and clarifies that report processing is not itself
  private sharing.
- The stricter project boundary remains unchanged: no raw DICOM pixels, radiology reports,
  patient-level metadata, identifiers, private competition code or data, or private artifacts may
  be sent to any external LLM, API, or service. Only recognized members of the same official Kaggle
  team may receive private competition code or data.

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

Recovery iteration 8 passed the complete D-026 gate with pytest 528/528 and produced freeze
`4958c4a` / bundle `09502a...`. Its private/offline/version-bound inputs, smoke, and full-data Run A
authenticated and passed. Run B version 1 reached `COMPLETE` at 25,940 seconds; two independent
bounded read-only polls 71 seconds apart agreed, and the established authenticated validator
returned `dicom_qa_output_validation=PASS mode=workflow stage=run-b`. The protected registry row is
terminal `blocked`: input, smoke, Run A, and Run B are `passed`; comparison, `review_plan`, and
`human_review` are `not_started`; `completed_utc` is set; and integrity, foreign keys, and mode are
`PASS`. This is authenticated Run B workflow-output evidence only, not Chunk 5 PASS or comparison,
determinism, QA, review, or performance evidence. Frozen-source preflight had found two independent
P1 defects before comparison launch: the finalizer's six-required/sole-
optional-orthogonal artifact contract disagreed with the validator's exact-seven requirement, and
the automatic review-plan event sequence disagreed with the generic start/completion events expected
by local validation. Comparison, review-plan materialization, UI/session creation, human review, and
finalization were not launched.

The two-file D-027 correction passes focused 9/9 and packaging 147/147, Ruff check and format, strict
validator mypy, and independent red-team with no P0/P1. It passed in r9 freeze `1db805e`; the later
dependency-wheel content rejection is separate. This is not promoted preprocessing evidence.

D-028 adds the previously omitted `efficiency_prize`, `external_assets`, `team_and_sharing`,
`license`, `winner_obligations`, and `ambiguities` sections to the existing `MATERIAL_SECTIONS` and
tests both mutation and wholesale removal in `tests/test_smoke.py`. Smoke passes 6/6; the combined
focused set passes 155/155; Ruff/format, mypy over 25 source plus nine trust-boundary files,
independent current-source `contract_drift=no`, and post-fix red-team PASS/no P0/P1 all pass. The
r9 candidate passed the exact 529/529 gate and produced freeze `1db805e` / bundle `28457d...`; all
non-content bundle checks passed. Final content inspection found pinned upstream `pydicom 3.0.2`
aggregate 104 `.dcm` members and 188 standard DICM-preamble members, so the bundle was rejected
before upload. No r9 remote artifact exists. Its protected registry row is terminal `blocked`, every
remote stage is `not_started`, and the reason is `dependency_wheel_medical_payload_detected`.

D-029 uses one shared stdlib sanitizer in `package_manifest_bundle` to remove the general test tree
and any `.dcm`, `.dicom`, or standard DICM-at-byte-128 member, regenerate wheel `RECORD`
deterministically, validate every other wheel fail-closed, and preserve runtime modules, metadata,
licenses, and offline preflight. The first r10 candidate passed on exact staged tree
`5bea3c110e100e9ddd2d94c8b89c29e1f0ff82a0`: pytest 530/530; isolated wheel
build/install/import; Ruff check/format; mypy over 25 source and nine trust-boundary files;
audit/configuration/submission; contract schema and current `contract_drift=no`; pre-commit;
privacy checks; `pip-audit`; exact inventory and unchanged-tree checks. That gate is
superseded. D-030 preflight found that the project wheel lacked the shared archive guard; deployment
could skip wheel/`RECORD` checks; the actual local kernel upload lacked an exact two-file/hash
allowlist; and remote dataset/kernel version-1 content, sources, listings, and race stability were
not completely authenticated. It also found raw private-reference-capable commands, an unscoped
credential path, and a root-trust gap that allowed dataset metadata and wheel scanning from a safe
sibling directory other than the verified bundle-manifest root. The same helper built the
audit-0002 bundle.

The minimal correction extends the shared guard to the project wheel and adds one deployment
authenticator that directly reuses the existing DICOM-QA version-1 helpers. Before network access,
every stage validates the exact local two-file kernel/hash, all wheels/`RECORD`, resolved dataset
metadata under the exact bundle-manifest parent, and kernel metadata under its exact sibling kernel
directory. Remote gates authenticate exact private dataset version-1 content/hashes, exact kernel
version-1 code/source graph, stable listings, and before/after race snapshots. Status is fixed to
`PENDING`, `RUNNING`, `COMPLETE`, or `ERROR`; token scope, logs, `/1` references, and gates remain
bounded. The mismatched-root regression proves zero remote calls, and independent authentication
and runbook red-teams pass with no P0/P1. The historical first complete exact 24-file D-015 gate
passed on tree
`cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260`: pytest 537/537 plus the full lock/build/import,
static, configuration, contract, schema, pre-commit, privacy, dependency-audit, inventory, and
unchanged-tree checks all passed. That result is superseded. The later 15-file PASS and failed
restaged tree are also historical and superseded. The first exact 16-file gate passed, but these
governance bytes require the fully restaged identical complete rerun and final red-team;
`complete_final_gate=PASS` remains unset.

A clean r10 immutable candidate authenticated input, performance smoke, Run A, Run B, comparison,
and the review-plan source graph. Review-plan version 1 reached `ERROR`; two bounded read-only checks
93 seconds apart agreed, and the frozen privacy/canary failure validator passed with only
`input_discovery_invalid`. The source graph was correct: the generic basename walk entered the
legitimate greater-than-4,096-study competition tree before selecting the exact source. No review
artifact, pixel, UI/session, human QA, or finalizer stage was accessed or created. The r10 protected
row is terminal `failed`.

D-031 limits base discovery to depth 1 and kernel discovery to the exact derived mount while
preserving symlink, duplicate, count, file-type, and error rejection. Independent red-team passes
with no P0/P1; focused identity 41/41, boundary matrix 12/12, combined identity plus packaging
188/188, full pytest 537/537, Ruff/format, strict finalizer mypy, and the scoped diff check pass. The
historical first exact staged D-015 gate passed on tree
`959f14e9422db9670d16683ba8effe681cf6641d` over exactly 10
files: locked offline reinstall/lock; isolated wheel build/install/import; tracked MIME/symlink and
sensitive guards; Ruff/format; mypy over 25 package plus 11 trust-boundary files; pytest 537/537;
config/synthetic-submission; protected current contract/schema and generated-schema bytes;
pre-commit/detect-secrets; `pip-audit` with no vulnerabilities; cached diff, inventory, and unchanged-
tree PASS. That 10-file result is superseded. The later 15-file PASS and failed restaged tree are also
historical and superseded. The first exact 16-file gate passed, but these governance bytes require
the fully restaged identical complete rerun and final red-team; `complete_final_gate=PASS` remains
unset. Do not delete, reuse, resume, or splice r8,
r9, or r10.

D-033 records the current r13 state-machine mismatch. The smoke producer emits smoke-specific
start, progress, and failure events over a smoke-specific phase set; the generic consumer accepted
only full-run events and phases. The smallest fix keeps one entry point, selects the closed protocol
from the first exact start event, and enforces its exact terminal event, phase allowlist, ordered
progress prefix, and phase-specific legal prefix length. Hybrid, reordered, extra, and wrong-phase
logs are rejected. Exact authenticated revalidation returns `phase=performance_smoke`,
`code=throughput_projection_exceeds_budget`; this is terminal failure evidence, not runtime
acceptance. The 15-file PASS and failed restaged tree are historical and superseded. The first exact
16-file gate passed, but the fully restaged identical complete rerun and final red-team remain
pending.

D-034 removes only the stale sample `elapsed +` retained when the former monolithic smoke plus full
pass was split into a standalone 3,600-second smoke and later full-budget Run A/Run B kernels. Both
admission sites retain pre-smoke setup accounting where applicable, the conservative full-pass
projection, 3,600-second reserve, finite checks, self/outer deadlines, authentication, and privacy
gates. Existing 3,801/3,799-second boundary tests, the 4,320-second standalone ceiling, and scoped
static checks pass. A fresh successor smoke is still required and may fail closed; the 15-file PASS
and failed restaged tree are historical and superseded. The first exact 16-file gate passed, but the
fully restaged identical complete rerun and final red-team remain pending.

A fresh immutable successor smoke is required, and Chunk 5, QA, downstream work, and Chunk 6 remain
blocked. The Run A-through-finalizer design below is future scientific work, not current
authorization; it requires authenticated terminal/output validation of that fresh smoke and a fresh
decision. Distinct successor private version-1 Run A and Run B kernels must independently process the
entire authorized training set from the same bundle, preprocessing configuration, competition
input, and source-manifest input. Each produces a canonical full-pass manifest, deterministic
metrics, and a deterministic cohort plan without QA replay or rendering. Every discovered study,
series, and file must reconcile to an explicit terminal state. Each run must separately match
train-series membership, `source_row_count`, organizer plane/fluid/fat flags, and every regular
DICOM's keyed relative identity, byte size, and raw digest to authenticated `manifest-v2`, with zero
unexplained DICOM issue and zero unresolved recoverable transfer-syntax, ordering, or geometry
blocker.

A separate successor version-1 comparator must require byte-exact equality of the canonical manifests and
cohort plans plus exact equality of declared deterministic metrics. Timing and resource fields may
differ only where excluded by the frozen comparison contract; no tolerance may be invented after a
mismatch. Its summary must pass the D-026 exact-path/optional-safe-log retrieval boundary. Complete
private runtime, decode, preprocessing, cache, disk, peak-memory, CPU-scaling, and throughput
evidence is still required. The review-plan validator must then require the finalizer's exact six
mandatory artifacts, permit only its optional `orthogonal.png`, and accept only
`dicom_qa_review_started`, the four declared `dicom_qa_plan_progress` events, and
`dicom_qa_review_template_complete`, while preserving every existing fail-closed output and privacy
gate.

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
A locally composed review attestation is neither required nor accepted. R10 provides authenticated
historical input, smoke, Run A, Run B, and comparison evidence only. R13 provides only authenticated
input and terminal smoke-failure evidence. Neither is accepted QA, human-review, performance,
finalizer, or Chunk 5 evidence, and neither can be spliced into a successor. No folds exist and no
fold-feasibility claim is made.

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
