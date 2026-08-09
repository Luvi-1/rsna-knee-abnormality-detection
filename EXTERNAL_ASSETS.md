# External Assets

No external datasets, models, checkpoints, or code components are approved.

Chunk 3 records research candidates and observed repository licenses in
`docs/research/research_matrix.csv`; those entries are discovery evidence only and do not approve an
asset. Clean-room method reproduction does not import the cited code, weights, data, or artifacts.

Before use, record:

| Asset | Version/identifier | URL | License | Checksum | Public/equal access evidence | Rule justification | Approval |
|---|---|---|---|---|---|---|---|

Discovery is not approval. Assets with unclear provenance, non-commercial restrictions, excessive cost, geographic restrictions, or incompatible winner-delivery terms remain blocked.

## Approved private-audit and preprocessing-QA software

These public PyPI packages contain code only—no data, weights, checkpoints, or competition
artifacts. Exact source and wheel hashes are locked in `uv.lock`; each Kaggle bundle manifest
records the exact selected Linux-wheel hashes. Approval is limited to the private manifest audit
and the private `dicom-model-v1` preprocessing/visual-QA workflow. It does not approve model
training, winner delivery, or public release.

The private QA output, review plan, case/series rows, artifact hashes, and expanded finalizer
completion are derived competition artifacts, not approved external assets. They must remain in
private Kaggle resources. The pinned private finalizer consumes the completed review session
directly and may release only the disclosure-validated aggregate; no detailed review handoff may
land locally. Each uploaded private dataset must pass the ready/private and exact-manifest listing
gate before a consuming kernel is pushed; no private resource reference, URL, identifier, artifact
hash, or review row may be recorded here.

`audit-0002-manifest-remediation` executed the approved set at code commit
`6fce3af8ba1cc85dacd6a29326f999bf5f5227ed`. The pinned wheel-set SHA-256 is
`f5811d2526d041af85a463cb954ca1e01573ca2e969cd209896a1f036aa1b743`. This execution does not
approve any external dataset, model, checkpoint, training asset, or winner-delivery dependency.

| Component | Version | Source | License evidence | Access | Approval |
|---|---:|---|---|---|---|
| langdetect | 1.0.9 | `pypi:langdetect` | Apache-2.0 bundled `LICENSE` and `NOTICE`; distribution metadata's free-text `License: MIT` conflicts with its Apache classifier and files, so the bundled license controls | Public/free | Approved for audit |
| NumPy | 2.4.6 | `pypi:numpy` | SPDX expression in wheel metadata: BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Public/free | Approved for audit and private preprocessing/QA |
| Pillow | 12.3.0 | `pypi:pillow` | SPDX expression in installed distribution metadata: MIT-CMU | Public/free | Approved for deterministic private QA rendering only |
| Pydantic | 2.13.4 | `pypi:pydantic` | MIT wheel metadata | Public/free | Approved for audit and strict private preprocessing configuration |
| pydantic-core | 2.46.4 | `pypi:pydantic-core` | MIT wheel metadata | Public/free | Approved transitively |
| pydicom | 3.0.2 | `pypi:pydicom` | MIT classifier and bundled `LICENSE` notices | Public/free | Approved for audit and private preprocessing/QA |
| pylibjpeg | 2.1.0 | `pypi:pylibjpeg` | MIT classifier and bundled `LICENCE.txt` | Public/free | Approved for audit and private preprocessing/QA |
| pylibjpeg-libjpeg | 2.4.0 | `pypi:pylibjpeg-libjpeg` | GPL V3.0 metadata/classifier and bundled `LICENSE` | Public/free | Approved for private audit and preprocessing/QA only; winner-delivery compatibility remains blocked |
| pylibjpeg-openjpeg | 2.5.0 | `pypi:pylibjpeg-openjpeg` | MIT metadata/classifier and bundled `LICENSE` | Public/free | Approved for audit and private preprocessing/QA |
| annotated-types | 0.8.0 | `pypi:annotated-types` | MIT wheel metadata | Public/free | Approved transitively |
| six | 1.17.0 | `pypi:six` | MIT wheel metadata | Public/free | Approved transitively |
| typing-extensions | 4.16.0 | `pypi:typing-extensions` | PSF-2.0 wheel metadata | Public/free | Approved transitively |
| typing-inspection | 0.4.2 | `pypi:typing-inspection` | MIT wheel metadata | Public/free | Approved transitively |

Rule justification: ordinary open-source execution dependencies are equally available to every
participant, work offline, and do not introduce external medical data or model assets. Revalidate
licenses and hashes before any winner-delivery or public-release decision.
