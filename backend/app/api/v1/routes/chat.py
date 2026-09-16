import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.agents.base import AgentContext, AgentEventSink
from app.agents.base import BaseAgent
from app.api.dependencies import (
    get_fast_llm_provider,
    get_herta_main_agent,
)
from app.api.v1.routes.auth import current_user, optional_current_user
from app.db.session import SessionLocal, get_db
from app.models.chat import ChatJob, ChatJobEvent, ChatMessage, Conversation
from app.models.planning import ProgressionPlan
from app.models.team import UserTeam
from app.models.user import User, UserCharacter, UserCharacterProgress, UserMemory
from app.schemas.ai_response import AIResponse, ChatRequest, RelatedEntity
from app.schemas.chat import (
    ChatMessageListResponse,
    ChatMessageResponse,
    ChatJobListResponse,
    ChatJobEventResponse,
    ChatJobResponse,
    ConversationListResponse,
    ConversationResponse,
)
from app.memory import care_cue as care_cue_service
from app.memory.injector import build_memory_injection
from app.memory.judge import MemoryJudge
from app.memory.repository import PgMemoryRepository
from app.knowledge.worldbook.engine import WorldbookEngine
from app.persona.scene_injector import build_scene_injection
from app.rag.embeddings import RemoteBGEEmbeddingProvider
from app.tasks.runner import SlowTaskRunner
from app.services.memory_service import MemoryService
from app.services.conversation_summary_service import (
    build_context_summary,
    inject_summary,
    should_refresh,
)
from app.services.catalog_service import CatalogService
from app.core.config import settings

router = APIRouter()
catalog_service = CatalogService(settings.docs_root)
_active_job_tasks: set[asyncio.Task[None]] = set()

logger = logging.getLogger(__name__)

# 生产后台恢复任务使用默认 SessionLocal；普通请求会从依赖注入的数据库派生仓库，
# 避免测试或多数据库部署时悄悄连接到另一套数据库。
_memory_repo = PgMemoryRepository(SessionLocal)
_memory_embedder = RemoteBGEEmbeddingProvider(settings.bge_service_url)


def _as_utc(value: datetime) -> datetime:
    """SQLite 可能返回无时区时间；生产 PostgreSQL 返回带时区时间。"""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _spawn_memory_judge(
    repository: PgMemoryRepository,
    user_id: str,
    idle_gap_seconds: float,
) -> None:
    try:
        judge = MemoryJudge(repository, get_fast_llm_provider(), _memory_embedder)
        task = judge.spawn_if_due(user_id, idle_gap_seconds=idle_gap_seconds)
        if task is not None:
            _active_job_tasks.add(task)
            task.add_done_callback(_active_job_tasks.discard)
            logger.info("MemoryJudge 触发（user_id=%s）", user_id)
    except Exception:  # noqa: BLE001 —— 记忆提取永不影响主回复
        logger.exception("MemoryJudge 任务派发失败")


def _owned_context(database: Session, user_id: str) -> list[dict[str, object]]:
    context: list[dict[str, object]] = [
        {
            "type": memory.memory_type,
            "content": memory.content,
            "source": memory.source,
        }
        for memory in database.scalars(
            select(UserMemory).where(
                UserMemory.user_id == user_id, UserMemory.is_active.is_(True)
            )
        ).all()
    ]
    characters = database.scalars(
        select(UserCharacter).where(UserCharacter.user_id == user_id)
    ).all()
    if characters:
        context.append(
            {
                "type": "owned_characters",
                "character_ids": [item.character_id for item in characters],
                "favorite_character_ids": [
                    item.character_id for item in characters if item.is_favorite
                ],
                "source": "profile",
            }
        )
    teams = database.scalars(
        select(UserTeam).where(UserTeam.user_id == user_id)
    ).all()
    if teams:
        context.append(
            {
                "type": "saved_teams",
                "names": [team.name for team in teams],
                "source": "profile",
            }
        )
    progress = database.scalars(
        select(UserCharacterProgress).where(UserCharacterProgress.user_id == user_id)
    ).all()
    if progress:
        context.append(
            {
                "type": "character_progress",
                "items": [
                    {
                        "character_id": item.character_id,
                        "current_level": item.current_level,
                        "target_level": item.target_level,
                    }
                    for item in progress
                ],
                "source": "profile",
            }
        )
    return context


