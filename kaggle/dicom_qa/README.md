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
  .review_policy.cohort_selection_version == "qa-cohort-selection-v2" and
  .review_policy.protocol_version == "private-dicom-qa-human-review-v1"
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

The `inputs` stage must pass before Run A is pushed. It proves the base and source-manifest datasets
ready, private, version 1, and exact-content-bound; authenticates the source-manifest v1 source,
status, metadata, and private output inventory; and detects mutation or a version race. The
validator temporarily re-downloads only the exact immutable base/source input-bundle allowlists
already present in the authorized local private bundle, using mode-0700 directories and mode-0600
files. It rejects nested paths, symlinks, extras, or missing files, recomputes every declared size
and SHA-256, captures and discards all CLI output, and deletes the snapshot immediately. It never
downloads competition DICOMs, source-kernel outputs or its private database, or any QA output. Do
not continue on any failure.

## 3. Run the immutable private chain through the safe UI template

`kernel-a` and `kernel-b` are different content-addressed kernel identities. Each independently
processes the entire authorized training set from fresh immutable inputs. This is not a replay in
one kernel and not a review-cohort-only run. The comparator requires exact byte equality of the
declared deterministic manifest and metadata fields; timing and resource measurements are declared
nondeterministic before comparison.

Push each directory once, in this order, and never repush it as version 2:

1. `kernel-a` — complete Run A.
2. `kernel-b` — independent complete Run B.
3. `comparison-kernel` — exact Run A/Run B comparison.
4. `review-plan-kernel` — rehash the Run A artifacts and create the bound private plan.
5. `review-ui-template-kernel` — safe, unattended template version 1.

Use the following helper for each named directory. Its protected log is deleted by the existing
trap and must never be pasted into chat or committed.

