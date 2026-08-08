# Decisions

## D-001 - Kaggle-heavy execution

- Date: 2026-08-07
- Owner: Luvi-1 and Codex
- Question: Where should full-data processing run?
- Alternatives: local MacBook; Kaggle; another cloud.
- Evidence: live data size is 569.76 GB and 819,640 files; final inference must run in an offline Kaggle Notebook within nine hours.
- Decision: keep full data, training, and inference on Kaggle; use the Mac for code, public metadata, aggregates, and synthetic tests.
- Risks: notebook quotas and environment drift.
- Reversal condition: a rule-compliant private environment is approved and offers a measurable advantage.
- Commit/experiment: `fdd9769`; no experiment.

## D-002 - Contract before modeling

- Date: 2026-08-07
- Owner: Luvi-1 and Codex
- Question: Start modeling or establish governance first?
- Alternatives: rapid notebook baseline; governed bootstrap.
- Evidence: binding MIRA, private-sharing, external-asset, runtime, and winner-delivery constraints affect architecture and data handling.
- Decision: complete the live contract and governance baseline first.
- Risks: delays first baseline by one small chunk.
- Reversal condition: none; the contract remains mandatory.
- Commit/experiment: `fdd9769`; no experiment.

## D-003 - Unknown labels remain masked

- Date: 2026-08-07
- Owner: Luvi-1 and Codex
- Question: How should unannotated conditions be represented?
- Alternatives: assume negative; report-derived weak label; unknown mask.
- Evidence: Kaggle says only a small training subset has per-condition labels and supplies multilingual reports for possible label derivation.
- Decision: default to unknown masks. Weak labels require a versioned extraction protocol and validation before use.
- Risks: fewer supervised examples initially.
- Reversal condition: organizer-provided semantics or validated weak supervision supports a different treatment.
- Commit/experiment: `fdd9769`; no experiment.

## D-004 - No speculative remote write

- Date: 2026-08-07
- Owner: Codex
- Question: Create a private GitHub repository automatically?
- Alternatives: create now; use an existing repository; request the remote choice.
- Evidence: no matching private repository exists, the only private repository is unrelated, and the fine-grained token currently sees no private repositories.
- Decision: prepare the local feature branch and request approval for the new private remote.
- Risks: local work is not yet backed up remotely.
- Reversal condition: user approves a repository name or identifies an existing private repository.
- Commit/experiment: `fdd9769`; no experiment.

Outcome: the Chunk 1 instruction authorized creation. The new source-of-truth repository was created under `Luvi-1`, verified private, and added as `origin`; it was not merged.

## D-005 - Use uv with locked non-editable installs

- Date: 2026-08-07
- Owner: Codex
- Question: Which reproducible Python dependency workflow should govern local and CI execution?
- Alternatives: pip plus requirements files; Poetry; `uv` with `uv.lock`.
- Evidence: `uv` 0.11.29 is installed, supports exact direct bounds and locked syncs, and a non-editable install works with the current Python security behavior.
- Decision: use Python 3.11, exact direct dependencies, `uv.lock`, and `UV_NO_EDITABLE=1` for local and CI commands.
- Risks: future lock refreshes require deliberate dependency review.
- Reversal condition: `uv` becomes unsupported on Kaggle or cannot reproduce the approved environment.
- Commit/experiment: this Chunk 1 commit; `exp-0000-smoke`.

## D-006 - Use SQLite as the experiment and provenance registry

- Date: 2026-08-07
- Owner: Codex
- Question: What is the minimum durable registry for experiment contracts, results, metrics, and artifacts?
- Alternatives: SQLite; Parquet; both.
- Evidence: the records are relational and low volume; SQLite supplies constraints, foreign keys, and one portable private file without another dependency.
- Decision: use schema-versioned SQLite. Add Parquet only when aggregate analytics demonstrate a need.
- Risks: concurrent writers are not a current use case.
- Reversal condition: registry volume or concurrent analysis makes SQLite measurably inadequate.
- Commit/experiment: this Chunk 1 commit; `exp-0000-smoke`.

## D-007 - Keep one project-skill source with a discovery link

- Date: 2026-08-07
- Owner: Codex
- Question: How should the requested `.codex/skills` layout remain discoverable by a new Codex session?
- Alternatives: duplicate skills; use only `.agents/skills`; link the discovery path to the requested source.
- Evidence: current Codex documentation discovers repository skills from `.agents/skills`, while this chunk explicitly requires `.codex/skills`.
- Decision: keep authoritative skills in `.codex/skills` and expose them through the relative `.agents/skills` symlink.
- Risks: clients that do not follow repository symlinks may need direct `.agents/skills` files.
- Reversal condition: Codex natively discovers `.codex/skills` or a target environment rejects symlinks.
- Commit/experiment: this Chunk 1 commit; no experiment.

