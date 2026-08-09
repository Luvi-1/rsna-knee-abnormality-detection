"""Fail-closed validation for remote listings and downloaded sanitized outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, Final

MAX_POLICY_BYTES: Final = 2 * 1024 * 1024
HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
FAILURE_PHASES: Final = {"bundle", "audit", "summary"}


class OutputValidationError(RuntimeError):
    """A stable error code that never includes inspected output contents."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _runner_module(expected_sha256: str, runner_path: Path | None = None) -> ModuleType:
    if not HEX_64.fullmatch(expected_sha256):
        raise OutputValidationError("trusted_validator_unavailable")
    path = runner_path or Path(__file__).parents[1] / "kaggle" / "manifest_audit" / "run.py"
    payload = _read_bounded(path, 512 * 1024, "trusted_validator_unavailable")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise OutputValidationError("trusted_validator_hash_mismatch")
    module = ModuleType("_trusted_manifest_audit_runner")
    module.__file__ = str(path)
    try:
        exec(compile(payload, str(path), "exec"), module.__dict__)
    except Exception as error:
        raise OutputValidationError("trusted_validator_unavailable") from error
    return module


def _read_bounded(path: Path, maximum: int, code: str) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise OutputValidationError(code)
        size = path.stat().st_size
        if size <= 0 or size > maximum:
            raise OutputValidationError(code)
        with path.open("rb") as stream:
            payload = stream.read(maximum + 1)
    except OSError as error:
        raise OutputValidationError(code) from error
    if len(payload) != size:
        raise OutputValidationError(code)
    return payload


def _json_object(path: Path, maximum: int, code: str) -> dict[str, Any]:
    payload = _read_bounded(path, maximum, code)
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OutputValidationError(code) from error
    if not isinstance(decoded, dict):
        raise OutputValidationError(code)
    return decoded


def load_verified_policy(
    run_config_path: Path,
    bundle_manifest_path: Path,
    *,
    expected_commit: str | None = None,
    expected_bundle: str | None = None,
) -> tuple[dict[str, Any], ModuleType]:
    manifest = _json_object(bundle_manifest_path, MAX_POLICY_BYTES, "bundle_manifest_invalid")
    kernel = manifest.get("kernel")
    if (
        not isinstance(kernel, dict)
        or kernel.get("code_file") != "run.py"
        or not isinstance(kernel.get("sha256"), str)
        or not HEX_64.fullmatch(kernel["sha256"])
    ):
        raise OutputValidationError("bundle_manifest_invalid")
    runner = _runner_module(kernel["sha256"])
    run_config = _json_object(run_config_path, MAX_POLICY_BYTES, "run_config_invalid")
    try:
        records = runner._validated_records(bundle_manifest_path.parent, manifest)
        verified_config, verified_paths, _dependency_paths = runner._verify_run_config(
            bundle_manifest_path.parent,
            manifest,
            records,
        )
    except Exception as error:
        raise OutputValidationError("bundle_verification_failed") from error
    try:
        requested_config_path = run_config_path.resolve(strict=True)
        verified_config_path = verified_paths["run_config"].resolve(strict=True)
    except OSError as error:
        raise OutputValidationError("policy_file_unreadable") from error
    if requested_config_path != verified_config_path or run_config != verified_config:
        raise OutputValidationError("policy_provenance_invalid")
    bundle_sha256 = run_config.get("bundle_sha256")
    commit = run_config.get("code_commit")
    if (
        run_config.get("schema_version") != 1
        or not isinstance(bundle_sha256, str)
        or not HEX_64.fullmatch(bundle_sha256)
        or not isinstance(commit, str)
        or not HEX_40.fullmatch(commit)
        or manifest.get("bundle_sha256") != bundle_sha256
    ):
        raise OutputValidationError("policy_provenance_invalid")
    if expected_commit is not None and commit != expected_commit:
        raise OutputValidationError("expected_commit_mismatch")
    if expected_bundle is not None and bundle_sha256 != expected_bundle:
        raise OutputValidationError("expected_bundle_mismatch")
    provenance = run_config.get("provenance")
    privacy = run_config.get("privacy")
    if (
        not isinstance(provenance, dict)
        or provenance.get("git_commit") != commit
        or not isinstance(privacy, dict)
        or privacy.get("minimum_export_cell") != 20
        or not isinstance(privacy.get("canary"), str)
        or any(
            privacy.get(key) is not False
            for key in (
                "raw_identifiers",
                "raw_reports",
                "patient_metadata",
                "pixel_data",
                "private_tables",
            )
        )
    ):
        raise OutputValidationError("policy_privacy_invalid")
    try:
        runner._validate_output_policy(run_config.get("output_policy"))
    except Exception as error:
        raise OutputValidationError("output_policy_invalid") from error
    return run_config, runner


