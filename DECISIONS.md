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
- Current evidence: the full private `audit-0002-manifest-remediation` recomputed v2 hard and soft
  structures at commit `6fce3af8ba1cc85dacd6a29326f999bf5f5227ed`. The sanitized result reports
  `protected_graph_closed: true`, `near_series_candidate_space_overflow: true`,
  `near_slice_study_pair_space_overflow: true`, and `near_slice_unresolved_study_pairs: zero`.
  Candidate/overflow evidence remained soft. No folds were assigned and feasibility was not
  assessed. Final staged-tree gates and hosted CI passed for release candidate `cc050a2`; any
  successor remains subject to the same exact-head gate.
- Risks: under-classifying a true repeat as soft could permit leakage later; over-classifying hard
  evidence can still reduce fold flexibility.
- Reversal condition: validated evidence promotes a specific soft relation to a versioned hard rule,
  or disproves an existing hard rule, with private edge-level review and regression coverage.
- Commit/experiment: `6fce3af8ba1cc85dacd6a29326f999bf5f5227ed`;
  `audit-0002-manifest-remediation`.

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
- Current evidence: the full private v2 run generated exactly five approved files under
  `joint-complementary-k20-v1`; the schema-v2 validator accepted their canonical tokens and hashes.
  No patient metadata, pixels, private tables, raw identifiers, or raw reports were released.
  Final staged-tree gates and hosted CI passed for release candidate `cc050a2`; any successor
  remains subject to the same exact-head gate.
- Risks: a future output field could create a new equation not represented in the complementary
  groups.
- Reversal condition: replace only with an independently reviewed policy that proves at least the
  same joint and cross-file protection.
- Commit/experiment: `6fce3af8ba1cc85dacd6a29326f999bf5f5227ed`;
  `audit-0002-manifest-remediation`.

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
- Current evidence: guarded history/ref cleanup passed and no active local or origin ref reaches the
  unsafe historical commit. The complete staged candidate then passed locked install/package,
  pytest 139/139, Ruff lint/format, strict mypy, all pre-commit hooks, exact staged secret/baseline
  comparison, sensitive-file and dependency audits, contract/config/submission checks, remote and
  local full-output validation, and four canonical byte comparisons. Hosted CI subsequently passed
  for release candidate `cc050a2`; any successor remains subject to the same exact-head gate.
  For r9, the exact candidate passed the 529/529 complete release gate and produced freeze
  `1db805e` / bundle `28457d...`; all non-content bundle checks passed. Final content inspection then
  rejected the bundle before upload because the pinned upstream `pydicom 3.0.2` wheel contains
  aggregate 104 `.dcm` members and 188 members with the standard `DICM` preamble. No r9 remote
  artifact exists. The first r10 D-029 candidate then passed 530/530 on exact staged tree
  `5bea3c110e100e9ddd2d94c8b89c29e1f0ff82a0`, but D-030 preflight found additional
  project-wheel and deployment-authentication trust gaps. That gate is superseded. After their
  correction, the first complete exact staged D-015 gate passed on tree
  `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260` over exactly 24 files: pytest 537/537;
  offline locked reinstall and lock; isolated wheel build/install/import; tracked MIME, symlink, and
  sensitive guard; Ruff check/format; mypy over 25 package and 11 trust-boundary files;
  config/submission; contract schema and current `contract_drift=no`; schema bytes; pre-commit;
  detect-secrets; `pip-audit` with no vulnerabilities; and diff, inventory, and unchanged-tree PASS.
  This governance reconciliation changes bytes, so D-015 requires an immediate identical fully
  restaged rerun; a PASS without further mutation fixes `complete_final_gate=PASS`.
- Risks: modifying or generating a file after the final run invalidates the result.
- Reversal condition: a reproducible release system proves cryptographic identity between the
  checked file set and the pushed commit while enforcing the same gates.
- Commit/experiment: control implemented at
  `6fce3af8ba1cc85dacd6a29326f999bf5f5227ed`; no experiment.

## D-016 - Accept manifest-v2 audit evidence without promoting downstream work

- Date: 2026-08-08
- Owner: Codex
- Question: Does the completed remediation run replace the historical audit as current manifest
  evidence, and what does it authorize?
- Alternatives: retain the v1 audit; accept v2 as fold/model readiness; or accept v2 only as the
  current private manifest and structural-grouping evidence.
- Evidence: `audit-0002-manifest-remediation` completed a full private CPU run in 10,092 seconds.
  The validated schema-v2 output reports complete coverage and five-level reconciliation,
  `unexplained_dicom_issues: zero`, `dicom_issue_dispositions_complete: true`,
  `protected_graph_closed: true`, `official_only: true`, `folds_assigned: false`, and
  `fold_feasibility: not_assessed`. Hard duplicate evidence and soft candidate/overflow evidence
  are represented separately; case details and identifiers remain private.
- Decision: accept `manifest-v2` / `protected-groups-v2` as the current audit representation and
  supersede `audit-0001-manifest` for downstream use. This closes the private rerun gate only. It
  does not authorize preprocessing, fold construction, weak labels, training, prediction,
  ensembles, submission, merge, or public release. D-029 later preserves this scientific evidence
  but supersedes `audit-0002-manifest-remediation` as a reusable source root because the shared
  helper that built its bundle also admitted dependency-wheel medical payloads.
