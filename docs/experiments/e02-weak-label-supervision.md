# Experiment Contract - E02 weak-label supervision

## Before run

- Experiment ID: E02-weak-labels-v1-fold0
- Hypothesis: report-derived weak labels (unmasked Effusion/Synovitis cells under v1 policy), calibrated by human review, give higher Fold 0 validation macro AUC than the official-only E01R scarcity reference.
- Primary change: supervision source only - official train.csv labels replaced by frozen weak-labels-v1 cell states with confidence-tier weighting (high >= 0.9 weight 1.0, medium 0.7-0.9 weight 0.5, low < 0.7 excluded).
- Frozen controls: TinyCNNShared encoder + classifier head; frozen r16 preprocessing (bundle da5b9c8 / 91ed07921059..., dicom-model-v1); grouped deterministic folds, Fold 0 validation; AdamW lr 1e-3, weight decay 0; batch 8; 30 epochs max; seed 42; study-level mean pooling over series slots; supervised-cell-normalized BCE.
- Data-manifest version: r16 source manifest (unchanged).
- Label/fold/preprocessing versions: weak-labels-v1 (frozen only after precision + provenance gates pass post-review), official labels v1 (evaluation only), folds v1, preprocessing dicom-model-v1.
- Model, loss, augmentation, seed: TinyCNNShared, masked BCE, none, 42.
- Compute estimate: full-eligible-population preprocessing plus training within one 9-hour GPU ceiling; preprocessing guard at 55 percent budget as in E01R.
- Expected information gain: whether report-derived supervision transfers to image-level prediction despite imperfect rule precision, measured against the 0.505 official-label Fold 0 macro AUC reference.
- Promotion criterion: pooled OOF macro AUC over official and human-reviewed labels computed with bootstrap intervals and all 12 per-label AUCs where both classes exist; must exceed the E01R reference outside its interval and show no fold-leakage findings.
- Kill criterion: human-review precision gate fails (weak-labels-v1 stays unfrozen, E02 does not launch), or OOF macro AUC does not beat chance/E01R reference.

## Launch gate

E02 may be packaged and launched only after:
1. The 80-row human review worksheet returns and rule precision is recalibrated on reviewed rows.
2. weak-labels-v1 freeze gates PASS (precision + provenance).
3. repr-v0 terminal state is validated and recorded (independent track, no shared artifacts).

## After run

To be recorded from authenticated kernel outputs only: code commit and config hash, runtime/GPU and peak memory, macro OOF AUC, all 12 per-label AUCs, positive/negative support, bootstrap intervals, language/source breakdown, skipped-study counts, train/val losses, failure modes.
