from __future__ import annotations

import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path

from case_agent_demo.legal_embeddings import HashingEmbeddingProvider
from case_agent_demo.legal_kb import LegalKnowledgeBaseTool
from case_agent_demo.legal_parser import PageText, parse_legal_pages


class LegalPdfParserTests(unittest.TestCase):
    def test_article_parser_keeps_structure_and_page_span(self):
        articles = parse_legal_pages(
            [
                PageText(1, "第一章 总则\n第一条 第一条内容跨页"),
                PageText(2, "继续说明。\n第二条 第二条内容。"),
            ]
        )

        self.assertEqual([item.article for item in articles], ["第一条", "第二条"])
        self.assertEqual(articles[0].chapter, "第一章 总则")
        self.assertEqual((articles[0].page_start, articles[0].page_end), (1, 2))
        self.assertIn("继续说明", articles[0].text)

    def test_article_reference_at_line_start_does_not_split_current_article(self):
        articles = parse_legal_pages(
            [
                PageText(
                    1,
                    "第七十六条 缓刑考验期内依法监督，如果没有本法\n"
                    "第七十七条规定的情形，考验期满。\n"
                    "第七十七条 被宣告缓刑的犯罪分子违反规定的，撤销缓刑。",
                )
            ]
        )

        self.assertEqual([item.article for item in articles], ["第七十六条", "第七十七条"])
        self.assertIn("第七十七条规定的情形", articles[0].text)

    def test_supplemental_article_heading_is_preserved(self):
        articles = parse_legal_pages(
            [
                PageText(
                    1,
                    "第一百三十三条 主条内容。\n"
                    "第一百三十三条之一 补充条款内容。",
                )
            ]
        )

        self.assertEqual(
            [item.article for item in articles],
            ["第一百三十三条", "第一百三十三条之一"],
        )


class LegalPdfRagTests(unittest.TestCase):
    def test_changing_embedding_dimensions_rebuilds_existing_vectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "law.md"
            source.write_text("示例法\n第一条 盗窃他人财物。", encoding="utf-8")
            root = Path(tmp) / "kb"
            LegalKnowledgeBaseTool(
                root,
                embedding_provider=HashingEmbeddingProvider(dimensions=64),
            ).ingest_document(source)

            LegalKnowledgeBaseTool(
                root,
                embedding_provider=HashingEmbeddingProvider(dimensions=128),
            )

            with closing(sqlite3.connect(root / "index" / "legal_kb.sqlite3")) as connection:
                dimensions = {row[0] for row in connection.execute("SELECT dimensions FROM embeddings")}
            self.assertEqual(dimensions, {128})

    def test_corrupted_mixed_vector_rows_are_detected_from_row_distribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "law.md"
            source.write_text(
                "示例法\n第一条 盗窃他人财物。\n第二条 殴打他人。",
                encoding="utf-8",
            )
            root = Path(tmp) / "kb"
            LegalKnowledgeBaseTool(
                root,
                embedding_provider=HashingEmbeddingProvider(dimensions=64),
            ).ingest_document(source)
            with closing(sqlite3.connect(root / "index" / "legal_kb.sqlite3")) as connection:
                chunk_id = connection.execute("SELECT chunk_id FROM embeddings LIMIT 1").fetchone()[0]
                connection.execute(
                    "UPDATE embeddings SET dimensions = 8, vector = ? WHERE chunk_id = ?",
                    (bytes(8 * 4), chunk_id),
                )
                connection.commit()

            LegalKnowledgeBaseTool(root)

            with closing(sqlite3.connect(root / "index" / "legal_kb.sqlite3")) as connection:
                rows = list(
                    connection.execute(
                        "SELECT model, dimensions, length(vector) FROM embeddings"
                    )
                )
            self.assertTrue(rows)
            self.assertEqual({(model, dimensions, size) for model, dimensions, size in rows}, {("local-hashing-bigram-v1", 64, 256)})

    def test_failed_update_and_reindex_keep_the_effective_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "law.md"
            source.write_text("示例法\n第一条 盗窃他人财物。", encoding="utf-8")
            kb = LegalKnowledgeBaseTool(
                Path(tmp) / "kb",
                embedding_provider=HashingEmbeddingProvider(),
            )
            document = kb.ingest_document(source)

            with self.assertRaises(FileNotFoundError):
                kb.update_document(document.document_id, Path(tmp) / "missing.md")
            self.assertEqual(kb.documents[document.document_id].effective_status, "effective")

            source.unlink()
            with self.assertRaises(FileNotFoundError):
                kb.reindex(document.document_id)
            self.assertEqual(kb.documents[document.document_id].effective_status, "effective")
            self.assertTrue(kb.search("盗窃他人财物").chunks)

    def test_pdf_ingestion_is_idempotent_and_search_has_relevance_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            law = source / "sample.md"
            law.write_text(
                "中华人民共和国示例法\n第一章 总则\n"
                "第一条 盗窃他人财物的，依法处理。\n"
                "第二条 殴打他人或者故意伤害他人身体的，依法处理。",
                encoding="utf-8",
            )
            kb = LegalKnowledgeBaseTool(
                Path(tmp) / "kb",
                embedding_provider=HashingEmbeddingProvider(),
            )

            first = kb.ingest_folder(source)
            second = kb.ingest_folder(source)

            self.assertEqual(len(first), 1)
            self.assertEqual(first[0].document_id, second[0].document_id)
            self.assertEqual(len(kb.documents), 1)
            self.assertEqual(len(kb.chunks), 2)
            self.assertEqual(kb.search("秘密窃取他人财物").chunks[0].article, "第一条")
            self.assertEqual(kb.search("量子计算卫星轨道").chunks, [])

    def test_two_project_laws_are_ingested_and_cross_law_results_are_traceable(self):
        law_dir = Path(__file__).resolve().parents[1] / "law_DB"
        if not law_dir.exists():
            self.skipTest("project law_DB is not available")

        with tempfile.TemporaryDirectory() as tmp:
            kb = LegalKnowledgeBaseTool(
                Path(tmp) / "kb",
                embedding_provider=HashingEmbeddingProvider(),
            )
            documents = kb.ingest_folder(law_dir)
            result = kb.search("盗窃他人财物 治安处罚 刑事责任", top_k=12)

            self.assertEqual(len(documents), 3)
            versions = {item.title: item.version for item in documents}
            self.assertEqual(versions["中华人民共和国刑法"], "2023年修正")
            self.assertEqual(versions["中华人民共和国治安管理处罚法"], "2025年修订")
            self.assertEqual(versions["中华人民共和国刑事诉讼法"], "2018年修正")
            self.assertGreaterEqual(len(kb.chunks), 950)
            self.assertIn("中华人民共和国刑法", {item.title for item in result.chunks})
            self.assertIn("中华人民共和国治安管理处罚法", {item.title for item in result.chunks})
            citations = {(item.title, item.article) for item in result.chunks}
            self.assertIn(("中华人民共和国刑法", "第二百六十四条"), citations)
            self.assertIn(("中华人民共和国治安管理处罚法", "第五十八条"), citations)
            self.assertTrue(all(item.metadata.get("source_page_start") for item in result.chunks))
            self.assertTrue(result.query_trace.get("embedding_model"))
            self.assertTrue((Path(tmp) / "kb" / "index" / "legal_kb.sqlite3").exists())
            self.assertTrue((Path(tmp) / "kb" / "metadata" / "corpus_manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
