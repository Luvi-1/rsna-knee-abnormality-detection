# Literature review for RSNA Knee Abnormality Detection

Snapshot: 2026-08-08 UTC. Scope: exact competition strategy before data processing or training.
The review combines official competition evidence, peer-reviewed studies, organizer-confirmed
winning solutions, official repositories, and clearly labeled public-participant claims.

## Evidence policy

- **T1:** current official Kaggle/RSNA contract or organizer statement, or a normative technical
  standard/API source used only for the exact behavior it specifies.
- **T2:** peer-reviewed external/multicenter validation, an organizer-confirmed winning solution,
  or official framework/library documentation used only for an implementation claim.
- **T3:** peer-reviewed patient-separated internal study or primary transferable method.
- **T4:** public notebook/discussion, author write-up, repository, or preprint claim.
- Facts below are reported source findings. “Competition inference” is our falsifiable transfer
  hypothesis, never a claim that a method will win here.
- A paper or code license does not license data, pretrained weights, checkpoints, or derived
  artifacts. No external asset is approved by this review.

## Executive synthesis

The most defensible path is: establish leakage-resistant grouped validation; validate multilingual
report labels per target; build a shared 2D MIL baseline; add ordered 2.5D context, plane/sequence
gating, and conservative localization one factor at a time; ensemble only OOF-diverse survivors;
and treat decode/runtime choices as model-selection constraints. The literature repeatedly shows
that external-center performance is lower than internal performance, while prior RSNA winners
repeatedly succeed with localization, 2D/2.5D encoders, ordered sequence aggregation, patient-grouped
OOF, and compact deployment paths. It does not support using test reports, scanner shortcuts,
uncleared assets, random folds alone, or monolithic high-resolution 3D as the first experiment.

## 1. Official notebooks and discussions

**Facts (T1/T4).** The live [Code page](https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/code)
shows rapidly changing public notebooks spanning report-derived supervision, DINOv2, 2.5D MIL,
pseudo-labeling, and metadata probes. Kaggle did not surface reusable code/checkpoint licenses on
the inspected cards. The host confirms in [discussion 733592](https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/discussion/733592)
that test reports are unavailable.

**Competition inference.** Public notebooks map the crowded baseline space, not truth. Reuse is
blocked until notebook-specific code and asset licensing is verified; methods must survive grouped
OOF independently.

## 2. Public leaderboard baselines

**Facts (T1/T4).** At 2026-08-08T02:19:15Z, 516 scored teams were shown, the best public score was
0.934, the top-10 cutoff was 0.888, the median was 0.749, and the best visible public notebook card
was 0.847. The leaderboard
uses only 30% of the hidden test; 70% is private.

**Competition inference.** The 0.087 gap is descriptive only: it cannot identify causal method
quality or predict private rank. Copy/reuse remains blocked because inspected cards lacked verified
license, asset-lineage, and grouped-OOF evidence. The 30/70 split makes public-leaderboard tuning
especially weak evidence; scores are timestamped observations, not validation results.

## 3. Previous RSNA/Kaggle winning solutions

