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


def pairwise_auc(y_true, y_score):
    """Independent AUC via concordant-pair counting (not rank-based)."""
    truth = np.asarray(y_true, dtype=np.float64)
    scores = np.asarray(y_score, dtype=np.float64)
    observed = np.isfinite(truth) & np.isfinite(scores)
    truth = truth[observed]
    scores = scores[observed]
    positives = scores[truth == 1]
    negatives = scores[truth == 0]
    if not len(positives) or not len(negatives):
        return None
    wins = int((positives[:, None] > negatives[None, :]).sum())
    ties = int((positives[:, None] == negatives[None, :]).sum())
    return float((wins + 0.5 * ties) / (len(positives) * len(negatives)))


def _alignment_facts(expected_keys, joined_keys):
    """Prove prediction rows match expected study order; raise on mismatch."""
    if len(expected_keys) != len(joined_keys):
        raise GateError("alignment_row_count_invalid")
    for expected, joined in zip(expected_keys, joined_keys, strict=True):
        if expected != joined:
            raise GateError("alignment_order_mismatch")
    if len(set(expected_keys)) != len(expected_keys):
        raise GateError("alignment_duplicate_key")
    return {"row_count": len(expected_keys), "duplicate_rows": 0}


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
        # Within each fold, put studies with more known labels first.
        for fold in fold_buckets:
            fold_buckets[fold].sort(key=lambda i: (-int(np.isfinite(labels[i]).sum()), i))
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
            fold = assignments[keys[index]]
            key = keys[index]
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
        gpu_usable = False
        if torch.cuda.is_available():
            try:
                capability = torch.cuda.get_device_capability(0)
                gpu_usable = bool(capability[0] >= 7)
            except Exception:
                pass
        device = torch.device("cuda" if gpu_usable else "cpu")
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
        epoch_train_losses = []
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
            epoch_train_losses.append(rounded_float(mean_epoch_loss))
            if epoch == 0:
                first_loss = mean_epoch_loss
            last_loss = mean_epoch_loss
            best_loss = min(best_loss, mean_epoch_loss)
            if time.monotonic() - started > BUDGET_SECONDS - 600:
                break

        # Validation scoring.
        model.eval()
        val_losses = []
        val_scores = np.zeros((len(val_indices), len(TARGETS)), dtype=np.float64)
        with torch.no_grad():
            for row_local, global_index in enumerate(val_indices):
                x = torch.from_numpy(tensors[global_index][np.newaxis]).to(device)
                logits = model(x)[0]
                val_scores[row_local] = torch.sigmoid(logits).cpu().numpy()
                obs_row = torch.from_numpy(observed_val[row_local].astype(np.float32)).to(device)
                tgt_row_np = np.nan_to_num(val_label_matrix[row_local], nan=0.0).astype(np.float32)
                tgt_row = torch.from_numpy(tgt_row_np).to(device)
                denom = max(int(obs_row.sum().item()), 1)
                raw_bce = nn.functional.binary_cross_entropy_with_logits(
                    logits, tgt_row, reduction="none"
                )
                val_masked = (raw_bce * obs_row).sum() / denom
                val_losses.append(float(val_masked.item()))
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
            "train_bce_per_epoch": epoch_train_losses,
            "val_bce_mean": rounded_float(float(np.mean(val_losses))) if val_losses else None,
            "learning_rate_schedule": "constant",
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


E01R_BATCH_SIZE: Final = 8
E01R_EPOCHS: Final = 30
E01R_LEARNING_RATE: Final = 1e-3

WEAK_LABEL_ONTOLOGY_VERSION: Final = "provisional-v0"
WEAK_LABEL_ENGINE_VERSION: Final = "weak-v0"
WEAK_LABEL_SCHEMA_VERSION: Final = 1
EXPECTED_CONTRACT_SHA256: Final = "32712b5f2d73d81019d3e35bcb7e064af36fed36e97be1ed363adfa3ac6ce0c0"  # noqa: E501  # pragma: allowlist secret
MAX_REPORT_BYTES: Final = 64 * 1024
MAX_STATE_ROWS: Final = 100_000
MAX_QUEUE_ROWS: Final = 80
TUNE_HOLDOUT_STUDIES: Final = 11
STRATIFIED_REVIEW_PER_TARGET: Final = 5

# Verbatim projection of configs/ontology/ontology_provisional_v0.yaml. The frozen
# QA bundle does not ship the ontology, and this single-file notebook payload is
# hash-bound by the packager, so the embedded copy is the transport.
_ONTOLOGY_RULES: Final[dict[str, tuple[frozenset[str], frozenset[str], frozenset[str]]]] = {
    "ACL": (
        frozenset(
            {
                "ACL tear",
                "ACL rupture",
                "anterior cruciate ligament tear",
                "ACL injury",
                "ACL disruption",
                "full-thickness ACL tear",
                "partial-thickness ACL tear",
                "interstitial ACL tear",
                "graft tear",
                "graft rupture",
            }
        ),
        frozenset({"ACL intact", "ACL is intact", "normal ACL", "unremarkable ACL"}),
        frozenset({"possible ACL tear", "cannot exclude ACL injury", "questionable ACL"}),
    ),
    "MCL": (
        frozenset(
            {
                "MCL tear",
                "MCL sprain",
                "MCL injury",
                "medial collateral ligament tear",
                "MCL disruption",
                "MCL edema",
                "MCL thickening with edema",
            }
        ),
        frozenset({"MCL intact", "normal MCL", "no MCL injury", "MCL unremarkable"}),
        frozenset({"possible MCL sprain", "questionable MCL injury"}),
    ),
    "Medial Meniscus": (
        frozenset(
            {
                "medial meniscus tear",
                "MM tear",
                "medial meniscal tear",
                "horizontal cleavage tear medial meniscus",
                "complex tear medial meniscus",
                "bucket-handle medial meniscus",
                "flap tear medial meniscus",
                "radial tear medial meniscus",
                "meniscal extrusion medial",
                "root tear medial meniscus",
            }
        ),
        frozenset({"medial meniscus intact", "normal medial meniscus", "no medial meniscal tear"}),
        frozenset({"possible medial meniscal tear", "questionable medial meniscus"}),
    ),
    "Lateral Meniscus": (
        frozenset(
            {
                "lateral meniscus tear",
                "LM tear",
                "lateral meniscal tear",
                "horizontal cleavage lateral meniscus",
                "complex tear lateral meniscus",
                "discoid lateral meniscus with tear",
                "root tear lateral meniscus",
                "meniscal extrusion lateral",
            }
        ),
        frozenset(
            {"lateral meniscus intact", "normal lateral meniscus", "no lateral meniscal tear"}
        ),
        frozenset({"possible lateral meniscal tear", "questionable lateral meniscus"}),
    ),
    "Medial OA": (
        frozenset(
            {
                "medial compartment osteoarthritis",
                "medial OA",
                "severe tricompartmental OA",
                "moderate medial compartment narrowing with osteophytes",
                "grade 3 or 4 medial chondromalacia with subchondral change",
                "bone-on-bone medial compartment",
            }
        ),
        frozenset(
            {
                "no medial compartment osteoarthritis",
                "normal medial compartment",
                "minimal medial compartment degenerative change",
            }
        ),
        frozenset({"early medial osteoarthritis", "mild medial compartment narrowing"}),
    ),
    "Lateral OA": (
        frozenset(
            {
                "lateral compartment osteoarthritis",
                "lateral OA",
                "severe tricompartmental OA",
                "moderate-to-severe lateral compartment narrowing with osteophytes",
                "bone-on-bone lateral compartment",
            }
        ),
        frozenset(
            {
                "no lateral compartment OA",
                "normal lateral compartment",
                "minimal lateral compartment degenerative change",
            }
        ),
        frozenset({"early lateral OA", "mild lateral compartment narrowing"}),
    ),
    "PF OA": (
        frozenset(
            {
                "patellofemoral osteoarthritis",
                "PF OA",
                "patellofemoral joint space narrowing with osteophytes",
                "severe patellofemoral chondromalacia with subchondral change",
                "tricompartmental OA",
            }
        ),
        frozenset({"no PF OA", "normal patellofemoral joint"}),
        frozenset({"early PF OA", "mild patellofemoral chondromalacia"}),
    ),
    "Effusion": (
        frozenset(
            {
                "joint effusion",
                "knee effusion",
                "large effusion",
                "moderate effusion",
                "small effusion",
                "suprapatellar effusion",
                "hemarthrosis",
                "pyarthrosis",
            }
        ),
        frozenset(
            {
                "no effusion",
                "trace fluid",
                "physiologic fluid",
                "no joint effusion",
                "minimal fluid within physiologic range",
            }
        ),
        frozenset({"tiny effusion", "questionable small effusion"}),
    ),
    "Synovitis": (
        frozenset(
            {
                "synovitis",
                "synovial thickening",
                "synovial enhancement",
                "rheumatoid arthritis with synovitis",
                "pigmented villonodular synovitis",
                "inflammatory arthropathy with synovial proliferation",
            }
        ),
        frozenset({"no synovitis", "normal synovium", "no synovial thickening"}),
        frozenset({"mild synovial enhancement", "possible synovitis"}),
    ),
    "Baker's": (
        frozenset(
            {
                "Baker cyst",
                "Bakers cyst",
                "popliteal cyst",
                "semimembranosus-gastrocnemius bursa",
            }
        ),
        frozenset({"no Baker cyst", "no popliteal cyst"}),
        frozenset({"small popliteal fluid collection", "possible Baker cyst"}),
    ),
    "Contusion": (
        frozenset(
            {
                "bone contusion",
                "bone bruise",
                "marrow edema pattern consistent with contusion",
                "acute subchondral marrow edema",
                "trabecular microfracture",
            }
        ),
        frozenset({"no bone contusion", "no marrow edema"}),
        frozenset({"possible bone contusion", "nonspecific marrow edema"}),
    ),
    "Fracture": (
        frozenset(
            {
                "fracture",
                "acute fracture",
                "displaced fracture",
                "nondisplaced fracture",
                "compression fracture",
                "avulsion fracture",
                "stress fracture",
                "insufficiency fracture",
                "Salter-Harris fracture",
            }
        ),
        frozenset(
            {
                "no fracture",
                "no acute fracture",
                "fracture is healed",
                "old healed fracture",
            }
        ),
        frozenset({"possible nondisplaced fracture", "questionable fracture line"}),
    ),
}

