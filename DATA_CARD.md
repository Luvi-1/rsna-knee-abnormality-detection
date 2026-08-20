# Data Card

Status: `audit-0002-manifest-remediation` remains historical scientific evidence only; the sanitized
audit-0003 successor supplied the authenticated r10 source root. R10 input, smoke, Run A, Run B, and
comparison passed, but review-plan v1 failed safely at input discovery before any review artifact or
pixel access. R10 is terminal failed, Chunk 5 has not passed, and only the fresh r12 no-splice chain may
continue.

## Current r12 recovery identity

The 2026-08-20 contract refresh found no material drift and froze commit
`2723ff4a1692d5d897234e67aba167c629017f9b`. The replacement bundle
`efe087afd5bb8f5391213e359c52b88f5930975c837b813ee98affe3f1fb9921` passed local packaging,
verified-policy, synthetic/offline preflight, and packaging checks. Registry r12 is append-only and
`planned`; all remote stages are `not_started`, and no r12 dataset, kernel, run, output, or pixel has
been created. The prior r11 candidate is historical and cannot be reused or spliced. A protected
metadata-only smoke-identity absence check is required before any new private version-1 smoke push.

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
- Host topic `733965` permits some compliant commercial LLM or external inference under the Rules,
  equal-access, and minimal-cost conditions and clarifies that report processing is not itself
  private sharing.
- This does not change the stricter project boundary: no raw DICOM pixels, radiology reports,
  patient-level metadata, identifiers, private competition code or data, or private artifacts may
  be sent to any external LLM, API, or service. Only recognized members of the same official Kaggle
  team may receive private competition code or data.

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
- Preprocessing candidate: `dicom-model-v1` is locally implemented and synthetic-tested but is not
  promoted; folds remain `unassigned`.

The v2 private schema retains reconciled entity tables, DICOM issue and disposition evidence, hard
protected components, separate soft candidate components, edge provenance, and private component
summaries. The public release boundary receives aggregates only and applies one joint disclosure
policy across every JSON and Markdown representation. The completed output reports
`coverage.complete: true`, `five_levels_reconciled: true`, `foreign_keys: true`,
`all_files_terminal: true`, `all_series_terminal: true`, and `private_artifacts_complete: true`.
Code, bundle, provenance, and artifact hashes are recorded in
`docs/experiments/audit-0002-manifest-remediation.md`.
These remain historical scientific provenance; they are not a reusable bundle/source root after
D-029.

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

`dicom-model-v1` has local and partial private implementation evidence, but it is not promoted data
readiness. D-026 passed its complete exact-set gate with pytest 528/528 and produced iteration-8
freeze `4958c4a` and immutable bundle `09502a...`. Its private/offline/version-bound inputs,
standalone smoke, and full-data Run A authenticated and passed. Run B version 1 reached `COMPLETE`
at 25,940 seconds; two independent bounded read-only polls 71 seconds apart agreed, and the
established authenticated validator returned
`dicom_qa_output_validation=PASS mode=workflow stage=run-b`. The protected registry row is terminal `blocked`:
input, smoke, Run A, and Run B are `passed`; comparison, `review_plan`, and
`human_review` are `not_started`; `completed_utc` is set; and integrity, foreign keys, and mode are
`PASS`. This is authenticated Run B workflow-output evidence only, not Chunk 5 PASS or comparison,
determinism, QA, review, or performance evidence.

Before comparison launch, frozen-source preflight found two independent P1 review-plan contract
defects. The finalizer requires six QA artifacts per review group and permits `orthogonal.png` only
when renderable, while the validator required exactly seven. Automatic materialization emits
`dicom_qa_review_started`, four `dicom_qa_plan_progress` events, and
`dicom_qa_review_template_complete`, while the validator expected generic run boundaries.
Comparison, review-plan materialization, UI/session creation, human review, and finalization were not
launched and must never launch on iteration 8 because D-027 and D-028 change frozen source. The
D-027 two-file correction passes focused 9/9 and packaging 147/147, Ruff check and
format, strict validator mypy, and independent red-team with no P0/P1. It is included in the r9
first complete release-gate PASS.