- Risks: hidden-test shift remains unevaluable; future folds still need class/support/leakage
  validation; private pull request #10 remains unmerged, and every successor to the green
  `cc050a2` candidate still requires exact-head hosted CI.
- Reversal condition: new input, loader, schema, grouping, label, or disclosure changes invalidate
  the pinned audit and require a new versioned private rerun.
- Commit/experiment: `6fce3af8ba1cc85dacd6a29326f999bf5f5227ed`;
  `audit-0002-manifest-remediation`.

## D-017 - Canonicalize the slice axis while preserving native in-plane anatomy

- Date: 2026-08-09
- Owner: Codex
- Question: How should heterogeneous MRI orientation be made deterministic without silently
  exchanging medial and lateral anatomy?
- Alternatives: rotate and reflect every image into one display convention; preserve acquisition
  order; or canonicalize physical slice direction while retaining native in-plane pixels.
- Evidence: DICOM `ImageOrientationPatient` and `ImagePositionPatient` define patient-space
  geometry. A universal in-plane reorientation can require a reflection, while no verified label
  transformation currently authorizes a medial/lateral exchange.
- Decision: `dicom-model-v1` orders slices by projection onto the IOP cross-product normal and
  canonicalizes that normal to the positive dominant LPS axis. It preserves native row/column pixel
  orientation, records the affine and every transformation, performs no horizontal flip, and blocks
  model use when a regular affine is unproven. QA displays explicit patient-direction and laterality
  legends outside the image pixels.
- Risks: models still see native in-plane acquisition variation; visual QA must detect systematic
  orientation or laterality errors before promotion.
- Reversal condition: a separately validated patient-space reorientation proves pixel, affine,
  laterality, and label-transform correctness across all observed acquisition geometries.
- Commit/experiment: pending clean Chunk 5 commit; `preprocess-0001-dicom-pipeline`.

## D-018 - Bind private visual review through an immutable two-stage workflow

- Date: 2026-08-09
- Owner: Codex
- Question: How can a human review private QA images without exposing them to Codex or allowing an
  unbound spreadsheet or mutable note to become promotion evidence?
- Alternatives: download images for local review; bring a detailed completed ledger back locally;
  record an informal checklist; or retain detailed review evidence in Kaggle and hand off only an
  aggregate attestation.
- Evidence: the review must cover at least 100 studies and heterogeneous acquisition strata while
  private images, identifiers, case mappings, and artifact hashes remain inside Kaggle. Promotion
  evidence must prove which exact artifacts were reviewed and prevent free-text disclosure.
- Historical decision: the initial private QA kernel would produce ordinal-only QA artifacts and
  private indexes, while a separate template would create rows and artifact hashes. A locally
  transported aggregate attestation would then be repackaged as a private finalizer input.
- Risks: manual review remains labor-intensive; an incomplete or blocked attestation correctly
  prevents promotion; authenticated Kaggle execution and at least 100 reviews remain outstanding.
- Reversal condition: replace only with a private workflow that provides equivalent immutable
  artifact binding, coverage, disclosure control, and independent validation.
- Commit/experiment: pending clean Chunk 5 commit; `preprocess-0001-dicom-pipeline`.
- Status: **superseded before remote execution by D-019.** No dataset, kernel, review, or local
  attestation was created under this design. Moving a human-composed aggregate across the Kaggle
  boundary was unnecessary and weaker than consuming the completed private review session
  directly.

## D-019 - Require independent full-data replay and a Kaggle-resident review ledger

- Date: 2026-08-09
- Owner: Codex
- Question: What execution and review chain can prove whole-input determinism and bind human
  decisions to the exact artifacts without exporting private review state?
- Alternatives: run only a 120-to-240-study QA cohort; process one cohort twice in one kernel;
  export a human-composed aggregate for repackaging; or use distinct full runs and keep the completed
  ledger inside the authenticated Kaggle kernel chain.
- Evidence: the Chunk 5 exit gate requires two independent complete runs over the authorized
  training set, exact comparison of deterministic outputs, post-run stratified review of at least
  100 studies and all their eligible diagnostic series, and cryptographic binding to the exact
  source manifest, preprocessing, cohort, and review kernel. `audit-0001-manifest` is superseded;
  `audit-0002-manifest-remediation` / `manifest-v2` remains historical scientific evidence, but
  D-029 supersedes it as a reusable source root. `audit-0003-wheel-sanitization` must complete before
  the new DICOM-QA bundle is bound to its validated source output.
