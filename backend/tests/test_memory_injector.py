"""记忆注入器测试：画像渲染、向量召回、关键词降级、空输入。"""

from __future__ import annotations

from app.memory.injector import build_memory_injection
from app.memory.schemas import L0Profile, L1Profile, L15Fact, L2Memory


class StubRepo:
    def __init__(self, l0=None, l1=None, memories=None, facts=None):
        self.l0 = l0 or L0Profile()
        self.l1 = l1 or L1Profile()
        self.memories = memories or []
        self.facts = facts or []
        self.stats_updated: list[str] = []

    def get_l0(self, user_id):
        return self.l0

    def get_l1(self, user_id):
        return self.l1

    def all_active_l2(self, user_id):
        return self.memories

    def get_facts(self, user_id):
        return self.facts

    def update_l2_stats(self, memory_id):
        self.stats_updated.append(memory_id)


def _memory(content, trigger, embedding=None):
    return L2Memory(id=f"m-{content[:6]}", user_id="u1", content=content, trigger_text=trigger, embedding=embedding)


def test_empty_user_returns_empty():
    assert build_memory_injection(StubRepo(), None, "随便") == ""


def test_profile_lines_render_nonempty_fields_only():
    repo = StubRepo(
        l0=L0Profile(main_role="主玩毁灭", preferences="别替我排体力"),
        l1=L1Profile(current_focus="在练流萤"),
    )
    text = build_memory_injection(repo, "u1", "我该练什么")
    assert "[玩家画像] 主玩：主玩毁灭；偏好：别替我排体力" in text
    assert "[近期状态] 当前在练：在练流萤" in text
    assert "称呼" not in text  # 空字段不渲染
    assert "[相关记忆]" not in text  # 无记忆不渲染该段


def test_vector_recall_selects_top_match_and_updates_stats():
    near = _memory("在练流萤，差一刀深渊满星", "深渊 练度", embedding=[1.0, 0.0])
    far = _memory("喜欢研究剧情考据", "剧情", embedding=[0.0, 1.0])
    repo = StubRepo(memories=[near, far])

    class FakeEmbedder:
        def embed_documents(self, texts):
            assert len(texts) == 1
            return [[0.98, 0.2]]  # 与 near 同向

    text = build_memory_injection(repo, "u1", "深渊差一刀怎么办", FakeEmbedder())
    assert "差一刀深渊满星" in text
    assert "剧情考据" not in text
    assert repo.stats_updated == [near.id]


def test_keyword_fallback_when_no_embedder():
    repo = StubRepo(memories=[_memory("连歪三次卡池后想弃游", "抽卡 歪了")])
    text = build_memory_injection(repo, "u1", "我又歪了，好难受")
    assert "连歪三次" in text


def test_keyword_fallback_when_embedder_fails():
    repo = StubRepo(memories=[_memory("连歪三次卡池后想弃游", "抽卡 歪了", embedding=[1.0])])

    class BrokenEmbedder:
        def embed_documents(self, texts):
            raise RuntimeError("BGE 服务不可用")

    text = build_memory_injection(repo, "u1", "我又歪了", BrokenEmbedder())
    assert "连歪三次" in text  # 降级关键词召回，主流程不中断


def test_recall_below_threshold_returns_empty():
    repo = StubRepo(memories=[_memory("在练流萤", "练度", embedding=[1.0, 0.0])])

    class UnrelatedEmbedder:
        def embed_documents(self, texts):
            return [[0.0, 1.0]]  # 与记忆正交

    assert "[相关记忆]" not in build_memory_injection(repo, "u1", "今天天气怎么样", UnrelatedEmbedder())


def test_l15_facts_rendered_with_age():
    import time

    fact = L15Fact(
        fact_key="latest_team",
        fact_value="流萤超击破队 → 综合分 78",
        updated_at=int(time.time()) - 3 * 86400,
    )
    repo = StubRepo(facts=[fact])
    text = build_memory_injection(repo, "u1", "上次那队怎么样")
    assert "[游戏档案] · 流萤超击破队 → 综合分 78（更新于 3 天前）" in text


def test_l15_fact_write_failure_degrades_gracefully():
    class BrokenFactRepo(StubRepo):
        def get_facts(self, user_id):
            raise RuntimeError("缓存读取失败")

    text = build_memory_injection(BrokenFactRepo(), "u1", "随便")
    assert "[游戏档案]" not in text  # 降级不中断
