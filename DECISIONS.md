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
  correction, the historical first complete exact staged D-015 gate passed on tree
  `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260` over exactly 24 files: pytest 537/537;
  offline locked reinstall and lock; isolated wheel build/install/import; tracked MIME, symlink, and
  sensitive guard; Ruff check/format; mypy over 25 package and 11 trust-boundary files;
  config/submission; contract schema and current `contract_drift=no`; schema bytes; pre-commit;
  detect-secrets; `pip-audit` with no vulnerabilities; and diff, inventory, and unchanged-tree PASS.
  That 24-file result is historical and superseded by the later validator, throughput, governance,
  and contract-snapshot changes. Exact 15-file tree
  `afd8909a798d30fa9314fe6568768bca68fbda14` then passed its complete D-015 gate: locked offline
  lock/sync; isolated wheel build and offline install/import; tracked MIME, exact `.agents/skills`
  symlink, and sensitive guard; Ruff check/format; mypy over 25 package plus 16 trust-boundary files;
  pytest 538/538; config audit and synthetic submission; contract schema and current
  `contract_drift=no`; generated schema bytes; pre-commit and full tracked detect-secrets;
  `pip-audit` with no vulnerabilities; and cached diff, exact 15-file inventory, no unstaged or
  untracked residue, and unchanged-tree checks. That PASS is now historical and superseded. After
  the governance bytes were restaged, exact tree
  `e298964891b214bfbf4dc06725f2cde3b3bd3f74` failed the mandatory pytest rerun with one failure and
  537 passes because `tests/test_manifest_runner.py` compared nondeterministic real wall-clock
  `runtime.elapsed_seconds`: the first run reported 3 seconds and the rerun 2 seconds. Production
  intentionally records `ceil(monotonic - start)`, and its validators accept an integer from zero
  through the configured maximum, so production, disclosure, and schema contracts are correct. The
  minimal test-only correction reuses `_validate_exact_aggregates` on the rerun and compares every
  aggregate section except `runtime`, while retaining exact table-hash, study-key, QA-byte, and
  audit-key equality. The focused target passed 3/3 repeatedly, the complete manifest-runner file
  passed 12/12, and Ruff check/format plus the scoped diff check pass. Exact staged tree
  `22c80aaa8f30d47a21e1a43fc3e945ab831c79ea` then passed the first complete 16-file D-015 gate:
  locked offline `uv` lock/sync; full pytest 538/538 in 63.84 seconds; isolated wheel build, offline
  install, and import of `rsna-knee 0.1.0`; Ruff PASS with 124 files formatted; mypy over 25 package
  plus 16 trust-boundary files; valid configuration with the established hash and synthetic
  submission `rows=2`; canonical contract schema valid, current `contract_drift=no`, and generated
  schema bytes current; sensitive guard PASS; tracked MIME exact at 154 regular files plus the one
  exact `.agents/skills` symlink; `pip-audit` with no known vulnerabilities; all pre-commit hooks
  PASS; full tracked detect-secrets PASS; and exact 16-file inventory, no unstaged or untracked
  residue, and unchanged-tree PASS. This eight-file governance reconciliation changes bytes, so
  D-015 requires one immediate fully restaged identical complete rerun. Only PASS with no later byte
  change fixes `complete_final_gate=PASS`; any failure invalidates the first-pass final-gate evidence
  and requires this record to be corrected. Final red-team remains pending.
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
  16-file candidate and its release gate are historical and superseded. The later 15-file PASS and
  failed restaged tree are also historical and superseded. Exact 16-file tree
  `22c80aaa8f30d47a21e1a43fc3e945ab831c79ea` passed its first complete D-015 gate, but these
  governance bytes require the immediate fully restaged identical complete rerun and final red-team
  before preparation. Current authorization still permits only a fully prepared fresh successor
  smoke; Run A requires authenticated smoke validation and a fresh decision.
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
  boundary is not proved. The r9 D-027/D-028 release-gate result is historical and superseded by later
  source, governance, and contract-snapshot changes. Neither r7 nor r8 may be spliced into a fresh
  chain. The 15-file PASS and failed restaged tree are historical and superseded. The first 16-file
  complete gate passed, but no freeze or smoke may proceed before the fully restaged identical rerun
  and final red-team pass with no later byte change.
- Historical reviewer state: the checkpoint relay could not connect to Chrome, and the then-current
  smoke-only checkpoint did not authorize Run A. The later r14 authorization and outcome supersede
  that operational boundary.
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
  auth and runbook red-teams now pass with no P0/P1. The exact 24-file D-015 result on tree
  `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260` is historical and superseded. The later 15-file PASS
  and failed restaged tree are also historical and superseded. The first 16-file complete gate
  passed, but these governance bytes require the fully restaged identical rerun and final red-team.
  Even after PASS with no later byte change, only the prepared fresh successor smoke is authorized
  until authenticated validation and a fresh Run A decision.
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
  correction. Independent auth and runbook red-teams pass with no P0/P1. The exact 24-file D-015
  result on tree `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260` is historical and superseded. The
  later 15-file PASS and failed restaged tree are also historical and superseded. The first 16-file
  complete gate passed, but these governance bytes require the fully restaged identical rerun and
  final red-team before any clean freeze, deterministic bundle, identity-absence proof, registry
  preparation, or successor smoke.
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
  The historical first complete exact staged D-015 gate then passed on tree
  `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260` over exactly 24 files with the full checks
  recorded in D-015. That 24-file result is superseded. The later 15-file PASS and failed restaged
  tree are also historical and superseded. The first 16-file complete gate passed, but these
  governance bytes require the fully restaged identical rerun and final red-team;
  `complete_final_gate=PASS` remains unset.
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
  privacy checks; independent auth and runbook red-teams both pass with no P0/P1. The historical
  exact staged D-015 gate passed on tree `cdb28c0d1e98dd9c9ce18b7fc1ca415262ff0260` over
  exactly 24 files with every check recorded in D-015. That result is superseded. The later 15-file
  PASS and failed restaged tree are also historical and superseded. The first 16-file complete gate
  passed, but these governance bytes require the fully restaged identical rerun and final red-team;
  `complete_final_gate=PASS` remains unset. The 530/530 gate on tree
  `5bea3c110e100e9ddd2d94c8b89c29e1f0ff82a0` remains superseded.
