# AUDIT-0002 — Manifest remediation rerun contract

Status: planned; not yet completed. This document records the private audit contract before compute
and must be updated only from validated run evidence.

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

## After run — pending evidence

- Execution status and timestamps: pending.
- Code commit, bundle hash, config/contract/schema/lock hashes: pending.
- Actual runtime and cost: pending.
- DICOM root-cause and safe disposition summary: pending; aggregate-only.
- Hard-versus-soft structural comparison: pending; disclosure-safe aggregate only.
- Five sanitized artifact hashes and schema versions: pending.
- Registry integrity, predecessor supersession, and artifact foreign keys: pending.
- Local final staged-tree gates: pending.
- GitHub-hosted CI: pending.
- Decision: pending; downstream work remains blocked until every promotion criterion and checkpoint
  exit gate passes.
