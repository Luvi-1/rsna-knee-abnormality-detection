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
x86-64 Linux wheels, rejects macOS/Windows/ARM wheels, and records every byte and SHA-256 in the
bundle manifest. Create one ignored, mode-0600 audit key and preserve it for every rebuild/rerun of
that immutable audit lineage; the packager never creates, prints, or places its material in public
configuration or sanitized output.

```bash
bundle_root="artifacts/manifest-audit-bundle"
audit_key_path="artifacts/manifest-audit-key.bin"
test -f "$audit_key_path" || (umask 077; openssl rand -out "$audit_key_path" 32)
chmod 600 "$audit_key_path"
uv run python scripts/package_manifest_bundle.py \
  --repo-root . \
  --output "$bundle_root" \
  --audit-key-path "$audit_key_path" \
  --owner "$KAGGLE_OWNER"

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

The success line contains only the bundle hash. Private dataset and kernel references remain inside
their local metadata files and should not be printed, pasted into chat, or committed. `artifacts/`
is ignored by Git.

## Approval-gated create and run

Do not run these commands until the human explicitly approves the corresponding remote write. Do
not add `--public`; Kaggle dataset creation is private by default.

```bash
token_value="$(launchctl getenv KAGGLE_API_TOKEN)"
test -n "$token_value"

KAGGLE_API_TOKEN="$token_value" kaggle datasets create \
  --path "$bundle_root/dataset" \
  --dir-mode skip \
  --quiet

dataset_ref="$(jq -r .id "$bundle_root/dataset/dataset-metadata.json")"
dataset_status="$(mktemp)"
dataset_listing="$(mktemp)"
KAGGLE_API_TOKEN="$token_value" kaggle datasets status \
  "$dataset_ref" --format json >"$dataset_status"
KAGGLE_API_TOKEN="$token_value" kaggle datasets files \
  "$dataset_ref" --page-size 200 --format json >"$dataset_listing"

KAGGLE_API_TOKEN="$token_value" kaggle kernels push \
  --path "$bundle_root/kernel" \
  --timeout 23400
```

Do not push the kernel until the saved status is `ready` and the saved listing exactly matches every
local dataset file except `dataset-metadata.json`. A successful create response can precede bundle
availability on the notebook mount. Keep both responses local and mode 0600; do not print or paste
them because they contain the private dataset reference.

Never run `kaggle config view`, print the token, print its length, or place it in a command-line
argument. The metadata pins one private dataset source plus the official competition source. The
runner rejects zero or multiple bundle manifests, any hash drift, a different script body, an
unsupported Python minor, an incomplete wheel set, or a missing competition mount.

## Monitor without exposing references

Load the private reference into a shell variable and pass it directly to the CLI. Status is for the
latest version, so never push another version while one is running.

```bash
kernel_ref="$(jq -r .id "$bundle_root/kernel/kernel-metadata.json")"

KAGGLE_API_TOKEN="$token_value" kaggle kernels status "$kernel_ref"

listing_file="$(mktemp)"
KAGGLE_API_TOKEN="$token_value" kaggle kernels files \
  "$kernel_ref" \
  --page-size 200 \
  --format json >"$listing_file"

uv run python scripts/validate_manifest_output.py \
  --run-config "$bundle_root/dataset/run-config.json" \
  --bundle-manifest "$bundle_root/dataset/bundle-manifest.json" \
  --remote-listing "$listing_file"
```

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
download_dir="$(mktemp -d)"
safe_pattern='^(audit-output/)?(sanitized_summary\.json|data_audit\.md|leakage_audit\.md|domain_shift_audit\.md|sanitized_artifact_inventory\.json)$'

KAGGLE_API_TOKEN="$token_value" kaggle kernels output \
  "$kernel_ref" \
  --path "$download_dir" \
  --file-pattern "$safe_pattern" \
  --quiet

uv run python scripts/validate_manifest_output.py \
  --run-config "$bundle_root/dataset/run-config.json" \
  --bundle-manifest "$bundle_root/dataset/bundle-manifest.json" \
  --local-dir "$download_dir"
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

- If status is still running, wait; do not push again or create overlapping compute.
- If status fails, retrieve only the session log with a no-match output filter, then validate it
  against the pinned bundle before reading the fixed phase and code:

  ```bash
  failure_dir="$(mktemp -d)"
  KAGGLE_API_TOKEN="$token_value" kaggle kernels output \
    "$kernel_ref" --path "$failure_dir" --file-pattern '^$' --quiet
  uv run python scripts/validate_manifest_output.py \
    --run-config "$bundle_root/dataset/run-config.json" \
    --bundle-manifest "$bundle_root/dataset/bundle-manifest.json" \
    --failure-log-dir "$failure_dir"
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
