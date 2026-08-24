# Kaggle baseline model scaffold

This directory contains the Kaggle notebook framework for the 2.5D baseline.
It must run with internet disabled and use only pre-packaged model bundles.

## Structure

- The training notebook is notebooks/baseline_synthetic_smoke.ipynb (synthetic
  only; no private data).
- Model bundles are created by scripts/package_model_bundle.py and validated by
  scripts/validate_model_output.py before upload.

## Security requirements

- No credentials in any file here.
- No private competition data attached to any Kaggle dataset.
- No submission is launched from this directory; submission requires explicit
  human approval per AGENTS.md external-action gates.

## Offline operation checklist

1. Verify contract/schema identity against packaged manifest.
2. Validate asset SHA-256 hashes before loading weights.
3. Confirm prediction column order matches contract.yaml.
4. Verify all probability values are in [0,1].
5. Measure phase runtime to confirm inference ceiling compliance.
