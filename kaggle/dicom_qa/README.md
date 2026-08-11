# Private Kaggle DICOM QA

This is the approval-gated Chunk 5 runbook. It runs the complete training set twice through the
immutable `dicom-model-v1` pipeline and then performs bound private human QA. It does not perform
ontology, fold, label, model, inference, prediction, ensemble, or submission work.

Pixels, identifiers, paths, private manifests, cohort rows and hashes, review artifacts, the
completed ledger, and private Kaggle references remain inside authorized private resources. Never
print them or persist copies outside the required ignored private metadata. Redirect Kaggle command
output to a mode-0700 temporary directory, delete it at exit, and expose only fixed pass/fail tokens.

## 1. Package one clean, immutable candidate

Start only after the complete local gate passes on a clean candidate commit. The packager refuses a
dirty tree. It also refuses the superseded `audit-0001` source manifest. Supply the ignored,
mode-0700 Chunk 4 bundle root (containing its `dataset/` and `kernel/`) and the ignored, mode-0600
audit registry whose `audit-0002-manifest-remediation` row is `completed` for `manifest-v2`.
The source root must contain the exact v1 `dataset/bundle-manifest.json`, `run-config.json`,
`dataset-metadata.json`, `kernel/run.py`, and `kernel-metadata.json`; the packager verifies their
complete local inventory, hashes, permissions, derived identities, and registry binding.

```bash
umask 077
: "${KAGGLE_OWNER:?set KAGGLE_OWNER without printing it}"
: "${SOURCE_MANIFEST_BUNDLE_ROOT:?set the ignored Chunk 4 bundle root}"
: "${SOURCE_MANIFEST_REGISTRY:?set the ignored Chunk 4 audit registry}"

bundle_root="artifacts/dicom-qa-bundle"
uv run python scripts/package_dicom_qa_bundle.py \
  --repo-root . \
  --output "$bundle_root" \
  --owner "$KAGGLE_OWNER" \
  --workers 4 \
  --source-manifest-bundle-root "$SOURCE_MANIFEST_BUNDLE_ROOT" \
  --source-manifest-registry "$SOURCE_MANIFEST_REGISTRY" \
  --source-manifest-audit-id audit-0002-manifest-remediation

expected_commit="$(jq -er .code_commit "$bundle_root/dataset/run-config.json")"
expected_bundle="$(jq -er .bundle_sha256 "$bundle_root/dataset/run-config.json")"
jq -e '
  .input_identity.source_manifest.audit_id == "audit-0002-manifest-remediation" and
  .input_identity.source_manifest.version == "manifest-v2" and
  .input_identity.source_manifest.kernel_version == 1 and
  .input_identity.source_manifest.bundle_dataset_version == 1 and
  .provenance.preprocessing_version == "dicom-model-v1" and
  .review_policy.cohort_selection_version == "qa-cohort-selection-v3" and
  .review_policy.stratum_registry_version == "qa-stratum-registry-v1" and
  .review_policy.protocol_version == "private-dicom-qa-human-review-v2" and
  .review_policy.instructions_version == "private-dicom-qa-review-instructions-v2"
' "$bundle_root/dataset/run-config.json" >/dev/null
```

The public success token includes only the bundle SHA-256. The packager binds the exact Chunk 4
kernel source/hash, bundle dataset/version/listing, manifest schema, private-output policy, registry
row, preprocessing/configuration, dependency lock and wheelhouse, QA logic, comparator, review UI,
finalizer, and validator.

Packaging also runs a fail-closed synthetic preflight before the bundle can exist. It installs the
built production project wheel and host-native dependencies from the exact frozen lock into an
isolated temporary target, disables normal site packages and network access, and runs a fixed
three-slice MR series twice through the real decode, physical-ordering, and preprocessing path. A
separate no-index resolver gate proves that the bundled Linux x86-64 wheelhouse is complete for
CPython 3.11 and 3.12. The canonical sanitized result is
`dataset/synthetic-preflight.json`; its exact size, SHA-256, singleton role, and provenance hash are
bound into the bundle manifest and run configuration. It contains no pixels, paths, UIDs, input
checksums, or private references. This is host-native execution plus Linux wheelhouse-resolution
evidence, not target-runtime execution: `kaggle_runtime_execution` remains `pending_run_a`, and the
immutable private Run A is the Kaggle execution proof.

The generated upload directories are exactly:

- `dataset`
- `performance-smoke-kernel`
- `kernel-a`
- `kernel-b`
- `comparison-kernel`
- `review-plan-kernel`
- `review-ui-template-kernel`
- `review-finalizer-kernel`

Do not patch any generated file. Any change requires a new clean candidate and bundle identity.

## 2. Create and authenticate the private base dataset

Remote creation requires explicit human approval immediately before this step. Do not add
`--public`, create a second dataset version, accept rules, or change a team. Keep all command output
inside a protected temporary directory because it can contain a private locator.

```bash
token_value="$(launchctl getenv KAGGLE_API_TOKEN)"
test -n "$token_value"
remote_audit_root="$(mktemp -d)"
chmod 700 "$remote_audit_root"
trap 'rm -rf "$remote_audit_root"' EXIT

KAGGLE_API_TOKEN="$token_value" kaggle datasets create \
  --path "$bundle_root/dataset" --dir-mode skip --quiet \
  >"$remote_audit_root/dataset-create.log" 2>&1
```

Define the one staged authenticated validator command. Every invocation authenticates the base
dataset and `audit-0002` source-manifest inputs, every immutable predecessor through the requested
stage, and a second base-dataset snapshot. It prints only a fixed token.

```bash
validate_workflow_stage() {
  local stage="$1"
  KAGGLE_API_TOKEN="$token_value" uv run python \
    scripts/validate_dicom_qa_output.py \
    --run-config "$bundle_root/dataset/run-config.json" \
    --bundle-manifest "$bundle_root/dataset/bundle-manifest.json" \
    --expected-commit "$expected_commit" \
    --expected-bundle "$expected_bundle" \
    --workflow-kernel-version 1 \
    --workflow-stage "$stage"
}

validate_workflow_stage inputs
```

The `inputs` stage must pass before the performance-smoke kernel is pushed. It proves the base and
source-manifest datasets ready, private, version 1, and exact-content-bound; authenticates the
version-1 source producing `manifest-v2`, its status, metadata, and private output inventory; and
detects mutation or a version race. The
validator temporarily re-downloads only the exact immutable base/source input-bundle allowlists
already present in the authorized local private bundle, using mode-0700 directories and mode-0600
files. It rejects nested paths, symlinks, extras, or missing files, recomputes every declared size
and SHA-256, captures and discards all CLI output, and deletes the snapshot immediately. It never
downloads competition DICOMs, source-kernel outputs or its private database, or any QA output. Do
not continue on any failure.

## 3. Run the private performance smoke, then the immutable chain

`kernel-a` and `kernel-b` are different content-addressed kernel identities. Each independently
processes the entire authorized training set from fresh immutable inputs. This is not a replay in
one kernel and not a review-cohort-only run. The comparator requires exact byte equality of the
declared deterministic manifest and metadata fields; timing and resource measurements are declared
nondeterministic before comparison.

Push each directory once, in this order, and never repush it as version 2:

1. `performance-smoke-kernel` — private, offline, CPU-only, bounded production-path smoke.
2. `kernel-a` — complete Run A.
3. `kernel-b` — independent complete Run B.
4. `comparison-kernel` — exact Run A/Run B comparison.
5. `review-plan-kernel` — replay the compared cohort, render and verify its private artifacts,
   run the representative benchmarks, and create the bound private plan.
6. `review-ui-template-kernel` — safe, unattended template version 1.

Use the following helper for each full-chain directory after the smoke. Its protected log is
deleted by the existing trap and must never be pasted into chat or committed.

The separate performance-smoke v1 must be private, offline, CPU-only, have GPU and TPU disabled,
and retain the exact bundle, competition, and authenticated `manifest-v2` inputs. It executes only
the authenticated source-manifest-stratified sample through the production series, cache,
source-reconciliation, bounded per-series QA replay/render, and representative benchmark paths
under a 3,600-second self deadline. Its allowlisted aggregate must say `full_run_started=false` and
reports a conservative whole-second Stage-B replay/render ceiling plus a quantized benchmark
ceiling; the smoke never
invokes Run A or a full-data pass. A passing projection is admission and downstream resource-
certificate evidence, not full-run runtime evidence. The `run-a` workflow gate reauthenticates the
completed smoke v1 before authenticating Run A, and every later gate does so transitively. Run A and
Run B do not repeat the smoke internally; their safe progress sequence begins with `full_pass`, so
the complete 27,000-second self budget remains available to the core full-data pass.