- Consequence: **amended by D-031.** D-030 subsequently authenticated the r10 source and deployment
  chain through input, smoke, Run A, Run B, and comparison. Review-plan v1 then failed safely at
  input discovery; the r10 registry is terminal `failed` and cannot be resumed or spliced.
- Reversal condition: replace only with a smaller equally fail-closed path that proves the same
  local root/wheel/kernel identity, exact private version-1 remote content/source identity, stable
  listings, race freedom, and fixed-output privacy boundary.

## D-031 - Scope automatic review-plan discovery to authenticated source mounts

- Date: 2026-08-16
- Owner: Luvi-1 and Codex
- Question: How should recovery proceed when an authenticated review-plan kernel fails before source
  selection because generic basename discovery walks the legitimate competition tree?
- Evidence: r10 input authentication, performance smoke, Run A, Run B, and exact comparison all
  passed their authenticated workflow validators. Review-plan version 1 reached `ERROR`; two bounded
  read-only status checks 93 seconds apart agreed. The frozen privacy/canary failure validator passed
  and released only `input_discovery_invalid`. The authenticated kernel source graph was exact. Static
  tracing showed that the shared `/kaggle/input` basename walk entered the official competition's
  legitimate `train_series` directory before selecting a source; that directory has more than 4,096
  study entries and correctly tripped the generic discovery count gate. No review artifact, pixel,
  UI/session, human review, or finalizer stage was accessed or created. The r10 registry is terminal
  `failed`.
- Decision: change only `kaggle/dicom_qa/finalize_review.py` and its existing focused identity test.
  Search one level below the base input root, and resolve kernel outputs only beneath the exact
  derived kernel mount. Reuse the existing optional-one helper and preserve all symlink, duplicate,
  entry-count, file-type, and error gates. Add no dependency, configuration, fallback search,
  abstraction, log access, or privacy exception.
- Verification: independent exact two-file red-team passes with no P0/P1; focused identity passes
  41/41; boundary matrix 12/12; combined identity plus packaging 188/188; full development pytest
  537/537. The historical first exact staged D-015 gate passed on tree
  `959f14e9422db9670d16683ba8effe681cf6641d` over exactly 10 files: locked offline reinstall/lock;
  isolated wheel build/install/import; tracked MIME/symlink and sensitive guards; Ruff check/format;
  mypy over 25 package and 11 trust-boundary files; pytest 537/537; config and synthetic-submission
  checks; contract schema plus protected current `contract_drift=no`; generated-schema byte check;
  pre-commit and detect-secrets; `pip-audit` with no vulnerabilities; cached diff, exact inventory,
  and unchanged-tree PASS. That 10-file result is historical and superseded. The later 15-file PASS
  and failed restaged tree are also historical and superseded. The first 16-file complete gate
  passed, but these governance bytes require the fully restaged identical rerun and final red-team;
  `complete_final_gate=PASS` remains unset.
- Consequence: r10 remains terminal historical evidence through comparison only. The former r11
  execution instruction is superseded. Current authorization stops at one fully prepared fresh
  successor smoke; authenticated terminal/output validation and a fresh decision are required before
  Run A. Chunk 5, private QA, every downstream stage, and Chunk 6 remain blocked.
- Reversal condition: replace only with a smaller equally source-scoped discovery rule that retains
  the same exact mount binding and every current fail-closed trust and privacy gate.

## D-032 - Re-freeze after the live contract refresh before r11 remote work

- Date: 2026-08-20
- Owner: Luvi-1 and Codex
- Question: What source and registry identity may authorize the next private DICOM-QA action after
  the aggregate-only contract refresh?
- Evidence: the official Kaggle MCP refresh at `2026-08-20T08:02:22Z` found no material contract
  drift. The exact six-file documentation refresh passed the complete D-015 gate and froze commit
  `2723ff4a1692d5d897234e67aba167c629017f9b`. The replacement DICOM-QA packager, verified-policy,
  synthetic/offline preflight, and packaging suites passed for bundle
  `efe087afd5bb8f5391213e359c52b88f5930975c837b813ee98affe3f1fb9921`. An append-only r12 registry
  successor is `planned` with all remote stages `not_started`; no r12 remote resource exists.
- Decision: use only the r12 freeze, bundle, and planned registry successor. Treat r10 and the old
  r11 candidate as historical, do not mutate or splice them, and perform one protected metadata-only
  derived smoke-identity absence check before any version-1 private/offline push. A non-`ABSENT`
  result is an access/infrastructure blocker, not evidence of absence or failure.
- Consequence: Chunk 5, Run A/B, comparison, review-plan, UI, human review, finalizer, and Chunk 6
  remain blocked until the fresh r12 chain passes each exact authenticated validator.
- Current update: this 2026-08-20 decision and its six-file gate are historical and superseded for
  current action by `docs/competition_contract/2026-08-21T200304Z.md`. The later 15-file PASS and
  failed restaged tree are also historical and superseded. The first 16-file complete gate passed,
  but these governance bytes require the fully restaged identical rerun and final red-team.
  Identity-verification state is unavailable and fail closed. After every recorded prerequisite
  passes, only a fresh successor smoke is in scope; Run A requires its authenticated terminal/output
  validation plus a fresh decision.
- Reversal condition: only a new complete gate and new immutable bundle may replace this identity;
  no tracked byte or remote artifact may be reused across freezes.

## D-033 - Bind failure validation to the producer's exact state machine

- Date: 2026-08-21
- Owner: Luvi-1 and Codex
- Question: How should a terminal performance-smoke failure be validated when its producer uses a
  different closed event protocol from the full-run producer?
- Evidence: exact r13 performance-smoke version 1 authenticated and reached terminal `ERROR` after
  input authentication passed. The smoke producer emits smoke-specific start, progress, and failure
  events across `bundle`, `authentication`, `performance_smoke`, and `output`; the generic consumer
  accepted only full-run events and phases. It therefore reduced every otherwise well-formed caught
  smoke failure to `failure_log_completion_invalid`, masking the safe terminal reason.
- Decision: keep one validator entry point and select the generic or performance-smoke protocol only
  from the first exact start event. For each protocol, require its exact terminal event, phase
  allowlist, ordered progress prefix, and phase-specific permitted prefix length. Reject hybrid,
  reordered, extra, and wrong-phase events. Preserve the generic path and CLI unchanged; add one
  focused regression rather than a new option, abstraction, dependency, or permissive fallback.
