# Checkpoint 1 governance and final-gate correction

- Incident: Chunk 4 governance reported that the final secret scan passed and that suppressed rare
  values could not be inferred. Neither claim held for the clean committed branch and its complete
  aggregate release.
- Date detected: 2026-08-08.
- Impact: the cumulative Chunks 1-4 branch was not merge-ready. The old aggregate release and
  grouping interpretation cannot support downstream data or validation work. No actual credential,
  token, raw DICOM, report, prediction, or patient-level record was found in the reviewed findings.

## Detection

- Running the secret hook against the clean reported commit flagged five high-entropy values in a
  newly tracked aggregate summary.
- Manual review classified all five as repository provenance, configuration, or content hashes,
  not secrets or private identifiers.
- Joint arithmetic review found that the same release exposed complementary values from which a
  below-threshold count could be reconstructed.
- Governance review found that remote GitHub Actions had not validated the cumulative branch and
  that local implementation, private execution, remote execution, merge-ready, and merged states
  had been conflated.

## Root cause

The final validation sequence ran before every intended generated/documentation file was tracked or
staged. Later files were included in the commit without re-running the entire final gate set. The
sanitizer also reasoned field-by-field instead of treating the aggregate release as a system of
related equations.

## Corrective and preventive controls

1. Add only exact reviewed detect-secrets baseline fingerprints; keep high-entropy and provider
   detectors enabled; prove a realistic token replacement is still rejected.
2. Scan the complete tracked/staged tree, cumulative diff against `main`, newly generated sanitized
   artifacts, and relevant history.
3. Apply joint complementary disclosure centrally and validate the canonical output set against
   cross-field and cross-file reconstruction attempts.
4. Mark `audit-0001-manifest` and its release superseded rather than deleting the non-sensitive
   provenance record.
5. Stage **every** intended file before the final install, lint, format, type, test, pre-commit,
   secret, sensitive-file, dependency, contract, disclosure, manifest, DICOM, and grouping gates.
6. Treat any later file change as invalidating final local results.
7. Push the exact checked commit and require green GitHub-hosted CI before “merge-ready” can be used.
8. Keep the cumulative pull request unmerged until explicit human approval.

## Current state

The narrow baseline, detection regression, centralized disclosure controller, and governance
corrections are implemented locally. The clean-history rewrite, regenerated private artifacts,
final staged-tree gates, cumulative private pull request, and green remote CI are pending. This
postmortem must be updated from actual evidence after those gates run; it must not be used as proof
that they already passed.
