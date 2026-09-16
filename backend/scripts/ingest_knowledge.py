import argparse
from collections import Counter
from pathlib import Path

from app.rag.chunking import chunk_documents
from app.rag.embeddings import HashEmbeddingProvider, RemoteBGEEmbeddingProvider
from app.rag.knowledge_loader import load_knowledge_documents
from app.rag.milvus_store import MilvusKnowledgeStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Load, filter, chunk and ingest game knowledge.")
    parser.add_argument("--docs", type=Path, required=True)
    parser.add_argument("--uri", default="http://localhost:19531")
    parser.add_argument("--collection", default="star_rail_knowledge_v1")
    parser.add_argument("--embedding", choices=("hash", "bge-m3"), default="hash")
    parser.add_argument("--model-service-url", default="http://localhost:8001")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument(
        "--entry-type",
        action="append",
        dest="entry_types",
        help="Only ingest the selected entry type; may be repeated.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--recreate", action="store_true")
    args = parser.parse_args()

    documents, rejected = load_knowledge_documents(args.docs)
    if args.entry_types:
        allowed_types = set(args.entry_types)
        documents = [
            document
            for document in documents
            if document.entry_type in allowed_types
        ]
    chunks = chunk_documents(documents)
    print(f"documents.accepted={len(documents)}")
    print(f"documents.rejected={len(rejected)}")
    print(f"chunks.total={len(chunks)}")
    print(f"documents.by_type={dict(Counter(doc.entry_type for doc in documents))}")
    print(f"chunks.by_type={dict(Counter(chunk.entry_type for chunk in chunks))}")
    for item in rejected:
        print(f"rejected={item.path.name} reasons={','.join(item.reasons)}")
    if args.dry_run:
        return

    embedding = (
        RemoteBGEEmbeddingProvider(args.model_service_url)
        if args.embedding == "bge-m3"
        else HashEmbeddingProvider()
    )
    store = MilvusKnowledgeStore(args.uri, args.collection, embedding)
    if args.recreate:
        store.recreate_collection()
    inserted = store.upsert_chunks(
        chunks,
        batch_size=args.batch_size,
        progress_callback=lambda done, total: print(
            f"milvus.progress={done}/{total} ({done / total:.1%})", flush=True
        ),
    )
    print(f"milvus.upserted={inserted}")
    print(f"milvus.count={store.count()}")


if __name__ == "__main__":
    main()
