from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_documents_declare_v058_without_erasing_history():
    assert 'version = "0.58.0"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for name in ("README.md", "项目介绍.md", "技术手册.md", "用户手册.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "v0.51" in text
        assert "v0.56" in text
        assert "v0.58" in text


def test_v058_validation_document_names_the_approved_sample_and_boundaries():
    text = (ROOT / "docs" / "V058_TEN_CASE_VALIDATION.md").read_text(encoding="utf-8")
    for article in (
        "第三百五十三条",
        "第一百八十五条",
        "第一百八十九条",
        "第四百二十九条",
        "第一百八十六条",
        "第五十一条",
        "第五十二条",
        "第三十一条",
        "第五十条",
        "第八十三条",
    ):
        assert article in text
    assert "不是事实概率" in text
    assert "关键词兜底" in text
