from __future__ import annotations

import json
import re
import zipfile
from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree

from case_agent_demo.models import Material, MaterialType


VAULT_SUBDIRS = ("statements", "report_images", "identification_images", "extracted")
STATEMENT_EXTENSIONS = {".txt", ".docx", ".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


@dataclass(frozen=True)
class EvidenceRecord:
    material_id: str
    material_type: str
    source_path: str
    extracted_path: str
    extraction_status: str
    requires_external_vision: bool


def ensure_evidence_vault(root: str | Path) -> Path:
    vault_root = Path(root)
    vault_root.mkdir(parents=True, exist_ok=True)
    for subdir in VAULT_SUBDIRS:
        (vault_root / subdir).mkdir(parents=True, exist_ok=True)
    manifest_path = vault_root / "manifest.json"
    if not manifest_path.exists():
        _write_manifest(manifest_path, [])
    return vault_root


class EvidenceIntake:
    def __init__(self, root: str | Path) -> None:
        self.root = ensure_evidence_vault(root)

    def load_materials(self) -> list[Material]:
        records: list[EvidenceRecord] = []
        materials: list[Material] = []

        for path in self._iter_files(self.root / "statements", STATEMENT_EXTENSIONS):
            material, record = self._load_statement(path)
            materials.append(material)
            records.append(record)

        for path in self._iter_files(self.root / "report_images", IMAGE_EXTENSIONS):
            material, record = self._load_image(path, MaterialType.REPORT_IMAGE, "R")
            materials.append(material)
            records.append(record)

        for path in self._iter_files(self.root / "identification_images", IMAGE_EXTENSIONS):
            material, record = self._load_image(path, MaterialType.EVIDENCE_IMAGE, "P")
            materials.append(material)
            records.append(record)

        _write_manifest(self.root / "manifest.json", records)
        return materials

    def _iter_files(self, directory: Path, extensions: set[str]) -> Iterable[Path]:
        return sorted(
            path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in extensions
        )

    def _load_statement(self, path: Path) -> tuple[Material, EvidenceRecord]:
        material_id = f"S-{_safe_stem(path)}"
        extracted = self._extracted_text(path)
        if extracted is not None:
            content = extracted
            status = "extracted_override"
            extracted_path = str(self._extracted_path(path))
        elif path.suffix.lower() == ".txt":
            content = _clean_text(path.read_text(encoding="utf-8"))
            status = "text_extracted"
            extracted_path = ""
        elif path.suffix.lower() == ".docx":
            content = _clean_text(_extract_docx_text(path))
            status = "text_extracted" if content.strip() else "empty"
            extracted_path = ""
        else:
            content = _clean_text(_extract_pdf_text(path))
            status = "text_extracted" if not content.startswith("PDF笔录待文本提取") else "needs_text_extraction"
            extracted_path = ""
        return (
            Material(material_id, MaterialType.STATEMENT, content.strip(), source_path=str(path)),
            EvidenceRecord(
                material_id=material_id,
                material_type=MaterialType.STATEMENT.value,
                source_path=str(path),
                extracted_path=extracted_path,
                extraction_status=status,
                requires_external_vision=False,
            ),
        )

    def _load_image(
        self, path: Path, material_type: MaterialType, prefix: str
    ) -> tuple[Material, EvidenceRecord]:
        material_id = f"{prefix}-{_safe_stem(path)}"
        extracted = self._extracted_text(path)
        if extracted is None:
            content = f"待外部 Qwen 识别：{path}"
            status = "needs_external_qwen"
            extracted_path = ""
        else:
            content = extracted
            status = "extracted_override"
            extracted_path = str(self._extracted_path(path))
        return (
            Material(material_id, material_type, content.strip(), source_path=str(path)),
            EvidenceRecord(
                material_id=material_id,
                material_type=material_type.value,
                source_path=str(path),
                extracted_path=extracted_path,
                extraction_status=status,
                requires_external_vision=True,
            ),
        )

    def _extracted_path(self, source_path: Path) -> Path:
        return self.root / "extracted" / f"{source_path.stem}.txt"

    def _extracted_text(self, source_path: Path) -> str | None:
        extracted_path = self._extracted_path(source_path)
        if not extracted_path.exists():
            return None
        text = _clean_text(extracted_path.read_text(encoding="utf-8"))
        return text or None


def _safe_stem(path: Path) -> str:
    return re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", path.stem).strip("_") or "material"


def _clean_text(text: str) -> str:
    return text.replace("\ufeff", "").strip()


def _write_manifest(path: Path, records: list[EvidenceRecord]) -> None:
    data = {
        "version": 1,
        "records": [asdict(record) for record in records],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    texts = [node.text or "" for node in root.findall(".//w:t", namespace)]
    return unescape("\n".join(item for item in texts if item))


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return f"PDF笔录待文本提取：{path}。请安装 pypdf/PyPDF2，或将提取文本写入 extracted/{path.stem}.txt。"
    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    text = "\n".join(page.strip() for page in pages if page.strip())
    return text or f"PDF笔录未提取到文本：{path}。请将文本写入 extracted/{path.stem}.txt。"
