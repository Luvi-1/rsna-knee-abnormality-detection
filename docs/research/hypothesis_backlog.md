# Evidence-ranked hypothesis backlog

Snapshot: 2026-08-08 UTC. Status: research hypotheses only; no experiment is authorized by
this document. Competition data, external weights, and public-leaderboard scores were not used to
fit these priorities.

## Scoring

Every dimension is ordinal from 1 (low) to 5 (high). `AUC`, `Weak`, `Valid`, `Diverse`, `Novel`,
and `Info` are benefits. `Effort`, `GPU`, `Runtime`, and `Rule` are costs or risks. The deterministic
triage score is:

`Priority = 3*AUC + 2*Weak + 2*Valid + Diverse + Novel + 2*Info - Effort - GPU - Runtime - 2*Rule`

The score ranks information-efficient tests; it is not a predicted AUC gain. Equal scores remain
ordered by prerequisite value, then lower compute. The selected portfolio contains exactly 5 label,
5 validation, 10 image-model, 5 ensemble, 5 efficiency, and 5 contrarian hypotheses. Five unsafe or
invalid ideas are scored for transparency and rejected in `rejected_ideas.md`.

| Rank | ID | Category | Idea | AUC | Weak | Valid | Diverse | Novel | Effort | GPU | Runtime | Rule | Info | Priority |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | CT-04 | Contrarian | Use report language/template/site only as grouping and audit variables | 4 | 5 | 4 | 5 | 5 | 3 | 1 | 1 | 1 | 5 | 43 |
| 2 | V-01 | Validation | Patient/repeat/duplicate/template-grouped folds | 5 | 5 | 5 | 2 | 2 | 3 | 1 | 1 | 1 | 5 | 42 |
| 3 | V-02 | Validation | Scanner/protocol grouped stress folds | 5 | 5 | 5 | 3 | 3 | 3 | 2 | 2 | 1 | 5 | 42 |
| 4 | V-04 | Validation | Dual random-versus-grouped promotion gate | 5 | 5 | 5 | 2 | 3 | 2 | 2 | 2 | 1 | 5 | 42 |
| 5 | IM-08 | Image | Condition-specific conservative ROI/localization | 5 | 5 | 4 | 5 | 3 | 4 | 3 | 2 | 1 | 5 | 40 |
| 6 | V-05 | Validation | Bootstrap weakest-label and worst-domain uncertainty | 4 | 5 | 5 | 2 | 2 | 2 | 1 | 1 | 1 | 5 | 40 |
| 7 | LQ-01 | Label | Tri-state multilingual assertion rules | 4 | 5 | 4 | 2 | 2 | 1 | 1 | 1 | 1 | 5 | 39 |
| 8 | V-03 | Validation | Multilabel and unknown-mask-balanced groups | 4 | 5 | 5 | 2 | 2 | 3 | 1 | 1 | 1 | 5 | 39 |
| 9 | IM-03 | Image | Per-label plane/sequence gates | 5 | 4 | 4 | 4 | 3 | 3 | 2 | 2 | 1 | 5 | 39 |
| 10 | EN-03 | Ensemble | Worst-domain shift-aware blend | 4 | 5 | 4 | 5 | 4 | 4 | 2 | 2 | 1 | 5 | 39 |
| 11 | IM-09 | Image | Shared encoder with negative-transfer-aware label heads | 4 | 5 | 4 | 3 | 3 | 3 | 2 | 1 | 1 | 5 | 38 |
| 12 | EN-01 | Ensemble | Per-label OOF rank average of diverse families | 4 | 4 | 5 | 5 | 2 | 2 | 2 | 3 | 1 | 5 | 38 |
| 13 | EN-02 | Ensemble | Nested nonnegative stacking | 4 | 4 | 5 | 4 | 3 | 3 | 2 | 2 | 1 | 5 | 38 |
| 14 | LQ-02 | Label | Section-aware anatomy-relation parsing | 4 | 4 | 4 | 2 | 3 | 2 | 1 | 1 | 1 | 5 | 37 |
| 15 | IM-02 | Image | Gated top-k slice attention MIL | 4 | 4 | 4 | 3 | 3 | 2 | 2 | 2 | 1 | 5 | 36 |
| 16 | CT-03 | Contrarian | No external weights; fold-local in-domain SSL | 4 | 5 | 3 | 5 | 5 | 4 | 4 | 2 | 1 | 5 | 36 |
| 17 | CT-05 | Contrarian | Label graph with negative-transfer isolation | 3 | 5 | 3 | 4 | 5 | 3 | 2 | 1 | 1 | 5 | 36 |
| 18 | IM-04 | Image | Lightweight pooled-token cross-plane attention | 5 | 4 | 3 | 4 | 4 | 4 | 3 | 3 | 1 | 5 | 35 |
| 19 | IM-05 | Image | Ordered adjacent-slice 2.5D input | 4 | 4 | 4 | 4 | 2 | 2 | 2 | 3 | 1 | 5 | 35 |
| 20 | EN-04 | Ensemble | Label-group specialist experts | 5 | 5 | 4 | 5 | 3 | 4 | 4 | 4 | 1 | 4 | 35 |
| 21 | EF-01 | Efficiency | Adaptive slice budget with full-stack parity | 3 | 3 | 5 | 3 | 3 | 2 | 1 | 1 | 1 | 5 | 35 |
| 22 | EF-03 | Efficiency | One encoder pass for all twelve heads | 3 | 4 | 5 | 2 | 2 | 2 | 1 | 1 | 1 | 5 | 35 |
| 23 | CT-01 | Contrarian | Adversarial scanner-invariant representation | 4 | 4 | 3 | 5 | 5 | 4 | 3 | 2 | 1 | 5 | 35 |
| 24 | IM-10 | Image | Cross-series transformer with missing-series masks | 5 | 4 | 3 | 4 | 4 | 4 | 3 | 3 | 1 | 5 | 35 |
| 25 | IM-01 | Image | MRNet-lite shared 2D MIL baseline | 4 | 3 | 5 | 3 | 1 | 2 | 2 | 2 | 1 | 5 | 34 |
| 26 | IM-07 | Image | Fold-local image self-supervision | 4 | 5 | 3 | 4 | 4 | 4 | 4 | 2 | 1 | 5 | 34 |
| 27 | EF-04 | Efficiency | AMP, batching, and resolution operating curve | 3 | 3 | 5 | 2 | 2 | 2 | 1 | 1 | 1 | 5 | 33 |
| 28 | CT-02 | Contrarian | Axial-first targeted specialist | 3 | 4 | 3 | 5 | 5 | 3 | 3 | 2 | 1 | 5 | 33 |
| 29 | LQ-03 | Label | Native multilingual rules plus small encoder consensus | 4 | 4 | 3 | 3 | 3 | 3 | 2 | 1 | 2 | 5 | 32 |
| 30 | LQ-05 | Label | Cross-fitted image-text agreement labels | 4 | 5 | 3 | 4 | 4 | 4 | 4 | 2 | 2 | 5 | 32 |
| 31 | EF-05 | Efficiency | Distill a diverse ensemble into one student | 4 | 4 | 3 | 2 | 4 | 4 | 4 | 1 | 1 | 4 | 29 |
| 32 | EN-05 | Ensemble | Correlation-pruned folds, seeds, and TTA | 3 | 3 | 5 | 4 | 2 | 2 | 3 | 4 | 1 | 4 | 28 |
| 33 | LQ-04 | Label | Positive-unlabeled risk for report omissions | 3 | 4 | 2 | 3 | 4 | 3 | 3 | 1 | 2 | 5 | 27 |
| 34 | EF-02 | Efficiency | DICOM decode and data-loader benchmark | 2 | 2 | 5 | 1 | 2 | 2 | 1 | 1 | 1 | 5 | 27 |
| 35 | IM-06 | Image | Selective anisotropic 3D specialist | 3 | 4 | 3 | 5 | 3 | 4 | 4 | 4 | 1 | 4 | 25 |
| 36 | RJ-02 | Reject | Metadata/site/UID shortcut | 4 | 3 | 1 | 4 | 3 | 2 | 1 | 1 | 5 | 4 | 21 |
| 37 | RJ-01 | Reject | Test-report-dependent inference | 5 | 5 | 1 | 4 | 1 | 3 | 1 | 1 | 5 | 1 | 19 |
| 38 | RJ-04 | Reject | Same-study pseudo-labeling or leaderboard threshold fitting | 4 | 4 | 1 | 3 | 2 | 2 | 2 | 1 | 5 | 1 | 14 |
| 39 | RJ-05 | Reject | Uncleared external asset or external LLM report upload | 4 | 3 | 1 | 4 | 3 | 2 | 2 | 2 | 5 | 1 | 13 |
| 40 | RJ-03 | Reject | Random folds as the only validation | 3 | 3 | 1 | 1 | 1 | 1 | 1 | 1 | 4 | 1 | 10 |

