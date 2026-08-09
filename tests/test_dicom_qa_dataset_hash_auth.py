from __future__ import annotations

import hashlib
import importlib.util
import os
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]


def _load_validator() -> Any:
    name = "_dicom_qa_dataset_hash_validator"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts/validate_dicom_qa_output.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


validator = _load_validator()


def _policy(payloads: dict[str, bytes]) -> dict[str, tuple[int, str]]:
    return {
        name: (len(payload), hashlib.sha256(payload).hexdigest())
        for name, payload in payloads.items()
    }


def test_verified_bundle_policies_retain_every_size_and_digest() -> None:
    payload = b'{"bundle":"synthetic"}\n'
    digest = hashlib.sha256(payload).hexdigest()
    manifest = {
        "schema_version": 1,
        "files": [
            {
                "path": "run-config.json",
                "bytes": len(payload),
                "sha256": digest,
                "role": "run_config",
            }
        ],
    }
    manifest_payload = validator._canonical_json_bytes(manifest)
    expected = {
        "run-config.json": (len(payload), digest),
        "bundle-manifest.json": (
            len(manifest_payload),
            hashlib.sha256(manifest_payload).hexdigest(),
        ),
    }
    source = {
        "bundle_dataset_files": [
            {"name": name, "bytes": size, "sha256": sha256}
            for name, (size, sha256) in expected.items()
        ]
    }

    assert validator._bundle_dataset_content_policy(manifest) == expected
    assert validator._source_manifest_dataset_content_policy(source) == expected


