# AUDIT-0002 — Manifest remediation rerun contract

Status: **private execution, schema-v2 output validation, guarded history/ref cleanup, and final
staged local gates passed**. The private PR and hosted CI remain open, so the cumulative branch is
not merge-ready.

## Before run

- Audit ID: `audit-0002-manifest-remediation`.
- Predecessor: `audit-0001-manifest` (preserved, then marked superseded in its private registry
  `result_json`; never overwritten).
- Hypothesis: the v2 manifest can reconcile every accessible object while assigning every DICOM
  exception an explained deterministic disposition, separating hard leakage groups from soft
  candidates, and releasing only aggregates that resist arithmetic reconstruction across all five
  approved artifacts.
- Primary change: remediation audit only—DICOM disposition completeness, hard/soft grouping
  semantics, and joint disclosure control.
- Frozen controls: refreshed canonical contract snapshot `2026-08-08T220312Z`, official competition
  inputs only, `manifest-v2`, `protected-groups-v2`, `official-labels-v1`, unchanged stable
  audit-key lineage, and preprocessing/folds/models unassigned.
- Seeds: retain the deterministic manifest/QA seeds from the predecessor unless the private package
  contract records and justifies a change before launch.
- Compute estimate: one private Kaggle CPU run with the existing bounded self and outer deadlines;
  no accelerator, training, inference, prediction, or submission.
- Expected information gain: determine whether every source object has a defensible terminal state,
  whether accepted hard components remain distinct from weak candidate chains, and whether a useful
  aggregate release can satisfy the stronger privacy contract.

## Promotion criterion

Pass only if all of the following are true:

1. Study, series, file, report, and label-source levels reconcile, with valid foreign keys and a
   terminal state for every accessible object.
2. Every DICOM exception has a private root-cause category and deterministic disposition; no case
   is unexplained and no valid recoverable object is unsupported.
3. Exact duplicate and confirmed repeat evidence remains connected in hard components; soft and
   overflow-candidate relationships remain separate with complete private edge provenance.
4. Representative paths for the largest hard and soft components are inspected privately; no
   identifier or path is exported.
5. The output controller generates exactly the five approved canonical artifacts and the local
   validator rejects addition, subtraction, percentage, nested, prior/current, and cross-file
   reconstruction attempts.
6. Code, config, contract, schema, dependency, bundle, artifact, data-manifest, label, fold, and
   preprocessing provenance are recorded; repeat execution is deterministic under the approved
   contract.
7. The private registry receives a new audit row and new artifact rows; the predecessor is marked
   superseded without losing provenance.

## Kill criterion

Stop and fail closed on contract drift; an unexpected input/bundle inventory; any raw identifier,
path, report, pixel, patient metadata, private table/hash/reference, or session detail in an export
or log; an unreconciled object; an unexplained DICOM case; fabricated geometry; filename-ordering
substitution; silent skip; a valid recoverable unsupported object; hard/soft semantic mixing;
missing edge provenance; output-schema drift; reconstruction of a below-threshold count; or
non-deterministic artifact content.

## After run — validated evidence

- Execution status: `COMPLETE`.
- Execution ID: `manifest-audit-6fce3af8ba1c`.
- Scope: `full`, `train-plus-example-test`; the visible test interface is example-only and the
  hidden test is not evaluable.
- Runtime: 10,092 seconds (2 hours, 48 minutes, 12 seconds) on CPU; below the recorded 21,600-second
  self-deadline and 23,400-second outer deadline.
- Versions: `manifest-v2`, `protected-groups-v2`, `official-labels-v1`; preprocessing and folds
  remain `unassigned`.
- Disclosure: schema version 2, `joint-complementary-k20-v1`, minimum export cell 20, fixed-width
  intervals, no published percentages, and no raw identifiers, reports, pixels, patient metadata,
  or private tables.

### Pinned code, bundle, and provenance

