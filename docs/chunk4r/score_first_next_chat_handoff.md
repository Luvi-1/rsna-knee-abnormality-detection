# Score-First 0.93 — Authenticated Kaggle Handoff

## Portable branch

- Repository: `Luvi-1/rsna-knee-abnormality-detection`
- Branch: `codex/score-first-093-campaign`
- Parent portable branch: `codex/chunk4r-assistant-public-audit`

This branch is portable support code. It is not based on the newest local Chunk 5A commit because that local history has not been pushed to GitHub.

Do not merge this branch directly into the latest local project history. Copy or cherry-pick its score-first files onto the latest local branch after reviewing conflicts.

## Files to integrate

```text
configs/public_baseline/score_first_093.json
docs/chunk4r/score_first_093_campaign.md
docs/chunk4r/score_first_next_chat_handoff.md
scripts/chunk4r_score_first.py
src/rsna_knee/public_repro/score_first.py
tests/test_score_first_campaign.py
```

## Local integration

From the newest local branch containing commit:

```text
ff61fefc0423759ef9bd726dcb415b9c03f9cb80
```

or any reviewed successor:

```bash
git status --short
git fetch origin codex/score-first-093-campaign

git checkout origin/codex/score-first-093-campaign -- \
  configs/public_baseline/score_first_093.json \
  docs/chunk4r/score_first_093_campaign.md \
  docs/chunk4r/score_first_next_chat_handoff.md \
  scripts/chunk4r_score_first.py \
  src/rsna_knee/public_repro/score_first.py \
  tests/test_score_first_campaign.py
```

Then run:

```bash
git diff --cached --check
uv run ruff check \
  scripts/chunk4r_score_first.py \
  src/rsna_knee/public_repro/score_first.py \
  tests/test_score_first_campaign.py
uv run ruff format --check \
  scripts/chunk4r_score_first.py \
  src/rsna_knee/public_repro/score_first.py \
  tests/test_score_first_campaign.py
uv run mypy src/rsna_knee/public_repro
uv run pytest tests/test_public_repro_contracts.py tests/test_score_first_campaign.py -q
```

Run the full repository gates only after provisioning the already documented ignored P1/certificate fixtures. Do not rewrite unrelated historical files merely to hide pre-existing failures.

## Authenticated discovery

```bash
uv run python scripts/chunk4r_score_first.py \
  --output private_outputs/chunk4r/score_first_scan.json
```

To pull the latest source and public output for the configured slugs:

```bash
uv run python scripts/chunk4r_score_first.py \
  --pull-known \
  --output private_outputs/chunk4r/score_first_scan.json
```

Important: the standard Kaggle CLI pulls the latest source. It does not prove that an older scored version such as V36 was retrieved.

## Primary target: Take Care Of Your Knee V36

Owner/slug:

```text
anhadmahajan06/rsna-knee-take-care-of-your-knee
```

Required evidence:

1. Exact V36 script version ID.
2. Exact V36 source bytes and SHA-256.
3. Exact V36 public output and SHA-256.
4. Exact input owner/slug/version for every mounted dataset/model.
5. Actual license or custom terms for every indispensable input.
6. Static checkpoint inventory and safe-loading result.
7. Confirmation that the notebook does not read test reports.
8. Confirmation that test study count is dynamic.
9. Confirmation that no competition submission API call is present.
10. Source-reported score recorded only as third-party public leaderboard evidence.

Current-page visible inputs that must be bound exactly:

```text
Images for Competition Notebook
Knee MRI - Max-Span Dense Corpus
knee mri fold weights
Knee MRI model weights: twelve findings
```

## Secondary target: Raptor CoAtNet V1

Owner/slug:

```text
hdhsjdjd/rsna-knee-raptor-coatnet
```

Required evidence is the same as above. Its source-reported public score is 0.933, but the public page reports 17 inputs; all indispensable nodes must be resolved.

## Fallback: single-model 0.924 candidate

Owner/slug:

```text
dreaddevelopment/knee-mri-twelve-findings-from-a-single-model
```

Use this when the 0.936 and 0.933 candidates remain blocked. Its smaller visible dependency surface makes it useful as a reproducible control or ensemble component.

## Compatibility reproduction

After one candidate clears the inference gate:

1. Copy the exact source into a private reproduction workspace.
2. Remove only submission calls, runtime networking, and credential access.
3. Do not alter preprocessing, model weights, ensemble order, rank transforms, clipping, or target blending.
4. Freeze the comparison tolerance before execution.
5. Run a private offline Kaggle kernel on the three public example studies.
6. Compare IDs, columns, target order, maximum absolute error, mean absolute error, and per-target rank correlation with the pinned public output.
7. Preserve complete failure artifacts when the output does not match.

## Clean-room implementation

Only after compatibility reproduction matches:

- implement the exact inference contract in importable project modules;
- require numerical agreement with the compatibility run;
- dynamically discover hidden test studies;
- verify every asset checksum before loading;
- access no report field at inference;
- make no network request;
- include no competition submission API call.

## Submission boundary

The campaign may prepare `submission.csv`, but it must not submit it.

A real submission requires a separate explicit instruction immediately before the action. Once authorized, make one submission, record the returned public score, and stop. Do not burn multiple daily submissions automatically.

## Ready-to-paste instruction for the next chat

```text
Continue the score-first RSNA Knee campaign.

Latest local project commit before this portable work:
ff61fefc0423759ef9bd726dcb415b9c03f9cb80

Portable GitHub branch:
codex/score-first-093-campaign

First integrate only the six score-first files listed in:
docs/chunk4r/score_first_next_chat_handoff.md

Do not merge the portable branch history wholesale because it is based on an older remote checkpoint.

Then:
1. Run the focused score-first and public-reproduction tests.
2. Use the authenticated official Kaggle CLI.
3. Run scripts/chunk4r_score_first.py.
4. Pin Take Care Of Your Knee V36 exactly.
5. Resolve every public input, license, file, version, and checksum.
6. If V36 clears the inference gate, run private public-example compatibility reproduction.
7. Otherwise audit Raptor CoAtNet V1.
8. Otherwise reproduce the single-model 0.924 candidate as a control.
9. Build the clean-room equivalent after an exact match.
10. Prepare a dynamic offline submission package.

Do not restart report-label work.
Do not use rejected project labels.
Do not use private or unlicensed inputs.
Do not claim source-reported scores as project scores.
Do not make a competition submission without separate explicit approval.
```