- Decision: build one immutable bundle and two distinct private version-1 full-run kernels, Run A
  and Run B, with identical frozen inputs. Each authenticates the complete `manifest-v2` source
  output, exactly reconciles train-series membership and organizer fields plus every regular DICOM's
  keyed relative identity, size, and raw digest, and processes the entire authorized training set to
  terminal accounting. A separate version-1 comparator requires exact equality of declared
  deterministic outputs. Only after the full pass, `qa-cohort-selection-v2` creates the private
  plan. Every row binds organizer/physical plane, assigned slot, retention, the six-slot missing
  mask, and ordinal sibling disposition context. A safe version-1 UI template resolves artifacts
  only under authenticated Run A and is copied and edited in Chrome into a distinct private
  review-session version 1 whose first operation is `START`; detailed identities, artifacts, cohort
  hashes, rows, and fixed decisions never leave Kaggle. The version-1 finalizer consumes the
  completed session directly, authenticates the entire chain, requires at least 100 reviewed
  studies, all represented material strata, all eligible diagnostic series, all nine checks
  terminal, and zero `BLOCK`, then emits only `human_review_summary.json` and
  `final_performance_report.json` as the two final allowlisted release-safe outputs with exact review
  counts retained privately.
- Current local evidence: the complete staged candidate had no unstaged or untracked residue and
  passed locked offline sync/lock, isolated wheel build/install/import, Ruff lint/format, strict mypy
  over 24 `src` files and seven trust-boundary files, full pytest 328/328, every pre-commit hook, exact
  secret scan, sensitive-file and path/magic guards, dependency audit with no known vulnerabilities,
  CLI/config/submission/contract-schema smoke checks, and Git diff check. An independent settled
  red-team found no P0/P1. Every later edit requires the complete staged gate again; commit approval
  and every private/remote gate remain outstanding.
- Risks: two full runs consume more CPU; a partial or failed run blocks comparison; a human must
  complete the private session; any changed bundle, input, preprocessing config, cohort, parent,
  source, or kernel version invalidates the chain.
- Reversal condition: replace only with a workflow that proves complete independent execution,
  equal or stronger cryptographic identity, equivalent private human evidence, and the same
  disclosure boundary.
- Commit/experiment: pending clean Chunk 5 commit; `preprocess-0001-dicom-pipeline`.
- Status: **amended by D-023.** The independent-run identity chain, private UI, review ledger, and
  finalizer boundary remain controlling. D-023 replaces the comparator payload, selector coverage,
  and QA materialization portions; the historical joint-material claim is not current evidence.

## D-020 - Separate source-manifest governance and producer execution identities

- Date: 2026-08-10
- Owner: Codex
- Question: Which identity should authenticate the private Chunk 4 database consumed by Chunk 5?
- Alternatives: compare the database execution ID with the promoted governance audit ID; accept a
  format-only producer ID; add a new public identity-schema field; or prove the producer identity
  from the already bound code commit, full bundle hash, and exact derived private references.
- Evidence: predecessor freeze `a5a44ac` and bundle `7cf43...` authenticated far enough to launch
  private Run A, which then failed before preprocessing with the sanitized code
  `source_manifest_version_mismatch`. The Chunk 4 database stores its producer execution ID in the
  `audit_id` row, while `audit-0002-manifest-remediation` identifies the promoted governance record.
  The consumer incorrectly treated those distinct namespaces as one value. The failure was
  fail-closed; no private reference, hash, path, identifier, report, or pixel was exported.
- Decision: retain `audit-0002-manifest-remediation` as the outer governance identity. Authenticate
  the database producer identity separately using the existing immutable binding: exact lowercase
  code commit, full source-bundle hash equality, the producer-ID derivation, a shared owner, and the
  exact content-derived source kernel and dataset references. Bind that producer tuple into the
  private source snapshot digest without changing the public/source identity schema.
- Current evidence: the two-file correction in `kaggle/dicom_qa/run.py` and
  `tests/test_dicom_qa_full_run.py` passed 32 focused tests plus Ruff and strict mypy. The exact
  12-file staged replacement candidate then passed the complete 404-test, build, typing, privacy,
  security, dependency, contract, and clean-tree gate. Replacement freeze `e6e5b35` and bundle
  `3a361...` passed input authentication, then Run A failed closed with
  `source_manifest_input_invalid`. Run B was not started. Both recovery chains are superseded-pending
  rather than completion evidence.
- Risks: the runtime proof depends on the already authenticated immutable source bundle and pinned
  producer code; a changed source bundle, producer, reference derivation, or identity schema
  invalidates the proof and requires a fresh audit and full gate.
- Reversal condition: replace only with a versioned identity schema that explicitly binds both
  namespaces with equal or stronger cryptographic and privacy guarantees.
- Commit/experiment: `e6e5b35` superseded-pending; `preprocess-0001-dicom-pipeline`.

## D-021 - Consume the promoted source-manifest schema exactly

- Date: 2026-08-10
- Owner: Codex
- Question: Which Chunk 4 fields define study-level issues and non-singleton protected duplicate
  membership?
- Alternatives: add private diagnostics; broaden the failure handler; infer study membership from
  other tables; or query the authenticated producer schema directly.
- Evidence: the `e6e5b35` input chain authenticated and Run A then failed closed with
  `source_manifest_input_invalid`. Reproduction against the real producer schema showed that
  `manifest_issue` stores every entity reference in `entity_key`, while the consumer queried a
  nonexistent `study_key` column for study-level issues. The same review showed that
  `protected_component` intentionally contains singleton rows, so an unfiltered query falsely
  classified essentially every study as a duplicate group.
