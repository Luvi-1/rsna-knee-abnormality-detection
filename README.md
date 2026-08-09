# RSNA Knee Competition Research

Private, synthetic-first tooling for a reproducible RSNA Knee Abnormality Detection campaign. No competition data belongs in this repository.

## Local setup

```bash
export UV_NO_EDITABLE=1
uv sync --locked
uv run rsna-knee audit --config configs/experiment.example.toml
uv run rsna-knee validate-submission synthetic_data/submission.csv \
  --contract-config configs/competition.yaml
uv run python -c \
  "from pathlib import Path; from rsna_knee.competition_contract import load_contract; load_contract(Path('docs/competition_contract/contract.yaml')); print('competition_contract_schema=valid')"
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv run pre-commit run --all-files
uv export --quiet --locked --all-groups --no-emit-project --output-file /tmp/rsna-knee-audit-requirements.txt
uv run pip-audit --strict --requirement /tmp/rsna-knee-audit-requirements.txt
```

Initialize a local, ignored experiment registry:

```bash
uv run python scripts/init_registry.py artifacts/experiments.sqlite3
```

Run one synthetic or manifest-resolved private series through the geometry-first DICOM pipeline:

```bash
uv run rsna-knee preprocess \
  --config configs/preprocessing.v1.json \
  --input-dir /path/to/one-series \
  --output-dir artifacts/preprocessed/one-series \
  --code-commit "$(git rev-parse HEAD)" \
  --source-manifest-version manifest-v2 \
  --benchmark
```

The input directory must contain only the exact regular files for one series. File extensions and
names are discovery-only; physical DICOM geometry controls ordering. Outputs are private and
ignored by Git.

## Kaggle execution

Full data and GPU execution stay inside private Kaggle sessions. See
[kaggle/README.md](kaggle/README.md) for model-work packaging and
[kaggle/dicom_qa/README.md](kaggle/dicom_qa/README.md) for the approval-gated Chunk 5 private QA,
benchmark, remote-validation, and human-review workflow. Do not download the full dataset to this
machine.

Distinct private Run A and Run B kernels process the complete authorized training set. A separate
comparator must prove the declared deterministic outputs equal before the private plan, safe UI
template, human review session, or finalizer can run. The plan, selected case/series rows, artifact
hashes, completed nine-check ledger, identifiers, and review identity remain entirely inside
Kaggle. The pinned finalizer rehashes every review artifact and consumes the completed private
session directly; only disclosure-validated aggregate outputs may return locally.

Before any consuming kernel is pushed, each uploaded private dataset input must be remotely
confirmed ready and private, and its complete saved file listing must exactly match the local
manifest. A missing size, extra file, changed byte, ambiguous page, or privacy mismatch fails
closed. Private resource references and URLs must stay in ignored local metadata and must never be
printed or committed.

## Competition contract

`docs/competition_contract/contract.yaml` is the canonical machine-readable source for submission
validation and future Kaggle packaging. It is JSON-compatible YAML 1.2, so no extra parser is
required. The local setup and CI command validate only its schema; they do not establish live
freshness. After a privacy-safe live refresh from authoritative sources, compare the independent,
aggregate-only candidate before work:

```bash
uv run python scripts/check_competition_contract.py /tmp/observed-contract.yaml
```

## Safety

Read `AGENTS.md` before work. Submissions, team changes, public releases, rule acceptance, merges, and unusually large compute require explicit human approval.
