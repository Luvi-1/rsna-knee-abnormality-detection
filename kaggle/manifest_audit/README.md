# Private Kaggle manifest audit

This directory is the one-file Kaggle script wrapper for the full private data audit. Packaging is
local and reproducible; dataset creation and kernel push are separate human-approval gates. The
wrapper runs with internet, GPU, and TPU disabled, verifies every bundled byte, installs only the
verified Linux wheelhouse into `/tmp`, suppresses package output, and emits two fixed JSON events on
success. The wheelhouse pins `pylibjpeg`, `pylibjpeg-libjpeg`, and `pylibjpeg-openjpeg` for CPython
3.11/3.12 Linux; the runner fails before corpus enumeration unless JPEG Lossless SV1 and JPEG 2000
Lossless decoding are both available at the recorded versions. Audit execution stops at 21,600
seconds, retaining 1,800 seconds before the 23,400-second outer ceiling for validation and cleanup.

## Local package gate

Start from a clean commit. The packager refuses modified or untracked files, builds the project
wheel offline, exports only locked runtime dependencies, downloads/builds CPython 3.11 and 3.12
x86-64 Linux wheels, removes the upstream pydicom medical test tree plus every `.dcm`, `.dicom`, or
standard `DICM`-preamble member, regenerates that wheel's `RECORD`, rejects any medical payload in
every other wheel, rejects macOS/Windows/ARM wheels, and records every retained byte and SHA-256 in
the bundle manifest. Create one ignored, mode-0600 audit key and preserve it for every rebuild/rerun
of that immutable audit lineage; the packager never creates, prints, or places its material in
public configuration or sanitized output.

```bash
set -euo pipefail
bundle_root="artifacts/manifest-audit-bundle"
audit_key_path="artifacts/manifest-audit-key.bin"
test -f "$audit_key_path" || (umask 077; openssl rand -out "$audit_key_path" 32)
chmod 600 "$audit_key_path"
uv run python scripts/package_manifest_bundle.py \
  --repo-root . \
  --output "$bundle_root" \
  --audit-key-path "$audit_key_path" \
  --owner "$KAGGLE_OWNER"

expected_commit="$(jq -er .code_commit "$bundle_root/dataset/run-config.json")"
expected_bundle="$(jq -er .bundle_sha256 "$bundle_root/dataset/run-config.json")"

authenticate_manifest_stage() {
  local stage="$1"
  local command=(uv run --locked --no-sync python -m scripts.authenticate_manifest_deployment \
    --run-config "$bundle_root/dataset/run-config.json" \
    --bundle-manifest "$bundle_root/dataset/bundle-manifest.json" \
    --dataset-metadata "$bundle_root/dataset/dataset-metadata.json" \
    --kernel-metadata "$bundle_root/kernel/kernel-metadata.json" \
    --expected-commit "$expected_commit" \
    --expected-bundle "$expected_bundle" \
    --stage "$stage")
  if [ "$stage" = local ]; then
    "${command[@]}"
  else
    test -n "${token_value:-}" || return 1
    KAGGLE_API_TOKEN="$token_value" "${command[@]}"
  fi
}

authenticate_manifest_stage local

jq -e '
  .is_private == true and
  .enable_internet == false and
  .enable_gpu == false and
  .enable_tpu == false and
  .kernel_type == "script" and
  .code_file == "run.py" and
  (.competition_sources == ["rsna-knee-abnormality-detection"]) and
  (.dataset_sources | length == 1)
' "$bundle_root/kernel/kernel-metadata.json" >/dev/null

jq -e '
  (.licenses == [{"name":"other"}]) and
  (.description | startswith("PRIVATE TEAM-ONLY"))
' "$bundle_root/dataset/dataset-metadata.json" >/dev/null
```

The success line contains only the bundle hash. The `local` authentication stage reopens the actual
assembled project and dependency wheels, verifies their Linux tags and medical-payload boundary,
and checks every retained pydicom member against its regenerated `RECORD`; it needs no network token.
Private dataset and kernel references remain inside their local metadata files and should not be
printed, pasted into chat, or committed. `artifacts/` is ignored by Git.

## Approval-gated create and run

Do not run these commands until the human explicitly approves the corresponding remote write. Do
not add `--public`; Kaggle dataset creation is private by default.

```bash
set -euo pipefail
token_value="$(launchctl getenv KAGGLE_API_TOKEN)"
test -n "$token_value"
audit_transport_root="$(umask 077; mktemp -d)"
chmod 700 "$audit_transport_root"

(umask 077; KAGGLE_API_TOKEN="$token_value" kaggle datasets create \
  --path "$bundle_root/dataset" \
  --dir-mode skip \
  --quiet >"$audit_transport_root/dataset-create.log" 2>&1)

authenticate_manifest_stage inputs

(umask 077; KAGGLE_API_TOKEN="$token_value" kaggle kernels push \
  --path "$bundle_root/kernel" \
  --timeout 23400 >"$audit_transport_root/kernel-push.log" 2>&1)

authenticate_manifest_stage kernel
```

