# RSNA Knee Abnormality Detection

## Operating boundary

- Optimize for private-leaderboard macro ROC AUC without promising placement.
- Use Kaggle for full data, GPU training, and inference. Keep local work limited to code, public metadata, aggregate summaries, and synthetic fixtures.
- Never send raw DICOM pixels, radiology reports, patient-level metadata, or private competition artifacts to an LLM, Hugging Face, W&B, GitHub, or another external service.
- Never commit competition data, credentials, checkpoints, or prediction artifacts.
- Treat outputs as research only, never clinical advice.

## Required start of every chunk

1. Read `STATUS.md`, `DECISIONS.md`, `RISK_REGISTER.md`, and the latest file in `docs/competition_contract/`.
2. Re-verify live Kaggle rules, data, evaluation, timeline, runtime, submission, external-asset, team, license, and sharing constraints.
3. Inspect the current tree and state one objective, its evidence, and its exit gate.
4. Work on a feature branch. Use separable agents only; never let agents edit the same files.
5. Record the experiment contract before compute and stop when the current chunk exit gate passes.

## External-action gates

Get explicit human approval immediately before any submission, team creation or merge, rules acceptance, public code/data/model release, remote deletion, PR merge, or unusually large compute spend. Do not spend leaderboard quota merely because it is available.

## Scientific invariants

- Group patients, repeated studies, exact duplicates, near duplicates, and report templates before folds.
- Treat missing labels as unknown, not negative. Never call report-derived labels expert ground truth.
- Fit labels, transforms, thresholds, ensemble weights, and pseudo-label rules within training folds only.
- A model may be promoted only with out-of-fold predictions, macro AUC, all 12 label AUCs, uncertainty, runtime, memory, size, and prediction-correlation evidence.
- A model must not pseudo-label any study it trained on.
- Change one principal experimental factor at a time unless interaction is the stated hypothesis.
- Build against the live nine-hour inference ceiling with a substantial safety margin.

## Engineering invariants

- Python is typed, configuration-driven, seed-controlled where possible, and dependency-locked.
- Keep reusable logic in modules; notebooks orchestrate it.
- Use synthetic DICOM fixtures for local tests.
- Test DICOM ordering, preprocessing, metrics, fold leakage, label masks, submission schema, and ensembles before promotion.
- Log only structured, non-sensitive identifiers and aggregates.
- Every artifact records code version, config hash, data-manifest version, fold version, preprocessing version, and label version.
- Keep the package installable from `uv.lock`; run Ruff, mypy, pytest, secret checks, and dependency audit before promotion.
- Treat `.agents/skills` as the Codex discovery path and `.codex/skills` as the checked-in project skill source.

## Experiment contract

Before a run, record its ID, hypothesis, one primary change, frozen controls, data/label/fold/preprocessing versions, model, loss, augmentation, seed, compute estimate, expected information gain, promotion criterion, and kill criterion. After a run, record actual runtime/cost, macro and 12 per-label OOF AUCs, confidence intervals, manual validations, shift results, failure modes, correlations, and keep/reject/revise/ensemble-only decision.

## Chunk completion

Report objective, files, commands, exact checks, quantitative results, decisions, risks, PASS/FAIL, the one recommended next chunk, and a ready-to-persist `STATUS.md` entry. Never claim a check passed without its output.

## Tool order

Use official Kaggle MCP first when exposed, then official Kaggle CLI. Use Context7 for current library APIs. Use Hugging Face only for public discovery and licensing. Keep W&B disabled until its aggregate-only boundary is approved.

Project skills live under `.codex/skills` and are exposed through `.agents/skills`. Invoke the narrowest matching skill before its workflow.
