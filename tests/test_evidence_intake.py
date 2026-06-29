import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from case_agent_demo.evidence_intake import EvidenceIntake, ensure_evidence_vault
from case_agent_demo.models import MaterialType


def write_minimal_docx(path: Path, text: str) -> None:
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>"
        f"{text}"
        "</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)


class EvidenceIntakeTests(unittest.TestCase):
    def test_creates_expected_evidence_vault_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evidence_vault"

            ensure_evidence_vault(root)

            self.assertTrue((root / "statements").is_dir())
            self.assertTrue((root / "report_images").is_dir())
            self.assertTrue((root / "identification_images").is_dir())
            self.assertTrue((root / "extracted").is_dir())
            self.assertTrue((root / "manifest.json").exists())

    def test_loads_statement_text_docx_and_image_extracted_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evidence_vault"
            ensure_evidence_vault(root)
            (root / "statements" / "S1.txt").write_text("张三称20时在家。", encoding="utf-8")
            write_minimal_docx(root / "statements" / "S2.docx", "李四称20时看见张三在现场。")
            (root / "report_images" / "R1.png").write_bytes(b"not-a-real-image")
            (root / "identification_images" / "P1.jpg").write_bytes(b"not-a-real-image")
            (root / "extracted" / "R1.txt").write_text(
                "监控研判报告：20时05分张三出现在现场附近。签章清晰。", encoding="utf-8"
            )
            (root / "extracted" / "P1.txt").write_text("现场照片显示一名男子和被损坏门锁。", encoding="utf-8")

            intake = EvidenceIntake(root)
            materials = intake.load_materials()
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

            by_id = {item.material_id: item for item in materials}
            self.assertEqual(by_id["S-S1"].material_type, MaterialType.STATEMENT)
            self.assertEqual(by_id["S-S2"].material_type, MaterialType.STATEMENT)
            self.assertIn("李四称20时看见张三在现场", by_id["S-S2"].content)
            self.assertEqual(by_id["R-R1"].material_type, MaterialType.REPORT_IMAGE)
            self.assertIn("监控研判报告", by_id["R-R1"].content)
            self.assertEqual(by_id["P-P1"].material_type, MaterialType.EVIDENCE_IMAGE)
            self.assertIn("损坏门锁", by_id["P-P1"].content)
            self.assertEqual(len(manifest["records"]), 4)
            self.assertTrue(any(record["requires_external_vision"] for record in manifest["records"]))
            self.assertTrue(any(record["extraction_status"] == "extracted_override" for record in manifest["records"]))

    def test_image_without_extracted_result_becomes_qwen_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evidence_vault"
            ensure_evidence_vault(root)
            (root / "identification_images" / "P2.png").write_bytes(b"not-a-real-image")

            materials = EvidenceIntake(root).load_materials()

            self.assertEqual(len(materials), 1)
            self.assertEqual(materials[0].material_type, MaterialType.EVIDENCE_IMAGE)
            self.assertIn("待外部 Qwen 识别", materials[0].content)
            self.assertTrue(materials[0].source_path.endswith("P2.png"))

    def test_groups_images_by_subfolder_and_keeps_loose_images_as_single_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evidence_vault"
            ensure_evidence_vault(root)
            group = root / "identification_images" / "group_a"
            group.mkdir()
            (group / "1.jpg").write_bytes(b"not-a-real-image")
            (group / "2.jpg").write_bytes(b"not-a-real-image")
            (root / "identification_images" / "single.jpg").write_bytes(b"not-a-real-image")

            materials = EvidenceIntake(root).load_materials()
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual([item.material_id for item in materials], ["P-group_a-1", "P-group_a-2", "P-single"])
            records_by_id = {record["material_id"]: record for record in manifest["records"]}
            self.assertEqual(records_by_id["P-group_a-1"]["group_id"], "group_a")
            self.assertEqual(records_by_id["P-group_a-2"]["group_id"], "group_a")
            self.assertEqual(records_by_id["P-single"]["group_id"], "single")

    def test_strips_utf8_bom_from_text_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evidence_vault"
            ensure_evidence_vault(root)
            (root / "statements" / "S3.txt").write_text("\ufeff张三称20时在家。", encoding="utf-8")

            materials = EvidenceIntake(root).load_materials()

            self.assertEqual(materials[0].content, "张三称20时在家。")


if __name__ == "__main__":
    unittest.main()
