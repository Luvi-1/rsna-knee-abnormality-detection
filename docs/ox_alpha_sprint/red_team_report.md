# Red team report

Date: 2026-08-22.
Scope: All modules written in chunks 7–12 on branch ox-alpha/rsna-seven-day-acceleration.

## Findings

### R-01: Rule labeler sentence-local negation scope

Severity: LOW.

The negation detector checks only the prefix of the current sentence. A report
phrase like "No evidence of ACL tear. However, a partial MCL tear is noted."
correctly isolates each target. But "ACL tear, not seen on this study" would
place the negation cue after the match and miss it. This is a known limitation
of sentence-scoped rules and is documented in chunk7_weak_labels.md.

Mitigation: human review gate remains mandatory; no weak label is treated as
ground truth.

### R-02: Greedy fold balance is suboptimal for rare labels

Severity: MEDIUM.

The greedy positive-mass assignment may leave one fold with all examples of a
rare label if that label appears in fewer than n_splits studies. This could
produce a fold where the validation AUC for that target is degenerate (0.5).

Mitigation: the metric function returns 0.5 rather than crashing, and the
promotion criterion requires all 12 per-label AUCs to be reported so the issue
would be visible before any leaderboard submission.

Recommended fix: add a post-assignment check that warns when any label has
fewer than n_splits positive examples across folds.

### R-03: Baseline model is intentionally trivial

Severity: INFO.

Baseline2_5D pools to four statistics per study and applies one linear layer.
It has no capacity to learn anything useful from real images. This is by design:
it exists only to validate plumbing shapes and determinism. The experiment
contract explicitly records kill criteria that prevent it from being promoted.

No mitigation needed.

### R-04: Annotation partition uses hash-prefix splitting without label balance

Severity: LOW.

Partition assignment maps the first 8 hex chars of the study key to [0,1] and
splits at dev_fraction. This produces uniform but not label-stratified splits.
If positive cases cluster in a narrow hash range, dev or holdout could be
skewed. The risk is low because the split is over hashed keys (effectively
random) but should be verified once real labels are available.

Mitigation: partition assignments can be regenerated with different parameters
once real data distribution is known.

### R-05: Output validator does not check row count against expected studies

Severity: MEDIUM.

validate_model_output.py checks header, key format, column count, and value
range but does not verify that every expected study_key is present exactly once.
A submission missing rows would pass validation.

Recommended fix: accept an optional --expected-keys file listing valid study
keys and check set equality. Deferred until real submission format is confirmed
against live Kaggle schema.

## Clean checks

- No credentials, API keys, tokens, or secrets in any new source file.
- No DICOM, NPY, NPZ, checkpoint, pickle, or other binary artifact committed.
- No private competition data read at any point; all test inputs are synthetic
  strings, integers, or seeded numpy arrays.
- No external network call in any new module.
- No modification to the active Chunk 5 workspace at /Users/.../Desktop/kaggle.
