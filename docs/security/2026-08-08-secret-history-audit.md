# Secret and private-artifact history audit

Date: 2026-08-08

Scope: the pre-audit working tree, the exact secret baseline, and the historical detector findings
from the superseded schema-v1 manifest summary.

No credential value, private URL, report, patient or study identifier, medical pixel, or private
artifact identifier is reproduced in this record.

During a later read-only remote-state check, the Git client printed the private repository locator
to transient terminal output. No credential, token, medical data, or write capability was exposed,
and the locator was not saved in the repository or copied into this record. This was nevertheless a
handling-control exception: subsequent checks must compare sanitized fields and print fixed status
tokens only.

## Current state

The four tracked schema-v1 aggregate artifacts have been removed from the working tree pending an
authoritative schema-v2 private rerun:

- `docs/manifest_summary.json`
- `docs/data_audit.md`
- `docs/leakage_audit.md`
- `docs/domain_shift_audit.md`

Their removal prevents the obsolete output from being part of the intended replacement tree, but
does not remove its blob from the existing feature-branch reference or Git history. A clean
replacement/squash and guarded remote-reference update are still pending. No commit, history
rewrite, push, or remote deletion was performed by this audit task.

`.secrets.baseline` contains only the ten exact, previously reviewed `Hex High Entropy String`
entries for `docs/competition_contract/contract.yaml`. It contains no approval for the deleted
manifest summary or any other path. Detector classes, thresholds, filters, and file scope remain
unchanged.

## Historical five-candidate classification

The superseded manifest summary produced five high-entropy findings. They were classified without
printing their values:

| Historical manifest field | Verification performed | Classification |
|---|---|---|
| `competition_config_sha256` | Recomputed from the tracked competition pointer | Non-secret content provenance |
| `competition_contract_sha256` | Recomputed from the canonical tracked contract | Non-secret content provenance |
| `git_commit` | Resolved as an existing ancestor commit object | Repository code provenance |
| `manifest_schema_sha256` | Recomputed from the tracked manifest schema | Non-secret content provenance |
| `uv_lock_sha256` | Recomputed from the tracked dependency lock | Non-secret content provenance |

None was a credential, authentication token, signed or private URL, session identifier,
patient/study identifier, or private Kaggle artifact identifier. Those classifications remain
audit evidence; they are not baseline approvals. Because the schema-v1 artifact is being removed
from the clean replacement history, adding exemptions for it would be both obsolete and broader
than necessary.

## Security invariant and regression

Only the exact current contract fingerprints may be approved before the rerun. The focused test:

1. scans the contract using baseline settings copied into an isolated temporary checkout;
2. requires the newly detected candidate records to equal the ten baseline records exactly;
3. requires the baseline result map to contain only the contract path;
4. confirms the real hook accepts the reviewed contract; and
5. confirms a runtime-constructed, unbaselined GitHub-token shape is rejected without echoing its
   value.

The scan settings file and hook baseline are temporary copies. No validation command is allowed to
refresh or mutate the shared repository baseline.

## Post-rerun approval gate

The authoritative schema-v2 rerun is expected to generate new provenance and canonical artifact
hashes. No future hash is pre-approved. After the intended v2 files exist, every high-entropy
candidate in each intended tracked summary or inventory must be independently matched to its exact
source artifact or code revision. Only then may snapshot-specific exact entries be added to the
baseline. The complete staged tree, cumulative diff, generated sanitized outputs, and corrected
history must be rescanned after those approvals; any later file change invalidates the result.

## Separate aggregate-disclosure history gate

The old summary's five high-entropy values were non-secrets, but the same historical artifact has a
separate privacy defect: exact complementary aggregates can reconstruct a below-threshold count.
Working-tree deletion cannot cure a reachable historical disclosure. Before a merge-ready claim,
the coordinating workflow must create the clean cumulative replacement, update only the intended
private feature reference with a guarded lease, and verify that the schema-v1 aggregate blob is not
reachable from that active reference. This audit does not authorize or perform that rewrite.

## Focused validation evidence

- `pytest -q tests/test_secret_scanning.py`: two tests passed.
- Ruff check and format check for `tests/test_secret_scanning.py`: passed.
- mypy for `tests/test_secret_scanning.py`: passed with no issues.
- Byte comparison against the committed baseline plus structural JSON assertions: passed; the
  baseline is unchanged and contains exactly one result path with ten contract records.
- Non-mutating `detect-secrets scan --no-verify` of this audit record and its regression test:
  passed with zero candidates.
- Read-only path/history check: all four legacy artifacts are absent from the working tree and
  still present at the current `HEAD`, proving that guarded history replacement remains necessary.

These are focused development checks, not the final release gates. The complete staged-tree,
cumulative-diff, corrected-history, generated-v2-artifact, pre-commit, and GitHub CI checks remain
pending and must run against the final unchanged candidate.

Current credential/secret-baseline status: exact contract-only policy is locally regression-tested.

Current aggregate-history status: blocked pending the guarded clean-history replacement and the
authoritative schema-v2 private rerun.
