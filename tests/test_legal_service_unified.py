from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from case_agent_demo.legal_kb import LegalKnowledgeBaseTool
from case_agent_demo.models import CaseGraph, Fact, LegalRAGResult
from case_agent_demo.tools import LegalRetrievalTool


class UnifiedLegalServiceTests(unittest.TestCase):
    def test_review_retrieval_uses_the_same_static_fallback_as_reasoning(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / "laws.jsonl"
            library.write_text(
                json.dumps(
                    {
                        "law_id": "law-1",
                        "law_name": "示例法",
                        "article": "第一条",
                        "text": "盗窃他人财物的，依法处理。",
                        "keywords": ["盗窃"],
                        "case_types": ["盗窃"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            graph = CaseGraph(
                facts=[Fact("F1", "M1", "statement", "甲", "甲盗窃他人财物")]
            )
            tool = LegalRetrievalTool(
                library_path=library,
                legal_kb=LegalKnowledgeBaseTool(Path(tmp) / "empty-kb"),
            )

            result = tool.retrieve_result(
                {
                    "confirmed_case_type": "盗窃",
                    "evidence_graph": graph,
                    "purpose": "final_compliance_review",
                }
            )

            self.assertIsInstance(result, LegalRAGResult)
            self.assertTrue(result.matches)
            self.assertTrue(result.chunks)
            self.assertEqual(result.query_trace["fallback"], "static_law_library")


if __name__ == "__main__":
    unittest.main()
