"""慢任务提交-收尾（规格 §11）。

slow=True 的工具（team_recommendation，1-2 分钟）在 FC 循环中不内联执行：
- 提交：立即返回 [任务已提交后台] 观察，模型当轮回复"任务已提交"
- 收尾：job 保持 running（SSE 不断开），后台执行完成后在同一 job 上发起一次
  收尾 run——把工具观察喂给主 Agent 用人格转述，增量继续走 delta_sink
- 结果落会话（assistant 消息），job.response_payload 用收尾回答

超时与失败语义：工具超时/异常转成 [错误·运行时] 文本，收尾 run 如实转述（A03）。"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.agents.base import AgentContext
from app.agents.fc_tools import safe_execute
from app.models.chat import ChatMessage

logger = logging.getLogger(__name__)


class SlowTaskRunner:
    """每个 job 一个实例；FC 循环通过 AgentContext.task_submitter 提交。"""

    TIMEOUT_SECONDS = 600
    FOLLOWUP_TIMEOUT = 240

    def __init__(self, agent: Any, session_factory: Any, memory_repo=None) -> None:
        self.agent = agent
        self.session_factory = session_factory
        self.memory_repo = memory_repo
        self._outcomes: list[dict[str, Any]] = []
        self._pending: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    def submit(
        self,
        *,
        tool_name: str,
        args: dict[str, Any],
        base_context: AgentContext,
        event_sink,
        delta_sink,
    ) -> str:
        definition = self.agent.definitions.get(tool_name)
        task_id = uuid4().hex[:8]
        snapshot = {
            "user_id": base_context.user_id,
            "conversation_id": base_context.conversation_id,
            "entities": dict(base_context.entities),
            "memories": list(base_context.memories),
            "conversation_history": list(base_context.conversation_history or []),
            "memory_injection": base_context.memory_injection,
        }
        self._outcomes.append(
            {
                "task_id": task_id,
                "tool_name": tool_name,
                "label": definition.label if definition else tool_name,
                "args": dict(args),
                "snapshot": snapshot,
                "observation": None,
                "citations": [],
                "done": False,
            }
        )
        task = asyncio.create_task(self._execute(task_id, definition, args, snapshot))
        self._pending.append(task)
        return task_id

    async def _execute(self, task_id: str, definition, args: dict, snapshot: dict) -> None:
        outcome = next(item for item in self._outcomes if item["task_id"] == task_id)
        context = AgentContext(
            user_id=snapshot["user_id"],
            message=str(args.get("request") or args.get("query") or args.get("name") or ""),
            conversation_id=snapshot["conversation_id"],
            entities=snapshot["entities"],
            memories=snapshot["memories"],
        )
        started = time.monotonic()
        try:
            text, result = await asyncio.wait_for(
                safe_execute(definition, dict(args), context), self.TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            text = f"[错误·运行时] {definition.label} 后台执行超时（>{self.TIMEOUT_SECONDS}s）。"
            result = None
        except Exception as exc:  # noqa: BLE001
            text = f"[错误·运行时] {type(exc).__name__}：后台执行失败。"
            result = None
        outcome["observation"] = text
        outcome["citations"] = list(result.citations) if result else []
        outcome["done"] = True
        # L1.5 缓存：慢工具结论（如配队）按用户落事实，后续"上次那队"可秒答
        if self.memory_repo is not None and snapshot.get("user_id"):
            try:
                from app.memory.schemas import L15Fact

                self.memory_repo.upsert_fact(
                    str(snapshot["user_id"]),
                    L15Fact(
                        fact_key="latest_team",
                        fact_value=f"{str(args.get('request') or '')[:80]} → {text[:180]}",
                    ),
                )
            except Exception:  # noqa: BLE001 —— 缓存失败不影响主流程
                pass
        logger.info(
            "慢任务完成 task=%s label=%s 耗时=%.1fs",
            task_id,
            outcome["label"],
            time.monotonic() - started,
        )

    # ------------------------------------------------------------------
    @property
    def has_pending_or_results(self) -> bool:
        return bool(self._outcomes)

    async def run_followups(
        self,
        *,
        event_sink=None,
        delta_sink=None,
        user_id: str | None,
        conversation_id: str | None,
    ) -> Any:
        """等待全部后台任务完成，逐个发起收尾 run；返回最后一个收尾响应。"""
        if not self._outcomes:
            return None
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)

        last_response = None
        for outcome in self._outcomes:
            if event_sink:
                await event_sink(
                    "task_completed",
                    f"{outcome['label']} 后台执行完成",
                    agent="fc_main_agent",
                    detail="开始向用户汇报结果。",
                    event_status="completed",
                    payload={"task_id": outcome["task_id"]},
                )
            observation = outcome.get("observation") or "[错误·运行时] 后台任务无结果。"
            original_request = str(
                (outcome.get("args") or {}).get("request")
                or (outcome.get("args") or {}).get("query")
                or ""
            )
            followup_message = (
                f"[后台任务完成：{outcome['label']}] 用户当时的原始要求：{original_request}。"
                f"工具返回如下，请用你的语气把结果告诉用户，事实句保留 [Cn] 引用编号；"
                f"转述前先核对结果是否满足用户原始要求（约束、范围），不满足就如实指出，"
                f"不要再提任务已提交：\n{observation}"
            )
            context = AgentContext(
                user_id=outcome["snapshot"]["user_id"],
                message=followup_message,
                conversation_id=outcome["snapshot"]["conversation_id"],
                entities=outcome["snapshot"]["entities"],
                memories=outcome["snapshot"]["memories"],
                conversation_history=outcome["snapshot"]["conversation_history"],
                memory_injection=outcome["snapshot"]["memory_injection"],
                delta_sink=delta_sink,
                event_sink=event_sink,
            )
            if delta_sink:
                await delta_sink("\n\n—— 后台结果来了 ——\n")
            try:
                response = await asyncio.wait_for(
                    self.agent.run(context), self.FOLLOWUP_TIMEOUT
                )
            except Exception as exc:  # noqa: BLE001 —— 收尾失败也必有汇报
                logger.exception("慢任务收尾 run 失败 task=%s", outcome["task_id"])
                from app.schemas.ai_response import (
                    AIResponse,
                    FilteringReport,
                    ValidationReport,
                )

                response = AIResponse(
                    agent="fc_main_agent",
                    answer=(
                        f"{outcome['label']} 后台跑完了，但汇报环节出了问题：{type(exc).__name__}。"
                        "原始结果我先留着，你可以再问一次。"
                    ),
                    claims=[],
                    citations=[],
                    validation=ValidationReport(status="unverified", method="slow_task_followup"),
                    filtering=FilteringReport(passed=True, removed_claims=0),
                )
            if outcome["citations"]:
                response = response.model_copy(update={"citations": outcome["citations"]})
            outcome["answer"] = response.answer
            last_response = response
            self._persist_assistant_message(conversation_id, response)
        return last_response

    def _persist_assistant_message(self, conversation_id: str | None, response: Any) -> None:
        if not conversation_id or not response.answer:
            return

        with self.session_factory() as session:
            session.add(
                ChatMessage(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=response.answer,
                    response_payload=response.model_dump(mode="json"),
                    created_at=datetime.now(timezone.utc),
                )
            )
            session.commit()
