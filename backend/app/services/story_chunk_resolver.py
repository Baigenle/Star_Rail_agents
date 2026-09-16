from __future__ import annotations

import json
from pathlib import Path

from app.rag.chunking import chunk_document
from app.rag.knowledge_loader import KnowledgeDocument


class StoryChunkResolver:
    """Map Milvus window hashes back to the source JSONL scene ids."""

    def __init__(self, docs_root: Path) -> None:
        self.story_path = (
            docs_root / "data_character_story" / "trailblaze_story_chunks.jsonl"
        )
        self._mapping: dict[str, str] | None = None

    def resolve(self, vector_chunk_id: str) -> str | None:
        if self._mapping is None:
            self._mapping = self._build_mapping()
        return self._mapping.get(vector_chunk_id)

    def _build_mapping(self) -> dict[str, str]:
        if not self.story_path.is_file():
            return {}
        mapping: dict[str, str] = {}
        with self.story_path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                payload = json.loads(line)
                source_chunk_id = str(payload.get("chunk_id") or "")
                mission_id = str(payload.get("mission_id") or "")
                mission_name = str(payload.get("mission_name") or "")
                content = str(payload.get("content") or "").strip()
                if not source_chunk_id or not mission_id or not mission_name or not content:
                    continue
                document = KnowledgeDocument(
                    path=self.story_path,
                    entry_id=mission_id,
                    entry_type="hsr_story",
                    title=mission_name,
                    content=content,
                    metadata={},
                )
                for chunk in chunk_document(document):
                    mapping[chunk.chunk_id] = source_chunk_id
        return mapping
