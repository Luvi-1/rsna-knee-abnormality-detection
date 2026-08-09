# Reproduction candidates

Snapshot: 2026-08-08 UTC. These are clean-room mechanism reproductions, not permission to copy
code, data, checkpoints, or preprocessing artifacts. No external asset is approved. Each candidate
must receive an experiment ID and pass the contract, asset, leakage, DICOM, and compute gates before
Kaggle execution.

## Common controls

- Baselines: `B0` central slice/shared 2D encoder/mean study pooling; `B1` deterministic 24-slice
  shared encoder/mean or GeM pooling; `B2` B1 with ordered adjacent-slice 2.5D; `B3` best promoted
  sequence model; `B4` best promoted single model.
- Use locked patient/repeat/duplicate/template groups, complete OOF predictions, all 12 AUCs, the
  canonical paired protected-group Bayesian-bootstrap 95% interval defined in
  `hypothesis_backlog.md`, and a second seed for any apparent gain.
- Default success: macro OOF +0.005, at least 9/12 label deltas nonnegative, no label below -0.02,
  and the canonical interval's 2.5% lower quantile above zero.
- Packaging gate: projected hidden inference <=6.5 hours, peak memory <80%, no internet, exact
  submission schema, and numerical/preprocessing parity.
- Code-license status never clears a pretrained weight, external dataset, or derived artifact.

| Order | Candidate and mechanism | Closest primary/public baseline | Code license observed | External-asset status | MVP and compute | Candidate-specific success / kill |
|---:|---|---|---|---|---|---|
| 1 | Shared MRNet-lite multiseries MIL | [MRNet](https://doi.org/10.1371/journal.pmed.1002699): per-slice 2D features, slice pooling, three-series fusion | Article supplements CC BY 4.0; official benchmark code lacks a separately verified software license | MRNet data and historical weights blocked | B0 versus B1; smoke <1 GPU-h, full OOF about 20-30 GPU-h | Success B1 >=B0+0.005; kill <0.002 or repeated DICOM/series failures |
| 2 | Gated top-k slice attention | MRNet hard max; [ELNet](https://proceedings.mlr.press/v121/tsai20a.html) layered aggregation | ELNet AGPL-3.0; clean-room concept only | All checkpoints blocked | Frozen B1 embeddings, then one end-to-end fold; <1 then 4-6 GPU-h | Success +0.005 and >=8/12 nonnegative; kill collapse or seed variance >gain |
| 3 | Adjacent-slice 2.5D | [HIGH D-DIMER](https://pubs.rsna.org/doi/full/10.1148/ryai.2021210068) and recent RSNA trauma solutions | HIGH D-DIMER code Apache-2.0; trauma winner code Apache-2.0/MIT by repository | ImageNet/timm weights and winner artifacts blocked | B1 versus B2, same sampler/backbone; 4-6 GPU-h screen | Success target-label mean +0.008 and macro +0.003; kill >1.6x inference or no target gain |
| 4 | Per-label plane/sequence gating | MRNet fusion, published plane ablations, and [CoPAS](https://doi.org/10.1038/s41467-024-51888-4) | CoPAS Apache-2.0 | CoPAS clinical data/samples/weights blocked | Cached B1 embeddings; <1 GPU-h | Success macro +0.004 and target group +0.008; kill site/missingness dependence |
| 5 | Compact ordered GRU or transformer | RSNA ICH and PE slice encoder to sequence-model winners; shared knee slice-transformer study | ICH winner repositories NOASSERTION; PE Educational Merit code Apache-2.0 | Historical checkpoints/pretrained assets blocked | B2 embeddings to one-layer GRU/attention; 2 GPU-h smoke, 30-40 GPU-h full | Success +0.003 and correlation <0.995; kill <0.001 or >25% latency growth |
| 6 | Conservative knee ROI with full-FOV fallback | 2025 multicenter knee coarse-to-fine system; RSNA mammography, spine, and abdominal-trauma winners | KAMRNet no license; winner repos range MIT/Apache-2.0/NOASSERTION | Locators, coordinates, external data, and weights blocked | Label-free or fold-trained locator; 2 GPU-h smoke, 15-25 GPU-h full | Success crop coverage >=99.5%, target +0.010; kill any rare-label truncation cluster |
| 7 | Full-FOV plus high-resolution ROI dual input | RSNA breast ROI plus abdominal organ-crop solutions | Relevant winner repos MIT/Apache-2.0 | All external crops/data/weights blocked | Add one small ROI view to B2; 2-3 GPU-h smoke, 25-35 GPU-h full | Success macro +0.003 or small-lesion labels +0.005; kill >1.7x inference |
| 8 | Train-only localization/visibility auxiliary head | RSNA abdominal trauma rank 1; OAI meniscus auxiliary-box study | Trauma code Apache-2.0; no licensed meniscus implementation verified | Segmentation labels/models blocked; use only permitted fold-local targets | One label family, discard head at inference; 1-2 GPU-h smoke, 20-30 GPU-h full | Success reproducible +0.002 with no inference cost; kill <0.001 or shortcut behavior |
| 9 | Selective anisotropic 3D specialist | RSNA-MICCAI brain-tumor winner, knee 3D CUBE studies, and CoPAS branches | Brain-tumor code MIT; CoPAS Apache-2.0 | Checkpoints/data blocked | One downsampled ROI/series blended with B3; 4-6 GPU-h smoke, 50-80 GPU-h full | Success target +0.005 and macro +0.002; kill >2x memory or runtime gate failure |
| 10 | OOF-diverse two-model ensemble | Recurrent RSNA winner pattern; OOF teammate ensembles in lumbar-spine solutions | Mixed and component-specific; no code import planned | All historical artifacts blocked | B4 plus lowest-correlated eligible model; CPU fit plus inference benchmark | Success +0.003, correlation <0.98; kill <0.001, correlation >0.995, or >6.5 h |
| 11 | Runtime-preserving package | RSNA mammography TensorRT deployment, feature caching in ICH solutions, official PyTorch/pydicom paths | Tool licenses must be captured at implementation; no new tool approved here | Export engines/plugins blocked until exact Kaggle image and license review | Fixed slice cap, one decode, AMP; export only after parity; 2-4 GPU-h | Success >=30% speedup with absolute delta AUC <=0.001; kill any schema/order/numeric mismatch |
| 12 | OOF-only label-noise audit | [Confident Learning](https://doi.org/10.1613/jair.1.12125) and cross-fitted weak supervision | cleanlab Apache-2.0; implementation choice remains gated | No checkpoint/data required if locally authored | Rank weak-label disagreements; 3-6 GPU-h audit after OOF, optional rerun 20-30 GPU-h | Success reviewed-error enrichment >=2x random; kill in-sample probabilities or >2% automatic removal |

## Recommended execution order

`1 -> 2 -> 3 -> 4 -> 5/8 -> 6/7 -> 10 -> 11`.

Candidate 9 requires cheaper evidence from 2.5D first. Candidate 12 is an audit, not automatic
relabeling, and requires both weak-label and leakage auditor approval. External reproduction remains
fail-closed until `EXTERNAL_ASSETS.md` records exact version, URL, license, checksum, equal-access
evidence, rule justification, and approval.