D-028 closes a separate contract-governance P1: the drift checker omitted `efficiency_prize`,
`external_assets`, `team_and_sharing`, `license`, `winner_obligations`, and `ambiguities`, allowing
mutation or wholesale removal to yield `contract_drift=no`. The minimal fix extends the existing
`MATERIAL_SECTIONS` and `tests/test_smoke.py` only. Smoke passes 6/6; the combined focused set passes
155/155; Ruff/format, mypy over 25 source plus nine trust-boundary files, independent current-source
`contract_drift=no`, and post-fix red-team PASS/no P0/P1 all pass. The r9 candidate passed the exact
529/529 gate and produced freeze `1db805e` / bundle `28457d...`; every non-content bundle check
passed. Final content inspection rejected the bundle before upload because pinned upstream
`pydicom 3.0.2` contains aggregate 104 `.dcm` members and 188 standard DICM-preamble members. No r9
remote artifact exists. Its registry row is terminal `blocked`, every remote stage is `not_started`,
and the reason is `dependency_wheel_medical_payload_detected`.

D-029 applies one shared stdlib sanitizer in `package_manifest_bundle`: remove the general test tree
plus any `.dcm`, `.dicom`, or standard DICM-at-byte-128 member; regenerate wheel `RECORD`
deterministically; validate every other wheel fail-closed; and preserve runtime modules, metadata,
licenses, and offline preflight. The first r10 candidate passed on exact staged tree
`5bea3c110e100e9ddd2d94c8b89c29e1f0ff82a0`: pytest 530/530; isolated wheel
build/install/import; Ruff check/format; mypy over 25 source and nine trust-boundary files;
audit/configuration/submission; contract schema and current `contract_drift=no`; pre-commit;
privacy checks; `pip-audit`; exact inventory and unchanged-tree checks. D-030 preflight then
found that the project wheel lacked the shared medical-payload guard, deployment stages could skip
wheel/`RECORD` checks, the actual local kernel upload lacked an exact two-file/hash allowlist, and
remote dataset/kernel version-1 content, sources, listings, and race stability were not completely
authenticated. Raw status/private-reference-capable commands and an unscoped credential path also
violated the fixed-output boundary. The 530/530 gate is therefore superseded.

The minimal D-030 correction extends the shared guard to the project wheel and adds one deployment
authenticator that directly reuses the existing DICOM-QA version-1 helpers. Before any network
operation, every stage validates the exact two-file local kernel/hash and every wheel/`RECORD`.
Remote gates authenticate exact private dataset version-1 content/hashes, exact kernel version-1
code/source graph, stable listings, and before/after race snapshots. Status is limited to
`PENDING`, `RUNNING`, `COMPLETE`, or `ERROR`; the runbook uses a command-scoped token, protected
logs, explicit `/1`, and bracketed gates. No dependency, framework, or new abstraction was added.
Both independent authentication and runbook red-teams pass with no P0/P1. The first complete exact
24-file D-015 gate passed on tree `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260`: pytest 537/537,
offline lock/build/import, Ruff/format, mypy over 25 package and 11 trust-boundary files,
config/submission/contract/schema checks, pre-commit, privacy scans, `pip-audit`, and exact
inventory/unchanged-tree checks all passed. This reconciliation changes bytes, so an immediate
identical fully restaged rerun is required; its PASS fixes `complete_final_gate=PASS`.

R10 then authenticated its exact input, smoke, Run A, Run B, comparison, and review-plan source
graph. Review-plan version 1 reached `ERROR`; two bounded read-only checks 93 seconds apart agreed,
and the frozen privacy/canary failure validator passed with only `input_discovery_invalid`. The
shared automatic basename walk had entered the official greater-than-4,096-study competition tree
before selecting the already-correct source. No private plan artifact, pixel, UI/session, human
review, or finalizer stage was accessed or created, and the r10 registry is terminal `failed`.

