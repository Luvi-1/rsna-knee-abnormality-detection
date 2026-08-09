# Chunk 4 manifest-audit recovery postmortem

- Incident/audit: `audit-0001-manifest` recovery, bounded-candidate hardening, and later checkpoint
  correction.
- Date: 2026-08-08.
- Impact: several private CPU attempts ended before a full aggregate was produced. A later run
  completed, but its release validator, protected-group semantics, and DICOM disposition evidence
  were insufficient for promotion. Preprocessing, folds, weak labels, training, predictions,
  ensembles, and submission remained blocked.
- Detection: terminal Kaggle status plus a scrubbed fixed-vocabulary failure record detected the
  execution failures. Checkpoint review later detected the disclosure equation, hard/soft semantic
  mixing, incomplete DICOM case dispositions, and premature final-gate claim.

## Execution-recovery evidence

- The earliest full attempt ended after about 192 minutes with a generic runner failure whose root
  cause remains unknown.
- A 50,000-file smoke launch initially found its bundle missing during private dataset propagation;
  after a readiness/inventory gate, the retry completed in 398 seconds.
- Later full runs ended after about 156 minutes on series/report candidate-space overflow and after
  about 181 minutes on near-slice study-pair overflow.
- The final v1 run completed in 11,453 seconds. Its five outputs passed the **then-current**
  field-level validator; this is not a claim that they pass the replacement joint-disclosure
  validator.
- The successor `audit-0002-manifest-remediation` completed a full private CPU run in 10,092
  seconds at code commit `6fce3af8ba1cc85dacd6a29326f999bf5f5227ed`. Its five approved schema-v2
  outputs passed the replacement validator; pinned bundle, provenance, and artifact hashes are in
  `docs/experiments/audit-0002-manifest-remediation.md`.

## Root cause and contributing factors

- The identified execution failures materialized threshold-complete candidate pairs beyond their
  bounded evidence spaces. A capped partial pair list would have made later leakage controls
  unsound. The separate smoke failure was a dataset-readiness race. The earliest generic failure is
  not attributed to either known cause.
- Full-data cardinality was much larger than bounded smoke evidence, the original launch gate did
  not verify exact remote bundle inventory, and the recovery path initially lacked fixed,
  privacy-safe phase/code detail.
- The v1 disclosure design treated fields independently. It did not model equations across totals,
  complements, percentages, nested records, or multiple rendered files.
- The v1 grouping design used conservative transitive closure without preserving a semantic
  boundary between accepted hard evidence and weak/approximate/overflow candidates.
- The DICOM release summarized nonzero exception categories but did not require every private case
  to have an explained root cause and deterministic disposition.

## Corrective action

- Require private dataset readiness plus an exact bundle inventory before launch and validate one
  scrubbed failure record against the local bundle root of trust.
- Keep the runtime self-deadline and outer deadline explicit.
- Make one central joint-disclosure controller the sole release boundary; generate every JSON and
  Markdown output canonically from it; adversarially test addition, subtraction, percentages,
  nesting, prior/current values, and cross-file combinations.
- Replace `protected-groups-v1` with hard-only `protected-groups-v2` components and separate private
  soft-candidate components, retaining every edge and provenance for review.
- Require an explained, deterministic DICOM disposition for every private exception and zero valid
  recoverable unsupported objects.
- Preserve this audit as superseded provenance and execute a new, separately registered private
  remediation audit rather than overwriting it.

These audit-specific corrective actions were exercised successfully by
`audit-0002-manifest-remediation`: five-level reconciliation and terminal accounting were complete;
`unexplained_dicom_issues: zero`; `dicom_issue_dispositions_complete: true`; and hard protected
components remained separate from soft candidate/overflow evidence with
`protected_graph_closed: true`. Private case details, component paths, identifiers, and counts were
not exported.

## Privacy and validation correction

No raw DICOM pixel, radiology report, patient-level metadata table, private manifest, or prediction
artifact was intentionally persisted to Git. However, the prior statement that the sanitized result
was privacy-valid was wrong: a rare value could be reconstructed arithmetically. The affected
release artifacts are superseded, their unsafe count narrative is not reproduced here, and the
branch history must be rebuilt so the unsafe result commit is not reachable.

The correct validation statement is: v1 passed only the validator and secret-check file set that
existed at the time and is superseded. The v2 private audit, sanitized-output validator, guarded
history/ref cleanup, and complete staged-tree local gates passed; GitHub-hosted CI remains pending.

## Remaining action

Guarded cleanup verified that no active local or origin ref reaches the unsafe historical commit,
and the complete staged candidate passed every final local gate. Obtain green remote CI on an
unmerged cumulative pull request. No fold, model, prediction, ensemble, or submission work may
begin from this postmortem alone.

- Owner: Codex.
- Historical code commit: `75792aad08a3685d0c9ce92b5cab90307bf1336c`.
- Historical audit: `audit-0001-manifest` (superseded).
- Successor code commit: `6fce3af8ba1cc85dacd6a29326f999bf5f5227ed`.
- Successor audit: `audit-0002-manifest-remediation` (private execution complete; checkpoint gates
  pending).
