# Security Policy

## Protected material

Raw competition images, reports, patient-level metadata, private artifacts, credentials, tokens, and private predictions must never enter Git, CI logs, external LLMs, Hugging Face, W&B, or public storage.

## Required controls

- Keep the repository private and grant access only to recognized Kaggle team members.
- Store credentials outside the repository and reference environment-variable names only.
- Stage every intended release file first, then set `UV_NO_EDITABLE=1` and run the install,
  pre-commit, sensitive-file, secret, and exported-lock dependency-audit commands in `README.md`
  against that complete candidate. Any later file change invalidates the final result and requires
  the gates to run again.
- Use synthetic fixtures in CI.
- Rotate exposed credentials immediately and remove the material from Git history using an approved incident procedure.

## Reporting

Report suspected exposure privately to the repository owner. Do not open a public issue containing secrets, patient information, competition data, or private URLs.
