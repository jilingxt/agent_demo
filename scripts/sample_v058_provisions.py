from __future__ import annotations

import argparse
import json
import random
import sqlite3
from pathlib import Path
from typing import Any

from scripts.v058_case_catalog import PROVISION_POOLS, PROVISION_REJECTIONS, ProvisionPool


DEFAULT_DATABASE = Path("legal_knowledge/index/legal_kb.sqlite3")


def sample_provisions(
    database: str | Path,
    *,
    seed: int = 58,
    count_per_law: int = 5,
) -> dict[str, object]:
    database_path = Path(database)
    if not database_path.is_file():
        raise FileNotFoundError(f"Legal knowledge database not found: {database_path}")

    accepted: dict[str, list[dict[str, Any]]] = {}
    rejected: list[dict[str, str]] = []
    draw_trace: dict[str, list[dict[str, object]]] = {}
    pool_sizes: dict[str, int] = {}

    with sqlite3.connect(database_path) as connection:
        for pool_spec in PROVISION_POOLS:
            pool = _load_pool(connection, pool_spec)
            pool_sizes[pool_spec.law_key] = len(pool)
            sampled = _draw_until_enough(
                pool,
                law_key=pool_spec.law_key,
                seed=seed,
                count=count_per_law,
            )
            accepted_items: list[dict[str, Any]] = []
            trace: list[dict[str, object]] = []

            for position, provision in enumerate(sampled, start=1):
                article = str(provision["article"])
                rejection_reason = PROVISION_REJECTIONS.get((pool_spec.law_key, article))
                trace.append(
                    {
                        "draw_position": position,
                        "article": article,
                        "chunk_id": provision["chunk_id"],
                        "accepted": rejection_reason is None,
                        "rejection_reason": rejection_reason or "",
                    }
                )
                if rejection_reason is not None:
                    rejected.append(
                        {
                            "law": pool_spec.law_key,
                            "article": article,
                            "reason": rejection_reason,
                            "replacement": "",
                        }
                    )
                    continue

                accepted_items.append(_manifest_provision(provision))
                if len(accepted_items) == count_per_law:
                    break

            if len(accepted_items) != count_per_law:
                raise ValueError(
                    f"Pool {pool_spec.law_key!r} yielded {len(accepted_items)} accepted "
                    f"provisions, expected {count_per_law}."
                )
            accepted[pool_spec.law_key] = accepted_items
            draw_trace[pool_spec.law_key] = trace

    for item in rejected:
        law_items = accepted[item["law"]]
        item["replacement"] = str(law_items[-1]["article"])

    return {
        "schema_version": "1.0",
        "seed": seed,
        "count_per_law": count_per_law,
        "database": database_path.as_posix(),
        "pool_sizes": pool_sizes,
        "accepted": accepted,
        "rejected": rejected,
        "draw_trace": draw_trace,
    }


def _draw_until_enough(
    pool: list[dict[str, Any]],
    *,
    law_key: str,
    seed: int,
    count: int,
) -> list[dict[str, Any]]:
    draw_count = count
    while draw_count <= len(pool):
        sampled = random.Random(seed).sample(pool, draw_count)
        accepted_count = sum(
            (law_key, str(item["article"])) not in PROVISION_REJECTIONS
            for item in sampled
        )
        if accepted_count >= count:
            return sampled
        draw_count += 1
    return []


def _load_pool(
    connection: sqlite3.Connection,
    pool_spec: ProvisionPool,
) -> list[dict[str, Any]]:
    provisions: list[dict[str, Any]] = []
    rows = connection.execute("SELECT chunk_id, document_id, payload FROM chunks")
    for chunk_id, document_id, payload in rows:
        chunk = json.loads(payload)
        metadata = chunk.get("metadata") or {}
        if chunk.get("title") != pool_spec.title:
            continue
        if metadata.get(pool_spec.metadata_key) != pool_spec.metadata_value:
            continue
        chunk["chunk_id"] = str(chunk.get("chunk_id") or chunk_id)
        chunk["document_id"] = str(chunk.get("document_id") or document_id)
        provisions.append(chunk)
    return provisions


def _manifest_provision(provision: dict[str, Any]) -> dict[str, Any]:
    metadata = provision.get("metadata") or {}
    return {
        "chunk_id": str(provision["chunk_id"]),
        "document_id": str(provision["document_id"]),
        "title": str(provision["title"]),
        "article": str(provision["article"]),
        "text": str(provision["text"]),
        "part": str(metadata.get("part", "")),
        "chapter": str(metadata.get("chapter", "")),
        "section": str(metadata.get("section", "")),
        "source_page_start": metadata.get("source_page_start"),
        "source_page_end": metadata.get("source_page_end"),
        "document_hash": str(metadata.get("document_hash", "")),
    }


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sample the reproducible v0.58 legal corpus.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--seed", type=int, default=58)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", type=Path)
    args = parser.parse_args(argv)

    manifest = sample_provisions(args.db, seed=args.seed)
    rendered = _canonical_json(manifest)
    if args.check is not None:
        expected = args.check.read_text(encoding="utf-8")
        if rendered != expected:
            raise SystemExit(f"Sampling manifest differs from {args.check}")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    elif args.check is None:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