- Decision: use `manifest_issue.entity_key` for study-level issues and admit only
  `protected_component.evidence_state='hard'` to the protected-duplicate review stratum. Keep the
  candidate-component query unchanged because the producer emits it only for actual candidate
  edges. Cover both corrections with one real-schema regression.
- Current evidence: all 33 focused full-run tests passed. The exact seven-file candidate also passed
  the complete 405-test build, typing, privacy, security, dependency, contract, and clean-tree gate,
  producing freeze `60df41c` / bundle `3dc575...`. Its inputs authenticated and Run A `r3` passed
  the source-manifest boundary before later failing closed on its processing self-deadline. The
  performance-recovery changes invalidate that prior release gate; a new complete exact-set gate,
  freeze, bundle, authentication, and Run A retry remain pending. Run B was not started.
- Risks: any later source-schema change must fail closed and requires a new versioned contract and
  regression; a generic error category alone is not sufficient evidence of compatibility.
- Reversal condition: replace only with an equally strict versioned schema adapter that preserves
  exact issue attribution and duplicate semantics.
- Commit/experiment: `60df41c` superseded-pending; `preprocess-0001-dicom-pipeline`.

## D-022 - Fail fast on measured throughput and retain a full runtime margin

- Date: 2026-08-10
- Owner: Codex
- Question: How should Chunk 5 recover after a correctly authenticated full-data Run A attempt
  exhausted its 21,600-second self-deadline during processing?
- Alternatives: waive the deadline; reduce full-data or QA coverage; extend the timeout alone;
  export detailed private profiling; or remove semantics-neutral hot-path work and admit the full
  pass only after a bounded authenticated throughput projection.
- Evidence: freeze `60df41c` / bundle `3dc575...` passed input authentication, then Run A `r3`
  failed closed with `self_deadline_exceeded` at 21,664 seconds. Run B was not started. Source review
  found two repeated costs that do not change model tensors or provenance: the ephemeral NPY cache
  forced durability and reread every file solely to compute its checksum, and invariant installed-
  package versions were resolved for every series. The old two-event safe log could not localize
  progress within processing. No private identities, paths, counts, pixels, or detailed artifacts
  were exported for this diagnosis.
- Decision: write each canonical NPY once while streaming its SHA-256, without an ephemeral `fsync`
  or checksum reread; cache invariant runtime-library versions once per process; and emit only the
  fixed authenticated phase/quarter sequence. Before the full pass, process at most 120 studies
  from the existing authenticated priority-1 stratified source-manifest sample through the same
  series, cache, and source-reconciliation path. Fail closed when the sample elapsed time plus the
  larger series- or file-scaled full-pass projection plus a 3,600-second post-pass reserve exceeds
  the remaining budget. Set the self-deadline to 27,000 seconds and outer kill to 28,800 seconds,
  preserving 1,800 seconds between them and 3,600 seconds below the verified 32,400-second ceiling.
- Current evidence: the working-tree implementation has focused regression evidence only. The
  complete exact-set local gate, new clean freeze, immutable bundle, authenticated Run A, Run B,
  comparison, benchmarks, and human review remain pending. The projection is a fail-fast admission
  control, not proof that either complete run fits.
- Risks: the bounded sample may underrepresent a slower private tail, and post-pass replay or
  benchmarks may still exhaust the reserve. Any projection failure, deadline failure, missing or
  reordered safe event, output mismatch, or incomplete terminal accounting blocks promotion.
- Reversal condition: replace only with a measured approach that retains full authorized-data and
  review coverage, equal deterministic/privacy guarantees, and at least the same competition-
  runtime margin.
- Commit/experiment: `60df41c` superseded-pending; next freeze pending;
  `preprocess-0001-dicom-pipeline`.
- Status: **superseded by D-023** for Chunk 5 execution staging and capacity admission. The
  semantics-neutral cache optimizations and fixed safe progress events remain valid.

## D-023 - Separate deterministic full passes from one capacity-gated QA materialization

- Date: 2026-08-11
- Owner: Luvi-1 and Codex
- Question: How should Chunk 5 preserve independent full-data determinism while fitting private QA
  replay, rendering, and benchmarks after the fourth Run A attempt completed the full pass but
  failed its superseded cohort selector?
- Alternatives: retain the monolithic Run A/Run B workflow; impose a fixed maximum cohort size;
  weaken coverage; add another private kernel or data reference; or make Run A/Run B prove only the
  deterministic full-pass outputs and let the existing review-plan kernel materialize QA once after
  exact comparison and capacity admission.
- Evidence: the fourth Run A attempt completed the full-data pass and then failed closed with
  `material_strata_coverage_impossible`; Run B was not started. The superseded selector combined a
  legacy joint-material coverage contract with an arbitrary cap, so the failure did not establish
  that the full pass was nondeterministic or that a valid bounded-registry cohort was impossible.
  The designated checkpoint reviewer classified the checkpoint `REMEDIATION REQUIRED` and advised
  independent full-pass outputs plus lightweight deterministic plans, exact comparison of both
  plans, one later replay/render/benchmark stage in the existing review-plan kernel, no arbitrary
  cohort maximum, bounded semantic registry categories, an identity-bound capacity certificate,
  and separate full-pass and QA-preparation smoke estimates.