## D-008 - One canonical machine-readable competition contract

- Date: 2026-08-07
- Owner: Codex
- Question: How should code consume mutable competition constraints without duplicating them?
- Alternatives: hard-code values in modules; copy values across configs; one canonical contract plus
  a project pointer.
- Evidence: the prior validator duplicated the 12 targets, and official sources contain live drift
  and contradictions.
- Decision: keep all operational values in `docs/competition_contract/contract.yaml`, point to it
  from `configs/competition.yaml`, and require the submission validator and future Kaggle packaging
  to load that source.
- Risks: a stale canonical file remains possible if no live refresh occurs.
- Reversal condition: Kaggle publishes a stable, complete machine API contract that can be consumed
  directly and reproducibly.
- Commit/experiment: this Chunk 2 commit; no experiment.

## D-009 - Fail closed on official-source contradictions

- Date: 2026-08-07
- Owner: Codex
- Question: Which interpretation governs when official pages or incorporated terms disagree?
- Alternatives: use the newest wording; use the most permissive wording; apply source authority and
  the narrowest safe interpretation.
- Evidence: nine live contradictions affect slug, schema, asset access, derivative works,
  commercial use, public weights, winner licensing, institution count, and start-date semantics.
- Decision: binding Rules and MIRA outrank contextual pages; named license legal text controls its
  meaning; unresolved operational fields fail closed. Track every contradiction in a private issue.
- Risks: conservative defaults may delay an otherwise permitted action.
- Reversal condition: written Kaggle or RSNA clarification resolves the specific ambiguity.
- Commit/experiment: this Chunk 2 commit; no experiment.

## D-010 - Rank research by evidence and information efficiency

- Date: 2026-08-08
- Owner: Codex
- Question: How should architecture, label, validation, ensemble, and efficiency ideas be ordered
  before competition-data experiments?
- Alternatives: follow public leaderboard notebooks; reproduce the largest published system; rank
  falsifiable hypotheses using source quality, expected value, compute, runtime, and rule risk.
- Evidence: 62 structured sources include current official pages, multicenter knee-MRI studies,
  organizer-confirmed winning solutions, clinical-NLP validation, domain-shift studies, and official
  inference documentation. Public notebook cards trail the public leaderboard and expose incomplete
  validation and licensing evidence.
- Decision: use the deterministic ten-dimension score in
  `docs/research/hypothesis_backlog.md`; promotion still requires the experiment gate and cannot be
  inferred from the score.
- Risks: ordinal scores encode judgment and may change when contract, data audit, or OOF evidence
  changes.
- Reversal condition: stronger primary evidence or controlled competition OOF results change the
  estimated impact, confidence, cost, or risk.
- Commit/experiment: this Chunk 3 commit; no experiment.

## D-011 - Validation and weak-label integrity precede model complexity

- Date: 2026-08-08
- Owner: Codex
- Question: Which research path should receive the first controlled compute?
- Alternatives: full multi-plane 3D/vision-language system; public-notebook reproduction; honest
  grouping and label audit followed by a shared 2D MIL control.
- Evidence: direct multicenter knee studies report lower external than internal AUC; slice-level
  medical leakage can create extreme inflation; paired report/image studies show granular report
  labels are incomplete; prior RSNA winners repeatedly use group folds, localization, 2D/2.5D
  encoders, and ordered aggregation.
- Decision: first establish patient/repeat/duplicate/template and scanner/protocol stress folds plus
  per-label weak-label validity. The first image control is MRNet-lite shared 2D MIL; ordered 2.5D,
  plane gating, compact attention, SSL, localization, and ensembles enter one factor at a time.
- Risks: a conservative sequence delays a large architecture that might score well publicly.
- Reversal condition: a cheaper aggregate audit proves the split/label gates already valid or a
  controlled baseline shows that the proposed image control is scientifically inadequate.
- Commit/experiment: this Chunk 3 commit; no experiment.

## D-012 - Close unbounded candidate spaces conservatively

- Date: 2026-08-08
- Owner: Codex
- Question: How should the manifest audit preserve future-fold safety when near-series or near-slice
  candidate pairs exceed the bounded direct-evidence space?
- Alternatives: raise caps until the run fits; keep a partial pair list; fail every oversized audit;
  or discard partial claims and close complete evidence components conservatively.
- Evidence: full runs exceeded 1,000,000 near-series candidate pairs and 250,000 near-slice study
  pairs. Exact/fingerprint scans remained complete, while a capped partial pair list could silently
  permit related studies to cross a future fold.
