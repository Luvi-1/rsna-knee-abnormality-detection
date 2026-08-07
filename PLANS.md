# Plans

## Chunk 1 - competition contract and governed bootstrap

Status: completed locally; private remote creation remains a human gate

Objective: establish a live, timestamped rules baseline and a safe local repository skeleton without accessing competition data or making a remote/competition write.

Evidence required:

- Official overview, data, rules, MIRA license, and authenticated CLI facts captured with UTC retrieval time.
- Existing local and private GitHub repositories checked.
- Required governance documents present on a feature branch.
- No raw competition data, submission, team action, rule acceptance, public release, or large compute action.

Exit gate:

- Contract snapshot passes completeness checks.
- Governance file set passes repository checks.
- Diff is reviewed.
- Any missing private remote is reported as a human gate.

## Recommended next chunk

Create or connect the approved private GitHub repository, restrict access to recognized team members, then implement the dependency-locked package skeleton and synthetic-only validation tests. Do not download the full dataset or launch training.
