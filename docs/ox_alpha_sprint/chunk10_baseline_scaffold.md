# Chunk 10 — Baseline model and training scaffold

Date: 2026-08-22.
Branch: ox-alpha/rsna-seven-day-acceleration.

## Objective

Provide a minimal, dependency-free reference model and synthetic smoke training
loop so the full pipeline (model forward, loss, OOF shape, key binding) can be
validated before any GPU or private data is touched. This scaffold makes no
generalization claim and must never be used as competition evidence.

## Scope delivered

- src/rsna_knee/models/baseline_2_5d.py: numpy-only 2.5D baseline that pools
  per-study statistics (mean/std/min/max) and applies a seeded linear layer with
  sigmoid output. Accepts [batch, H, W] or [batch, C, H, W] tensors.
- src/rsna_knee/training/smoke_loop.py: deterministic single-pass smoke loop
  producing bounded OOF predictions and matching study keys.
- configs/models/baseline_2_5d.yaml and
  configs/experiments/baseline_synthetic_smoke.yaml recording the experiment
  contract for this plumbing test.

## Evidence

Commands:

- PYTHONPATH=src uv run pytest tests/test_baseline_model.py
  tests/test_training_smoke.py tests/test_oof_writer.py
- uv run ruff check src/rsna_knee/models src/rsna_knee/training (and tests)
- uv run ruff format (same paths)
- uv run mypy src/rsna_knee/models src/rsna_knee/training

Results: 9 targeted tests passed; Ruff clean; strict mypy clean.

## Design decisions

- No torch dependency: the baseline uses only numpy to avoid adding a heavy
  framework dependency before the real architecture is chosen.
- Pooling reduces all spatial dimensions to four per-study statistics, making
  the model trivially small but still exercising the full forward path.
- The smoke loop explicitly labels its val_auc as 0.5 (plumbing only) and the
  experiment contract records kill criteria for any shape or finiteness failure.
