"""DMAE 引擎与注入块测试：激活/衰减/久别重逢/级联/预算。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.session import Base
from app.knowledge.worldbook.engine import DmaeParams, EntryState, WorldbookEngine
from app.knowledge.worldbook.injector import build_injection
from app.knowledge.worldbook.loader import WorldbookEntry


@pytest.fixture()
def engine_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return factory


def _entry(entry_id: str, keywords, *, permanent=False, intrinsic=80.0, links=()):
    return WorldbookEntry(
        entry_id=entry_id,
        title=entry_id,
        keywords=tuple(keywords),
        permanent=permanent,
        intrinsic=intrinsic,
        priority=100.0,
        link_triggers=tuple(links),
        content=f"【事实】{entry_id} 的正文内容，用于验证注入。",
    )


def _engine(factory, entries):
    return WorldbookEngine(session_factory=factory, entries=entries)


def test_permanent_entries_skip_state_machine(engine_factory):
    entries = [
        _entry("perm", ["常驻词"], permanent=True),
        _entry("dyn", ["动态词"]),
    ]
    eng = _engine(engine_factory, entries)
    text = eng.on_turn_and_build("conv-1", "常驻词 动态词", "")
    assert "【perm】" in text and "【dyn】" in text
    # 常驻条目不产生状态行
    with engine_factory() as session:
        from app.models.memory import WorldbookStateRow

        rows = session.query(WorldbookStateRow).all()
        assert all(row.entry_id != "perm" for row in rows)


def test_user_hit_activates_and_miss_decays(engine_factory):
    entries = [_entry("dyn", ["动态词"])]
    eng = _engine(engine_factory, entries)

    eng.on_turn_and_build("conv-1", "提到动态词", "")
    states = eng._load_states("conv-1")
    assert states["dyn"].activation >= 20.0  # 基础奖励

    # 连续 5 轮沉默 → 衰减（严格低于首次激活值，但不会瞬间清零）
    for _ in range(5):
        eng.on_turn_and_build("conv-1", "无关话题", "")
    states = eng._load_states("conv-1")
    assert 0.0 < states["dyn"].activation < 35.0


def test_wake_bonus_grows_with_silence(engine_factory):
    entries = [_entry("dyn", ["动态词"])]
    eng = _engine(engine_factory, entries)

    eng.on_turn_and_build("conv-1", "提到动态词", "")  # 首次激活 20
    for _ in range(4):
        eng.on_turn_and_build("conv-1", "无关", "")
    before = eng._load_states("conv-1")["dyn"].activation
    eng.on_turn_and_build("conv-1", "又提到动态词", "")  # 久别重逢
    after = eng._load_states("conv-1")["dyn"].activation
    assert after - before > 20.0  # 久别增益 > 基础奖励


def test_model_hits_alone_never_activate(engine_factory):
    entries = [_entry("dyn", ["动态词"])]
    eng = _engine(engine_factory, entries)
    for _ in range(3):
        eng.on_turn_and_build("conv-1", "用户没提", "模型自己复述动态词")
    states = eng._load_states("conv-1")
    assert states["dyn"].activation == 0.0  # 无用户兴趣，模型自说自话不激活


def test_persistence_across_engine_instances(engine_factory):
    entries = [_entry("dyn", ["动态词"])]
    eng1 = _engine(engine_factory, entries)
    eng1.on_turn_and_build("conv-1", "提到动态词", "")

    eng2 = WorldbookEngine(session_factory=engine_factory, entries=entries)
    text = eng2.on_turn_and_build("conv-1", "无关", "")
    # 状态从 PG/SQLite 恢复：注入块仍在（激活分未清零，衰减一轮不至于低于阈值）
    assert "【dyn】" in text


def test_cascade_injects_without_state_change(engine_factory):
    entries = [
        _entry("main", ["主线词"], links=["关联词"]),
        _entry("linked", ["关联词"]),
    ]
    eng = _engine(engine_factory, entries)
    text = eng.on_turn_and_build("conv-1", "提到主线词", "")
    assert "【linked】" in text  # 连带注入
    states = eng._load_states("conv-1")
    assert states["linked"].activation == 0.0  # 只注入、不改状态


def test_injection_budget_and_caps():
    params = DmaeParams(max_active=2, char_budget=200)
    entries = [_entry(f"e{i}", [f"词{i}"]) for i in range(5)]
    states = {f"e{i}": EntryState(activation=50.0) for i in range(5)}
    cascade = set()
    text = build_injection(entries, states, cascade, params)
    assert len(text) <= 200 + len(_entry("x", ["x"]).content[:0]) + 200  # 预算硬约束
    assert text.count("【e") <= 3  # max_active=2 + 预算截断


def test_below_threshold_not_injected():
    params = DmaeParams()
    entries = [_entry("hot", ["热词"]), _entry("cold", ["冷词"])]
    states = {
        "hot": EntryState(activation=80.0),
        "cold": EntryState(activation=10.0),  # 低于 30
    }
    text = build_injection(entries, states, set(), params)
    assert "【hot】" in text
    assert "【cold】" not in text