def _user_entities(database: Session, user_id: str) -> dict[str, object]:
    characters = database.scalars(
        select(UserCharacter).where(UserCharacter.user_id == user_id)
    ).all()
    progress = database.scalars(
        select(UserCharacterProgress).where(UserCharacterProgress.user_id == user_id)
    ).all()
    active_plans = database.scalars(
        select(ProgressionPlan)
        .where(
            ProgressionPlan.user_id == user_id,
            ProgressionPlan.status == "active",
        )
        .order_by(ProgressionPlan.priority)
    ).all()
    return {
        "owned_character_ids": [item.character_id for item in characters],
        "favorite_character_ids": [
            item.character_id for item in characters if item.is_favorite
        ],
        "character_progress": [
            {
                "character_id": item.character_id,
                "current_level": item.current_level,
                "target_level": item.target_level,
                "current_skills": item.current_skills,
                "target_skills": item.target_skills,
            }
            for item in progress
        ],
        "active_progression_plans": [
            {
                "id": item.id,
                "name": item.name,
                "priority": item.priority,
            }
            for item in active_plans
        ],
    }


def _count_messages(database: Session, conversation_id: str) -> int:
    return (
        database.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .count()
    )


def _conversation_history(
    database: Session, conversation_id: str, *, limit: int = 12
) -> list[dict[str, str]]:
    recent = database.scalars(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {"role": message.role, "content": message.content}
        for message in reversed(recent)
    ]


