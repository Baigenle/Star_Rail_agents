"""FC 主 Agent：原生 Function Calling 决策循环（main-agent-spec.md §6 落地，2026-09-05）。

与 ReactMainAgent（JSON-ReAct）的差异：
1. bind_tools/ToolMessage 原生协议——删除 JSON 容错解析与格式重试；
2. 无意图前置分流（规格禁令）——不再有循环前的 _route 调用；
3. 收底四道防线补齐：safe_execute 前缀协议 → 连续超时退出 → 强制总结轮 → 降级文案。

消息序列：system（人格+规则+工具目录，逐字节稳定，吃前缀缓存）→ 会话历史 →
本轮用户消息（含动态上下文）→ [AIMessage(tool_calls) / ToolMessage]×N → 最终文本。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage

from app.agents.base import AgentContext, BaseAgent
from app.agents.fc_tools import build_fc_tools, rewrite_refs, safe_execute
from app.agents.react_main_agent import ACTION_MAP
from app.schemas.ai_response import (
    AIResponse,
    AgentAction,
    Citation,
    FilteringReport,
    QueryStep,
    ValidationReport,
)

MAX_ROUNDS = 8
PER_ROUND_TIMEOUT = 60
SUMMARY_TIMEOUT = 90
MAX_CONSECUTIVE_TIMEOUTS = 2

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts" / "persona"
_PERSONA_FILES = ("system.md", "identity.md", "soul.md", "tone_rules.md", "canon_quotes.md")


def _load_persona() -> str:
    parts = [
        (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()
        for name in _PERSONA_FILES
        if (PROMPTS_DIR / name).exists()
    ]
    if not parts:  # 人格文件缺失时保持可运行
        parts.append("你是星穹列车智库的主控大脑「黑塔」，通过调用工具回答问题。")
    return "\n\n---\n\n".join(parts)


def _fallback_answer(tool_notes: list[str]) -> str:
    if tool_notes:
        return (
            "这轮思考没能整合出完整结论，先把我查到的信息给你：\n"
            + "\n".join(f"- {note}" for note in tool_notes[:3])
            + "\n\n你可以换个说法补充细节，我再重新查一遍。"
        )
    return (
        "这轮我没能从智库工具里拿到足够材料来回答这个问题。"
        "你可以换个说法补充细节（角色名、场景或想要的结果），我再重新想一遍。"
    )


class FCMainAgent(BaseAgent):
    name = "fc_main_agent"
    description = "原生 Function Calling 决策循环主 Agent：模型绑定工具自主调度，收底四道防线保证必有回复"

    def __init__(
        self,
        tools: list[Any],  # list[react_tools.ToolSpec]
        llm: Any,  # ChatOpenAI（须支持 bind_tools）；测试可注入脚本化假客户端
        *,
        max_rounds: int = MAX_ROUNDS,
        per_round_timeout: float = PER_ROUND_TIMEOUT,
        summary_timeout: float = SUMMARY_TIMEOUT,
    ) -> None:
        self.definitions = build_fc_tools(tools)
        self.llm = llm
        self.max_rounds = max_rounds
        self.per_round_timeout = per_round_timeout
        self.summary_timeout = summary_timeout
        self._system_text = self._system_prompt()

    # ------------------------------------------------------------------
    def _system_prompt(self) -> str:
        catalog = "\n".join(
            f"- {d.tool_id}（{d.label}）：{d.description}"
            for d in self.definitions.values()
        )
        return (
            f"{_load_persona()}\n\n---\n\n"
            "## 可用能力\n"
            f"{catalog}\n\n"
            "## 调用纪律\n"
            "- 需要数据时直接调用对应工具；观察文本以 [无结果]/[错误·配置]/[错误·运行时] 开头时，如实转述原因与建议，禁止编造。\n"
            "- 最终回答的事实句句尾标注 [Cn]（编号来自观察文本里的引用列表）；无引用不陈述数值。\n"
            "- 复合问题逐项覆盖；回答开头不要复述用户问题。"
        )

    @staticmethod
    def _history(context: AgentContext) -> list[Any]:
        messages: list[Any] = []
        for item in context.conversation_history or []:
            role = str(item.get("role") or "")
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
            else:  # 摘要等伪历史条目并入本轮动态段，不进消息序列
                continue
        return messages

    @staticmethod
    def _turn_prompt(context: AgentContext) -> str:
        parts = [f"用户消息：{context.message}"]
        mentioned = [
            f"{item.get('name')}({item.get('character_id')})"
            for item in context.entities.get("mentioned_characters", [])
            if isinstance(item, dict)
        ]
        if mentioned:
            parts.append(f"已确认实体：{'、'.join(mentioned)}")
        owned = context.entities.get("owned_character_ids") or []
        memories = [
            str(item.get("content") or "")
            for item in context.memories[:6]
            if isinstance(item, dict)
        ]
        if owned or memories:
            parts.append(
                f"用户画像：角色池 {len(owned)} 名；长期记忆：{'；'.join(memories) or '无'}"
            )
        summaries = [
            str(item.get("content") or "").strip()
            for item in (context.conversation_history or [])
            if str(item.get("role") or "") not in {"user", "assistant"} and str(item.get("content") or "").strip()
        ]
        if summaries:
            parts.append("[历史摘要] " + " ".join(summaries)[:600])
        if context.memory_injection:
            parts.append(context.memory_injection)
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    async def _invoke_round(self, bound: Any, messages: list, context: AgentContext, *, timeout: float | None = None) -> Any:
        """一轮 LLM 调用。有 delta_sink 时走 astream 逐字转发（出现 tool_call 片段立即
        停止转发，防止把工具轮的过渡语漏给用户）；流式异常自动回退非流式。"""
        effective_timeout = timeout or self.per_round_timeout
        if context.delta_sink is None:
            return await asyncio.wait_for(bound.ainvoke(messages), effective_timeout)

        async def _consume() -> Any:
            accumulated = AIMessageChunk(content="")
            forwarding = True
            async for chunk in bound.astream(messages):
                accumulated = accumulated + chunk
                if getattr(chunk, "tool_call_chunks", None):
                    forwarding = False
                if forwarding and chunk.content and context.delta_sink:
                    await context.delta_sink(str(chunk.content))
            return AIMessage(
                content=accumulated.content,
                additional_kwargs=dict(accumulated.additional_kwargs or {}),
                tool_calls=list(getattr(accumulated, "tool_calls", None) or []),
            )

        try:
            return await asyncio.wait_for(_consume(), effective_timeout)
        except asyncio.TimeoutError:
            raise
        except Exception:  # noqa: BLE001 —— 流式不可用/兼容性问题时回退非流式
            return await asyncio.wait_for(bound.ainvoke(messages), effective_timeout)

    async def run(self, context: AgentContext) -> AIResponse:
        started = perf_counter()
        await context.emit_event(
            "fc.started",
            "主 Agent 开始思考",
            agent=self.name,
            detail=f"FC 决策循环启动，{len(self.definitions)} 个可用工具。",
            event_status="running",
            progress={"stage": "orchestration", "percent": 8},
        )

        messages: list[Any] = [
            SystemMessage(content=self._system_text),
            *self._history(context),
            HumanMessage(content=self._turn_prompt(context)),
        ]
        bound = self.llm.bind_tools([d.spec() for d in self.definitions.values()])
        bare = self.llm.bind_tools([])

        citations: list[Citation] = []
        used_tools: list[str] = []
        tool_notes: list[str] = []
        answer = ""
        rounds_used = 0
        consecutive_timeouts = 0

        for round_no in range(1, self.max_rounds + 1):
            rounds_used = round_no
            await context.emit_event(
                "fc.round",
                f"思考 · 第{round_no}轮",
                agent=self.name,
                event_status="running",
                progress={"stage": "thinking", "percent": min(90, 15 + round_no * 10)},
            )
            try:
                ai = await self._invoke_round(bound, messages, context)
            except asyncio.TimeoutError:
                consecutive_timeouts += 1
                await context.emit_event(
                    "fc.round_timeout",
                    f"第{round_no}轮请求超时",
                    agent=self.name,
                    detail=f"连续超时 {consecutive_timeouts}/{MAX_CONSECUTIVE_TIMEOUTS}",
                    event_status="failed",
                )
                if consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
                    break
                continue
            except Exception as exc:  # noqa: BLE001 —— 循环大脑失败不放弃，走收底
                await context.emit_event(
                    "fc.error",
                    "循环大脑调用失败",
                    agent=self.name,
                    detail=type(exc).__name__,
                    event_status="failed",
                )
                break
            consecutive_timeouts = 0
            messages.append(ai)

            tool_calls = getattr(ai, "tool_calls", None) or []
            if not tool_calls:
                answer = str(ai.content or "").strip()
                break

            for call in tool_calls:
                tool_name = str(call.get("name") or "")
                definition = self.definitions.get(tool_name)
                label = definition.label if definition else tool_name

                # 慢任务（规格 §11）：不内联执行，转后台并在 job 收尾时人格转述
                if definition is not None and definition.slow and context.task_submitter is not None:
                    task_id = context.task_submitter(tool_name, dict(call.get("args") or {}), context)
                    await context.emit_event(
                        "task_submitted",
                        f"{label} 已转入后台执行",
                        agent=self.name,
                        detail=f"任务 {task_id}：完成后自动向用户汇报结果。",
                        event_status="running",
                    )
                    output = (
                        f"[任务已提交后台] {definition.label} 正在后台执行（约 1-2 分钟）。"
                        "请立即告知用户任务已提交、完成后会自动汇报；不要等待，不要编造结果。"
                    )
                    used_tools.append(tool_name)
                    tool_notes.append(f"{label}：已转后台执行")
                    messages.append(
                        ToolMessage(content=output, tool_call_id=str(call.get("id") or tool_name))
                    )
                    await context.emit_event(
                        "fc.tool_result",
                        f"{label} 已转后台",
                        agent=self.name,
                        detail="后台执行中，收尾时汇报结果。",
                        event_status="completed",
                    )
                    continue

                await context.emit_event(
                    "fc.tool_started",
                    f"调用 {label}",
                    agent=self.name,
                    detail=json.dumps(call.get("args") or {}, ensure_ascii=False)[:200],
                    event_status="running",
                )
                offset = len(citations)
                output, result = await safe_execute(definition, dict(call.get("args") or {}), context)
                output = rewrite_refs(output, offset)
                if result:
                    for citation in result.citations:
                        citations.append(citation.model_copy(update={"id": f"C{len(citations) + 1}"}))
                used_tools.append(tool_name)
                tool_notes.append(f"{label}：{output[:120]}")
                messages.append(
                    ToolMessage(content=output, tool_call_id=str(call.get("id") or tool_name))
                )
                await context.emit_event(
                    "fc.tool_result",
                    f"{label} 完成",
                    agent=self.name,
                    detail=output[:160],
                    event_status="completed",
                )

        if not answer:
            # 强制总结轮：禁用工具，必出回复（规格 §6.6）
            messages.append(
                HumanMessage(content="请基于以上工具返回的信息，直接给用户最终回复。不要再调用工具。")
            )
            try:
                ai = await self._invoke_round(bare, messages, context, timeout=self.summary_timeout)
                answer = str(ai.content or "").strip()
                await context.emit_event(
                    "fc.summary",
                    "强制总结完成",
                    agent=self.name,
                    detail="循环未收敛，已用总结轮兜底。",
                    event_status="completed",
                )
            except Exception:  # noqa: BLE001 —— 最后一道防线：降级文案
                answer = ""
                await context.emit_event(
                    "fc.fallback",
                    "降级文案",
                    agent=self.name,
                    detail="总结轮也失败，使用已收集结果拼装回复。",
                    event_status="failed",
                )
        if not answer:
            answer = _fallback_answer(tool_notes)

        elapsed_ms = int((perf_counter() - started) * 1000)
        query_steps = [
            QueryStep(
                id="fc_loop",
                name="FC 决策循环",
                status="completed",
                detail=f"{rounds_used} 轮、{len(used_tools)} 次工具调用、{len(citations)} 条引用，总耗时 {elapsed_ms}ms。",
                duration_ms=elapsed_ms,
            )
        ]
        if tool_notes:
            query_steps.append(
                QueryStep(
                    id="fc_tools",
                    name="工具观察",
                    status="completed",
                    detail="；".join(tool_notes)[:800],
                    duration_ms=0,
                )
            )
        await context.emit_event(
            "fc.completed",
            "主 Agent 完成",
            agent=self.name,
            detail=f"{rounds_used} 轮；工具 {len(used_tools)} 次；引用 {len(citations)} 条。",
            event_status="completed",
            progress={"stage": "completed", "percent": 100},
            payload={"invoked_agents": used_tools},
        )

        return AIResponse(
            agent=self.name,
            answer=answer,
            claims=[],
            citations=citations,
            validation=ValidationReport(
                status="verified" if citations else "unverified",
                method="fc_tool_loop",
                evidence_count=len(citations),
                notes=["回答由 FC 决策循环整合工具结果生成，事实句带来源引用。"],
            ),
            filtering=FilteringReport(
                passed=True,
                removed_claims=0,
                rules=["引用随工具证据走；收底由强制总结轮与降级文案保证。"],
            ),
            query_steps=query_steps,
            invoked_agents=[self.name, *dict.fromkeys(used_tools)],
            follow_up_questions=[],
            actions=self._build_actions(used_tools, context, citations),
        )

    # ------------------------------------------------------------------
    def _build_actions(
        self,
        used_tools: list[str],
        context: AgentContext,
        citations: list[Citation],
    ) -> list[AgentAction]:
        actions: list[AgentAction] = []
        seen_urls: set[str] = set()
        character_name = ""
        for item in context.entities.get("mentioned_characters", []):
            name = str(item.get("name") or "").strip()
            if name:
                character_name = name
                break
        for tool_name in dict.fromkeys(used_tools):
            mapping = ACTION_MAP.get(tool_name)
            if mapping is None:
                continue
            title, url, text = mapping
            if url in seen_urls:
                continue
            seen_urls.add(url)
            params: dict[str, str] = {}
            action_type = "navigate"
            if tool_name in {"team_recommendation", "character_profile"} and character_name:
                params["core"] = character_name
                action_type = "prefill"
            actions.append(
                AgentAction(
                    action_type=action_type,
                    title=title,
                    target_url=url,
                    description=text,
                    params=params,
                )
            )
        return actions[:2]
