# Status

Updated: 2026-08-08T00:44:26Z

- Current branch: `feat/chunk-2-competition-contract`; not merged.
- Chunk 2: the live competition contract is captured in a dated evidence snapshot and one canonical
  machine-readable file. No competition-data analysis or MRI training occurred.
- `configs/competition.yaml` points to `docs/competition_contract/contract.yaml`; submission
  validation now consumes that source instead of duplicating targets.
- The exact study-level 12-target schema, unweighted macro-AUC formula, timeline, offline
  nine-hour CPU/GPU limits, submission/team limits, aggregate inventory, and train/test interface
  were verified through official Kaggle sources.
- Test reports are unavailable. `PatientSex` is not in the current train/test CSV interface; no
  DICOM metadata field may become a dependency until verified on the scoring-equivalent test input.
- Nine official-source contradictions are tracked as private GitHub issues #1–#9 with explicit
  authority and conservative defaults. Private repository URLs are not recorded.
- Degenerate-label scorer behavior, the exact 86 DICOM tags, and accelerator details remain
  unresolved and fail closed.
- The official Kaggle MCP is configured but its tools were not exposed, so official Kaggle CLI
  2.2.4 and signed-in pages were used. The official GitHub connector could not access the private
  repository; after verifying the owner and private target, its CLI fallback created the issues.
- Kaggle, GitHub, Context7, and Hugging Face MCP configurations remain enabled. W&B remains
  disabled. The fine-grained GitHub MCP token still needs private-repository access.
- The account had already entered and accepted the competition rules before this chunk. This chunk
  did not accept rules, submit, alter a team, or publish any artifact. Kaggle identity verification
  remains incomplete.
- No model, data manifest, folds, labels, experiments, or competition artifacts exist yet.
- Locked non-editable package install, Ruff, mypy, three synthetic tests, the synthetic submission
  smoke test, canonical contract self-check, pre-commit, sensitive-file guard, secret scan, and
  exported-lock dependency audit pass locally.

Next gate: complete Kaggle identity verification and grant the fine-grained GitHub token access,
then build an aggregate-only data/label manifest and leakage plan inside Kaggle. Do not train yet.
