# Chunk 4R Assistant Public-Baseline Audit

Captured: 2026-08-31

## Scope

This branch contains a portable, network-free screening contract and a current public-candidate
snapshot for the RSNA Knee Abnormality Detection competition. It does **not** contain model weights,
competition data, report text, predictions, private Kaggle output, or a competition submission.

The branch is intentionally based on the remotely available
`checkpoint/chunks-1-4-remediated` branch. It is designed to be cherry-picked onto the newer local
Chunk 4R worktree after that worktree is pushed or made available.

## Controlling claim boundary

Every leaderboard value below is a **third-party, source-reported public leaderboard score**. The
project has not independently submitted or achieved any of these scores.

A public notebook is not an approved project baseline until all indispensable inference files are:

1. pinned to one immutable saved version;
2. publicly and equally accessible;
3. checksum-bound;
4. covered by actionable competition-use terms;
5. safe to load;
6. reproduced on the public example studies;
7. matched by a clean-room implementation;
8. packaged for dynamic, offline hidden-test inference.

## Current public landscape

| Candidate | Immutable evidence presently available | Source-reported public score | Source runtime | Current screening result |
|---|---|---:|---:|---|
| Historical DINOsaur V4 V14 | Version 14, script version `345082720`, source/output hashes from the prior project audit | 0.936 | 170.59 s | Blocked: indispensable asset terms, exact bindings, and checkpoint safety unresolved |
| Current DINOsaur V4 | Current slug has changed materially; best score still points to historical V14 | Current page approximately 0.922; best 0.936 V14 | Approximately 3m21s on current output page | Not immutable until the exact current script version is pulled |
| DINOsaur V3 | Kaggle currently reports best 0.921 at V18, with newer source versions present | 0.921 | Version-specific runtime not yet pinned | Blocked pending exact V18 source/output and transitive inputs |
| Tony Li DINO–RadImageNet rank ensemble | Public V1, Apache-2.0 notebook, one named reproduction-assets dataset plus official DINOv2 | 0.920 | 102.9 s | **Highest-priority fallback to pin with authenticated Kaggle CLI** |
| André Tony rank ensemble V2 | Saved V2, script version `343083003`, visible three-row public output | 0.920 | 108 s | Same asset-license and binding work as Tony source |
| Super Ensemble 0920 V1 | Public score and large multi-input graph visible | 0.920 | 119 s | Lower priority because dependency surface is much larger |
| V39 reproduction V1 | Saved V1; title says 0.916 but Kaggle page score controls | 0.909 | 98.2 s | Below preferred 0.90 fallback threshold only marginally; assets still unresolved |
| Historical bend-to-DINOv3 V13 | Page reports historical best 0.935, current versions differ | 0.935 | Not pinned | Secondary path: many inputs and DINOv3 access/license complexity |

## Key findings

### 1. Tony Li's rank ensemble is the best first executable target

It is not the highest source score, but it has the smallest visible inference surface among the
public candidates at or above 0.920:

- one public competition input;
- one reproduction-assets dataset;
- one official DINOv2 model;
- an Apache-2.0 notebook;
- a source runtime near 103 seconds.

It remains blocked until the authenticated Kaggle environment resolves the exact dataset
owner/slug/version, custom terms, file inventory, source hash, output hash, dynamic test behavior,
and checkpoint safety.

### 2. The historical 0.936 DINOsaur result remains an audit reference

Historical DINOsaur V4 V14 should not be deleted or rewritten. It is still the strongest pinned
source-reported score in the project evidence. It is not safe to run until its required assets and
loading paths clear the inference gate.

### 3. Training and inference reproducibility must remain separate

A candidate can be classified:

- `INFERENCE_AND_TRAINING_REPRODUCIBLE`;
- `INFERENCE_REPRODUCIBLE_TRAINING_OPAQUE`;
- `INFERENCE_BLOCKED`;
- `SOURCE_UNAVAILABLE`.

`INFERENCE_REPRODUCIBLE_TRAINING_OPAQUE` is sufficient only for a private inference candidate. It
does not authorize retraining, fine-tuning, or consuming opaque public weak labels.

### 4. Notebook license is not the asset license

An Apache-2.0 notebook does not automatically license its datasets, trained heads, caches, or
checkpoints. Each indispensable file requires its own terms and checksum.

### 5. Titles are not score evidence

The V39 notebook title contains “0.916,” while the current immutable V1 page reports 0.909. The
registry records the page score, not the title.

## Implemented safeguards

This branch adds:

- a typed candidate and asset contract;
- deterministic candidate selection;
- inference/training reproducibility separation;
- source-score claim boundaries;
- exact-version and SHA-256 gates;
- actionable-license gates;
- dynamic-test and no-report-access gates;
- static checkpoint archive/path/pickle preflight;
- a network-free registry screening script;
- synthetic tests for all major fail-closed decisions.

## Current machine-readable result

`configs/public_baseline/chunk4r_candidates.json` intentionally selects no candidate yet. The
registry is valid, but every candidate still has at least one evidence or safety blocker.

Run:

```bash
uv run python scripts/chunk4r_screen_candidates.py
```

Exit codes:

- `0`: at least one candidate clears every inference gate;
- `2`: registry is valid, but no candidate is currently eligible;
- other nonzero: malformed registry or implementation failure.

## Public source pages used for this snapshot

- https://www.kaggle.com/code/romantamrazov/rsna-knee-dinosaur-v4
- https://www.kaggle.com/code/romantamrazov/rsna-knee-dinosaur-v3
- https://www.kaggle.com/code/tonylica/rsna-knee-dino-radimagenet-rank-ensemble
- https://www.kaggle.com/code/andreluizpedroso/rsna-knee-tony-rank-ensemble?scriptVersionId=343083003
- https://www.kaggle.com/code/amanatar/rsna-knee-super-ensemble-0920
- https://www.kaggle.com/code/ieshanmeghani/rsna-knee-v39-public-0-916-reproduction
- https://www.kaggle.com/code/nishantkharga/bend-the-knee-to-dinov3-ensembled-nk
- https://github.com/facebookresearch/dinov2

## Decision

Do not attempt another 58-study frozen-feature model.

First use the authenticated Kaggle CLI to pin and inspect Tony Li's rank ensemble and its exact
reproduction-assets dataset. If that candidate fails inference licensing or safety, move down the
screened list rather than weakening the gate.