- Current evidence: the corrected strict validator classifies the exact authenticated r13 failure as
  `phase=performance_smoke`, `code=throughput_projection_exceeds_budget`. The registry is terminal
  `failed`, input authentication is `passed`, and Run A, Run B, comparison, review-plan, and human
  review are `not_started`. No rerun or splice occurred.
- Consequence: the 15-file tree containing the validator/test protocol correction, separate budget-
  formula correction, eight governance files, and latest snapshot passed its complete exact staged
  D-015 gate but is historical and superseded. The failed restaged tree exposed the test-only runtime
  equality defect. The corrected 16-file tree passed its first complete D-015 gate, but these
  governance bytes require the fully restaged identical rerun and final red-team before a clean
  freeze, deterministic bundle, authenticated identity-absence proof, and append-only registry
  preparation. Those prerequisites authorize one fresh immutable successor smoke only. R13 remains
  terminal historical evidence; Run A requires the successor smoke's authenticated terminal/output
  validation and a fresh decision.
- Reversal condition: replace only with an equally strict producer-bound validator that rejects every
  mixed or impossible state and preserves the same privacy, authentication, and immutable-chain gates.

## D-034 - Do not double-charge sample time after splitting the smoke kernel

- Date: 2026-08-21
- Owner: Luvi-1 and Codex
- Question: Which elapsed time belongs in the standalone performance-smoke admission formula after
  smoke and full runs became separate kernels?
- Evidence: the exact r13 safe log contains one smoke progress event, localizing the terminal failure
  to the inner throughput gate. In monolithic freeze `a36b053`, smoke and the full pass shared one
  27,000-second kernel, so charging sample elapsed time before the projected full pass was correct.
  Freeze `01ea270` moved smoke to a standalone 3,600-second kernel and gave each later full run the
  full 27,000-second budget, but both admission sites retained
  `elapsed + projected_full_pass + reserve`. The current run contract confirms that neither sample
  work nor smoke work is repeated inside Run A or Run B.
- Decision: remove only the stale leading sample `elapsed +` from both shared admission sites. Keep
  pre-smoke setup accounting in the standalone entry point, the conservative full-pass projection,
  the 3,600-second post-pass reserve, self and outer deadlines, finite-value checks, source
  authentication, privacy gates, and every fail-closed error unchanged.
- Verification: existing boundary tests now distinguish 3,801 seconds from 3,799 seconds and fix the
  standalone projected ceiling at 4,320 seconds. Targeted tests and scoped static checks pass. Exact
  15-file tree `afd8909a798d30fa9314fe6568768bca68fbda14` passed its complete D-015 gate with pytest
  538/538 but is historical and superseded. Restaged tree
  `e298964891b214bfbf4dc06725f2cde3b3bd3f74` failed the unrelated nondeterministic runtime-equality
  test with one failure and 537 passes. The minimal test-only correction passed focused 3/3
  repeatedly, the complete manifest-runner file 12/12, Ruff check/format, and the scoped diff check.
  Exact 16-file tree `22c80aaa8f30d47a21e1a43fc3e945ab831c79ea` passed its first complete D-015 gate
  with pytest 538/538 in 63.84 seconds and every check recorded in D-015. These governance byte
  changes require the fully restaged identical complete rerun and final red-team;
  `complete_final_gate=PASS` remains unset.
- Consequence: r13 remains terminal failed and cannot be retried or spliced. A fresh immutable
  successor smoke is still required after the complete gates pass and may fail closed on its own
  measured projection.
- Reversal condition: restore sample elapsed time only if a future run contract again performs that
  sample work inside the same full-run budget and the boundary tests are updated before compute.

## D-035 - Bind review failures and both official Kaggle mount forms

- Date: 2026-08-22
- Owner: Luvi-1 and Codex
- Question: How should the r14 review-plan failure be classified and how should authenticated
  notebook-output sources be found without reopening global input traversal?
- Evidence: r14 inputs, smoke, Run A, Run B, and comparison authenticated `PASS`; review-plan v1 was
  stably terminal `ERROR`. The frozen workflow validator returned `kernel_status_invalid`, and the
  frozen failure consumer rejected the producer's exact review start/progress/failure protocol.
  After the smallest consumer correction, the retained no-match log validates as
  `phase=review`, `code=input_discovery_invalid`. The producer failed before cohort replay. Official
  Kaggle supports direct `<slug>` mounts and collision-safe `<owner>/<slug>` mounts, while the
  frozen helper accepted only the first. Snapshot `2026-08-22T062926Z` records no material drift.
- Decision: extend the shared failure validator with the exact review producer state machine and
  fixed `review` phase. Resolve each derived kernel source only through the exact direct or fully
  qualified mount, require exactly one, and preserve bounded depth, entry caps, symlink/file/type,
  duplicate, and counterfeit-source rejection. Add no broad scan, dependency, fallback heuristic,
  or version-2 repair.
- Verification: focused producer/consumer and automatic-discovery tests pass; both complete DICOM-QA
  identity/packaging files pass. Exact 13-file staged tree
  `b9cf3ab0b5494e1bc85f1cd498b1108d1e7f20b0` passed its first complete D-015 gate with pytest
  539/539, offline build/install/import, Ruff, format, strict mypy, config/submission,
  contract/schema/no-drift, privacy/secrets, zero-vulnerability dependency audit, inventory, and
  residue checks. Release rule: only an identical complete rerun and final red-team PASS on the
  fully restaged tree containing these governance bytes, with no later byte change, fixes
  `complete_final_gate=PASS` and permits a new freeze/bundle or append-only successor.
- Consequence: r14 is terminal failed and cannot be resumed or spliced. Human QA remains
  `not_started`; Chunk 5 is not passed.
- Reversal condition: remove the qualified form only if Kaggle guarantees direct mounts for all
  attached notebook outputs and a target-runtime regression proves that guarantee.

## D-036 - Certify passed cores for stage-aware downstream reuse

- Date: 2026-08-22
- Owner: Luvi-1 and Codex
- Question: May an already-authenticated passed core (inputs, performance smoke, Run A, Run B,
  deterministic comparison) from a recovery chain that later failed at review-plan be formally
  reused by a downstream QA adapter without rerunning the expensive core, without weakening
  reproducibility or provenance?