## Support and evaluability contract

- Audit sampling is frozen before predictions with seed `20260808`, stratified by the predeclared
  label, language, and assertion cells, and counts at most one record from each protected component
  (patient, repeat, exact/near duplicate, or report-template link) in a cell. A promoted PPV cell
  requires at least 20 independent determinate-positive components and a Wilson 95% lower bound.
  Every other claimed label-quality proportion, F1, error, or flip-rate cell requires at least 50
  independent components in every reference class used by that metric. Proportions use Wilson 95%
  bounds; paired differences and F1 use the canonical interval below. Unsupported cells cannot be
  pooled, dropped, or treated as passing.
- Mandatory domains and their mapping are frozen before model outcomes. Every mandatory domain must
  have at least 20 independent positive and 20 independent negative protected groups for every one
  of the 12 labels. The worst-domain statistic includes all mandatory domains; if any is unsupported,
  the robustness claim and dependent promotion are blocked. Descriptive results may instead be
  labeled `worst evaluable domain`, but cannot satisfy a promotion gate.
- The canonical interval is 10,000 paired protected-group Bayesian-bootstrap replicates generated
  by NumPy `PCG64` seed `20260808`, with one independent `Exp(1)` weight per group and identical
  weights for both compared models. The two-sided percentile 95% interval is the linear-interpolated
  `[2.5%, 97.5%]` quantile pair; “lower bound above zero” means the 2.5% quantile is strictly positive.
  The source set must have at least 20 independent positive and 20 independent negative groups for
  every evaluated label. Any one-class or numerical replicate blocks the claim; labels, domains,
  and replicates are never skipped, imputed, or reweighted after inspection.

