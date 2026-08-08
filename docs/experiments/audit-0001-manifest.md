# AUDIT-0001 — Historical full-data manifest and leakage audit

Status: **superseded for promotion and downstream use** by Checkpoint 1 remediation. Preserved as a
historical audit record; no preprocessing, folds, weak labels, model, prediction, ensemble, or
submission followed it.

Superseded by: planned `audit-0002-manifest-remediation` (not yet executed).

## Before run

- Audit ID: `audit-0001-manifest`.
- Hypothesis: a five-level manifest plus protected duplicate components could account for every
  accessible study, series, file, report, and official label cell while quantifying only supported
  train/example-test shift without exporting row-level data.
- Primary change: inventory and audit only.
- Frozen controls: contract snapshot `2026-08-08T025148Z`, schema `manifest-v1`, grouping
  `protected-groups-v1`, official labels only, and preprocessing/folds/models unassigned.
- Label version: `official-labels-v1`.
- Seeds: `0` for deterministic language detection and `20260808` for deterministic QA sampling.
- Compute estimate: one private CPU Kaggle run, 21,600-second self-deadline, 23,400-second outer
  deadline, no accelerator.
- Original promotion criterion: all accessible entities reconcile; privacy and disclosure checks
  pass; every duplicate candidate is grouped or blocks; provenance hashes are recorded; and shift
  claims remain within observed support.
- Original kill criterion: contract drift, sensitive content in any export/log, count mismatch,
  unclassified entity, non-deterministic content hash, incomplete duplicate grouping, or
  label/provenance coercion.

## Historical execution and provenance

- Private execution completed in 11,453 seconds on CPU, within the recorded self and outer
  deadlines. No separate monetary cost was recorded.
- Code commit: `75792aad08a3685d0c9ce92b5cab90307bf1336c`.
- Bundle SHA-256: `428c76fc30c15233afa2c2527ed3d41709f43a31a97d79dbfd39d6de2ddddd3e`.
- Competition-config SHA-256: `c41ce0dad5c24cd9a051facda3a4907c6f5bf5a0dc045df9eb9e380cbfe79006`.
- Competition-contract SHA-256: `f96608e3898126354a8f1ca2ec3157785359fb3485eab2539125d840ba2f4a79`.
- Manifest-schema SHA-256: `9e5f598e2bb927132116bbc6b9023f354965015a194b46227cee5a10d360218a`.
- `uv.lock` SHA-256: `d707ff22384bcbda10bc5ccd5780690794f5c5b3d1c92860a2a63eaa87caf759`.
- Historical versions: `manifest-v1`, `protected-groups-v1`, `official-labels-v1`;
  preprocessing and folds `unassigned`.

### Historical release hashes

These hashes preserve non-sensitive provenance. The artifacts they identify are superseded and
must not be republished or used as current results.

| Artifact | SHA-256 |
|---|---|
| `sanitized_summary.json` | `71bf1fc11322f647a7147760bca428643f2c1c5ab35b0c54a419647d72ed5220` |
| `data_audit.md` | `776a2b722e8527f7d0f92d27bfa6a0651d3c335e0b5d5ef4ffb62b9995a4394f` |
| `leakage_audit.md` | `4048ae5f062e3baac5547820ac2355b6799cf674654d74e4ded78d7f6bfb1dcd` |
| `domain_shift_audit.md` | `896e5841545b37ba6415805ca20cd0e09aa29012d1c98a6bcc120b21370e3fe9` |
| `sanitized_artifact_inventory.json` | `e7366141b02a0ec617f92725fe54bfce7dfba55fa4923b477cb0e6654cd83665` |

Private manifest roots, row-level hashes, grouping keys, identifiers, reports, pixels, QA selections,
private references, and session logs were not intentionally retrieved from the private Kaggle run.

## Why the original pass claim is withdrawn

The run passed the validator that existed at the time, but that validator was not sufficient for
the current disclosure and evidence standard:

1. Independent field suppression left totals/complements from which a below-threshold value could
   be reconstructed. The result release is therefore not privacy-valid under the joint disclosure
   policy.
2. `protected-groups-v1` mixed accepted hard duplicate/repeat evidence with weak similarity and
   overflow-candidate evidence. Its component-closure result cannot establish fold feasibility.
3. DICOM decode/quarantine findings were represented by a nonzero privacy token but had not all
   received private case-level root-cause and deterministic disposition review.
4. The “final secret scan passed” report preceded the final tracked file set; the clean committed
   branch subsequently flagged five reviewed provenance/content hashes.
5. No GitHub-hosted CI result established that the cumulative branch was remotely valid.

The former exact aggregate narrative is deliberately not repeated here because preserving an
unsafe release equation would repeat the disclosure defect. The correction record preserves the
fact of the defect, the old artifact hashes, code/config provenance, runtime, and decisions without
releasing private identifiers or rare counts.

## Historical decision and successor gate

The original audit correctly blocked downstream work, but for incomplete reasons. It is now
formally superseded rather than overwritten. The registry successor must be a new row named
`audit-0002-manifest-remediation` and must reference this audit as its predecessor.

The successor may pass only when every accessible object reconciles; every DICOM exception has an
explained deterministic disposition; hard and soft grouping semantics validate separately; every
approved aggregate is regenerated from the central joint-disclosure boundary; the old audit is
marked superseded without losing provenance; and local plus remote release gates pass. Until that
evidence exists, downstream data and model work remains blocked.
