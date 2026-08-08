"""Deterministic duplicate evidence and protected-component construction.

The helpers in this module operate on already-opaque identifiers.  Callers must
not pass raw competition UIDs or report text to persisted outputs.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum


class DuplicateInvariantError(ValueError):
    """Raised when duplicate evidence cannot form a valid protected graph."""


class EdgeDisposition(StrEnum):
    """Strength of duplicate evidence."""

    HARD = "hard"
    CANDIDATE = "candidate"
    NONE = "none"


def canonical_endpoints(left: str, right: str) -> tuple[str, str]:
    """Return non-empty, distinct edge endpoints in lexical order."""

    if not left or not right:
        raise DuplicateInvariantError("duplicate edge endpoints must be non-empty")
    if left == right:
        raise DuplicateInvariantError("duplicate edges may not be self-edges")
    return (left, right) if left < right else (right, left)


@dataclass(frozen=True, order=True)
class DuplicateEdge:
    """Canonical duplicate evidence between two opaque entity keys."""

    left: str
    right: str
    kind: str
    disposition: EdgeDisposition

    def __post_init__(self) -> None:
        left, right = canonical_endpoints(self.left, self.right)
        object.__setattr__(self, "left", left)
        object.__setattr__(self, "right", right)
        if not self.kind:
            raise DuplicateInvariantError("duplicate edge kind must be non-empty")
        if self.disposition is EdgeDisposition.NONE:
            raise DuplicateInvariantError("non-matches must not be stored as duplicate edges")


class _DeterministicUnionFind:
    """Union-find whose representative is always the lexical minimum member."""

    def __init__(self, nodes: Iterable[str]) -> None:
        self._parent = {node: node for node in nodes}
        if any(not node for node in self._parent):
            raise DuplicateInvariantError("protected-component keys must be non-empty")

    def add(self, node: str) -> None:
        if not node:
            raise DuplicateInvariantError("protected-component keys must be non-empty")
        self._parent.setdefault(node, node)

    def find(self, node: str) -> str:
        parent = self._parent[node]
        while parent != self._parent[parent]:
            parent = self._parent[parent]
        root = parent
        parent = self._parent[node]
        while parent != root:
            next_parent = self._parent[parent]
            self._parent[parent] = root
            parent = next_parent
        self._parent[node] = root
        return root

    def union(self, left: str, right: str) -> None:
        self.add(left)
        self.add(right)
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        root, child = sorted((left_root, right_root))
        self._parent[child] = root

    def component_map(self) -> dict[str, str]:
        return {node: self.find(node) for node in sorted(self._parent)}


def build_protected_components(
    nodes: Iterable[str],
    edges: Iterable[DuplicateEdge],
    *,
    include_candidates: bool = False,
) -> dict[str, str]:
    """Map every node to a deterministic hard protected component.

    Candidate evidence is deliberately never allowed to merge protected
    components. ``include_candidates`` remains as a compatibility keyword, but
    no longer changes the protection policy; callers that need the review-only
    closure must use :func:`build_candidate_components` explicitly.
    """

    edge_list = sorted(set(edges))
    graph = _DeterministicUnionFind(nodes)
    for edge in edge_list:
        graph.add(edge.left)
        graph.add(edge.right)
        if edge.disposition is EdgeDisposition.HARD:
            graph.union(edge.left, edge.right)
    components = graph.component_map()
    assert_hard_edges_within_components(edge_list, components)
    # Consume the compatibility argument so static analysis makes the intended
    # no-op explicit. Candidate evidence cannot alter a protected mapping.
    _ = include_candidates
    return components


def build_candidate_components(
    nodes: Iterable[str],
    edges: Iterable[DuplicateEdge],
) -> dict[str, str]:
    """Map nodes to review-only soft clusters without changing hard groups.

    Hard and candidate edges both participate in this map so every member of a
    hard component follows its candidate-connected neighbours into the same
    soft review cluster. The result must never be used as a fold group.
    """

    edge_list = sorted(set(edges))
    graph = _DeterministicUnionFind(nodes)
    for edge in edge_list:
        graph.add(edge.left)
        graph.add(edge.right)
        graph.union(edge.left, edge.right)
    components = graph.component_map()
    assert_protected_edges_within_components(
        edge_list,
        components,
        include_candidates=True,
    )
    return components


def component_members(component_by_node: Mapping[str, str]) -> tuple[tuple[str, ...], ...]:
    """Return deterministic component membership tuples."""

    members: dict[str, list[str]] = {}
    for node, component in sorted(component_by_node.items()):
        members.setdefault(component, []).append(node)
    return tuple(tuple(values) for _, values in sorted(members.items()))


def assert_hard_edges_within_components(
    edges: Iterable[DuplicateEdge], component_by_node: Mapping[str, str]
) -> None:
    """Prove that every hard duplicate edge is contained by one component."""

    assert_protected_edges_within_components(
        edges,
        component_by_node,
        include_candidates=False,
    )


def assert_protected_edges_within_components(
    edges: Iterable[DuplicateEdge],
    component_by_node: Mapping[str, str],
    *,
    include_candidates: bool,
) -> None:
    """Prove that every edge selected by the protection policy is contained."""

    for edge in edges:
        protected = edge.disposition is EdgeDisposition.HARD or (
            include_candidates and edge.disposition is EdgeDisposition.CANDIDATE
        )
        if not protected:
            continue
        left_component = component_by_node.get(edge.left)
        right_component = component_by_node.get(edge.right)
        if left_component is None or right_component is None:
            raise DuplicateInvariantError(
                "protected edge endpoint is absent from component mapping"
            )
        if left_component != right_component:
            raise DuplicateInvariantError("protected duplicate edge crosses protected components")


_DATE_PATTERNS = (
    re.compile(r"(?<!\w)\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?!\w)"),
    re.compile(r"(?<!\w)\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}(?!\w)"),
)
_TIME_PATTERN = re.compile(r"(?<!\w)\d{1,2}:\d{2}(?::\d{2})?(?!\w)")
_MEASUREMENT_PATTERN = re.compile(
    r"(?<!\w)[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)\s*"
    r"(mm|cm|km|m|um|µm|kg|mg|g|ml|l|degrees?|deg|°)(?!\w)",
    re.IGNORECASE,
)
_PERCENT_PATTERN = re.compile(r"(?<!\w)[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)\s*%(?!\w)")
_NUMBER_PATTERN = re.compile(r"(?<!\w)[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)(?!\w)")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_TOKEN_PATTERN = re.compile(r"<[^>]+>|[^\W_]+", re.UNICODE)


def _measurement_placeholder(match: re.Match[str]) -> str:
    unit = match.group(1).casefold().replace("µ", "u").replace("°", "deg")
    if unit.startswith("degree"):
        unit = "deg"
    return f"<measurement:{unit}>"


def normalize_report(text: str) -> str:
    """Normalize report structure with typed placeholders for numeric values."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    for pattern in _DATE_PATTERNS:
        normalized = pattern.sub("<date>", normalized)
    normalized = _TIME_PATTERN.sub("<time>", normalized)
    normalized = _MEASUREMENT_PATTERN.sub(_measurement_placeholder, normalized)
    normalized = _PERCENT_PATTERN.sub("<percent>", normalized)
    normalized = _NUMBER_PATTERN.sub("<number>", normalized)
    return _WHITESPACE_PATTERN.sub(" ", normalized).strip()