## Top five label-quality hypotheses

| ID | Mechanism and affected labels | Minimum viable experiment, data, compute | Success and kill gates | Leakage/confounding and closest baseline |
|---|---|---|---|---|
| LQ-01 | High-precision multilingual lexicons plus explicit `positive`, `negative`, `uncertain`, and `unmentioned` states. All 12 labels. | Synthetic multilingual assertion fixtures, fold-training reports, and official labels; CPU minutes. | Success: >=20 independent audited determinate-positive components overall and in every promoted label-language cell; Wilson 95% PPV lower bound >=0.90 overall and >=0.80 per cell. Kill: unsupported cell, any major-language cell below 0.75 point PPV, or silent unknown-to-negative conversion. | Report assertion is not image truth; use the frozen protected-group audit sampling. Baselines: ContextD, NegBio, CheXpert rules. |
| LQ-02 | Section-aware assertion plus anatomy/relation parsing for ligament, meniscus side, OA compartment, effusion/cyst, and acute injury. All labels; strongest for ACL, MCL, both menisci, and three OA labels. | Compare fixed-window rules with section, temporality, negation, uncertainty, laterality, and anatomy relations on the frozen protected-group audit; CPU minutes. | Success: supported cells and either macro-F1 point delta >=0.03 with canonical 95% lower bound >0, or anatomy/laterality error point reduction >=30% with lower bound >0; recall-loss 95% upper bound <=0.05. Kill: unsupported cell, unresolved collision, or unparseable-layout Wilson upper bound >0.10. | Templates and bilateral/historical wording can masquerade as findings. Baselines: NegBio and RadGraph schema. |
| LQ-03 | Consensus between native-language rules and a small approved multilingual encoder; translation is a separately audited arm. All 12. | Inner-fold text classifier versus deterministic rules; frozen language/template-stratified protected-group audit; <2 GPU-h plus CPU. | Success: every claimed language is supported, worst-language F1 point delta >=0.03 with canonical 95% lower bound >0, and English-loss 95% upper bound <=0.01. Kill: unsupported cell, laterality/assertion-flip Wilson upper bound >0.02, license failure, or API dependency. | Language and site are confounded; raw reports never leave Kaggle. Baseline: TF-IDF/logistic regression and native rules. |
| LQ-04 | Non-negative PU risk treats high-precision report mentions as positives and unmentioned studies as unlabeled. All 12; most useful where mention precision is high and recall is low. | One-label masked-BCE versus nnPU screen with class-prior sensitivity +/-20%; one baseline-sized run. | Success: positive OOF AUC delta across the full prior range and portfolio promotion gate. Kill: result changes sign, too few positives, or selection-bias diagnostics fail. | SCAR is implausible because severity, language, site, and clinical question affect mention. Baseline: masked BCE and nnPU. |
| LQ-05 | Accept a weak target only when an independent high-precision text label and strictly cross-fitted image teacher agree; otherwise retain unknown. All 12. | K grouped-fold teachers label only excluded groups; combine with LQ-01; <=K existing teacher runs plus one student. | Success: each promoted label has >=20 independent audited accepted-positive components, point PPV >=0.95 and Wilson 95% lower bound >=0.90; coverage Wilson lower bound >=0.20 in at least six supported labels; macro +0.005 across two seeds. Kill: unsupported label, genealogy breach, coverage lower bound <0.10, or language/severity concentration. | Highest leakage risk: no teacher or ancestor may train on its target protected component. Baseline: one-shot OOF pseudo-labeling. |

