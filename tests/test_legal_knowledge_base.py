import json
import tempfile
import unittest
from pathlib import Path

from case_agent_demo.legal_kb import LegalKnowledgeBaseTool
from case_agent_demo.models import CaseGraph, Fact, LegalRAGResult
from case_agent_demo.tools import LegalRetrievalTool


class LegalKnowledgeBaseTests(unittest.TestCase):
    def test_ingest_search_update_delete_and_legacy_retrieve(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "legal_knowledge"
            incoming = root / "incoming"
            incoming.mkdir(parents=True)
            txt = incoming / "injury.txt"
            txt.write_text("中华人民共和国刑法\n第二百三十四条 故意伤害他人身体，轻伤、重伤应结合证据审查。", encoding="utf-8")
            kb = LegalKnowledgeBaseTool(root)

            docs = kb.ingest_folder()
            result = kb.search("故意伤害 轻伤", top_k=3)

            self.assertEqual(len(docs), 1)
            self.assertIsInstance(result, LegalRAGResult)
            self.assertTrue(result.chunks)
            self.assertTrue(result.matches)

            new_txt = incoming / "injury_v2.md"
            new_txt.write_text("# 刑法伤害条款\n第二百三十四条 故意伤害他人身体。", encoding="utf-8")
            updated = kb.update_document(docs[0].document_id, new_txt)
            self.assertEqual(updated.effective_status, "effective")
            self.assertTrue(any(doc.effective_status == "archived" for doc in kb.documents.values()))

            kb.delete_document(updated.document_id)
            self.assertFalse(kb.search("故意伤害").chunks)

    def test_ingest_old_laws_jsonl_and_legacy_tool_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "legal_knowledge"
            incoming = root / "incoming"
            incoming.mkdir(parents=True)
            laws = incoming / "laws.jsonl"
            laws.write_text(
                json.dumps(
                    {
                        "law_id": "criminal_law_234",
                        "law_name": "中华人民共和国刑法",
                        "article": "第二百三十四条",
                        "text": "故意伤害他人身体。",
                        "legal_elements": ["故意伤害", "他人身体"],
                        "keywords": ["故意伤害", "轻伤"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            kb = LegalKnowledgeBaseTool(root)
            kb.ingest_folder()
            graph = CaseGraph(facts=[Fact("F1", "S1", "statement", "张三", "张三殴打李四", object="李四")])

            rag = kb.retrieve_for_case("故意伤害类案件", graph)
            matches = LegalRetrievalTool(legal_kb=kb).retrieve({"confirmed_case_type": "故意伤害类案件", "evidence_graph": graph})

            self.assertTrue(rag.matches)
            self.assertTrue(matches)

    def test_reloaded_index_keeps_domain_affinities_searchable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "legal_knowledge"
            incoming = root / "incoming"
            incoming.mkdir(parents=True)
            txt = incoming / "injury.txt"
            txt.write_text("故意伤害 他人身体 轻伤 鉴定意见", encoding="utf-8")

            LegalKnowledgeBaseTool(root).ingest_folder()
            reloaded = LegalKnowledgeBaseTool(root)
            result = reloaded.search("故意伤害", domain_ids=["criminal_injury"])

            self.assertTrue(result.chunks)


if __name__ == "__main__":
    unittest.main()