- Evidence: r14 and r15 both reached five authenticated core-stage passes and then failed only at
  review-plan input discovery (phase=review, code=input_discovery_invalid), each time after
  six-plus hours of core compute. The protected registry preserves these rows append-only, and the
  existing workflow validator already authenticates the exact dataset/kernel identities,
  version-1 pins, source graphs, version-race snapshots, and sanitized output contracts end to end.
  Repeating full chains for downstream-only defects wastes compute and adds no upstream evidence.
- Decision: adopt a stage-aware lineage policy. A terminal-failed chain stays terminal as a whole;
  its independently passed stages may be bound into a Core Execution Certificate when: the stage
  reached authenticated terminal PASS; its output contract is immutable; all source and output
  identities are cryptographically bound; every downstream consumer validates the certificate; no
  upstream semantics changed; and the stage is not mixed with an incompatible lineage. Copying
  arbitrary files from failed runs, mixing Run A and Run B across freezes, consuming unvalidated
  partial artifacts, silently changing preprocessing, or accepting failed or ambiguous core stages
  remain prohibited. The certificate binds lineage identifier, source-input snapshot, dataset
  identity and version, freeze commit, bundle SHA, kernel identities and versions, run-output
  digests, comparison digest, contract versions, preprocessing/canonical-manifest/evidence-ledger/
  QA-registry membership versions, validation timestamps, and validator identity, and states
  core_status=passed, qa_adapter_status=not_passed, human_review_status=not_started. Changing any
  bound field must invalidate verification.
- Verification: tests/test_core_execution_certificate.py proves the offline round-trip against the
  real r15 registry/bundle and rejects every bound-field tamper, status flip, missing row,
  non-reusable failure shape, tampered run summary, and tampered comparison proof. Live end-to-end
  certification re-runs the authenticated workflow gate and is recorded separately once executed;
  a transient host network outage deferred it during this session and blocks no local gate.
- Consequence: r14 and r15 remain terminal failed as whole chains while their certified cores may
  feed an independently versioned QA Adapter. A review-path resolver correction never justifies
  another full Run A/B cycle by itself. Overall Chunk 5 remains not passed until genuine human
  review passes.
- Reversal condition: revoke certified-core consumption if any consumed artifact fails identity
  revalidation, if Kaggle invalidates derived notebook outputs as immutable provenance sources, or
  if a core semantic defect is proven; then require a fresh fully gated chain.

## D-037 - Authenticate the sealed finalizer, never the mutable working tree

- Date: 2026-08-22
- Owner: Luvi-1 and Codex
- Question: When the immutable r15 bundle pins the pre-D-036 finalizer but the local recovery tree
  contains corrected finalizer bytes, how should workflow authentication load the trusted
  finalizer without either weakening the frozen hash pin or falsely failing the already-passed core?
- Evidence: the r15 bundle manifest and packaged dataset both pin and contain finalizer SHA-256
  c1a3b7c2cfa5db14fead0e8e3378c73ab30de41baefeed16481e42c5b8ab64bf; Run A, Run B, comparison,
  and their validators passed against that identity. The default finalizer loader instead read the
  repository working tree, whose D-036 discovery correction necessarily has different bytes.
  Loading that mutable file eagerly caused a false trusted_finalizer_hash_mismatch before remote
  validation. A temporary adapter bypass was rejected because it weakened the frozen pin.
- Decision: keep the frozen finalizer hash absolute. Add an explicit optional source path to the
  authenticated-workflow gate and have CLI certification pass the exact finalize_review.py sealed
  in the verified r15 bundle directory; the normal validator CLI likewise consumes the bundle
  sibling after policy verification. No adapter mode, mismatch allowance, lazy pin, or
  working-tree fallback is permitted. The correction changes validator provenance only and does not
  alter any passed core semantic, output, resolver behavior, or frozen identity.
- Verification: all 63 focused certificate/identity tests pass; selected packaging workflow tests
  pass; full pytest reports 553 passes with exactly three known sandbox-environment failures
  (offline wheel build denied at the user cache and two process-pool semaphore denials); Ruff check
  and format pass on all files; strict mypy passes both configured scopes; sensitive-file guard and
  tracked-Python secret scan pass. Live end-to-end certification remains deferred by the host
  network outage and must be recorded separately when connectivity returns.
- Consequence: core certification can authenticate the exact sealed r15 code despite unrelated
  local review-discovery work. The failed r15 chain remains terminal, and its certificate still
  requires live authentication plus adapter gates before QA-adapter reuse.
- Reversal condition: require working-tree loading only if the project later proves that sealed
  bundle siblings cannot represent deployed producer code, and replace this rule with an equally
  hash-pinned explicit source contract.

## D-038 - Bind the QA adapter to the live-certified r15 core certificate and proven mount forms

- Date: 2026-08-23
- Owner: Luvi-1 and Codex
- Question: After the r15 core passed live end-to-end certification but review-plan still failed
  on input discovery, how should the QA adapter consume the certified core without weakening any
  provenance gate or rerunning A/B?
- Evidence: live certification PASSED at 2026-08-22T22:08:33Z with payload
  f7736e681f54dd9d2ae1ad7cd75a3a1208f7efec4967f6d3bdae99e81cbfa55d and offline verify PASS. The
  single authorized mount-layout diagnostic proved Kaggle mounts inputs under type-prefixed
  parents (competitions/<slug>, datasets/<owner>/<slug>, notebooks/<owner>/<slug>); no legacy
  direct or qualified form was observed at the expected depths.
- Decision: the QA adapter resolver searches exactly these proven forms plus the two legacy forms,
  authenticates candidates by exact marker filenames, rejects duplicates across all four forms,
  rejects symlinks, and preserves bounded entry-count caps. The adapter is bound to the core
  certificate; it may be corrected without rerunning the certified core provided every consumed
  identity remains valid. No core semantics changed; Run A/B/comparison were not rerun.
- Verification: complete local gate on HEAD (1bdcc01): Ruff check/format PASS (127 files),
  strict mypy src PASS (25 files), strict mypy trust-boundary PASS (3 files),
  focused certificate/identity suites 77/77 PASS, full pytest 575/575 exit 0,
  sensitive-file guard PASS.
- Consequence: adapter freeze/bundle may proceed against this certified core; Chunk 5 remains
  technically incomplete until the adapter-only execution chain reaches human visual QA.