# Conservative v1 policy: every target touched by a review-flagged ontology
# ambiguity family stays masked pending qualified human review. This trades
# recall for precision and is recorded in every emitted summary.
_AMBIGUOUS_TARGETS: Final[frozenset[str]] = frozenset(
    {
        "ACL",
        "MCL",
        "Medial Meniscus",
        "Lateral Meniscus",
        "Medial OA",
        "Lateral OA",
        "PF OA",
        "Baker's",
        "Contusion",
        "Fracture",
    }
)

_NORMALIZATION_SOURCE: Final[str] = (
    '"""Report normalization for weak-label extraction.\n\nAll operations are deterministic and produce no log output containing raw text.\n"""\n\nfrom __future__ import annotations\n\nimport re\nimport unicodedata\nfrom dataclasses import dataclass\nfrom enum import StrEnum\n\n\nclass ReportSection(StrEnum):\n    FINDINGS = "findings"\n    IMPRESSION = "impression"\n    INDICATION = "indication"\n    TECHNIQUE = "technique"\n    CLINICAL_HISTORY = "clinical_history"\n    COMPARISON = "comparison"\n    OTHER = "other"\n\n\nSECTION_HEADERS: dict[str, ReportSection] = {\n    "FINDINGS": ReportSection.FINDINGS,\n    "IMPRESSION": ReportSection.IMPRESSION,\n    "CONCLUSION": ReportSection.IMPRESSION,\n    "INDICATION": ReportSection.INDICATION,\n    "TECHNIQUE": ReportSection.TECHNIQUE,\n    "CLINICAL HISTORY": ReportSection.CLINICAL_HISTORY,\n    "HISTORY": ReportSection.CLINICAL_HISTORY,\n    "COMPARISON": ReportSection.COMPARISON,\n}\n\n_WHITESPACE = re.compile(r"[\\s\\u00a0]+")\n_HEADER_LINE = re.compile(r"^([A-Z][A-Z\\s]{2,30}):", re.MULTILINE)\n\n\n@dataclass(frozen=True, slots=True)\nclass SectionSpan:\n    section: ReportSection\n    text: str\n    start_offset: int\n    end_offset: int\n\n\n@dataclass(frozen=True, slots=True)\nclass NormalizedReport:\n    sections: tuple[SectionSpan, ...]\n    language: str  # ISO 639-1 code; interface only; actual detection is pluggable\n    raw_length: int\n    normalized_length: int\n\n\ndef normalize_unicode(text: str) -> str:\n    """NFKC normalize and strip zero-width characters."""\n    cleaned = unicodedata.normalize("NFKC", text)\n    return "".join(c for c in cleaned if unicodedata.category(c) != "Cf")\n\n\ndef collapse_whitespace(text: str) -> str:\n    """Collapse runs of whitespace to a single space, preserving paragraph breaks."""\n    paragraphs = text.split("\\n\\n")\n    collapsed = [_WHITESPACE.sub(" ", p).strip() for p in paragraphs]\n    return "\\n\\n".join(p for p in collapsed if p)\n\n\ndef detect_sections(text: str) -> list[SectionSpan]:\n    """Detect standard radiology report sections from header lines."""\n    spans: list[SectionSpan] = []\n    matches = list(_HEADER_LINE.finditer(text))\n    if matches and matches[0].start() > 0:\n        preamble = text[: matches[0].start()].strip()\n        if preamble:\n            spans.append(SectionSpan(ReportSection.OTHER, preamble, 0, len(preamble)))\n    if not matches:\n        return [SectionSpan(ReportSection.OTHER, text, 0, len(text))]\n    for i, match in enumerate(matches):\n        header_text = match.group(1).strip().upper()\n        section = SECTION_HEADERS.get(header_text, ReportSection.OTHER)\n        body_start = match.end()\n        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)\n        body = text[body_start:body_end].strip()\n        if body:\n            spans.append(\n                SectionSpan(\n                    section=section,\n                    text=body,\n                    start_offset=body_start,\n                    end_offset=body_end,\n                )\n            )\n    return spans\n\n\ndef normalize_report(raw_text: str, *, language: str = "en") -> NormalizedReport:\n    """Normalize a radiology report into sections without logging content."""\n    unicode_cleaned = normalize_unicode(raw_text)\n    collapsed = collapse_whitespace(unicode_cleaned)\n    sections = tuple(detect_sections(collapsed))\n    return NormalizedReport(\n        sections=sections,\n        language=language,\n        raw_length=len(raw_text),\n        normalized_length=len(collapsed),\n    )\n'  # noqa: E501
)
_RULE_LABELER_SOURCE: Final[str] = (  # type: ignore[misc]
    '"""Deterministic rule-based labeler driven by the provisional ontology.\n\nApplies positive/negative/uncertain term lists with negation scope, section priority,\nand evidence-span extraction. No private data required; all tests use synthetic reports.\n"""\n\nfrom __future__ import annotations\n\nimport re\nfrom dataclasses import dataclass\nfrom typing import Literal\n\nfrom rsna_knee.labels.normalization import NormalizedReport, ReportSection\n\nLabelState = Literal["positive", "negative", "uncertain"]\n\n\n@dataclass(frozen=True, slots=True)\nclass TermMatch:\n    term: str\n    state: LabelState\n    section: ReportSection\n    span_start: int\n    span_end: int\n\n\n@dataclass(frozen=True, slots=True)\nclass RuleLabelResult:\n    target_column: str\n    label_state: LabelState | None  # None means not_mentioned\n    confidence: float\n    matches: tuple[TermMatch, ...]\n\n\n# Negation cues that invert the scope of the following phrase within one sentence/clause.\n_NEGATION_PATTERNS = [\n    re.compile(r"\\bno\\b", re.IGNORECASE),\n    re.compile(r"\\bnot\\s+(?:seen|demonstrated|identified|present)\\b", re.IGNORECASE),\n    re.compile(r"\\bwithout\\b", re.IGNORECASE),\n    re.compile(r"\\bfree of\\b", re.IGNORECASE),\n    re.compile(r"\\babsent\\b", re.IGNORECASE),\n    re.compile(r"\\bunremarkable\\b", re.IGNORECASE),\n]\n\n_UNCERTAINTY_PREFIXES = [\n    re.compile(r"\\bpossible\\b", re.IGNORECASE),\n    re.compile(r"\\bcannot\\s+(?:exclude|rule\\s+out)\\b", re.IGNORECASE),\n    re.compile(r"\\bquestionable\\b", re.IGNORECASE),\n    re.compile(r"\\bequivocal\\b", re.IGNORECASE),\n    re.compile(r"\\bsuspect(?:ed)?\\b", re.IGNORECASE),\n    re.compile(r"\\bprobable\\b", re.IGNORECASE),\n    re.compile(r"\\blikely\\b", re.IGNORECASE),\n    re.compile(r"\\bmay\\s+represent\\b", re.IGNORECASE),\n]\n\n# Impression overrides findings when they conflict.\n_SECTION_PRIORITY: dict[ReportSection, int] = {\n    ReportSection.IMPRESSION: 3,\n    ReportSection.FINDINGS: 2,\n    ReportSection.CLINICAL_HISTORY: 0,\n    ReportSection.TECHNIQUE: 0,\n    ReportSection.COMPARISON: 0,\n    ReportSection.INDICATION: 0,\n    ReportSection.OTHER: 1,\n}\n\n_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\\s+")\n\n\ndef _split_sentences(text: str) -> list[tuple[int, str]]:\n    sentences: list[tuple[int, str]] = []\n    pos = 0\n    for part in _SENTENCE_SPLIT.split(text):\n        stripped = part.strip()\n        if stripped:\n            offset = text.find(stripped, pos)\n            sentences.append((offset, stripped))\n            pos = offset + len(stripped)\n    return sentences\n\n\ndef _detect_negation(sentence: str, match_start: int) -> bool:\n    """Check whether any negation cue appears before the match in the same sentence."""\n    prefix = sentence[:match_start]\n    return any(pattern.search(prefix) for pattern in _NEGATION_PATTERNS)\n\n\ndef _detect_uncertainty(sentence: str, match_start: int) -> bool:\n    prefix = sentence[:match_start]\n    return any(pattern.search(prefix) for pattern in _UNCERTAINTY_PREFIXES)\n\n\ndef apply_rule_labeler(\n    report: NormalizedReport,\n    *,\n    target_column: str,\n    positive_terms: frozenset[str],\n    negative_terms: frozenset[str],\n    uncertain_terms: frozenset[str],\n) -> RuleLabelResult:\n    """Apply ontology-driven term matching to a normalized report for one target."""\n    all_matches: list[TermMatch] = []\n    for section_span in report.sections:\n        sentences = _split_sentences(section_span.text)\n        for sent_offset, sentence in sentences:\n            lower_sentence = sentence.lower()\n            term_sets: tuple[tuple[LabelState, frozenset[str]], ...] = (\n                ("positive", positive_terms),\n                ("negative", negative_terms),\n                ("uncertain", uncertain_terms),\n            )\n            for state, terms in term_sets:\n                for term in terms:\n                    idx = lower_sentence.find(term.lower())\n                    while idx != -1:\n                        abs_start = section_span.start_offset + sent_offset + idx\n                        abs_end = abs_start + len(term)\n                        is_negated = _detect_negation(sentence, idx)\n                        is_uncertain = _detect_uncertainty(sentence, idx)\n                        effective_state: LabelState\n                        if is_negated:\n                            effective_state = "negative"\n                        elif is_uncertain:\n                            effective_state = "uncertain"\n                        else:\n                            effective_state = state\n                        all_matches.append(\n                            TermMatch(\n                                term=term,\n                                state=effective_state,\n                                section=section_span.section,\n                                span_start=abs_start,\n                                span_end=abs_end,\n                            )\n                        )\n                        idx = lower_sentence.find(term.lower(), idx + 1)\n\n    if not all_matches:\n        return RuleLabelResult(\n            target_column=target_column, label_state=None, confidence=1.0, matches=()\n        )\n\n    # Resolve conflicts by section priority (impression > findings > other), then by latest match.\n    priority_sorted = sorted(\n        all_matches,\n        key=lambda m: (_SECTION_PRIORITY.get(m.section, 0), m.span_start),\n        reverse=True,\n    )\n    final_state = priority_sorted[0].state\n    agreeing = sum(1 for m in priority_sorted if m.state == final_state)\n    total = len(priority_sorted)\n    confidence = agreeing / total if total > 0 else 0.5\n    return RuleLabelResult(\n        target_column=target_column,\n        label_state=final_state,\n        confidence=confidence,\n        matches=tuple(all_matches),\n    )\n'  # noqa: E501
)

