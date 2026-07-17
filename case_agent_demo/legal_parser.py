from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_NUMBER = r"[一二三四五六七八九十百千万零〇两0-9]+"
_ARTICLE_RE = re.compile(rf"^\s*(第{_NUMBER}条(?:之{_NUMBER})?)(?:\s+(.*))?$")
_PART_RE = re.compile(rf"^\s*(第{_NUMBER}编\s*[^\n]*)$")
_CHAPTER_RE = re.compile(rf"^\s*(第{_NUMBER}章\s*[^\n]*)$")
_SECTION_RE = re.compile(rf"^\s*(第{_NUMBER}节\s*[^\n]*)$")


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str


@dataclass(frozen=True)
class ParsedLegalArticle:
    article: str
    text: str
    page_start: int
    page_end: int
    part: str = ""
    chapter: str = ""
    section: str = ""


def load_pdf_pages(path: str | Path) -> list[PageText]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF入库需要安装 pypdf：pip install 'case-agent-demo[rag]'") from exc

    pages = [
        PageText(index, _normalize_text(page.extract_text() or ""))
        for index, page in enumerate(PdfReader(str(path)).pages, start=1)
    ]
    if not pages or not any(page.text.strip() for page in pages):
        raise ValueError(f"PDF没有可用文本层，需要先OCR：{path}")
    return pages


def parse_legal_pages(pages: list[PageText]) -> list[ParsedLegalArticle]:
    articles: list[ParsedLegalArticle] = []
    current_lines: list[str] = []
    current_article = ""
    current_start = 0
    current_end = 0
    part = ""
    chapter = ""
    section = ""
    article_part = ""
    article_chapter = ""
    article_section = ""

    def finish() -> None:
        nonlocal current_lines
        if not current_article:
            return
        articles.append(
            ParsedLegalArticle(
                article=current_article,
                text="\n".join(current_lines).strip(),
                page_start=current_start,
                page_end=current_end,
                part=article_part,
                chapter=article_chapter,
                section=article_section,
            )
        )
        current_lines = []

    for page in pages:
        for raw_line in page.text.splitlines():
            line = _normalize_line(raw_line)
            if not line:
                continue
            if _PART_RE.match(line):
                part = _format_heading(line, "编")
                chapter = ""
                section = ""
                continue
            if _CHAPTER_RE.match(line):
                chapter = _format_heading(line, "章")
                section = ""
                continue
            if _SECTION_RE.match(line):
                section = _format_heading(line, "节")
                continue
            match = _ARTICLE_RE.match(line)
            if match:
                finish()
                current_article = match.group(1)
                current_start = page.page_number
                current_end = page.page_number
                article_part = part
                article_chapter = chapter
                article_section = section
                current_lines = [f"{current_article} {match.group(2) or ''}".strip()]
            elif current_article:
                current_lines.append(line)
                current_end = page.page_number
    finish()
    unique: dict[str, ParsedLegalArticle] = {}
    for item in articles:
        current = unique.get(item.article)
        if current is None or len(item.text) > len(current.text):
            unique[item.article] = item
    return list(unique.values())


def read_legal_source(path: str | Path) -> tuple[str, list[PageText]]:
    source = Path(path)
    if source.suffix.lower() == ".pdf":
        pages = load_pdf_pages(source)
        return "\n".join(page.text for page in pages), pages
    text = source.read_text(encoding="utf-8-sig")
    return text, [PageText(1, text)]


def _normalize_text(text: str) -> str:
    return text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")


def _normalize_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    article = re.match(rf"^(第{_NUMBER}条)\s*(之{_NUMBER})?\s+(.*)$", line)
    if article:
        article_number = f"{article.group(1)}{article.group(2) or ''}"
        return f"{article_number} {_remove_chinese_spaces(article.group(3))}"
    return _remove_chinese_spaces(line)


def _remove_chinese_spaces(text: str) -> str:
    return re.sub(r"(?<=[\u4e00-\u9fff]) (?=[\u4e00-\u9fff])", "", text)


def _format_heading(line: str, marker: str) -> str:
    return re.sub(rf"^(第{_NUMBER}{marker})(.*)$", r"\1 \2", line).strip()