The 28,800-second Run A/B outer timeout preserves 30 minutes after the runner's 27,000-second
fail-closed self deadline and remains one hour below the verified 32,400-second competition
ceiling.

```bash
KAGGLE_API_TOKEN="$token_value" kaggle kernels push \
  --path "$bundle_root/performance-smoke-kernel" --timeout 4200 \
  >"$remote_audit_root/performance-smoke-kernel.push.log" 2>&1

push_kernel_v1() {
  local directory="$1"
  KAGGLE_API_TOKEN="$token_value" kaggle kernels push \
    --path "$bundle_root/$directory" --timeout 28800 \
    >"$remote_audit_root/${directory}.push.log" 2>&1
}
```

Wait for performance-smoke v1 to complete, then authenticate its private/offline/version-1
configuration, exact sources and input binding, version-2 absence, bounded output allowlist, and
sanitized `full_run_started=false` result:

```bash
validate_workflow_stage performance-smoke
```

Do not push Run A unless this gate passes.

```bash
push_kernel_v1 kernel-a
```

Wait for Run A v1 to complete, then authenticate it before launching the independent Run B
identity:

```bash
validate_workflow_stage run-a
```

```bash
push_kernel_v1 kernel-b
```

Wait for Run B v1 to complete and authenticate both full runs before launching the comparator:

```bash
validate_workflow_stage run-b
```

```bash
push_kernel_v1 comparison-kernel
```

```bash
validate_workflow_stage comparison
```

```bash
push_kernel_v1 review-plan-kernel
```

```bash
validate_workflow_stage plan
```

```bash
push_kernel_v1 review-ui-template-kernel
```

```bash
validate_workflow_stage ui
```

Run each validator gate only after the pushed v1 reaches terminal completion. Do not push a
dependent stage until its exact predecessor gate passes. A failed, incomplete, or timed-out v1 is
a blocker; do not repair it by creating v2.

Run A and Run B are deliberately core-only. Each emits exactly three private files:
`private_full_run_manifest.jsonl`, `private_full_run_metrics.json`, and
`private_cohort_plan.json`. Its only release-safe files are `sanitized_summary.json` and
`sanitized_artifact_inventory.json`. Neither run renders the selected cohort, writes a private case
index or artifact inventory, creates `private-review/`, nor runs the representative decode and CPU
scaling benchmarks. This keeps both independently executed deterministic scopes identical and
leaves enough wall-time margin for the complete full-data pass.

The bound `output_policy` keeps separate `run_private_remote_only`, `run_downloadable`,
`review_private_remote_only`, `review_private_remote_patterns`, and `review_downloadable`
allowlists, with distinct run/review remote and download byte caps. A producer or validator that
falls back to the former shared allowlist fails closed.

The runs retain private terminal dispositions for every discovered study, series, and file, full
transform provenance, slot/mask/sampling decisions, core performance measurements, and the exact
post-pass cohort plan. After the full pass, seeded greedy selection combines the `manifest-v2`
evidence with `qa-stratum-registry-v1` and `qa-cohort-selection-v3`. The selector has a
minimum of 100 studies, not a maximum: it grows the cohort as needed to satisfy the represented
registry-value quota `min(2, population)` and records the exact private coverage ledger. Selection
never limits the full-data run, and no case row or registry value leaves Kaggle. The comparator requires byte
equality of both full manifests, equality of the
declared deterministic metrics, and byte equality of `private_cohort_plan.json`; it exposes only
the fixed `cohort_plan_byte_equality` result, not cohort contents or an artifact inventory claim.

The existing review-plan kernel is the only downstream QA-preparation stage; do not add another
kernel. Its exact kernel sources are performance-smoke v1, Run A v1, Run B v1, and comparison v1,
in that order, and its only competition source is the official competition. It deliberately has no
direct source-manifest kernel source: the already-authenticated full manifests and cohort plan bind
the source identity, while the official competition mount supplies the selected DICOMs for replay.
The stage first verifies the comparison and exact plan, then replays every selected eligible series,
renders twice, proves the two private inventories match, runs preprocessing/decode/CPU-scaling and
RAM/cache benchmarks, and writes `private_case_index.json`,
`private_artifact_inventory.json`, `private-review/`, `sanitized_summary.json`, `benchmark.md`,
`sanitized_artifact_inventory.json`, and the bound `private_review_plan.json`. These artifacts are
owned by review-plan v1, never by Run A or Run B.