Do not push the kernel until the `inputs` stage prints its fixed PASS token. It requires a private,
ready dataset whose current version is exactly 1; exact names, sizes, downloaded hashes, and
before/after snapshots must match the verified local bundle. A successful create response can
precede bundle availability on the notebook mount. The immediate `kernel` stage authenticates
remote version 1, private/offline metadata, exact code hash, and the dataset/competition source
graph without requiring a terminal status. It prints no private reference.

The create and push transports are captured only in fresh mode-0600 files below the mode-0700
audit root. Never print, paste, or commit those files; rely only on the fixed authentication
lines for acceptance.

Never run `kaggle config view`, print the token, print its length, or place it in a command-line
argument. The metadata pins one private dataset source plus the official competition source. The
runner rejects zero or multiple bundle manifests, any hash drift, a different script body, an
unsupported Python minor, an incomplete wheel set, or a missing competition mount.

## Monitor without exposing references

Load the private reference into a shell variable without printing it. The fixed-output status stage
authenticates remote version 1 and emits only
`manifest_deployment_status=PENDING|RUNNING|COMPLETE|ERROR`; Kaggle exposes no reliable aggregate
progress percentage here. Never push another version while version 1 is running.

```bash
set -euo pipefail
kernel_ref="$(jq -r .id "$bundle_root/kernel/kernel-metadata.json")"

authenticate_manifest_stage status
```

Allow each status request to complete or time out. Keep exactly one request in flight. Only after a
timeout or transport failure, issue at most one identical, non-overlapping read-only retry. If that
retry fails, record a monitoring transport issue rather than a job failure and keep all downstream
work blocked.

Only after the fixed status is `COMPLETE`, authenticate and validate the exact version-1 listing:

```bash
set -euo pipefail
authenticate_manifest_stage complete
listing_file="$(umask 077; mktemp)"
KAGGLE_API_TOKEN="$token_value" kaggle kernels files \
  "$kernel_ref/1" \
  --page-size 200 \
  --format json >"$listing_file" 2>"$audit_transport_root/kernel-files.log"

uv run python scripts/validate_manifest_output.py \
  --run-config "$bundle_root/dataset/run-config.json" \
  --bundle-manifest "$bundle_root/dataset/bundle-manifest.json" \
  --expected-commit "$expected_commit" \
  --expected-bundle "$expected_bundle" \
  --remote-listing "$listing_file"
authenticate_manifest_stage complete
```

The two `complete` checks bracket the version-1 listing. Each requires two agreeing API/code/source
checks, two terminal COMPLETE checks, the exact paginated output inventory, unchanged dataset
snapshots, and an exact content-hash download. A transport failure is not a run failure; retry only
with the established bounded, non-overlapping policy.

The remote-list validator permits the six named private artifacts only while they remain on Kaggle:

- `private_manifest.sqlite3` (8 GiB self-cap)
- `private_duplicate_groups.csv` and `private_preliminary_group_keys.csv` (256 MiB each)
- `private_qa_samples.csv` (64 MiB)
- `private_artifact_inventory.json` (1 MiB)
- `audit_key.bin` (exactly 32 bytes)

All live under `audit-output/`. Unknown names, missing required files, duplicates, incomplete
pagination, or a total above the 9 GiB self-cap fail closed. The validator reads names and sizes
only; it never opens or downloads private artifacts.

Kaggle's current kernel-files response exposes an opaque positive identifier in its `size` field,
not byte length. In that response mode, the validator checks the exact output-name set while the
cryptographically pinned remote runner enforces the byte caps before declaring success. If the API
supplies `totalBytes` or `bytes`, the validator also enforces every per-file and total byte cap.

## Retrieve sanitized outputs only

Use a fresh temporary directory. Kaggle CLI may also write the session log even with a file filter;
the local validator therefore requires exactly one scrubbed log containing only the fixed start and
completion events.

```bash
set -euo pipefail
download_dir="$(mktemp -d)"
safe_pattern='^(audit-output/)?(sanitized_summary\.json|data_audit\.md|leakage_audit\.md|domain_shift_audit\.md|sanitized_artifact_inventory\.json)$'

authenticate_manifest_stage complete
KAGGLE_API_TOKEN="$token_value" kaggle kernels output \
  "$kernel_ref/1" \
  --path "$download_dir" \
  --file-pattern "$safe_pattern" \
  --quiet >"$audit_transport_root/safe-output.log" 2>&1

uv run python scripts/validate_manifest_output.py \
  --run-config "$bundle_root/dataset/run-config.json" \
  --bundle-manifest "$bundle_root/dataset/bundle-manifest.json" \
  --expected-commit "$expected_commit" \
  --expected-bundle "$expected_bundle" \
  --local-dir "$download_dir"

authenticate_manifest_stage complete
```

