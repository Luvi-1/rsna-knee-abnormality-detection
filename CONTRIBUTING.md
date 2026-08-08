# Contributing

1. Read `AGENTS.md`, `STATUS.md`, `DECISIONS.md`, `RISK_REGISTER.md`, and the latest competition contract.
2. Work on a feature branch and keep one principal experimental question per change.
3. Never add raw DICOMs, reports, patient metadata, credentials, checkpoints, private predictions, or W&B local data.
4. Set `UV_NO_EDITABLE=1`, install with `uv sync --locked`, and run `uv run pre-commit install` once.
5. Before review, stage every intended file and run the exact quality, sensitive-file, secret, and
   exported-lock dependency-audit commands in `README.md` against that complete candidate. If any
   file changes afterward, stage it and repeat every final gate.
6. Update governance cards and the experiment registry when behavior or evidence changes.

Use synthetic fixtures locally. Full-data work belongs only in an approved private Kaggle environment. Do not merge or publish without explicit approval.
