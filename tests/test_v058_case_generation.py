from __future__ import annotations

import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageStat

from scripts.generate_v058_cases import generate_corpus
from scripts.v058_case_catalog import SYNTHETIC_BANNER


ROOT = Path(__file__).resolve().parents[1]


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    return re.sub(r"<[^>]+>", "", xml)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_generator_creates_five_cases_per_law(tmp_path: Path) -> None:
    cases = generate_corpus(tmp_path)

    assert len(cases) == 10
    assert len([path for path in cases if path.name.startswith("CR-")]) == 5
    assert len([path for path in cases if path.name.startswith("PS-")]) == 5
    assert (tmp_path / "sampling_manifest.json").is_file()


def test_every_case_has_complete_material_and_expected_contracts(tmp_path: Path) -> None:
    for case_dir in generate_corpus(tmp_path):
        assert (case_dir / "case.json").is_file()
        assert (case_dir / "sampling.json").is_file()
        statements = list((case_dir / "statements").glob("*.docx"))
        reports = list((case_dir / "reports").glob("*.docx"))
        report_images = list((case_dir / "report_images").glob("*.png"))
        assert len(statements) >= 2
        assert reports
        assert report_images
        assert (case_dir / "expected" / "semantic_assertions.json").is_file()
        assert (case_dir / "expected" / "expected_outcome.json").is_file()

        for document in [*statements, *reports]:
            assert SYNTHETIC_BANNER in _docx_text(document)

        semantic = _json(case_dir / "expected" / "semantic_assertions.json")
        outcome = _json(case_dir / "expected" / "expected_outcome.json")
        assert semantic["case_id"] == outcome["case_id"]
        assert semantic["assertions"]
        assert outcome["required_claims"]
        assert outcome["forbidden_final_conclusions"]


def test_generated_report_images_are_nonblank_and_a4_like(tmp_path: Path) -> None:
    for case_dir in generate_corpus(tmp_path):
        for image_path in (case_dir / "report_images").glob("*.png"):
            with Image.open(image_path) as image:
                assert image.width >= 1200
                assert image.height >= 1600
                assert image.height > image.width
                grayscale = image.convert("L")
                extrema = ImageStat.Stat(grayscale).extrema[0]
                assert extrema[1] - extrema[0] >= 100


def test_generated_case_text_rejects_realistic_identifiers(tmp_path: Path) -> None:
    citizen_id = re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")
    mobile = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")

    for case_dir in generate_corpus(tmp_path):
        payloads = [
            path.read_text(encoding="utf-8")
            for path in case_dir.rglob("*.json")
        ]
        payloads.extend(_docx_text(path) for path in case_dir.rglob("*.docx"))
        combined = "\n".join(payloads)
        assert SYNTHETIC_BANNER in combined
        assert citizen_id.search(combined) is None
        assert mobile.search(combined) is None
        assert "司法鉴定中心" not in combined
        assert "公安局" not in combined


def test_corpus_exercises_all_approved_complexity_types(tmp_path: Path) -> None:
    complexity_types = {
        str(_json(case_dir / "case.json")["complexity_type"])
        for case_dir in generate_corpus(tmp_path)
    }

    assert complexity_types >= {
        "direct_denial",
        "business_authorization_dispute",
        "evidence_insufficient",
        "non_offense_context",
        "partial_admission",
        "full_admission",
        "alternative_explanation",
        "ordinary_activity_dispute",
        "actor_attribution_dispute",
        "statutory_exception",
    }


def test_generator_script_runs_directly_from_project_root(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_v058_cases.py"),
            "--output",
            str(tmp_path / "corpus"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert len(list((tmp_path / "corpus").glob("CR-*"))) == 5
    assert len(list((tmp_path / "corpus").glob("PS-*"))) == 5
