from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.core.config import Settings
from app.rag.base import RetrievalDocument
from app.rag.providers import build_rag_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest local review corpus into RAG backend.")
    parser.add_argument(
        "--input",
        required=True,
        help="Path to JSONL corpus file. Required fields per line: id, source, content.",
    )
    return parser.parse_args()


def load_documents(path: Path) -> list[RetrievalDocument]:
    docs: list[RetrievalDocument] = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            docs.append(
                RetrievalDocument(
                    doc_id=str(row["id"]),
                    source=str(row["source"]),
                    content=str(row["content"]),
                    metadata=row.get("metadata", {}),
                )
            )
    return docs


async def run() -> None:
    args = parse_args()
    corpus_path = Path(args.input)
    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus file not found: {corpus_path}")

    settings = Settings.from_env()
    rag_service = build_rag_service(settings)
    documents = load_documents(corpus_path)
    inserted = await rag_service.ingest_documents(documents)
    print(
        f"Ingested documents: requested={len(documents)}, inserted={inserted}, "
        f"backend={settings.rag_backend}"
    )


if __name__ == "__main__":
    asyncio.run(run())