D-031 changes only the shared finalizer and its focused identity regression: base discovery stops at
depth 1 and kernel-output discovery starts below the exact derived kernel mount. Existing symlink,
duplicate, count, file-type, and error gates remain fail closed. Independent red-team passes with no
P0/P1; focused identity 41/41, boundary matrix 12/12, combined identity plus packaging 188/188, full
pytest 537/537, Ruff/format, strict finalizer mypy, and the scoped diff check pass. The first exact
staged D-015 gate passed on tree `959f14e9422db9670d16683ba8effe681cf6641d` over exactly 10 files:
locked offline reinstall/lock; isolated wheel build/install/import; tracked MIME/symlink and
sensitive guards; Ruff/format; mypy over 25 package plus 11 trust-boundary files; pytest 537/537;
config/synthetic-submission; protected current contract/schema and generated-schema bytes;
pre-commit/detect-secrets; `pip-audit` with no vulnerabilities; cached diff, inventory, and unchanged-
tree PASS. This governance reconciliation changes bytes, so one immediate identical restaged rerun
must PASS to fix the final gate as passed; failure invalidates and must correct this record. Do not
reuse, resume, delete, or splice any r8, r9, or r10 stage.
Distinct fresh r11 Run A and Run B version-1 kernels must independently process the entire authorized
training set from the same immutable bundle, configuration, competition input, and source-manifest
input.
Each run emits a canonical full-pass manifest, deterministic metrics, and a deterministic cohort
plan, without replaying or rendering the selected QA artifacts.
Every run must exactly reconcile train-series membership, `source_row_count`, organizer
plane/fluid/fat flags, and every regular DICOM's keyed relative identity, byte size, and raw digest
against `manifest-v2`. Every discovered study, series, and file must also reach one explicit terminal
state, and all case-level geometry, decode, slot, quality, transform, checksum, cache, failure, and
performance evidence must remain in Kaggle.

A separate private comparator must require byte-exact equality of the canonical manifests and
cohort plans plus exact equality of deterministic metrics. Runtime and resource observations are
measured but excluded from equality only where frozen before execution; every other mismatch
requires investigation and an unexplained mismatch blocks Chunk 5.

Selector v3 runs from each complete full-pass result. It has a minimum target of 100 reviewable
studies but no arbitrary study maximum; exact incremental greedy selection continues until every
required represented value quota is met across bounded semantic registries, including bounded
site-domain buckets. Physical file, byte, time, and disk gates may fail closed but cannot silently
reduce coverage. The legacy joint-material census and coverage claim are removed. The only public
registry-coverage token is `all_required_represented_registry_values_satisfy_quotas`.

After exact Run A/Run B comparison, the existing review-plan kernel authenticates a capacity
certificate bound to the freeze, bundle, manifest, both runs, cohort plan, and renderer. It replays
every selected series, renders each twice, runs the representative decode/preprocessing/resource
benchmarks once, and materializes the private plan without adding another kernel or data reference.
Every eligible diagnostic series in each selected study must be reviewed. The private plan, review
identity, cohort hash, artifact hashes, rows, and fixed nine-check decisions remain inside Kaggle.
Every row also binds the private organizer/physical plane, assigned slot, retention reasons,
six-slot missing mask, and ordinal sibling slot/terminal/model-eligibility/retention/quality-block
context. Each remote review group must contain the finalizer's exact six mandatory artifacts and may
contain only the optional `orthogonal.png`; its safe log must use the exact automatic review start,
four progress, and template-completion event sequence.

The authorized human uses Chrome Copy & Edit on the safe private UI template to create a distinct
private review session, enters `START` before any artifact access, and records only `PASS`, `BLOCK`,
or `NOT_APPLICABLE`. The pinned finalizer consumes that completed private session directly and
authenticates the exact source manifest, bundle, preprocessing configuration, Run A/Run B,
comparison, cohort, UI, parent, and kernel versions. No locally composed review attestation is an
input. Review artifacts resolve only under the authenticated Run A slug root. Only
`human_review_summary.json` and `final_performance_report.json` may be retrieved as the two final
allowlisted release-safe outputs. They must prove identity binding, at least 100 studies,
`all_required_represented_registry_values_satisfy_quotas`, all eligible series, all nine checks
terminal, and zero `BLOCK` using
disclosure-controlled tokens while exact review counts, private identities, and private hashes
remain inside Kaggle.

Every r11 private input and kernel must pass the D-030 ready/private, offline, exact-version-1,
exact-content/source/listing, and before/after race gates with fixed sanitized output. Until the
final sanitized determinism, performance, and human-review outputs
validate, preprocessed artifacts are experimental and folds, weak labels, training, inference,
prediction, ensembles, and submission remain blocked. R10 supplies historical evidence only through
comparison; Chunk 5, QA, and Chunk 6 remain blocked.