def _safe_remote_path(value: object) -> str:
    if not isinstance(value, str) or len(value) > 240 or "\\" in value:
        raise OutputValidationError("remote_listing_invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise OutputValidationError("remote_listing_invalid")
    if any(not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", part) for part in path.parts):
        raise OutputValidationError("remote_listing_invalid")
    return path.as_posix()


def _canonical_artifact_path(
    name: str, output_prefix: str, basenames: set[str]
) -> tuple[str, str | None]:
    if name in basenames:
        return f"{output_prefix}/{name}", "flat"
    prefix = f"{output_prefix}/"
    if name.startswith(prefix) and name.removeprefix(prefix) in basenames:
        return name, "nested"
    return name, None


def _listing_records(payload: object) -> list[dict[str, Any]]:
    records: object
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        token = payload.get("nextPageToken") or payload.get("next_page_token")
        if token:
            raise OutputValidationError("remote_listing_incomplete")
        records = payload.get("files", payload.get("data"))
    else:
        raise OutputValidationError("remote_listing_invalid")
    if not isinstance(records, list) or len(records) > 64:
        raise OutputValidationError("remote_listing_invalid")
    if any(not isinstance(record, dict) for record in records):
        raise OutputValidationError("remote_listing_invalid")
    return records


def _remote_size(record: Mapping[str, Any]) -> tuple[int, bool]:
    fields = [key for key in ("totalBytes", "bytes", "size") if key in record]
    if len(fields) != 1:
        raise OutputValidationError("remote_size_invalid")
    field = fields[0]
    value = record[field]
    if isinstance(value, str) and value.isdecimal():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise OutputValidationError("remote_size_invalid")
    # Kaggle kernel listings currently expose an opaque file identifier as `size`.
    return value, field != "size"


def validate_remote_listing(path: Path, run_config: Mapping[str, Any], runner: ModuleType) -> None:
    try:
        payload = json.loads(_read_bounded(path, MAX_POLICY_BYTES, "remote_listing_invalid"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OutputValidationError("remote_listing_invalid") from error
    records = _listing_records(payload)
    output_prefix = str(runner.OUTPUT_DIRECTORY)
    private_policy = {
        f"{output_prefix}/{name}": limits for name, limits in runner.PRIVATE_OUTPUT_POLICY.items()
    }
    downloadable_policy = {
        f"{output_prefix}/{name}": limits
        for name, limits in runner.DOWNLOADABLE_OUTPUT_POLICY.items()
    }
    required = set(private_policy) | set(downloadable_policy)
    artifact_basenames = set(runner.PRIVATE_OUTPUT_POLICY) | set(runner.DOWNLOADABLE_OUTPUT_POLICY)
    observed: set[str] = set()
    layout: str | None = None
    byte_sizes_reliable: bool | None = None
    total = 0
    log_count = 0
    for record in records:
        raw_name = _safe_remote_path(record.get("name"))
        name, record_layout = _canonical_artifact_path(raw_name, output_prefix, artifact_basenames)
        if record_layout is not None:
            if layout is not None and layout != record_layout:
                raise OutputValidationError("remote_layout_mixed")
            layout = record_layout
        size, reliable = _remote_size(record)
        if byte_sizes_reliable is not None and byte_sizes_reliable != reliable:
            raise OutputValidationError("remote_size_schema_mixed")
        byte_sizes_reliable = reliable
        if name in observed:
            raise OutputValidationError("remote_duplicate_name")
        observed.add(name)
        total += size
        if name in private_policy:
            maximum, exact = private_policy[name]
            if reliable and (size > maximum or (exact is not None and size != exact)):
                raise OutputValidationError("remote_size_invalid")
        elif name in downloadable_policy:
            if reliable and size > downloadable_policy[name][1]:
                raise OutputValidationError("remote_size_invalid")
        elif "/" not in raw_name and re.fullmatch(runner.SESSION_LOG_PATTERN, raw_name):
            log_count += 1
            if reliable and size > 2 * 1024 * 1024:
                raise OutputValidationError("remote_size_invalid")
        else:
            raise OutputValidationError("remote_name_not_allowed")
    if not required.issubset(observed) or log_count > 1:
        raise OutputValidationError("remote_required_output_missing")
    maximum_total = run_config["output_policy"]["max_remote_bytes"]
    if byte_sizes_reliable and total > maximum_total:
        raise OutputValidationError("remote_total_size_invalid")


def _validated_log_events(payload: bytes, runner: ModuleType, canary: str) -> list[dict[str, str]]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise OutputValidationError("log_encoding_invalid") from error
    try:
        runner._scan_unstructured(payload, canary)
    except Exception as error:
        raise OutputValidationError("log_privacy_invalid") from error

    lines: list[str]
    try:
        wrapper = json.loads(text)
    except json.JSONDecodeError:
        wrapper = None
    if isinstance(wrapper, list):
        if not wrapper or len(wrapper) > 10_000:
            raise OutputValidationError("log_schema_invalid")
        lines = []
        for record in wrapper:
            if (
                not isinstance(record, dict)
                or set(record) != {"stream_name", "time", "data"}
                or record.get("stream_name") not in {"stdout", "stderr"}
                or isinstance(record.get("time"), bool)
                or not isinstance(record.get("time"), (int, float))
                or record["time"] < 0
                or not isinstance(record.get("data"), str)
            ):
                raise OutputValidationError("log_schema_invalid")
            if record["stream_name"] == "stdout":
                lines.extend(line for line in record["data"].splitlines() if line)
    else:
        lines = text.splitlines()
    if not lines or len(lines) > 10_000:
        raise OutputValidationError("log_schema_invalid")
    events: list[dict[str, str]] = []
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise OutputValidationError("log_schema_invalid") from error
        if (
            not isinstance(event, dict)
            or not {"event"} <= set(event) <= {"event", "phase", "code"}
            or event.get("event")
            not in {"manifest_audit_started", "manifest_audit_complete", "manifest_audit_failed"}
            or any(
                not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value)
                for value in event.values()
            )
        ):
            raise OutputValidationError("log_schema_invalid")
        events.append({str(key): str(value) for key, value in event.items()})
    return events


def _validate_log(payload: bytes, runner: ModuleType, canary: str) -> None:
    events = _validated_log_events(payload, runner, canary)
    if events != [
        {"event": "manifest_audit_started"},
        {"event": "manifest_audit_complete"},
    ]:
        raise OutputValidationError("log_completion_invalid")


def validate_failure_log(
    root: Path, run_config: Mapping[str, Any], runner: ModuleType
) -> tuple[str, str]:
    """Validate one scrubbed failed-session log and return only fixed safe codes."""

    try:
        if root.is_symlink() or not root.is_dir():
            raise OutputValidationError("failure_log_layout_invalid")
        entries = list(root.iterdir())
    except OSError as error:
        raise OutputValidationError("failure_log_layout_invalid") from error
    if (
        len(entries) != 1
        or entries[0].is_symlink()
        or not entries[0].is_file()
        or re.fullmatch(runner.SESSION_LOG_PATTERN, entries[0].name) is None
    ):
        raise OutputValidationError("failure_log_layout_invalid")
    payload = _read_bounded(entries[0], 2 * 1024 * 1024, "failure_log_size_invalid")
    events = _validated_log_events(payload, runner, str(run_config["privacy"]["canary"]))
    if (
        len(events) != 2
        or events[0] != {"event": "manifest_audit_started"}
        or set(events[1]) != {"event", "phase", "code"}
        or events[1]["event"] != "manifest_audit_failed"
        or events[1]["phase"] not in FAILURE_PHASES
    ):
        raise OutputValidationError("failure_log_completion_invalid")
    return events[1]["phase"], events[1]["code"]


def validate_local_output(
    root: Path,
    run_config: Mapping[str, Any],
    runner: ModuleType,
    *,
    allow_bounded_smoke: bool = False,
) -> None:
    if root.is_symlink() or not root.is_dir():
        raise OutputValidationError("local_output_invalid")
    try:
        entries = sorted(root.rglob("*"), key=lambda item: item.as_posix())
    except OSError as error:
        raise OutputValidationError("local_output_invalid") from error
    if any(entry.is_symlink() for entry in entries):
        raise OutputValidationError("local_symlink_forbidden")
    files = [entry for entry in entries if entry.is_file()]
    raw_relative = {entry: entry.relative_to(root).as_posix() for entry in files}
    downloadable = {
        f"{runner.OUTPUT_DIRECTORY}/{name}": policy
        for name, policy in runner.DOWNLOADABLE_OUTPUT_POLICY.items()
    }
    artifact_basenames = set(runner.PRIVATE_OUTPUT_POLICY) | set(runner.DOWNLOADABLE_OUTPUT_POLICY)
    relative: dict[Path, str] = {}
    layouts: set[str] = set()
    for entry, raw_name in raw_relative.items():
        name, layout = _canonical_artifact_path(
            _safe_remote_path(raw_name), str(runner.OUTPUT_DIRECTORY), artifact_basenames
        )
        relative[entry] = name
        if layout is not None:
            layouts.add(layout)
    if len(layouts) > 1:
        raise OutputValidationError("local_layout_mixed")
    allowed_directories = {root / runner.OUTPUT_DIRECTORY} if layouts == {"nested"} else set()
    directories = {entry for entry in entries if entry.is_dir()}
    if directories != allowed_directories:
        raise OutputValidationError("local_directory_not_allowed")
    required = set(downloadable)
    observed = set(relative.values())
    logs = [
        entry
        for entry, name in raw_relative.items()
        if "/" not in name and re.fullmatch(runner.SESSION_LOG_PATTERN, name)
    ]
    unknown = observed - required - {raw_relative[entry] for entry in logs}
    if unknown:
        private_names = {
            f"{runner.OUTPUT_DIRECTORY}/{name}" for name in runner.PRIVATE_OUTPUT_POLICY
        }
        code = (
            "private_artifact_downloaded" if unknown & private_names else "local_file_not_allowed"
        )
        raise OutputValidationError(code)
    if not required.issubset(observed) or len(logs) != 1:
        raise OutputValidationError("local_required_output_missing")
    total = 0
    payloads: dict[str, bytes] = {}
    for entry, name in relative.items():
        if name in downloadable:
            payload = _read_bounded(entry, downloadable[name][1], "local_size_invalid")
        else:
            payload = _read_bounded(entry, 2 * 1024 * 1024, "local_size_invalid")
        payloads[name] = payload
        total += len(payload)
    if total > run_config["output_policy"]["max_download_bytes"]:
        raise OutputValidationError("local_total_size_invalid")

    canary = str(run_config["privacy"]["canary"])
    summary_name = f"{runner.OUTPUT_DIRECTORY}/sanitized_summary.json"
    try:
        summary = json.loads(payloads[summary_name])
        runner._validated_summary(summary, run_config)
    except Exception as error:
        raise OutputValidationError("summary_validation_failed") from error
    mode = summary["aggregates"]["scope"]["mode"]
    max_files = run_config.get("max_files")
    if allow_bounded_smoke:
        if (
            mode != "bounded"
            or isinstance(max_files, bool)
            or not isinstance(max_files, int)
            or max_files <= 0
        ):
            raise OutputValidationError("bounded_smoke_not_verified")
    elif mode != "full" or max_files is not None:
        raise OutputValidationError("full_scan_not_verified")

    documents: dict[str, bytes] = {}
    for name in runner.DOCUMENT_HEADINGS:
        relative_name = f"{runner.OUTPUT_DIRECTORY}/{name}"
        payload = payloads[relative_name]
        try:
            runner._validate_document(name, payload, run_config, summary["aggregates"])
        except Exception as error:
            raise OutputValidationError("documentation_validation_failed") from error
        documents[name] = payload
    try:
        expected_documents = runner._render_disclosed_documents(
            summary["aggregates"], canary=canary
        )
    except Exception as error:
        raise OutputValidationError("documentation_validation_failed") from error
    if documents != expected_documents:
        raise OutputValidationError("documentation_cross_file_mismatch")
    inventory_name = f"{runner.OUTPUT_DIRECTORY}/sanitized_artifact_inventory.json"
    try:
        runner._validate_sanitized_inventory(
            payloads[inventory_name],
            run_config=run_config,
            documents=documents,
        )
    except Exception as error:
        raise OutputValidationError("sanitized_inventory_validation_failed") from error
    for log in logs:
        _validate_log(payloads[relative[log]], runner, canary)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-config", type=Path, required=True)
    parser.add_argument("--bundle-manifest", type=Path)
    parser.add_argument("--expected-commit")
    parser.add_argument("--expected-bundle")
    parser.add_argument("--allow-bounded-smoke", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--remote-listing", type=Path)
    mode.add_argument("--local-dir", type=Path)
    mode.add_argument("--failure-log-dir", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest_path = args.bundle_manifest or args.run_config.with_name("bundle-manifest.json")
    try:
        run_config, runner = load_verified_policy(
            args.run_config,
            manifest_path,
            expected_commit=args.expected_commit,
            expected_bundle=args.expected_bundle,
        )
        failure: tuple[str, str] | None = None
        if args.remote_listing is not None:
            validate_remote_listing(args.remote_listing, run_config, runner)
            mode = "remote"
        elif args.failure_log_dir is not None:
            failure = validate_failure_log(args.failure_log_dir, run_config, runner)
            mode = "failure"
        else:
            validate_local_output(
                args.local_dir,
                run_config,
                runner,
                allow_bounded_smoke=args.allow_bounded_smoke,
            )
            mode = "local"
    except OutputValidationError as error:
        print(f"manifest_output_validation=FAIL code={error.code}")
        return 2
    except Exception:
        print("manifest_output_validation=FAIL code=internal_error")
        return 2
    suffix = "" if failure is None else f" phase={failure[0]} code={failure[1]}"
    print(f"manifest_output_validation=PASS mode={mode}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
