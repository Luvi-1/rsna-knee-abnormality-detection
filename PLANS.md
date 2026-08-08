# Plans

## Chunk 1 - private repository operating system

Status: complete on the Chunk 1 feature-branch commit

Objective: turn the verified governance baseline into an installable, tested, private-repository operating system without accessing competition data or training a model.

Evidence required:

- Private remote visibility verified without exposing its URL.
- Reproducible `uv` environment, package, experiment configuration, SQLite registry, CLI, synthetic fixtures, and CI.
- Ten validated project-scoped skills discoverable from a fresh Codex session.
- Package install, Ruff, mypy, pytest, pre-commit, secret, sensitive-file, and vulnerability checks pass.
- No competition data, submission, team action, rule acceptance, public release, or model training.

Exit gate:

- All required checks pass from the locked environment.
- Git tree contains no blocked data, credentials, private outputs, or oversized artifacts.
- Feature branch is committed and pushed without merge.

## Recommended next chunk

Run the privacy-safe Kaggle metadata audit needed to design leakage-resistant groups and version the first data manifest. Do not train a model.
