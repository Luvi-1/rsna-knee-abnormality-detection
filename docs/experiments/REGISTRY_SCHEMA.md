# Experiment Registry

SQLite schema version 2 is defined in `src/rsna_knee/registry.py`.

- `experiments` stores the pre-run experiment contract, version references, code version, and configuration hash.
- `audit_runs` stores non-model data, contract, privacy, and packaging audits without pretending
  they are training experiments. Audit history is append-only at the workflow level: a rerun gets a
  new `audit_id`; the predecessor is preserved and its `result_json` records `superseded_by` plus a
  non-sensitive reason. The successor records `predecessor_audit_id` in its own `result_json`.
- `metrics` stores macro and per-label values with optional confidence intervals.
- `experiment_results` stores runtime, cost, manual validation, domain shift, failure modes, prediction correlations, hypothesis support, and disposition.
- `artifacts` stores URI, checksum, size, code/config provenance, and data/label/fold/preprocessing
  versions linked to either an experiment or an audit run.

Checkpoint 1 convention: keep `audit-0001-manifest` and its artifact rows for provenance, mark it
superseded in `result_json`, and insert `audit-0002-manifest-remediation` plus new artifact rows. Do
not overwrite old hashes, runtime, or status to make the successor appear to be the original run.
Registry files and any artifact URIs remain private and must not be copied into governance docs.

Registry files are private artifacts and ignored by Git. Initialize one with:

```bash
uv run python scripts/init_registry.py artifacts/experiments.sqlite3
```
