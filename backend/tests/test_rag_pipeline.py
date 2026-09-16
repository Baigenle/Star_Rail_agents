import json
import math
from pathlib import Path

from app.rag.chunking import chunk_document
from app.rag.embeddings import HashEmbeddingProvider
from app.rag.knowledge_loader import KnowledgeDocument, load_knowledge_documents


def test_chunking_filters_exporter_sections() -> None:
    document = KnowledgeDocument(
        path=Path("1_测试.md"),
        entry_id="1",
        entry_type="hsr_item",
        title="测试物品",
        content=(
            "# 测试物品\n\n"
            "## 基本资料\n\n这是应保留的知识。\n\n"
            "### 子标题\n\n子标题应与二级章节放在同一个语义块中。\n\n"
            "## 使用说明\n\n这段导出器说明不应进入向量库。"
        ),
        metadata={
            "data_version": "1.0",
            "source_page": "https://example.com/1",
            "generated_at": "2026-01-01T00:00:00+08:00",
        },
    )

    chunks = chunk_document(document)

    assert any("这是应保留的知识" in chunk.content for chunk in chunks)
    assert any("子标题应与" in chunk.content for chunk in chunks)
    assert all("导出器说明" not in chunk.content for chunk in chunks)


def test_hash_embedding_is_deterministic_and_normalized() -> None:
    provider = HashEmbeddingProvider(dimension=128)
    first = provider.embed_query("黄泉是雷属性虚无角色")
    second = provider.embed_query("黄泉是雷属性虚无角色")

    assert first == second
    assert len(first) == 128
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0)


def test_loader_accepts_structured_story_and_lore_jsonl(tmp_path: Path) -> None:
    story_dir = tmp_path / "data_character_story"
    lore_dir = tmp_path / "data_lore_pages"
    story_dir.mkdir()
    lore_dir.mkdir()
    story = {
        "chunk_id": "story-1",
        "mission_id": "mission-1",
        "version": "2.0",
        "mission_name": "测试主线",
        "mission_type": "开拓任务",
        "scene_title": "冲突发生",
        "content": "【剧情正文】角色为了保护同伴作出了选择。",
        "source_url": "https://example.com/story",
    }
    lore = {
        "chunk_id": "lore-1",
        "document_id": "lore-doc-1",
        "page_title": "星神",
        "document_type": "aeon",
        "heading": "「开拓」阿基维利",
        "section_path": ["星神", "开拓"],
        "content": "阿基维利执掌开拓命途，并曾不断探索未知边界。",
        "source_url": "https://example.com/lore",
        "source_revision_id": 42,
    }
    (story_dir / "trailblaze_story_chunks.jsonl").write_text(
        json.dumps(story, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (lore_dir / "lore_sections.jsonl").write_text(
        json.dumps(lore, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    documents, rejected = load_knowledge_documents(tmp_path)

    assert rejected == []
    assert {(item.entry_type, item.title) for item in documents} == {
        ("hsr_story", "测试主线"),
        ("hsr_lore", "「开拓」阿基维利"),
    }
    story_document = next(
        item for item in documents if item.entry_type == "hsr_story"
    )
    assert story_document.entry_id == "mission-1"
    assert story_document.metadata["mission_type"] == "开拓任务"
    assert story_document.metadata["source_page"] == "https://example.com/story"


def test_loader_rejects_invalid_story_jsonl_line(tmp_path: Path) -> None:
    story_dir = tmp_path / "data_character_story"
    story_dir.mkdir()
    (story_dir / "trailblaze_story_chunks.jsonl").write_text(
        '{"chunk_id":"ok-but-incomplete"}\nnot-json\n', encoding="utf-8"
    )

    documents, rejected = load_knowledge_documents(tmp_path)

    assert documents == []
    assert len(rejected) == 2
    assert any("invalid_json" in reason for item in rejected for reason in item.reasons)
