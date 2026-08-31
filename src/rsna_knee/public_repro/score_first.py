"""Score-first public baseline discovery and static notebook auditing.

The helpers in this module are deliberately network-free. They parse evidence
collected by the official Kaggle CLI and enforce claim boundaries before a
public notebook can become a private reproduction candidate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence


_SCORE_FIELDS = ("score", "publicScore", "public_score", "bestScore", "best_score")
_REF_FIELDS = ("ref", "kernelRef", "kernel_ref", "id")
_TITLE_FIELDS = ("title", "name")
_RUNTIME_FIELDS = ("runtime", "runtimeSeconds", "runtime_seconds")
_VERSION_FIELDS = ("version", "versionNumber", "version_number")

_SUBMISSION_PATTERNS = (
    re.compile(r"\bkaggle\s+competitions\s+submit\b", re.IGNORECASE),
    re.compile(r"\bcompetition_submit\s*\(", re.IGNORECASE),
    re.compile(r"\bcompetitions?\.submit\s*\(", re.IGNORECASE),
)
_NETWORK_PATTERNS = (
    re.compile(r"\brequests\.(?:get|post|put|patch|delete)\s*\(", re.IGNORECASE),
    re.compile(r"\burllib\.request\.", re.IGNORECASE),
    re.compile(r"\b(?:wget|curl)\s+https?://", re.IGNORECASE),
)
_REPORT_PATTERNS = (
    re.compile(r"test(?:_df|_data|_csv)?\s*\[[^\]]*['\"]Report['\"]", re.IGNORECASE),
    re.compile(r"['\"]Report['\"]\s+in\s+test", re.IGNORECASE),
)
_PRIVATE_INPUT_PATTERNS = (
    re.compile(r"\[Private Dataset\]", re.IGNORECASE),
    re.compile(r"private[_ -]?dataset", re.IGNORECASE),
)
_DYNAMIC_TEST_PATTERNS = (
    re.compile(r"read_csv\([^\n]*test\.csv", re.IGNORECASE),
    re.compile(r"StudyInstanceUID", re.IGNORECASE),
)
_HARDCODED_THREE_PATTERNS = (
    re.compile(r"\brange\(3\)"),
    re.compile(r"\bhead\(3\)"),
    re.compile(r"\b(?:test|submission)\s*=\s*(?:test|submission)\s*\[:3\]"),
)


class ScoreFirstError(ValueError):
    """Raised when score-first evidence violates its contract."""


@dataclass(frozen=True, slots=True)
class KernelListing:
    """One normalized row from ``kaggle kernels list --csv`` output."""

    ref: str
    title: str
    score: float | None
    runtime_seconds: float | None
    version: int | None
    raw: Mapping[str, str]

    @property
    def owner_slug(self) -> str:
        """Return the canonical owner/slug reference."""

        return self.ref.strip()


@dataclass(frozen=True, slots=True)
class NotebookStaticAudit:
    """Static source-code red flags for a public notebook."""

    private_input_markers: int
    submission_api_calls: int
    network_calls: int
    test_report_accesses: int
    unsafe_torch_loads: int
    safe_torch_loads: int
    hardcoded_three_markers: int
    dynamic_test_evidence: bool

    @property
    def blocking_reasons(self) -> tuple[str, ...]:
        """Return fail-closed blockers visible from source text alone."""

        blockers: list[str] = []
        if self.private_input_markers:
            blockers.append("private_input_marker")
        if self.submission_api_calls:
            blockers.append("submission_api_call")
        if self.network_calls:
            blockers.append("runtime_network_call")
        if self.test_report_accesses:
            blockers.append("test_report_access")
        if self.unsafe_torch_loads:
            blockers.append("unsafe_torch_load")
        if self.hardcoded_three_markers:
            blockers.append("possible_public_example_hardcode")
        if not self.dynamic_test_evidence:
            blockers.append("dynamic_test_discovery_unverified")
        return tuple(blockers)


@dataclass(frozen=True, slots=True)
class CampaignCandidate:
    """One score-first candidate from the machine-readable campaign file."""

    candidate_id: str
    owner_slug: str
    required_version: int
    script_version_id: int | None
    source_reported_public_score: float
    priority: int
    status: str
    reason: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CampaignCandidate":
        candidate = cls(
            candidate_id=_required_text(value, "candidate_id"),
            owner_slug=_required_text(value, "owner_slug"),
            required_version=_required_positive_int(value, "required_version"),
            script_version_id=_optional_positive_int(value.get("script_version_id")),
            source_reported_public_score=_required_score(
                value, "source_reported_public_score"
            ),
            priority=_required_positive_int(value, "priority"),
            status=_required_text(value, "status"),
            reason=_required_text(value, "reason"),
        )
        if "/" not in candidate.owner_slug:
            raise ScoreFirstError(
                f"{candidate.candidate_id}: owner_slug must use owner/slug"
            )
        return candidate


@dataclass(frozen=True, slots=True)
class PullEvidence:
    """Checksums and audit results for a locally pulled public notebook."""

    owner_slug: str
    source_root: str
    source_files: tuple[dict[str, Any], ...]
    output_files: tuple[dict[str, Any], ...]
    source_audit: NotebookStaticAudit

    def to_json(self) -> dict[str, Any]:
        """Return a stable JSON-compatible representation."""

        return {
            "owner_slug": self.owner_slug,
            "source_root": self.source_root,
            "source_files": list(self.source_files),
            "output_files": list(self.output_files),
            "source_audit": asdict(self.source_audit),
            "blocking_reasons": list(self.source_audit.blocking_reasons),
        }


def parse_kaggle_kernel_csv(text: str) -> tuple[KernelListing, ...]:
    """Parse official Kaggle CLI CSV output with tolerant field aliases."""

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ScoreFirstError("Kaggle kernel CSV is missing a header")

    rows: list[KernelListing] = []
    for raw_row in reader:
        row = {str(key): str(value or "") for key, value in raw_row.items()}
        ref = _first_nonempty(row, _REF_FIELDS)
        title = _first_nonempty(row, _TITLE_FIELDS)
        if not ref:
            raise ScoreFirstError("Kaggle kernel row is missing a ref")
        if not title:
            title = ref
        rows.append(
            KernelListing(
                ref=ref,
                title=title,
                score=_first_float(row, _SCORE_FIELDS),
                runtime_seconds=_first_float(row, _RUNTIME_FIELDS),
                version=_first_int(row, _VERSION_FIELDS),
                raw=row,
            )
        )
    return tuple(rows)


def shortlist_listings(
    listings: Iterable[KernelListing],
    *,
    minimum_score: float = 0.93,
) -> tuple[KernelListing, ...]:
    """Return score-qualified listings in deterministic order."""

    if not 0.0 <= minimum_score <= 1.0:
        raise ScoreFirstError("minimum_score must be within [0, 1]")
    selected = [
        item for item in listings if item.score is not None and item.score >= minimum_score
    ]
    selected.sort(
        key=lambda item: (
            -(item.score if item.score is not None else -1.0),
            item.ref,
        )
    )
    return tuple(selected)


def scan_notebook_source(source: str) -> NotebookStaticAudit:
    """Statically scan notebook/script text for reproduction blockers."""

    unsafe_loads = 0
    safe_loads = 0
    for line in source.splitlines():
        if "torch.load" not in line:
            continue
        compact = re.sub(r"\s+", "", line)
        if "weights_only=True" in compact:
            safe_loads += 1
        else:
            unsafe_loads += 1

    return NotebookStaticAudit(
        private_input_markers=_count_patterns(source, _PRIVATE_INPUT_PATTERNS),
        submission_api_calls=_count_patterns(source, _SUBMISSION_PATTERNS),
        network_calls=_count_patterns(source, _NETWORK_PATTERNS),
        test_report_accesses=_count_patterns(source, _REPORT_PATTERNS),
        unsafe_torch_loads=unsafe_loads,
        safe_torch_loads=safe_loads,
        hardcoded_three_markers=_count_patterns(source, _HARDCODED_THREE_PATTERNS),
        dynamic_test_evidence=all(
            pattern.search(source) is not None for pattern in _DYNAMIC_TEST_PATTERNS
        ),
    )


def load_campaign(path: str | Path) -> tuple[CampaignCandidate, ...]:
    """Load and validate the score-first campaign configuration."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("candidates"), list):
        raise ScoreFirstError("campaign must contain a candidates list")
    candidates = tuple(
        CampaignCandidate.from_mapping(item) for item in raw["candidates"]
    )
    ids = [item.candidate_id for item in candidates]
    if len(ids) != len(set(ids)):
        raise ScoreFirstError("candidate_id values must be unique")
    return candidates


