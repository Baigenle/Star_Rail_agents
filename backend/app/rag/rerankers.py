from abc import ABC, abstractmethod

import httpx


class Reranker(ABC):
    name: str

    @abstractmethod
    def score(self, query: str, passages: list[str]) -> list[float]:
        raise NotImplementedError


class RemoteBGEReranker(Reranker):
    name = "BAAI/bge-reranker-v2-m3"

    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        timeout: float = 300.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        response = httpx.post(
            f"{self.base_url}/v1/rerank",
            json={"query": query, "passages": passages},
            timeout=self.timeout,
        )
        response.raise_for_status()
        scores = [float(score) for score in response.json()["scores"]]
        if len(scores) != len(passages):
            raise ValueError("Reranker returned a different number of scores than passages")
        return scores
