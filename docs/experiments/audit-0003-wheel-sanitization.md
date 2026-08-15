# AUDIT-0003 — Dependency-wheel sanitization rerun contract

Status: **planned; the first release-gate tree is superseded by deployment-authentication hardening,
and a new complete gate remains pending before freeze**.

## Before run

- Audit ID: `audit-0003-wheel-sanitization`.
- Predecessor: `audit-0002-manifest-remediation`, preserved as historical scientific evidence but
  superseded as a reusable bundle root because its locked upstream `pydicom` wheel contains raw
  medical test fixtures while the bundle metadata says it contains no DICOM pixels.
- Hypothesis: removing only upstream medical fixtures from the pinned dependency wheel will preserve
  the exact `manifest-v2` audit semantics while restoring the no-raw-DICOM bundle boundary.
- Primary change: deterministically strip the packaged pydicom test tree plus every `.dcm`,
  `.dicom`, or standard `DICM`-preamble member; regenerate the wheel `RECORD`; change no manifest,
  grouping, disclosure, or DICOM-processing logic.
- Frozen controls: official competition inputs only; `manifest-v2`; `protected-groups-v2`;
  `official-labels-v1`; seed `20260808`; workers `4`; the existing manifest schema, runner,
  disclosure policy, audit-key lineage, pinned decoder versions, and no-network Kaggle execution.
  Preprocessing, folds, and model are `unassigned`; loss and augmentation are `not_applicable`;
  training, inference, and submission remain out of scope.
- Compute estimate: one private Kaggle CPU run, approximately 10,092 seconds from the predecessor,
  under the existing bounded self and outer deadlines; no accelerator or unusually large spend.
- Expected information gain: prove that the sanitized immutable bundle installs and executes
  unchanged audit logic, produces a complete authenticated source manifest, and can safely replace
  the prior source root for Chunk 5.

## Promotion criterion

Pass only if all of the following are true:

1. The exact staged source passes the complete release gate and produces a clean immutable bundle.
2. Every bundled dependency wheel is a safe regular archive with no pydicom test-tree member,
   `.dcm`/`.dicom` member, or standard `DICM` preamble; the rewritten pydicom `RECORD` exactly binds
   every retained member and preserves runtime code, metadata, and license files.
3. CPython 3.11/3.12 Linux wheel coverage, exact pydicom `RECORD`, and synthetic fixture checks pass;
   the private runner installs only the verified no-index wheelhouse and validates decoder imports
   before corpus enumeration.
4. The private dataset authenticates as ready/private/current version 1 with exact downloaded
   hashes before kernel push. Local kernel metadata authenticates before push; remote version-1
   privacy, code, source graph, listing, and unchanged dataset snapshots authenticate immediately
   after push and again before any result is accepted.
5. The full private run reaches `COMPLETE`; every discovered object reaches one terminal state;
   foreign keys, five-level reconciliation, DICOM dispositions, protected-graph closure, private
   artifact inventory, and the existing disclosure validator pass.
6. The new registry row is completed and binds the exact run-config hash, `manifest-v2`, freeze,
   bundle, and execution evidence; the predecessor remains preserved and is not reused by Chunk 5.

## Kill criterion

Stop and fail closed on contract drift; any medical payload remaining in a wheel; missing or invalid
wheel metadata, license, or `RECORD`; offline install or synthetic-preflight failure; unexpected
input or output inventory; any identifier, path, report, pixel, patient metadata, private reference,
or sensitive detail in an export or log; incomplete terminal accounting; unexplained DICOM issues;
hard/soft grouping drift; disclosure failure; or a runtime/deadline failure. Do not patch a generated
bundle or reuse any prior source-manifest or DICOM-QA chain after a failure.

## After run

The first exact staged gate passed on tree `5bea3c110e100e9ddd2d94c8b89c29e1f0ff82a0`, including
530/530 tests and the complete build, static, privacy, dependency, schema, contract, and clean-tree
checks. Preflight then found that the project wheel and remote manifest deployment lacked the same
explicit authentication applied to dependencies and Chunk 5 inputs. It also found that a safe
sibling wheel directory could satisfy the scan independently of the verified manifest root, and
that raw status/transport commands could expose a private reference. That tree is superseded.

The current minimal candidate validates the project wheel through the shared archive guard; binds
the exact manifest dataset root, metadata, two-file kernel upload, script hash, every wheel, and the
pydicom `RECORD` before any network call; reuses the existing exact-version Kaggle authentication
helpers; and exposes only fixed status or authentication tokens. Its non-final checks pass: full
pytest 537/537, combined manifest/DICOM packaging 204/204, Ruff check/format, strict mypy over 25
package and 11 trust-boundary files, shell/privacy checks, and two independent P0/P1 red-team
reviews. A complete staged D-015 gate, freeze, bundle, and private execution remain pending. Record
the exact freeze, bundle, input versions, runtime, aggregate validation, registry state, and
keep/reject decision only after authenticated completion.
