"""场景注入器测试：加载、向量匹配、关键词降级、正经模式标记。"""

from __future__ import annotations

import pytest

from app.persona.scene_injector import build_scene_injection, load_scenes, match_scene


@pytest.fixture(scope="module")
def scenes():
    loaded = load_scenes()
    assert len(loaded) == 7
    return loaded


def test_scene_library_loaded(scenes):
    expected = {
        "lose_streak", "tilted", "win_streak", "hero_question",
        "salt_mine", "drought_chat", "daily_chat",
    }
    assert set(scenes) == expected
    assert scenes["lose_streak"].serious and scenes["tilted"].serious
    assert not scenes["win_streak"].serious and not scenes["daily_chat"].serious
    # 每个场景至少 5 条台词样本 + 3 条代表语料
    for scene in scenes.values():
        assert scene.body.count("> 「") >= 5
        assert len(scene.corpus) >= 3


def test_keyword_match_serious_priority():
    # "没满星"命中 lose_streak、"烦死了"命中 tilted，平局 → 正经场景优先
    scene = match_scene("深渊又没满星 烦死了 连跪")
    assert scene is not None and scene.scene_id == "lose_streak"
    text = build_scene_injection("深渊又没满星 烦死了 连跪")
    assert "[当前场景：深渊受挫]" in text
    assert "【正经模式：本轮禁止损人，先站队】" in text


def test_keyword_match_scene_specific():
    assert match_scene("烦死了 恶心").scene_id == "tilted"
    assert match_scene("黄泉的光锥怎么选").scene_id == "hero_question"
    assert match_scene("又歪了 小保底").scene_id == "salt_mine"
    assert match_scene("这期深渊满星了").scene_id == "win_streak"


def test_fallback_scene_never_matched():
    # daily_chat 是兜底基调，规则由 system 静态段承载，永不注入
    assert match_scene("你好呀") is None
    assert build_scene_injection("在吗") == ""


def test_vector_match_via_embedder():
    scenes = load_scenes()

    class FakeEmbedder:
        def embed_documents(self, texts):
            # 让 query 与 win_streak 的代表语料同向（"一次过"是该场景专属词）
            vectors = [[1.0, 0.0] if "一次过" in text else [0.0, 1.0] for text in texts]
            return vectors

    scene = match_scene("这期深渊满星了 一次过", FakeEmbedder())
    assert scene is not None and scene.scene_id == scenes["win_streak"].scene_id


def test_embedder_failure_falls_back_to_keywords():
    class BrokenEmbedder:
        def embed_documents(self, texts):
            raise RuntimeError("BGE 不可用")

    scene = match_scene("烦死了 恶心", BrokenEmbedder())
    assert scene is not None and scene.scene_id == "tilted"


def test_no_match_returns_empty_injection():
    assert match_scene("帮我看看景元的技能是什么") is None
    assert build_scene_injection("帮我看看景元的技能是什么") == ""