## Top five validation hypotheses

| ID | Mechanism and affected labels | Minimum viable experiment, data, compute | Success and kill gates | Leakage/confounding and closest baseline |
|---|---|---|---|---|
| V-01 | Build groups spanning patient, repeated study, exact/near duplicate, and report template before folds. All labels. | Privacy-safe manifest audit and duplicate graph; then one synthetic split check and one Kaggle aggregate audit; CPU. | Success: zero connected component crosses folds and each label has both classes. Kill: no defensible group key or unresolved cross-fold component. | UID uniqueness alone is insufficient. Baseline: patient GroupKFold used by prior RSNA winners. |
| V-02 | Hold out scanner/protocol fingerprints to estimate hidden-site robustness. All labels, especially Fracture, OA, and Baker's where the public metadata probe reported larger gaps. | Freeze mandatory privacy-safe vendor/field-strength/protocol domains; compare group holdouts with patient-only folds; one baseline OOF cycle. | Success: every mandatory domain passes support, worst-domain macro is within 0.02 of pooled OOF, and conclusions are stable. Kill: any mandatory domain is unsupported or any architecture gain vanishes/reverses under grouped evaluation. | Metadata can encode site/prevalence; grouping features never enter the predictor. Baselines: multi-center knee studies and scanner-shift studies. |
| V-03 | Optimize fold assignment for per-label positive, negative, and unknown balance subject to fixed groups. All labels. | Deterministic constrained group allocator and synthetic proof before Kaggle aggregates; CPU. | Success: every fold has both classes for all 12 and maximum prevalence deviation <=0.05 where feasible. Kill: balance requires splitting a protected group or using report-derived targets as truth. | Small rare-label counts may make five folds infeasible; reduce folds rather than violate groups. Baseline: iterative multilabel stratification constrained by groups. |
| V-04 | Require both patient-random and scanner/protocol-grouped OOF regimes; grouped evidence governs promotion. All labels. | Same frozen baseline and preprocessing in two split regimes; one extra OOF cycle. | Success: proposed gain >=0.005 in both, >=9/12 nonnegative, canonical interval lower bound >0. Kill: random-only gain or grouped loss >0.01. | Two regimes are diagnostic, not two chances to cherry-pick. Baseline: random split versus GroupKFold metadata probe. |
| V-05 | Use paired protected-group Bayesian-bootstrap CIs plus weakest-label and worst-domain reporting. All labels. | Run the predeclared 10,000-replicate procedure on locked OOF predictions; CPU minutes. | Success: source support contract passes, all replicates are evaluable, and promotion lower bound >0 for macro delta. Kill: unsupported source, any degenerate/numerically invalid replicate, CI crossing zero, or any label loss >0.02. | Resampling rows would understate uncertainty for repeats; no invalid replicate or label is silently omitted. Baseline: paired clustered Bayesian bootstrap and 12-label macro AUC. |

