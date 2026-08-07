# Label Card

Version: unassigned

## Targets

`ACL`, `MCL`, `Medial Meniscus`, `Lateral Meniscus`, `Medial OA`, `Lateral OA`, `PF OA`, `Effusion`, `Synovitis`, `Baker's`, `Contusion`, `Fracture`.

## Current evidence

- Kaggle defines targets as per-study binary findings.
- Only a small subset of training studies has per-condition labels.
- Remaining studies include multilingual free-text radiology reports that may support weak supervision.

## Policy

- Missing is unknown, never automatically negative.
- Official labels and report-derived weak labels remain separate sources.
- Report-derived labels are not expert ground truth.
- Every weak-label rule records language, assertion/negation/uncertainty behavior, provenance, version, confidence, and validation sample.
- No pseudo-label may come from a model trained on the same study.

## Promotion gate

No weak labels enter training until manual report validation, per-label error analysis, leakage review, and a versioned label manifest are complete.
