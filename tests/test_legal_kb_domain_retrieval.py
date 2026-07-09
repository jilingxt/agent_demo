import tempfile
import unittest
from pathlib import Path

from case_agent_demo.legal_kb import LegalKnowledgeBaseTool
from case_agent_demo.models import CaseGraph, Fact


class LegalKbDomainRetrievalTests(unittest.TestCase):
    def test_retrieve_for_review_prioritizes_evidence_and_forensic_domains(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "legal_knowledge"
            incoming = root / "incoming"
            incoming.mkdir(parents=True)
            (incoming / "review.md").write_text(
                "# 证据审查规则\n鉴定意见、视听资料、询问笔录应审查真实性、合法性、关联性。\n",
                encoding="utf-8",
            )
            kb = LegalKnowledgeBaseTool(root)
            kb.ingest_folder()
            graph = CaseGraph(facts=[Fact("F1", "R1", "report_image", "李四", "鉴定意见显示轻伤二级", object="李四")])

            result = kb.retrieve_for_review("故意伤害类案件", graph, "报告初稿")

            self.assertTrue(result.chunks)
            self.assertTrue(result.query_trace.get("domain_ids"))


if __name__ == "__main__":
    unittest.main()