Before replay starts, the plan stage must combine the authenticated smoke resource certificate
with the exact selected eligible-series count. It fails closed if seven artifacts per series would
exceed the 20,000-file cap, if the projection cannot fit its 27,000-second self deadline and
fixed 600-second finalization reserve, or if the 8 GiB total and 32 MiB per-file caps cannot be
respected. The same 28,800-second outer timeout applies. It must never truncate the selected cohort
to make the budget fit. Its `dicom_qa_plan_progress` sequence is exactly `cohort_replay`
start/complete followed by `benchmark` start/complete; it must not emit core `full_pass` progress
or repeat the standalone smoke.

The 25 mandatory dimensions are `laterality`, `organizer_plane`, `physical_plane`,
`organizer_physical_plane_relation`, `assigned_diagnostic_slot`,
`additional_diagnostic_series`, `multiple_series_per_slot`, `missing_diagnostic_slot`,
`retained_nonduplicate_abnormal_series`, `duplicate_handling`, `bit_depth_category`,
`photometric_interpretation`, `transfer_syntax`, `slice_thickness_stratum`,
`slice_spacing_stratum`, `resolution_extreme`, `slice_count_extreme`,
`scanner_manufacturer`, `scanner_model`, `field_strength`, `site_domain_cluster`,
`source_manifest_quality_flag`, `terminal_state`, `pipeline_case`, and
`dicom_edge_case_subtype`. Missing scanner hardware or domain evidence is an explicit `missing`
value, not an omitted dimension. The registry therefore covers left, right, and unknown laterality;
organizer/physical-plane conflicts; assigned, additional, retained-abnormal, duplicate, and missing
slot cases; syntax, photometric, bit-depth, thickness, spacing, resolution, and slice-count values;
terminal/recoverable pipeline cases; and each represented DICOM edge subtype.

Each run also requires exact agreement between the current training population and authenticated
`manifest-v2`. It reconciles train-series membership, `source_row_count`, and the organizer
`plane`, `fluid_sensitive`, and `fat_suppression` fields before processing. During the same full
pass, every regular DICOM must match its private keyed relative `file_key`, `file_size_bytes`, and
`raw_file_exact_key` in `slice_file_manifest`. An added, removed, relocated, resized, or byte-changed
series or file fails closed as `source_manifest_population_mismatch`; terminal accounting alone is
insufficient.

The review-plan release-safe benchmark combines the authenticated Run A core timing with its own
post-comparison replay, render, decode/preprocessing, CPU-scaling, RAM, and cache measurements. Its
nine-hour assessment states only the measured preprocessing contribution and remaining budget
under 32,400 seconds; it never claims that a future model fits.

After the notebook loads the signed UI module, its first operation before any review-data access is
the interactive `START` gate. Its unattended push receives EOF, emits
`INTERACTIVE_REVIEW_REQUIRED`, and must not read or display the plan or artifacts or write a ledger.
Its v1 output may contain only the bounded session log.

## 4. Complete the bound human review in Chrome

Use the signed-in private Kaggle interface in Chrome. Computer Use may navigate to the safe template
and prepare the private Copy & Edit only while no review rows or pixels are loaded. A human
reviewer—not Codex, Computer Use, another LLM, or browser automation—must inspect the pixels.

1. Open the authenticated private `review-ui-template-kernel` v1.
2. Choose **Copy & Edit**. The copy must remain private, offline, and retain exactly the template's
   base-dataset and four kernel sources: Run A, Run B, comparison, and review-plan. The smoke is
   already bound and consumed by review-plan, so the UI must not add it as a fifth source.
3. Before the first Save Version, name the distinct review session with the required slug pattern
   `rsna-knee-dqa-review-<commit7>-<bundle12>`. It must be a child of the template, not the template
   itself.
4. Run the single notebook cell. Before typing `START`, stop all LLM and browser automation,
   including Computer Use, screenshots, screen sharing, and accessibility inspection. The human
   then takes exclusive control and must type exactly `START`. Only then may the notebook discover the
   plan or display private artifacts.
5. Confirm the displayed `REVIEW_BUNDLE_ID`, `PREPROCESSING_VERSION`, and `QA_COHORT_HASH` remain
   unchanged for the whole review. The authenticated identity also binds `manifest-v2`, exact input
   versions, the bundle and preprocessing-config hashes, the compared runs, review-plan v1, and
   every artifact hash.
   Do not copy any private identity outside Kaggle.
