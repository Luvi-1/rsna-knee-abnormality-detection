# Score-First 0.93 Campaign

## Decision

Stop launching new report-label experiments. The project has already established that:

- the owned 58-study frozen-feature baseline is technically valid but not competitive;
- the project-generated report-label routes did not produce approved supervision;
- the first public-baseline audit was too dependent on one historically blocked notebook;
- a leaderboard score can only be verified by an authorized competition submission.

The next execution path is a bounded reproduction campaign over current public notebooks that have a source-reported public score at or above 0.93.

All leaderboard values in this document are third-party, source-reported public scores. The project has not independently achieved them.

## Campaign order

### 1. Take Care Of Your Knee — required V36

- Owner/slug: `anhadmahajan06/rsna-knee-take-care-of-your-knee`
- Source-reported best public score: `0.936` at V36
- Current page observed at V39
- Current page notebook license: Apache-2.0
- Current page shows public-named inputs rather than an explicit private-dataset marker
- Exact V36 source, script version ID, output, input versions, asset licenses, and checkpoint safety remain to be pinned

This is the first target because it combines a 0.936 source score with a currently visible public input surface.

### 2. Raptor CoAtNet — V1

- Owner/slug: `hdhsjdjd/rsna-knee-raptor-coatnet`
- Source-reported public score: `0.933`
- Runtime observed: approximately 136 seconds
- Notebook license: Apache-2.0
- Public page shows a 17-input graph

This is the second target because V1 is immutable and already above 0.93, but its larger dependency graph requires more exact binding work.

### 3. Dread single model — required V1

- Owner/slug: `dreaddevelopment/knee-mri-twelve-findings-from-a-single-model`
- Source-reported public score: `0.924`
- Runtime observed: approximately 53 seconds
- Visible external dependency: `Knee MRI model weights: twelve findings`

This does not meet the 0.93 objective by itself, but its simple dependency surface makes it useful as a fallback and possible ensemble component.

## Excluded from the first execution pass

### Head and shoulders, knees and toes — V38

The source-reported best score is 0.936, but the current page displays private dataset inputs. It remains blocked unless every indispensable private input is replaced by a public immutable equivalent.

### DINOsaur V4 — V14

The source-reported score is 0.936, but the completed audit found unresolved transitive provenance, asset terms, file bindings, and unsafe checkpoint loading. It remains evidence, not an execution candidate.

## Fast execution sequence

1. Use the authenticated official Kaggle CLI to list score-descending competition notebooks.
2. Pull the current source and output of every configured public slug into `private_outputs/`.
3. Pin the required historical scored version through immutable Kaggle version evidence. The standard CLI normally pulls the latest version and must not be treated as proof of an older version.
4. Bind every input file to one exact owner/slug/version and SHA-256.
5. Read actual custom license text rather than relying on the label `other`.
6. Run static checkpoint preflight before any deserialization.
7. Reject source code that requires test reports, hardcodes three studies, calls the competition submission API, or requires runtime internet.
8. Create a private compatibility copy of the first candidate that clears the inference gate.
9. Run only on the three public example studies.
10. Compare the output against the pinned public output with a tolerance frozen before execution.
11. Build a clean-room implementation only after compatibility reproduction succeeds.
12. Prepare a dynamic hidden-test package.
13. Request separate explicit approval immediately before a real competition submission.

## Commands

Discovery only:

```bash
uv run python scripts/chunk4r_score_first.py
```

Pull the latest public source/output for configured slugs into ignored private storage:

```bash
uv run python scripts/chunk4r_score_first.py --pull-known
```

The pull command is evidence collection only. It does not prove that a historical scored version was retrieved.

## Exit conditions

The campaign reaches `SUBMISSION_CANDIDATE_READY` only when one candidate has:

- exact scored source version;
- exact public reference output;
- all indispensable public inputs bound to versions and checksums;
- actionable competition-use terms;
- safe checkpoint loading or private conversion to a non-executable tensor format;
- dynamic test discovery;
- offline compatibility reproduction;
- clean-room numerical agreement;
- projected runtime below nine hours;
- no competition submission call.

The project reaches `0.93+ VERIFIED` only after a separately authorized submission returns a public leaderboard score of at least 0.93.
