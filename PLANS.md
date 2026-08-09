# Plans

This file records the continuous sequence of work. A historical chunk can have useful deliverables
while still requiring correction before cumulative merge. “Complete” below never means merged.

## Chunk 1 - private repository operating system

Historical status: implementation delivered on a private feature branch; cumulative validation is
being repeated in Checkpoint 1.

Objective: establish an installable, dependency-locked, synthetic-tested private-repository
operating system without competition-data access or model training.

Delivered evidence:

- Private source-of-truth repository, `uv` lock, typed package and CLI, configuration and SQLite
  registry schemas, synthetic fixtures, CI workflow, governance files, and project-scoped skills.
- No competition data, report, checkpoint, prediction, model, or credential was intentionally
  committed.

Correction/gate outcome:

- The prior final secret-pass claim was made before the final tracked file set was included. Exact
  reviewed baseline entries and a detection regression now exist locally. The complete staged-tree,
  cumulative-diff, history, and generated-artifact checks passed. Hosted CI passed on cumulative
  release candidate `cc050a2`; later commits remain subject to the same gate.

## Chunk 2 - live competition contract

Historical status: contract captured and refreshed; no competition-data analysis or model work.

Objective: create one authoritative, machine-readable operating contract for the exact competition
before any data or modeling decision.

Delivered evidence:

- `docs/competition_contract/contract.yaml` is canonical and is loaded through
  `configs/competition.yaml` rather than duplicating targets or constraints in code.
- Rules, metric, schema, dates, notebook/runtime and submission limits, data interface, external
  assets, team/sharing constraints, licenses, and contradictions are recorded with conservative
  defaults.
- The latest live refresh at `2026-08-08T22:03:12Z` found no material payload or source-fingerprint
  drift. Official Kaggle CLI/API was the approved fallback because the configured official Kaggle
  MCP was not exposed.

Open gates:

- Identity verification remains incomplete. Degenerate-label scorer behavior, exact retained DICOM
  tag names, and exact accelerator availability remain unresolved and fail closed.

## Chunk 3 - evidence-ranked research portfolio

Historical status: research portfolio delivered on a private feature branch; not merged.

Objective: rank label, validation, image, ensemble, contrarian, and efficiency hypotheses without
competition-data processing or model training.

Delivered evidence:

- Current official competition context, timestamped public landscape, structured source matrix,
  exactly 35 hypotheses, and five hard rejects.
- External assets remain blocked until provenance, version, identifier, license, checksum,
  equal-access, offline packaging, rule justification, and approval are complete.

Exit retained: no data processing, model, submission, notebook fork, public action, or external
asset use occurred in the chunk.

## Chunk 4 - full-data manifest and structural grouping audit

Current evidence: `audit-0001-manifest` is superseded. Its successor,
`audit-0002-manifest-remediation`, completed a full private CPU run in 10,092 seconds against
`manifest-v2` / `protected-groups-v2`. Downstream fold and model work remains blocked by the
remaining Checkpoint 1 release gates.

What remains valid as historical provenance:

- A private CPU audit executed with no preprocessing, folds, model, prediction, ensemble, or
  submission.
- Private artifacts were kept within the Kaggle boundary, and only an aggregate release set was
  retrieved.
- The run exposed real DICOM exception, bounded-candidate, disclosure, and governance-control gaps
  that now define Checkpoint 1 remediation.

Validated successor evidence:

- Complete five-level reconciliation, foreign-key integrity, and terminal file/series accounting.
- `unexplained_dicom_issues: zero` and `dicom_issue_dispositions_complete: true`; private case
  evidence was not exported.
- Hard protected components remained separate from soft candidate/overflow evidence, with
  `protected_graph_closed: true`; no folds were assigned and feasibility was not assessed.
- Exactly five approved outputs passed the schema-v2 joint disclosure boundary. Only the four
  approved release artifacts are being persisted with governance; the inventory hash remains in
  the experiment provenance record.

Why the original exit assessment is withdrawn:

- The then-current sanitizer independently suppressed fields and allowed arithmetic reconstruction
  through related totals and complements.
- Weak/candidate/overflow relationships were allowed to affect the same protected components as
  hard duplicate/repeat evidence, so the v1 zero-crossing statement was not fold-feasibility proof.
- Nonzero DICOM exception cases had not received complete private root-cause and deterministic
  disposition review.
- The reported final secret gate did not cover the eventual committed file set, and remote CI had
  not validated the cumulative branch.

## Checkpoint 1 - Chunks 1-4 remediation

Status: private remediation execution, guarded history/ref cleanup, and complete staged-candidate
local gates passed on `checkpoint/chunks-1-4-remediated`. Private pull request #10 is open and
unmerged; hosted CI passed on release candidate `cc050a2`, and any successor must pass it again.

Objective: make Chunks 1-4 truthful, privacy-safe, reproducible, privately revalidated, and remotely
reviewable. Do not start Chunk 5.

Completed and validated so far:

- Narrow exact secret-baseline correction plus a regression that must still detect realistic token
  replacement.
- One central joint-disclosure boundary and output schema with arithmetic-reconstruction tests.
- `manifest-v2` / `protected-groups-v2` separation of hard protected components from soft
  candidates; no fold identifiers are created.
- Live contract refresh with no material drift.
- Full private `audit-0002-manifest-remediation` execution at commit
  `6fce3af8ba1cc85dacd6a29326f999bf5f5227ed`, completed in 10,092 seconds.
- Schema-v2 sanitized evidence with complete coverage, zero unexplained DICOM issues, complete
  dispositions, private hard/soft provenance checks, and five approved artifact hashes.
- `audit-0001-manifest` preserved as historical provenance and superseded for all downstream use.
- Guarded history/ref cleanup passed: the old feature ref now points to the clean history, the
  temporary unsafe branch is deleted, and no active local or origin ref reaches the unsafe commit.
- Final complete staged-candidate gates passed: locked install/package, 139/139 pytest, Ruff
  lint/format, strict mypy, pre-commit, secret/baseline comparison, sensitive-file guard,
  vulnerability audit, contract/config/submission checks, full-output validation, and four
  canonical byte comparisons.
- Private pull request #10 is open and unmerged; its hosted `quality` workflow passed on release
  candidate `cc050a21ab3386b501170d224ef57ef990a3753b`.

Pending exit evidence:

1. Require green GitHub-hosted CI for the exact final head of private pull request #10. The pull
   request must remain unmerged.

## Recommended next chunk

None until this checkpoint passes. After it passes, propose exactly one next chunk for explicit
review; do not infer authority to preprocess data, create folds, weak-label, train, predict,
ensemble, or submit.