6. Review every row. The plan contains at least 100 studies, includes every eligible diagnostic
   series for every selected study, and grows beyond 100 whenever the private coverage ledger needs
   more studies to satisfy every represented registry value. Before deciding, inspect the
   plan-bound private `review_context`: `organizer_plane`, `physical_plane`, `laterality`,
   `laterality_transform`, `horizontal_flip_applied`, `assigned_slot`, `retention_reasons`, the
   six-boolean `missing_series_mask`, `sibling_series`, `check_9_applicable`, and
   `check_9_reason_codes`. Every ordinal-ordered sibling record has exactly `series_ordinal`,
   `slot`, `terminal_state`, `model_eligible`, `retention_reasons`, and
   `quality_blocked_reasons`. The UI resolves every artifact only below the authenticated
   review-plan slug root named by the review identity; a missing, duplicate, ambiguous, symlinked,
   or non-review-plan source fails closed.
7. For each row enter one nine-character vector using only `P`, `B`, or `N` for `PASS`, `BLOCK`, or
   `NOT_APPLICABLE`, in this immutable order:

   1. `slice_order`
   2. `anatomical_orientation`
   3. `laterality_preservation`
   4. `no_unintended_mirroring`
   5. `intensity_polarity`
   6. `anatomy_not_clipped`
   7. `sequence_slot_assignment`
   8. `preprocessing_appearance`
   9. `duplicate_missing_abnormal_handling`

   Use the following fixed rubric. `PASS` requires positive visual and context evidence. Record
   `BLOCK` for a defect, missing comparison evidence, ambiguity, or doubt; checks 1-8 never permit
   `NOT_APPLICABLE`.

   - `slice_order`: `PASS` only when physical slice progression is smooth, ordered, and unrepeated.
   - `anatomical_orientation`: `PASS` only when anatomy agrees with the physical-plane and direction
     evidence.
   - `laterality_preservation`: `PASS` only when every available source side marker or cue is
     unchanged and the bound provenance records no laterality-changing transform. Source
     laterality recorded as unknown is valid only when it remains unknown; never infer or invent a
     side.
   - `no_unintended_mirroring`: `PASS` only when source-to-processed comparison shows no unintended
     reflection. No mirroring or horizontal flip is authorized.
   - `intensity_polarity`: `PASS` only when source-to-processed tissue polarity is consistent and
     not inverted.
   - `anatomy_not_clipped`: `PASS` only when the knee remains fully inside the processed field.
   - `sequence_slot_assignment`: `PASS` only when plane, contrast, slot, siblings, missing mask, and
     reasons agree.
   - `preprocessing_appearance`: `PASS` only when anatomy and contrast are preserved without
     banding, washout, nonfinite regions, or interpolation distortion.
   - `duplicate_missing_abnormal_handling`: when the UI says `CHECK_9_APPLICABLE=YES`, `PASS` only
     when duplicate, missing, blocked, or reasoned-series handling matches the displayed context;
     otherwise record `BLOCK`. `N` is permitted only for `duplicate_missing_abnormal_handling`, and
     only when the UI says `CHECK_9_APPLICABLE=NO`.

   There is no global one-`PASS`-per-check shortcut: each applicable row must carry its own positive
   evidence, and all decisions must be terminal.

8. Continue until every row is complete. Then type this fixed attestation exactly when prompted:
   `I ATTEST THAT I AM AN AUTHORIZED HUMAN REVIEWER, I PERSONALLY INSPECTED EVERY DISPLAYED PRIVATE
   ARTIFACT, AND NO LLM OR BROWSER AUTOMATION VIEWED THE PRIVATE ARTIFACTS.` The attestation is
   created only after all rows; its instructions version and timestamp are part of the ledger.
9. Continue until the UI emits `PRIVATE_REVIEW_COMPLETE`. Use **Quick Save** with output files only
   then; that first human Save Version must create the distinct review-session v1 containing only
   `completed_review_ledger.json` and at most one bounded log. In-progress checkpoints support only
   the still-running live review session and must never be durably saved. If that session is lost or
   an incomplete v1 is saved, stop; do not resume from stale evidence or create v2.
10. After the completed v1 is saved, the human must close the review tab or navigate to a page that
    shows no review pixels or rows. Only then may control return to Codex, Computer Use, browser
    automation, screenshots, screen sharing, or accessibility inspection for aggregate-only
    authentication.

After review-session v1 reaches terminal completion, authenticate it before launching the
finalizer:

```bash
validate_workflow_stage review
```