- Decision: Run A and Run B each perform exactly one complete full-data pass and produce a canonical
  manifest, deterministic metrics, and a deterministic cohort plan. The comparator requires exact
  manifest and cohort-plan bytes and exact deterministic metrics. Only after that comparison, the
  existing version-1 review-plan kernel authenticates a capacity certificate bound to the freeze,
  bundle, manifest, both runs, cohort plan, and renderer, then replays selected series, renders each
  twice, runs the representative decode/preprocessing/resource benchmarks once, and materializes
  the private review plan. No new kernel or private data reference is added. The safe UI, first-
  operation `START` gate, nine fixed human checks, and finalizer boundary are unchanged.
- Selection contract: selector v3 has a minimum review target but no arbitrary study maximum. It
  uses exact deterministic incremental greedy selection until every required represented value
  satisfies its quota in bounded semantic registries. Site-domain membership is exposed to the
  selector only through `missing`, `singleton`, `rare_2_4`, `represented_5_19`, and
  `represented_20_plus` buckets; no high-cardinality composite is a registry category. Physical
  file, byte, time, and disk limits remain fail-closed admission gates. The only public registry-
  coverage claim is `all_required_represented_registry_values_satisfy_quotas`; the legacy joint-
  material census and coverage claim are removed.
- Current evidence: D-026 passed its complete gate with pytest 528/528 and produced recovery-
  iteration-8 freeze `4958c4a` and immutable bundle `09502a...`. Its private version-1 inputs,
  standalone smoke, and full-data Run A authenticated and passed. Run B version 1 reached
  `COMPLETE` at 25,940 seconds; two independent bounded read-only polls 71 seconds apart agreed, and
  the established authenticated validator returned
  `dicom_qa_output_validation=PASS mode=workflow stage=run-b`. The protected registry row is
  terminal `blocked`: input, smoke, Run A, and Run B are `passed`; comparison, `review_plan`, and
  `human_review` are `not_started`; `completed_utc` is set; and integrity, foreign keys, and mode are
  `PASS`. Frozen-source preflight had found the two D-027 plan-contract defects before comparison
  launch. UI/session creation and final validation were not launched. This is Run B workflow-output
  validation only, not Chunk 5 PASS or comparison, determinism, QA, review, or performance evidence.
  Because D-027 and D-028 change source, iteration-8 comparison and QA must never launch, and the
  chain cannot be spliced into iteration 9.
- Risks: an eligible population can legitimately require more than the minimum review count; a
  physical capacity gate can still block QA materialization; a mismatch in any of the three
  deterministic outputs blocks the review stage; and sampled smoke estimates may miss a slower
  tail. None permits reducing coverage after observing private results.
- Reversal condition: replace only with a workflow that preserves two independent complete
  full-data proofs, exact plan comparison, every required represented bounded-registry quota, the
  same physical and privacy gates, and equally strong human-review binding.
- Commit/experiment: `4958c4a` / `09502a...` are superseded-pending by D-027; recovery iteration 8
  is terminal `blocked` after passing inputs, smoke, Run A, and Run B; every downstream stage remains
  `not_started` or unlaunched.

## D-024 - Admit only the observed Kaggle wrapper log beside smoke output

- Date: 2026-08-11
- Decision: when official Kaggle CLI 2.2.4 retrieves the allowlisted performance-smoke summary,
  accept at most one additional root file whose basename matches the existing safe-log pattern.
  Bound that log to 2 MiB and scan it with the exact run canary and downloadable sensitive-data
  policy. Continue to require exactly one summary and reject every symlink, nonregular entry,
  nested log, extra file, or extra directory.
- Reason: the authenticated remote listing already allowed one execution log, and observed CLI
  behavior always materialized it even when a file pattern requested only the summary. Requiring
  exactly one local file therefore rejected a valid completed smoke without strengthening privacy.
- Evidence: the corrected boundary passed 11 focused tests and a privacy-safe probe against the
  completed recovery-iteration-5 smoke; canary and patient-identifier log fixtures fail closed.
- Remote result: the complete replacement gate produced freeze
  `1c4470e8a9557141682a81737981271635db7fdc` and bundle
  `9e6be825c219f458c79fa1599feb82ace33d97dade441858fa53656820e6fda4`; recovery iteration 6 then
  authenticated its inputs and passed the standalone smoke-output workflow. The later Run A error
  is a separate cohort-plan defect.
- Reversal condition: replace only if a pinned official client provides a stronger exact-output
  retrieval primitive without the wrapper log.

## D-025 - Bind cohort-plan dimensions and representatives to the selected cohort

- Date: 2026-08-13
- Owner: Luvi-1 and Codex
- Question: How should recovery proceed after the iteration-6 Run A failure classified as
  `phase=processing`, `code=private_cohort_plan_invalid`?
- Evidence: the bounded exact-reference failure-log classification passed without releasing private
  rows or identifiers. Source tracing found that `SelectedStudy` serialized every dimension carried
  by the internal `CohortStudy`, including legacy/internal dimensions outside the exact 25-dimension
  review-plan schema. The same trace found a latent binding defect: small/median/large representative
  series were selected from the global eligible population rather than the selected study cohort.
