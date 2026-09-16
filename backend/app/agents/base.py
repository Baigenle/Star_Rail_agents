from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.schemas.ai_response import AIResponse

AgentEventSink = Callable[..., Awaitable[None]]


@dataclass(slots=True)
class AgentContext:
    user_id: str | None
    message: str
    conversation_id: str | None = None
    intent: str | None = None
    intent_metadata: dict[str, Any] = field(default_factory=dict)
    entities: dict[str, Any] = field(default_factory=dict)
    memories: list[dict[str, Any]] = field(default_factory=list)
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    retrieved_documents: list[dict[str, Any]] = field(default_factory=list)
    memory_injection: str = ""  # [玩家画像]/[近期状态]/[相关记忆]/[回应提示] 注入段（Phase 2）
    delta_sink: Callable[[str], Awaitable[None]] | None = None  # 真流式增量回调（Phase 4.1，仅 job 链路）
    task_submitter: Callable[[str, dict, "AgentContext"], str] | None = None  # 慢任务提交（Phase 4.2）
    event_sink: AgentEventSink | None = None

    async def emit_event(
        self,
        event_type: str,
        title: str,
        *,
        agent: str | None = None,
        detail: str = "",
        event_status: str = "running",
        duration_ms: int | None = None,
        payload: dict[str, object] | None = None,
        progress: dict[str, object] | None = None,
    ) -> None:
        if self.event_sink:
            await self.event_sink(
                event_type,
                title,
                agent=agent,
                detail=detail,
                event_status=event_status,
                duration_ms=duration_ms,
                payload=payload,
                progress=progress,
            )


class BaseAgent(ABC):
    name: str
    description: str

    @abstractmethod
    async def run(self, context: AgentContext) -> AIResponse:
        """Return the shared Claim -> Citation -> Validation -> Filtering contract."""
        raise NotImplementedError
