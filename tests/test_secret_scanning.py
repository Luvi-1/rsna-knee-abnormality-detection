from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from shutil import copyfile

ROOT = Path(__file__).resolve().parents[1]
HOOK = Path(sys.executable).with_name("detect-secrets-hook")
SCAN = Path(sys.executable).with_name("detect-secrets")
CONTRACT_PATH = "docs/competition_contract/contract.yaml"
SUMMARY_PATH = "docs/manifest_summary.json"
CERTIFICATE_TEST_PATH = "tests/test_core_execution_certificate.py"
REVIEW_PATH = "kaggle/dicom_qa/on_demand_review.py"


def run_hook(checkout: Path, *filenames: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(HOOK), "--baseline", ".secrets.baseline", *filenames],
        cwd=checkout,
        check=False,
        capture_output=True,
        text=True,
    )


def isolated_checkout(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "competition_contract").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "kaggle" / "dicom_qa").mkdir(parents=True)
    copyfile(ROOT / ".secrets.baseline", tmp_path / ".secrets.baseline")
    copyfile(
        ROOT / "docs/competition_contract/contract.yaml",
        tmp_path / "docs/competition_contract/contract.yaml",
    )
    copyfile(ROOT / SUMMARY_PATH, tmp_path / SUMMARY_PATH)
    copyfile(ROOT / CERTIFICATE_TEST_PATH, tmp_path / CERTIFICATE_TEST_PATH)
    copyfile(ROOT / REVIEW_PATH, tmp_path / REVIEW_PATH)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", ".secrets.baseline"], cwd=tmp_path, check=True)
    return tmp_path


def test_reviewed_provenance_hashes_are_exactly_baselined(tmp_path: Path) -> None:
    checkout = isolated_checkout(tmp_path)
    baseline = json.loads((checkout / ".secrets.baseline").read_text())
    settings_only = {**baseline, "results": {}}
    (checkout / ".scan-settings.json").write_text(
        json.dumps(settings_only, indent=2, sort_keys=True) + "\n"
    )
    scan = subprocess.run(
        [
            str(SCAN),
            "scan",
            "--baseline",
            ".scan-settings.json",
            "--no-verify",
            CONTRACT_PATH,
            SUMMARY_PATH,
            CERTIFICATE_TEST_PATH,
            REVIEW_PATH,
        ],
        cwd=checkout,
        check=False,
        capture_output=True,
        text=True,
    )

    assert scan.returncode == 0, scan.stderr
    observed = json.loads((checkout / ".scan-settings.json").read_text())
    assert set(baseline["results"]) == {
        CONTRACT_PATH,
        SUMMARY_PATH,
        CERTIFICATE_TEST_PATH,
        REVIEW_PATH,
    }
    assert len(baseline["results"][CONTRACT_PATH]) == 10
    assert len(baseline["results"][SUMMARY_PATH]) == 5
    assert len(baseline["results"][CERTIFICATE_TEST_PATH]) == 5
    assert observed["results"] == baseline["results"]

    result = run_hook(checkout, CONTRACT_PATH, SUMMARY_PATH, CERTIFICATE_TEST_PATH)

    assert result.returncode == 0, result.stdout + result.stderr


def test_realistic_unbaselined_token_is_rejected(tmp_path: Path) -> None:
    checkout = isolated_checkout(tmp_path)
    candidate_value = "ghp_" + "A" * 36
    candidate = checkout / "docs/competition_contract/contract.yaml"
    payload = json.loads(candidate.read_text())
    payload["data"]["description_fingerprint"] = candidate_value
    candidate.write_text(json.dumps(payload, separators=(",", ":")) + "\n")

    result = run_hook(checkout, "docs/competition_contract/contract.yaml")
    output = result.stdout + result.stderr

    assert result.returncode == 1
    assert "GitHub Token" in output
    assert candidate_value not in output
