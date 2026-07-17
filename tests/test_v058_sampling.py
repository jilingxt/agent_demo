from __future__ import annotations

import json
from pathlib import Path

from scripts.sample_v058_provisions import sample_provisions


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "legal_knowledge" / "index" / "legal_kb.sqlite3"


def _articles(manifest: dict[str, object], law_key: str) -> list[str]:
    accepted = manifest["accepted"]
    assert isinstance(accepted, dict)
    provisions = accepted[law_key]
    assert isinstance(provisions, list)
    return [str(item["article"]) for item in provisions]


def test_seed_58_reproduces_approved_ten_provision_sample() -> None:
    manifest = sample_provisions(DATABASE, seed=58)

    assert _articles(manifest, "criminal_law") == [
        "第三百五十三条",
        "第一百八十五条",
        "第一百八十九条",
        "第四百二十九条",
        "第一百八十六条",
    ]
    assert _articles(manifest, "public_security_law") == [
        "第五十一条",
        "第五十二条",
        "第三十一条",
        "第五十条",
        "第八十三条",
    ]


def test_sampling_manifest_records_the_rejected_penalty_provision() -> None:
    manifest = sample_provisions(DATABASE, seed=58)

    assert manifest["rejected"] == [
        {
            "law": "criminal_law",
            "article": "第三百八十三条",
            "reason": "pure_penalty_provision",
            "replacement": "第一百八十六条",
        }
    ]


def test_sampling_manifest_is_canonically_reproducible() -> None:
    first = sample_provisions(DATABASE, seed=58)
    second = sample_provisions(DATABASE, seed=58)

    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second,
        ensure_ascii=False,
        sort_keys=True,
    )
    assert first["pool_sizes"] == {
        "criminal_law": 402,
        "public_security_law": 64,
    }


def test_project_database_path_is_canonical_for_absolute_and_relative_inputs(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)

    absolute = sample_provisions(DATABASE, seed=58)
    relative = sample_provisions(DATABASE.relative_to(ROOT), seed=58)

    assert absolute == relative
    assert absolute["database"] == "legal_knowledge/index/legal_kb.sqlite3"
