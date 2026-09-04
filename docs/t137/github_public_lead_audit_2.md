# T137 GitHub Public-Lead Audit — Additional Multi-Plane Lead

Captured: 2026-09-03

Scope: public GitHub source inspection only. No Kaggle asset download, competition-data access,
checkpoint load, inference, prediction generation, resource creation, or submission occurred.

## `sam12fak/rsna-knee-abnormality-detection`

Pinned public source commit:

```text
507bf62cc81d3fabd605a4f00490ebefceb44b0c
```

The repository is relevant to T137 because its README describes a multi-plane knee-MRI pipeline
using sagittal and coronal images, fixed 32-slice sampling, and an ensemble involving ResNet50,
EfficientNet-B0, and DenseNet121 families. That makes it architecturally different from the current
T133 Raptor champion and therefore potentially interesting as a diversity lead.

### Report boundary

A repository code search for `Report` returned README/documentation context rather than an active
report-reading inference path. The inspected inference source loads image-model checkpoints and
operates on image inputs. This is useful negative evidence for the hidden-inference report boundary,
but it is not enough by itself to certify the whole route.

### Blocking evidence

The inspected inference code expects external checkpoint files loaded with `torch.load`. The public
repository does not establish an exact immutable checkpoint bundle, checkpoint SHA-256 values, or an
independently verified public leaderboard score for the route. A `LICENSE` file was not available at
the pinned repository path during this audit, so actionable source/license terms are also not bound.

Therefore this source cannot enter the active model bank under the project contract merely from its
architecture description.

### T137 disposition

```text
BLOCKED_SOURCE_AND_LICENSE
```

Rationale:

- architecture is potentially complementary;
- inference appears image-oriented rather than report-dependent in the inspected source;
- exact trained weights are not checksum-bound from this public source;
- actionable repository/checkpoint license terms are not established;
- no trustworthy source score or target-level validation is bound to exact released weights.

Do not spend a competition submission slot on this lead. Reopen only if an exact public weight bundle
with actionable terms and reproducible source/output evidence is identified.

## Updated specialist-search priority

1. Reauthenticate the already reproduced EfficientNetV2-L 480 OA control in the current local
   campaign history.
2. Reauthenticate the already reproduced CoAtNet 384 Fluid control.
3. Measure targetwise rank diversity against T133 submission `55976422` / `0.929` on an approved
   private cohort.
4. Use the previously recorded clean DINOv2-small max-pooling source only as a low-priority
   diversity lead after its third-party asset terms are reauthenticated.
5. Keep this `sam12fak` multi-plane route blocked unless exact public weights and license evidence
   emerge.
6. Keep report-distilled high-score routes closed.

This audit changes no submission-authorization state.
