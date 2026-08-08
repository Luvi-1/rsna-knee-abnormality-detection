---
name: dicom-integrity-auditor
description: Audit DICOM study, series, slice-ordering, geometry, pixel-decoding, and preprocessing integrity while preserving patient privacy. Use before preprocessing or training, after loader changes, when creating a data manifest, or when scan counts, geometry, duplicates, corruption, or ordering look suspicious.
---

# DICOM Integrity Auditor

## Trigger conditions

- Run before approving a DICOM manifest, preprocessing version, loader change, training dataset, or inference package.
- Run when slice order, orientation, spacing, dimensions, decoding, duplication, corruption, or study counts are uncertain.
- Run locally only on synthetic DICOM fixtures; run full-data audits inside the authorized Kaggle environment.

## Required inputs

- Provide the authorized data root or a synthetic fixture root.
- Provide the expected study/series organization and preprocessing contract.
- Provide a private output location for quarantined identifiers and a public-safe aggregate output location.
- Provide the code version and proposed data-manifest/preprocessing versions.

## Procedure

1. Enumerate files read-only and reconcile file, study, and series counts.
2. Parse headers defensively. Classify unreadable files, unsupported transfer syntaxes, multi-frame objects, and missing critical tags.
3. Group by study and series within the authorized environment. Never expose raw identifiers outside it.
4. Derive slice position from `ImagePositionPatient` projected onto the normal from `ImageOrientationPatient`. Use `InstanceNumber` only as a flagged fallback; never use filename order as evidence.
5. Check orientation consistency, position monotonicity, duplicate positions/SOP instances, spacing, dimensions, photometric interpretation, pixel representation, bit depth, rescale values, and decode success.
6. Quarantine ambiguous series. Emit only aggregate counts and hashed, non-reversible private references where needed.
7. Exercise the same ordering and preprocessing path with synthetic fixtures.

## Forbidden actions

- Do not modify source DICOMs, silently drop failures, silently impute geometry, or guess slice order.
- Do not re-identify patients or log names, dates, accession numbers, UIDs, free text, pixels, or raw metadata externally.
- Do not send DICOMs, reports, patient metadata, or private manifests to an LLM, GitHub, Hugging Face, W&B, or another external service.
- Do not commit competition manifests, quarantined identifiers, pixels, or derived private artifacts.

## Outputs

- Produce a versioned aggregate audit report with counts by integrity state and failure reason.
- Produce a private quarantine manifest inside the authorized environment when necessary.
- Produce a pass/block verdict for the data-manifest and preprocessing versions.

## Validation checks

- Confirm every discovered file and series reaches exactly one terminal integrity state.
- Confirm aggregate counts reconcile and ordering is deterministic across repeated runs.
- Confirm geometry-based ordering is monotonic or explicitly quarantined.
- Confirm synthetic tests cover shuffled filenames, reversed instance numbers, duplicate positions, missing tags, and corrupt input.
- Confirm outputs contain no direct identifiers, free text, pixels, credentials, or private URLs.

## Failure behavior

- Fail closed and quarantine any series with ambiguous ordering, inconsistent geometry, or decode failure.
- Block preprocessing and training when counts do not reconcile or synthetic checks fail.
- Report the failing invariant and safe remediation; never weaken the audit to force a pass.