- Reversal condition: if a future diagnostic proves additional mount forms or invalidates any
  bound identity, re-open discovery under a new bounded authorization before changing resolver code.

## D-039 - Stage-aware core_reuse binding for certified-core adapter execution

- Date: 2026-08-23
- Owner: Luvi-1 and Codex
- Question: How should the QA adapter consume the live-certified r15 core outputs without
  rerunning A/B/comparison and without weakening any identity gate?
- Evidence: the sealed resolver previously derived all kernel refs from the current commit/bundle
  identity, making certified r15 upstream outputs unreachable. The single authorized mount
  diagnostic proved type-prefixed mount forms; the core certificate binds every upstream identity.
- Decision: add one optional `core_reuse` block to run-config with exactly three fields:
  `core_lineage_id`, `core_certificate_payload_sha256`, and an `upstream_refs` map limited to
  exactly four roles (performance_smoke, run_a, run_b, comparison). The resolver redirects only
  these roles; all downstream adapter identities remain bound to the current commit/bundle.
  Invalid lineage, payload digest, role injection, or malformed refs fail closed with
  review_identity_invalid. The packager accepts --core-reuse JSON and writes it into run-config
  before bundle-manifest sealing. Both finalizer and validator enforce identical validation rules.
- Verification: focused identity tests cover positive redirect, downstream freshness,
  wrong-lineage rejection, short-payload rejection, downstream-role injection rejection, and
  path-like ref rejection; full pytest 575/575 exit 0 on commit d1a2d53; Ruff check/format PASS;
  both strict mypy scopes PASS. Adapter bundle e49ebe396206 built from clean tree at this commit.
- Consequence: the QA adapter can consume certified r15 upstream outputs directly without a new
  core freeze or A/B rerun. Adapter-only corrections may iterate under D-036/D-038 recovery-loop
  bounds while every consumed upstream identity remains valid.
- Reversal condition: if the certified core contract changes or any upstream identity becomes
  invalid, re-certify before adapter reuse; never widen the allowed role set beyond these four.

## D-040 - Seal optional core_reuse inside bundle identity and allow it in the runner schema

- Date: 2026-08-23
- Owner: Luvi-1 and Codex
- Question: Why did adapter input validation fail closed with bundle_verification_failed despite
  a complete remote dataset, and what is the minimal evidence-preserving correction?
- Evidence: every deployed file matched its manifest record, but the runner rejected the deployed
  run-config because its strict key set omitted the post-seal core_reuse addition. Recomputing
  identity returned
  648562a89527d01b3a61eb8f13fd3ad5f2b03415445638024cd1ec407c7b95eb rather than sealed
  cff25c8d5d1ec22658b4835e9f1647d5208bc6d85a096621675a400c19504908.
- Decision: insert an optional core_reuse block before normalized-run-record derivation so bundle
  identity covers it, while retaining all other D-039 semantics. Permit that same single optional
  key in the runner's exact config-key check. Do not mutate DICOM semantics or certified-core
  outputs; this is adapter remediation one of at most two under the authorized loop.
- Verification: a new packager regression builds and verifies a core-reuse bundle through the
  runner; focused packaging and identity checks pass after the change. The failed v1 dataset is
  preserved as evidence and not reused remotely; fresh adapter deployment follows the full gate.
- During the post-change gate, the certifier was additionally corrected to load the policy runner
  from the sealed dataset qa_runner file instead of the mutable working tree; the optional runner
  path parameter defaults to prior behavior so every other caller remains unchanged.
- Consequence: adapter-only repackaging can proceed without rerunning Run A/B/comparison. Any
  further extension must be schema-versioned rather than adding another unversioned key.
- Reversal condition: if authenticating sealed legacy bundles and covered reuse requires weakening
  another invariant, stop and redesign the config contract.

## D-041 - Terminal classification of sealed-policy adapter after validator mismatch

- Date: 2026-08-23
- Owner: Luvi-1 and Codex
- Question: Why did remediation-two adapter validation fail closed at exact authenticated inputs before any remote launch, and what is the evidence-preserving disposition?
- Evidence: D-039 made run-config core_reuse the validator's only reuse input, but D-040/remediation two removed that field from run-config and injected the equivalent policy into the sealed finalizer. On commit 1c4fa7e594ece3752b32281ccc7c23d49814986f, offline reproduction proved that sealed _public_review_identity correctly emits upstream refs bound to d3771e7-61963849d8ec, while validate_dicom_qa_output._workflow_refs -> _apply_core_reuse still derives those roles from the current 1c4fa7e-fd8238f94ef1 identity because it reads only run-config. The one exact authenticated inputs invocation returned dicom_qa_output_validation=FAIL code=review_identity_invalid with exit 2 before Kaggle mutation. Independent checks confirmed certificate verification PASS, deployed dataset ready, plan-kernel identity absent, and all four r15 upstream kernels live COMPLETE.
- Decision: classify this as the third and final authorized adapter attempt under the objective's bounded loop. Do not create a fourth iteration or a third remediation. Preserve commit, bundle SHA fd8238f94ef1f91282b8a9d904c3a273e56e5499779a2b5700b920a1bf42b8cf, and dataset lavicheema/rsna-knee-dicom-qa-bundle-1c4fa7e-fd8238f94ef1 version 1 as immutable failure evidence. A human must choose whether to authorize one narrowly scoped, fully gated validator-only correction that consumes the already-sealed finalizer policy, or abandon the certified-core adapter route.
- Verification: no remote write occurred; no downstream kernel was pushed; plan identity remains absent; registry integrity is OK; protected history unchanged.
- Consequence: review-plan remains blocked pending explicit human decision. The defect is localized to validator/finalizer integration, not core validity or mount layout.
- Reversal condition: only explicit human approval may supersede the limit; a correction must bind validator expectations to the sealed policy, add regressions, rerun the complete gate, and deploy a fresh adapter identity.

## D-042 - Human-approved validator-only correction binding sealed core-reuse policy