The plan covers all 25 registry dimensions and every represented value, with a required private
quota of `min(2, population)`. The plan and finalizer verify the coverage ledger, eligible-series
completeness, artifact presence, and hashes as separate invariants; visual decisions cannot
substitute for missing coverage or a missing artifact.

Any `BLOCK`, incomplete row, missing eligible series, unsatisfied represented registry-value quota,
identity change, artifact mismatch, or suspected systematic ordering/orientation/laterality error
prevents Chunk 5 exit. If review-session v1 is saved incomplete or with the wrong identity, stop and
create a new immutable candidate identity; never use v2 to overwrite the evidence.

## 5. Run the private finalizer and authenticate the whole workflow

Only after the completed review-session v1 exists, push the prebuilt finalizer once:

```bash
push_kernel_v1 review-finalizer-kernel
```

The finalizer consumes the authenticated review-plan v1 directly, reconstructs its exact plan,
rehashes every private artifact owned by that stage, requires the same full review identity, row
set, coverage ledger, and eligible-series set, validates every fixed decision, and derives both the
detailed private completion and the two allowlisted release-safe outputs. Its exact sources are
Run A, Run B, comparison, review-plan, and the completed review session; omission of review-plan
fails closed. It never accepts a locally fabricated or stale aggregate attestation. It rejects an
attestation with the wrong instructions version or statement, a time before review start, a future
time, a completion/attestation mismatch, or any identity mismatch. The private completion holds the
review identity, cohort hash, private coverage evidence, reviewed-study and eligible-series counts,
nine-check counts, block count, timestamps, ledger hash, and rows. Exact counts, strata, identities,
and hashes remain private. The release-safe `human_review_summary.json` contains only
disclosure-controlled count tokens, fixed version labels, coverage/completion booleans, nine
canonical results, identity-bound status, and block status. The separate
`final_performance_report.json` combines the authenticated core-run measurements with the
review-plan benchmark, determinism, and human-review completion; it does not release exact review
counts, private manifests, exact throughput counts, or private identity hashes.

After finalizer v1 reaches terminal completion, authenticate the complete exit chain:

```bash
validate_workflow_stage final
```

The only ordered stage values are `inputs`, `performance-smoke`, `run-a`, `run-b`, `comparison`,
`plan`, `ui`, `review`, and `final`. Do not pass removed legacy version or attestation flags. The
workflow validator derives every private reference internally. For each stage before `final`, require exactly
`dicom_qa_output_validation=PASS mode=workflow stage=<stage>` with the requested stage substituted.
The completed exit gate must return exactly
`dicom_qa_output_validation=PASS mode=workflow stage=final determinism=pass human_review=pass`.
Anything else is a blocker.

Kaggle CLI 2.2.4 can parse a version suffix while some status, listing, or output paths still resolve
against the latest version. The validator closes that ambiguity by proving v2 absence; requiring v1
terminal status; pulling and hashing the exact v1 source before and after authenticated listings;
checking exact output inventories; and repeating dataset snapshots. For packaged kernels it
verifies private/offline and exact dataset, kernel, competition, and model sources from authenticated
metadata. For the human review session, it performs bounded source-only v1 pulls before and after
the metadata and listing checks, requires the exact notebook hash, type, parent, and source sets,
and never retrieves notebook outputs, the completed ledger, attachments, or review artifacts.

The validator temporarily retrieves only allowlisted sanitized aggregates: the performance smoke's
`sanitized_performance_smoke.json`; each run's `sanitized_summary.json` and
`sanitized_artifact_inventory.json`; review-plan's `sanitized_summary.json`, `benchmark.md`, and
`sanitized_artifact_inventory.json`; comparator `sanitized_determinism.json`; and finalizer
`human_review_summary.json` plus `final_performance_report.json`. It authenticates private output
inventories by listing names and bounded sizes but never downloads a full manifest,
`private_cohort_plan.json`, private case/artifact inventory, review plan, ledger, private completion,
identifier, path, image, pixel, or case artifact. Temporary safe copies are deleted.
Do not broaden the allowlists or manually retrieve private files.

A schema-valid aggregate with any block remains an exit failure. No human QA has occurred at this
checkpoint. Chunk 5 passes only when the
authenticated workflow, exact Run A/Run B comparison, real performance evidence, at-least-100/all-
represented-strata/all-eligible-series review, all nine checks, zero blocks, disclosure controls,
governance, final staged engineering gates, commit, push, and clean-tree gates all pass. Stop before
Chunk 6.
