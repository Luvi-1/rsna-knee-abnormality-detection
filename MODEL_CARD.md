# Model Card

Status: no model, checkpoint, training run, inference output, prediction, or submission exists.
Chunk 5 implements only a candidate preprocessing pipeline and does not change this status.

## Intended use

Competition research: predict probabilities for 12 knee MRI findings and maximize validated macro ROC AUC under the offline nine-hour notebook limit.

## Prohibited use

No diagnosis, triage, treatment, patient care, re-identification, or clinical deployment.

## Initial baseline gate

A baseline must have a registered experiment contract, synthetic smoke test, deterministic preprocessing, OOF predictions, per-label metrics, runtime evidence, and documented external-asset licenses before promotion.

Model architecture, loss, training data, thresholds, calibration, and model limitations remain
unassigned. `dicom-model-v1` is only a preprocessing candidate until Chunk 5 passes.
