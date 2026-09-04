# T137 GitHub Public-Lead Audit

Captured: 2026-09-03

Scope: public GitHub source discovery only. No Kaggle asset download, checkpoint load, competition
input access, prediction generation, resource creation, or submission occurred in this audit.

## Disposition summary

Two public-code leads were inspected because they could plausibly affect the OA / Fluid / Bone
specialist search. Neither is promoted into the active T137 model bank by this document.

| Lead | Useful evidence | Blocking / limiting evidence | T137 disposition |
|---|---|---|---|
| `tuannm3812/kaggle-rsna-knee-abnormality-detection` | Report-free frozen DINOv2-small image baseline; target-level 58-study OOF diagnostics; max-vs-mean pooling gives positive deltas for Lateral OA, Synovitis, PF OA and Contusion | Submitted public LB only 0.681/0.687; third-party DINO processor config is CC BY-NC 4.0 and other vendored components retain their own terms; the target deltas are within a small 58-study evaluation and do not establish superiority to the project 0.929 champion | `LOW_EXPECTED_VALUE_RESEARCH_LEAD`; optional diversity-only screen if local compute is cheap |
| `evgendvorkin/rsna-baseline` as reproduced/reviewed in `tsukasahamaoka9-source/DS_Practice` | Third-party review records a source-reported public LB around 0.936 | The copied/reviewed inference explicitly loads `dreaddevelopment/raptor-knee-widedense`, a checkpoint lineage already closed by the project as report-distilled | `BLOCKED_PROVENANCE`; do not reopen without authoritative lineage change |

## Lead 1 — clean image-only DINOv2 baseline

Public source commit inspected:

```text
https://github.com/tuannm3812/kaggle-rsna-knee-abnormality-detection/tree/8c0fa9d57eefda5952e3f161308ecb75dfde06c3
```

The repository README reports:

- mean-pool submission: public LB `0.681`;
- max-pool submission: public LB `0.687`;
- pooled OOF macro AUC `0.6346` on the 58 human-labelled studies;
- informative baseline target AUCs including Effusion `0.811`, ACL `0.786`, Lateral Meniscus
  `0.755`, and Medial OA `0.752`;
- max-over-slices versus mean pooling improves Lateral OA by `+0.091`, Synovitis by `+0.076`, PF OA
  by `+0.066`, and Contusion by `+0.057`, while reducing Effusion by `-0.041`;
- complete path runtime projected around 3.5 hours with a safety margin.

The repository's own source is MIT, but its LICENSE explicitly separates third-party artifacts. It
lists, among others, a DINOv2 processor configuration under CC BY-NC 4.0 and a GPL-3.0 JPEG codec
wheel. Therefore this source is not automatically an admissible model-bank component merely because
the repository code is MIT.

T137 implication:

- The source is materially different from the previously blocked report-distilled DINO routes: it is
  an image-only frozen encoder baseline using human-labelled evaluation.
- Its overall leaderboard performance is far below the 0.929 champion, so it is not a submission
  candidate.
- The per-target max-pooling deltas are useful architecture evidence for focal OA/Synovitis/Contusion
  findings, not evidence that its ranks beat the champion.
- If the local campaign has spare private compute, the only justified use is a bounded diversity
  screen on those targets after full asset/license reauthentication. Do not spend a submission slot.

## Lead 2 — high-score `evgendvorkin/rsna-baseline`

Public review/copy inspected:

```text
https://github.com/tsukasahamaoka9-source/DS_Practice/blob/305896185b9065f0b6e2ac7fefca158ee81c8bc0/Daily_Kaggle_Review/2026-08-31/competition_rsna-baseline.ipynb
```

The public review identifies the Kaggle source notebook as:

```text
https://www.kaggle.com/code/evgendvorkin/rsna-baseline
```

and records a source-reported public score around `0.936`. The copied/reviewed inference text also
states that pretrained weights are loaded from:

```text
https://www.kaggle.com/datasets/dreaddevelopment/raptor-knee-widedense
```

The project has already established owner-authored evidence that the widedense published-arm
training route used report-distilled soft labels. Under the project's current admissibility boundary,
this is a terminal provenance blocker. A high public score does not override that gate.

T137 implication:

- Do not spend time reproducing this route under the current rules.
- Do not use its `0.936` as project performance evidence.
- Reopen only if authoritative new evidence changes the exact widedense checkpoint provenance or the
  project's admissibility decision.

## Recommended active search order

1. Reauthenticate the already reproduced EfficientNetV2-L 480 OA lead locally.
2. Reauthenticate the already reproduced CoAtNet 384 Fluid lead locally.
3. Measure their targetwise rank diversity against T133 `55976422` / `0.929`.
4. Use the clean DINOv2 max-pooling source only as a low-priority diversity lead for Lateral OA,
   Synovitis, PF OA or Contusion if the first two controls fail.
5. Keep report-distilled high-score routes closed.

This audit changes no submission authorization state.