```bash
push_kernel_v1() {
  local directory="$1"
  KAGGLE_API_TOKEN="$token_value" kaggle kernels push \
    --path "$bundle_root/$directory" --timeout 23400 \
    >"$remote_audit_root/${directory}.push.log" 2>&1
}

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
Run A/B retain private terminal dispositions for every discovered study, series, and file, full
transform provenance, slot/mask/sampling decisions, performance measurements, QA artifacts, and
the deterministic post-pass cohort. After the full pass, seeded greedy selection combines the
`manifest-v2` acquisition/domain strata with terminal geometry, resolution, quality, slot,
duplicate, missing-series, and DICOM-edge strata. It targets 120 studies and may expand to 240 to
cover every represented dimension value, including singleton/nonmaterial values, plus the material
joint strata; selection never limits the full-data run. No case row leaves Kaggle.

Each run also requires exact agreement between the current training population and authenticated
`manifest-v2`. It reconciles train-series membership, `source_row_count`, and the organizer
`plane`, `fluid_sensitive`, and `fat_suppression` fields before processing. During the same full
pass, every regular DICOM must match its private keyed relative `file_key`, `file_size_bytes`, and
`raw_file_exact_key` in `slice_file_manifest`. An added, removed, relocated, resized, or byte-changed
series or file fails closed as `source_manifest_population_mismatch`; terminal accounting alone is
insufficient.

The release-safe benchmark reports aggregate full-run runtime, decode/preprocessing/slot/QA/cache
times, throughput, peak RAM and disk/cache size, and representative 1/2/4/8-worker scaling where
the private runtime supports it. Its nine-hour assessment states only the measured preprocessing
contribution and remaining budget under 32,400 seconds; it never claims that a future model fits.

After the notebook loads the signed UI module, its first operation before any review-data access is
the interactive `START` gate. Its unattended push receives EOF, emits
`INTERACTIVE_REVIEW_REQUIRED`, and must not read or display the plan or artifacts or write a ledger.
Its v1 output may contain only the bounded session log.

## 4. Complete the bound human review in Chrome

Use the signed-in private Kaggle interface in GPT/Chrome. Do not use Brave. A human reviewer—not
Codex or another LLM—must inspect the pixels.

1. Open the authenticated private `review-ui-template-kernel` v1.
2. Choose **Copy & Edit**. The copy must remain private, offline, and retain exactly the template's
   base-dataset and four kernel sources.
3. Before the first Save Version, name the distinct review session with the required slug pattern
   `rsna-knee-dqa-review-<commit7>-<bundle12>`. It must be a child of the template, not the template
   itself.
4. Run the single notebook cell and type exactly `START`. Only then may it discover the plan or
   display private artifacts.
5. Confirm the displayed `REVIEW_BUNDLE_ID`, `PREPROCESSING_VERSION`, and `QA_COHORT_HASH` remain
   unchanged for the whole review. Do not copy those private values outside Kaggle.
6. Review every row. The plan contains at least 100 studies, includes every eligible diagnostic
   series for every selected study, and deterministically expands up to 240 studies when needed to
   cover every represented dimension value, including singleton/nonmaterial values, plus every
   material joint stratum. Before deciding, inspect the plan-bound private `review_context`:
   `organizer_plane`, `physical_plane`, `assigned_slot`, `retention_reasons`, the
   six-boolean `missing_series_mask`, and `sibling_series`. Every ordinal-ordered sibling record has
   exactly `series_ordinal`, `slot`, `terminal_state`, `model_eligible`, `retention_reasons`, and
   `quality_blocked_reasons`. The UI resolves every artifact only below the authenticated Run A slug
   root named by the review identity; a missing, duplicate, ambiguous, symlinked, or non-Run-A
   source fails closed.
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

   `N` is permitted only for `duplicate_missing_abnormal_handling`. At least one reviewed series
   must record `PASS` for every check before the all-nine exit gate can pass.

8. Continue until the UI emits `PRIVATE_REVIEW_COMPLETE`. Use **Quick Save** with output files only
   then; that first human Save Version must create the distinct review-session v1 containing only
   `completed_review_ledger.json` and at most one bounded log.

After review-session v1 reaches terminal completion, authenticate it before launching the
finalizer:

```bash
validate_workflow_stage review
```

The plan covers represented acquisition plane, fluid sensitivity, fat suppression, manufacturer,
scanner model, field strength, domain/site cluster, resolution, slice count/spacing, obliquity,
multi-series slots, missing slots, quality extremes, duplicate/candidate groups, DICOM edges, and
eligible remediated decode cases. The plan and finalizer verify artifact presence and hashes as a
separate invariant; visual decisions cannot substitute for a missing artifact.

Any `BLOCK`, incomplete row, missing eligible series, missing represented material stratum,
identity change, artifact mismatch, or suspected systematic ordering/orientation/laterality error
prevents Chunk 5 exit. If review-session v1 is saved incomplete or with the wrong identity, stop and
create a new immutable candidate identity; never use v2 to overwrite the evidence.

## 5. Run the private finalizer and authenticate the whole workflow

Only after the completed review-session v1 exists, push the prebuilt finalizer once:

```bash
push_kernel_v1 review-finalizer-kernel
```

The finalizer reconstructs the exact plan from Run A, rehashes every private artifact, requires the
same full review identity and row set, validates every fixed decision, and derives both the detailed
private completion and the two allowlisted release-safe outputs. It never accepts a locally
fabricated aggregate attestation. The private completion holds the review identity, cohort hash,
reviewed-study and eligible-series counts, represented strata, nine-check counts, block count,
completion timestamp, ledger hash, and rows. Exact reviewed-study, eligible-series, decision, and
stratum counts remain private. The release-safe `human_review_summary.json` contains only k20 count
tokens, one
`at_or_above_threshold` token for every reviewed-study count from 220 through 240, version labels,
fixed `all_material_covered`, coverage/completion booleans, nine canonical PASS/BLOCK results,
identity-bound status, and block status. The separate `final_performance_report.json` combines the
already-sanitized Run A
measurements with authenticated determinism and human-review completion and repeats the identical
validated review tokens; it does not release exact review counts, private manifests, exact
throughput counts, or private identity hashes.

After finalizer v1 reaches terminal completion, authenticate the complete exit chain:

```bash
validate_workflow_stage final
```

The only ordered stage values are `inputs`, `run-a`, `run-b`, `comparison`, `plan`, `ui`, `review`,
and `final`. Do not pass removed legacy version or attestation flags. The workflow validator derives
every private reference internally. For each stage before `final`, require exactly
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

The validator temporarily retrieves only allowlisted sanitized aggregates: each run's
`sanitized_summary.json`, `benchmark.md`, and `sanitized_artifact_inventory.json`; comparator
`sanitized_determinism.json`; and finalizer `human_review_summary.json` plus
`final_performance_report.json`. It never downloads the full manifests, cohort, ledger, private
completion, identifiers, paths, images, pixels, or case artifacts. Temporary copies are deleted.
Do not broaden the allowlists or manually retrieve private files.

A schema-valid aggregate with any block remains an exit failure. Chunk 5 passes only when the
authenticated workflow, exact Run A/Run B comparison, real performance evidence, at-least-100/all-
represented-strata/all-eligible-series review, all nine checks, zero blocks, disclosure controls,
governance, final staged engineering gates, commit, push, and clean-tree gates all pass. Stop before
Chunk 6.
