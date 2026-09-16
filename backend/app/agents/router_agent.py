import asyncio
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from app.agents.answer_review_agent import AnswerReviewAgent, SubtaskResult
from app.agents.capability import is_capability_question
from app.agents.base import AgentContext, BaseAgent
from app.agents.activity_strategy_agent import ActivityStrategyAgent
from app.agents.character_build_agent import CharacterBuildAgent
from app.agents.conversation_agent import ConversationAgent
from app.agents.custom_character_agent import CustomCharacterAgent
from app.agents.custom_character_review_agent import (
    ChatCustomCharacterReviewAgent,
)
from app.agents.intent_analyzer import IntentAnalyzer, IntentSubtask
from app.agents.material_query_agent import MaterialQueryAgent
from app.agents.memory_agent import MemoryAgent
from app.agents.rag_agent import RAGAgent
from app.agents.registry import (
    AgentRegistry,
    build_agent_registry,
    default_keyword_routes,
)
from app.agents.story_analysis_agent import StoryAnalysisAgent
from app.agents.team_recommendation_agent import TeamRecommendationAgent
from app.agents.weekly_planning_agent import WeeklyPlanningAgent
from app.llm.base import LLMProvider
from app.schemas.ai_response import AIResponse, QueryStep


class RouterAgent(BaseAgent):
    name = "router_agent"
    description = "识别用户意图并分发到独立业务 Agent"

    def __init__(
        self,
        rag_agent: RAGAgent,
        docs_root: Path | None = None,
        intent_llm: LLMProvider | None = None,
        reasoning_llm: LLMProvider | None = None,
        draft_provider=None,
    ) -> None:
        self.rag_agent = rag_agent
        self.intent_analyzer = (
            IntentAnalyzer(intent_llm, fallback_llm=reasoning_llm)
            if intent_llm
            else None
        )
        root = docs_root or rag_agent.docs_root
        self.custom_character_agent = CustomCharacterAgent()
        self.conversation_agent = ConversationAgent()
        self.memory_agent = MemoryAgent()
        self.weekly_planning_agent = WeeklyPlanningAgent()
        self.answer_review_agent = AnswerReviewAgent(reasoning_llm)
        agents_by_intent: dict[str, BaseAgent] = {
            "conversation": self.conversation_agent,
            "conversation_recall": self.conversation_agent,
            "knowledge_qa": rag_agent,
            "story_analysis": StoryAnalysisAgent(rag_agent),
            "custom_character_creation": self.custom_character_agent,
            "custom_team_recommendation": self.custom_character_agent,
            "memory": self.memory_agent,
            "weekly_plan": self.weekly_planning_agent,
            "custom_character_review": ChatCustomCharacterReviewAgent(
                draft_provider,
                reasoning_llm,
            ),
        }
        structured_agent = getattr(
            rag_agent, "structured_character_agent", None
        )
        if structured_agent:
            agents_by_intent["structured_lookup"] = structured_agent
        if root:
            agents_by_intent.update(
                {
                    "team_recommendation": TeamRecommendationAgent(
                        root, reasoning_llm
                    ),
                    "character_build": CharacterBuildAgent(root, rag_agent),
                    "material_query": MaterialQueryAgent(root, rag_agent),
                    "activity_strategy": ActivityStrategyAgent(
                        root, reasoning_llm
                    ),
                }
            )
        self.registry: AgentRegistry = build_agent_registry(agents_by_intent)
        self.agents: dict[str, BaseAgent] = {
            intent: agent
            for intent, agent in agents_by_intent.items()
        }

    def agent_for_intent(self, intent: str) -> BaseAgent:
        return self.registry.agent_for_intent(intent)

    async def run(self, context: AgentContext) -> AIResponse:
        started = perf_counter()
        original_message = context.message
        planned_subtasks: list[IntentSubtask] = []
        status = "fallback"
        detail = ""
        if is_capability_question(original_message):
            # 自我认知询问（"你能做什么""配队是干嘛的"）：由闲聊 Agent
            # 基于能力注册表回答，不进功能 Agent，避免"问配队是干嘛的"
            # 被当成真的要生成配队。
            context.intent = "conversation"
            context.intent_metadata = {
                "confidence": 1.0,
                "needs_retrieval": False,
                "reason": "用户在询问系统能力或功能用法，按自我认知回答。",
                "answer_depth": "concise",
                "clarification_question": None,
                "task_mode": "capability_intro",
                "referenced_character_ids": [],
            }
            status = "completed"
            detail = "识别为系统能力询问，基于能力注册表回答。"
        elif self._is_ambiguous_xingqiong_term(original_message):
            context.intent = "conversation"
            context.intent_metadata = {
                "confidence": 1.0,
                "needs_retrieval": False,
                "reason": "“星穹”可能指星琼、星穹列车或标题用语，必须先澄清。",
                "answer_depth": "concise",
                "clarification_question": None,
                "task_mode": "ambiguous_catalog_term",
                "referenced_character_ids": [],
            }
            status = "completed"
            detail = "检测到容易与物品“星琼”混淆的术语，暂停检索并请求澄清。"
        elif self._is_assistant_identity_question(original_message):
            context.intent = "conversation"
            context.intent_metadata = {
                "confidence": 1.0,
                "needs_retrieval": False,
                "reason": "用户在询问当前助手身份，不是在查询游戏角色档案。",
                "answer_depth": "concise",
                "clarification_question": None,
                "task_mode": "assistant_identity",
                "referenced_character_ids": [],
            }
            status = "completed"
            detail = "确定为助手身份询问，无需调用知识库。"
        elif self.intent_analyzer:
            try:
                decision = await self.intent_analyzer.analyze(context)
                if decision.confidence < 0.55:
                    raise ValueError("intent confidence below threshold")
                explicit_entities = context.entities.get(
                    "mentioned_characters", []
                )
                explicit_ids = {
                    str(item.get("character_id", ""))
                    for item in explicit_entities
                }
                referenced_ids = [
                    item
                    for item in dict.fromkeys(
                        decision.referenced_character_ids
                    )
                    if item in explicit_ids
                ]
                context.intent = decision.intent
                context.intent_metadata = {
                    "confidence": decision.confidence,
                    "needs_retrieval": decision.needs_retrieval,
                    "reason": decision.reason,
                    "answer_depth": decision.answer_depth,
                    "clarification_question": decision.clarification_question,
                    "task_mode": decision.task_mode,
                    "referenced_character_ids": referenced_ids,
                }
                planned_subtasks = self._safe_subtasks(
                    decision.subtasks,
                    explicit_entities,
                )
                if len(planned_subtasks) < 2:
                    planned_subtasks = (
                        self._deterministic_subtasks(
                            original_message,
                            explicit_entities,
                        )
                        or planned_subtasks
                    )
                if len(planned_subtasks) < 2:
                    planned_subtasks = self._compound_fallback_subtasks(
                        original_message
                    )
                context.intent_metadata["subtasks"] = [
                    task.model_dump() for task in planned_subtasks
                ]
                if len(planned_subtasks) < 2:
                    context.message = self._safe_standalone_query(
                        original_message,
                        decision.standalone_query,
                        explicit_entities,
                    )
                status = "completed"
                detail = (
                    f"{self.intent_analyzer.llm.name} 判断语义意图为 "
                    f"{decision.intent}，回答深度 {decision.answer_depth}，置信度 "
                    f"{decision.confidence:.2f}；{decision.reason}"
                    + (
                        f"；已拆解为 {len(planned_subtasks)} 个子任务"
                        if len(planned_subtasks) >= 2
                        else ""
                    )
                )
            except Exception as exc:
                context.intent = self.classify_intent(context.message)
                context.intent_metadata = self._fallback_metadata(context)
                planned_subtasks = self._deterministic_subtasks(
                    original_message,
                    context.entities.get("mentioned_characters", []),
                )
                detail = (
                    "语义意图模型不可用，已回退确定性规则；"
                    f"原因：{type(exc).__name__}。"
                )
        else:
            context.intent = self.classify_intent(context.message)
            context.intent_metadata = self._fallback_metadata(context)
            planned_subtasks = self._deterministic_subtasks(
                original_message,
                context.entities.get("mentioned_characters", []),
            )
            detail = "未配置意图模型，使用确定性规则完成路由。"
        target = (
            self.answer_review_agent
            if len(planned_subtasks) >= 2
            else self.agent_for_intent(context.intent)
        )
        routing_duration_ms = int((perf_counter() - started) * 1000)
        await context.emit_event(
            "intent.completed",
            "意图识别完成",
            agent=self.name,
            detail=detail,
            event_status=status,
            duration_ms=routing_duration_ms,
            payload={
                "intent": context.intent,
                "confidence": context.intent_metadata.get("confidence"),
            },
            progress={
                "stage": "agent",
                "percent": 30,
                "agent": target.name,
            },
        )
        await context.emit_event(
            "agent.selected",
            "已选择专业 Agent",
            agent=target.name,
            detail=f"Router 将本轮问题交给 {target.name}。",
            event_status="completed",
            progress={
                "stage": "agent",
                "percent": 36,
                "agent": target.name,
            },
        )
        await context.emit_event(
            "agent.started",
            "专业 Agent 开始处理",
            agent=target.name,
            progress={
                "stage": "agent",
                "percent": 42,
                "agent": target.name,
            },
        )
        if len(planned_subtasks) >= 2:
            response = await self._run_compound(
                original_message,
                context,
                planned_subtasks,
            )
        else:
            response = await target.run(context)
            if context.intent not in self._review_skip_intents():
                response = await self.answer_review_agent.review_single(
                    original_message,
                    IntentSubtask(
                        intent=context.intent,
                        standalone_query=context.message,
                        needs_retrieval=bool(
                            context.intent_metadata.get("needs_retrieval", True)
                        ),
                        task_mode=context.intent_metadata.get(
                            "task_mode", "other"
                        ),
                        answer_depth=context.intent_metadata.get(
                            "answer_depth", "standard"
                        ),
                        reason=str(
                            context.intent_metadata.get("reason") or ""
                        ),
                        referenced_character_ids=list(
                            context.intent_metadata.get(
                                "referenced_character_ids", []
                            )
                        ),
                    ),
                    response,
                )
        await context.emit_event(
            "agent.completed",
            "专业 Agent 已完成处理",
            agent=target.name,
            event_status="completed",
            progress={
                "stage": "validation",
                "percent": 68,
                "agent": target.name,
            },
        )
        router_step = QueryStep(
            id="router",
            name="语义理解与意图路由",
            status=status,
            detail=f"{detail} 路由到 {target.name}。",
            duration_ms=routing_duration_ms,
        )
        return response.model_copy(
            update={"query_steps": [router_step, *response.query_steps]}
        )

    async def _run_compound(
        self,
        original_message: str,
        context: AgentContext,
        tasks: list[IntentSubtask],
    ) -> AIResponse:
        async def execute(task: IntentSubtask) -> SubtaskResult:
            subtask_entities = dict(context.entities)
            catalog_entities = [
                item
                for item in context.entities.get(
                    "mentioned_catalog_entities", []
                )
                if str(item.get("name") or "") in task.standalone_query
            ]
            if catalog_entities:
                subtask_entities["mentioned_catalog_entities"] = (
                    catalog_entities
                )
                subtask_entities["mentioned_characters"] = [
                    {
                        "character_id": item.get("character_id")
                        or item.get("entity_id"),
                        "name": item.get("name"),
                    }
                    for item in catalog_entities
                    if item.get("entity_type") == "hsr_character"
                ]
            subcontext = replace(
                context,
                message=task.standalone_query,
                intent=task.intent,
                intent_metadata={
                    "confidence": context.intent_metadata.get("confidence"),
                    "needs_retrieval": task.needs_retrieval,
                    "reason": task.reason,
                    "answer_depth": task.answer_depth,
                    "clarification_question": None,
                    "task_mode": task.task_mode,
                    "referenced_character_ids": task.referenced_character_ids,
                },
                entities=subtask_entities,
            )
            response = await self.agent_for_intent(task.intent).run(subcontext)
            return SubtaskResult(task=task, response=response)

        results = await asyncio.gather(*(execute(task) for task in tasks))
        return await self.answer_review_agent.review(
            original_message, results
        )

    @classmethod
    def _compound_fallback_subtasks(cls, message: str) -> list[IntentSubtask]:
        """模型声称需要拆分却返回空 subtasks 时的确定性兜底。

        只在消息同时命中两个及以上"强任务意图"关键词时才拆分，
        避免把普通单目标消息误拆成碎片。
        """
        strong_intents = {
            "custom_team_recommendation",
            "custom_character_creation",
            "custom_character_review",
            "team_recommendation",
            "activity_strategy",
            "material_query",
            "character_build",
            "story_analysis",
            "weekly_plan",
        }
        profile_signals = ("介绍", "是谁", "简介", "什么角色", "基本信息")
        matched: list[str] = []
        for keywords, intent in default_keyword_routes():
            if intent in strong_intents and any(
                keyword in message for keyword in keywords
            ):
                if intent not in matched:
                    matched.append(intent)
        asks_profile = any(signal in message for signal in profile_signals)
        if asks_profile and "knowledge_qa" not in matched:
            # “介绍/是谁”类查询信号与一个强任务意图同时出现时按复合处理。
            if len(matched) >= 1:
                matched.append("knowledge_qa")
        if len(matched) < 2:
            return []
        return [
            IntentSubtask(
                intent=intent,
                standalone_query=message,
                needs_retrieval=intent != "memory",
                task_mode=cls.task_mode_for(message, intent),
                answer_depth="standard",
                reason="确定性规则：模型拆解缺失，按消息中的多个任务目标兜底拆分。",
            )
            for intent in matched
        ]

    @classmethod
    def _deterministic_subtasks(
        cls,
        message: str,
        explicit_entities: list[dict],
    ) -> list[IntentSubtask]:
        """为最常见的复合角色问法提供不依赖模型的拆解兜底。"""
        if len(explicit_entities) != 1:
            return []
        entity = explicit_entities[0]
        character_id = str(entity.get("character_id") or "").strip()
        character_name = str(entity.get("name") or "").strip()
        if not character_id or not character_name:
            return []
        asks_profile = any(
            token in message
            for token in (
                "是谁",
                "介绍",
                "简介",
                "什么角色",
                "基本信息",
                "角色信息",
            )
        )
        asks_skills = any(
            token in message
            for token in (
                "技能",
                "普攻",
                "战技",
                "终结技",
                "天赋",
                "秘技",
                "忆灵技",
                "欢愉技",
            )
        )
        if not (asks_profile and asks_skills):
            return []
        answer_depth = (
            "detailed"
            if any(token in message for token in ("详细", "完整", "全部"))
            else "standard"
        )
        common = {
            "intent": "knowledge_qa",
            "needs_retrieval": True,
            "task_mode": "single_character_fact",
            "answer_depth": answer_depth,
            "reason": "确定性规则识别到同一角色的身份与技能两个目标。",
            "referenced_character_ids": [character_id],
        }
        return [
            IntentSubtask(
                standalone_query=f"{character_name}是谁？",
                **common,
            ),
            IntentSubtask(
                standalone_query=f"{character_name}的技能是什么？",
                **common,
            ),
        ]

    @classmethod
    def _safe_subtasks(
        cls,
        tasks: list[IntentSubtask],
        explicit_entities: list[dict],
    ) -> list[IntentSubtask]:
        explicit_ids = {
            str(item.get("character_id", ""))
            for item in explicit_entities
            if item.get("character_id")
        }
        safe: list[IntentSubtask] = []
        seen: set[tuple[str, str]] = set()
        for task in tasks[:4]:
            query = cls._safe_standalone_query(
                task.standalone_query,
                task.standalone_query,
                explicit_entities,
            )
            key = (task.intent, query.strip())
            if key in seen:
                continue
            seen.add(key)
            safe.append(
                task.model_copy(
                    update={
                        "standalone_query": query,
                        "referenced_character_ids": [
                            character_id
                            for character_id in dict.fromkeys(
                                task.referenced_character_ids
                            )
                            if character_id in explicit_ids
                        ],
                    }
                )
            )
        return safe

    @staticmethod
    def classify_intent(message: str) -> str:
        normalized = message.strip()
        if RouterAgent._is_assistant_identity_question(message):
            return "conversation"
        fallback_routes = default_keyword_routes()
        # “攻略/怎么打”在关键词表中优先归入知识问答，避免被活动意图吞掉。
        knowledge_routes = tuple(
            (keywords, intent)
            for keywords, intent in fallback_routes
            if intent == "knowledge_qa"
        )
        routes = tuple(
            (keywords, intent)
            for keywords, intent in fallback_routes
            if intent != "knowledge_qa"
        ) + knowledge_routes
        for keywords, intent in routes:
            if any(keyword in message for keyword in keywords):
                return intent
        if normalized in {"hi", "hello", "hey"}:
            return "conversation"
        return "knowledge_qa"

    @staticmethod
    def _review_skip_intents() -> set[str]:
        """跳过最终答案相关性复核的意图。

        自查报告本身即任务产物、不引用知识库证据，相关性复核会误判并
        替换回答；对话类意图同理。
        """
        return {"conversation", "conversation_recall", "custom_character_review"}

    @staticmethod
    def _is_assistant_identity_question(message: str) -> bool:
        normalized = message.strip().replace("？", "?")
        return (
            "你是" in normalized
            and any(token in normalized for token in ("还是", "或者", "or"))
            and "黑塔" in normalized
        )

    @staticmethod
    def _is_ambiguous_xingqiong_term(message: str) -> bool:
        normalized = message.strip().replace("？", "?").lower()
        if "星琼" in normalized or "星穹列车" in normalized or "星穹铁道" in normalized:
            return False
        return "星穹" in normalized and any(
            token in normalized for token in ("是什么", "指什么", "什么意思")
        )

    @staticmethod
    def task_mode_for(message: str, intent: str) -> str:
        if RouterAgent._is_assistant_identity_question(message):
            return "assistant_identity"
        if intent == "team_recommendation":
            return "team_synergy"
        if intent == "character_build":
            return "build_planning"
        if intent == "story_analysis":
            return (
                "character_relationship"
                if any(
                    token in message
                    for token in ("关系", "认识", "互动", "联系")
                )
                else "story_detail"
            )
        if intent == "conversation_recall":
            return "conversation_recall"
        if intent == "weekly_plan":
            return "weekly_planning"
        return "other"

    @classmethod
    def _fallback_metadata(cls, context: AgentContext) -> dict:
        return {
            "confidence": None,
            "needs_retrieval": context.intent
            not in {"conversation", "conversation_recall"},
            "reason": "未使用语义模型，按确定性规则路由。",
            "answer_depth": "standard",
            "clarification_question": None,
            "task_mode": cls.task_mode_for(
                context.message, context.intent
            ),
            "referenced_character_ids": [
                str(item.get("character_id", ""))
                for item in context.entities.get(
                    "mentioned_characters", []
                )
                if item.get("character_id")
            ],
        }

    @staticmethod
    def _safe_standalone_query(
        original: str,
        standalone: str,
        explicit_entities: list[dict],
    ) -> str:
        names = [
            str(item.get("name", "")).strip()
            for item in explicit_entities
            if str(item.get("name", "")).strip()
        ]
        if names and not all(name in standalone for name in names):
            return original
        return standalone
