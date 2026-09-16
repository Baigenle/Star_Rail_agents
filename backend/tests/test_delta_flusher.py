"""_DeltaFlusher 测试：增量合并落库、partial_answer 权威字段、finalize 补齐语义。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.api.v1.routes.chat import _DeltaFlusher
from app.db.session import Base
from app.models.chat import ChatJob, ChatJobEvent, Conversation


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as database:
        database.add(Conversation(id="c1", user_id="u1", title="测试会话"))
        database.add(
            ChatJob(id="j1", user_id="u1", conversation_id="c1", request_payload={})
        )
        database.commit()
    return factory


def _deltas(factory, job_id: str = "j1") -> list[str]:
    with factory() as database:
        events = database.scalars(
            select(ChatJobEvent)
            .where(
                ChatJobEvent.job_id == job_id,
                ChatJobEvent.event_type == "answer.delta",
            )
            .order_by(ChatJobEvent.sequence)
        ).all()
        return [str(event.payload.get("delta") or "") for event in events]


@pytest.mark.asyncio
async def test_sink_coalesces_and_finalize_emits_tail(factory):
    flusher = _DeltaFlusher("j1", factory)
    await flusher.sink("你好")
    await flusher.sink("，访客。")
    answer = "你好，访客。任务完成。"
    await flusher.finalize(answer)

    deltas = _deltas(factory)
    assert "".join(deltas) == answer  # 增量拼接 == 最终回答
    assert flusher.streamed_chars == len(answer)

    with factory() as database:
        job = database.get(ChatJob, "j1")
        assert job.partial_answer == answer  # 权威字段与最终回答一致
        sequences = [
            event.sequence
            for event in database.scalars(
                select(ChatJobEvent).where(ChatJobEvent.job_id == "j1")
            ).all()
        ]
        assert sequences == sorted(sequences)  # 序号严格递增


@pytest.mark.asyncio
async def test_finalize_replaces_drifted_stream(factory):
    flusher = _DeltaFlusher("j1", factory)
    await flusher.sink("工具轮泄漏的过渡语")
    drifted_answer = "真正的最终回答。"
    await flusher.finalize(drifted_answer)

    deltas = _deltas(factory)
    # 漂移时整段补发，前端完成后以 partial_answer 校正
    assert deltas[-1] == drifted_answer
    with factory() as database:
        job = database.get(ChatJob, "j1")
        assert job.partial_answer == drifted_answer


@pytest.mark.asyncio
async def test_large_stream_coalesces_into_bounded_events(factory):
    flusher = _DeltaFlusher("j1", factory)
    answer = "字" * 300
    for index in range(0, len(answer), 10):
        await flusher.sink(answer[index : index + 10])
    await flusher.finalize(answer)

    deltas = _deltas(factory)
    assert "".join(deltas) == answer
    # 300 字按 64 字合并，事件数应有界（≤ 6 + 1）
    assert len(deltas) <= 6