## Top ten image-model hypotheses

| ID | Mechanism and affected labels | Minimum viable experiment, data, compute | Success and kill gates | Leakage/confounding and closest baseline |
|---|---|---|---|---|
| IM-01 | Shared 2D slice encoder, deterministic 24-slice budget, masked 12 heads, mean/GeM/max MIL, late series fusion. All labels. | B0 central-slice versus full MIL baseline; smoke <1 GPU-h, full OOF about 20-30 GPU-h. | Success: B1 macro >=B0+0.005 with projected hidden inference <=6.5 h. Kill: no gain or any systematic DICOM failure. | Group folds and fold-fit normalization only. Closest baseline: MRNet and ELNet. |
| IM-02 | Replace hard max with gated top-k attention over ordered slice embeddings. All labels; expected benefit ACL, menisci, contusion, fracture. | Freeze IM-01 embeddings for head-only screen, then one end-to-end fold; <1 then 4-6 GPU-h. | Success: macro +0.005, >=8/12 nonnegative, no label <-0.005. Kill: <0.003, attention collapse, or seed variance exceeds gain. | Slice count/protocol may drive attention. Baseline: MRNet hard max. |
| IM-03 | Per-label plane/sequence gates with explicit missing-series masks. ACL sagittal; MCL coronal; menisci multi-plane; PF OA axial; fluid-sensitive labels. | Cached-embedding gate versus uniform late fusion; <1 GPU-h screen. | Success: macro +0.004 and targeted-label mean +0.008. Kill: one-plane collapse or site/missingness-specific gain. | Only test-available sequence facts; audit site prediction. Baselines: MRNet fusion and plane ablations. |
| IM-04 | Cross-plane and cross-sequence attention over pooled tokens, never full pixel volumes. ACL, MCL, menisci, contusion. | Same encoder/token budget as IM-03; one fold 4-8 GPU-h. | Success: macro +0.005 with <=25% latency/VRAM growth and <=6 h projected inference. Kill: <0.003 or geometry/resource instability. | Orientation/order and absent-series stress tests. Baseline: CoPAS-lite versus late fusion. |
| IM-05 | Three adjacent, geometry-valid slices as 2.5D channels. ACL, menisci, fracture, contusion. | Same sampler/backbone as single-slice IM-01; one fold 4-6 GPU-h. | Success: target mean +0.008, macro +0.003. Kill: no target gain or >1.6x inference. | Never bridge gaps or series; DICOM audit must pass. Baseline: adjacent-slice RSNA PE and trauma winners. |
| IM-06 | Small anisotropic 3D branch only for a high-value ROI/series, blended with the best 2.5D model. Initially menisci or OA. | Downsampled ROI, one target family, 4-6 GPU-h smoke and 50-80 GPU-h full. | Success: target mean +0.005, macro +0.002, <=2x memory, runtime gate. Kill: no target gain or >6.5 h projected ensemble. | ROI selection is fold-contained; full-resolution 3D is out of scope. Baseline: 3D ResNet/CUBE studies. |
| IM-07 | Fold-local image self-supervision learns anatomy from competition training pixels only, followed by identical supervised fine-tuning. All labels, expected rare-label help. | One-fold approved pretext versus scratch/approved initialization; 8-12 GPU-h. | Success: macro +0.005 and rare-label mean +0.010 across two seeds. Kill: <0.003, collapse, or budget overrun. | Pretraining excludes held-out groups and all test pixels. Baseline: SKID-style SSL and medical SSL literature. |
| IM-08 | Conservative anatomy localization/crops with full-FOV fallback; one specialist family at a time. ACL, both menisci, OA compartments. | Fold-local locator or label-free anatomy bounds; 2 GPU-h smoke, 15-25 GPU-h full. | Success: crop coverage >=99.5%, target +0.010, macro +0.004. Kill: >0.5% QA failure, rare-label truncation, or <0.005 target gain. | No validation-label-derived crop; atypical scans retain full FOV. Baselines: KAMRNet and recent RSNA localization winners. |
| IM-09 | Shared encoder with masked heads and label-group adapters only where gradient conflict proves negative transfer. All labels; focus rare labels. | Shared baseline versus equal-capacity grouped heads; one fold 6-10 GPU-h. | Success: macro +0.005, rare-label mean +0.010, no label <-0.010. Kill: >2 harmed labels or unstable gradient grouping. | Missing remains masked; grouping selected inside training data only. Baseline: shared multi-task Res3DKnee/CoPAS. |
| IM-10 | Compact transformer over bounded per-series tokens with acquisition-type and missing-series masks. All labels. | IM-03 embeddings, one-layer sequence model versus gated pooling; 2 GPU-h smoke, 30-40 GPU-h full. | Success: macro +0.003, correlation <0.995 with pooling, <=25% latency increase. Kill: <0.001 or shortcut dependence. | Sequence metadata is identity/mask only, never UID/site. Baseline: RSNA PE CNN-transformer and shared knee slice transformer. |

