# T137 Targetwise Specialist — Assistant Portable Handoff

## Purpose

This branch contains network-free support code for the next OA / Fluid / Bone specialist round.
It does **not** contain the newest local T133–T136 history, competition predictions, checkpoints,
DICOM data, reports, or Kaggle credentials.

The current verified project champion reported by the campaign is:

- submission `55976422`
- public score `0.929`
- candidate `T133_RAPTOR_V42`

The T136 window ablation scored `0.928` and should remain rejected. The window-count route is closed.

## Portable branch

Repository:

```text
Luvi-1/rsna-knee-abnormality-detection
```

Branch:

```text
codex/t137-assistant-portable
```

The branch was created from the older remote score-first support branch because the current local
competition history is not available on GitHub. **Do not merge this branch wholesale into the active
local campaign history.** Copy or cherry-pick only the files listed below after reviewing conflicts.

## Files to integrate

```text
configs/t137/portable_campaign.json
docs/t137/assistant_portable_handoff.md
docs/t137/github_public_lead_audit.md
scripts/t137_build_candidate.py
scripts/t137_freeze_round.py
src/rsna_knee/targetwise_specialist/__init__.py
src/rsna_knee/targetwise_specialist/blend.py
src/rsna_knee/targetwise_specialist/contracts.py
src/rsna_knee/targetwise_specialist/hidden_safety.py
src/rsna_knee/targetwise_specialist/io.py
src/rsna_knee/targetwise_specialist/rank.py
src/rsna_knee/targetwise_specialist/selection.py
tests/test_t137_hidden_safety.py
tests/test_t137_private_io.py
tests/test_t137_targetwise_specialist.py
```

## What is implemented

The portable package provides:

- exact 12-target and T137 family contracts;
- protected champion `55976422` / `0.929` assertions;
- deterministic average-tie normalized ranks;
- probability, logit, and rank blends;
- target/family-only swaps with champion fallback;
- prediction-table schema and identifier reconciliation;
- Pearson/Spearman/rank-disagreement diagnostics;
- duplicate-like ranking detection;
- transparent offline evidence ranking;
- dynamic hidden-size row reconciliation and bounded batch helpers;
- fail-closed malformed-series category handling and per-study usable-series coverage checks;
- candidate package identity checks for checkpoint, wheel, config, runner and metadata SHA-256;
- mandatory private/offline/dynamic-test/report-free/no-submission-call candidate gates;
- frozen round manifests whose reported SHA-256 covers the exact written bytes;
- exact placeholder-free authorization request generation;
- a family candidate builder that has no Kaggle or submission code.

None of these helpers sends data to Kaggle or makes a competition submission.

## Local integration

From the latest reviewed local branch that contains the real T133/T136 evidence:

```bash
git status --short
git fetch origin codex/t137-assistant-portable

git checkout origin/codex/t137-assistant-portable -- \
  configs/t137/portable_campaign.json \
  docs/t137/assistant_portable_handoff.md \
  docs/t137/github_public_lead_audit.md \
  scripts/t137_build_candidate.py \
  scripts/t137_freeze_round.py \
  src/rsna_knee/targetwise_specialist/__init__.py \
  src/rsna_knee/targetwise_specialist/blend.py \
  src/rsna_knee/targetwise_specialist/contracts.py \
  src/rsna_knee/targetwise_specialist/hidden_safety.py \
  src/rsna_knee/targetwise_specialist/io.py \
  src/rsna_knee/targetwise_specialist/rank.py \
  src/rsna_knee/targetwise_specialist/selection.py \
  tests/test_t137_hidden_safety.py \
  tests/test_t137_private_io.py \
  tests/test_t137_targetwise_specialist.py
```

Then run focused validation before committing:

```bash
uv run ruff check \
  scripts/t137_build_candidate.py \
  scripts/t137_freeze_round.py \
  src/rsna_knee/targetwise_specialist \
  tests/test_t137_hidden_safety.py \
  tests/test_t137_private_io.py \
  tests/test_t137_targetwise_specialist.py

uv run ruff format --check \
  scripts/t137_build_candidate.py \
  scripts/t137_freeze_round.py \
  src/rsna_knee/targetwise_specialist \
  tests/test_t137_hidden_safety.py \
  tests/test_t137_private_io.py \
  tests/test_t137_targetwise_specialist.py

uv run mypy src/rsna_knee/targetwise_specialist
uv run pytest \
  tests/test_t137_hidden_safety.py \
  tests/test_t137_private_io.py \
  tests/test_t137_targetwise_specialist.py -q
uv run python scripts/check_no_sensitive_files.py
git diff --cached --check
```