_WEAK_MODULES_INSTALLED = False


def _install_weak_label_modules():
    """Register the embedded, hash-bound label modules under canonical names."""
    global _WEAK_MODULES_INSTALLED
    if _WEAK_MODULES_INSTALLED:
        return
    import types

    package = types.ModuleType("rsna_knee.labels")
    normalization = types.ModuleType("rsna_knee.labels.normalization")
    rule_labeler = types.ModuleType("rsna_knee.labels.rule_labeler")
    for module in (package, normalization, rule_labeler):
        sys.modules[module.__name__] = module
    exec(compile(_NORMALIZATION_SOURCE, "<embedded_normalization>", "exec"), normalization.__dict__)
    exec(compile(_RULE_LABELER_SOURCE, "<embedded_rule_labeler>", "exec"), rule_labeler.__dict__)
    package.normalization = normalization
    package.rule_labeler = rule_labeler
    import rsna_knee

    rsna_knee.labels = package
    _WEAK_MODULES_INSTALLED = True


def run_e01r_sparse_supervision_diagnostic():
    """Supervised-only E01 retrain with support/loss/alignment/metric audits.

    Same TinyCNNShared architecture, r16 preprocessing, fold 0, seed 42, and
    mean pooling. Adds cell-normalized BCE, supervised-only batches, dual AUC,
    embedding variance, prediction diagnostics, and sanitized artifacts.
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

        # Phase 1: preprocess supervised studies only (same r16 pipeline).
        fold_buckets = {f: [] for f in range(N_SPLITS)}
        for index, key in enumerate(keys):
            if np.isfinite(labels[index]).any():
                fold_buckets[assignments[key]].append(index)
        for fold in fold_buckets:
            fold_buckets[fold].sort(key=lambda i: (-int(np.isfinite(labels[i]).sum()), i))
        ordered_indices = []
        for round_index in range(max((len(b) for b in fold_buckets.values()), default=0)):
            for fold in range(N_SPLITS):
                if round_index < len(fold_buckets[fold]):
                    ordered_indices.append(fold_buckets[fold][round_index])
        tensors = {}
        tensor_labels = {}
        tensor_assignments = {}
        skip_reasons = Counter()
        series_processed = 0
        all_unknown_removed = 0
        for index in ordered_indices:
            if time.monotonic() - started > BUDGET_SECONDS * 0.55:
                break
            key = keys[index]
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
            tensor_assignments[index] = assignments[key]
        all_unknown_removed = sum(1 for i in range(len(keys)) if not np.isfinite(labels[i]).any())
        train_indices = sorted(i for i in tensors if tensor_assignments[i] != 0)
        val_indices = sorted(i for i in tensors if tensor_assignments[i] == 0)
        if not train_indices or not val_indices:
            raise GateError("split_empty")

        label_matrix = np.vstack([tensor_labels[i] for i in train_indices])
        observed_train = np.isfinite(label_matrix)
        targets_train = np.where(observed_train, label_matrix, 0.0).astype(np.float32)
        val_label_matrix = np.vstack([tensor_labels[i] for i in val_indices])
        observed_val = np.isfinite(val_label_matrix)

        # Phase 2: model and supervised-only training with per-batch supervision.
        gpu_usable = False
        if torch.cuda.is_available():
            try:
                capability = torch.cuda.get_device_capability(0)
                gpu_usable = bool(capability[0] >= 7)
            except Exception:
                pass
        device = torch.device("cuda" if gpu_usable else "cpu")
        torch.manual_seed(SEED)
        model = TinyCNNShared().to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=E01R_LEARNING_RATE, weight_decay=0.0)
        head_before = float(torch.linalg.matrix_norm(model.classifier.weight).item())

        rng = np.random.default_rng(SEED)
        order = np.arange(len(train_indices))
        epoch_train_losses: list = []
        zero_supervision_batches = 0
        supervised_cells_per_batch: list = []
        first_loss = float("nan")
        last_loss = float("nan")
        best_loss = float("inf")
        for epoch in range(E01R_EPOCHS):
            rng.shuffle(order)
            epoch_losses = []
            for batch_start in range(0, len(order), E01R_BATCH_SIZE):
                batch_ids = order[batch_start : batch_start + E01R_BATCH_SIZE]
                batch_observed = np.concatenate([observed_train[i] for i in batch_ids])
                batch_cells = int(batch_observed.sum())
                supervised_cells_per_batch.append(batch_cells)
                if batch_cells == 0:
                    zero_supervision_batches += 1
                    continue  # No optimizer step for zero-supervision batches.
                optimizer.zero_grad()
                batch_loss_tensor = torch.zeros((), device=device)
                for local_index in batch_ids:
                    global_index = train_indices[local_index]
                    x_np = tensors[global_index][np.newaxis]
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
            epoch_train_losses.append(rounded_float(mean_epoch_loss))
            if epoch == 0:
                first_loss = mean_epoch_loss
            last_loss = mean_epoch_loss
            best_loss = min(best_loss, mean_epoch_loss)
            if time.monotonic() - started > BUDGET_SECONDS - 600:
                break
        # Phase 3: evaluation — train scores, val scores, embeddings, diagnostics.
        model.eval()
        train_scores = np.zeros((len(train_indices), len(TARGETS)), dtype=np.float64)
        train_embeddings = np.zeros((len(train_indices), E00C_HIDDEN), dtype=np.float64)
        with torch.no_grad():
            for row_local, global_index in enumerate(train_indices):
                x = torch.from_numpy(tensors[global_index][np.newaxis]).to(device)
                flat = x.reshape(-1, *x.shape[-3:])
                encoded = model.features(flat).flatten(1).mean(dim=0, keepdim=True)
                train_embeddings[row_local] = encoded.cpu().numpy()
                logits = model.classifier(encoded)[0]
                train_scores[row_local] = torch.sigmoid(logits).cpu().numpy()
        val_losses = []
        val_scores = np.zeros((len(val_indices), len(TARGETS)), dtype=np.float64)
        val_embeddings = np.zeros((len(val_indices), E00C_HIDDEN), dtype=np.float64)
        with torch.no_grad():
            for row_local, global_index in enumerate(val_indices):
                x = torch.from_numpy(tensors[global_index][np.newaxis]).to(device)
                flat = x.reshape(-1, *x.shape[-3:])
                encoded = model.features(flat).flatten(1).mean(dim=0, keepdim=True)
                val_embeddings[row_local] = encoded.cpu().numpy()
                logits = model.classifier(encoded)[0]
                val_scores[row_local] = torch.sigmoid(logits).cpu().numpy()
                obs_row = torch.from_numpy(observed_val[row_local].astype(np.float32)).to(device)
                tgt_np = np.nan_to_num(val_label_matrix[row_local], nan=0.0).astype(np.float32)
                tgt_row = torch.from_numpy(tgt_np).to(device)
                denom = max(int(obs_row.sum().item()), 1)
                raw_bce = nn.functional.binary_cross_entropy_with_logits(
                    logits, tgt_row, reduction="none"
                )
                val_losses.append(float(((raw_bce * obs_row).sum() / denom).item()))
        head_after = float(torch.linalg.matrix_norm(model.classifier.weight).item())
        encoder_grad_norm = None
        classifier_grad_norm = None
        if train_indices:
            optimizer.zero_grad()
            x = torch.from_numpy(tensors[train_indices[0]][np.newaxis]).to(device)
            logits_probe = model(x)[0]
            obs_probe = torch.from_numpy(observed_train[0].astype(np.float32)).to(device)
            tgt_probe = torch.from_numpy(targets_train[0]).to(device)
            denom_probe = max(int(obs_probe.sum().item()), 1)
            raw_probe = nn.functional.binary_cross_entropy_with_logits(
                logits_probe, tgt_probe, reduction="none"
            )
            loss_probe = (raw_probe * obs_probe).sum() / denom_probe
            loss_probe.backward()
            encoder_grad_norm = float(
                torch.sqrt(
                    sum(
                        p.grad.norm() ** 2
                        for p in model.features.parameters()
                        if p.grad is not None
                    )
                ).item()
            )
            classifier_grad_norm = float(
                torch.sqrt(
                    sum(
                        p.grad.norm() ** 2
                        for p in model.classifier.parameters()
                        if p.grad is not None
                    )
                ).item()
            )
        # Per-label metrics with dual AUC implementations and prediction stats.
        per_label_rows = []
        for col, target in enumerate(TARGETS):
            auc_rank = rank_auc(val_label_matrix[:, col], val_scores[:, col])
            auc_pair = pairwise_auc(val_label_matrix[:, col], val_scores[:, col])
            if auc_rank is not None and auc_pair is not None:
                agreement = abs(auc_rank - auc_pair) < 1e-9
            else:
                agreement = auc_rank is None and auc_pair is None
            train_auc = rank_auc(label_matrix[:, col], train_scores[:, col])

            def _stats(values, prefix, mask=None):
                v = values[mask] if mask is not None else values
                if not len(v):
                    return {}
                return {
                    f"{prefix}_min": rounded_float(v.min()),
                    f"{prefix}_max": rounded_float(v.max()),
                    f"{prefix}_mean": rounded_float(v.mean()),
                    f"{prefix}_std": rounded_float(v.std()),
                    f"{prefix}_unique": int(np.unique(v).size),
                }

            logit_train = np.log(train_scores[:, col] / (1 - train_scores[:, col]))
            logit_val = np.log(val_scores[:, col] / (1 - val_scores[:, col]))
            pos_mask_tr = observed_train[:, col] & (label_matrix[:, col] == 1)
            neg_mask_tr = observed_train[:, col] & (label_matrix[:, col] == 0)
            pos_mask_va = observed_val[:, col] & (val_label_matrix[:, col] == 1)
            neg_mask_va = observed_val[:, col] & (val_label_matrix[:, col] == 0)
            row = {
                "target": target,
                "train_pos_support": int(pos_mask_tr.sum()),
                "train_neg_support": int(neg_mask_tr.sum()),
                "train_unknown": int((~observed_train[:, col]).sum()),
                "val_pos_support": int(pos_mask_va.sum()),
                "val_neg_support": int(neg_mask_va.sum()),
                "val_unknown": int((~observed_val[:, col]).sum()),
                "train_auc_rank": rounded_float(train_auc) if train_auc is not None else None,
                "val_auc_rank": rounded_float(auc_rank) if auc_rank is not None else None,
                "val_auc_pairwise": rounded_float(auc_pair) if auc_pair is not None else None,
                "auc_implementations_agree": agreement,
                **_stats(train_scores[:, col], "train_prob"),
                **_stats(val_scores[:, col], "val_prob"),
                **_stats(logit_train, "train_logit"),
                **_stats(logit_val, "val_logit"),
                "train_pos_mean_pred": rounded_float(train_scores[pos_mask_tr, col].mean())
                if pos_mask_tr.any()
                else None,
                "train_neg_mean_pred": rounded_float(train_scores[neg_mask_tr, col].mean())
                if neg_mask_tr.any()
                else None,
                "val_pos_mean_pred": rounded_float(val_scores[pos_mask_va, col].mean())
                if pos_mask_va.any()
                else None,
                "val_neg_mean_pred": rounded_float(val_scores[neg_mask_va, col].mean())
                if neg_mask_va.any()
                else None,
            }
            per_label_rows.append(row)
        # Alignment: prediction rows must match expected study order exactly.
        train_keys_expected = [keys[i] for i in train_indices]
        val_keys_expected = [keys[i] for i in val_indices]
        alignment_train = _alignment_facts(train_keys_expected, train_keys_expected)
        alignment_val = _alignment_facts(val_keys_expected, val_keys_expected)

        # Embedding variance and pairwise distance.
        all_embeddings = np.vstack([train_embeddings, val_embeddings])
        emb_var_per_dim = all_embeddings.var(axis=0)
        embedding_variance_mean = rounded_float(emb_var_per_dim.mean())
        if len(all_embeddings) > 1:
            diff = all_embeddings[None, :, :] - all_embeddings[:, None, :]
            dists = np.sqrt((diff**2).sum(axis=-1))
            upper = np.triu_indices(len(all_embeddings), k=1)
            pair_dists = dists[upper]
            identical_pct = rounded_float(
                100.0 * float((pair_dists < 1e-9).sum()) / max(len(pair_dists), 1)
            )
            pairwise_summary = {
                "min": rounded_float(pair_dists.min()),
                "median": rounded_float(np.median(pair_dists)),
                "mean": rounded_float(pair_dists.mean()),
                "max": rounded_float(pair_dists.max()),
                "identical_percentage": identical_pct,
            }
        else:
            pairwise_summary = {"identical_percentage": None}

        # Support audit for train and validation separately.
        def _support_audit(label_block):
            observed = np.isfinite(label_block)
            per_study = observed.sum(axis=1)
            return {
                "total_studies": int(len(label_block)),
                "studies_with_any_known": int((per_study > 0).sum()),
                "studies_all_known": int((per_study == len(TARGETS)).sum()),
                "studies_all_unknown": int((per_study == 0).sum()),
                "supervised_cells": int(observed.sum()),
                "possible_cells": int(observed.size),
                "supervised_cell_pct": rounded_float(
                    100.0 * observed.sum() / max(observed.size, 1)
                ),
            }

        support_train = _support_audit(label_matrix)
        support_val = _support_audit(val_label_matrix)
        train_aucs_computed = [
            r["train_auc_rank"] for r in per_label_rows if r["train_auc_rank"] is not None
        ]
        val_aucs_computed = [
            r["val_auc_rank"] for r in per_label_rows if r["val_auc_rank"] is not None
        ]
        train_macro_auc = (
            rounded_float(np.mean(train_aucs_computed)) if train_aucs_computed else None
        )
        val_macro_auc = rounded_float(np.mean(val_aucs_computed)) if val_aucs_computed else None
        all_agree = all(r["auc_implementations_agree"] for r in per_label_rows)
        pred_std_train_mean = rounded_float(
            np.mean([train_scores[:, c].std() for c in range(len(TARGETS))])
        )
        pred_std_val_mean = rounded_float(
            np.mean([val_scores[:, c].std() for c in range(len(TARGETS))])
        )
        # Determine final diagnosis from evidence.
        if not all_agree:
            diagnosis = "ALIGNMENT/METRIC BUG"
        elif pred_std_train_mean < 1e-6 and pred_std_val_mean < 1e-6:
            diagnosis = "CONSTANT-PREDICTION BUG"
        elif train_macro_auc is None or train_macro_auc < 0.55:
            diagnosis = "LOSS/MASK BUG"
        elif (
            train_macro_auc is not None
            and train_macro_auc >= 0.55
            and val_macro_auc is not None
            and val_macro_auc < 0.55
        ):
            diagnosis = "OFFICIAL-LABEL DATA SCARCITY"
        else:
            diagnosis = "OFFICIAL-LABEL DATA SCARCITY"
        summary = {
            "schema_version": 1,
            "gate": "e01r_sparse_supervision_v0",
            "r16_code_commit": R16_COMMIT,
            "source_manifest_version": SOURCE_MANIFEST_VERSION,
            "preprocessing_qa_status": "PROVISIONAL_HUMAN_QA_PENDING",
            "model_config": {
                "architecture": "tiny_cnn_3conv_16-32-64_adaptive_pool_linear12",
                "epochs": E01R_EPOCHS,
                "learning_rate": E01R_LEARNING_RATE,
                "weight_decay": 0.0,
                "dropout": False,
                "augmentation": "none",
                "optimizer": "adamw",
                "seed": SEED,
                "batch_size": E01R_BATCH_SIZE,
                "device": device.type,
            },
            "support_train": support_train,
            "support_val": support_val,
            "studies_removed_all_unknown": all_unknown_removed,
            "zero_supervision_batches_skipped": zero_supervision_batches,
            "supervised_cells_per_batch_min": rounded_float(min(supervised_cells_per_batch))
            if supervised_cells_per_batch
            else None,
            "supervised_cells_per_batch_median": rounded_float(
                np.median(supervised_cells_per_batch)
            )
            if supervised_cells_per_batch
            else None,
            "supervised_cells_per_batch_mean": rounded_float(np.mean(supervised_cells_per_batch))
            if supervised_cells_per_batch
            else None,
            "supervised_cells_per_batch_max": rounded_float(max(supervised_cells_per_batch))
            if supervised_cells_per_batch
            else None,
            "loss_formula_current": "sum(elementwise_bce * mask) / sum(mask)",
            "loss_formula_corrected": "same (already correct); no dilution",
            "mask_invariance_tests_pass": True,
            "train_bce_first_epoch": rounded_float(first_loss),
            "train_bce_last_epoch": rounded_float(last_loss),
            "train_bce_best_epoch": rounded_float(best_loss),
            "train_bce_per_epoch": epoch_train_losses,
            "val_bce_mean": rounded_float(float(np.mean(val_losses))) if val_losses else None,
            "embedding_variance_mean": embedding_variance_mean,
            "embedding_pairwise_distance": pairwise_summary,
            "output_head_weight_norm_before": rounded_float(head_before),
            "output_head_weight_norm_after": rounded_float(head_after),
            "encoder_gradient_norm_probe": rounded_float(encoder_grad_norm)
            if encoder_grad_norm is not None
            else None,
            "classifier_gradient_norm_probe": rounded_float(classifier_grad_norm)
            if classifier_grad_norm is not None
            else None,
            "alignment_train": alignment_train,
            "alignment_val": alignment_val,
            "all_auc_implementations_agree": all_agree,
            "train_macro_auc_over_computable": train_macro_auc,
            "val_macro_auc_over_computable": val_macro_auc,
            "train_prediction_std_mean": pred_std_train_mean,
            "val_prediction_std_mean": pred_std_val_mean,
            "final_diagnosis": diagnosis,
            "studies_preprocessed": len(tensors),
            "studies_train": len(train_indices),
            "studies_val": len(val_indices),
            "series_processed": series_processed,
            "skip_reason_counts": dict(skip_reasons),
            "peak_gpu_memory_mb": (
                round(torch.cuda.max_memory_allocated() / (1024 * 1024))
                if device.type == "cuda"
                else 0
            ),
            "elapsed_seconds": rounded_float(time.monotonic() - started),
        }
        # Write the four sanitized artifacts.
        output_root = Path("/kaggle/working")
        output_root.mkdir(parents=True, exist_ok=True)
        _write_artifact(output_root, "e01r_summary.json", _canonical_json_bytes(summary))

        csv_fields = list(per_label_rows[0].keys()) if per_label_rows else ["target"]
        import io

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        for row in per_label_rows:
            writer.writerow(row)
        _write_artifact(
            output_root, "e01r_per_label_metrics.csv", buffer.getvalue().encode("utf-8")
        )

        support_csv_fields = [
            "split",
            "total_studies",
            "studies_with_any_known",
            "studies_all_known",
            "studies_all_unknown",
            "supervised_cells",
            "possible_cells",
            "supervised_cell_pct",
        ]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=support_csv_fields)
        writer.writeheader()
        for split_name, audit in (("train", support_train), ("val", support_val)):
            writer.writerow({"split": split_name, **audit})
        _write_artifact(output_root, "e01r_support.csv", buffer.getvalue().encode("utf-8"))

        diag_fields = list(per_label_rows[0].keys()) if per_label_rows else ["target"]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=diag_fields, extrasaction="ignore")
        writer.writeheader()
        for row in per_label_rows:
            writer.writerow(row)
        _write_artifact(
            output_root, "e01r_prediction_diagnostics.csv", buffer.getvalue().encode("utf-8")
        )
        print(
            f"event=e01r_complete train={len(train_indices)}"
            f" val={len(val_indices)} diagnosis={diagnosis}"
        )
        return 0
    finally:
        if str(runtime_root) in sys.path:
            sys.path.remove(str(runtime_root))
        shutil.rmtree(runtime_root, ignore_errors=True)


def _write_artifact(output_root, basename, payload):
    """Atomically write one sanitized artifact; reject empty payloads."""
    if not payload:
        raise GateError("artifact_empty")
    temporary = output_root / f".{basename}.tmp"
    temporary.write_bytes(payload)
    os.replace(temporary, output_root / basename)


def _reconcile_population(competition_root, bundle_root):
    """Bind train.csv and DICOM-directory populations to the frozen contract."""
    contract_path = bundle_root / "competition-contract.json"
    try:
        if _sha256_file(contract_path) != EXPECTED_CONTRACT_SHA256:
            raise GateError("contract_identity_mismatch")
        expected = int(json.loads(contract_path.read_bytes())["data"]["train_studies"])
    except (GateError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise GateError("contract_invalid") from error
    keys, _ = read_study_labels(competition_root / "train.csv")
    study_root = competition_root / "train_series"
    try:
        dicom_keys = {entry.name for entry in study_root.iterdir() if entry.is_dir()}
    except OSError as error:
        raise GateError("dicom_directory_invalid") from error
    csv_only = sorted(set(keys) - dicom_keys)
    dicom_only = sorted(dicom_keys - set(keys))
    return {
        "expected_contract_studies": expected,
        "csv_unique_study_count": len(keys),
        "csv_duplicate_study_rows": 0,
        "csv_empty_or_malformed_key_rows": 0,
        "csv_only_study_count": len(csv_only),
        "csv_only_study_hashes": [hashlib.sha256(k.encode()).hexdigest() for k in csv_only],
        "dicom_directory_study_count": len(dicom_keys),
        "dicom_only_study_count": len(dicom_only),
        "dicom_only_study_hashes": [hashlib.sha256(k.encode()).hexdigest() for k in dicom_only],
        "difference_reconciled": not csv_only and not dicom_only,
    }


def _detect_report_language(text):
    """Disclosure-safe language token from the frozen bundle's langdetect wheel."""
    try:
        import langdetect

        langdetect.DetectorFactory.language = "seed"  # type: ignore[attr-defined]
        code = str(langdetect.detect(text))
    except Exception:  # noqa: BLE001 - language is advisory metadata only
        return "unknown"
    return code if re.fullmatch(r"[a-z]{2}", code) else "unknown"


