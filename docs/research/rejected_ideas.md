# Ideas rejected immediately

Snapshot: 2026-08-08 UTC. These ideas are excluded before experimentation. A high apparent upside
does not override an impossible test interface, invalid validation, leakage, privacy, or licensing.
Scores use the formula in `hypothesis_backlog.md`; they are retained to expose why attractive but
invalid ideas were considered.

| ID | Rejected idea | Priority | Evidence-backed reason | Failure mode | Reversal condition |
|---|---|---:|---|---|---|
| RJ-01 | Depend on radiology reports during inference | 19 | The competition host states test reports are unavailable before and after notebook submission. | The feature cannot exist for the hidden test; training/inference mismatch is certain. | Only an official contract change that supplies scoring-time reports. |
| RJ-02 | Predict from scanner, site, UID shape, series composition, or metadata fingerprints | 21 | A current participant's metadata probe reported a random-fold macro AUC of 0.6516 falling to 0.5981 under scanner-fingerprint GroupKFold; this is a public claim, not validated ground truth, but it demonstrates shortcut risk. | Site prevalence and acquisition policy inflate local/public results and can invert on hidden sites; unpublished DICOM-tag availability also makes the interface unsafe. | Metadata may be used only for grouping, QA, sequence identity, and explicit missingness unless organizers define a stable clinical covariate and grouped OOF proves transportability. |
| RJ-03 | Use patient-random folds as the only validation | 10 | Multi-center knee studies and prior RSNA solutions require patient/group separation; this dataset may also contain repeats, duplicates, templates, and scanner/site structure. | Optimistic OOF, invalid model selection, and public-leaderboard overfitting. | Never as the only regime. It may remain a diagnostic comparison after protected grouped folds are locked. |
| RJ-04 | Generate a pseudo-label from a model trained on that study, fit thresholds/ensemble weights on their evaluation rows, or tune from public-LB movement | 14 | The Master Operating Prompt prohibits same-study pseudo-labeling and same-row ensemble fitting; pseudo-label literature documents confirmation bias. | Direct leakage and circular evidence that cannot support promotion. | None. A strictly grouped, cross-fitted teacher with auditable ancestry is a different hypothesis (LQ-05). |
| RJ-05 | Import an uncleared external dataset/checkpoint/notebook or send raw reports/DICOMs to an external LLM/API | 13 | Competition rules require adequate rights and equal access; MIRA and the repository privacy boundary prohibit redistribution/external disclosure. Public notebook licenses do not automatically cover weights or data. | Rule breach, privacy breach, irreproducible winner deliverable, or unavailable offline inference asset. | Exact version, public URL/identifier, code and weight/data licenses, checksum, equal-access evidence, offline packaging, MIRA compatibility, and explicit approval are all documented before use. Raw report or DICOM upload remains prohibited. |

## Tempting but deferred, not rejected

- Full-resolution 3D multi-plane networks: defer until a selective anisotropic 3D branch proves that
  2.5D lacks necessary context and the runtime margin survives.
- Large medical vision-language foundation models: defer until an exact checkpoint is freely and
  equally accessible, license-cleared, offline-packaged, and shown to improve a cheaper image-only
  baseline. Report text remains training-only and private.
- Large historical winner ensembles: reproduce mechanisms, not their 11-to-30-model footprint.
- Automatic weak-label correction: begin with audit queues; never overwrite official labels.
