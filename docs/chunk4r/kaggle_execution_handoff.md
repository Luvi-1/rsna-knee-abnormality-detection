# Chunk 4R Kaggle Execution Handoff

This file lists the work that still requires an authenticated local/Kaggle session. The public
research contract and fail-closed screening code are already present in this branch.

## Before starting

Cherry-pick this branch's commit onto the latest local Chunk 4R branch. Do not merge the old remote
checkpoint history over the newer local project history.

Verify:

```bash
git status --short
uv sync --locked
uv run pytest tests/test_public_repro_contracts.py -q
uv run python scripts/chunk4r_screen_candidates.py
```

The screening command is expected to exit `2` until exact Kaggle evidence is added.

## Priority 1: pin Tony Li's V1 notebook

Use the official authenticated Kaggle CLI. Do not paste credentials into source or shell history.

```bash
mkdir -p private_outputs/chunk4r/tony-rank-v1/source
mkdir -p private_outputs/chunk4r/tony-rank-v1/output

kaggle kernels pull \
  tonylica/rsna-knee-dino-radimagenet-rank-ensemble \
  -p private_outputs/chunk4r/tony-rank-v1/source \
  -m

kaggle kernels output \
  tonylica/rsna-knee-dino-radimagenet-rank-ensemble \
  -p private_outputs/chunk4r/tony-rank-v1/output
```

Then capture through official metadata/CLI:

- exact notebook version;
- script version ID;
- source SHA-256;
- metadata SHA-256;
- output SHA-256;
- score and score type;
- runtime and accelerator;
- every input owner/slug/version;
- notebook license;
- copied-from lineage.

Do not rely on the live page title or latest version alone.

## Priority 2: bind the reproduction-assets dataset

The notebook page exposes the title:

`RSNA Knee Bend the Knee 0.917 reproduction assets`

Resolve the exact owner/slug/version from pulled notebook metadata.

Then:

```bash
kaggle datasets metadata <owner>/<slug> \
  -p private_outputs/chunk4r/tony-rank-v1/dataset-metadata

kaggle datasets files <owner>/<slug>
```

Download only after confirming expected size and storage:

```bash
kaggle datasets download <owner>/<slug> \
  -p private_outputs/chunk4r/tony-rank-v1/dataset \
  --unzip
```

Record:

- exact version;
- actual custom license text, not only the Kaggle category;
- LICENSE/README hashes;
- file inventory;
- file SHA-256 values;
- whether competition inference is permitted;
- redistribution/conversion restrictions;
- exact files referenced by notebook code.

If no actionable terms exist, keep the candidate blocked.

## Priority 3: inspect checkpoints safely

Never begin with unrestricted `torch.load(..., weights_only=False)`.

For every checkpoint:

1. Record size and SHA-256.
2. Run the static preflight utility.
3. Inspect ZIP members and pickle opcodes.
4. Try `torch.load(..., weights_only=True)` only in a disposable, network-disabled environment.
5. If custom classes are required, inspect their exact source first.
6. Remove Kaggle credentials from the sandbox.
7. Convert tensor-only contents to `safetensors` only when the original terms permit it.
8. Keep converted files private.
9. Compare original and converted inference numerically.

Example static preflight:

```python
from pathlib import Path
from rsna_knee.public_repro.checkpoint_security import inspect_checkpoint_archive

result = inspect_checkpoint_archive(Path("private_outputs/chunk4r/weights/model.pt"))
print(result)
```

`requires_sandbox=False` means only that obvious archive and pickle risks were not found. It is not
a complete safety proof.

## Priority 4: update the candidate registry

Fill only verified values in:

```text
configs/public_baseline/chunk4r_candidates.json
```

A required asset must have:

- exact public resource;
- exact version;
- exact file binding;
- canonical SHA-256;
- actionable inference license;
- availability;
- safe-loading evidence.

Set `dynamic_test_discovery=true` only after reviewing or testing the code.

Run:

```bash
uv run python scripts/chunk4r_screen_candidates.py \
  --output private_outputs/chunk4r/screening-result.json
```

Do not edit the selection output manually.

## Priority 5: private compatibility run

After the registry selects a candidate:

- create only private Kaggle resources;
- disable internet;
- bind exact inputs;
- remove any submission API call;
- dynamically discover test studies;
- run on the three public examples;
- compare with the pinned public output using a tolerance frozen before viewing results.

Required evidence:

- exact and mean absolute probability difference;
- ID and target-order match;
- per-target rank correlation;
- runtime;
- peak CPU and GPU memory;
- output checksum;
- private visibility.

## Priority 6: clean-room implementation

Implement the same mathematical inference contract in the current project package. Require the
clean-room output to match the compatibility run within the same frozen tolerance.

Do not:

- use project-rejected Chunk 2 labels;
- train from opaque public labels;
- call gold-overridden predictions OOF;
- claim the public source score as a project score;
- submit to the competition.

## Exact completion boundary for the next chat

The next chat should receive:

```text
Repository:
Luvi-1/rsna-knee-abnormality-detection

Portable branch/commit:
<commit from codex/chunk4r-assistant-public-audit>

Latest local Chunk 4R branch:
<local branch>

Authenticated Kaggle evidence:
<private archive or exact paths>

Task:
Cherry-pick the portable audit commit, fill only checksum-verified registry fields,
run the candidate screen, execute the highest passing candidate privately, and stop
before competition submission.
```