def report_exact_digest(text: str, *, key: bytes | None = None) -> str:
    """Return a normalized-text digest, optionally protected by a private key.

    Unkeyed digests are suitable only for ephemeral comparison inside the
    authorized environment.  Any persisted row-level digest must use ``key``.
    """

    payload = normalize_report(text).encode("utf-8")
    if key is None:
        return hashlib.sha256(payload).hexdigest()
    if len(key) < 32:
        raise ValueError("report digest keys must contain at least 32 bytes")
    return hmac.digest(key, payload, "sha256").hex()


def _report_tokens(normalized: str) -> tuple[str, ...]:
    return tuple(_TOKEN_PATTERN.findall(normalized))


def _token_shingles(tokens: Sequence[str], size: int) -> set[tuple[str, ...]]:
    if size <= 0:
        raise ValueError("shingle size must be positive")
    if len(tokens) < size:
        return set()
    return {tuple(tokens[index : index + size]) for index in range(len(tokens) - size + 1)}


def _jaccard(left: set[tuple[str, ...]], right: set[tuple[str, ...]]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _levenshtein_similarity(left: Sequence[str], right: Sequence[str]) -> float:
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_token in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_token in enumerate(right, start=1):
            substitution_cost = 0 if left_token == right_token else 1
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + substitution_cost,
                )
            )
        previous = current
    return 1.0 - previous[-1] / max(len(left), len(right))