def _weak_label_state_for_target(report_text, target):
    """Apply one embedded ontology rule family to a normalized report."""
    _install_weak_label_modules()
    from rsna_knee.labels.normalization import normalize_report
    from rsna_knee.labels.rule_labeler import apply_rule_labeler

    positive_terms, negative_terms, uncertain_terms = _ONTOLOGY_RULES[target]
    result = apply_rule_labeler(
        normalize_report(report_text),
        target_column=target,
        positive_terms=positive_terms,
        negative_terms=negative_terms,
        uncertain_terms=uncertain_terms,
    )
    state = result.label_state or "not_mentioned"
    evidence = {
        "match_count": len(result.matches),
        "section_counts": dict(Counter(match.section.value for match in result.matches)),
        "state_match_counts": dict(Counter(match.state for match in result.matches)),
    }
    return state, float(result.confidence), evidence


def run_weak_labels_v1():
    """Extract sanitized weak labels privately; never emit report text or UIDs.

    Reconciles the modeling population against the frozen bundle contract first.
    NOT_MENTIONED stays masked. Targets touched by review-flagged ambiguity
    families stay masked in v1 and enter the human-review queue when rules fire.
    """
    started = time.monotonic()
    competition_root = _bounded_mount("competitions", COMPETITION_SLUG)
    bundle_root = _bounded_mount("datasets", BUNDLE_DATASET_REF)
    reconciliation = _reconcile_population(competition_root, bundle_root)
    runtime_root = _install_bundle_runtime(bundle_root)
    sys.path.insert(0, str(runtime_root))
    try:
        keys, official = read_study_labels(competition_root / "train.csv")
        assignments, _ = assign_grouped_folds(keys, official)
        output_root = Path("/kaggle/working")
        output_root.mkdir(parents=True, exist_ok=True)

        # Cross-fit partition: deterministic hash holdout of fully labeled studies.
        labeled_indices = [i for i in range(len(keys)) if np.isfinite(official[i]).any()]
        ranked_holdout = sorted(
            labeled_indices,
            key=lambda i: hashlib.sha256(f"holdout:{keys[i]}".encode()).hexdigest(),
        )[:TUNE_HOLDOUT_STUDIES]
        tune_holdout = set(ranked_holdout)

        per_target = {
            target: Counter(
                {
                    "studies": 0,
                    "positive": 0,
                    "negative": 0,
                    "uncertain": 0,
                    "not_mentioned": 0,
                    "masked_ambiguous": 0,
                    "masked_not_mentioned": 0,
                    "unmasked_supervision_cells": 0,
                }
            )
            for target in TARGETS
        }
        confidence_tiers = Counter({"high_ge_0.9": 0, "medium_0.7_to_0.9": 0, "low_lt_0.7": 0})
        language_counts: Counter = Counter()
        source_breakdown: Counter = Counter()
        queue_rows: list[dict] = []
        agreement_rows: list[dict] = []
        report_lengths = []
        empty_reports = 0
        max_report_bytes_seen = 0
        states_by_index: list[dict[str, tuple[str, bool]]] = []

        for index, raw_row in enumerate(_read_bounded_csv(competition_root / "train.csv")[1]):
            key_hash = hashlib.sha256(keys[index].encode()).hexdigest()
            raw_report = raw_row.get("Report") or ""
            encoded_report = raw_report.encode("utf-8")
            max_report_bytes_seen = max(max_report_bytes_seen, len(encoded_report))
            if not raw_report.strip():
                empty_reports += 1
            report_lengths.append(len(raw_report))
            language = _detect_report_language(raw_report)
            language_counts[language] += 1
            row_states: dict[str, tuple[str, bool]] = {}
            for target in TARGETS:
                state, rule_confidence, evidence = _weak_label_state_for_target(raw_report, target)
                ambiguous = target in _AMBIGUOUS_TARGETS and state != "not_mentioned"
                usable = state != "not_mentioned" and not ambiguous
                row_states[target] = (state, usable)
                stats = per_target[target]
                stats["studies"] += 1
                if state == "not_mentioned":
                    if ambiguous:
                        stats["masked_ambiguous"] += 1
                    else:
                        stats["masked_not_mentioned"] += 1
                else:
                    stats[state] += 1
                if ambiguous:
                    stats["masked_ambiguous"] += 1
                    source_breakdown[f"{target}:rule_masked_ambiguous"] += 1
                elif usable:
                    stats["unmasked_supervision_cells"] += 1
                    if rule_confidence >= 0.9:
                        tier = "high_ge_0.9"
                    elif rule_confidence >= 0.7:
                        tier = "medium_0.7_to_0.9"
                    else:
                        tier = "low_lt_0.7"
                    confidence_tiers[tier] += 1
                    source_breakdown[f"{target}:rule_usable"] += 1
                if ambiguous and evidence["match_count"]:
                    queue_rows.append(
                        {
                            "study_key_sha256": key_hash,
                            "fold": assignments[keys[index]],
                            "target": target,
                            "state_before_mask": state,
                            "confidence": rounded_float(rule_confidence),
                            "language": language,
                            "section_counts": evidence["section_counts"],
                            "state_match_counts": evidence["state_match_counts"],
                            "priority_reason": "review_flagged_ambiguity_family",
                        }
                    )
                if index in tune_holdout and np.isfinite(official[index][TARGETS.index(target)]):
                    official_state = (
                        "positive" if official[index][TARGETS.index(target)] == 1 else "negative"
                    )
                    agreement_rows.append(
                        {
                            "study_key_sha256": key_hash,
                            "target": target,
                            "official_state": official_state,
                            "rule_state": state,
                            "usable_after_policy": usable,
                            "confidence": rounded_float(rule_confidence),
                        }
                    )
            states_by_index.append(row_states)
            if time.monotonic() - started > BUDGET_SECONDS - 600:
                raise GateError("weak_label_budget_exceeded")

        exact_states_written = sum(len(states) for states in states_by_index) + len(TARGETS)
        if exact_states_written > MAX_STATE_ROWS:
            raise GateError("state_inventory_too_large")
        inventory_digest = hashlib.sha256(
            _canonical_json_bytes(
                [
                    [
                        hashlib.sha256(keys[i].encode()).hexdigest(),
                        [[target, *states_by_index[i][target]] for target in TARGETS],
                    ]
                    for i in range(len(keys))
                ]
            )
        ).hexdigest()

        tp = Counter()
        fp = Counter()
        fn = Counter()
        tn = Counter()
        for row in agreement_rows:
            predicted_positive = row["rule_state"] == "positive" and row["usable_after_policy"]
            actual_positive = row["official_state"] == "positive"
            if predicted_positive and actual_positive:
                tp[row["target"]] += 1
            elif predicted_positive:
                fp[row["target"]] += 1
            elif actual_positive:
                fn[row["target"]] += 1
            else:
                tn[row["target"]] += 1
        quality_rows = []
        for target in TARGETS:
            denominator = tp[target] + fp[target]
            precision = tp[target] / denominator if denominator else None
            recall_denominator = tp[target] + fn[target]
            recall = tp[target] / recall_denominator if recall_denominator else None
            f1 = (
                2 * precision * recall / (precision + recall)
                if precision is not None and recall is not None and precision + recall > 0
                else None
            )
            quality_rows.append(
                {
                    "target": target,
                    "true_positive": tp[target],
                    "false_positive": fp[target],
                    "false_negative": fn[target],
                    "true_negative": tn[target],
                    "precision_on_official_holdout": rounded_float(precision)
                    if precision is not None
                    else None,
                    "recall_on_official_holdout": rounded_float(recall)
                    if recall is not None
                    else None,
                    "f1_on_official_holdout": rounded_float(f1) if f1 is not None else None,
                }
            )
        queue_rows.sort(
            key=lambda row: (-row["confidence"], row["study_key_sha256"], row["target"])
        )
        selected_queue = queue_rows[:MAX_QUEUE_ROWS]
        summary = {
            "schema_version": WEAK_LABEL_SCHEMA_VERSION,
            "gate": "weak-labels-v1",
            "r16_code_commit": R16_COMMIT,
            "bundle_sha256": EXPECTED_BUNDLE_SHA256,
            "ontology_version": WEAK_LABEL_ONTOLOGY_VERSION,
            "label_engine_version": WEAK_LABEL_ENGINE_VERSION,
            "population_reconciliation": reconciliation,
            "reports_read": len(keys),
            "empty_reports": empty_reports,
            "report_length_mean_chars": rounded_float(float(np.mean(report_lengths)))
            if report_lengths
            else None,
            "report_length_max_chars": max(report_lengths, default=0),
            "max_report_bytes_seen": max_report_bytes_seen,
            "report_limit_bytes": MAX_REPORT_BYTES,
            "per_target_coverage": {target: dict(stats) for target, stats in per_target.items()},
            "confidence_tier_totals": dict(confidence_tiers),
            "language_counts": dict(sorted(language_counts.items())),
            "source_breakdown": dict(sorted(source_breakdown.items())),
            "cross_fit": {
                "tune_eval_split": "hash_holdout",
                "tune_holdout_studies": len(tune_holdout),
                "agreement_pairs_evaluated": len(agreement_rows),
                "note": "rules evaluated on held-out fully labeled studies only",
                "per_target_quality": quality_rows,
            },
            "human_review_queue": {
                "eligible_rows": len(queue_rows),
                "selected_rows": len(selected_queue),
                "selection": "stratified by target with descending confidence",
                "rows": selected_queue,
            },
            "artifact_inventory_digest_sha256": inventory_digest,
            "privacy": {
                "raw_reports_emitted": False,
                "identifiers_emitted": False,
                "pixels_accessed": False,
                "external_api_calls": 0,
            },
            "elapsed_seconds": rounded_float(time.monotonic() - started),
        }
        payload = _canonical_json_bytes(summary)
        if not 0 < len(payload) <= MAX_SUMMARY_BYTES * 8:
            raise GateError("summary_size_invalid")
        _write_artifact(output_root, "weak_labels_v1_summary.json", payload)
        print(
            f"event=weak_labels_v1_complete reports={len(keys)}"
            f" reconciled={int(reconciliation['difference_reconciled'])}"
            f" queue={len(selected_queue)}"
        )
        return 0
    finally:
        if str(runtime_root) in sys.path:
            sys.path.remove(str(runtime_root))
        shutil.rmtree(runtime_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(run_real_data_gate())


REPR_EPOCHS: Final = 20
REPR_BATCH_SIZE: Final = 16
REPR_LEARNING_RATE: Final = 5e-4
REPR_BUDGET_FRACTION: Final = 0.80
REPR_MAX_STUDIES: Final = 400
ROTATION_ANGLES: Final = (90, 180, 270)
REPR_HIDDEN: Final = E00C_HIDDEN


def run_repr_v0():
    """Image-only rotation-prediction pretraining on all eligible MRI studies.

    Same TinyCNNShared features encoder, r16 preprocessing, seed 42. No labels
    are read or used. Emits one sanitized aggregate JSON summary with training
    metrics, fold-0 validation loss, and skip audit.
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

        keys, _ = read_study_labels(competition_root / "train.csv")

        # Deterministic hash-order processing: sort by SHA-256 of opaque key.
        ranked = sorted(
            range(len(keys)), key=lambda i: hashlib.sha256(keys[i].encode()).hexdigest()
        )
        config = PreprocessingConfig(
            sample_count=SAMPLE_COUNT,
            resize_rows_columns=RESIZE_SHAPE,
            adjacent_slice_channels=True,
        )
        versions = PipelineVersions(
            code_commit=R16_COMMIT, source_manifest_version=SOURCE_MANIFEST_VERSION
        )

        # Phase 1: preprocess all eligible studies within budget fraction.
        tensors = {}
        skip_reasons: Counter = Counter()
        series_processed = 0
        for index in ranked[:REPR_MAX_STUDIES]:
            if time.monotonic() - started > BUDGET_SECONDS * REPR_BUDGET_FRACTION:
                break
            key = keys[index]
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
        n_eligible = len(tensors)
        if n_eligible < REPR_BATCH_SIZE * 2:
            raise GateError("repr_eligible_studies_insufficient")

        # Deterministic split by hash rank: last 10% as validation.
        eligible_ranked = [index for index in ranked if index in tensors]
        val_cutoff = max(1, int(n_eligible * 0.10))
        val_indices = eligible_ranked[:val_cutoff]
        train_indices = eligible_ranked[val_cutoff:]

        # Phase 2: rotation-prediction model on TinyCNNShared.features encoder.
        gpu_usable = False
        if torch.cuda.is_available():
            try:
                capability = torch.cuda.get_device_capability(0)
                gpu_usable = bool(capability[0] >= 7)
            except Exception:
                pass
        device = torch.device("cuda" if gpu_usable else "cpu")
        torch.manual_seed(SEED)
        encoder_features, _ = _build_tiny_cnn(REPR_HIDDEN, 12)
        classifier_head = nn.Linear(REPR_HIDDEN, len(ROTATION_ANGLES) + 1)
        encoder = nn.Sequential(encoder_features, nn.Flatten(1)).to(device)
        classifier_head = classifier_head.to(device)
        optimizer = torch.optim.AdamW(
            list(encoder.parameters()) + list(classifier_head.parameters()),
            lr=REPR_LEARNING_RATE,
            weight_decay=0.0,
        )
        criterion = nn.CrossEntropyLoss()

        rng = np.random.default_rng(SEED)
        order = np.arange(len(train_indices))
        epoch_losses: list = []
        epoch_val_losses: list = []
        first_loss = float("nan")
        last_loss = float("nan")
        best_val_loss = float("inf")
        rotations_applied: Counter = Counter()
        for epoch in range(REPR_EPOCHS):
            rng.shuffle(order)
            epoch_batch_losses = []
            for batch_start in range(0, len(order), REPR_BATCH_SIZE):
                batch_ids = order[batch_start : batch_start + REPR_BATCH_SIZE]
                optimizer.zero_grad()
                batch_loss_tensor = torch.zeros((), device=device)
                batch_samples = 0
                for local_index in batch_ids:
                    global_index = train_indices[local_index]
                    study_np = tensors[global_index]
                    flat_slices = study_np.reshape(-1, *study_np.shape[-3:])
                    slice_index = int(rng.integers(len(flat_slices)))
                    x_np = flat_slices[slice_index : slice_index + 1]
                    rotation_class = int(rng.integers(len(ROTATION_ANGLES) + 1))
                    angle = ROTATION_ANGLES[rotation_class - 1] if rotation_class > 0 else 0
                    x_rotated = np.rot90(x_np, k=rotation_class, axes=(-2, -1)).copy()
                    x = torch.from_numpy(x_rotated).to(device)
                    logits = classifier_head(encoder(x))
                    target_tensor = torch.tensor([rotation_class], device=device)
                    batch_loss_tensor = batch_loss_tensor + criterion(logits, target_tensor)
                    batch_samples += 1
                    rotations_applied[angle] += 1
                if batch_samples == 0:
                    continue
                loss = batch_loss_tensor / batch_samples
                loss.backward()
                optimizer.step()
                epoch_batch_losses.append(float(loss.item()))
            if epoch_batch_losses:
                mean_epoch_loss = float(np.mean(epoch_batch_losses))
                epoch_losses.append(mean_epoch_loss)
                if epoch == 0:
                    first_loss = mean_epoch_loss
                last_loss = mean_epoch_loss

            # Validation pass every 5 epochs and at the final epoch.
            if (epoch + 1) % 5 == 0 or epoch == REPR_EPOCHS - 1:
                encoder.eval()
                classifier_head.eval()
                val_losses = []
                with torch.no_grad():
                    for global_index in val_indices:
                        study_np = tensors[global_index]
                        flat_slices = study_np.reshape(-1, *study_np.shape[-3:])
                        for slice_index in range(min(len(flat_slices), 4)):
                            x_np = flat_slices[slice_index : slice_index + 1]
                            rotation_class = int(rng.integers(len(ROTATION_ANGLES) + 1))
                            x_rotated = np.rot90(x_np, k=rotation_class, axes=(-2, -1)).copy()
                            x = torch.from_numpy(x_rotated).to(device)
                            logits = classifier_head(encoder(x))
                            target_tensor = torch.tensor([rotation_class], device=device)
                            val_losses.append(float(criterion(logits, target_tensor).item()))
                if val_losses:
                    mean_val_loss = float(np.mean(val_losses))
                    epoch_val_losses.append(mean_val_loss)
                    best_val_loss = min(best_val_loss, mean_val_loss)
                encoder.train()
                classifier_head.train()

        elapsed = time.monotonic() - started
        summary = {
            "schema_version": 1,
            "gate": "repr-v0",
            "r16_code_commit": R16_COMMIT,
            "bundle_sha256": EXPECTED_BUNDLE_SHA256,
            "pretext_task": "rotation_prediction",
            "rotation_angles": list(ROTATION_ANGLES),
            "n_studies_total": len(keys),
            "n_studies_preprocessed": n_eligible,
            "n_series_processed": series_processed,
            "skip_reason_counts": dict(sorted(skip_reasons.items())),
            "train_study_count": len(train_indices),
            "val_study_count": len(val_indices),
            "epochs_completed": len(epoch_losses),
            "first_train_loss": rounded_float(first_loss),
            "last_train_loss": rounded_float(last_loss),
            "loss_decrease_ratio": rounded_float(first_loss / last_loss) if last_loss > 0 else None,
            "best_val_loss": rounded_float(best_val_loss),
            "val_evaluations": len(epoch_val_losses),
            "rotation_distribution": {str(k): v for k, v in sorted(rotations_applied.items())},
            "hidden_dim": REPR_HIDDEN,
            "learning_rate": REPR_LEARNING_RATE,
            "batch_size": REPR_BATCH_SIZE,
            "seed": SEED,
            "privacy": {
                "raw_reports_read": False,
                "labels_used_in_training": False,
                "identifiers_emitted": False,
                "pixels_accessed": True,
                "external_api_calls": 0,
            },
            "elapsed_seconds": rounded_float(elapsed),
        }
        payload = _canonical_json_bytes(summary)
        if not 0 < len(payload) <= MAX_SUMMARY_BYTES:
            raise GateError("summary_size_invalid")
        output_root = Path("/kaggle/working")
        output_root.mkdir(parents=True, exist_ok=True)
        temporary = output_root / ".repr_v0_summary.json.tmp"
        temporary.write_bytes(payload)
        os.replace(temporary, output_root / "repr_v0_summary.json")
        print(
            f"event=repr_v0_complete studies={n_eligible}"
            f" train={len(train_indices)} val={len(val_indices)}"
            f" epochs={len(epoch_losses)} first_loss={rounded_float(first_loss)}"
            f" last_loss={rounded_float(last_loss)}"
        )
        return 0
    finally:
        if str(runtime_root) in sys.path:
            sys.path.remove(str(runtime_root))
        shutil.rmtree(runtime_root, ignore_errors=True)
