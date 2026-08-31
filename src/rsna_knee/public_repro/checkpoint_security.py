"""Static, network-free checkpoint preflight helpers.

These checks do not prove that a checkpoint is safe. They identify obvious
archive/path/pickle risks and determine whether isolated sandbox inspection is
required before deserialization.
"""

from __future__ import annotations

import hashlib
import pickletools
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


_DANGEROUS_PICKLE_OPCODES = frozenset(
    {
        "GLOBAL",
        "STACK_GLOBAL",
        "REDUCE",
        "BUILD",
        "INST",
        "OBJ",
        "NEWOBJ",
        "NEWOBJ_EX",
        "EXT1",
        "EXT2",
        "EXT4",
        "PERSID",
        "BINPERSID",
    }
)


@dataclass(frozen=True, slots=True)
class CheckpointPreflight:
    """Result of a static checkpoint inspection."""

    sha256: str
    size_bytes: int
    is_zip: bool
    member_count: int
    path_traversal_members: tuple[str, ...]
    pickle_members: tuple[str, ...]
    dangerous_pickle_opcodes: tuple[str, ...]
    oversized_members: tuple[str, ...]
    requires_sandbox: bool


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Calculate a file SHA-256 without loading the whole file into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_checkpoint_archive(
    path: str | Path,
    *,
    maximum_member_bytes: int = 4 * 1024**3,
    pickle_scan_limit_bytes: int = 64 * 1024**2,
) -> CheckpointPreflight:
    """Inspect a ZIP-based checkpoint without importing model code.

    Non-ZIP files are conservatively marked as requiring a sandbox.
    """

    checkpoint_path = Path(path)
    file_sha = sha256_file(checkpoint_path)
    size_bytes = checkpoint_path.stat().st_size
    if not zipfile.is_zipfile(checkpoint_path):
        return CheckpointPreflight(
            sha256=file_sha,
            size_bytes=size_bytes,
            is_zip=False,
            member_count=0,
            path_traversal_members=(),
            pickle_members=(),
            dangerous_pickle_opcodes=(),
            oversized_members=(),
            requires_sandbox=True,
        )

    traversal: list[str] = []
    pickle_members: list[str] = []
    dangerous: set[str] = set()
    oversized: list[str] = []

    with zipfile.ZipFile(checkpoint_path) as archive:
        members = archive.infolist()
        for info in members:
            name = info.filename
            if _is_unsafe_member(name):
                traversal.append(name)
            if info.file_size > maximum_member_bytes:
                oversized.append(name)
            if name.endswith((".pkl", ".pickle")):
                pickle_members.append(name)
                if info.file_size <= pickle_scan_limit_bytes:
                    payload = archive.read(info)
                    dangerous.update(_dangerous_pickle_opcodes(payload))
                else:
                    dangerous.add("PICKLE_TOO_LARGE_TO_SCAN")

    requires_sandbox = bool(traversal or pickle_members or dangerous or oversized)
    return CheckpointPreflight(
        sha256=file_sha,
        size_bytes=size_bytes,
        is_zip=True,
        member_count=len(members),
        path_traversal_members=tuple(sorted(traversal)),
        pickle_members=tuple(sorted(pickle_members)),
        dangerous_pickle_opcodes=tuple(sorted(dangerous)),
        oversized_members=tuple(sorted(oversized)),
        requires_sandbox=requires_sandbox,
    )


def _is_unsafe_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    return path.is_absolute() or ".." in path.parts


def _dangerous_pickle_opcodes(payload: bytes) -> Iterable[str]:
    try:
        return {
            opcode.name
            for opcode, _argument, _position in pickletools.genops(payload)
            if opcode.name in _DANGEROUS_PICKLE_OPCODES
        }
    except Exception:
        return {"MALFORMED_PICKLE"}
