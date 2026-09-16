"""慢任务提交-收尾测试（规格 §11 / A01-A03）。"""

from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.agents.base import AgentContext
from app.agents.fc_main_agent import FCMainAgent
from app.agents.fc_tools import build_fc_tools, safe_execute
from app.agents.react_tools import ToolResult, ToolSpec
from app.db.session import Base
from app.memory.schemas import L2Memory  # noqa: F401
from app.models.chat import ChatMessage
from app.schemas.ai_response import Citation
from app.tasks.runner import SlowTaskRunner


class FakeLLM:
    def __init__(self, script: list):
        self._script = list(script)

    def bind_tools(self, tools):  # noqa: ANN001, ANN202
        return self

    async def ainvoke(self, messages):  # noqa: ANN001, ANN202
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _slow_spec(handler) -> ToolSpec:
    async def wrapper(args, context):  # noqa: ANN001, ANN202
        return await handler(args, context)

    return ToolSpec(
        name="team_recommendation",
        label="智能配队引擎",
        description="慢工具测试",
        args_schema='{"request": "需求"}',
        handler=wrapper,
    )


def _slow_agent(script: list, handler) -> FCMainAgent:
    agent = FCMainAgent(tools=[_slow_spec(handler)], llm=FakeLLM(script))
    return agent


def _repo_fixture_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.mark.asyncio
async def test_submit_returns_immediately_and_followup_reports():
    async def handler(args, context):  # noqa: ANN001, ANN202
        await asyncio.sleep(0.05)
        return ToolResult(
            summary="配队完成",
            data={"answer": "流萤队综合分 78 [C1]"},
            citations=[Citation(id="C1", title="配队评分", source="引擎")],
        )

    agent = _slow_agent([AIMessage(content="结果汇报：流萤队 [C1]")], handler)
    runner = SlowTaskRunner(agent, _repo_fixture_factory())

    submitted: list[str] = []

    async def sink(delta: str) -> None:
        return None

    async def event_sink(*args, **kwargs):  # noqa: ANN001, ANN202
        return None

    base_ctx = AgentContext(
        user_id=None,
        message="流萤怎么配队",
        entities={"owned_character_ids": ["liuying"]},
        memory_injection="[玩家画像] 主玩：毁灭",
    )

    # 循环内调用 task_submitter：立即返回、不内联执行
    task_id = runner.submit(
        tool_name="team_recommendation",
        args={"request": "流萤配队"},
        base_context=base_ctx,
        event_sink=event_sink,
        delta_sink=sink,
    )
    assert task_id
    assert runner.has_pending_or_results

    definition = build_fc_tools([_slow_spec(handler)])["team_recommendation"]
    text, result = await safe_execute(definition, {"request": "x"}, base_ctx)  # 定义可执行
    assert text

    followup = await runner.run_followups(
        event_sink=event_sink, delta_sink=sink, user_id=None, conversation_id=None
    )
    assert followup is not None
    assert "[C1]" in followup.answer
    assert followup.citations and followup.citations[0].id == "C1"
    assert submitted == []


@pytest.mark.asyncio
async def test_timeout_becomes_error_prefix_for_honest_report():
    async def slow_handler(args, context):  # noqa: ANN001, ANN202
        await asyncio.sleep(1.0)
        return ToolResult(summary="不应到达", data={"answer": "x"})

    agent = _slow_agent([AIMessage(content="如实转述超时")], slow_handler)
    runner = SlowTaskRunner(agent, _repo_fixture_factory())
    runner.TIMEOUT_SECONDS = 0.05

    async def noop(*args, **kwargs):  # noqa: ANN001, ANN202
        return None

    runner.submit(
        tool_name="team_recommendation",
        args={"request": "流萤配队"},
        base_context=AgentContext(user_id=None, message="配队"),
        event_sink=noop,
        delta_sink=noop,
    )
    followup = await runner.run_followups(event_sink=noop, delta_sink=noop, user_id=None, conversation_id=None)
    assert followup is not None
    # 收尾 run 的脚本回答由 FakeLLM 给出；断言喂给模型的观察里带超时前缀
    observation = runner._outcomes[0]["observation"]
    assert observation.startswith("[错误·运行时]")


@pytest.mark.asyncio
async def test_followup_persists_assistant_message():
    async def handler(args, context):  # noqa: ANN001, ANN202
        return ToolResult(summary="ok", data={"answer": "结果"}, citations=[])

    factory = _repo_fixture_factory()
    with factory() as database:
        database.add(ChatMessage(conversation_id="c9", role="user", content="配队"))
        database.commit()

    agent = _slow_agent([AIMessage(content="汇报完成")], handler)
    runner = SlowTaskRunner(agent, factory)

    async def noop(*args, **kwargs):  # noqa: ANN001, ANN202
        return None

    base_ctx = AgentContext(user_id=None, message="配队", conversation_id="c9")
    runner.submit(
        tool_name="team_recommendation",
        args={"request": "配队"},
        base_context=base_ctx,
        event_sink=noop,
        delta_sink=noop,
    )
    await runner.run_followups(event_sink=noop, delta_sink=noop, user_id=None, conversation_id="c9")

    with factory() as database:
        rows = database.query(ChatMessage).filter_by(conversation_id="c9", role="assistant").all()
        assert len(rows) == 1
        assert rows[0].content == "汇报完成"


@pytest.mark.asyncio
async def test_fc_loop_slow_tool_submits_without_inline_execution():
    """循环集成：slow 工具 + task_submitter → 立即提交，当轮回复"已提交"。"""
    async def handler(args, context):  # noqa: ANN001, ANN202
        await asyncio.sleep(0.05)
        return ToolResult(summary="配队完成", data={"answer": "结果 [C1]"})

    agent = _slow_agent(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "team_recommendation", "args": {"request": "流萤配队"}, "id": "t1", "type": "tool_call"}
                ],
            ),
            AIMessage(content="任务已提交，好了叫你。"),
        ],
        handler,
    )
    submit_calls: list[str] = []

    def submitter(tool_name: str, args: dict, base_context: AgentContext) -> str:
        submit_calls.append(tool_name)
        return "task-1"

    deltas: list[str] = []

    async def sink(delta: str) -> None:
        deltas.append(delta)

    response = await agent.run(
        AgentContext(user_id=None, message="流萤怎么配队", delta_sink=sink, task_submitter=submitter)
    )
    assert submit_calls == ["team_recommendation"]
    assert response.answer == "任务已提交，好了叫你。"
    assert "team_recommendation" in response.invoked_agents
    # 工具未内联执行：没有真实结果引用
    assert response.citations == []
