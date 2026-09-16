from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import CrossEncoder, SentenceTransformer


EMBEDDING_PATH = Path(os.getenv("BGE_EMBEDDING_PATH", "/models/bge-m3"))
RERANKER_PATH = Path(os.getenv("BGE_RERANKER_PATH", "/models/bge-reranker-v2-m3"))
DEVICE = os.getenv("BGE_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
EMBEDDING_BATCH_SIZE = int(os.getenv("BGE_EMBEDDING_BATCH_SIZE", "8"))
RERANKER_BATCH_SIZE = int(os.getenv("BGE_RERANKER_BATCH_SIZE", "4"))
RERANKER_MAX_LENGTH = int(os.getenv("BGE_RERANKER_MAX_LENGTH", "512"))
PRELOAD = os.getenv("BGE_PRELOAD", "true").lower() in {"1", "true", "yes", "on"}


class EmbeddingRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=128)


class EmbeddingResponse(BaseModel):
    model: str
    dimension: int
    vectors: list[list[float]]


class RerankRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4096)
    passages: list[str] = Field(min_length=1, max_length=100)


class RerankResponse(BaseModel):
    model: str
    scores: list[float]


def _model_files_available(path: Path) -> bool:
    has_weights = (path / "pytorch_model.bin").is_file() or any(path.glob("*.safetensors"))
    return (path / "config.json").is_file() and has_weights


class ModelRegistry:
    def __init__(self) -> None:
        self.embedding: SentenceTransformer | None = None
        self.reranker: CrossEncoder | None = None
        self.lock = threading.RLock()

    def load_embedding(self) -> SentenceTransformer:
        with self.lock:
            if self.embedding is None:
                if not _model_files_available(EMBEDDING_PATH):
                    raise RuntimeError(f"Embedding model is incomplete: {EMBEDDING_PATH}")
                self.embedding = SentenceTransformer(
                    str(EMBEDDING_PATH),
                    device=DEVICE,
                    local_files_only=True,
                    trust_remote_code=True,
                )
            return self.embedding

    def load_reranker(self) -> CrossEncoder:
        with self.lock:
            if self.reranker is None:
                if not _model_files_available(RERANKER_PATH):
                    raise RuntimeError(f"Reranker model is incomplete: {RERANKER_PATH}")
                self.reranker = CrossEncoder(
                    str(RERANKER_PATH),
                    device=DEVICE,
                    max_length=RERANKER_MAX_LENGTH,
                    local_files_only=True,
                    trust_remote_code=True,
                    default_activation_function=torch.nn.Sigmoid(),
                )
            return self.reranker

    def load_all(self) -> None:
        self.load_embedding()
        self.load_reranker()


registry = ModelRegistry()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if PRELOAD:
        registry.load_all()
    yield


app = FastAPI(title="Star Rail BGE Service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, object]:
    available = {
        "embedding": _model_files_available(EMBEDDING_PATH),
        "reranker": _model_files_available(RERANKER_PATH),
    }
    return {
        "status": "ok" if all(available.values()) else "degraded",
        "device": DEVICE,
        "cuda_available": torch.cuda.is_available(),
        "models_available": available,
        "models_loaded": {
            "embedding": registry.embedding is not None,
            "reranker": registry.reranker is not None,
        },
    }


@app.post("/v1/embeddings", response_model=EmbeddingResponse)
def embeddings(request: EmbeddingRequest) -> EmbeddingResponse:
    try:
        model = registry.load_embedding()
        with registry.lock:
            vectors = model.encode(
                request.texts,
                batch_size=EMBEDDING_BATCH_SIZE,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    matrix = np.asarray(vectors, dtype=np.float32)
    return EmbeddingResponse(
        model="BAAI/bge-m3",
        dimension=int(matrix.shape[1]),
        vectors=matrix.tolist(),
    )


@app.post("/v1/rerank", response_model=RerankResponse)
def rerank(request: RerankRequest) -> RerankResponse:
    try:
        model = registry.load_reranker()
        pairs = [[request.query, passage] for passage in request.passages]
        with registry.lock:
            scores = model.predict(
                pairs,
                batch_size=RERANKER_BATCH_SIZE,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RerankResponse(
        model="BAAI/bge-reranker-v2-m3",
        scores=np.asarray(scores, dtype=float).reshape(-1).tolist(),
    )
