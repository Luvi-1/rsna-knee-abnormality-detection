# Label Card

Version: `official-labels-v1`

## Targets

`ACL`, `MCL`, `Medial Meniscus`, `Lateral Meniscus`, `Medial OA`, `Lateral OA`, `PF OA`,
`Effusion`, `Synovitis`, `Baker's`, `Contusion`, `Fracture`.

## Validated audit coverage

- Source: organizer-provided official label cells only, revalidated by the completed private
  `audit-0002-manifest-remediation`.
- Schema-v2 reports `official_only: true`, `non_official_sources: zero`, and `conflict_cells: zero`.
- The validated joint-disclosure tokens are `official_cells: range_52880_52899`,
  `positive_cells: range_240_259`, `negative_cells: range_440_459`, and
  `unknown_cells: range_52180_52199`. These tokens must not be converted into exact counts or
  percentages.
- Exact schema-v1 cell-state counts remain intentionally unrepublished because that release is
  superseded.
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

`official-labels-v1` is reconciled in `manifest-v2`, but it is not yet training-ready. No folds
exist, final staged local gates passed, the private PR/hosted CI gates remain open, and most target
cells remain unknown under the approved disclosure token. Weak labels remain blocked until manual
report validation, per-label error analysis, leakage review, and a new versioned label manifest
pass their own gates.
