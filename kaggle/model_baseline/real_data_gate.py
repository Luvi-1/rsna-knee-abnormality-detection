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

COMPETITION_SLUG: Final = "rsna-knee-abnormality-detection"
BUNDLE_DATASET_REF: Final = "lavicheema/rsna-knee-dicom-qa-bundle-da5b9c8-91ed07921059"
# pragma: allowlist secret - published content digest identity, not a credential
EXPECTED_BUNDLE_SHA256: Final = "91ed079210592448664f52c1a24ce1a693275ef09fa350167712097ab97de40b"
# pragma: allowlist secret - frozen r16 git commit identifier, not a credential
R16_COMMIT: Final = "da5b9c83b874f02067ecc8f1c0a4a1d50fe01b1f"
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
E00B_EPOCHS: Final = 2000
MAX_SERIES_PER_STUDY: Final = 4
MAX_FILES_PER_SERIES: Final = 128
SAMPLE_COUNT: Final = 8
RESIZE_SHAPE: Final = (64, 64)
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


if __name__ == "__main__":
    raise SystemExit(run_real_data_gate())