Run the repository-wide suite only after provisioning the pre-existing ignored fixtures required by
that local history. Do not weaken unrelated historical checks merely to make this portable patch pass.

## Building a private family candidate

The builder takes two exact 13-column prediction CSVs already produced in the private environment.
It reconciles row order by `StudyInstanceUID`, changes only one configured family, and writes a
private candidate plus aggregate diversity audit.

Example OA candidate:

```bash
uv run python scripts/t137_build_candidate.py \
  --champion private_outputs/t137/champion.csv \
  --challenger private_outputs/t137/efficientnetv2_l_480.csv \
  --family osteoarthritis \
  --champion-weight 0.75 \
  --output private_outputs/t137/OA_EFFNET_75_25.csv \
  --audit-output private_outputs/t137/OA_EFFNET_75_25.audit.json
```

Valid families are:

```text
osteoarthritis
fluid_inflammation
bone
```

The candidate and identifier-bearing inputs must remain private/ignored.

## Freezing a round without submitting

Prepare a private JSON file with a top-level `candidates` array. Every candidate must include the
exact package identity rather than placeholders. Example shape:

```json
{
  "candidates": [
    {
      "candidate_id": "T137_OA_EFFNET_75_25",
      "parent_submission_id": 55976422,
      "parent_score": 0.929,
      "changed_targets": ["Medial OA", "Lateral OA", "PF OA"],
      "blend_type": "normalized_rank",
      "model_ids": ["T133_RAPTOR_V42", "efficientnetv2_l_480"],
      "weights": [0.75, 0.25],
      "runtime_seconds": 12000.0,
      "expected_information_gain": 0.8,
      "checkpoint_sha256s": ["<64-lowercase-hex>"],
      "wheel_sha256": "<64-lowercase-hex>",
      "config_sha256": "<64-lowercase-hex>",
      "runner_sha256": "<64-lowercase-hex>",
      "metadata_sha256": "<64-lowercase-hex>",
      "privacy_pass": true,
      "offline": true,
      "dynamic_test": true,
      "report_free": true,
      "submission_api_absent": true
    }
  ]
}
```

The example uses placeholders only to document the schema. Replace every hash with a real value before
running the freezer; the contract rejects non-SHA values.

Then run:

```bash
uv run python scripts/t137_freeze_round.py \
  --round-id T137_TARGETWISE_SPECIALIST_001_PREPARED \
  --live-allowance <LIVE_INTEGER> \
  --candidates private_outputs/t137/candidates.json \
  --output private_outputs/t137/submission_round_manifest.json
```

The script:

1. fails when candidate count exceeds the live allowance;
2. fails when a candidate is not descended from submission `55976422` at score `0.929`;
3. fails on malformed weights, targets, runtime, hashes or package-safety flags;
4. writes canonical JSON bytes and computes SHA-256 over those exact file bytes;
5. prints an exact authorization sentence with no placeholders;
6. prints `authorization_present=false`;
7. contains no submission action.

A real Kaggle submission still requires separate explicit authorization in the active Kaggle-enabled
chat.

## GitHub public-lead research completed

`docs/t137/github_public_lead_audit.md` records two additional public-code findings:

- a report-free DINOv2-small baseline whose overall public LB is only `0.687`, but whose published
  max-vs-mean target deltas make Lateral OA, PF OA, Synovitis and Contusion possible low-priority
  diversity leads; its third-party licenses still require reauthentication;
- a source-reported `0.936` `evgendvorkin/rsna-baseline` route that explicitly loads the already
  provenance-blocked `raptor-knee-widedense` weights, so it remains closed under the project rules.

Neither source is promoted into a submission candidate.

## Recommended next local execution

1. Reauthenticate the locally reproduced EfficientNetV2-L 480 and CoAtNet 384 assets.
2. Produce private prediction vectors on the approved diversity cohort.
3. Measure per-target ranking disagreement against the `0.929` T133 champion.
4. Reject models with effectively duplicate rankings.
5. Build at most the highest-value OA / Fluid / Bone candidates.
6. Use the clean DINOv2 lead only if the first two controls fail and its complete asset terms pass.
7. Refresh the live submission allowance.
8. Freeze only the candidates allowed by that live count.
9. Run hidden-shape safety simulations in the real local campaign code.
10. Stop at `SUBMISSION_READY_AWAITING_AUTHORIZATION`.

## Claim boundary

The portable utilities do not establish target AUCs or leaderboard improvements. Prediction
correlation is diversity evidence only. Source metrics remain source metrics. The project reaches the
requested objective only when an authorized project submission returns a public score of at least
`0.950`.
