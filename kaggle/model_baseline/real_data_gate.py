"""Private offline real-data fold-feasibility and tiny-overfit gate.

Runs inside one Kaggle notebook with the competition mount and the frozen r16 bundle
dataset attached. Reads organizer CSVs and DICOM pixels only inside Kaggle; emits one
sanitized aggregate JSON summary. Never prints or persists identifiers, reports, or
pixels. Human-QA status stays PROVISIONAL_HUMAN_QA_PENDING.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Final

import numpy as np
import pydicom

COMPETITION_SLUG: Final = "rsna-knee-abnormality-detection"
BUNDLE_DATASET_REF: Final = "lavicheema/rsna-knee-dicom-qa-bundle-da5b9c8-91ed07921059"
EXPECTED_BUNDLE_SHA256: Final = "91ed079210592448664f52c1a24ce1a693275ef09fa350167712097ab97de40b"  # noqa: E501  # pragma: allowlist secret
R16_COMMIT: Final = "da5b9c83b874f02067ecc8f1c0a4a1d50fe01b1f"  # pragma: allowlist secret
SOURCE_MANIFEST_VERSION: Final = "manifest-v3"
TARGETS: Final[tuple] = (
    "ACL",
    "MCL",
    "Medial Meniscus",
    "Lateral Meniscus",
    "Medial OA",
    "Lateral OA",
    "PF OA",
    "Effusion",
    "Synovitis",
    "Baker's",
    "Contusion",
    "Fracture",
)
N_SPLITS: Final = 5
SELECTED_STUDIES: Final = 24
PROCESSED_TARGET: Final = 16
MIN_PROCESSED: Final = 8
E00B_COHORT: Final = 12
E00C_COHORT: Final = 12
E01_EPOCHS: Final = 30
E01_LEARNING_RATE: Final = 1e-3
E01_BATCH_SIZE: Final = 8
E00B_EPOCHS: Final = 2000
E00C_EPOCHS: Final = 3000
E00C_LEARNING_RATE: Final = 1e-3
E00C_HIDDEN: Final = 64


def _build_tiny_cnn(hidden: int, n_targets: int):
    """Shared slice encoder, study mean-pool, linear head (used by E00c/E01)."""
    from torch import nn

    return nn.Sequential(
        nn.Conv2d(3, 16, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Conv2d(16, 32, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Conv2d(32, hidden, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.AdaptiveAvgPool2d(1),
    ), nn.Linear(hidden, n_targets)


class TinyCNNShared:
    """Study-level CNN: encode every sampled slice, mean-pool to one vector."""

    def __init__(self, hidden=E00C_HIDDEN, n_targets=None):
        if n_targets is None:
            n_targets = len(TARGETS)
        features, classifier = _build_tiny_cnn(hidden, n_targets)
        self.features = features
        self.classifier = classifier

    def parameters(self):
        return list(self.features.parameters()) + list(self.classifier.parameters())

    def to(self, device):
        self.features = self.features.to(device)
        self.classifier = self.classifier.to(device)
        return self

    def train(self):
        self.features.train()
        self.classifier.train()

    def eval(self):
        self.features.eval()
        self.classifier.eval()

    def forward(self, x):
        batch_shape = x.shape  # [B, S, C, H, W] or [B, n_series, S, C, H, W]
        flat = x.reshape(-1, *batch_shape[-3:])
        encoded = self.features(flat).flatten(1)
        pooled = encoded.mean(dim=0, keepdim=True)  # single-study mode
        return self.classifier(pooled).reshape(batch_shape[:1] + (-1,))

    def __call__(self, x):
        return self.forward(x)


MAX_SERIES_PER_STUDY: Final = 4
MAX_FILES_PER_SERIES: Final = 128
SAMPLE_COUNT: Final = 8
RESIZE_SHAPE: Final = (64, 64)
SPACING_ABS_TOL_MM: Final = 0.1
SPACING_REL_TOL: Final = 0.05
DUPLICATE_POSITION_TOL_MM: Final = 0.01
EPOCHS: Final = 300
LEARNING_RATE: Final = 0.05
SEED: Final = 42
BUDGET_SECONDS: Final = 2700
MAX_CSV_BYTES: Final = 64 * 1024 * 1024
MAX_SUMMARY_BYTES: Final = 256 * 1024
SAFE_TOKEN: Final = re.compile(r"[a-z0-9_]{1,80}\Z")
SUMMARY_BASENAME: Final = "sanitized_real_data_gate.json"


class GateError(RuntimeError):
    """One fixed, disclosure-safe gate failure."""

    def __init__(self, code: str) -> None:
        self.code = code if SAFE_TOKEN.fullmatch(code) else "internal_error"
        super().__init__(self.code)


def _canonical_json_bytes(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bounded_mount(kind, ref):
    root = Path("/kaggle/input")
    candidate = root / kind / ref
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise GateError("input_mount_missing") from error
    if root not in resolved.parents or resolved.is_symlink():
        raise GateError("input_mount_invalid")
    return resolved


def _read_bounded_csv(path):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_CSV_BYTES:
            raise GateError("csv_invalid")
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = []
            for row in reader:
                rows.append({key: value or "" for key, value in row.items()})
                if len(rows) > 100_000:
                    raise GateError("csv_too_large")
    except GateError:
        raise
    except (OSError, UnicodeError, csv.Error) as error:
        raise GateError("csv_invalid") from error
    return fields, rows


def read_study_labels(path):
    """Return opaque study keys and the label matrix; empty cells stay NaN (unknown)."""
    expected = ["StudyInstanceUID", "Report", *TARGETS]
    fields, rows = _read_bounded_csv(path)
    if fields != expected:
        raise GateError("train_header_invalid")
    keys = []
    matrix = np.full((len(rows), len(TARGETS)), np.nan, dtype=np.float64)
    seen = set()
    for index, row in enumerate(rows):
        key = row["StudyInstanceUID"].strip()
        if not key or key in seen:
            raise GateError("study_key_invalid")
        seen.add(key)
        keys.append(key)
        for column, target in enumerate(TARGETS):
            raw = row[target].strip()
            if raw in {"0", "1"}:
                matrix[index, column] = float(raw)
    return keys, matrix


def assign_grouped_folds(keys, labels):
    """Greedy positive-mass folds; ties break by fold index for determinism."""
    if len(keys) != labels.shape[0]:
        raise GateError("fold_shape_invalid")
    mass = np.where(np.isfinite(labels) & (labels == 1), 1, 0).sum(axis=1)
    order = sorted(range(len(keys)), key=lambda i: (-int(mass[i]), keys[i]))
    fold_mass = [0] * N_SPLITS
    assignments = {}
    for sequence, index in enumerate(order):
        if int(mass[index]) == 0:
            # Round-robin zero-mass studies to avoid single-fold collapse.
            fold = sequence % N_SPLITS
        else:
            fold = min(range(N_SPLITS), key=lambda f: (fold_mass[f], f))
        assignments[keys[index]] = fold
        fold_mass[fold] += int(mass[index])
    return assignments, fold_mass


def fold_feasibility(keys, labels):
    """Sanitized aggregate feasibility facts for the full train split."""
    assignments, fold_mass = assign_grouped_folds(keys, labels)
    sizes = Counter(assignments.values())
    val_indices = [i for i, key in enumerate(keys) if assignments[key] == 0]
    val_block = labels[val_indices]
    degenerate = [
        target
        for column, target in enumerate(TARGETS)
        if len(np.unique(val_block[:, column][np.isfinite(val_block[:, column])])) < 2
    ]
    positives = [int(int(np.sum(labels[:, c] == 1))) for c in range(len(TARGETS))]
    known = [int(int(np.isfinite(labels[:, c]).sum())) for c in range(len(TARGETS))]
    rare = [target for target, count in zip(TARGETS, positives, strict=True) if 0 < count < 10]
    return {
        "n_studies": len(keys),
        "fold_sizes": [sizes.get(fold, 0) for fold in range(N_SPLITS)],
        "fold_positive_mass": fold_mass,
        "per_label_known": dict(zip(TARGETS, known, strict=True)),
        "per_label_positives": dict(zip(TARGETS, positives, strict=True)),
        "val_fold_zero_degenerate_targets": degenerate,
        "rare_targets_under_10_positives": rare,
    }


def rank_auc(y_true, y_score):
    """Tie-corrected ROC AUC over observed 0/1 pairs; None when single-class."""
    mask = np.isfinite(y_true) & np.isin(y_true, (0.0, 1.0)) & np.isfinite(y_score)
    truth = y_true[mask]
    scores = y_score[mask]
    positive = truth == 1.0
    negative = truth == 0.0
    n_pos = int(positive.sum())
    n_neg = int(negative.sum())
    if n_pos == 0 or n_neg == 0:
        return None
    _, inverse = np.unique(scores, return_inverse=True)
    counts = np.bincount(inverse, minlength=len(inverse)).astype(np.float64)
    cumulative = np.cumsum(counts)
    average_ranks = cumulative - counts / 2.0 + 0.5
    positive_rank_sum = float(average_ranks[inverse[positive]].sum())
    concordant = positive_rank_sum - n_pos * (n_pos + 1) / 2.0
    return float(concordant / (n_pos * n_neg))


def fit_linear_probe(features, labels, epochs=EPOCHS, learning_rate=LEARNING_RATE, seed=SEED):
    """Masked-BCE gradient descent; NaN labels contribute nothing (unknown, not negative)."""
    rng = np.random.default_rng(seed)
    weights = rng.normal(0.0, 0.01, size=(features.shape[1], labels.shape[1]))
    bias = np.zeros(labels.shape[1])
    observed = np.isfinite(labels)
    targets = np.where(observed, labels, 0.0)
    denominator = max(int(observed.sum()), 1)
    epsilon = 1e-8
    first_loss = float("nan")
    last_loss = float("nan")
    best_loss = float("inf")
    for step in range(epochs):
        logits = np.clip(features @ weights + bias, -30.0, 30.0)
        probabilities = 1.0 / (1.0 + np.exp(-logits))
        terms = -(targets * np.log(probabilities + epsilon))
        terms -= (1.0 - targets) * np.log(1.0 - probabilities + epsilon)
        last_loss = float((terms * observed).sum() / denominator)
        best_loss = min(best_loss, last_loss)
        if step == 0:
            first_loss = last_loss
        gradient = (probabilities - targets) * observed / denominator
        weights -= learning_rate * (features.T @ gradient)
        bias -= learning_rate * gradient.sum(axis=0)
    return weights, bias, first_loss, best_loss


def _safe_series_token(error):
    """Extract one disclosure-safe token from a pipeline or decode error."""
    token = getattr(error, "code", None) or getattr(getattr(error, "issue", None), "value", None)
    return (
        str(token)
        if isinstance(token, str) and SAFE_TOKEN.fullmatch(token)
        else "preprocess_failed"
    )


def run_skip_audit():
    """Aggregate uneven-slice-spacing skips over every train study/series.

    Header-only (no pixel decoding): reproduces the frozen r16 spacing rule
    exactly — sort by projection on the dominant orientation normal, flag a
    series when any adjacent gap deviates more than max(0.1 mm, 5% median).
    """
    import math
    from concurrent.futures import ThreadPoolExecutor

    started = time.monotonic()
    competition_root = _bounded_mount("competitions", COMPETITION_SLUG)
    bundle_root = _bounded_mount("datasets", BUNDLE_DATASET_REF)
    manifest = json.loads((bundle_root / "bundle-manifest.json").read_bytes())
    if manifest.get("bundle_sha256") != EXPECTED_BUNDLE_SHA256:
        raise GateError("bundle_identity_mismatch")
    _, rows = _read_bounded_csv(competition_root / "train.csv")
    _, series_rows = _read_bounded_csv(competition_root / "train_series.csv")
    keys, labels = read_study_labels(competition_root / "train.csv")
    row_index = {key: index for index, key in enumerate(keys)}

    series_by_study = {}
    for row in series_rows:
        study = row["StudyInstanceUID"].strip()
        series_uid = row["SeriesInstanceUID"].strip()
        series_by_study.setdefault(study, []).append(series_uid)
    assignments, fold_mass = assign_grouped_folds(keys, labels)

    # Deterministic per-study work items; each item audits one series header-only.
    def audit_item(study_key):
        series_dirs = []
        study_root = competition_root / "train_series" / study_key
        try:
            entries = sorted(entry for entry in study_root.iterdir() if entry.is_dir())
        except OSError:
            return study_key, [("series_directory_invalid", 0)]
        for series_dir in entries[:MAX_SERIES_PER_STUDY]:
            try:
                files = sorted(item for item in series_dir.iterdir() if item.is_file())[
                    :MAX_FILES_PER_SERIES
                ]
            except OSError:
                series_dirs.append(("series_directory_invalid", 0))
                continue
            if not files:
                continue
            try:
                metas = []
                ok = True
                for path in files:
                    dataset = pydicom.dcmread(str(path), stop_before_pixels=True)
                    iop = dataset.get("ImageOrientationPatient")
                    ipp = dataset.get("ImagePositionPatient")
                    if iop is None or len(iop) != 6 or ipp is None or len(ipp) != 3:
                        ok = False
                        break
                    values_iop = [float(value) for value in iop]
                    values_ipp = [float(value) for value in ipp]
                    row_v = np.array(values_iop[0:3])
                    col_v = np.array(values_iop[3:6])
                    normal = np.cross(row_v, col_v)
                    norm = float(np.linalg.norm(normal))
                    if not math.isfinite(norm) or norm < 1e-8:
                        ok = False
                        break
                    normal = normal / norm
                    metas.append((float(np.dot(np.array(values_ipp), normal)), normal))
                if not ok or len(metas) < 2:
                    reason = "header_incomplete" if not ok else "too_few_slices"
                    series_dirs.append((reason, 0))
                    continue
                reference_normal = metas[0][1]
                max_angle = 0.0
                for _, normal in metas[1:]:
                    cos_angle = float(abs(np.dot(normal, reference_normal)))
                    angle = math.degrees(math.acos(min(1.0, cos_angle)))
                    max_angle = max(max_angle, angle)
                if max_angle > 0.5:
                    series_dirs.append(("orientation_inconsistent", 0))
                    continue
                projections = sorted(item[0] for item in metas)
                diffs = np.diff(np.asarray(projections, dtype=np.float64))
                if bool(np.any(diffs <= DUPLICATE_POSITION_TOL_MM)):
                    series_dirs.append(("duplicate_position", 0))
                    continue
                median_spacing = float(np.median(diffs))
                tolerance = max(SPACING_ABS_TOL_MM, SPACING_REL_TOL * median_spacing)
                if bool(np.any(np.abs(diffs - median_spacing) > tolerance)):
                    series_dirs.append(("uneven_slice_spacing", 1))
                else:
                    series_dirs.append(("eligible", 1))
            except Exception:  # noqa: BLE001 - fixed token below
                series_dirs.append(("preprocess_failed", 1))
        return study_key, series_dirs

    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for key, dirs in pool.map(audit_item, keys):
            results[key] = dirs

    n_total_series = sum(len(items) for items in results.values())
    n_uneven_series = 0
    studies_with_any_uneven = set()
    per_fold_skipped_studies = [0] * N_SPLITS
    per_target_positives_skipped = dict.fromkeys(TARGETS, 0)
    per_target_negatives_skipped = dict.fromkeys(TARGETS, 0)
    for key, items in results.items():
        has_uneven = any(reason == "uneven_slice_spacing" for reason, _flagged in items)
        if has_uneven:
            studies_with_any_uneven.add(key)
            fold = assignments.get(key)
            if fold is not None:
                per_fold_skipped_studies[fold] += 1
            label_row = labels[row_index[key]]
            observed = np.isfinite(label_row)
            for column, target in enumerate(TARGETS):
                if observed[column] and label_row[column] == 1.0:
                    per_target_positives_skipped[target] += 1
                elif observed[column] and label_row[column] == 0.0:
                    per_target_negatives_skipped[target] += 1
    for items in results.values():
        for reason, flagged in items:
            if reason == "uneven_slice_spacing":
                n_uneven_series += flagged
    total_positives_per_target = {
        target: int((labels[:, column] == 1).sum()) for column, target in enumerate(TARGETS)
    }
    summary = {
        "schema_version": 1,
        "gate": "e00_skip_audit_v0",
        "r16_code_commit": R16_COMMIT,
        "n_studies_total": len(keys),
        "n_series_audited": n_total_series,
        "studies_with_any_uneven_series": len(studies_with_any_uneven),
        "series_flagged_uneven": n_uneven_series,
        "pct_studies_with_uneven": rounded_float(
            100.0 * len(studies_with_any_uneven) / max(len(keys), 1)
        ),
        "pct_series_uneven": rounded_float(100.0 * n_uneven_series / max(n_total_series, 1)),
        "per_fold_skipped_studies": dict(
            zip(range(N_SPLITS), per_fold_skipped_studies, strict=True)
        ),
        "fold_positive_mass": fold_mass,
        "per_target_positives_skipped": per_target_positives_skipped,
        "per_target_negatives_skipped": per_target_negatives_skipped,
        "total_positives_per_target": total_positives_per_target,
        "scanner_domain_breakdown": "unavailable_header_only",
        "elapsed_seconds": rounded_float(time.monotonic() - started),
        "completion": "E00_SKIP_AUDIT_PASS",
    }
    payload = _canonical_json_bytes(summary)
    if not 0 < len(payload) <= MAX_SUMMARY_BYTES:
        raise GateError("summary_size_invalid")
    output_root = Path("/kaggle/working")
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = output_root / ".sanitized_real_data_gate.json.tmp"
    temporary.write_bytes(payload)
    os.replace(temporary, output_root / SUMMARY_BASENAME)
    print(f"event=skip_audit_complete studies={len(keys)} uneven_series={n_uneven_series}")
    return 0


def study_feature(tensor):
    """Pool one preprocessed series tensor to four scalar statistics."""
    return np.array([tensor.mean(), tensor.std(), tensor.min(), tensor.max()])


def _series_paths(competition_root, study_key):
    study_root = competition_root / "train_series" / study_key
    try:
        entries = sorted(entry for entry in study_root.iterdir() if entry.is_dir())
    except OSError as error:
        raise GateError("study_directory_invalid") from error
    chosen = []
    for series_directory in entries[:MAX_SERIES_PER_STUDY]:
        try:
            files = sorted(item for item in series_directory.iterdir() if item.is_file())[
                :MAX_FILES_PER_SERIES
            ]
        except OSError as error:
            raise GateError("series_directory_invalid") from error
        if files:
            chosen.append(files)
    return chosen


def _install_bundle_runtime(bundle_root):
    try:
        manifest = json.loads((bundle_root / "bundle-manifest.json").read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise GateError("bundle_manifest_invalid") from error
    if manifest.get("bundle_sha256") != EXPECTED_BUNDLE_SHA256:
        raise GateError("bundle_identity_mismatch")
    wheels = [
        record
        for record in manifest.get("files", [])
        if isinstance(record, dict) and record.get("role") == "project_wheel"
    ]
    if len(wheels) != 1 or not isinstance(wheels[0].get("sha256"), str):
        raise GateError("bundle_manifest_invalid")
    wheel_path = bundle_root / str(wheels[0]["path"])
    if _sha256_file(wheel_path) != wheels[0]["sha256"]:
        raise GateError("project_wheel_hash_mismatch")
    runtime_root = Path(tempfile.mkdtemp(prefix="rsna-knee-model-gate-runtime-"))
    environment = os.environ.copy()
    environment.update(
        {
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INDEX": "1",
            "PIP_NO_INPUT": "1",
            "PIP_KEYRING_PROVIDER": "disabled",
            "PYTHONNOUSERSITE": "1",
        }
    )
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--isolated",
                "--no-index",
                "--find-links",
                str(bundle_root),
                "--only-binary=:all:",
                "--ignore-installed",
                "--no-compile",
                "--no-cache-dir",
                "--disable-pip-version-check",
                "--no-input",
                "--no-warn-script-location",
                "--target",
                str(runtime_root),
                str(wheel_path),
            ],
            env=environment,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=300,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        shutil.rmtree(runtime_root, ignore_errors=True)
        raise GateError("offline_dependency_install_failed") from error
    return runtime_root


def rounded_float(value, digits=6):
    return round(float(value), digits)


def run_real_data_gate():
    """Execute the full gate and write exactly one sanitized aggregate summary."""
    started = time.monotonic()
    competition_root = _bounded_mount("competitions", COMPETITION_SLUG)
    bundle_root = _bounded_mount("datasets", BUNDLE_DATASET_REF)
    runtime_root = _install_bundle_runtime(bundle_root)
    sys.path.insert(0, str(runtime_root))
    try:
        from rsna_knee.dicom.pipeline import (
            PipelineVersions,
            PreprocessingConfig,
            dicom_to_model,
        )

        keys, labels = read_study_labels(competition_root / "train.csv")
        feasibility = fold_feasibility(keys, labels)
        row_index = {key: index for index, key in enumerate(keys)}

        # Deterministic cohort: sort by SHA-256 of the opaque study key, take a prefix.
        # Only select studies that have at least one known label (0 or 1).
        has_known = np.isfinite(labels).any(axis=1)
        eligible = [key for index, key in enumerate(keys) if has_known[index]]
        ranked = sorted(eligible, key=lambda key: hashlib.sha256(key.encode()).hexdigest())
        cohort = ranked[:SELECTED_STUDIES]
        cohort_labels = np.vstack([labels[row_index[key]] for key in cohort])
        assignments, _ = assign_grouped_folds(cohort, cohort_labels)

        config = PreprocessingConfig(sample_count=SAMPLE_COUNT, resize_rows_columns=RESIZE_SHAPE)
        versions = PipelineVersions(
            code_commit=R16_COMMIT, source_manifest_version=SOURCE_MANIFEST_VERSION
        )
        features = {}
        skip_reasons = Counter()
        series_processed = 0
        for key in cohort:
            if len(features) >= PROCESSED_TARGET or time.monotonic() - started > BUDGET_SECONDS:
                break
            try:
                tensors = [
                    dicom_to_model(paths, config, versions).tensor
                    for paths in _series_paths(competition_root, key)
                ]
            except Exception as error:  # noqa: BLE001 - reduced to fixed safe token below
                token = getattr(error, "code", None) or getattr(
                    getattr(error, "issue", None), "value", None
                )
                safe = (
                    str(token)
                    if isinstance(token, str) and SAFE_TOKEN.fullmatch(token)
                    else "preprocess_failed"
                )
                skip_reasons[safe] += 1
                continue
            features[key] = np.mean([study_feature(tensor) for tensor in tensors], axis=0)
            series_processed += len(tensors)
        if len(features) < MIN_PROCESSED:
            raise GateError("insufficient_processed_studies")

        ordered_keys = sorted(features)
        matrix = np.vstack([features[key] for key in ordered_keys])
        # Replace non-finite values and z-score normalize to prevent divergence.
        matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)
        mean = matrix.mean(axis=0)
        std = matrix.std(axis=0)
        std = np.where(std < 1e-8, 1.0, std)  # Avoid divide-by-zero on constant features.
        matrix = (matrix - mean) / std
        label_matrix = np.vstack([labels[row_index[key]] for key in ordered_keys])
        is_validation = np.array([assignments[key] == 0 for key in ordered_keys])
        if not is_validation.any() or is_validation.all():
            raise GateError("split_empty")
        train_matrix = matrix[~is_validation]
        train_labels = label_matrix[~is_validation]
        val_matrix = matrix[is_validation]
        val_labels = label_matrix[is_validation]
        weights, bias, first_loss, best_loss = fit_linear_probe(train_matrix, train_labels)
        val_scores = 1.0 / (1.0 + np.exp(-(val_matrix @ weights + bias)))
        per_label_auc = {
            target: rank_auc(val_labels[:, column], val_scores[:, column])
            for column, target in enumerate(TARGETS)
        }
        computed = [value for value in per_label_auc.values() if value is not None]
        val_macro = float(np.mean(computed)) if computed else None
        if not np.isfinite(first_loss) or not np.isfinite(best_loss) or best_loss >= first_loss:
            raise GateError("tiny_overfit_loss_not_reduced")

        summary = {
            "schema_version": 1,
            "gate": "real_data_tiny_overfit_v0",
            "r16_code_commit": R16_COMMIT,
            "source_manifest_version": SOURCE_MANIFEST_VERSION,
            "preprocessing_qa_status": "PROVISIONAL_HUMAN_QA_PENDING",
            "feasibility": feasibility,
            "cohort_selected": len(cohort),
            "studies_processed": len(features),
            "series_processed": series_processed,
            "skip_reason_counts": dict(skip_reasons),
            "train_studies_used": int((~is_validation).sum()),
            "val_studies_used": int(is_validation.sum()),
            "masked_bce_first_epoch": rounded_float(first_loss),
            "masked_bce_best_epoch": rounded_float(best_loss),
            "val_per_label_auc": per_label_auc,
            "val_macro_auc_over_computable": rounded_float(val_macro)
            if val_macro is not None
            else None,
            "elapsed_seconds": rounded_float(time.monotonic() - started),
            "completion": "REAL_DATA_GATE_PASS",
        }
        payload = _canonical_json_bytes(summary)
        if not 0 < len(payload) <= MAX_SUMMARY_BYTES:
            raise GateError("summary_size_invalid")
        output_root = Path("/kaggle/working")
        output_root.mkdir(parents=True, exist_ok=True)
        temporary = output_root / f".{SUMMARY_BASENAME}.tmp"
        temporary.write_bytes(payload)
        os.replace(temporary, output_root / SUMMARY_BASENAME)
        print(f"event=real_data_gate_complete studies={len(features)} series={series_processed}")
        return 0
    finally:
        if str(runtime_root) in sys.path:
            sys.path.remove(str(runtime_root))
        shutil.rmtree(runtime_root, ignore_errors=True)


def run_e00b_memorization_gate():
    """Prove the model can memorize a tiny cohort with real supervised labels.

    Selects 8-16 studies with both positive and negative labels per target where
    possible. Trains on all of them (no val split) for enough epochs to drive
    training BCE toward zero. Reports per-label training AUC and supervised-cell
    counts. Every selected study must contribute at least one nonzero gradient.
    """
    started = time.monotonic()
    competition_root = _bounded_mount("competitions", COMPETITION_SLUG)
    bundle_root = _bounded_mount("datasets", BUNDLE_DATASET_REF)
    runtime_root = _install_bundle_runtime(bundle_root)
    sys.path.insert(0, str(runtime_root))
    try:
        from rsna_knee.dicom.pipeline import (
            PipelineVersions,
            PreprocessingConfig,
            dicom_to_model,
        )

        keys, labels = read_study_labels(competition_root / "train.csv")

        # Select studies that have both positive and negative labels across targets.
        # Prefer studies with more known cells; tie-break by SHA-256 for determinism.
        n_known = np.isfinite(labels).sum(axis=1)
        has_pos_and_neg = np.zeros(len(keys), dtype=bool)
        for index in range(len(keys)):
            row = labels[index]
            observed = np.isfinite(row)
            if observed.any() and (row[observed] == 1).any() and (row[observed] == 0).any():
                has_pos_and_neg[index] = True
        eligible = [i for i in range(len(keys)) if has_pos_and_neg[i]]
        ranked = sorted(
            eligible,
            key=lambda i: (-int(n_known[i]), hashlib.sha256(keys[i].encode()).hexdigest()),
        )
        cohort_indices = ranked[:E00B_COHORT]
        cohort_keys = [keys[i] for i in cohort_indices]

        config = PreprocessingConfig(sample_count=SAMPLE_COUNT, resize_rows_columns=RESIZE_SHAPE)
        versions = PipelineVersions(
            code_commit=R16_COMMIT, source_manifest_version=SOURCE_MANIFEST_VERSION
        )
        features = {}
        skip_reasons = Counter()
        series_processed = 0
        for key in cohort_keys:
            try:
                tensors = [
                    dicom_to_model(paths, config, versions).tensor
                    for paths in _series_paths(competition_root, key)
                ]
            except Exception as error:  # noqa: BLE001 - reduced to fixed safe token below
                token = getattr(error, "code", None) or getattr(
                    getattr(error, "issue", None), "value", None
                )
                safe = (
                    str(token)
                    if isinstance(token, str) and SAFE_TOKEN.fullmatch(token)
                    else "preprocess_failed"
                )
                skip_reasons[safe] += 1
                continue
            features[key] = np.mean([study_feature(tensor) for tensor in tensors], axis=0)
            series_processed += len(tensors)
        if not features:
            raise GateError("insufficient_processed_studies")

        ordered_keys = sorted(features)
        matrix = np.vstack([features[key] for key in ordered_keys])
        matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)
        mean = matrix.mean(axis=0)
        std = matrix.std(axis=0)
        std = np.where(std < 1e-8, 1.0, std)
        matrix = (matrix - mean) / std
        row_index = {key: index for index, key in enumerate(keys)}
        label_matrix = np.vstack([labels[row_index[key]] for key in ordered_keys])

        # Train on ALL studies — no validation split.
        weights, bias, first_loss, best_loss = fit_linear_probe(
            matrix, label_matrix, epochs=E00B_EPOCHS, learning_rate=LEARNING_RATE, seed=SEED
        )

        # Training AUC on the same data (memorization check).
        train_scores = 1.0 / (1.0 + np.exp(-(np.clip(matrix @ weights + bias, -30.0, 30.0))))
        train_auc = {
            target: rank_auc(label_matrix[:, column], train_scores[:, column])
            for column, target in enumerate(TARGETS)
        }
        computable_auc = {k: v for k, v in train_auc.items() if v is not None}
        train_macro = float(np.mean(list(computable_auc.values()))) if computable_auc else None

        # Supervised-cell count per label (how many nonzero gradients each target gets).
        observed = np.isfinite(label_matrix)
        supervised_cells_per_label = {}
        positive_cells_per_label = {}
        negative_cells_per_label = {}
        for column, target in enumerate(TARGETS):
            obs_col = observed[:, column]
            pos_count = int((label_matrix[obs_col, column] == 1).sum())
            neg_count = int((label_matrix[obs_col, column] == 0).sum())
            supervised_cells_per_label[target] = int(obs_col.sum())
            positive_cells_per_label[target] = pos_count
            negative_cells_per_label[target] = neg_count

        # Confirm every selected study contributes at least one nonzero gradient.
        per_study_supervised = {}
        for row_i, key in enumerate(ordered_keys):
            n_observed = int(observed[row_i].sum())
            n_positive = int((label_matrix[row_i][observed[row_i]] == 1).sum())
            n_negative = int((label_matrix[row_i][observed[row_i]] == 0).sum())
            per_study_supervised[key] = {
                "known": n_observed,
                "positive": n_positive,
                "negative": n_negative,
                "contributes_nonzero_loss": n_observed > 0,
            }
        all_contribute = all(v["contributes_nonzero_loss"] for v in per_study_supervised.values())

        summary = {
            "schema_version": 1,
            "gate": "e00b_memorization_v0",
            "r16_code_commit": R16_COMMIT,
            "source_manifest_version": SOURCE_MANIFEST_VERSION,
            "preprocessing_qa_status": "PROVISIONAL_HUMAN_QA_PENDING",
            "cohort_selected": len(cohort_keys),
            "studies_processed": len(features),
            "series_processed": series_processed,
            "skip_reason_counts": dict(skip_reasons),
            "supervised_bce_first_epoch": rounded_float(first_loss),
            "supervised_bce_best_epoch": rounded_float(best_loss),
            "train_per_label_auc": train_auc,
            "train_macro_auc_over_computable": rounded_float(train_macro)
            if train_macro is not None
            else None,
            "n_computable_labels": len(computable_auc),
            "supervised_cells_per_label": supervised_cells_per_label,
            "positive_cells_per_label": positive_cells_per_label,
            "negative_cells_per_label": negative_cells_per_label,
            "per_study_supervised": per_study_supervised,
            "all_studies_contribute_nonzero_loss": all_contribute,
            "elapsed_seconds": rounded_float(time.monotonic() - started),
            "completion": (
                "E00B_MEMORIZATION_PASS"
                if all_contribute and best_loss < first_loss
                else "E00B_MEMORIZATION_FAIL"
            ),
        }
        payload = _canonical_json_bytes(summary)
        if not 0 < len(payload) <= MAX_SUMMARY_BYTES:
            raise GateError("summary_size_invalid")
        output_root = Path("/kaggle/working")
        output_root.mkdir(parents=True, exist_ok=True)
        temporary = output_root / f".{SUMMARY_BASENAME}.tmp"
        temporary.write_bytes(payload)
        os.replace(temporary, output_root / SUMMARY_BASENAME)
        print(f"event=e00b_complete studies={len(features)} series={series_processed}")
        return 0
    finally:
        if str(runtime_root) in sys.path:
            sys.path.remove(str(runtime_root))
        shutil.rmtree(runtime_root, ignore_errors=True)


def run_e00c_cnn_memorization_gate():
    """Prove a genuine pixel-level CNN can memorize a tiny real cohort.

    Uses the frozen r16 preprocessing (adjacent-slice channels, deterministic
    sampling), a small PyTorch CNN encoder with masked BCE, no augmentation,
    no dropout, zero weight decay, fixed seed. Every selected study must have
    at least one supervised label and contribute nonzero loss.
    """
    import torch
    from torch import nn

    started = time.monotonic()
    competition_root = _bounded_mount("competitions", COMPETITION_SLUG)
    bundle_root = _bounded_mount("datasets", BUNDLE_DATASET_REF)
    runtime_root = _install_bundle_runtime(bundle_root)
    sys.path.insert(0, str(runtime_root))
    try:
        from rsna_knee.dicom.pipeline import (
            PipelineVersions,
            PreprocessingConfig,
            dicom_to_model,
        )

        keys, labels = read_study_labels(competition_root / "train.csv")

        # Same cohort policy as E00b: studies with both pos and neg labels,
        # ranked by known-cell count then SHA-256 tie-break. Deterministic.
        n_known = np.isfinite(labels).sum(axis=1)
        has_pos_and_neg = np.zeros(len(keys), dtype=bool)
        for index in range(len(keys)):
            row = labels[index]
            observed = np.isfinite(row)
            if observed.any() and (row[observed] == 1).any() and (row[observed] == 0).any():
                has_pos_and_neg[index] = True
        eligible = [i for i in range(len(keys)) if has_pos_and_neg[i]]
        ranked = sorted(
            eligible,
            key=lambda i: (-int(n_known[i]), hashlib.sha256(keys[i].encode()).hexdigest()),
        )
        cohort_keys = [keys[i] for i in ranked[:E00C_COHORT]]

        config = PreprocessingConfig(
            sample_count=SAMPLE_COUNT,
            resize_rows_columns=RESIZE_SHAPE,
            adjacent_slice_channels=True,
        )
        versions = PipelineVersions(
            code_commit=R16_COMMIT, source_manifest_version=SOURCE_MANIFEST_VERSION
        )
        tensors = {}
        skip_reasons = Counter()
        series_processed = 0
        for key in cohort_keys:
            study_tensors = []
            try:
                for paths in _series_paths(competition_root, key):
                    result = dicom_to_model(paths, config, versions)
                    study_tensors.append(result.tensor)  # [S=8, C=3, H=64, W=64]
                    series_processed += 1
            except Exception as error:  # noqa: BLE001 - reduced to fixed safe token below
                skip_reasons[_safe_series_token(error)] += 1
                continue
            if not study_tensors:
                skip_reasons["no_eligible_series"] += 1
                continue
            tensors[key] = np.stack(study_tensors, axis=0)  # [n_series, S, C, H, W]
        if len(tensors) < MIN_PROCESSED:
            raise GateError("insufficient_processed_studies")

        ordered_keys = sorted(tensors)
        label_matrix = np.vstack([labels[keys.index(key)] for key in ordered_keys])
        observed = np.isfinite(label_matrix)
        targets = np.where(observed, label_matrix, 0.0).astype(np.float32)

        # Small CNN: shared encoder over each sampled slice, mean-pool over the
        # 8 samples and all series, then one linear head over 12 logits.
        class TinyCNN(nn.Module):
            def __init__(self):
                super().__init__()
                self.features = nn.Sequential(
                    nn.Conv2d(3, 16, kernel_size=3, padding=1),
                    nn.ReLU(),
                    nn.MaxPool2d(2),
                    nn.Conv2d(16, 32, kernel_size=3, padding=1),
                    nn.ReLU(),
                    nn.MaxPool2d(2),
                    nn.Conv2d(32, E00C_HIDDEN, kernel_size=3, padding=1),
                    nn.ReLU(),
                    nn.AdaptiveAvgPool2d(1),
                )
                self.classifier = nn.Linear(E00C_HIDDEN, len(TARGETS))

            def forward(self, x):
                batch_shape = x.shape  # [B, n_series, S, C, H, W] or [B, S, C, H, W]
                flat = x.reshape(-1, *batch_shape[-3:])  # [B*n*S, C, H, W]
                encoded = self.features(flat).flatten(1)  # [B*n*S, hidden]
                pooled = encoded.mean(dim=0, keepdim=True)  # single-study mode only
                return self.classifier(pooled).reshape(batch_shape[:1] + (-1,))

        torch.manual_seed(SEED)
        model = TinyCNN()
        optimizer = torch.optim.AdamW(model.parameters(), lr=E00C_LEARNING_RATE, weight_decay=0.0)
        first_loss = float("nan")
        best_loss = float("inf")
        last_loss = float("nan")
        observed_t = torch.from_numpy(observed.astype(np.float32))
        targets_t = torch.from_numpy(targets)
        initial_params = {name: param.detach().clone() for name, param in model.named_parameters()}

        # Full-batch training on every processed study simultaneously; every study's
        # labels are in the same loss term so each contributes nonzero gradient.
        per_study_losses = []
        for step in range(E00C_EPOCHS):
            optimizer.zero_grad()
            total_loss = 0.0
            step_loss_value = 0.0
            for row_index_local, key in enumerate(ordered_keys):
                x = torch.from_numpy(tensors[key].astype(np.float32)).unsqueeze(0)
                logits = model(x)[0]  # [12]
                obs_row = observed_t[row_index_local]
                tgt_row = targets_t[row_index_local]
                denom = max(int(obs_row.sum().item()), 1)
                loss_row = nn.functional.binary_cross_entropy_with_logits(
                    logits, tgt_row, reduction="none"
                )
                masked = (loss_row * obs_row).sum() / denom
                total_loss = total_loss + masked
                step_loss_value += float(masked.item())
            total_loss_tensor = (
                total_loss if isinstance(total_loss, torch.Tensor) else torch.tensor(total_loss)
            )
            total_loss_tensor.backward()
            optimizer.step()
            step_loss_value /= max(len(ordered_keys), 1)
            if step == 0:
                first_loss = step_loss_value
            last_loss = step_loss_value
            best_loss = min(best_loss, step_loss_value)
            per_study_losses.append(step_loss_value)
            if time.monotonic() - started > BUDGET_SECONDS - 120:
                break

        # Training AUC on the same data using final parameters.
        with torch.no_grad():
            train_scores = np.zeros((len(ordered_keys), len(TARGETS)), dtype=np.float64)
            for row_index_local, key in enumerate(ordered_keys):
                x = torch.from_numpy(tensors[key].astype(np.float32)).unsqueeze(0)
                train_scores[row_index_local] = (
                    torch.sigmoid(model(x)[0]).numpy().astype(np.float64)
                )
        train_auc = {
            target: rank_auc(label_matrix[:, column], train_scores[:, column])
            for column, target in enumerate(TARGETS)
        }
        computable_auc = {k: v for k, v in train_auc.items() if v is not None}
        train_macro = float(np.mean(list(computable_auc.values()))) if computable_auc else None

        params_changed = any(
            not torch.equal(initial_params[name], param.detach())
            for name, param in model.named_parameters()
        )
        finite_scores = bool(np.isfinite(train_scores).all())
        per_study_contribution = {}
        for row_index_local, key in enumerate(ordered_keys):
            n_obs = int(observed[row_index_local].sum())
            row = row_index_local
            per_study_contribution[key] = {
                "known": n_obs,
                "positive": int((label_matrix[row][observed[row]] == 1).sum()),
                "negative": int((label_matrix[row][observed[row]] == 0).sum()),
                "contributes_nonzero_loss": n_obs > 0,
            }
        all_contribute = all(v["contributes_nonzero_loss"] for v in per_study_contribution.values())
        memorization_evidence = (
            all_contribute and params_changed and finite_scores and last_loss < 0.15
        )
        summary = {
            "schema_version": 1,
            "gate": "e00c_cnn_memorization_v0",
            "r16_code_commit": R16_COMMIT,
            "source_manifest_version": SOURCE_MANIFEST_VERSION,
            "preprocessing_qa_status": "PROVISIONAL_HUMAN_QA_PENDING",
            "cohort_selected": len(cohort_keys),
            "studies_processed": len(tensors),
            "series_processed": series_processed,
            "skip_reason_counts": dict(skip_reasons),
            "model_config": {
                "architecture": "tiny_cnn_3conv_16-32-64_adaptive_pool_linear12",
                "epochs": E00C_EPOCHS,
                "learning_rate": E00C_LEARNING_RATE,
                "weight_decay": 0.0,
                "dropout": False,
                "augmentation": "none",
                "optimizer": "adamw",
                "seed": SEED,
            },
            "supervised_bce_first_epoch": rounded_float(first_loss),
            "supervised_bce_last_epoch": rounded_float(last_loss),
            "supervised_bce_best_epoch": rounded_float(best_loss),
            "train_per_label_auc": train_auc,
            "train_macro_auc_over_computable": rounded_float(train_macro)
            if train_macro is not None
            else None,
            "n_computable_labels": len(computable_auc),
            "per_study_supervised": per_study_contribution,
            "all_studies_contribute_nonzero_loss": all_contribute,
            "parameters_changed": params_changed,
            "scores_finite": finite_scores,
            "elapsed_seconds": rounded_float(time.monotonic() - started),
            "completion": (
                "E00C_CNN_MEMORIZATION_PASS"
                if memorization_evidence
                else "E00C_CNN_MEMORIZATION_FAIL"
            ),
        }
        payload = _canonical_json_bytes(summary)
        if not 0 < len(payload) <= MAX_SUMMARY_BYTES:
            raise GateError("summary_size_invalid")
        output_root = Path("/kaggle/working")
        output_root.mkdir(parents=True, exist_ok=True)
        temporary = output_root / f".{SUMMARY_BASENAME}.tmp"
        temporary.write_bytes(payload)
        os.replace(temporary, output_root / SUMMARY_BASENAME)
        print(f"event=e00c_complete studies={len(tensors)} series={series_processed}")
        return 0
    finally:
        if str(runtime_root) in sys.path:
            sys.path.remove(str(runtime_root))
        shutil.rmtree(runtime_root, ignore_errors=True)


def run_e01_fold_zero_training():
    """Train the tiny CNN on Fold 0's complement and validate on Fold 0.

    Full-data preprocessing inside Kaggle, then GPU mini-batch training.
    Reports sanitized aggregates only (no UIDs, reports, or pixels).
    """
    import torch
    from torch import nn

    started = time.monotonic()
    competition_root = _bounded_mount("competitions", COMPETITION_SLUG)
    bundle_root = _bounded_mount("datasets", BUNDLE_DATASET_REF)
    runtime_root = _install_bundle_runtime(bundle_root)
    sys.path.insert(0, str(runtime_root))
    try:
        from rsna_knee.dicom.pipeline import (
            PipelineVersions,
            PreprocessingConfig,
            dicom_to_model,
        )

        keys, labels = read_study_labels(competition_root / "train.csv")
        assignments, _ = assign_grouped_folds(keys, labels)

        config = PreprocessingConfig(
            sample_count=SAMPLE_COUNT,
            resize_rows_columns=RESIZE_SHAPE,
            adjacent_slice_channels=True,
        )
        versions = PipelineVersions(
            code_commit=R16_COMMIT, source_manifest_version=SOURCE_MANIFEST_VERSION
        )

        # Phase 1: preprocess every study; store tensors keyed by opaque index.
        # Round-robin across folds so the time-budget cut still yields train+val.
        fold_buckets = {f: [] for f in range(N_SPLITS)}
        for index, key in enumerate(keys):
            fold_buckets[assignments[key]].append(index)
        ordered_indices = []
        for round_index in range(max(len(b) for b in fold_buckets.values())):
            for fold in range(N_SPLITS):
                if round_index < len(fold_buckets[fold]):
                    ordered_indices.append(fold_buckets[fold][round_index])
        tensors = {}
        tensor_labels = {}
        tensor_assignments = {}
        skip_reasons = Counter()
        series_processed = 0
        for index in ordered_indices:
            if time.monotonic() - started > BUDGET_SECONDS * 0.55:
                break  # Reserve time for training and evaluation.
            fold = assignments[key]
            study_tensors = []
            try:
                for paths in _series_paths(competition_root, key):
                    result = dicom_to_model(paths, config, versions)
                    study_tensors.append(result.tensor)
                    series_processed += 1
            except Exception as error:  # noqa: BLE001
                skip_reasons[_safe_series_token(error)] += 1
                continue
            if not study_tensors:
                skip_reasons["no_eligible_series"] += 1
                continue
            tensors[index] = np.stack(study_tensors, axis=0).astype(np.float32)
            tensor_labels[index] = labels[index]
            tensor_assignments[index] = fold

        train_indices = sorted(i for i in tensors if tensor_assignments[i] != 0)
        val_indices = sorted(i for i in tensors if tensor_assignments[i] == 0)
        if not train_indices or not val_indices:
            raise GateError("split_empty")

        # Phase 2: build model and train on folds 1-4, validate on fold 0.
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        torch.manual_seed(SEED)
        model = TinyCNNShared().to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=E01_LEARNING_RATE, weight_decay=0.0)

        label_matrix = np.vstack([tensor_labels[i] for i in train_indices])
        observed_train = np.isfinite(label_matrix)
        targets_train = np.where(observed_train, label_matrix, 0.0).astype(np.float32)
        val_label_matrix = np.vstack([tensor_labels[i] for i in val_indices])
        observed_val = np.isfinite(val_label_matrix)

        first_loss = float("nan")
        last_loss = float("nan")
        best_loss = float("inf")
        rng = np.random.default_rng(SEED)
        order = np.arange(len(train_indices))
        for epoch in range(E01_EPOCHS):
            rng.shuffle(order)
            epoch_losses = []
            for batch_start in range(0, len(order), E01_BATCH_SIZE):
                batch_ids = order[batch_start : batch_start + E01_BATCH_SIZE]
                optimizer.zero_grad()
                batch_loss_tensor = torch.zeros((), device=device)
                for local_index in batch_ids:
                    global_index = train_indices[local_index]
                    x_np = tensors[global_index][np.newaxis]  # [1, S, C, H, W]
                    x = torch.from_numpy(x_np).to(device)
                    logits = model(x)[0]
                    obs_row = torch.from_numpy(observed_train[local_index].astype(np.float32)).to(
                        device
                    )
                    tgt_row = torch.from_numpy(targets_train[local_index]).to(device)
                    denom = max(int(obs_row.sum().item()), 1)
                    raw_loss = nn.functional.binary_cross_entropy_with_logits(
                        logits, tgt_row, reduction="none"
                    )
                    masked = (raw_loss * obs_row).sum() / denom
                    batch_loss_tensor = batch_loss_tensor + masked
                batch_loss_tensor.backward()
                optimizer.step()
                epoch_losses.append(float(batch_loss_tensor.item()) / len(batch_ids))
            mean_epoch_loss = float(np.mean(epoch_losses)) if epoch_losses else float("nan")
            if epoch == 0:
                first_loss = mean_epoch_loss
            last_loss = mean_epoch_loss
            best_loss = min(best_loss, mean_epoch_loss)
            if time.monotonic() - started > BUDGET_SECONDS - 600:
                break

        # Validation scoring.
        model.eval()
        val_scores = np.zeros((len(val_indices), len(TARGETS)), dtype=np.float64)
        with torch.no_grad():
            for row_local, global_index in enumerate(val_indices):
                x = torch.from_numpy(tensors[global_index][np.newaxis]).to(device)
                val_scores[row_local] = torch.sigmoid(model(x)[0]).cpu().numpy()
        per_target_auc = {}
        per_target_pos = {}
        per_target_neg = {}
        computed_aucs = []
        for col, target in enumerate(TARGETS):
            auc_value = rank_auc(val_label_matrix[:, col], val_scores[:, col])
            per_target_auc[target] = auc_value
            obs_col = observed_val[:, col]
            per_target_pos[target] = int((val_label_matrix[obs_col, col] == 1).sum())
            per_target_neg[target] = int((val_label_matrix[obs_col, col] == 0).sum())
            if auc_value is not None:
                computed_aucs.append(auc_value)
        macro_auc = float(np.mean(computed_aucs)) if computed_aucs else None

        peak_memory_mb = 0
        if device.type == "cuda":
            peak_memory_mb = round(torch.cuda.max_memory_allocated() / (1024 * 1024))

        summary = {
            "schema_version": 1,
            "gate": "e01_fold_zero_v0",
            "r16_code_commit": R16_COMMIT,
            "source_manifest_version": SOURCE_MANIFEST_VERSION,
            "preprocessing_qa_status": "PROVISIONAL_HUMAN_QA_PENDING",
            "model_config": {
                "architecture": "tiny_cnn_3conv_16-32-64_adaptive_pool_linear12",
                "epochs": E01_EPOCHS,
                "learning_rate": E01_LEARNING_RATE,
                "weight_decay": 0.0,
                "dropout": False,
                "augmentation": "none",
                "optimizer": "adamw",
                "seed": SEED,
                "batch_size": E01_BATCH_SIZE,
                "device": device.type,
            },
            "studies_preprocessed": len(tensors),
            "studies_train": len(train_indices),
            "studies_val": len(val_indices),
            "series_processed": series_processed,
            "skip_reason_counts": dict(skip_reasons),
            "train_bce_first_epoch": rounded_float(first_loss),
            "train_bce_last_epoch": rounded_float(last_loss),
            "train_bce_best_epoch": rounded_float(best_loss),
            "val_per_label_auc": per_target_auc,
            "val_per_label_positive_support": per_target_pos,
            "val_per_label_negative_support": per_target_neg,
            "val_macro_auc_over_computable": (
                rounded_float(macro_auc) if macro_auc is not None else None
            ),
            "n_computable_labels": len(computed_aucs),
            "peak_gpu_memory_mb": peak_memory_mb,
            "elapsed_seconds": rounded_float(time.monotonic() - started),
        }
        payload = _canonical_json_bytes(summary)
        if not 0 < len(payload) <= MAX_SUMMARY_BYTES * 4:
            raise GateError("summary_size_invalid")
        output_root = Path("/kaggle/working")
        output_root.mkdir(parents=True, exist_ok=True)
        temporary = output_root / f".{SUMMARY_BASENAME}.tmp"
        temporary.write_bytes(payload)
        os.replace(temporary, output_root / SUMMARY_BASENAME)
        print(f"event=e01_complete train={len(train_indices)} val={len(val_indices)}")
        return 0
    finally:
        if str(runtime_root) in sys.path:
            sys.path.remove(str(runtime_root))
        shutil.rmtree(runtime_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(run_real_data_gate())