- Date: 2026-08-23
- Owner: Luvi-1 and Codex
- Question: May remediation-two's terminal validator mismatch be corrected once, narrowly, without changing DICOM semantics, runner bytes, certified-core evidence, or packaging semantics?
- Evidence: On 2026-08-23 the operator explicitly approved one narrowly scoped validator-only correction, superseding the two-remediation limit recorded by D-041 for exactly this defect. Offline reproduction had proved that the sealed finalizer's CORE_REUSE_POLICY emitted the intended d3771e7-61963849d8ec upstream refs while the validator still derived expectations from run-config and therefore expected 1c4fa7e-fd8238f94ef1 refs.
- Decision: source the validator's certified-core reuse policy from the already-authenticated sealed finalizer module (CORE_REUSE_POLICY) instead of run-config. Apply identical fail-closed checks: exact three-field policy schema, lineage regex, HEX64 certificate payload digest, role allowlist limited to performance_smoke/run_a/run_b/comparison, and owner/slug ref regex. Downstream adapter roles remain bound to the current commit/bundle. Do not modify finalize_review.py, qa_runner.py, run.py bytes, packager semantics, or any certified-core output.
- Verification: regression proves a packaged core-reuse bundle's workflow identity matches the sealed finalizer policy while keeping review_plan bound to the fresh bundle identity, and five malformed-policy cases fail closed with kernel_identity_invalid. Complete local gate on this change against parent d3d2d7c: Ruff format/check PASS (127 files), strict mypy src PASS (25 files), strict mypy trust-boundary PASS (3 files), full pytest 587 passed exit 0, sensitive-file guard PASS, tracked secret scan clean, git diff --check clean.
- Consequence: one fresh adapter bundle may be packaged, deployed, inputs-validated, and used for the single approved review-plan push under the existing external-action gates. Any further adapter failure stops for human decision again.
- Reversal condition: if authenticating the sealed policy would require widening the role allowlist, trusting unsealed configuration, or weakening another invariant, stop and redesign under a new authorization.

## D-043 - Certified-core adapter route terminally blocked by runner provenance binding

- Date: 2026-08-23
- Owner: Luvi-1 and Codex
- Question: After D-042's approved validator-only correction passed exact authenticated inputs validation, why did review-plan v1 lavicheema/rsna-knee-dqa-plan-533ae53-988a62aa6688 still fail, and what is the terminal disposition?
- Evidence: The corrected validator returned dicom_qa_output_validation=PASS mode=workflow stage=inputs exit 0 against dataset lavicheema/rsna-knee-dicom-qa-bundle-533ae53-988a62aa6688 version 1 (ready). Plan identity absence was proven, then plan v1 was pushed exactly once and reached terminal ERROR in about 12.5 seconds emitting phase=review code=private_cohort_plan_invalid before any replay, rendering, or human review. Static inspection of the sealed certified runner shows prepare_private_review cryptographically binds consumed core artifacts' embedded provenance (git_commit and bundle_sha256, plus smoke-summary provenance) to the executing bundle's own run-config identity. Certified-core outputs permanently carry the frozen r15 identity d3771e7-61963849d8ec..., while any compliant adapter bundle necessarily carries a fresh content-derived identity, so this validation can never pass without changing runner verification semantics.
- Decision: classify the certified-core adapter route as blocked with proven root cause. The runner change required to accept certificate-bound foreign-identity outputs is outside the approved validator-only scope, would alter the certified runner bytes bound into the core certificate payload, and therefore requires explicit human authorization and likely recertification. Do not iterate again autonomously; preserve the failed plan kernel, its dataset, and remediation-two evidence as terminal.
- Verification: no DICOM semantics, runner bytes, or core outputs changed; registry integrity untouched; no submission, merge, publication, or downstream kernel launch; the sanitized plan log contains only protocol events and library warnings.
- Consequence: Chunk 5 remains technically incomplete pending a human choice between authorizing a runner-semantics redesign with recertification, scheduling a fully gated fresh successor chain incorporating the validated discovery fixes, or parking the effort.

## D-044 - Human-approved r16 fresh successor chain supersedes adapter reuse

- Date: 2026-08-23
- Owner: Luvi-1 and Codex
- Question: Following D-043, which authorized path completes Chunk 5 without weakening provenance?
- Evidence: The operator explicitly approved Option 2, a fresh end-to-end r16 successor chain from the current tree. Pre-flight on branch feat/chunk-5-dicom-pipeline at parent commit 8e57bab2db0e822db6b7a2c22b5bb411b0753cd8 confirmed the clean tree and terminal D-042/D-043 state. A live contract refresh produced docs/competition_contract/2026-08-23T043419Z.md with verdict PASS_NO_MATERIAL_DRIFT and unchanged canonical contract SHA-256 prefix 32712b5f. A known-fix checklist audit found every named fix present (D-035 mount forms including type-prefixed layouts, D-037 sealed-finalizer loading, D-042 validator policy sourcing, 25-dimension registry, capacity certificate). The packaged synthetic production preflight passed all ten checks (status=pass) from an installed project wheel bound to that commit. Complete local gate on this exact tree: Ruff format/check PASS (129 files), strict mypy src PASS (25 files), strict mypy trust-boundary PASS (3 files), full pytest 589 passed exit 0 (~23 s), sensitive-file guard PASS, tracked secret scan clean, pre-commit all hooks PASS, pip-audit --strict no known vulnerabilities, contract drift check contract_drift=no, git diff --check clean. A synthetic lineage rehearsal suite proves same-successor-identity Run A/B artifacts pass full review preparation while foreign-core identity fails closed with exactly private_cohort_plan_invalid (the D-043 failure mode), preventing silent cross-chain splicing.
- Decision: proceed through one complete r16 chain - implementation freeze, deterministic immutable bundle, private base dataset v1, inputs validation, performance smoke v1, Run A v1 and Run B v1, deterministic comparison, review-plan materialization, QA preparation, and review UI authentication - stopping hard at the human visual-QA boundary. No adapter reuse; r15 core evidence remains historical only.
- Verification: every stage must pass its exact authenticated validator before its dependent stage launches; registry rows append-only with r10-r15 byte-preserved; any source change after freeze invalidates the candidate and requires a new iteration.
- Consequence: r15/r14 and all earlier chains stay terminal and immutable; the r16 row is appended in planned state before remote writes.
- Reversal condition: any P0/P1 red-team finding, validator FAIL, or terminal kernel ERROR stops the chain for classification; no retry of a failed identity.

## D-045 - R16 terminal comparison failure from remote kernel-source ordering

- Date: 2026-08-23
- Owner: Luvi-1 and Codex
- Question: Why did the fresh same-identity r16 comparison fail exact authentication after inputs,
  smoke, Run A, and Run B passed, and may review-plan proceed?