- Decision: filter each serialized selected-study dimension through the existing exact review
  registry, select the cohort before representative profiles, and restrict the representative pool
  to selected study identifiers. Preserve the selector, quotas, plan schema, and all fail-closed
  validation; do not widen the schema or relax the validator.
- Verification: the two source/test files passed all 46 focused full-run tests, Ruff check and
  format, strict mypy, and the diff check, then passed the complete exact-set gate. Recovery-
  iteration-7 freeze `e3c6334` / bundle `5fe504...` authenticated its inputs and smoke; independent
  full-data Run A and Run B both passed. Iteration-8 freeze `4958c4a` / bundle `09502a...` retained
  the correction through authenticated inputs, smoke, and full-data Run A and Run B; the latter
  reached `COMPLETE` and passed authenticated workflow-output validation. Its protected row is
  nevertheless terminal `blocked` before comparison. The later comparison-output and review-plan
  contract defects are independent and do not reverse the D-025 diagnosis.
- Consequence: preserve r7 and r8 as historical provenance at their exact attained stages. The r9
  16-file candidate has passed its first complete release gate; after D-015's immediate identical
  post-governance rerun, it still requires a new freeze/commit, bundle, private version-1 dataset
  chain, smoke, Run A, Run B, and comparison workflow before QA materialization may start.
- Reversal condition: replace only with an equally strict solution that emits exactly the frozen
  25-dimension schema and proves every representative belongs to the selected cohort.

## D-026 - Admit one bounded Kaggle wrapper log beside the exact comparison summary

- Date: 2026-08-13
- Owner: Luvi-1 and Codex
- Question: How should the comparison-output boundary handle the official Kaggle CLI 2.2.4
  retrieval layout without weakening privacy or accepting ambiguous output?
- Evidence: recovery iteration 7 used freeze `e3c6334` / bundle `5fe504...`; its private inputs,
  smoke, Run A, and Run B authenticated and passed. The comparator kernel reached `COMPLETE` and
  the producer was correct. Workflow validation nevertheless failed closed with
  `comparison_output_layout_invalid` because the CLI unconditionally materialized one root wrapper
  log beside the requested comparison summary while the local validator required one file total.
  The append-only r7 registry row is terminal failed. Review-plan materialization, UI/session,
  human review, and finalization were not started.
- Decision: change only the comparison-output validator and its regression file. Require the exact
  comparison-summary path. Permit at most one root wrapper log under the existing bounded-size and
  privacy-scan policy. Reject every extra file or directory, wrong-path summary, symlink, special
  file, oversized log, canary hit, or sensitive content. Do not relax comparison semantics or the
  producer.
- Verification: the focused and complete exact-set gates passed with pytest 528/528, producing
  recovery-iteration-8 freeze `4958c4a` and immutable bundle `09502a...`. Its private inputs, smoke,
  and full-data Run A authenticated and passed. Run B version 1 reached `COMPLETE` at 25,940
  seconds; two independent bounded read-only polls 71 seconds apart agreed, and the established
  authenticated validator returned `dicom_qa_output_validation=PASS mode=workflow stage=run-b`.
  The protected row is terminal `blocked`, with input/smoke/Run A/Run B `passed`,
  comparison/`review_plan`/`human_review` `not_started`, `completed_utc` set, and integrity, foreign
  keys, and mode `PASS`. Comparison was not launched, so remote acceptance of the D-026 retrieval
  boundary is not proved. The r9 D-027/D-028 candidate has passed its first complete release gate;
  D-015 requires the immediate identical post-governance rerun before freeze. Neither r7 nor r8 may
  be spliced into the fresh chain.
- Reviewer state: the checkpoint relay could not connect to Chrome, so no new reviewer response or
  decision exists. The user's standing authorization for Chunk 5 recovery remains controlling.
- Consequence: Chunk 5 remains not passed. Comparison, review-plan materialization, UI/session
  creation, human review, and finalization remain blocked until the D-027 replacement chain reaches
  and validates each gate in order.
- Reversal condition: replace only if a pinned official client supplies a stronger exact-output
  retrieval primitive while preserving the same fail-closed privacy and layout checks.

## D-027 - Bind review-plan validation to the frozen producer contracts

- Date: 2026-08-14
- Owner: Luvi-1 and Codex
- Question: How should recovery proceed when frozen-source preflight shows that a valid review-plan
  producer output cannot satisfy its local consumer validator?
- Evidence: before iteration-8 comparison launch, two independent P1 defects were confirmed. First,
  the finalizer requires six artifacts per review group and permits `orthogonal.png` only when the
  source geometry supports it, while the remote-listing validator required exactly seven artifacts.
  Second, automatic materialization emits `dicom_qa_review_started`, the four frozen
  `dicom_qa_plan_progress` events, and `dicom_qa_review_template_complete`, while local validation
  expected the generic full-run start and completion events. Either mismatch would reject a valid
  plan after expensive remote work. Neither is a DICOM, determinism, input-authentication, or
  privacy failure.
