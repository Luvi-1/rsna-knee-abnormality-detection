# OX Alpha Sprint Risk Register

## R-S1. Identifier-path transcript exposure

- Date: 2026-08-22.
- Description: Kaggle CLI files call printed identifier-bearing test-series paths into an internal
  transcript. No download, repo write, external transmission, user-facing output, or private-artifact
  creation occurred.
- Mitigation: further CLI file listing/download/pagination prohibited for this sprint;
  aggregate-only endpoints only.
- Status: Open; canary rotation is the active chain owner's responsibility before next private run.

## R-S2. Contract page fingerprints unverifiable via rendered HTML

- Date: 2026-08-22.
- Description: Rendered-page hashes differ from canonical extraction pipeline used for contract.yaml.
  Cannot distinguish real drift from extraction differences.
- Mitigation: page-level facts stay bound to the 2026-08-22T062926Z snapshot; stale until canonical refresh.
- Status: Open.

## R-S3. Sprint scope risk

- Date: 2026-08-22.
- Description: Seven workstreams is ambitious for autonomous execution quality.
- Mitigation: phase-gate each with tests before moving on; red-team at end.
- Status: Mitigated by phasing.