- Evidence: freeze `da5b9c83b874f02067ecc8f1c0a4a1d50fe01b1f` and bundle
  `91ed079210592448664f52c1a24ce1a693275ef09fa350167712097ab97de40b` passed exact inputs,
  performance-smoke, Run A, and Run B validators. Comparison v1 reached `COMPLETE`, but the exact
  workflow validator returned `kernel_metadata_invalid`. The sealed comparison metadata orders
  kernel sources as Run A then Run B; authenticated Kaggle source metadata stores the same exact
  two refs as Run B then Run A. The preserved r15 comparator stores Run A then Run B. A bounded
  source-only diagnostic using the observed r16 order authenticated the exact comparator hash,
  private/offline/version-1 state, output inventory, sanitized deterministic PASS summary, and
  stable before/after source metadata, isolating the ordered-list mismatch as the sole defect.
- Decision: classify r16 terminal `failed` at comparison authentication. Do not treat set equality
  or the diagnostic PASS as workflow acceptance, do not weaken the frozen validator, do not push
  version 2, and do not launch review-plan or any later stage. Preserve the remote identity and
  append-only registry evidence. Any new successor or source-order contract change requires a new
  explicit human decision and complete gating.
- Verification: the guarded registry transition records Run A/B `passed`, comparison
  `failed_kernel_metadata_invalid`, review-plan/human review `not_started`, and terminal reason
  `comparison_kernel_source_order_mismatch`; integrity and foreign keys pass and the r15 registry
  payload hash is unchanged. The live r16 inventory contains only dataset, smoke, Run A, Run B,
  and comparison identities.
- Consequence: Chunk 5 remains technically incomplete. Human review never started. Final status is
  `BLOCKED WITH PROVEN ROOT CAUSE`.

## D-046 - Provisionally release the r16 preprocessing core for nonclinical research

- Date: 2026-08-23
- Owner: Luvi-1 and Codex
- Question: Does r16's nonsemantic authenticated source-order mismatch justify another complete
  successor chain, or may the substantively validated preprocessing core proceed to a simpler
  human-QA path while preserving the formal failure?
- Evidence: R16 inputs, smoke, Run A, and Run B passed exact authenticated validation. Comparison
  v1 completed and every available deterministic-comparison field passed except the frozen ordered
  `kernel_sources` equality check. The expected and observed lists each contain exactly one Run A
  and one Run B source at version 1 with the exact expected code hash, no duplicate, no missing or
  unexpected source, and stable before/after metadata. The independent order-insensitive verifier
  returns `exact_duplicate_free_source_set_verifier = PASS`; eight focused regressions cover reverse
  order, same order, duplicates, missing/extra sources, hash drift, version drift, and repeated
  random permutations. The original ordered validator remains `FAIL`.
- Decision: The r16 preprocessing core is approved for nonclinical Kaggle model-development
  research because two independent full-data runs passed authenticated validation and their
  deterministic result comparison passed substantively. The remaining formal workflow failure is
  an ordering difference in an otherwise exact, duplicate-free, authenticated two-source set. The
  original ordered-validator failure remains preserved. Human visual QA is still required before
  Chunk 5 formally passes.
- Recorded statuses: `preprocessing_research_status=PROVISIONALLY_APPROVED`;
  `formal_multi_kernel_orchestration=DEFERRED`; `human_visual_qa=REQUIRED`;
  `final_submission_readiness=NOT_APPROVED`; `clinical_use=PROHIBITED`.
- R17 disposition: `CANCELLED_BY_STRATEGIC_DECISION`; reason: a nonsemantic source-order issue does
  not justify another 14-hour A/B cycle. No r17 dataset, smoke, Run A, Run B, comparison, adapter,
  or review-plan artifact may be created. No orchestration-only change may trigger another full-data
  A/B replay.
- Consequence: prepare exactly one fresh private, offline, version-1 human-QA notebook using the
  frozen r16 bundle, approved competition input, and authenticated private manifest. It derives only
  cohort-selection metadata, renders one selected study on demand, keeps all identifiers and pixels
  private, and stops for exclusive human control before `START`. This decision does not approve
  training, submission, merge, publication, team action, or Chunk 6.
- Reversal condition: any exact-set verification failure, source/hash/version drift, substantive
  preprocessing defect, privacy or competition-rule violation, or human `BLOCK` revokes provisional
  use and requires fail-closed classification. A metadata-ordering issue alone does not.

## D-047 - Preserve the failed on-demand v1 and correct only its input boundary

- Date: 2026-08-23
- Owner: Luvi-1 and Codex
- Question: How should the single approved on-demand v1 `input_missing` result be classified and
  corrected without changing the frozen r16 core or crossing the human-review boundary?
- Evidence: the approved package at commit `43215041603323c23d1e0b2201429b7973b5ce65` was pushed
  exactly once and reached terminal `ERROR`. Its bounded log emitted the fixed token
  `ON_DEMAND_REVIEW_FAILED=input_missing` at 11.467 seconds; its output listing was empty. It did
  not install the frozen runtime, build a cohort, access pixels, create a review ledger, display a
  UI, or reach `START`. An authenticated read-only pull preserved the exact private/offline/CPU-only
  three-input metadata. Canonical local and pulled notebook JSON matched exactly, proving the raw
  hash mismatch was serialization-only. The generic failure token does not identify which candidate
  failed. Static trace against D-038 found two incompatibilities capable of producing it: the
  on-demand resolver omitted one root form already accepted by the frozen resolver and required
  exact source-directory equality even though the frozen runner later authenticates the required
  inventory, schema, private artifacts, and hashes.
- Decision: preserve the failed identity unchanged with no v2 or deletion. Add only the proven
  source-root form; permit bounded mount-added entries while requiring every API-authenticated
  expected entry to remain a regular file; retain symlink, duplicate-root, entry-count, identity,
  inventory, schema, hash, and privacy rejection. Canonicalize notebook JSON before hashing only in
  the on-demand validator, rejecting duplicate JSON keys and every semantic notebook mutation.
  Do not change the frozen r16 runner, selector, preprocessing, A/B outputs, comparison, or D-046.