- Historical decision: on overflow, discard incomplete direct-pair claims and preserve
  indivisibility through complete exact/fingerprint component closure plus minimal candidate-only
  overflow forests. Never represent capped evidence as complete; preserve the unchanged exact
  behavior below each cap.
- Risks: conservative closure can over-group studies, reduce fold flexibility, and require explicit
  feasibility checks during fold construction.
- Reversal condition: a bounded, deterministic, privacy-safe algorithm can enumerate and validate
  the complete candidate relation within the approved runtime and memory budget.
- Commit/experiment: `ea0a34b`, `75792aad08a3685d0c9ce92b5cab90307bf1336c`;
  `audit-0001-manifest`.
- Status: **superseded by D-013.** The v1 implementation allowed weak similarity and overflow
  candidate evidence to collapse the same components as hard duplicate/repeat evidence. That was
  conservative against leakage but semantically overclosed and cannot support a fold-feasibility
  claim.

## D-013 - Separate hard protected groups from soft candidates

- Date: 2026-08-08
- Owner: Codex
- Question: Which relationships may make studies permanently indivisible before fold construction?
- Alternatives: put every similarity or overflow candidate in one component; ignore weak evidence;
  or separate accepted hard relations from review/stress-test candidates.
- Evidence: exact duplicates and confirmed repeat-patient relations express an indivisibility
  constraint. Near-report, weak label-vector, approximate similarity, and overflow-candidate
  relations are hypotheses whose transitive chains can merge unrelated studies.
- Decision: `protected-groups-v2` builds hard protected components only from accepted hard evidence.
  It stores soft/candidate components, every edge, and provenance separately for private review and
  later fold stress testing. Soft identifiers can never be used as fold group identifiers. No fold
  feasibility is claimed at this checkpoint.
- Current evidence: implemented and locally testable in the working tree; full private
  recomputation, representative-component inspection, and remote CI remain pending.
- Risks: under-classifying a true repeat as soft could permit leakage later; over-classifying hard
  evidence can still reduce fold flexibility.
- Reversal condition: validated evidence promotes a specific soft relation to a versioned hard rule,
  or disproves an existing hard rule, with private edge-level review and regression coverage.
- Commit/experiment: pending remediation commit; planned `audit-0002-manifest-remediation`.

## D-014 - Enforce disclosure jointly across related outputs

- Date: 2026-08-08
- Owner: Codex
- Question: How should aggregate outputs protect a below-threshold count that has published totals,
  complements, percentages, or repeated representations?
- Alternatives: suppress each field independently; change the threshold; manually edit reports; or
  apply one central complementary-disclosure policy to the entire release.
- Evidence: the v1 release could reconstruct a rare value by subtraction even though the field was
  labelled suppressed. Separate JSON and Markdown representations also created cross-file attack
  surfaces.
- Decision: make the sanitizer the sole release boundary. Counts use validated disclosure tokens;
  linked totals and complements are transformed together; redundant percentages are forbidden; and
  all JSON/Markdown outputs must be canonical derivatives of the same controlled object. The
  validator must reject arithmetic reconstruction across fields and files.
- Current evidence: implemented with adversarial local tests; newly generated full-data artifacts
  and remote CI are pending.
- Risks: a future output field could create a new equation not represented in the complementary
  groups.
- Reversal condition: replace only with an independently reviewed policy that proves at least the
  same joint and cross-file protection.
- Commit/experiment: pending remediation commit; planned `audit-0002-manifest-remediation`.

## D-015 - Final gates run only on the complete staged release candidate

- Date: 2026-08-08
- Owner: Codex
- Question: When may governance claim that final local validation passed?
- Alternatives: rely on incremental checks; scan tracked files before generated docs are added; or
  stage the complete intended change first and run every final gate against that exact candidate.
- Evidence: Chunk 4 reported a final secret pass before newly tracked aggregate/provenance files were
  included, so the clean committed branch failed its high-entropy scan.
- Decision: incremental checks are development evidence only. Before any merge-ready claim, stage
  every intended file and run install, Ruff, formatting, mypy, pytest, pre-commit, secret scanning,
  sensitive-file/size guard, dependency audit, contract check, disclosure validation, and the
  applicable manifest/DICOM/grouping tests. Then require green GitHub-hosted CI on the same pushed
  commit.
- Current evidence: control recorded; the checkpoint's final staged-tree run has not occurred.
- Risks: modifying or generating a file after the final run invalidates the result.
- Reversal condition: a reproducible release system proves cryptographic identity between the
  checked file set and the pushed commit while enforcing the same gates.
- Commit/experiment: pending remediation commit; no experiment.