| Item | SHA-256 / identifier |
|---|---|
| Code commit | `6fce3af8ba1cc85dacd6a29326f999bf5f5227ed` |
| Bundle (`rsna-knee-manifest-audit-bundle-v1`) | `27de1fcc413b2d79d913f0f59c698f969b7ddc19d86f77bcc99aba0f4025dd28` |
| Competition config | `c41ce0dad5c24cd9a051facda3a4907c6f5bf5a0dc045df9eb9e380cbfe79006` |
| Competition contract | `08e1c29635132dcfff78140e3a0f12723127cf8737954016c3adda192513813d` |
| Manifest schema | `4fa5806db32a767e2dcf7d6d7a97fb2caf1f3c07704c3a837a433642e05dee15` |
| `uv.lock` | `d707ff22384bcbda10bc5ccd5780690794f5c5b3d1c92860a2a63eaa87caf759` |
| Run config | `430d3615854771c8752e86cca740d49bcd843f32c05db33bfc4dae9c70f19a90` |
| Runtime requirements | `a2169549a930776b7c4581c2cc1b9be4bb7e8765ecb3c9efcb21cf2a301c6b44` |
| Linux wheel set | `f5811d2526d041af85a463cb954ca1e01573ca2e969cd209896a1f036aa1b743` |
| Project wheel | `f871cca758bf65dbf099c1f16e81626ed2cb431e1865923a69bdb9f4f857758b` |

The runtime decoder set was `pylibjpeg==2.1.0`, `pylibjpeg-libjpeg==2.4.0`, and
`pylibjpeg-openjpeg==2.5.0` under the private-audit-only approval in `EXTERNAL_ASSETS.md`.

### Approved release artifact hashes

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `sanitized_summary.json` | 4,972 | `7b03911d34f0a7b9dc2349e010aa86b5cc05bc6d8ce35e3a0d345438b625d859` |
| `data_audit.md` | 1,769 | `d88e0633d6c9ec4358779dd47446eac13b6e024ff27dbded80007935166986e8` |
| `leakage_audit.md` | 1,931 | `50c1abc7dc29d9deca5d9479f03ea8fa4506b62b9f4a81933aa9b9a504337ba9` |
| `domain_shift_audit.md` | 1,555 | `7e506a4d93a0cac0a783a0edd07a45ab0ef074f91606a254d8997193af914fbe` |
| `sanitized_artifact_inventory.json` | 1,603 | `61fd9533308d16b65563d9695b6c62c557513b04f1c7d1612b72f1e5229d87ca` |

### DICOM disposition outcome

- `coverage.complete: true`, `five_levels_reconciled: true`, `all_files_terminal: true`, and
  `all_series_terminal: true`.
- Decode failures, quarantined files, and quarantined series each use only the approved
  `below_threshold_nonzero` token. `files_unreadable: zero`, `series_fallback: zero`, and
  `path_header_mismatch: zero`.
- `unexplained_dicom_issues: zero` and `dicom_issue_dispositions_complete: true`. Under the v2
  producer gate, any unresolved blocker or valid recoverable unsupported object would have made
  completion false. Root-cause, resolution, path, and case-level evidence stayed private.

### Hard and soft grouping outcome

- Hard evidence: `exact_file_groups: zero`, `exact_pixel_groups: range_1220_1239`,
  `exact_series_groups: range_20_39`, `exact_study_groups: below_threshold_nonzero`, and
  `protected_components: range_4400_4419`.
- Soft/review evidence: `candidate_edges: range_8800_8819`,
  `near_series_candidate_space_overflow: true`, and
  `near_slice_study_pair_space_overflow: true`. The private representation preserved candidate
  edges, overflow provenance, component distributions, edge attribution, and representative
  transitive paths separately from hard fold-protection IDs.
- Closure: `protected_graph_closed: true`, `cross_split_components: zero`, and
  `near_slice_unresolved_study_pairs: zero`.
- Structural interpretation only: `folds_assigned: false`, `fold_feasibility: not_assessed`, and
  `future_fold_crossings: zero`. The last token is not a fold-feasibility or leakage-free-validation
  claim.

### Decision and remaining gates

The audit-specific promotion criteria passed: the five levels reconciled, DICOM dispositions were
complete with zero unexplained issues, hard and soft structures validated separately, the five
approved outputs passed the joint disclosure validator, foreign keys were valid, private artifacts
were complete, and `audit-0001-manifest` was preserved and superseded.

Guarded history/ref cleanup passed: the old feature ref was replaced by the clean history, the
temporary unsafe branch was deleted, and no active local or origin ref reaches the unsafe commit.
The complete staged candidate passed locked reinstall/package, pytest 139/139, Ruff lint/format,
strict mypy, all pre-commit hooks, exact staged secret/baseline comparison, the sensitive-file
guard, pip-audit with no vulnerabilities, contract/config/submission checks, remote and local full
output validators, and four canonical byte comparisons.

The checkpoint itself remains **in progress**. The exact locally checked commit must be pushed to
one private cumulative pull request, and GitHub-hosted CI must be green. No merge, preprocessing,
fold, weak-label, model, prediction, ensemble, or submission action is authorized.
