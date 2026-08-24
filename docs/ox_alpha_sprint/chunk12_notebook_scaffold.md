 # Chunk 12 — Notebook scaffold
 
 Date: 2026-08-22.
 Branch: ox-alpha/rsna-seven-day-acceleration.
 
 ## Objective
 
 Provide a reproducible notebook entry point that orchestrates the synthetic
 smoke loop and validates its OOF output shape before any real-data notebook is
 authored. The notebook contains no private data, no credentials, and no
 submission logic.
 
 ## Scope delivered
 
 - notebooks/baseline_synthetic_smoke.ipynb: minimal cells that import the
   synthetic smoke loop, run it with a fixed seed, assert output shapes, and
   print aggregate statistics only. No raw pixel, report, or identifier output.
 
 ## Design decisions
 
 - Notebook is intentionally thin: all reusable logic lives in src/rsna_knee/
   modules per engineering invariants; the notebook only orchestrates calls.
 - Output suppression is enforced by using aggregate prints (loss value, shape
   tuple) rather than inline dataframe or image rendering.
