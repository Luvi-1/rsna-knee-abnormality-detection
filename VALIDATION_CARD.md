# Validation Card

Hard-group version: `protected-groups-v2` implemented locally; private full-data recomputation
pending.

Fold version: `unassigned`; no folds exist.

## Competition metric contract

- Canonical source: `docs/competition_contract/contract.yaml` through
  `configs/competition.yaml`.
- Primary metric: unweighted mean of all 12 per-label ROC AUC values in canonical order.
- Degenerate-label behavior is unresolved. Local evaluation must require at least one positive and
  one negative for every target and fail closed otherwise.
- No threshold, transform, fold, label rule, calibration, or ensemble weight may be fit on
  validation rows.
- The live contract refreshed at `2026-08-08T22:03:12Z` with no material drift. Identity
  verification and the recorded unresolved fields still fail closed.

## Correction to historical grouping evidence

The historical `protected-groups-v1` audit is not current validation evidence. It allowed hard
duplicate/repeat relations and weak/approximate/overflow candidate relations to affect the same
components. Its reported zero future crossing was a property of an overclosed v1 graph, not proof
that folds were feasible, balanced, assigned, or leakage-free.

`protected-groups-v2` defines:

- **Hard protected components:** accepted exact duplicate and confirmed repeat relations that later
  folds must keep indivisible.
- **Soft candidate components:** weak near, report/template, label-vector, or overflow/approximation
  relationships retained for private review and later stress testing; these IDs cannot be fold
  group IDs.
- **Private provenance:** every relationship edge, evidence kind, component summary, and
  representative review path remains inside Kaggle.

The v2 logic is implemented locally. Exact-duplicate and repeat connectivity, long weak-chain
separation, overflow semantics, private component recomputation, and representative-largest-path
review must pass before the representation can be called structurally suitable for a future fold
chunk.

## Disclosure boundary

The v1 sanitized output independently suppressed fields and allowed a rare value to be derived from
related totals. It is superseded. The replacement sanitizer controls linked counts jointly, forbids
unsafe percentages/redundant equations, emits validated qualitative/range tokens, and renders every
approved JSON/Markdown artifact from one controlled object. Development tests exist; a fresh
private output and final staged-tree/remote validation are pending.

## DICOM block

DICOM readiness is unproven. Every private exception must receive an explained root cause and
deterministic disposition. The gate requires complete study/series/file reconciliation, no
unexplained case, no valid recoverable unsupported object, and no fabricated geometry, filename
ordering substitution, or silent skip. Unavoidable source corruption may be quarantined only with
private evidence and a safe aggregate disposition.

## Shift and subgroup limits

The example-test interface has insufficient support for a reliable domain comparison, its reports
are unavailable, and the hidden scoring set is not evaluable. No domain-stratification or
hidden-shift claim is supported, so R-019 remains open.

## Required future fold evidence

- Positive, negative, and unknown support for all 12 targets in every candidate fold.
- Component-indivisible hard patient/repeat/duplicate splits plus explicit soft-candidate stress
  tests and a fresh leakage audit.
- Bootstrap confidence intervals and permitted scanner/protocol/language subgroup checks.
- Runtime, peak memory, model size, prediction correlations, and manual report/MRI validation when
  applicable.
- Out-of-fold predictions for every promoted model; nested or held-out evidence for ensemble
  weights.

None of that future evidence exists in this checkpoint because no fold or model work is authorized.
