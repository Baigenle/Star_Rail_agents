import re
from collections.abc import Iterable
from collections.abc import Callable

from pymilvus import DataType, MilvusClient

from app.rag.chunking import KnowledgeChunk
from app.rag.embeddings import EmbeddingProvider
from app.rag.rerankers import Reranker


class MilvusKnowledgeStore:
    def __init__(
        self,
        uri: str,
        collection_name: str,
        embedding: EmbeddingProvider,
        reranker: Reranker | None = None,
    ) -> None:
        self.client = MilvusClient(uri=uri)
        self.collection_name = collection_name
        self.embedding = embedding
        self.reranker = reranker

    def ensure_collection(self) -> None:
        if self.client.has_collection(self.collection_name):
            return
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("chunk_id", DataType.VARCHAR, is_primary=True, max_length=64)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=self.embedding.dimension)
        schema.add_field("entry_id", DataType.VARCHAR, max_length=64)
        schema.add_field("entry_type", DataType.VARCHAR, max_length=64)
        schema.add_field("title", DataType.VARCHAR, max_length=512)
        schema.add_field("section", DataType.VARCHAR, max_length=1024)
        schema.add_field("content", DataType.VARCHAR, max_length=65535)
        schema.add_field("content_hash", DataType.VARCHAR, max_length=64)
        schema.add_field("data_version", DataType.VARCHAR, max_length=64)
        schema.add_field("source_page", DataType.VARCHAR, max_length=2048)
        schema.add_field("generated_at", DataType.VARCHAR, max_length=64)
        schema.add_field("embedding_model", DataType.VARCHAR, max_length=128)

        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )

    def recreate_collection(self) -> None:
        if self.client.has_collection(self.collection_name):
            self.client.drop_collection(self.collection_name)
        self.ensure_collection()

    @staticmethod
    def _batches(values: list[KnowledgeChunk], size: int) -> Iterable[list[KnowledgeChunk]]:
        for start in range(0, len(values), size):
            yield values[start : start + size]

    def upsert_chunks(
        self,
        chunks: list[KnowledgeChunk],
        batch_size: int = 128,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> int:
        self.ensure_collection()
        total = 0
        for batch in self._batches(chunks, batch_size):
            vectors = self.embedding.embed_documents([chunk.content for chunk in batch])
            rows = [
                {
                    "chunk_id": chunk.chunk_id,
                    "vector": vector,
                    "entry_id": chunk.entry_id,
                    "entry_type": chunk.entry_type,
                    "title": chunk.title,
                    "section": chunk.section,
                    "content": chunk.content,
                    "content_hash": chunk.content_hash,
                    "data_version": chunk.data_version,
                    "source_page": chunk.source_page,
                    "generated_at": chunk.generated_at,
                    "embedding_model": self.embedding.name,
                }
                for chunk, vector in zip(batch, vectors, strict=True)
            ]
            self.client.upsert(collection_name=self.collection_name, data=rows)
            total += len(rows)
            if progress_callback:
                progress_callback(total, len(chunks))
        self.client.flush(self.collection_name)
        return total

    def search(
        self, query: str, limit: int = 5, entry_type: str | None = None
    ) -> list[dict[str, object]]:
        filter_expression = f'entry_type == "{entry_type}"' if entry_type else ""
        candidate_limit = max(100, limit * 20)
        output_fields = [
            "chunk_id",
            "entry_id",
            "entry_type",
            "title",
            "section",
            "content",
            "data_version",
            "source_page",
            "embedding_model",
        ]
        results = self.client.search(
            collection_name=self.collection_name,
            data=[self.embedding.embed_query(query)],
            filter=filter_expression,
            limit=candidate_limit,
            output_fields=output_fields,
            search_params={"metric_type": "COSINE", "params": {}},
        )
        candidates = results[0] if results else []
        normalized_query = self._normalize(query)
        title_matches = {
            self._normalize(str(result["entity"]["title"]))
            for result in candidates
            if self._normalize(str(result["entity"]["title"])) in normalized_query
        }
        if title_matches:
            longest = max(len(title) for title in title_matches)
            selected_titles = {title for title in title_matches if len(title) == longest}
            candidates.sort(
                key=lambda result: (
                    self._normalize(str(result["entity"]["title"]))
                    not in selected_titles
                )
            )
        ranked = self._rerank(query, candidates)
        if self.reranker:
            ranked = self._semantic_rerank(query, ranked[: max(30, limit * 6)])
        normalized_query = self._normalize(query)
        exact_titles = {
            self._normalize(str(result["entity"]["title"]))
            for result in ranked
            if self._normalize(str(result["entity"]["title"])) in normalized_query
        }
        longest_exact_title = (
            max(exact_titles, key=len) if exact_titles else ""
        )
        exact_entity_ids = {
            str(result["entity"]["entry_id"])
            for result in ranked
            if self._normalize(str(result["entity"]["title"])) == longest_exact_title
        }
        if len(exact_entity_ids) == 1:
            return ranked[:limit]
        diversified: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for result in ranked:
            entity = result["entity"]
            key = (str(entity["title"]), str(entity["section"]))
            if key in seen:
                continue
            seen.add(key)
            diversified.append(result)
            if len(diversified) == limit:
                return diversified
        for result in ranked:
            if result not in diversified:
                diversified.append(result)
            if len(diversified) == limit:
                break
        return diversified

    def _semantic_rerank(
        self, query: str, candidates: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        passages = []
        normalized_query = self._normalize(query)
        for result in candidates:
            entity = result["entity"]
            passages.append(
                "\n".join(
                    [
                        f"标题：{entity['title']}",
                        f"章节：{entity['section']}",
                        str(entity["content"]),
                    ]
                )
            )
        scores = self.reranker.score(query, passages) if self.reranker else []
        for result, score in zip(candidates, scores, strict=True):
            title = self._normalize(str(result["entity"]["title"]))
            exact_title_boost = 1.0 if title and title in normalized_query else 0.0
            result["model_rerank_score"] = score
            result["reranker_model"] = self.reranker.name if self.reranker else ""
            result["rerank_score"] = score + exact_title_boost
        return sorted(
            candidates,
            key=lambda item: float(item["rerank_score"]),
            reverse=True,
        )

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", text).lower()

    @classmethod
    def _query_features(cls, query: str) -> set[str]:
        normalized = cls._normalize(query)
        features: set[str] = set()
        for size in (2, 3, 4):
            features.update(
                normalized[index : index + size]
                for index in range(max(0, len(normalized) - size + 1))
            )
        return features

    @classmethod
    def _rerank(
        cls, query: str, candidates: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        normalized_query = cls._normalize(query)
        query_features = cls._query_features(query)
        feature_weight = sum(len(feature) for feature in query_features) or 1
        for result in candidates:
            entity = result["entity"]
            title = cls._normalize(str(entity["title"]))
            content = cls._normalize(str(entity["content"]))
            coverage = (
                sum(len(feature) for feature in query_features if feature in content)
                / feature_weight
            )
            title_boost = 5.0 if title and title in normalized_query else 0.0
            vector_score = float(result["distance"])
            result["vector_score"] = vector_score
            result["rerank_score"] = vector_score + 2.0 * coverage + title_boost
        return sorted(candidates, key=lambda item: float(item["rerank_score"]), reverse=True)

    def count(self) -> int:
        result = self.client.query(
            collection_name=self.collection_name,
            filter="",
            output_fields=["count(*)"],
        )
        return int(result[0]["count(*)"]) if result else 0