- Verification: commits `6d8f133` and `4ad9a08`; focused input-discovery checks 7/7 PASS; normalized
  notebook hash accepts Kaggle formatting and rejects a semantic mutation. A live read-only
  validation now passes source hashing and stops at the preserved terminal status with
  `kernel_status_invalid`. The first complete clean-tree gate at `71d87ee` passed locked offline
  sync, Ruff, mypy src plus strict trust scope, pytest 615/615, sensitive/secret/pre-commit checks,
  pip-audit, contract schema, required exact-set output, frozen-runner equality, and clean-tree
  checks. The identical post-governance gate and fresh-package identity proof remain required before
  requesting another launch.
- Consequence: no additional remote launch is authorized. Human review remains `NOT_STARTED` and
  Chunk 5 remains technically incomplete. A fresh private v1 may be launched only after the complete
  gate, fresh absent-identity proof, and renewed explicit human approval.
- Reversal condition: any failure of required-file, hash, schema, duplicate, symlink, privacy, or
  semantic-notebook tamper checks blocks packaging; any post-`START` evidence or private output leak
  terminates this route.

## D-048 - Terminal classification of the corrected on-demand 4ab1b24 v1 launch

- Date: 2026-08-23
- Owner: Luvi-1 and Codex
- Question: After the complete gate and fresh absent-identity proof on clean commit
  `4ab1b24c8617f1fd7992bb2ad2a101b0a66087a0`, did the explicitly approved private on-demand v1
  launch pass, and if not how is it terminally classified?
- Evidence: the operator issued the exact approval token `APPROVE 4AB1B24 PRIVATE V1`. Final
  preflight matched every recorded identity. The exact kernel reference was authenticated absent
  immediately before launch. Kaggle accepted exactly one version-1 push of
  `lavicheema/rsna-knee-dqa-ondemand-4ab1b24-87326f052bef`. The kernel reached terminal
  `ERROR`; the exact validator returned `kernel_status_invalid` without retrieving outputs; a
  bounded log retrieval passed the frozen privacy scanner and yielded only the disclosure-safe
  failure token `ON_DEMAND_REVIEW_FAILED=input_missing` plus generic wrapper exception names. No
  readiness artifact existed, so no cohort replay, pixel decode, rendering, ledger creation, UI
  display, human review, or `START` occurred. No retry or version 2 was attempted and no remote
  state was deleted.
- Decision: classify the corrected 4ab1b24 on-demand v1 as terminal `failed_input_missing`.
  Preserve its remote identity and log evidence unchanged with no deletion, no version 2, no retry,
  and no duplicate successor under this approval. Do not weaken the resolver further or change the
  frozen r16 runner, selector, bundle, A/B outputs, comparison evidence, or D-046 statuses. Any new
  correction or launch requires fresh root-cause evidence, the full local gate on a clean commit,
  authenticated identity absence, and renewed explicit human approval. Human review remains
  `NOT_STARTED`; Chunk 5 remains technically incomplete; submission, merge, publication, and
  Chunk 6 remain blocked.
- Verification: pre-push absence proof returned `on_demand_kernel_absent=PASS`; the single push
  returned `Kernel version 1 successfully pushed`; bounded status polling observed terminal
  `ERROR`; the exact validator failed closed with exit code 2; sanitized classification used only
  fixed safe tokens after a passing privacy scan; the working tree remained clean before the push and
  contains only this governance record afterward.
- Consequence: the on-demand QA route is blocked again at the same early input-discovery boundary,
  now with independent evidence that the D-047 resolver corrections did not resolve the live mount
  mismatch for this input graph. The next step is a read-only mount-layout diagnosis against this
  exact three-input graph before any further code proposal.
- Reversal condition: only renewed explicit human approval after a complete fresh gate may authorize
  another launch identity; any private-content exposure or post-`START` automation terminates the
  route permanently.

## D-049 - Root cause of 4ab1b24 input_missing classified as C IDENTITY_MARKER_NOT_AT_EXPECTED_DEPTH

- Date: 2026-08-23
- Owner: Luvi-1 and Codex
- Question: After the explicitly approved private mount-layout diagnostic v1, which single root-cause
  category explains the terminal `ON_DEMAND_REVIEW_FAILED=input_missing` result of the corrected
  on-demand 4ab1b24 launch?
- Evidence: The operator issued `APPROVE 4AB1B24 PRIVATE V1`. Clean commit `a83e9f9` carried forward
  the complete gate from `71d87ee` through docs-only governance commits. The diagnostic package was
  rebuilt with the exact failed three-input graph (bundle dataset, source kernel, competition),
  passed compile, Ruff check/format, six synthetic-fixture self-checks covering all mount forms,
  duplicate detection, missing detection, and identity-incomplete detection. Authenticated absence
  proof returned not-found; exactly one version-1 push succeeded as
  `lavicheema/rsna-knee-mount-diag-da5b9c8-4ab1b24c`; bounded polling reached COMPLETE in under
  30 seconds; log retrieval privacy scan returned zero UID patterns, canary tokens, DICM markers,
  or report-content markers.
- Decision: classify as category **C IDENTITY_MARKER_NOT_AT_EXPECTED_DEPTH**. All three inputs were
  mounted at their expected type-prefixed depth-3 forms. Bundle and competition both resolved
  FOUND_UNIQUE with all identity markers present. The source kernel directory exists at
  `notebooks/lavicheema/rsna-knee-manifest-audit-2a1f56e-64a7ae040887` with 6 entries and no
  symlink, but its entry set is incomplete: it does not contain all six required source entries
  (`audit_key.bin`, `private_artifact_inventory.json`, `private_duplicate_groups.csv`,
  `private_manifest.sqlite3`, `private_preliminary_group_keys.csv`, `private_qa_samples.csv`).
  Kaggle mounts derived-kernel outputs as metadata-only wrappers rather than exposing the full
  private output payload. This structural limitation means the on-demand QA design cannot access
  required source artifacts through kernel-source attachment for this graph. No resolver correction
  can fix this without changing what Kaggle exposes.
- Consequence: no resolver change can resolve category C alone. Any further QA attempt requires a
  redesigned input path (for example, packaging required artifacts into a separate dataset) and a
  fresh approval. Human review remains NOT_STARTED; Chunk 5 remains technically incomplete;
  submission, merge, publication, and Chunk 6 remain blocked.
- Reversal condition: only renewed explicit human approval after complete fresh gates may authorize
  another launch identity; any private-content exposure terminates the route permanently.
