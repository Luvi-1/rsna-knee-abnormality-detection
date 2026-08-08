# Current Kaggle landscape

Retrieved: 2026-08-08T02:19:15Z (2026-08-07 19:19:15 PDT). This is a volatile, public,
read-only snapshot from signed-in Kaggle pages. No notebook was copied or run; no vote, comment,
follow, fork, submission, team action, or rules action occurred. Public scores are weak evidence and
must not select models, thresholds, labels, folds, or ensemble weights.

## Official frame

- Competition: [RSNA Knee Abnormality Detection](https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/overview).
- Prediction: one 12-probability vector per `StudyInstanceUID`; unweighted mean of twelve per-label
  ROC AUC values.
- Public/private leaderboard split: 30%/70% of the hidden test according to the live leaderboard.
- Code submission: offline notebook, at most nine hours on CPU or GPU, `submission.csv`; five
  submissions per day and two selected final submissions.
- Reports are training-only: the host states that test reports are unavailable before and after
  notebook submission in [the official discussion](https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/discussion/733592).

The same-day live contract refresh found no content-hash drift across Rules, Description,
Evaluation, Timeline, Data, Prizes, Code Requirements, abstract, or Efficiency pages. The canonical
snapshot remains `docs/competition_contract/contract.yaml`.

## Public leaderboard snapshot

| Observation | Value |
|---|---:|
| Teams shown | 516 |
| Best public score | 0.934 |
| Second / third | 0.932 / 0.915 |
| Fifth / tenth | 0.901 / 0.888 |
| Best score among visible public notebook cards below | 0.847 |

The refreshed distribution was: 99th percentile 0.901, 95th 0.850, 90th 0.836, 75th 0.813,
median 0.749, 25th 0.555, 10th 0.500, and minimum 0.457. Seven teams were at least 0.900,
28 at least 0.850, 193 at least 0.800, 258 at least 0.750, 70 exactly 0.500, and seven below
0.500. An earlier 01:43Z browser snapshot showed 512 teams, demonstrating live drift.

The 0.087 gap between the best public leaderboard score and the best visible public notebook card
is descriptive only: it cannot identify causal method quality or predict private rank. Copy/reuse
remains blocked because inspected cards lacked verified license, asset-lineage, and grouped-OOF
evidence—not because of the score gap. The snapshot is not evidence that leading entries are valid
on the private 70%, reproducible, or rule-compliant.

## Visible public notebook cards

Source: the live [competition Code page](https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/code).
“Updated” values are the relative age displayed at retrieval. Kaggle did not surface a reusable
software or checkpoint license in the inspected cards, so every code/weight reuse decision is
blocked pending a notebook-specific license and asset review.

| Notebook card | Author | Updated | Public score | Votes | Evidence use |
|---|---|---:|---:|---:|---|
| RSNA Knee: read the report, then the knee | `prvsiyan` | 12 h | 0.847 | 34 at prior snapshot | Highest visible card; title implies a training-side report idea, not a test-report interface |
| Knee RSNA | `sakhawathossen` | 7 h | 0.836 | not recorded | Card described earlier as a fork/copy; not independent evidence |
| RSNA Knee infer | `tonylica` | 10 h | 0.832 | 37 at prior snapshot | Public inference baseline only |
| RSNA Knee - Data structure, EDA, baseline | `romanrozen` | 9 h | 0.809 | 75 at prior snapshot | Useful public orientation, not validated truth |
| RSNA Knee Public 4-fold DINOv2 v4 | `hida1211` | 1 d | 0.806 | not recorded | Suggests SSL features are already public; asset/license and fold validity unknown |
| RSNA-dinov2-ensemble | `mawramusawwar` | 2 d | 0.783 | not recorded | Ensemble evidence is weak without OOF details |
| RSNA Knee 101 Read This Before You Start | `stevenleehans` | 15 h | 0.770 | not recorded | Educational baseline |
| RSNA Knee MRI Baseline with Pseudo Labels | `jek1wantaufik` | 19 h | 0.625 | not recorded | Pseudo-label lineage and leakage controls unknown |
| RSNA - Metadata Probe | `zhukovoleksiy` | 19 h | 0.556 | not recorded | Falsification/audit value, not a candidate predictor |
| Plane-Aware 2.5D MIL GPU Baseline | `lucifer19` | 19 h | 0.518 | not recorded | Mechanism is relevant; score and validation do not establish quality |

The pinned “RSNA Knee Abnormalities - Efficiency LB” card by Ryan Holbrook displayed 67 votes in
the earlier snapshot and an update age of three hours in the refresh. Its role is official
orientation; it is not a license or approval for
other assets.

## Discussion intelligence

The public thread [“0.932 LB within one day. Tested for DICOM metadata shortcut”](https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/discussion/733517)
is a participant report, not organizer-verified evidence. The author reports:

- metadata-only random-fold macro AUC 0.6516;
- scanner-fingerprint GroupKFold macro AUC 0.5981, a 0.0534 decrease;
- series-composition macro AUC 0.5954;
- 265 scanner fingerprints, with the top 20 covering 45.5%; and
- the largest reported random-to-group drops for Fracture (0.086), PF OA (0.081), and both medial
  and lateral OA (0.074 each).

The labels were report-derived, and the author noted only 58 official-labeled studies in that
analysis. Therefore the result may partly measure reporting practice rather than image pathology.
Operational use: group and stress-test scanner/protocol fingerprints, prohibit them as shortcuts,
and avoid treating the reported AUCs as a model benchmark.

Other visible discussions covered DINO-style models, external assets/LLMs, efficiency,
`PatientSex`, data inconsistencies, and test-report availability. Host statements and the live
contract outrank participant claims.

The host also states that reports can be ambiguous or internally inconsistent and do not map
one-to-one to labels. Sample image labels were produced by two independent readers with
third-reader adjudication; a definite meniscal tear is positive while degenerative intrasubstance
signal not reaching the articular surface is negative. This
[official clarification](https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/discussion/733491)
strengthens the per-label report-versus-image audit and ontology-review gates.

## Landscape decisions

1. Lock leakage-resistant grouped OOF before reading leaderboard movement as evidence.
2. Prioritize label validity, domain robustness, multi-plane/MIL baselines, and inference budgets.
3. Reproduce mechanisms cleanly; do not fork or copy an unlicensed notebook.
4. Treat every notebook score as a timestamped public-30% observation with unknown private
   generalization, asset lineage, and validation quality.
5. Re-snapshot this page before any public-landscape-dependent decision; it will drift.
