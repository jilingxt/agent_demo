import json
import tempfile
import unittest
from pathlib import Path

from case_agent_demo.tools import LegalRetrievalTool


class StaticLegalLibraryTests(unittest.TestCase):
    def test_retrieves_matching_laws_from_jsonl_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            library_path = Path(tmp) / "laws.jsonl"
            laws = [
                {
                    "law_id": "criminal_law_264",
                    "law_name": "中华人民共和国刑法",
                    "article": "第二百六十四条",
                    "text": "盗窃公私财物，数额较大的，依法处理。",
                    "legal_elements": ["非法占有目的", "秘密窃取", "公私财物"],
                    "keywords": ["盗窃", "手机", "财物"],
                    "case_types": ["盗窃类案件"],
                    "effective_status": "effective",
                    "source": "static_law_library",
                },
                {
                    "law_id": "criminal_law_275",
                    "law_name": "中华人民共和国刑法",
                    "article": "第二百七十五条",
                    "text": "故意毁坏公私财物，数额较大或者有其他严重情节的，依法处理。",
                    "legal_elements": ["故意毁坏", "公私财物", "数额较大"],
                    "keywords": ["毁坏", "损坏", "门锁"],
                    "case_types": ["故意损毁财物类案件"],
                    "effective_status": "effective",
                    "source": "static_law_library",
                },
            ]
            library_path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in laws),
                encoding="utf-8",
            )
            tool = LegalRetrievalTool(library_path=library_path)

            matches = tool.retrieve(
                {
                    "confirmed_case_type": "盗窃类案件",
                    "behaviors": ["拿走他人手机"],
                    "purpose": "unit_test",
                }
            )

            self.assertEqual(matches[0].law_id, "criminal_law_264")
            self.assertEqual(matches[0].law_name, "中华人民共和国刑法")
            self.assertEqual(matches[0].article, "第二百六十四条")
            self.assertIn("非法占有目的", matches[0].legal_element)
            self.assertIn("static_law_library", matches[0].source)

    def test_falls_back_to_demo_law_when_library_has_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            library_path = Path(tmp) / "laws.jsonl"
            library_path.write_text(
                json.dumps(
                    {
                        "law_id": "criminal_law_275",
                        "law_name": "中华人民共和国刑法",
                        "article": "第二百七十五条",
                        "text": "故意毁坏公私财物。",
                        "keywords": ["毁坏"],
                        "case_types": ["故意损毁财物类案件"],
                        "source": "static_law_library",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            tool = LegalRetrievalTool(library_path=library_path)

            matches = tool.retrieve({"confirmed_case_type": "盗窃类案件", "behaviors": ["拿走手机"]})

            self.assertEqual(matches[0].law_id, "L-DEMO-1")
            self.assertIn("demo", matches[0].source)


if __name__ == "__main__":
    unittest.main()
