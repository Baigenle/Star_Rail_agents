import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes.stories import router
from app.api.v1.routes.stories import get_story_catalog
from app.services.story_catalog_service import StoryCatalogService


def _client(tmp_path: Path) -> TestClient:
    story_root = tmp_path / "data_character_story"
    story_root.mkdir()
    missions = [
        {
            "mission_id": "mission-1",
            "mission_name": "测试同行任务",
            "mission_type": "同行任务",
            "version": "1.2",
            "world": "仙舟「罗浮」",
            "series_name": "测试系列",
            "mission_order": 1,
            "characters": ["驭空", "MediaWiki", "刃"],
            "summary": "关于驭空过去的任务。",
            "story_text": "完整正文",
            "source_url": "https://example.com/mission-1",
        }
    ]
    scenes = [
        {
            "chunk_id": "scene-1",
            "mission_id": "mission-1",
            "version": "1.2",
            "mission_name": "测试同行任务",
            "world": "仙舟「罗浮」",
            "series_name": "测试系列",
            "mission_order": 1,
            "chunk_order": 1,
            "scene_title": "第一幕",
            "location": "司辰宫",
            "characters": ["驭空", "MediaWiki", "刃"],
            "content": (
                "【出场角色】驭空、MediaWiki、刃\n\n"
                "【剧情正文】\n驭空:我会亲自讲述自己的过去。\n"
                "MediaWiki:PlotOptions"
            ),
            "source_url": "https://example.com/mission-1",
        },
        {
            "chunk_id": "scene-2",
            "mission_id": "mission-1",
            "version": "1.2",
            "mission_name": "测试同行任务",
            "world": "仙舟「罗浮」",
            "series_name": "测试系列",
            "mission_order": 1,
            "chunk_order": 2,
            "scene_title": "第二幕",
            "location": "司辰宫",
            "characters": ["驭空"],
            "content": "故事继续。",
            "source_url": "https://example.com/mission-1",
        },
    ]
    for name, rows in (
        ("trailblaze_missions.jsonl", missions),
        ("trailblaze_story_chunks.jsonl", scenes),
    ):
        (story_root / name).write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
            encoding="utf-8",
        )

    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_story_catalog] = lambda: StoryCatalogService(
        story_root
    )
    return TestClient(application)


def test_story_list_filters_and_returns_facets(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get(
            "/stories",
            params={
                "version": "1.2",
                "world": "仙舟「罗浮」",
                "mission_type": "同行任务",
                "character": "驭空",
                "q": "过去",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["mission_id"] == "mission-1"
    assert body["items"][0]["matched_character"] == "驭空"
    assert body["items"][0]["matched_scene_count"] == 1
    assert body["items"][0]["first_matching_chunk_id"] == "scene-1"
    assert body["filters"]["versions"] == ["1.2"]


def test_story_character_filter_requires_actual_dialogue_appearance(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        false_match = client.get("/stories", params={"character": "刃"})
        true_match = client.get("/stories", params={"character": "驭空"})
        detail = client.get("/stories/mission-1")
        scene = client.get("/stories/mission-1/scenes/scene-1")

    assert false_match.status_code == 200
    assert false_match.json()["total"] == 0
    assert true_match.json()["total"] == 1
    assert detail.json()["characters"] == ["驭空"]
    assert scene.json()["characters"] == ["驭空"]
    assert "MediaWiki" not in scene.json()["content"]
    assert "【出场角色】" not in scene.json()["content"]


def test_story_detail_and_exact_scene_navigation(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        detail = client.get("/stories/mission-1")
        scene = client.get("/stories/mission-1/scenes/scene-2")
        missing = client.get("/stories/mission-1/scenes/not-found")

    assert detail.status_code == 200
    assert [item["chunk_id"] for item in detail.json()["scenes"]] == [
        "scene-1",
        "scene-2",
    ]
    assert scene.status_code == 200
    assert scene.json()["previous_chunk_id"] == "scene-1"
    assert scene.json()["next_chunk_id"] is None
    assert missing.status_code == 404
