"""Bounded, identifier-free performance measurements for the DICOM pipeline."""

from __future__ import annotations

import os
import platform
import resource
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
import pydicom

from rsna_knee.dicom.pipeline import (
    PipelineVersions,
    PreprocessedSeries,
    PreprocessingConfig,
    decode_dicom,
    dicom_to_model,
    order_series,
    preprocess_series,
)


@dataclass(frozen=True, slots=True)
class TimingSummary:
    minimum_seconds: float
    median_seconds: float
    maximum_seconds: float


@dataclass(frozen=True, slots=True)
class WorkerTiming:
    workers: int
    tasks: int
    wall_seconds: float
    tasks_per_second: float
    speedup_vs_one_worker: float


@dataclass(frozen=True, slots=True)
class KaggleCompatibility:
    python_version: str
    platform_system: str
    platform_machine: str
    cpu_count: int
    numpy_version: str
    pydicom_version: str
    python_supported: bool
    linux_runtime_observed: bool
    offline_bundle_verified: bool
    kaggle_runtime_verified: bool
    accelerator: str
    horizontal_flip: bool
    through_plane_resampling: bool


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    schema_version: int
    iterations: int
    slices_per_series: int
    decode_time: TimingSummary
    preprocessing_time: TimingSummary
    representative_tensor_cache_bytes: int
    process_peak_rss_bytes: int
    peak_rss_increase_bytes: int
    cpu_parallelism: tuple[WorkerTiming, ...]
    kaggle_compatibility: KaggleCompatibility
    deterministic_replay: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready report containing no paths, IDs, or checksums."""

        return asdict(self)


def _summary(values: list[float]) -> TimingSummary:
    return TimingSummary(
        minimum_seconds=min(values),
        median_seconds=statistics.median(values),
        maximum_seconds=max(values),
    )


def _peak_rss_bytes() -> int:
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return peak if sys.platform == "darwin" else peak * 1024


def _tensor_cache_bytes(result: PreprocessedSeries) -> int:
    buffer = BytesIO()
    np.save(buffer, result.tensor, allow_pickle=False)
    return buffer.tell()


def _run_once(
    paths: tuple[Path, ...], config: PreprocessingConfig, versions: PipelineVersions
) -> str:
    return dicom_to_model(paths, config, versions).provenance.output_checksum


def benchmark_dicom_pipeline(
    paths: tuple[Path, ...],
    config: PreprocessingConfig,
    versions: PipelineVersions,
    *,
    iterations: int = 3,
    worker_counts: tuple[int, ...] = (1, 2),
    offline_bundle_verified: bool = False,
) -> BenchmarkReport:
    """Measure synthetic/private in-place execution without returning source details."""

    if not paths:
        raise ValueError("benchmark_input_empty")
    if not 1 <= iterations <= 20:
        raise ValueError("benchmark_iterations_invalid")
    workers = tuple(sorted(set(worker_counts) | {1}))
    if not workers or any(value < 1 or value > 16 for value in workers):
        raise ValueError("benchmark_worker_count_invalid")

    peak_rss_before = _peak_rss_bytes()
    decode_times: list[float] = []
    preprocessing_times: list[float] = []
    checksums: set[str] = set()
    result: PreprocessedSeries | None = None
    for _ in range(iterations):
        started = time.perf_counter()
        decoded = tuple(decode_dicom(path) for path in paths)
        decode_times.append(time.perf_counter() - started)

        started = time.perf_counter()
        ordered = order_series(
            decoded,
            allow_instance_fallback_for_qa=config.allow_instance_fallback_for_qa,
        )
        result = preprocess_series(ordered, config, versions)
        preprocessing_times.append(time.perf_counter() - started)
        checksums.add(result.provenance.output_checksum)
    if result is None or len(checksums) != 1:
        raise RuntimeError("benchmark_nondeterministic_output")

    tasks = max(workers) * iterations
    parallel_raw: list[tuple[int, float, float]] = []
    parallel_checksums: set[str] = set()
    for worker_count in workers:
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(_run_once, paths, config, versions) for _ in range(tasks)]
            parallel_checksums.update(future.result() for future in futures)
        elapsed = max(time.perf_counter() - started, 1e-12)
        parallel_raw.append((worker_count, elapsed, tasks / elapsed))
    if parallel_checksums != checksums:
        raise RuntimeError("benchmark_parallel_nondeterministic_output")
    baseline_throughput = parallel_raw[0][2]
    parallel = tuple(
        WorkerTiming(
            workers=worker_count,
            tasks=tasks,
            wall_seconds=elapsed,
            tasks_per_second=throughput,
            speedup_vs_one_worker=throughput / baseline_throughput,
        )
        for worker_count, elapsed, throughput in parallel_raw
    )

    python_supported = (3, 11) <= sys.version_info[:2] < (3, 13)
    linux_runtime = platform.system() == "Linux"
    compatibility = KaggleCompatibility(
        python_version=platform.python_version(),
        platform_system=platform.system(),
        platform_machine=platform.machine(),
        cpu_count=os.cpu_count() or 1,
        numpy_version=np.__version__,
        pydicom_version=pydicom.__version__,
        python_supported=python_supported,
        linux_runtime_observed=linux_runtime,
        offline_bundle_verified=offline_bundle_verified,
        kaggle_runtime_verified=python_supported and linux_runtime and offline_bundle_verified,
        accelerator="cpu",
        horizontal_flip=False,
        through_plane_resampling=False,
    )
    return BenchmarkReport(
        schema_version=1,
        iterations=iterations,
        slices_per_series=len(paths),
        decode_time=_summary(decode_times),
        preprocessing_time=_summary(preprocessing_times),
        representative_tensor_cache_bytes=_tensor_cache_bytes(result),
        process_peak_rss_bytes=_peak_rss_bytes(),
        peak_rss_increase_bytes=max(0, _peak_rss_bytes() - peak_rss_before),
        cpu_parallelism=parallel,
        kaggle_compatibility=compatibility,
        deterministic_replay=True,
    )
