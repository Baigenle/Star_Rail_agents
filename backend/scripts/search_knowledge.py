import argparse

from app.rag.embeddings import HashEmbeddingProvider, RemoteBGEEmbeddingProvider
from app.rag.milvus_store import MilvusKnowledgeStore
from app.rag.rerankers import RemoteBGEReranker


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the Milvus knowledge collection.")
    parser.add_argument("query")
    parser.add_argument("--uri", default="http://localhost:19531")
    parser.add_argument("--collection", default="star_rail_knowledge_v1")
    parser.add_argument("--embedding", choices=("hash", "bge-m3"), default="hash")
    parser.add_argument("--model-service-url", default="http://localhost:8001")
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument("--entry-type")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    embedding = (
        RemoteBGEEmbeddingProvider(args.model_service_url)
        if args.embedding == "bge-m3"
        else HashEmbeddingProvider()
    )
    reranker = RemoteBGEReranker(args.model_service_url) if args.rerank else None
    store = MilvusKnowledgeStore(args.uri, args.collection, embedding, reranker)
    for index, result in enumerate(
        store.search(args.query, args.limit, args.entry_type), start=1
    ):
        entity = result["entity"]
        print(
            f"{index}. score={result['rerank_score']:.4f} "
            f"vector={result['vector_score']:.4f} "
            f"title={entity['title']} type={entity['entry_type']} section={entity['section']}"
        )
        print(f"   source={entity['source_page']}")
        print(f"   {str(entity['content']).replace(chr(10), ' ')[:240]}")


if __name__ == "__main__":
    main()