@dataclass(frozen=True)
class ReportMatch:
    """Privacy-safe similarity evidence; no report tokens are retained."""

    disposition: EdgeDisposition
    exact: bool
    token_count_left: int
    token_count_right: int
    length_ratio: float
    shingle_jaccard: float
    levenshtein_similarity: float


def compare_reports(
    left: str,
    right: str,
    *,
    minimum_tokens: int = 20,
    shingle_size: int = 5,
    candidate_jaccard: float = 0.90,
    confirmed_jaccard: float = 0.95,
    confirmed_levenshtein: float = 0.95,
    minimum_length_ratio: float = 0.90,
) -> ReportMatch:
    """Classify report similarity as review-only evidence or unrelated."""

    if minimum_tokens <= 0:
        raise ValueError("minimum_tokens must be positive")
    if not 0.0 <= candidate_jaccard <= confirmed_jaccard <= 1.0:
        raise ValueError("invalid report Jaccard thresholds")
    if not 0.0 <= confirmed_levenshtein <= 1.0:
        raise ValueError("invalid report Levenshtein threshold")
    if not 0.0 <= minimum_length_ratio <= 1.0:
        raise ValueError("invalid report length-ratio threshold")

    left_normalized = normalize_report(left)
    right_normalized = normalize_report(right)
    left_tokens = _report_tokens(left_normalized)
    right_tokens = _report_tokens(right_normalized)
    maximum_length = max(len(left_tokens), len(right_tokens))
    length_ratio = (
        min(len(left_tokens), len(right_tokens)) / maximum_length if maximum_length else 1.0
    )

    exact = bool(left_normalized) and left_normalized == right_normalized
    if exact:
        return ReportMatch(
            disposition=EdgeDisposition.CANDIDATE,
            exact=True,
            token_count_left=len(left_tokens),
            token_count_right=len(right_tokens),
            length_ratio=length_ratio,
            shingle_jaccard=1.0,
            levenshtein_similarity=1.0,
        )

    if (
        min(len(left_tokens), len(right_tokens)) < minimum_tokens
        or length_ratio < minimum_length_ratio
    ):
        return ReportMatch(
            disposition=EdgeDisposition.NONE,
            exact=False,
            token_count_left=len(left_tokens),
            token_count_right=len(right_tokens),
            length_ratio=length_ratio,
            shingle_jaccard=0.0,
            levenshtein_similarity=0.0,
        )

    left_shingles = _token_shingles(left_tokens, shingle_size)
    right_shingles = _token_shingles(right_tokens, shingle_size)
    jaccard = _jaccard(left_shingles, right_shingles)
    levenshtein = _levenshtein_similarity(left_tokens, right_tokens)
    if jaccard >= candidate_jaccard:
        disposition = EdgeDisposition.CANDIDATE
    else:
        disposition = EdgeDisposition.NONE
    return ReportMatch(
        disposition=disposition,
        exact=False,
        token_count_left=len(left_tokens),
        token_count_right=len(right_tokens),
        length_ratio=length_ratio,
        shingle_jaccard=jaccard,
        levenshtein_similarity=levenshtein,
    )


PerceptualHash = int | str


def _perceptual_hash_int(value: PerceptualHash) -> int:
    if isinstance(value, bool):
        raise ValueError("perceptual hashes must be unsigned 64-bit integers or 16-digit hex")
    if isinstance(value, str):
        if re.fullmatch(r"[0-9a-fA-F]{16}", value) is None:
            raise ValueError("perceptual hashes must be unsigned 64-bit integers or 16-digit hex")
        return int(value, 16)
    maximum = (1 << 64) - 1
    if not 0 <= value <= maximum:
        raise ValueError("perceptual hashes must be unsigned 64-bit integers or 16-digit hex")
    return value


