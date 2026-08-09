# RSNA Knee Competition Research

Private, synthetic-first tooling for a reproducible RSNA Knee Abnormality Detection campaign. No competition data belongs in this repository.

## Local setup

```bash
export UV_NO_EDITABLE=1
uv sync --locked
uv run rsna-knee audit --config configs/experiment.example.toml
uv run rsna-knee validate-submission synthetic_data/submission.csv \
  --contract-config configs/competition.yaml
uv run python scripts/check_competition_contract.py docs/competition_contract/contract.yaml
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

## Kaggle execution

Full data and GPU execution stay inside private Kaggle sessions. See [kaggle/README.md](kaggle/README.md) for the approval-gated packaging and run commands. Do not download the full dataset to this machine.

## Competition contract

`docs/competition_contract/contract.yaml` is the canonical machine-readable source for submission
validation and future Kaggle packaging. It is JSON-compatible YAML 1.2, so no extra parser is
required. After a privacy-safe live refresh, compare the aggregate-only candidate before work:

```bash
uv run python scripts/check_competition_contract.py /tmp/observed-contract.yaml
```

## Safety

Read `AGENTS.md` before work. Submissions, team changes, public releases, rule acceptance, merges, and unusually large compute require explicit human approval.