- Decision: change only `scripts/validate_dicom_qa_output.py` and
  `tests/test_dicom_qa_packaging.py`. Bind listing validation to the finalizer's exact
  `REQUIRED_SUFFIXES` and `ALLOWED_SUFFIXES`: require all six mandatory artifacts, permit only the
  optional orthogonal view, and preserve duplicate, extra-entry, wrong-path, symlink, special-file,
  size, canary, and sensitive-content rejection. Validate the actual automatic start, four progress,
  and completion events. Do not change the producer, renderer, cohort, review, or privacy contract.
- Verification: focused checks passed 9/9; the complete packaging file passed 147/147; Ruff check
  and format passed; strict mypy passed for the validator; the pre-governance implementation diff
  was exactly the two declared source/test files; and an independent red-team returned PASS with no
  P0/P1. Combined with D-028, the exact r9 candidate passed its 529/529 gate and produced freeze
  `1db805e` / bundle `28457d...`; the later dependency-wheel content rejection is independent of the
  D-027 producer/consumer fix. No r9 remote artifact exists. The first r10 D-029 gate on exact
  staged tree `5bea3c110e100e9ddd2d94c8b89c29e1f0ff82a0` is superseded by D-030. Independent
  auth and runbook red-teams now pass with no P0/P1. The first exact 24-file D-015 gate passed on
  tree `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260`; this byte-changing governance
  reconciliation requires its immediate identical fully restaged rerun before the new freeze,
  bundles, and private chain.
- Consequence: iteration 8 is terminal `blocked` after authenticated Run B workflow-output
  validation. This is not Chunk 5 PASS or comparison, determinism, QA, review, or performance
  evidence. Because this decision changes frozen source, iteration-8 comparison and every QA/review
  stage must never launch; its successes cannot be spliced into iteration 9.
- Reversal condition: replace only with an equally strict single producer-consumer contract that
  preserves the same artifact, event, privacy, and output-layout boundaries.

## D-028 - Treat every operational contract section as material drift

- Date: 2026-08-14
- Owner: Luvi-1 and Codex
- Question: Which canonical competition-contract sections must block a release when changed or
  removed?
- Evidence: the material-drift checker covered the core competition fields but omitted
  `efficiency_prize`, `external_assets`, `team_and_sharing`, `license`, `winner_obligations`, and
  `ambiguities`. Mutation or wholesale removal of any omitted section could therefore return
  `contract_drift=no`, even though the change could alter legal, privacy, sharing, asset, eligibility,
  or delivery obligations.
- Decision: add those six names to the existing `MATERIAL_SECTIONS` set. Extend the existing
  `tests/test_smoke.py` coverage to mutate and wholly remove every material section. Add no dependency,
  helper layer, configuration surface, or abstraction.
- Verification: smoke checks pass 6/6; the combined focused set passes 155/155; Ruff check and format
  pass; mypy passes across 25 `src` files and nine trust-boundary files; an independent current-source
  check returns `contract_drift=no`; and the post-fix red-team returns PASS with no P0/P1. The r9
  529/529 gate retained this correction in freeze `1db805e`; the later dependency-wheel content
  rejection is separate. The first r10 D-029 gate on exact staged tree
  `5bea3c110e100e9ddd2d94c8b89c29e1f0ff82a0` is superseded by the D-030 trust-boundary
  correction. Independent auth and runbook red-teams pass with no P0/P1. The first exact 24-file
  D-015 gate passed on tree `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260`; this byte-changing
  governance reconciliation requires its immediate identical fully restaged rerun before a new
  freeze, bundles, and fresh remote chain.
- Consequence: no release, freeze, bundle, or remote replacement chain may proceed on the prior
  narrow drift proof. Iteration 8 is preserved only as terminal `blocked` historical evidence after
  authenticated Run B workflow-output validation. Because this decision changes frozen source, its
  comparison and QA must never launch; the downstream block remains controlling.
- Reversal condition: replace only with an equally fail-closed checker that proves mutation and
  removal sensitivity for every operational contract section.

## D-029 - Sanitize dependency wheels once in the shared manifest-bundle helper

- Date: 2026-08-14
- Owner: Luvi-1 and Codex
- Question: How should offline bundles exclude dependency-wheel medical payloads without duplicating
  policy across the manifest and DICOM-QA packagers?
- Evidence: the r9 exact candidate passed the 529/529 gate and produced freeze `1db805e` / bundle
  `28457d...`; all non-content bundle checks passed. Before upload, final content inspection found
  that pinned upstream `pydicom 3.0.2` contributes aggregate 104 `.dcm` members and 188 members with
  the standard `DICM` preamble. The bundle was rejected, no r9 remote artifact exists, and the r9
  registry row is terminal `blocked` with every remote stage `not_started` and reason
  `dependency_wheel_medical_payload_detected`. The same shared helper built the
  `audit-0002-manifest-remediation` bundle.
- Decision: implement the sanitizer only in `scripts/package_manifest_bundle.py` and
  `tests/test_manifest_packaging.py`. In the existing `package_manifest_bundle` path, use the Python
  standard library to remove the general test tree plus every `.dcm`, `.dicom`, or standard
  `DICM`-at-byte-128 member; regenerate wheel `RECORD` deterministically; validate every other wheel
  fail-closed; and preserve runtime modules, distribution metadata, licenses, and offline preflight.
  Add no dependency, packager-specific branch, helper layer, or configuration surface. Rebind the
  existing DICOM-QA source-audit constants and fixtures to the required audit-0003 successor.