**Facts (T2/T4).** Organizer-confirmed solutions repeatedly use localization and ordered context:
[RSNA PE Educational Merit](https://pubs.rsna.org/doi/full/10.1148/ryai.2021210068) used adjacent
slices, CNN features, transformers, five-fold CV, and a 7-8 hour final inference; the
[2023 abdominal-trauma rank-1 solution](https://github.com/Nischaydnk/RSNA-2023-1st-place-solution)
used patient GroupKFold, organ crops, adjacent-slice inputs, and GRU aggregation; the
[2024 lumbar-spine rank-4 solution](https://github.com/yu4u/kaggle-rsna2024-4th) used localization,
plane-specific 2.5D classifiers, and OOF stacking. Winner repositories have mixed licenses and do
not automatically license their weights or external data.

**Competition inference.** Reproduce mechanisms cleanly: ROI -> 2D/2.5D encoder -> ordered MIL or
sequence head -> OOF-diverse blend. Avoid reproducing 11-to-30-model ensembles under a nine-hour
ceiling.

## 4. Multi-plane and multi-sequence knee MRI classification

**Facts (T2/T3).** [MRNet](https://doi.org/10.1371/journal.pmed.1002699) studied 1,370 examinations
with sagittal T2, coronal T1, and axial PD series, patient-separated development, and late plane
fusion. [CoPAS](https://doi.org/10.1038/s41467-024-51888-4) studied 1,748 patients across five
centers and twelve abnormalities using multi-plane/multi-sequence branches. A 2025
[multicenter nine-abnormality system](https://pubmed.ncbi.nlm.nih.gov/41079026/) used three-plane
PD-fat-suppressed imaging and external-center testing.

**Competition inference.** Series provide complementary evidence, but acquisition missingness and
site can become shortcuts. Begin with shared embeddings, per-label plane gates, and explicit
missing-series masks.

## 5. Co-plane attention and cross-series fusion

**Facts (T2).** CoPAS creates co-plane representations and applies cross-plane and cross-sequence
attention; it reported lower AUC on external/fewer-sequence settings than internally and explicitly
noted parameter load, slow convergence, and overfitting. The code repository is Apache-2.0, while
clinical data and linked weights are not cleared.

**Competition inference.** Test a pooled-token CoPAS-lite against late fusion under the same encoder
and token budget. Full synthetic 3D volumes are deferred until compact attention proves value.

## 6. Multiple-instance learning over MRI slices

**Facts (T3).** MRNet applies a 2D encoder to slices, pools spatially, takes a maximum across slices,
then combines series. [ELNet](https://proceedings.mlr.press/v121/tsai20a.html) showed a very small,
scratch-trained layered aggregation model could remain competitive on the MRNet benchmark.

**Competition inference.** Shared 2D slice features plus mean/GeM/max form the correct first image
baseline. Gated top-k attention is a cheap, controlled next test for focal findings.

## 7. 2.5D versus anisotropic 3D

**Facts (T2/T3).** Adjacent slices mapped into channels recur in RSNA PE, abdominal-trauma, and spine
solutions. Knee studies using 3D CUBE volumes report useful lesion classification, including a
[1,435-study 3D system](https://pubmed.ncbi.nlm.nih.gov/34142088/), but those protocols are more
uniform than routine multi-series data and the pipelines are heavier. Recent 2.5D knee work is
promising but small and endpoint-specific.

**Competition inference.** Ordered 3-slice input has better first-test economics. A downsampled,
anisotropic 3D specialist is justified only after 2.5D leaves a reproducible target-label gap.

## 8. Medical-image self-supervised learning

**Facts (T3/T4).** Knee-specific self-supervision has been evaluated on MRNet/KneeMRI, but it does
not establish superiority for this twelve-label task. The 2026 CVPR
[MASS](https://openaccess.thecvf.com/content/CVPR2026/html/Gao_Learning_Generalizable_3D_Medical_Image_Representations_from_Mask-Guided_Self-Supervision_CVPR_2026_paper.html)
paper reports mask-guided pretraining across 5,000 CT/MRI/PET volumes and smaller 20-200 scan
settings; this is new cross-modality evidence, not knee-competition proof.

**Competition inference.** Fold-local SSL avoids an external-checkpoint dependency and may help rare
labels, but it remains governed by MIRA and unresolved derivative/public-weight terms; artifacts
stay private. Held-out groups must be excluded from pretraining. Compare against scratch and a
separately approved initialization.

## 9. Image-report contrastive learning

**Facts (T3).** [ConVIRT](https://arxiv.org/abs/2010.00747),
[GLoRIA](https://openaccess.thecvf.com/content/ICCV2021/html/Huang_GLoRIA_A_Multimodal_Global-Local_Representation_Learning_Framework_for_Label-Efficient_Medical_ICCV_2021_paper.html),
and [MedCLIP](https://aclanthology.org/2022.emnlp-main.256/) report label-efficient representations
from image-text relationships, primarily in chest imaging. GLoRIA adds global-local region/word
alignment; MedCLIP addresses false negatives through semantic matching.

**Competition inference.** A fold-local knee image/report pretext is plausible but high-risk because
reports are multilingual, incomplete, and potentially template/site linked. The text encoder is
training-only; test inference remains image-only. It ranks behind deterministic label extraction
and image-only SSL.

## 10. Weak labels from radiology reports

**Facts (T2/T3).** [CheXpert](https://doi.org/10.1609/aaai.v33i01.3301590) preserves positive,
negative, uncertain, and unmentioned states. [VisualCheXbert](https://doi.org/10.1145/3450439.3451862)
demonstrates a discrepancy between report-derived and image labels. A 2023
[paired brain-MRI study](https://doi.org/10.3389/fradi.2023.1251825) found strong binary agreement
but materially variable granular-category sensitivity.

**Competition inference.** Validate report-to-image error per knee label. Official, report-derived,
and image-pseudo sources remain separate with masks and provenance; report labels are never expert
ground truth.

## 11. Negation, uncertainty, temporality, and missing mentions

**Facts (T3).** [ContextD](https://doi.org/10.1186/s12859-014-0373-3) found that translated triggers
alone were inadequate and document-type adaptations mattered. [NegBio](https://pmc.ncbi.nlm.nih.gov/articles/PMC5961822/)
improved radiology assertion detection through dependency-pattern scope. CheXpert shows that the
best treatment of uncertainty can vary by finding.

**Competition inference.** Implement explicit assertion and temporal states with section and anatomy
relations. Unmentioned always remains unknown; uncertain policies are selected per label in inner
folds only.

## 12. Multilingual clinical NLP

**Facts (T2/T3).** A 2023 [five-hospital French/German RECIST study](https://doi.org/10.3389/fdgth.2023.1195017)
reported lower transfer across hospitals/languages than in-domain performance. A 2024
[Radiology translation evaluation](https://doi.org/10.1148/radiol.241736) found performance varied
by model/language and medical terminology was the weakest qualitative criterion.

**Competition inference.** Start with native-language rules and a small offline classifier; measure
worst-language performance and assertion/laterality flips. Never send reports to an API.

## 13. Positive-unlabeled learning

**Facts (T3).** [Elkan and Noto](https://doi.org/10.1145/1401890.1401920) require assumptions about
how positives become labeled. [Kiryo et al.](https://proceedings.neurips.cc/paper_files/paper/2017/hash/7cce53cf90577442771720a370c3c723-Abstract.html)
introduced a non-negative PU risk to limit overfitting in flexible models.

**Competition inference.** Report mention is unlikely selected completely at random: severity,
language, site, template, and clinical question affect selection. nnPU is a sensitivity-analysis
arm only, with inner-fold class-prior sweeps and a deterministic masked-BCE control.

## 14. Learning with noisy labels

**Facts (T3).** [Loss correction](https://openaccess.thecvf.com/content_cvpr_2017/html/Patrini_Making_Deep_Neural_CVPR_2017_paper.html)
assumes an estimable transition structure. [Confident Learning](https://doi.org/10.1613/jair.1.12125)
ranks likely errors from predicted probabilities. [DivideMix](https://openreview.net/forum?id=qBbAV8Wg90K)
uses two-network cross-partitioning but doubles training complexity.

**Competition inference.** Begin with an OOF audit queue, never automatic correction. Transition
matrices are valid only if stable across language/template/site; DivideMix is deferred until cheap
label baselines fail.

## 15. Cross-fitted pseudo-labeling

**Facts (T3/T4).** [Arazo et al.](https://doi.org/10.1109/IJCNN48605.2020.9207304) document
confirmation bias in naive pseudo-labeling. Prior RSNA solution reports include both successful and
negative pseudo-label experiments, so benefit is task-specific.

**Competition inference.** Use one-shot grouped cross-fitting: a teacher labels only studies and
protected related groups excluded from its ancestry. Record teacher/config/checkpoint/fold hashes,
probability, threshold, source, and study group. Any genealogy breach kills the experiment.

## 16. Domain generalization across hospitals, scanners, field strengths, and protocols

**Facts (T2/T3).** The 2025 multicenter knee system's primary-task AUC fell from 0.898 internally to
0.815 and 0.812 on two external cohorts. A 2023
[scanner-manufacturer study](https://pubmed.ncbi.nlm.nih.gov/37798392/) reports inconsistent MRI
classification performance across GE, Philips, and Siemens data. A broad 2026
[scanner-shift study](https://pubmed.ncbi.nlm.nih.gov/42062639/) reports that MRI and x-ray suffered
the largest average shift among the evaluated modalities.

**Competition inference.** Scanner/protocol grouped folds and worst-domain reporting are promotion
gates. Metadata is used to construct stress tests, not to predict labels. Domain-adversarial
training is a contrarian experiment only after the honest gap is measured.

## 17. Condition-specific anatomical localization

**Facts (T2/T3).** The multicenter knee system uses attention-guided coarse-to-fine localization;
ACL, meniscus, cartilage, breast, spine, and abdominal-trauma studies repeatedly use crops or
anatomy masks. Localization can also fail by truncating small or atypical pathology.

**Competition inference.** Test one conservative specialist family at a time, require >=99.5% crop
coverage, preserve a full-FOV fallback, and generate every learned crop fold-locally. Menisci, ACL,
and OA compartments are the first targets.

## 18. ROC-AUC-oriented ensembling

**Facts (T1/T2).** The competition metric is the equal mean of twelve rank-based AUCs. Historical
RSNA winners use OOF blends, but large ensembles often approach the runtime ceiling. Calibration or
threshold optimization does not directly improve ROC AUC ordering.

**Competition inference.** Start with two OOF-diverse families and per-label rank averaging. Compare
nested nonnegative stacking, worst-domain blends, and label-group specialists. Fit and evaluate
weights on disjoint OOF levels; prune correlations and measure marginal AUC per runtime second.

## 19. Efficient DICOM inference

**Facts (T1/T3).** Official [pydicom pixel utilities](https://pydicom.github.io/pydicom/stable/reference/pixels.utils.html)
provide source-based `pixel_array` and `iter_pixels` paths and plugin-specific decoding. Official
[PyTorch DataLoader documentation](https://docs.pytorch.org/docs/stable/data.html) supports
multi-process loading, prefetch, persistent workers, and pinned memory. Historical RSNA solutions
show that feature caching, fixed slice budgets, AMP, and early ROI filtering are material.

**Competition inference.** Profile decode, ordering, preprocessing, host-to-device transfer, model,
and write phases separately. Optimize only after parity on synthetic DICOM and a permitted fixed
batch; one decode and one shared encoder pass per selected slice is the default.

## 20. Kaggle notebook optimization

**Facts (T1).** The [competition overview](https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/overview)
requires an offline notebook and allows no more than nine hours on CPU or GPU. The published
efficiency formula includes full notebook wall time, so imports, installs, DICOM reads, model load,
and file writes count. Exact accelerator/RAM details remain unpublished and must be rechecked in
the editor at packaging.

**Competition inference.** Target <=6.5 hours and <80% peak memory, pin every offline input, remove
network/install dependencies, benchmark worst-case study counts, and keep a single reproducible
inference path. Export/compile/TensorRT is considered only after exact numerical and preprocessing
parity; a slower boring path is preferred if export destabilizes the notebook.

## Research decisions

1. Validation and label quality precede architecture complexity.
2. IM-01 (MRNet-lite) is the scientific control; IM-02/03/05 are the first efficient model screens.
3. IM-08 localization is the highest-upside model hypothesis but enters only after the baseline and
   crop-coverage audit.
4. Fold-local image-only SSL precedes image-report contrastive learning.
5. Every external dataset/checkpoint remains blocked; clean-room mechanism reproduction is allowed
   only after an experiment contract and source review.
6. Public landscape changes trigger a re-snapshot, not reactive model selection.