def _owned_conversation(
    database: Session, user_id: str, conversation_id: str
) -> Conversation:
    conversation = database.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conversation


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> ConversationListResponse:
    items = database.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
    ).all()
    return ConversationListResponse(
        items=[ConversationResponse.model_validate(item) for item in items],
        total=len(items),
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=ChatMessageListResponse,
)
def list_conversation_messages(
    conversation_id: str,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> ChatMessageListResponse:
    conversation = database.scalar(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return ChatMessageListResponse(
        conversation=ConversationResponse.model_validate(conversation),
        items=[
            ChatMessageResponse(
                id=message.id,
                role=message.role,
                content=message.content,
                response=(
                    AIResponse.model_validate(message.response_payload)
                    if message.response_payload
                    else None
                ),
                created_at=message.created_at,
            )
            for message in conversation.messages
        ],
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    conversation_id: str,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> Response:
    conversation = _owned_conversation(database, user.id, conversation_id)
    database.delete(conversation)
    database.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/messages", response_model=AIResponse)
async def create_message(
    request: ChatRequest,
    agent: BaseAgent = Depends(get_herta_main_agent),
    user: User | None = Depends(optional_current_user),
    database: Session = Depends(get_db),
) -> AIResponse:
    return await _execute_message(request, agent, user, database)


async def _execute_message(
    request: ChatRequest,
    agent: BaseAgent,
    user: User | None,
    database: Session,
    *,
    commit: bool = True,
    event_sink: AgentEventSink | None = None,
    delta_sink: Callable[[str], Awaitable[None]] | None = None,
    task_submitter: Callable[[str, dict, AgentContext], str] | None = None,
    memory_repo: PgMemoryRepository | None = None,
) -> AIResponse:
    # 所有记忆与 Worldbook 访问必须绑定当前请求的数据库引擎。
    request_session_factory = sessionmaker(bind=database.get_bind(), expire_on_commit=False)
    request_memory_repo = memory_repo or PgMemoryRepository(session=database)
    worldbook_engine = WorldbookEngine(session=database)
    conversation: Conversation | None = None
    catalog_characters = catalog_service.list_characters()
    mentioned_characters = MemoryService.character_mentions(
        request.message, catalog_characters, limit=None
    )
    mentioned_items = sorted(
        (
            item
            for item in catalog_service.list_items(limit=5000)
            if len(item.name) >= 2 and item.name in request.message
        ),
        key=lambda item: len(item.name),
        reverse=True,
    )[:1]
    mentioned_catalog_entities = [
        {
            "entity_type": "hsr_character",
            "entity_id": character.id,
            "character_id": character.id,
            "name": character.name,
        }
        for character in mentioned_characters
    ]
    mentioned_catalog_entities.extend(
        {
            "entity_type": "hsr_item",
            "entity_id": item.id,
            "name": item.name,
        }
        for item in mentioned_items
    )
    if user:
        if request.conversation_id:
            conversation = _owned_conversation(
                database, user.id, str(request.conversation_id)
            )
        else:
            conversation = Conversation(
                user_id=user.id,
                title=request.message.strip()[:80],
            )
            database.add(conversation)
            database.flush()

    entities = _user_entities(database, user.id) if user else {}
    entities["mentioned_characters"] = [
        {"character_id": character.id, "name": character.name}
        for character in mentioned_characters
    ]
    entities["mentioned_catalog_entities"] = mentioned_catalog_entities
    conversation_history = (
        _conversation_history(database, conversation.id)
        if conversation and request.conversation_id
        else [item.model_dump() for item in request.history]
    )
    if conversation and request.conversation_id:
        # 长对话渐进摘要：旧消息压缩为上下文摘要注入（见 conversation_summary_service）。
        if should_refresh(conversation, _count_messages(database, conversation.id)):
            await build_context_summary(
                database, conversation, get_fast_llm_provider()
            )
        conversation_history = inject_summary(
            conversation_history, conversation.summary_text or ""
        )

    # 记忆层（Phase 2）：轮次计数 + 画像/情景注入 + care cue 消费（仅登录用户）。
    memory_injection = ""
    idle_gap_seconds = 0.0
    if user and conversation:
        profile = request_memory_repo.get_l1(str(user.id))
        profile.round_count += 1
        request_memory_repo.save_l1(str(user.id), profile)
        memory_injection = build_memory_injection(
            request_memory_repo, str(user.id), request.message, _memory_embedder
        )
        # Worldbook 主动注入层：骨架知识按触发命中/激活分进 prompt（模型不调工具也知道）
        last_reply = next(
            (
                str(item.get("content") or "")
                for item in reversed(conversation_history or [])
                if item.get("role") == "assistant"
            ),
            "",
        )
        worldbook_block = worldbook_engine.on_turn_and_build(
            str(conversation.id), request.message, last_reply
        )
        if worldbook_block:
            memory_injection = (memory_injection + "\n" + worldbook_block).strip()
        if conversation.updated_at:
            idle_gap_seconds = max(
                0.0,
                (datetime.now(timezone.utc) - _as_utc(conversation.updated_at)).total_seconds(),
            )
        cue = care_cue_service.consume_care_cue(database, conversation)
        if cue:
            memory_injection = (memory_injection + "\n[回应提示] " + cue).strip()
        # 场景语气（Phase 3）：未命中返回空串，通用语气由 system 静态段承载
        scene_block = build_scene_injection(request.message, _memory_embedder)
        if scene_block:
            memory_injection = (memory_injection + "\n" + scene_block).strip()
    agent_context = AgentContext(
        user_id=user.id if user else None,
        message=request.message,
        conversation_id=conversation.id if conversation else None,
        memories=_owned_context(database, user.id) if user else [],
        entities=entities,
        conversation_history=conversation_history,
        memory_injection=memory_injection,
        delta_sink=delta_sink,
        task_submitter=task_submitter,
        event_sink=event_sink,
    )
    result = await agent.run(agent_context)
    suppress_character_cards = agent_context.intent_metadata.get(
        "task_mode"
    ) == "assistant_identity"
    related_entities = (
        []
        if suppress_character_cards
        else [
            RelatedEntity(
                entity_type="character",
                entity_id=character.id,
                name=character.name,
                entity_url=f"/characters/{character.id}",
                image_url=character.image_url,
            )
            for character in mentioned_characters
        ]
    )
    related_keys = {
        (item.entity_type, item.entity_id) for item in related_entities
    }
    for item in mentioned_items:
        key = ("item", item.id)
        if key in related_keys:
            continue
        related_entities.append(
            RelatedEntity(
                entity_type="item",
                entity_id=item.id,
                name=item.name,
                entity_url=f"/items/{item.id}",
                image_url=item.image_url,
            )
        )
        related_keys.add(key)
    url_types = {
        "characters": "character",
        "items": "item",
        "lightcones": "lightcone",
        "relics": "relic",
        "stories": "story",
        "activities": "activity",
    }
    single_reference_types = {"item", "story"}
    for citation in result.citations:
        if not citation.entity_url or not citation.document_id:
            continue
        prefix = citation.entity_url.lstrip("/").split("/", 1)[0]
        entity_type = url_types.get(prefix)
        if entity_type is None:
            continue
        if entity_type in single_reference_types and any(
            item.entity_type == entity_type for item in related_entities
        ):
            continue
        key = (entity_type, citation.document_id)
        if key in related_keys:
            continue
        related_entities.append(
            RelatedEntity(
                entity_type=entity_type,
                entity_id=citation.document_id,
                name=citation.title.split(" · ", 1)[0].strip() or "完整剧情",
                entity_url=citation.entity_url,
                image_url=citation.image_url,
            )
        )
        related_keys.add(key)
    suggestions = MemoryService.suggestions(request.message) if user else []
    favorite_suggestions = []
    if user:
        characters = database.scalars(
            select(UserCharacter).where(UserCharacter.user_id == user.id)
        ).all()
        owned_ids = {item.character_id for item in characters}
        favorite_ids = {
            item.character_id for item in characters if item.is_favorite
        }
        favorite_suggestions = MemoryService.favorite_character_suggestions(
            request.message,
            catalog_characters,
            owned_character_ids=owned_ids,
            favorite_character_ids=favorite_ids,
        )
    response = result.model_copy(
        update={
            "conversation_id": UUID(conversation.id) if conversation else None,
            "memory_suggestions": suggestions,
            "favorite_character_suggestions": favorite_suggestions,
            "related_entities": related_entities,
        }
    )

    if conversation:
        message_time = datetime.now(timezone.utc)
        database.add_all(
            [
                ChatMessage(
                    conversation_id=conversation.id,
                    role="user",
                    content=request.message,
                    created_at=message_time,
                ),
                ChatMessage(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=response.answer,
                    response_payload=response.model_dump(mode="json"),
                    created_at=message_time + timedelta(microseconds=1),
                ),
            ]
        )
        conversation.updated_at = message_time + timedelta(microseconds=1)
        care_cue_service.update_care_cue(database, conversation, request.message)
        if commit:
            database.commit()

    if user and conversation:
        # Judge 可能在响应返回后继续运行，不能持有即将关闭的请求 Session。
        _spawn_memory_judge(
            PgMemoryRepository(request_session_factory),
            str(user.id),
            idle_gap_seconds,
        )
    return response


def _job_response(job: ChatJob) -> ChatJobResponse:
    return ChatJobResponse(
        id=job.id,
        conversation_id=job.conversation_id,
        status=job.status,
        message=str(job.request_payload.get("message") or ""),
        response=(
            AIResponse.model_validate(job.response_payload)
            if job.response_payload
            else None
        ),
        partial_answer=job.partial_answer or "",
        progress=job.progress_payload or {},
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
    )


def _append_job_event(
    database: Session,
    job: ChatJob,
    event_type: str,
    title: str,
    *,
    agent: str | None = None,
    detail: str = "",
    event_status: str = "running",
    duration_ms: int | None = None,
    payload: dict[str, object] | None = None,
    progress: dict[str, object] | None = None,
) -> ChatJobEvent:
    last_sequence = database.scalar(
        select(func.max(ChatJobEvent.sequence)).where(ChatJobEvent.job_id == job.id)
    )
    event = ChatJobEvent(
        job_id=job.id,
        sequence=int(last_sequence or 0) + 1,
        event_type=event_type,
        agent=agent,
        title=title,
        detail=detail,
        status=event_status,
        duration_ms=duration_ms,
        payload=payload or {},
    )
    database.add(event)
    if progress is not None:
        job.progress_payload = progress
    database.flush()
    return event


def _safe_agent_name(response: AIResponse) -> str:
    return next(
        (
            name
            for name in response.invoked_agents
            if name not in {"herta_main_agent", "router_agent"}
        ),
        response.agent,
    )


def _append_job_event_once(
    database: Session,
    job: ChatJob,
    event_type: str,
    title: str,
    **kwargs,
) -> ChatJobEvent | None:
    exists = database.scalar(
        select(ChatJobEvent.id)
        .where(
            ChatJobEvent.job_id == job.id,
            ChatJobEvent.event_type == event_type,
        )
        .limit(1)
    )
    if exists:
        return None
    return _append_job_event(
        database,
        job,
        event_type,
        title,
        **kwargs,
    )


async def run_chat_job(
    job_id: str,
    agent: BaseAgent,
    session_factory: sessionmaker,
) -> None:
    with session_factory() as database:
        job = database.get(ChatJob, job_id)
        if job is None or job.status not in {"queued", "running"}:
            return
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.error_message = None
        # 旁白事件按引擎区分：FC 链路的过程叙事由 agent 自身的 fc.* 事件承载，
        # 旧的"意图/专业 Agent/检索/验证"四步旁白只属于 react/herta 旧管线。
        is_fc = getattr(agent, "name", "") == "fc_main_agent"
        _append_job_event(
            database,
            job,
            "job.running",
            "后台问答开始执行",
            agent="fc_main_agent" if is_fc else "herta_main_agent",
            progress={
                "stage": "routing",
                "percent": 5,
                "agent": "fc_main_agent" if is_fc else "router_agent",
            },
        )
        if not is_fc:
            _append_job_event(
                database,
                job,
                "intent.started",
                "正在理解问题并识别意图",
                agent="router_agent",
                progress={"stage": "intent", "percent": 10, "agent": "router_agent"},
            )
        database.commit()
        try:
            user = database.get(User, job.user_id)
            if user is None:
                raise ValueError("任务用户不存在")
            request = ChatRequest.model_validate(job.request_payload)

            async def record_event(
                event_type: str,
                title: str,
                **kwargs,
            ) -> None:
                current_job = database.get(ChatJob, job_id)
                if current_job is None:
                    return
                _append_job_event(
                    database,
                    current_job,
                    event_type,
                    title,
                    **kwargs,
                )
                database.commit()

            delta_flusher = _DeltaFlusher(job_id, session_factory)
            job_memory_repo = PgMemoryRepository(session_factory)
            slow_runner = SlowTaskRunner(agent, session_factory, memory_repo=job_memory_repo)

            def _task_submitter(tool_name: str, args: dict, base_context: AgentContext) -> str:
                return slow_runner.submit(
                    tool_name=tool_name,
                    args=args,
                    base_context=base_context,
                    event_sink=record_event,
                    delta_sink=delta_flusher.sink,
                )

            response = await _execute_message(
                request,
                agent,
                user,
                database,
                commit=False,
                event_sink=record_event,
                delta_sink=delta_flusher.sink,
                task_submitter=_task_submitter,
            )
            job = database.get(ChatJob, job_id)
            if job is None:
                return
            selected_agent = _safe_agent_name(response)
            if is_fc:
                # FC 链路：过程叙事已由 fc.* 事件承载，跳过旧管线旁白
                database.commit()
            else:
                router_step = next(
                    (step for step in response.query_steps if step.id == "router"),
                    None,
                )
                _append_job_event_once(
                    database,
                    job,
                    "intent.completed",
                    "意图识别完成",
                    agent="router_agent",
                    detail=router_step.detail if router_step else "已完成语义路由。",
                    event_status="completed",
                    duration_ms=router_step.duration_ms if router_step else None,
                    progress={
                        "stage": "agent",
                        "percent": 35,
                        "agent": selected_agent,
                    },
                )
                _append_job_event_once(
                    database,
                    job,
                    "agent.selected",
                    "已选择专业 Agent",
                    agent=selected_agent,
                    detail=f"本轮由 {selected_agent} 处理，再交给黑塔主 Agent 组织回答。",
                    event_status="completed",
                    payload={"invoked_agents": response.invoked_agents},
                    progress={
                        "stage": "retrieval",
                        "percent": 50,
                        "agent": selected_agent,
                    },
                )
                _append_job_event_once(
                    database,
                    job,
                    "agent.completed",
                    "专业 Agent 已完成处理",
                    agent=selected_agent,
                    event_status="completed",
                )
                _append_job_event_once(
                    database,
                    job,
                    "retrieval.completed",
                    "知识检索完成",
                    agent=selected_agent,
                    detail=f"获得 {len(response.citations)} 条可引用证据。",
                    event_status="completed",
                    payload={"evidence_count": len(response.citations)},
                    progress={
                        "stage": "validation",
                        "percent": 70,
                        "agent": selected_agent,
                    },
                )
                _append_job_event(
                    database,
                    job,
                    "validation.completed",
                    "证据验证完成",
                    agent=selected_agent,
                    detail="；".join(response.validation.notes[:3]),
                    event_status="completed",
                    payload={
                        "validation_status": response.validation.status,
                        "evidence_count": response.validation.evidence_count,
                    },
                    progress={
                        "stage": "filtering",
                        "percent": 80,
                        "agent": selected_agent,
                    },
                )
                _append_job_event(
                    database,
                    job,
                    "filtering.completed",
                    "低可信内容过滤完成",
                    agent=selected_agent,
                    detail="；".join(response.filtering.warnings[:3]),
                    event_status="completed",
                    payload={
                        "passed": response.filtering.passed,
                        "removed_claims": response.filtering.removed_claims,
                    },
                    progress={
                        "stage": "answer",
                        "percent": 88,
                        "agent": "herta_main_agent",
                    },
                )
                database.commit()

            answer = response.answer
            if delta_flusher.streamed_chars > 0:
                # 真流式已完成逐字推送：冲刷剩余增量并保证 partial_answer 一致
                await delta_flusher.finalize(answer)
            else:
                # 非流式引擎（react 等）：保留原有的答后切片行为
                job.partial_answer = ""
                chunk_size = 48
                for offset in range(0, len(answer), chunk_size):
                    chunk = answer[offset : offset + chunk_size]
                    job.partial_answer = f"{job.partial_answer or ''}{chunk}"
                    _append_job_event(
                        database,
                        job,
                        "answer.delta",
                        "黑塔正在组织最终回答",
                        agent="herta_main_agent",
                        payload={"delta": chunk},
                        progress={
                            "stage": "answer",
                            "percent": min(
                                98,
                                88 + int((offset + len(chunk)) / max(len(answer), 1) * 10),
                            ),
                            "agent": "herta_main_agent",
                        },
                    )
                    database.commit()
                    await asyncio.sleep(0)

            # 慢任务收尾（Phase 4.2）：等待后台结果并用人格转述；job 在此之前保持 running
            followup = await slow_runner.run_followups(
                event_sink=record_event,
                delta_sink=delta_flusher.sink,
                user_id=user.id if user else None,
                conversation_id=str(response.conversation_id) if response.conversation_id else None,
            )
            if followup is not None:
                response = followup
                await delta_flusher.flush()
                job.partial_answer = delta_flusher.partial_text
            _append_job_event(
                database,
                job,
                "answer.completed",
                "最终回答生成完成",
                agent="herta_main_agent",
                event_status="completed",
            )
            job.status = "completed"
            job.response_payload = response.model_dump(mode="json")
            job.completed_at = datetime.now(timezone.utc)
            _append_job_event(
                database,
                job,
                "job.completed",
                "后台问答已完成",
                agent="herta_main_agent",
                event_status="completed",
                progress={
                    "stage": "completed",
                    "percent": 100,
                    "agent": "herta_main_agent",
                },
            )
            database.commit()
            # 任务完成后异步补刷长对话摘要：不需要等下一条用户消息。
            try:
                summary_conversation = (
                    database.get(Conversation, str(response.conversation_id))
                    if response.conversation_id
                    else None
                )
                if summary_conversation and should_refresh(
                    summary_conversation,
                    _count_messages(database, summary_conversation.id),
                ):
                    await build_context_summary(
                        database,
                        summary_conversation,
                        get_fast_llm_provider(),
                    )
            except Exception:  # noqa: BLE001 - 摘要补刷失败不影响任务结果
                pass
        except Exception:
            logger.exception("后台问答执行失败（job_id=%s）", job_id)
            database.rollback()
            failed = database.get(ChatJob, job_id)
            if failed is not None:
                failed.status = "failed"
                failed.error_message = "AI回答失败，请稍后重试。"
                failed.completed_at = datetime.now(timezone.utc)
                _append_job_event(
                    database,
                    failed,
                    "job.failed",
                    "后台问答执行失败",
                    agent="herta_main_agent",
                    event_status="failed",
                    progress={
                        "stage": "failed",
                        "percent": 100,
                        "agent": "herta_main_agent",
                    },
                )
                database.commit()


class _DeltaFlusher:
    """真流式（Phase 4.1）：把 FC 循环的逐字增量合并成 answer.delta 事件落库。

    合并策略：未冲刷 ≥64 字或距上次冲刷 ≥0.5s 先到先刷——事件行数可控，
    端到端延迟 ≈ 冲刷间隔 + SSE 轮询 250ms。partial_answer 始终保存已流出
    的完整文本；前端在流结束后用它整体替换，任何漂移自愈。
    写库走同步调用（与 record_event 同模式，同事件循环内串行，避免双线程
    抢 job+sequence 撞唯一约束）。"""

    FLUSH_CHARS = 64
    FLUSH_INTERVAL = 0.5

    def __init__(self, job_id: str, session_factory: sessionmaker) -> None:
        self.job_id = job_id
        self.session_factory = session_factory
        self._pending: list[str] = []
        self._streamed_text = ""
        self._last_flush = time.monotonic()

    @property
    def streamed_chars(self) -> int:
        return len(self._streamed_text)

    @property
    def partial_text(self) -> str:
        return self._streamed_text

    async def sink(self, delta: str) -> None:
        if not delta:
            return
        self._pending.append(delta)
        pending_len = sum(len(piece) for piece in self._pending)
        if pending_len >= self.FLUSH_CHARS or time.monotonic() - self._last_flush >= self.FLUSH_INTERVAL:
            await self.flush()

    async def flush(self) -> None:
        chunk = "".join(self._pending)
        self._pending.clear()
        if not chunk:
            self._last_flush = time.monotonic()
            return
        self._streamed_text += chunk
        self._last_flush = time.monotonic()

        with self.session_factory() as database:
            job = database.get(ChatJob, self.job_id)
            if job is None:
                return
            _append_job_event(
                database,
                job,
                "answer.delta",
                "黑塔正在组织最终回答",
                agent="fc_main_agent",
                payload={"delta": chunk},
                progress={
                    "stage": "answer",
                    "percent": min(97, 88 + len(self._streamed_text) // 64),
                },
            )
            job.partial_answer = self._streamed_text
            database.commit()

    async def finalize(self, final_answer: str) -> None:
        """流结束：冲刷剩余增量；最终答案与已流出文本有偏差（流式失败回退等）时
        补发差额或整段，保证 partial_answer 与最终回答一致。"""
        await self.flush()
        if final_answer == self._streamed_text:
            return
        if final_answer.startswith(self._streamed_text):
            tail = final_answer[len(self._streamed_text) :]
        else:
            tail = final_answer  # 漂移：整段补发，前端完成后以 partial_answer 校正

        with self.session_factory() as database:
            job = database.get(ChatJob, self.job_id)
            if job is None:
                return
            _append_job_event(
                database,
                job,
                "answer.delta",
                "最终回答补齐",
                agent="fc_main_agent",
                payload={"delta": tail},
                progress={"stage": "answer", "percent": 98},
            )
            job.partial_answer = final_answer
            database.commit()
        self._streamed_text = final_answer


def recover_chat_jobs(
    agent: BaseAgent,
    session_factory: sessionmaker,
) -> list[asyncio.Task[None]]:
    try:
        with session_factory() as database:
            jobs = database.scalars(
                select(ChatJob).where(ChatJob.status.in_(("queued", "running")))
            ).all()
            for job in jobs:
                job.status = "queued"
                _append_job_event(
                    database,
                    job,
                    "job.recovered",
                    "服务重启后已恢复任务",
                    agent="herta_main_agent",
                    event_status="completed",
                    progress={
                        "stage": "queued",
                        "percent": 0,
                        "agent": "herta_main_agent",
                    },
                )
            database.commit()
            job_ids = [job.id for job in jobs]
    except SQLAlchemyError:
        return []
    return [
        schedule_chat_job(job_id, agent, session_factory)
        for job_id in job_ids
    ]


def schedule_chat_job(
    job_id: str,
    agent: BaseAgent,
    session_factory: sessionmaker,
) -> asyncio.Task[None]:
    task = asyncio.create_task(run_chat_job(job_id, agent, session_factory))
    _active_job_tasks.add(task)
    task.add_done_callback(_active_job_tasks.discard)
    return task


def active_chat_job_tasks() -> list[asyncio.Task[None]]:
    return list(_active_job_tasks)


@router.post(
    "/jobs",
    response_model=ChatJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_chat_job(
    request: ChatRequest,
    agent: BaseAgent = Depends(get_herta_main_agent),
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> ChatJobResponse:
    if request.conversation_id:
        conversation = _owned_conversation(
            database, user.id, str(request.conversation_id)
        )
    else:
        conversation = Conversation(
            user_id=user.id,
            title=request.message.strip()[:80],
        )
        database.add(conversation)
        database.flush()
    normalized_request = request.model_copy(
        update={"conversation_id": UUID(conversation.id)}
    )
    job = ChatJob(
        user_id=user.id,
        conversation_id=conversation.id,
        request_payload=normalized_request.model_dump(mode="json"),
        progress_payload={
            "stage": "queued",
            "percent": 0,
            "agent": "herta_main_agent",
        },
    )
    database.add(job)
    database.flush()
    _append_job_event(
        database,
        job,
        "job.queued",
        "问题已进入后台队列",
        agent="herta_main_agent",
        progress={
            "stage": "queued",
            "percent": 0,
            "agent": "herta_main_agent",
        },
    )
    database.commit()
    database.refresh(job)
    factory = sessionmaker(
        bind=database.get_bind(),
        autoflush=False,
        expire_on_commit=False,
    )
    schedule_chat_job(job.id, agent, factory)
    return _job_response(job)


@router.get("/jobs", response_model=ChatJobListResponse)
def list_chat_jobs(
    job_status: str | None = Query(default=None, alias="status"),
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> ChatJobListResponse:
    if job_status and job_status not in {"queued", "running", "completed", "failed"}:
        raise HTTPException(status_code=422, detail="不支持的任务状态")
    query = select(ChatJob).where(ChatJob.user_id == user.id)
    if job_status:
        query = query.where(ChatJob.status == job_status)
    jobs = database.scalars(query.order_by(ChatJob.created_at.desc()).limit(50)).all()
    return ChatJobListResponse(
        items=[_job_response(job) for job in jobs],
        total=len(jobs),
    )


def _owned_job(database: Session, user_id: str, job_id: str) -> ChatJob:
    job = database.scalar(
        select(ChatJob).where(ChatJob.id == job_id, ChatJob.user_id == user_id)
    )
    if job is None:
        raise HTTPException(status_code=404, detail="问答任务不存在")
    return job


@router.get("/jobs/{job_id}", response_model=ChatJobResponse)
def get_chat_job(
    job_id: str,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> ChatJobResponse:
    return _job_response(_owned_job(database, user.id, job_id))


@router.get(
    "/jobs/{job_id}/events",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "按顺序推送公开的 Agent 执行事件与回答增量。",
            "content": {"text/event-stream": {}},
        }
    },
)
def stream_chat_job_events(
    job_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> StreamingResponse:
    _owned_job(database, user.id, job_id)
    try:
        after_sequence = max(0, int(last_event_id or 0))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Last-Event-ID 必须是整数") from exc
    factory = sessionmaker(
        bind=database.get_bind(),
        autoflush=False,
        expire_on_commit=False,
    )

    async def event_stream():
        cursor = after_sequence
        idle_rounds = 0
        while True:
            with factory() as event_database:
                job = event_database.scalar(
                    select(ChatJob).where(
                        ChatJob.id == job_id,
                        ChatJob.user_id == user.id,
                    )
                )
                if job is None:
                    return
                events = event_database.scalars(
                    select(ChatJobEvent)
                    .where(
                        ChatJobEvent.job_id == job_id,
                        ChatJobEvent.sequence > cursor,
                    )
                    .order_by(ChatJobEvent.sequence)
                ).all()
                terminal = job.status in {"completed", "failed"}
                for event in events:
                    cursor = event.sequence
                    payload = ChatJobEventResponse.model_validate(event).model_dump(
                        mode="json"
                    )
                    yield (
                        f"id: {event.sequence}\n"
                        f"event: {event.event_type}\n"
                        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    )
            if terminal and not events:
                return
            if events:
                idle_rounds = 0
            else:
                idle_rounds += 1
                if idle_rounds % 60 == 0:
                    yield ": keep-alive\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/jobs/{job_id}/retry",
    response_model=ChatJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_chat_job(
    job_id: str,
    agent: BaseAgent = Depends(get_herta_main_agent),
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> ChatJobResponse:
    job = _owned_job(database, user.id, job_id)
    if job.status != "failed":
        raise HTTPException(status_code=409, detail="只有失败任务可以重试")
    job.status = "queued"
    job.error_message = None
    job.response_payload = None
    job.partial_answer = None
    job.completed_at = None
    _append_job_event(
        database,
        job,
        "job.queued",
        "失败任务已重新进入队列",
        agent="herta_main_agent",
        progress={
            "stage": "queued",
            "percent": 0,
            "agent": "herta_main_agent",
        },
    )
    database.commit()
    database.refresh(job)
    factory = sessionmaker(
        bind=database.get_bind(),
        autoflush=False,
        expire_on_commit=False,
    )
    schedule_chat_job(job.id, agent, factory)
    return _job_response(job)