- Verification: the exact two-file source/test diff passes its focused checks and both packaging
  suites. The first r10 candidate passed on exact staged tree
  `5bea3c110e100e9ddd2d94c8b89c29e1f0ff82a0`: pytest 530/530; isolated wheel
  build/install/import; Ruff check/format; mypy over 25 source and nine trust-boundary files;
  audit/configuration/submission; contract schema and current `contract_drift=no`; pre-commit;
  privacy checks; `pip-audit`; exact inventory and unchanged-tree checks. D-030 preflight
  then found additional trust gaps, so that gate is superseded. Current non-final evidence after the
  minimal correction is focused root/authentication 8/8; pytest 537/537; manifest plus DICOM-QA
  packaging 204/204; Ruff check/format; mypy over 25 package and 11 trust-boundary files; and scoped
  diff, shell, and privacy checks; independent auth and runbook red-teams both pass with no P0/P1.
  The first complete exact staged D-015 gate then passed on tree
  `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260` over exactly 24 files with the full checks
  recorded in D-015. This governance reconciliation changes bytes; an immediate identical fully
  restaged rerun is required, and a PASS without further mutation fixes `complete_final_gate=PASS`.
- Consequence: `audit-0002-manifest-remediation` remains valid historical scientific evidence but is
  superseded as a reusable source root. The new `audit-0003-wheel-sanitization` experiment contract
  must complete and validate `manifest-v2` before a new DICOM-QA bundle is bound to that output. Do
  not delete or reuse any old remote artifact; do not reuse r9 freeze/bundle evidence; run the full
  fresh chain. Chunk 5 remains not passed, and every downstream or Chunk 6 stage remains blocked.
- Reversal condition: replace only with an equally small shared, deterministic, fail-closed wheel
  policy that excludes the same payload classes while preserving the same runtime, metadata,
  license, and offline guarantees.

## D-030 - Authenticate the exact manifest deployment before promotion

- Date: 2026-08-14
- Owner: Luvi-1 and Codex
- Question: How should the audit-0003 manifest dataset and kernel be proved identical to the locally
  checked candidate without exposing private remote references or duplicating remote validators?
- Evidence: after the first r10 candidate passed 530/530 on staged tree
  `5bea3c110e100e9ddd2d94c8b89c29e1f0ff82a0`, preflight found that the project wheel did not
  enter the shared medical-payload archive guard; the local runbook did not exact-allowlist and hash
  the actual two-file kernel upload; remote stages could skip wheel/`RECORD` validation; and the
  deployment path lacked complete exact dataset/kernel version-1 content, source-graph, listing,
  and race authentication. Raw status/private-reference-capable commands and an unscoped credential
  path also violated the fixed-output boundary. A final root-trust check found that the initial
  authenticator could read dataset metadata and scan wheels from a safe sibling directory distinct
  from the verified bundle-manifest root. No audit-0003 remote artifact had been launched.
- Decision: extend the existing `package_manifest_bundle` wheel guard to the project wheel. Add one
  local `authenticate_manifest_deployment` script that directly reuses the established DICOM-QA
  version-1 helpers. Before any network operation, every stage must validate the exact two-file
  local kernel and hash and every project/dependency wheel plus `RECORD`; resolved dataset metadata
  must belong to the exact bundle-manifest parent and kernel metadata to its exact sibling kernel
  directory. Authenticate exact private
  dataset version-1 files and hashes, exact kernel version-1 code and source graph, complete stable
  listings, and before/after race snapshots. Emit only fixed authentication tokens or
  `PENDING`/`RUNNING`/`COMPLETE`/`ERROR`; use a command-scoped token, protected logs, explicit `/1`
  references, and bracketed gates. Add no dependency, framework, or new validator abstraction.
- Verification: the mismatched-root regression proves zero remote calls. Focused root/authentication
  checks pass 8/8; pytest passes 537/537; manifest plus DICOM-QA packaging passes 204/204;
  Ruff check/format; mypy over 25 package and 11 trust-boundary files; and scoped diff, shell, and
  privacy checks; independent auth and runbook red-teams both pass with no P0/P1. The first complete
  exact staged D-015 gate passed on tree `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260` over
  exactly 24 files with every check recorded in D-015. This governance reconciliation changes bytes,
  so an immediate identical fully restaged rerun is required; a PASS without further mutation fixes
  `complete_final_gate=PASS`. The 530/530 gate on tree
  `5bea3c110e100e9ddd2d94c8b89c29e1f0ff82a0` remains superseded.
- Consequence: no r10 freeze, bundle, dataset, kernel, or audit-0003 remote evidence exists. Restage
  and fully gate the exact corrected candidate before creating a replacement freeze and sanitized
  manifest bundle. Then run the full authenticated audit-0003 and DICOM-QA chain in order. Chunk 5
  remains not passed; comparison, QA, human review, every downstream stage, and Chunk 6 stay blocked.
- Reversal condition: replace only with a smaller equally fail-closed path that proves the same
  local root/wheel/kernel identity, exact private version-1 remote content/source identity, stable
  listings, race freedom, and fixed-output privacy boundary.
