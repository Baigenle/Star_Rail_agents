import json
from pathlib import Path

from app.rag.chunking import chunk_document
from app.rag.knowledge_loader import KnowledgeDocument
from app.services.story_chunk_resolver import StoryChunkResolver


def test_story_vector_hash_resolves_to_source_scene_id(tmp_path: Path) -> None:
    story_root = tmp_path / "data_character_story"
    story_root.mkdir()
    payload = {
        "chunk_id": "trailblaze_scene_0001",
        "mission_id": "trailblaze_mission_0001",
        "mission_name": "小城畸人",
        "content": "【剧情正文】\n流萤:很高兴能再次与你同行。",
    }
    (story_root / "trailblaze_story_chunks.jsonl").write_text(
        json.dumps(payload, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    document = KnowledgeDocument(
        path=story_root / "trailblaze_story_chunks.jsonl",
        entry_id=payload["mission_id"],
        entry_type="hsr_story",
        title=payload["mission_name"],
        content=payload["content"],
        metadata={},
    )
    vector_chunk_id = chunk_document(document)[0].chunk_id

    resolver = StoryChunkResolver(tmp_path)

    assert resolver.resolve(vector_chunk_id) == "trailblaze_scene_0001"
    assert resolver.resolve("unknown-hash") is None