## Top five ensemble hypotheses

| ID | Mechanism and affected labels | Minimum viable experiment, data, compute | Success and kill gates | Leakage/confounding and closest baseline |
|---|---|---|---|---|
| EN-01 | Per-label rank-average two genuinely diverse OOF model families. All labels. | Best model plus lowest-correlated competitive model; OOF analysis and second-model inference. | Success: macro +0.003, correlation <0.98, every label >=best single-OOF minus 0.005. Kill: <0.001, correlation >0.995, or runtime >6.5 h. | Select on locked OOF only; no public-LB weights. Baseline: simple equal/rank blend. |
| EN-02 | Nested nonnegative stacking learns label-wise weights on inner OOF and evaluates on outer OOF. All labels. | Two to four eligible base predictors; CPU fitting. | Success: macro +0.003 over equal blend and weights stable across outer folds. Kill: weight sign/identity instability or gain vanishes nested. | Fitting and evaluating weights on the same OOF rows is prohibited. Baseline: equal blend. |
| EN-03 | Optimize a conservative blend for worst-domain macro subject to pooled-AUC and runtime constraints. All labels. | Inner-fold summaries from all mandatory predeclared domains; CPU. | Success: every mandatory domain passes support, worst-domain +0.010, pooled noninferior within 0.001, no label <-0.005. Kill: any unsupported mandatory domain or harm to pooled OOF. | No post-hoc domain selection, dropping, or private-leaderboard proxy. Baseline: pooled-AUC blend. |
| EN-04 | Specialists contribute only to predeclared label groups: ligaments, menisci, OA, inflammatory/cyst, acute bone injury. All labels through routing. | Add one validated specialist to shared model; 3-8 GPU-h plus benchmark. | Success: affected mean +0.008, macro +0.003, correlation <0.98. Kill: <0.003 macro or runtime margin fails. | Route is label ontology, never exam metadata. Baseline: shared model plus one specialist. |
| EN-05 | Prune folds, seeds, and TTA by OOF correlation and marginal AUC per runtime second. All labels. | Greedy selection on inner OOF, outer evaluation; CPU plus inference benchmark. | Success: retain >=99.9% ensemble macro with >=30% runtime reduction. Kill: any label >0.005 loss or selection unstable. | Fold/seed replicas are not assumed diverse. Baseline: full uniform ensemble. |

## Top five efficiency hypotheses