Local validation requires all five sanitized artifacts under `audit-output/`, exactly one successful
session log at the download root, a total below 4 MiB, exact provenance, the complete full-scan
schema, joint k=20 complementary disclosure, fixed-template Markdown, and an inventory whose sizes
and hashes match the three documents. Counts are released only as `zero`,
`below_threshold_nonzero`, `at_or_above_threshold`, or a fixed-width `range_L_U`; exact population
counts and percentages are rejected. The validator also rejects private filenames, symlinks, extra
directories/files, raw UID/report or pixel-shaped data, UUID/opaque hashes, paths/private URLs,
rare category strings, privacy canaries, and credential-shaped text without printing inspected
contents. Do not copy the six remote-only artifacts locally and never commit the session log.

Kaggle's kernel-files listing currently flattens output names while downloads may preserve the
`audit-output/` folder. The validator accepts either layout, but rejects a mixture. For a bounded
timing smoke only, pass `--allow-bounded-smoke`; never use that flag for the final full-data gate.

The sanitized shift section must account for exactly these 16 fixed feature names in both JSON and
`domain_shift_audit.md`: `patient_sex`, `scanner_manufacturer`, `scanner_model`,
`protocol_cluster`, `plane_availability`, `sequence_composition`, `report_language`,
`site_domain_cluster`, `series_description_vocabulary`, `patient_age_years`, `field_strength_t`,
`study_complexity_series_count`, `study_complexity_slice_count`,
`in_plane_resolution_area_mm2`, `slice_thickness_mm`, and `overall_missingness`. With the accessible
three-study example test set, the only permitted public values are
`suppressed_low_test_support`, except `report_language`, which must be
`not_evaluable_test_reports_unavailable`. Numeric effects, tiers, confidence intervals, raw category
names, and support counts stay in the private Kaggle artifacts. A future dataset with at least 20
train and test studies requires an explicit reviewed schema revision before any bounded numeric
effect may be exported.

The leakage summary likewise uses a fixed duplicate-evidence vocabulary: file, pixel, series,
study, raw/normalized/overlapping/union report pairs, near-slice groups and edges, raw-container
variation, altered metadata, near-series/report edges, candidate edges, label-copy candidates,
protected components, and structural crossing checks. Hard protected components use only accepted
hard evidence; report, perceptual, label-vector, and overflow candidates remain in private soft
review components. The document explicitly records `folds_assigned: false` and
`fold_feasibility: not_assessed`. No fold claim is made in this audit.

Every private file/series issue records a fixed root-cause category, scope impact, disposition,
resolution state, and policy version. Missing decoders, unsupported syntaxes, ambiguous decode
errors, and unclassified cases remain unresolved blockers; they cannot be converted into a passing
quarantine count. Public output exposes only the fixed taxonomy plus
`dicom_issue_dispositions_complete: true` and `unexplained_dicom_issues: zero`, never case-level
occurrence data.

Slice-to-study, series, and report candidate discovery each also expose a fixed overflow boolean, a
zero or at-least-20 candidate-pair lower bound, and a k=20-suppressed protective study-chain count.
This makes conservative component fallback visible without exporting fingerprints, identifiers,
report content, or direct pair evidence.

## Recovery

- If status is `PENDING` or `RUNNING`, wait; do not push again or create overlapping compute.
- If status is `ERROR`, retrieve only the session log with a no-match output filter, then validate it
  against the pinned bundle before reading the fixed phase and code:

  ```bash
  set -euo pipefail
  failure_dir="$(mktemp -d)"
  authenticate_manifest_stage kernel
  KAGGLE_API_TOKEN="$token_value" kaggle kernels output \
    "$kernel_ref/1" --path "$failure_dir" --file-pattern '^$' --quiet \
    >"$audit_transport_root/failure-output.log" 2>&1
  uv run python scripts/validate_manifest_output.py \
    --run-config "$bundle_root/dataset/run-config.json" \
    --bundle-manifest "$bundle_root/dataset/bundle-manifest.json" \
    --expected-commit "$expected_commit" \
    --expected-bundle "$expected_bundle" \
    --failure-log-dir "$failure_dir"
  authenticate_manifest_stage kernel
  ```

  A safe failure contains exactly the start event and one allowlisted failure event. The validator
  prints only fixed phase/code values; it rejects extra files, text, fields, or unsafe values.
- If bundle, wheel, script, policy, or provenance validation fails, make the smallest local fix,
  commit it, re-run all checks, and package a new immutable bundle. Never patch the uploaded dataset
  in place.
- If the Kaggle image moves outside Python 3.11/3.12 or no compatible locked wheel exists, stop and
  refresh the lock/bundle on a new reviewed commit.
- Preserve the clean commit, generated bundle directory, metadata, and bundle hash locally until the
  remote audit and retrieval checks pass. Preserve the mode-0600 audit key for deterministic reruns;
  losing or rotating it requires a new immutable bundle lineage. A Kaggle status alone is not proof
  of valid artifacts.
