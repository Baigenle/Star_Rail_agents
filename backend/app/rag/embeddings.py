import hashlib
import math
import re
from abc import ABC, abstractmethod

import httpx


TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9_]+")


class EmbeddingProvider(ABC):
    dimension: int
    name: str

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class HashEmbeddingProvider(EmbeddingProvider):
    """Dependency-free baseline for deterministic ingestion smoke tests.

    This is lexical feature hashing, not the final semantic embedding model.
    Keeping it behind the common interface makes the Milvus pipeline testable
    without API keys or a large model download.
    """

    name = "hash-ngram-v1"

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    @staticmethod
    def _features(text: str) -> list[str]:
        features: list[str] = []
        for token in TOKEN_PATTERN.findall(text.lower()):
            if re.fullmatch(r"[\u4e00-\u9fff]+", token):
                for size in (1, 2, 3):
                    features.extend(
                        token[index : index + size]
                        for index in range(max(0, len(token) - size + 1))
                    )
            else:
                features.append(token)
        return features

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for feature in self._features(text):
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            number = int.from_bytes(digest, "little")
            index = number % self.dimension
            sign = 1.0 if number & (1 << 63) else -1.0
            vector[index] += sign * (1.0 + 0.25 * min(len(feature), 3))
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            return [value / norm for value in vector]
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]


class RemoteBGEEmbeddingProvider(EmbeddingProvider):
    """BGE-M3 adapter backed by the local GPU inference service."""

    name = "BAAI/bge-m3"
    dimension = 1024

    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        batch_size: int = 16,
        timeout: float = 300.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.batch_size = batch_size
        self.timeout = timeout

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        with httpx.Client(timeout=self.timeout) as client:
            for start in range(0, len(texts), self.batch_size):
                response = client.post(
                    f"{self.base_url}/v1/embeddings",
                    json={"texts": texts[start : start + self.batch_size]},
                )
                response.raise_for_status()
                payload = response.json()
                if int(payload["dimension"]) != self.dimension:
                    raise ValueError(
                        f"Expected {self.dimension}-dimensional BGE-M3 vectors, "
                        f"received {payload['dimension']}"
                    )
                vectors.extend(payload["vectors"])
        return vectors