| ID | Mechanism and affected labels | Minimum viable experiment, data, compute | Success and kill gates | Leakage/confounding and closest baseline |
|---|---|---|---|---|
| EF-01 | Adaptive but bounded slice selection processes 16/24 slices instead of the full stack, retaining edge and saliency coverage. All labels. | Inference ablation on fixed OOF model; 1-2 GPU-h. | Success: >=2x throughput with absolute macro delta <=0.001 and no label <-0.005. Kill: protocol/prevalence-dependent misses. | Selector trained inside folds; no positive-slice labels. Baseline: uniform full stack. |
| EF-02 | Benchmark DICOM decode plugins, metadata-only reads, worker count, prefetch, and pinned-memory transfer before optimizing the model. All labels unchanged. | Synthetic DICOM first, then permitted aggregate timing on a fixed study batch; CPU/GPU minutes. | Success: >=30% wall-time reduction with bitwise order and numeric preprocessing parity. Kill: decode disagreement, order change, worker instability, or excess RAM. | Never cache private pixels outside the permitted environment. Baseline: single-worker pydicom path. |
| EF-03 | Decode and encode each selected slice once; share embeddings across all twelve heads and label-group adapters. All labels. | Profile shared versus duplicated passes on synthetic and fixed permitted batches; <1 GPU-h. | Success: >=40% compute reduction with prediction difference <=1e-6 before any intended head change. Kill: hidden duplicated preprocessing or reduced AUC. | Exact preprocessing/config hash required. Baseline: one model per label/plane. |
| EF-04 | Measure the Pareto curve for resolution, batch size, AMP, workers, and deterministic settings. All labels. | Fixed model and OOF subset; 2-4 GPU-h benchmark. | Success: >=30% speed or memory improvement with |delta AUC| <=0.001 and numerical parity tolerance recorded. Kill: NaNs, ordering drift, >0.005 label loss, or >80% peak memory. | Tune on inner OOF; reserve outer results for confirmation. Baseline: FP32 batch-one. |
| EF-05 | Distill promoted diverse teachers into one shared student using fold-clean soft targets. All labels. | Teachers produce strictly OOF soft targets; one student, 20-30 GPU-h. | Success: student retains >=99.5% teacher macro and runs >=2x faster. Kill: any label >0.01 loss or teacher ancestry cannot be proven clean. | No teacher predicts its own training group. Baseline: full two-model ensemble. |

## Five deliberately contrarian hypotheses

| ID | Mechanism and affected labels | Minimum viable experiment, data, compute | Success and kill gates | Leakage/confounding and closest baseline |
|---|---|---|---|---|
| CT-01 | Gradient reversal removes scanner/protocol information while preserving pathology ranking. All labels. | Add a fold-training domain classifier to IM-01; one fold 4-8 GPU-h. | Success: domain accuracy approaches chance, grouped macro +0.005, pooled noninferior. Kill: pathology AUC loss >0.003 or domains encode true prevalence irreducibly. | Domain labels remain training-only; audit label-domain imbalance. Baseline: augment-only domain generalization. |
| CT-02 | An axial-first specialist challenges the sagittal-default assumption for menisci, PF OA, effusion, synovitis, and Baker's. | Single-plane equal-capacity ablation; 4-6 GPU-h. | Success: target mean +0.008 versus best single plane or adds correlation <0.98 to ensemble. Kill: no target gain or site dependence. | Equal sampling/resolution prevents compute confounding. Baseline: published plane ablations. |
| CT-03 | Forgo every external checkpoint and pretrain fold-locally on the competition's own images. All labels. | Scratch versus fold-local SSL versus separately approved generic initialization; 8-12 GPU-h per screen. | Success: grouped macro +0.005 or equivalent AUC with cleaner licensing. Kill: <0.003 and materially higher compute. | Held-out groups never enter SSL. Baseline: approved ImageNet initialization. |
| CT-04 | Use report language, template, and inferred site only to prevent leakage and measure shift—never as predictive features. All labels. | Grouping/falsification study; CPU plus one baseline OOF cycle. | Success: identifies an honest split and reduces random-to-grouped gap; no loss from removing text/site inputs at inference because none are used. Kill: grouping is statistically infeasible, requiring organizer guidance. | This explicitly sacrifices exploitable shortcuts. Baseline: participant metadata-only probe. |
| CT-05 | Learn a low-rank label graph only for stable residual relations and isolate heads when relations flip across folds/domains. OA/Syn/Baker's and Contusion/Fracture groups. | Inner-OOF logits, low-rank residual versus independent heads; <1 GPU-h head screen. | Success: macro +0.003, weakest-label +0.005, stable relation signs. Kill: sign flips, calibration harm, or rare-label loss >0.01. | Use inner-OOF predictions, not in-sample logits. Baseline: independent sigmoid heads. |

## Portfolio-wide experiment gate

Unless a stricter row-level gate applies, promotion requires a locked grouped OOF macro-AUC gain
of at least 0.005, canonical paired protected-group Bayesian-bootstrap 95% lower bound above zero,
reproduction across two seeds, at least 9 of 12 label deltas nonnegative, no label loss worse than
0.02, complete OOF predictions, and projected hidden inference no more than 6.5 hours with peak
memory below 80%. Any support, data, fold, label, preprocessing, asset, or lineage violation is an
immediate kill regardless of score.