def prioritized_campaign(
    candidates: Sequence[CampaignCandidate],
) -> tuple[CampaignCandidate, ...]:
    """Return candidates ordered by declared execution priority."""

    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.priority,
                -item.source_reported_public_score,
                item.candidate_id,
            ),
        )
    )


def collect_pull_evidence(
    owner_slug: str,
    source_root: str | Path,
    output_root: str | Path,
) -> PullEvidence:
    """Fingerprint pulled source/output trees and statically audit source text."""

    source_path = Path(source_root)
    output_path = Path(output_root)
    source_files = _inventory(source_path)
    output_files = _inventory(output_path)
    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(source_path.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".py", ".ipynb", ".json", ".md"}
    )
    return PullEvidence(
        owner_slug=owner_slug,
        source_root=source_path.name,
        source_files=source_files,
        output_files=output_files,
        source_audit=scan_notebook_source(source_text),
    )


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return a canonical lowercase SHA-256 for a local file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory(root: Path) -> tuple[dict[str, Any], ...]:
    if not root.exists():
        return ()
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return tuple(rows)


def _count_patterns(text: str, patterns: Sequence[re.Pattern[str]]) -> int:
    return sum(len(pattern.findall(text)) for pattern in patterns)


def _first_nonempty(row: Mapping[str, str], keys: Sequence[str]) -> str:
    for key in keys:
        value = row.get(key, "").strip()
        if value:
            return value
    return ""


def _first_float(row: Mapping[str, str], keys: Sequence[str]) -> float | None:
    raw = _first_nonempty(row, keys)
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _first_int(row: Mapping[str, str], keys: Sequence[str]) -> int | None:
    raw = _first_nonempty(row, keys)
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _required_text(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ScoreFirstError(f"{key} must be a non-empty string")
    return item.strip()


def _required_positive_int(value: Mapping[str, Any], key: str) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int) or item < 1:
        raise ScoreFirstError(f"{key} must be a positive integer")
    return item


def _optional_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ScoreFirstError("optional integer must be null or positive")
    return value


def _required_score(value: Mapping[str, Any], key: str) -> float:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, (int, float)):
        raise ScoreFirstError(f"{key} must be numeric")
    score = float(item)
    if not 0.0 <= score <= 1.0:
        raise ScoreFirstError(f"{key} must be within [0, 1]")
    return score
