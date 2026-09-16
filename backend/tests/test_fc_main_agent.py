"""FC 主 Agent 单测：脚本化 LLM 客户端，不触网。

覆盖五条路径：工具调用→回答 / 工具异常→前缀协议 / 循环耗尽→强制总结 /
连续超时→强制总结 / 无工具直答。收底四道防线中 ①②③④ 各有断言。
"""

from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from app.agents.base import AgentContext
from app.agents.fc_main_agent import FCMainAgent
from app.agents.react_tools import ToolResult, ToolSpec
from app.schemas.ai_response import Citation


class StubArgs(BaseModel):
    query: str = ""


class FakeLLM:
    """脚本化客户端：ainvoke 依序弹出脚本项（AIMessage 或异常实例）。"""

    def __init__(self, script: list):
        self._script = list(script)

    def bind_tools(self, tools):  # noqa: ANN001, ANN202
        return self

    async def ainvoke(self, messages):  # noqa: ANN001, ANN202
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _tool_call(name: str = "knowledge_search", args: dict | None = None) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args or {"query": "黑塔"}, "id": "t1", "type": "tool_call"}],
    )


def _spec(handler) -> ToolSpec:
    async def wrapper(args, context):  # noqa: ANN001, ANN202
        return await handler(args, context)

    return ToolSpec(
        name="knowledge_search",
        label="知识库检索",
        description="测试工具",
        args_schema='{"query": "问题"}',
        handler=wrapper,
    )


def _result() -> ToolResult:
    citation = Citation(id="C1", title="黑塔档案", source="docs")
    return ToolResult(summary="命中 1 条", data={"answer": "结果 [C1]"}, citations=[citation])


def _context() -> AgentContext:
    return AgentContext(user_id=None, message="黑塔是谁")


async def _ok_handler(args, context):  # noqa: ANN001, ANN202
    return _result()


def _agent(script: list, handler=_ok_handler, **kwargs) -> FCMainAgent:
    return FCMainAgent(tools=[_spec(handler)], llm=FakeLLM(script), **kwargs)


@pytest.mark.asyncio
async def test_tool_call_then_final_answer():
    agent = _agent([_tool_call(), AIMessage(content="黑塔是天才俱乐部#83 [C1]")])
    response = await agent.run(_context())
    assert "黑塔" in response.answer
    assert response.invoked_agents == ["fc_main_agent", "knowledge_search"]
    assert response.validation.status == "verified"
    assert response.citations[0].id == "C1"
    assert response.agent == "fc_main_agent"


@pytest.mark.asyncio
async def test_tool_exception_becomes_error_prefix_not_raise():
    async def boom(args, context):
        raise RuntimeError("Milvus 断线")

    agent = _agent([_tool_call(), AIMessage(content="查不了，抱歉")], handler=boom)
    response = await agent.run(_context())  # 不应抛出
    assert "查不了" in response.answer
    steps = " ".join(step.detail for step in response.query_steps)
    assert "[错误·运行时]" in steps
    assert response.validation.status == "unverified"


@pytest.mark.asyncio
async def test_loop_exhaustion_triggers_forced_summary():
    agent = _agent(
        [_tool_call(), _tool_call(), AIMessage(content="基于已查信息：黑塔是 #83")],
        max_rounds=2,
    )
    response = await agent.run(_context())
    assert response.answer == "基于已查信息：黑塔是 #83"
    assert any("总结" in step.name or "FC" in step.name for step in response.query_steps)


@pytest.mark.asyncio
async def test_consecutive_timeouts_trigger_forced_summary():
    agent = _agent(
        [
            asyncio.TimeoutError(),
            asyncio.TimeoutError(),
            AIMessage(content="超时兜底回复"),
        ]
    )
    response = await agent.run(_context())
    assert response.answer == "超时兜底回复"


@pytest.mark.asyncio
async def test_no_tool_direct_answer():
    agent = _agent([AIMessage(content="你好呀，访客。")])
    response = await agent.run(_context())
    assert response.answer == "你好呀，访客。"
    assert response.invoked_agents == ["fc_main_agent"]


@pytest.mark.asyncio
async def test_unknown_tool_reports_config_error():
    agent = _agent([_tool_call(name="不存在的工具"), AIMessage(content="如实回复")])
    response = await agent.run(_context())
    assert response.answer == "如实回复"
    steps = " ".join(step.detail for step in response.query_steps)
    assert "[错误·配置]" in steps


# ---------------------------------------------------------------------------
# 真流式（Phase 4.1）
# ---------------------------------------------------------------------------


class FakeStreamingLLM(FakeLLM):
    """脚本项为 AIMessageChunk 列表（一轮的增量序列）或异常。"""

    async def astream(self, messages):  # noqa: ANN001, ANN202
        pieces = self._script.pop(0)
        if isinstance(pieces, Exception):
            raise pieces
        for piece in pieces:
            yield piece


@pytest.mark.asyncio
async def test_streaming_forwards_deltas_and_final_answer():
    from langchain_core.messages import AIMessageChunk

    agent = _agent([])  # 脚本由流式客户端接管
    agent.llm = FakeStreamingLLM(
        [[AIMessageChunk(content="你好"), AIMessageChunk(content="，访客。")]]
    )
    deltas: list[str] = []

    async def sink(delta: str) -> None:
        deltas.append(delta)

    response = await agent.run(AgentContext(user_id=None, message="你好", delta_sink=sink))
    assert response.answer == "你好，访客。"
    assert "".join(deltas) == "你好，访客。"


@pytest.mark.asyncio
async def test_streaming_stops_forwarding_on_tool_round():
    from langchain_core.messages import AIMessageChunk

    tool_round = [
        AIMessageChunk(
            content="",
            tool_call_chunks=[
                {
                    "name": "knowledge_search",
                    "args": '{"query": "黑塔"}',
                    "id": "t1",
                    "index": 0,
                    "type": "tool_call_chunk",
                }
            ],
        )
    ]
    final_round = [AIMessageChunk(content="答案 [C1]")]
    agent = _agent([])
    agent.llm = FakeStreamingLLM([tool_round, final_round])
    deltas: list[str] = []

    async def sink(delta: str) -> None:
        deltas.append(delta)

    response = await agent.run(AgentContext(user_id=None, message="查黑塔", delta_sink=sink))
    assert response.answer == "答案 [C1]"
    assert deltas == ["答案 [C1]"]  # 工具轮零泄漏
    assert response.invoked_agents == ["fc_main_agent", "knowledge_search"]


@pytest.mark.asyncio
async def test_streaming_failure_falls_back_to_ainvoke():

    agent = _agent([])
    agent.llm = FakeStreamingLLM(
        [RuntimeError("BGE 流式不可用"), AIMessage(content="兜底回答")]
    )
    deltas: list[str] = []

    async def sink(delta: str) -> None:
        deltas.append(delta)

    response = await agent.run(AgentContext(user_id=None, message="你好", delta_sink=sink))
    assert response.answer == "兜底回答"
    assert deltas == []  # 回退路径不产生增量，由 finalize/切片兜底
