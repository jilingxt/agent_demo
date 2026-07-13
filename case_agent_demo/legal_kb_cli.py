from __future__ import annotations

import argparse
import json
from pathlib import Path

from case_agent_demo.legal_embeddings import FastEmbedProvider, HashingEmbeddingProvider
from case_agent_demo.legal_kb import LegalKnowledgeBaseTool


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="法律混合RAG知识库管理")
    parser.add_argument("--root", default="legal_knowledge", help="知识库根目录")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="入库法律文件夹")
    ingest.add_argument("--source", default="law_DB", help="法律源文件夹")
    ingest.add_argument(
        "--embedding-provider",
        choices=("fastembed", "hashing"),
        default="fastembed",
    )

    search = commands.add_parser("search", help="检索法律条文")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=8)

    commands.add_parser("stats", help="查看索引统计")
    args = parser.parse_args(argv)
    root = Path(args.root)

    if args.command == "ingest":
        provider = (
            FastEmbedProvider(cache_dir=str(root / "models"))
            if args.embedding_provider == "fastembed"
            else HashingEmbeddingProvider()
        )
        kb = LegalKnowledgeBaseTool(root, embedding_provider=provider)
        documents = kb.ingest_folder(args.source)
        _print(
            {
                "documents": len(documents),
                "chunks": len(kb.chunks),
                "embedding_backend": provider.backend,
                "embedding_model": provider.model_name,
                "database": str(kb.database_path.resolve()),
            }
        )
        return 0

    kb = LegalKnowledgeBaseTool(root)
    if args.command == "stats":
        _print(
            {
                "documents": len(kb.documents),
                "chunks": len(kb.chunks),
                "embedding_backend": kb.embedding_provider.backend,
                "embedding_model": kb.embedding_provider.model_name,
                "database": str(kb.database_path.resolve()),
            }
        )
        return 0

    result = kb.search(args.query, top_k=args.top_k)
    _print(
        {
            "query": result.query,
            "results": [
                {
                    "title": chunk.title,
                    "article": chunk.article,
                    "score": chunk.score,
                    "page": chunk.metadata.get("source_page_start"),
                    "text": chunk.text,
                }
                for chunk in result.chunks
            ],
            "trace": result.query_trace,
        }
    )
    return 0


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
