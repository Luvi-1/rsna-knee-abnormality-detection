# Data Card

Status: Checkpoint 1 remediation in progress. The historical `manifest-v1` audit is preserved for
provenance but superseded for downstream use; `manifest-v2` has not completed a private full-data
rerun.

## Source, scope, and license

- Competition: RSNA Knee Abnormality Detection.
- Canonical live inventory: 569.76 GB, 819,640 files, including 819,635 DICOM files and five CSV
  metadata files. These are official competition-level inventory facts, not released private audit
  counts.
- Types: DICOM and CSV under the competition rules and RSNA MIRA Dataset Research Use Agreement.
- Use is research/competition only. Redistribution, download-link sharing, re-identification,
  unauthorized access, clinical use, and unapproved public or commercial derived-artifact use are
  prohibited or fail closed pending written clarification.
- Full-data inspection must run only inside private Kaggle. Raw identifiers, paths, reports, pixels,
  patient-level metadata, private tables, row-level/private hashes, logs, and case-level DICOM
  findings must remain inside that boundary.

## Historical audit correction

The private `audit-0001-manifest` exercised the five intended levels: study, series, slice/file,
report, and label source. It cannot be used as current data-readiness evidence because:

- its v1 sanitized release independently suppressed related fields and allowed arithmetic
  reconstruction through published complements;
- `protected-groups-v1` mixed hard duplicate/repeat evidence with soft or overflow-candidate
  similarities;
- nonzero DICOM decode/quarantine findings had not received complete case-level root-cause and
  deterministic disposition review; and
- the final secret and remote-CI gates did not cover a complete cumulative release candidate.

The previous aggregate files and narrative counts are therefore superseded. This card does not
repeat their private result values. Their non-sensitive code, bundle, configuration, and artifact
hash provenance remains in `docs/experiments/audit-0001-manifest.md`.

## Remediation schema

- Manifest: `manifest-v2` (implemented locally; private rerun pending).
- Hard grouping: `protected-groups-v2` (implemented locally; private rerun pending).
- Labels: `official-labels-v1`; missing labels remain unknown, not negative.
- Preprocessing and folds: `unassigned`.

The v2 private schema retains reconciled entity tables, DICOM issue and disposition evidence, hard
protected components, separate soft candidate components, edge provenance, and private component
summaries. The public release boundary receives aggregates only and applies one joint disclosure
policy across every JSON and Markdown representation.

## DICOM integrity status

DICOM readiness is **not established**. Every historical decode/quarantine case must be reopened
inside private Kaggle and assigned an evidence-backed root-cause category and deterministic
disposition. The remediation audit may pass with unavoidable, documented source corruption, but it
must have:

- no unexplained case;
- no valid recoverable object left unsupported;
- no fabricated geometry or silent filename ordering;
- no silently skipped file; and
- complete object reconciliation and terminal disposition accounting.

No case identifier, exact rare count, or case-level path may be published.

## Duplicate and leakage structure

Hard evidence (for example, accepted exact duplicate or confirmed repeat-patient relations) may
make studies indivisible. Weak near similarities, report/template candidates, label-vector
similarities, and approximation/overflow candidates are kept as soft review/stress evidence and do
not automatically merge hard components. Every edge and its provenance remain private.

The representation is only a precursor to later fold construction. No fold exists, and no fold
feasibility, class balance, subgroup support, or leakage-free validation claim is currently
supported.

## Shift limitations

The visible test interface is example-only and low support, test reports are unavailable, and the
hidden scoring distribution is not evaluable. No hidden-test domain-shift claim is supported. Any
future safe aggregate comparison must meet the joint disclosure policy and minimum-support gates.

## Public schema

- `train.csv`: `StudyInstanceUID`, multilingual `Report`, and 12 partially populated binary targets.
- `train_series.csv`: study/series IDs, fluid sensitivity, fat suppression, and anatomical plane.
- `train_series/<StudyInstanceUID>/<SeriesInstanceUID>/<SOPInstanceUID>.dcm`: one slice per file.
- `PatientSex` is absent from the CSV interface. No DICOM tag may become a model dependency until it
  is verified on a scoring-equivalent test interface.

## Next evidence required

A new private `audit-0002-manifest-remediation` must reconcile every accessible object, validate
all DICOM dispositions and hard/soft grouping semantics, and generate five canonical sanitized
artifacts that pass joint arithmetic-disclosure validation. Until then, preprocessing, folds, weak
labels, training, prediction, ensembles, and submission remain blocked.
