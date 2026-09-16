"""MemoryJudge 测试：解析容错、字段合并策略、触发判据。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.session import Base
from app.memory.judge import MemoryJudge
from app.memory.repository import PgMemoryRepository

VALID = (
    '[{"layer":"L0","field":"main_role","content":"主玩毁灭","confidence":0.9,"trigger_text":"命途"},'
    ' {"layer":"L2","content":"连歪三次卡池后说想弃游","confidence":0.8,"trigger_text":"抽卡 歪了"}]'
)
TRUNCATED = (
    '[{"layer":"L0","field":"preferences","content":"别替我排体力","confidence":0.9},'
    ' {"layer":"L0","field":"main_role","content":"主玩'  # 第二个对象被截断
)
GARBAGE = "这段对话没有值得记录的内容。"
HISTORY = [
    {"role": "user", "content": "我主玩毁灭，在练流萤"},
    {"role": "assistant", "content": "记下了。"},
]


class FakeJudgeLLM:
    def __init__(self, raw: str):
        self.raw = raw
        self.calls = 0

    async def complete(self, messages):  # noqa: ANN001, ANN202
        self.calls += 1
        return self.raw

    async def stream(self, messages):  # noqa: ANN001, ANN202
        yield self.raw


@pytest.fixture()
def repo():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return PgMemoryRepository(factory)


@pytest.mark.asyncio
async def test_valid_candidates_written(repo):
    judge = MemoryJudge(repo, FakeJudgeLLM(VALID))
    written = await judge.extract_and_write("u1", 6, history=HISTORY)
    assert written == 2
    assert repo.get_l0("u1").main_role == "主玩毁灭"
    assert len(repo.all_active_l2("u1")) == 1
    assert repo.get_l1("u1").last_judged_round == 6


@pytest.mark.asyncio
async def test_truncated_json_salvages_complete_objects(repo):
    judge = MemoryJudge(repo, FakeJudgeLLM(TRUNCATED))
    written = await judge.extract_and_write("u2", 6, history=HISTORY)
    assert written == 1  # 截断的第二个对象被丢弃，第一个打捞成功
    assert repo.get_l0("u2").preferences == "别替我排体力"
    assert repo.get_l0("u2").main_role == ""


@pytest.mark.asyncio
async def test_garbage_output_writes_nothing(repo):
    judge = MemoryJudge(repo, FakeJudgeLLM(GARBAGE))
    written = await judge.extract_and_write("u3", 6, history=HISTORY)
    assert written == 0
    assert repo.get_l0("u3").main_role == ""
    assert repo.get_l1("u3").last_judged_round == 6  # 游标仍前进，避免重复空转


@pytest.mark.asyncio
async def test_confidence_merge_rules(repo):
    judge = MemoryJudge(repo, FakeJudgeLLM(VALID))
    await judge.extract_and_write("u4", 6, history=HISTORY)

    # 置信度更低 → 保留现值
    lower = MemoryJudge(repo, FakeJudgeLLM(
        '[{"layer":"L0","field":"main_role","content":"主玩辅助","confidence":0.8}]'
    ))
    assert await lower.extract_and_write("u4", 12, history=HISTORY) == 0
    assert repo.get_l0("u4").main_role == "主玩毁灭"

    # 置信度更高 → 覆盖
    higher = MemoryJudge(repo, FakeJudgeLLM(
        '[{"layer":"L0","field":"main_role","content":"主玩辅助","confidence":0.95}]'
    ))
    assert await higher.extract_and_write("u4", 18, history=HISTORY) == 1
    assert repo.get_l0("u4").main_role == "主玩辅助"

    # 空字段 → 任何 ≥0.6 候选可直接写入
    filler = MemoryJudge(repo, FakeJudgeLLM(
        '[{"layer":"L1","field":"season_goal","content":"深渊满星","confidence":0.7}]'
    ))
    assert await filler.extract_and_write("u4", 24, history=HISTORY) == 1
    assert repo.get_l1("u4").season_goal == "深渊满星"


@pytest.mark.asyncio
async def test_spawn_trigger_thresholds(repo):
    import asyncio
    import contextlib

    judge = MemoryJudge(repo, FakeJudgeLLM(GARBAGE))

    assert judge.spawn_if_due("s1") is None  # 0 轮

    l1 = repo.get_l1("s1")
    l1.round_count = 3
    repo.save_l1("s1", l1)
    assert judge.spawn_if_due("s1") is None  # 3 轮未达阈值、无闲置

    l1.round_count = 6
    repo.save_l1("s1", l1)
    task = judge.spawn_if_due("s1")
    assert task is not None  # 达 6 轮阈值
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    l1.round_count = 3
    repo.save_l1("s1", l1)
    task = judge.spawn_if_due("s1", idle_gap_seconds=3600)
    assert task is not None  # 闲置 30 分钟 + ≥2 轮未提取 → 兜底
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_no_llm_never_spawns(repo):
    judge = MemoryJudge(repo, None)
    assert judge.spawn_if_due("u9") is None