def hamming_distance_64(left: PerceptualHash, right: PerceptualHash) -> int:
    """Return Hamming distance between two unsigned 64-bit hashes."""

    return (_perceptual_hash_int(left) ^ _perceptual_hash_int(right)).bit_count()


def _quantile_select(values: Sequence[PerceptualHash], count: int) -> tuple[PerceptualHash, ...]:
    if count == 1:
        return (values[(len(values) - 1) // 2],)
    return tuple(
        values[math.floor(index * (len(values) - 1) / (count - 1))] for index in range(count)
    )


@dataclass(frozen=True)
class SeriesHashMatch:
    """Forward/reverse perceptual-hash sequence comparison."""

    disposition: EdgeDisposition
    direction: str
    compared_slices: int
    length_ratio: float
    hard_match_count: int
    median_hamming: float
    maximum_hamming: int
    distances: tuple[int, ...]


def compare_phash_sequences(
    left: Sequence[PerceptualHash],
    right: Sequence[PerceptualHash],
    *,
    minimum_slices: int = 5,
    hard_max_hamming: int = 4,
    hard_median_hamming: float = 2.0,
    candidate_max_hamming: int = 8,
    candidate_median_hamming: float = 4.0,
    minimum_length_ratio: float = 0.90,
) -> SeriesHashMatch:
    """Compare quantile-aligned pHash sequences in both slice directions."""

    if not left or not right:
        raise ValueError("perceptual-hash sequences must be non-empty")
    if minimum_slices <= 0:
        raise ValueError("minimum_slices must be positive")
    if not 0 <= hard_max_hamming <= candidate_max_hamming <= 64:
        raise ValueError("invalid Hamming thresholds")
    if not 0.0 <= hard_median_hamming <= candidate_median_hamming <= 64.0:
        raise ValueError("invalid median Hamming thresholds")
    if not 0.0 <= minimum_length_ratio <= 1.0:
        raise ValueError("invalid sequence length-ratio threshold")

    count = min(len(left), len(right))
    length_ratio = count / max(len(left), len(right))
    left_selected = _quantile_select(left, count)
    right_selected = _quantile_select(right, count)
    forward = tuple(
        hamming_distance_64(left_value, right_value)
        for left_value, right_value in zip(left_selected, right_selected, strict=True)
    )
    reverse = tuple(
        hamming_distance_64(left_value, right_value)
        for left_value, right_value in zip(left_selected, reversed(right_selected), strict=True)
    )

    def median_distance(distances: tuple[int, ...]) -> float:
        ordered = sorted(distances)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return float(ordered[middle])
        return (ordered[middle - 1] + ordered[middle]) / 2.0

    def score(distances: tuple[int, ...], direction_rank: int) -> tuple[int, float, int, int]:
        hard_failures = sum(distance > hard_max_hamming for distance in distances)
        return (
            hard_failures,
            median_distance(distances),
            sum(distances),
            direction_rank,
        )

    if score(forward, 0) <= score(reverse, 1):
        direction = "forward"
        distances = forward
    else:
        direction = "reverse"
        distances = reverse

    median = median_distance(distances)
    hard_matches = sum(distance <= hard_max_hamming for distance in distances)
    candidate_matches = sum(distance <= candidate_max_hamming for distance in distances)
    required_matches = max(1, count - 1)
    if (
        length_ratio >= minimum_length_ratio
        and count >= minimum_slices
        and hard_matches >= required_matches
        and median <= hard_median_hamming
    ):
        disposition = EdgeDisposition.HARD
    elif (
        length_ratio >= minimum_length_ratio
        and count >= minimum_slices
        and candidate_matches >= required_matches
        and median <= candidate_median_hamming
    ):
        disposition = EdgeDisposition.CANDIDATE
    else:
        disposition = EdgeDisposition.NONE
    return SeriesHashMatch(
        disposition=disposition,
        direction=direction,
        compared_slices=count,
        length_ratio=length_ratio,
        hard_match_count=hard_matches,
        median_hamming=median,
        maximum_hamming=max(distances),
        distances=distances,
    )
