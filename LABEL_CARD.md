# Label Card

Version: `official-labels-v1`

## Targets

`ACL`, `MCL`, `Medial Meniscus`, `Lateral Meniscus`, `Medial OA`, `Lateral OA`, `PF OA`,
`Effusion`, `Synovitis`, `Baker's`, `Contusion`, `Fracture`.

## Historical audit coverage

- Source: organizer-provided official label cells only, as recorded by the superseded
  `audit-0001-manifest`.
- The exact schema-v1 cell-state counts are intentionally not republished because that release is
  superseded and all audit population counts must pass the central joint disclosure boundary.
- Current schema-v2 count states are pending the authoritative private rerun and may appear only as
  validated disclosure tokens in the canonical v2 outputs.
- No missing cell was coerced to negative, and no report-derived or model-derived label entered this
  version.

## Policy

- Missing remains unknown.
- Official, report-derived, and model-derived labels remain separate, versioned sources.
- Report-derived labels are not expert ground truth.
- Every future weak-label rule must record language, assertion, negation, uncertainty, provenance,
  confidence, and validation evidence.
- No pseudo-label may come from a model trained on the same study.
- Accepted hard duplicate/repeat components must remain within one future fold. Soft
  report/template or similarity candidates remain separate review/stress evidence and cannot be
  used as fold identifiers without validated promotion to a hard rule.

## Promotion gate

`official-labels-v1` is not training-ready. The `manifest-v2` private rerun must re-establish label
reconciliation, complete every DICOM disposition, validate hard/soft grouping semantics, and pass
the joint disclosure release gate. Weak labels remain blocked until manual report validation,
per-label error analysis, leakage review, and a new versioned label manifest pass their own gates.
