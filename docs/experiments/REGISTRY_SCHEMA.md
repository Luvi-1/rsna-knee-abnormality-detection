# Experiment Registry

SQLite schema version 1 is defined in `src/rsna_knee/registry.py`.

- `experiments` stores the pre-run experiment contract, version references, code version, and configuration hash.
- `metrics` stores macro and per-label values with optional confidence intervals.
- `experiment_results` stores runtime, cost, manual validation, domain shift, failure modes, prediction correlations, hypothesis support, and disposition.
- `artifacts` stores URI, checksum, size, code/config provenance, and data/label/fold/preprocessing versions.

Registry files are private artifacts and ignored by Git. Initialize one with:

```bash
uv run python scripts/init_registry.py artifacts/experiments.sqlite3
```
