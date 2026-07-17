from pathlib import Path

from case_agent_demo.legal_embeddings import HashingEmbeddingProvider
from case_agent_demo.legal_kb import LegalKnowledgeBaseTool
from case_agent_demo.legal_parser import PageText, parse_legal_pages


def test_parser_keeps_spaced_supplementary_article_as_its_own_article():
    articles = parse_legal_pages(
        [
            PageText(
                1,
                "第十七条 基础条文\n第十七条 之一 补充条文\n第十八条 后续条文",
            )
        ]
    )

    assert [item.article for item in articles] == ["第十七条", "第十七条之一", "第十八条"]


def test_criminal_procedure_law_is_classified_and_ranked_for_evidence_review(tmp_path):
    source = tmp_path / "刑诉法.txt"
    source.write_text(
        "中华人民共和国刑事诉讼法\n第一条 规范刑事诉讼。\n"
        "第五十五条 对一切案件的判处都要重证据，证据确实、充分并排除合理怀疑。\n"
        "第五十六条 采用刑讯逼供等非法方法收集的犯罪嫌疑人供述应当予以排除。",
        encoding="utf-8",
    )
    kb = LegalKnowledgeBaseTool(
        tmp_path / "kb",
        embedding_provider=HashingEmbeddingProvider(),
    )

    document = kb.ingest_document(source)
    result = kb.search(
        "证据确实充分 排除合理怀疑 非法证据排除",
        purpose="evidence_review",
        top_k=5,
    )

    assert document.title == "中华人民共和国刑事诉讼法"
    assert document.doc_type == "criminal_procedure_law"
    assert result.chunks
    assert all(item.doc_type == "criminal_procedure_law" for item in result.chunks)


def test_reindex_repairs_stale_type_for_a_canonical_law(tmp_path):
    source = tmp_path / "刑诉法.txt"
    source.write_text(
        "中华人民共和国刑事诉讼法\n第一条 规范刑事诉讼。",
        encoding="utf-8",
    )
    kb = LegalKnowledgeBaseTool(
        tmp_path / "kb",
        embedding_provider=HashingEmbeddingProvider(),
    )
    document = kb.ingest_document(source, doc_type="normative_file")

    kb.reindex(document.document_id)

    assert kb.documents[document.document_id].doc_type == "criminal_procedure_law"


def test_reindex_keeps_document_identity_when_the_parser_normalizes_its_title(tmp_path):
    source = tmp_path / "刑诉法.txt"
    source.write_text(
        "旧解析标题\n第一条 规范刑事诉讼。",
        encoding="utf-8",
    )
    kb = LegalKnowledgeBaseTool(
        tmp_path / "kb",
        embedding_provider=HashingEmbeddingProvider(),
    )
    document = kb.ingest_document(source)
    source.write_text(
        "中华人民共和国刑事诉讼法\n第一条 规范刑事诉讼。",
        encoding="utf-8",
    )

    kb.reindex(document.document_id)

    assert set(kb.documents) == {document.document_id}
    assert kb.documents[document.document_id].title == "中华人民共和国刑事诉讼法"
    assert kb.documents[document.document_id].doc_type == "criminal_procedure_law"
