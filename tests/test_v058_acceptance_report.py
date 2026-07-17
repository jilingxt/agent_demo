import hashlib
import json
from pathlib import Path
import subprocess
import sys

from scripts.build_v058_acceptance_report import build_report, write_report
from tests.v058_case_helpers import CORPUS_ROOT


ROOT = Path(__file__).resolve().parents[1]


def test_report_script_can_run_directly():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_v058_acceptance_report.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_acceptance_report_covers_all_ten_cases(tmp_path):
    report = build_report(corpus_root=CORPUS_ROOT)

    assert report["version"] == "0.58.0"
    assert report["sampling"]["seed"] == 58
    assert len(report["cases"]) == 10
    assert all(item["deterministic_status"] == "passed" for item in report["cases"])
    assert all(item["material_hashes"] for item in report["cases"])
    assert all(item["claim_assessments"] for item in report["cases"])
    assert all("model_versions" in item for item in report["cases"])
    assert all("parameter_hashes" in item for item in report["cases"])


def test_report_material_hashes_match_corpus_and_write_both_formats(tmp_path):
    report = build_report(corpus_root=CORPUS_ROOT)
    first = report["cases"][0]
    first_case = next(path for path in CORPUS_ROOT.iterdir() if path.name == first["directory"])
    relative_path, digest = next(iter(first["material_hashes"].items()))

    assert hashlib.sha256((first_case / relative_path).read_bytes()).hexdigest() == digest

    json_path, markdown_path = write_report(report, tmp_path)
    assert json.loads(json_path.read_text(encoding="utf-8"))["version"] == "0.58.0"
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "v0.58" in markdown
    assert "10" in markdown