def test_exact_versioned_dataset_files_are_downloaded_and_hashed_without_output_retrieval(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ref = "test-owner/private-code-bundle"
    payloads = {
        "bundle-manifest.json": b'{"schema_version":1}\n',
        "run-config.json": b'{"bundle":"synthetic"}\n',
    }
    calls: list[tuple[str, ...]] = []

    def fake_cli(arguments: tuple[str, ...], **kwargs: object) -> bytes:
        calls.append(arguments)
        assert kwargs["allow_empty"] is True
        assert kwargs["maximum"] == 64 * 1024
        timeout = kwargs["timeout_seconds"]
        assert isinstance(timeout, (int, float)) and not isinstance(timeout, bool)
        assert 0 < timeout <= 300.0
        assert arguments[:3] == ("datasets", "download", f"{ref}/1")
        assert arguments[-2:] == ("--force", "--quiet")
        name = arguments[arguments.index("--file") + 1]
        root = Path(arguments[arguments.index("--path") + 1])
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        (root / name).write_bytes(payloads[name])
        return b"captured but never printed"

    monkeypatch.setattr(validator, "_run_kaggle_cli", fake_cli)

    validator._authenticate_dataset_content(ref, _policy(payloads))

    assert capsys.readouterr() == ("", "")
    assert len(calls) == len(payloads)
    assert {call[call.index("--file") + 1] for call in calls} == set(payloads)
    assert all(call[:2] == ("datasets", "download") for call in calls)
    assert all("output" not in call for call in calls)


def test_same_size_uploaded_mutation_fails_hash_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ref = "test-owner/private-code-bundle"
    expected = b"expected"
    mutated = b"mutated!"
    assert len(expected) == len(mutated)

    def fake_cli(arguments: tuple[str, ...], **_kwargs: object) -> bytes:
        root = Path(arguments[arguments.index("--path") + 1])
        name = arguments[arguments.index("--file") + 1]
        (root / name).write_bytes(mutated)
        return b""

    monkeypatch.setattr(validator, "_run_kaggle_cli", fake_cli)

    with pytest.raises(
        validator.OutputValidationError, match=r"\Adataset_download_hash_mismatch\Z"
    ):
        validator._authenticate_dataset_content(
            ref,
            _policy({"bundle-manifest.json": expected}),
        )


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra", "symlink", "path_escape"],
)
def test_download_layout_rejects_missing_extra_symlink_or_path_escape(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    ref = "test-owner/private-code-bundle"
    payload = b"synthetic code bundle"

    def fake_cli(arguments: tuple[str, ...], **_kwargs: object) -> bytes:
        root = Path(arguments[arguments.index("--path") + 1])
        name = arguments[arguments.index("--file") + 1]
        if mutation == "missing":
            return b""
        if mutation == "symlink":
            os.symlink("/dev/null", root / name)
            return b""
        (root / name).write_bytes(payload)
        if mutation == "extra":
            (root / "unexpected.bin").write_bytes(b"unexpected")
        elif mutation == "path_escape":
            (root.parent / "escaped.bin").write_bytes(b"escaped")
        return b""

    monkeypatch.setattr(validator, "_run_kaggle_cli", fake_cli)

    with pytest.raises(
        validator.OutputValidationError, match=r"\Adataset_download_layout_invalid\Z"
    ):
        validator._authenticate_dataset_content(
            ref,
            _policy({"bundle-manifest.json": payload}),
        )


def test_untrusted_expected_path_is_rejected_before_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_cli(_arguments: tuple[str, ...], **_kwargs: object) -> bytes:
        nonlocal called
        called = True
        return b""

    monkeypatch.setattr(validator, "_run_kaggle_cli", fake_cli)

    with pytest.raises(
        validator.OutputValidationError, match=r"\Adataset_content_policy_invalid\Z"
    ):
        validator._authenticate_dataset_content(
            "test-owner/private-code-bundle",
            {"../escaped.bin": (1, hashlib.sha256(b"x").hexdigest())},
        )
    assert called is False


def test_base_and_source_code_bundles_are_hashed_between_source_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_ref = "test-owner/private-base-bundle"
    source_ref = "test-owner/private-source-bundle"
    # Each producer-valid bundle is bounded independently; their combined size may exceed 128 MiB.
    base_policy = {"bundle-manifest.json": (100 * 1024**2, "a" * 64)}
    source_policy = {"bundle-manifest.json": (60 * 1024**2, "b" * 64)}
    source = {
        "kernel_ref": "test-owner/private-source-kernel",
        "kernel_version": 1,
        "kernel_code_file": "run.py",
        "kernel_code_sha256": "a" * 64,
        "bundle_dataset_ref": source_ref,
        "bundle_dataset_files": [
            {"name": name, "bytes": size, "sha256": digest}
            for name, (size, digest) in source_policy.items()
        ],
    }
    events: list[tuple[str, str]] = []

    def fake_snapshot(ref: str, _files: dict[str, int]) -> dict[str, object]:
        events.append(("snapshot", ref))
        return {"dataset_id": 1, "files": ()}

    def fake_content(
        ref: str,
        _files: dict[str, tuple[int, str]],
        *,
        deadline: float,
    ) -> None:
        assert deadline > 0
        events.append(("content", ref))

    monkeypatch.setattr(validator, "_authenticated_dataset_snapshot", fake_snapshot)
    monkeypatch.setattr(validator, "_authenticate_dataset_content", fake_content)
    monkeypatch.setattr(validator, "_assert_version_absent", lambda *_args: None)
    monkeypatch.setattr(validator, "_kernel_status_complete", lambda *_args: None)
    monkeypatch.setattr(validator, "_authenticated_listing", lambda *_args: ())
    monkeypatch.setattr(validator, "_validate_source_manifest_listing", lambda *_args: None)
    monkeypatch.setattr(
        validator,
        "_pull_and_verify_exact_kernel",
        lambda *_args, **_kwargs: {"authenticated": True},
    )

    validator._authenticate_source_manifest_kernel(
        source=source,
        competition_slug="synthetic-competition",
        bundle_dataset_ref=base_ref,
        bundle_dataset_content=base_policy,
    )

    assert events == [
        ("snapshot", source_ref),
        ("content", base_ref),
        ("content", source_ref),
        ("snapshot", source_ref),
    ]
