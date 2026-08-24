# OX Alpha Sprint Plan

Updated: 2026-08-22.
Base commit: d3771e7 (fix review-plan source discovery).

## Phase 1 — Repository reconstruction and downstream audit

- [x] Read all governance cards, plans, and contract snapshot.
- [x] Create isolated worktree on ox-alpha/rsna-seven-day-acceleration.
- [x] Attempt live contract refresh via official MCP; fall back to bounded CLI.
- [x] Produce chunk5_downstream_contract.md from source-code evidence only.

## Phase 2 — Ontology package

- [x] configs/ontology/ontology_provisional_v0.yaml with 12 targets and four states.
- [x] schemas/annotation_record.schema.json (strict JSON Schema).
- [x] docs/ox_alpha_sprint/chunk6_ontology.md and annotation_manual.md.
- [x] tests/test_ontology_schema.py.

## Phase 3 — Weak-label framework

- [x] src/rsna_knee/labels/ normalization + rule engine + combiner.
- [x] schemas/weak_label.schema.json.
- [x] tests/test_report_normalization.py, test_rule_labeler.py, test_weak_label_combiner.py.
- [x] docs/ox_alpha_sprint/chunk7_weak_labels.md.

## Phase 4 — Annotation/gold-set tooling

- [ ] src/rsna_knee/annotation/ partition isolation + active-learning queue.
- [ ] schemas/annotation_database.schema.json.
- [ ] tests/test_annotation_partitioning.py, test_active_learning_queue.py.

## Phase 5 — Folds and exact evaluation

- [ ] src/rsna_knee/folds/ grouped multilabel stratified folds.
- [ ] src/rsna_knee/evaluation/ macro ROC AUC + bootstrap CI + subgroup metrics.
- [ ] tests/test_grouped_folds.py, test_metric.py, test_oof_provenance.py.

## Phase 6 — Baseline scaffold

- [ ] src/rsna_knee/models/baseline_2_5d.py (lightweight reference encoder).
- [ ] src/rsna_knee/training/ synthetic smoke loop.
- [ ] configs/models/baseline_2_5d.yaml + configs/experiments/baseline_synthetic_smoke.yaml.
- [ ] tests/test_baseline_model.py, test_training_smoke.py, test_oof_writer.py.

## Phase 7 — Notebook/packaging scaffold

- [ ] notebooks/baseline_synthetic_smoke.ipynb.
- [ ] scripts/package_model_bundle.py + validate_model_output.py.
- [ ] tests/test_model_packaging.py.

## Phase 8 — Experiment portfolio and visual handbook

- [ ] docs/ox_alpha_sprint/experiment_portfolio.csv (top 30 ranked).
- [ ] docs/ox_alpha_sprint/chunks11_15_strategy.md.
- [ ] configs/experiments/candidate_experiments/.
- [ ] docs/ox_alpha_sprint/visual_qa_handbook.md + assets/.

## Phase 9 — Red team and final handoff

- [ ] Independent adversarial red-team pass.
- [ ] Full gate suite (pytest, Ruff, mypy, pre-commit, secret scan, sensitive-file guard).
- [ ] docs/ox_alpha_sprint/red_team_report.md + postmortem.md + FINAL_HANDOFF.md.
