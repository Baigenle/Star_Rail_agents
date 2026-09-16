import json
import re
from time import perf_counter
from zlib import crc32

from pydantic import BaseModel, Field

from app.agents.base import AgentContext, BaseAgent
from app.agents.router_agent import RouterAgent
from app.core.answer_budget import budget_for, soft_trim
from app.llm.base import LLMMessage, LLMProvider
from app.schemas.ai_response import AIResponse, AgentAction, QueryStep
from app.services.follow_up_service import generate_follow_ups


class PersonaFrame(BaseModel):
    opening: str = Field(default="", max_length=100)
    closing: str = Field(default="", max_length=100)


PERSONA_PROMPT = """你是黑塔主 Agent，只负责给已验证的子 Agent 回答添加说话风格。
语气应聪明、自信、直接、略带居高临下，但不恶意羞辱。
你不能改写或复述事实正文，不能添加任何游戏事实、数值、角色设定、建议或引用编号。
opening 和 closing 只能是非事实性的交互话语，每项最多一句；不需要时返回空字符串。
风格要求（本次必须遵守）：{style_directive}
禁止套话：不要使用"先把智库里能确认的内容说清楚""记好了，别再忘了"这类模板开场；
两次不同的回答禁止出现相同开头。根据用户问题的语气自然调整（热情提问可俏皮，
抱怨可毒舌一点，严肃考据可收敛傲慢）。
只返回 JSON：{"opening":"","closing":""}"""

# 风格指令池：按会话+消息哈希轮换，保证多样性且同轮稳定。
STYLE_DIRECTIVES = (
    "用一句轻快的短开场，像随口抖机灵",
    "开场带一点不耐烦的天才傲气，但别骂人",
    "开场先夸用户一句问到点子上了，再自然过渡",
    "开场平淡克制，把傲慢藏在收尾里",
    "开场用反问句式引出回答",
    "开场提一句自己早就知道答案，懒得炫耀",
)


class HertaMainAgent(BaseAgent):
    name = "herta_main_agent"
    description = "面向用户的黑塔人格主 Agent，负责任务编排与统一回答风格"

    def __init__(
        self,
        router_agent: RouterAgent,
        persona_llm: LLMProvider | None = None,
    ) -> None:
        self.router_agent = router_agent
        self.persona_llm = persona_llm

    async def run(self, context: AgentContext) -> AIResponse:
        registry = getattr(self.router_agent, "registry", None)
        manifest = registry.planner_manifest() if registry else []
        await context.emit_event(
            "orchestration.started",
            "主 Agent 接管编排",
            agent=self.name,
            detail=(
                f"黑塔主 Agent 已接管本轮请求；已读取注册表中 "
                f"{len(manifest)} 个专业 Agent 的能力清单，进入调度。"
            ),
            event_status="running",
            progress={"stage": "orchestration", "percent": 8},
            payload={"registered_agents": len(manifest)},
        )

        response = await self.router_agent.run(context)
        started = perf_counter()

        # 页面动作：按注册表声明生成（深链 + 预填）。
        actions = self._build_actions(context, response)
        if actions:
            existing_urls = {action.target_url for action in response.actions}
            response = response.model_copy(
                update={
                    "actions": [
                        *response.actions,
                        *[
                            action
                            for action in actions
                            if action.target_url not in existing_urls
                        ],
                    ]
                }
            )

        frame = await self._persona_frame(context, response)
        delegated_agent = response.agent
        answer = self._grounded_answer(context, response, frame)
        answer = self._expand_with_claims(
            response,
            answer,
            str(context.intent_metadata.get("answer_depth") or "standard"),
        )
        clarification = str(
            context.intent_metadata.get("clarification_question") or ""
        ).strip()
        if clarification:
            answer = f"{answer}\n\n{clarification}"

        # 文本预算：按意图类型软截断（自我认知/功能介绍放宽保证清单完整）。
        # 复合回答按子任务逐个累计预算，避免"简介+技能+材料"类回答被砍尾；
        # 深度取意图层的 answer_depth（detailed ×1.8 / concise ×0.6）。
        task_mode = str(context.intent_metadata.get("task_mode") or "")
        depth = str(context.intent_metadata.get("answer_depth") or "standard")
        if task_mode == "capability_intro":
            answer_budget = 700
        else:
            subtasks = context.intent_metadata.get("subtasks") or []
            answer_budget = budget_for(context.intent, depth)
            if len(subtasks) >= 2:
                answer_budget = max(
                    answer_budget,
                    sum(
                        budget_for(str(task.get("intent") or ""), depth)
                        for task in subtasks
                    ),
                )
        answer = soft_trim(answer, answer_budget)

        # 衍生问题：预算超限时首条固定为"展开"类，呼应渐进式回答策略。
        follow_ups = generate_follow_ups(
            context.intent,
            message=context.message,
            entities=context.entities,
            answer_text=answer,
            depth=str(context.intent_metadata.get("answer_depth") or "standard"),
            task_mode=task_mode,
        )

        step = QueryStep(
            id="herta_response",
            name="黑塔主 Agent 组织回答",
            status="completed",
            detail=(
                f"{self.persona_llm.name} 根据意图组织黑塔式非事实表达；"
                "子 Agent 的有据正文及引用保持原样。"
                if self.persona_llm
                else "使用确定性黑塔引导语；子 Agent 的有据正文及引用保持原样。"
            ),
            duration_ms=int((perf_counter() - started) * 1000),
        )
        orchestrator_step = QueryStep(
            id="herta_orchestration",
            name="黑塔主 Agent 编排汇总",
            status="completed",
            detail=(
                f"编排完成：调度 {delegated_agent}"
                f"{' 等 ' + str(len(response.invoked_agents)) + ' 个 Agent' if len(response.invoked_agents) > 1 else ''}"
                f"，生成 {len(response.actions)} 个页面动作、{len(follow_ups)} 个衍生问题。"
            ),
        )
        await context.emit_event(
            "orchestration.completed",
            "主 Agent 编排完成",
            agent=self.name,
            detail=(
                f"意图 {context.intent or 'unknown'}；"
                f"本轮共 {len(response.invoked_agents)} 个 Agent 参与执行；"
                f"生成 {len(response.actions)} 个页面动作、{len(follow_ups)} 个衍生问题。"
            ),
            event_status="completed",
            progress={"stage": "orchestration", "percent": 100},
            payload={
                "intent": context.intent,
                "invoked_agents": response.invoked_agents,
                "actions": [action.model_dump() for action in response.actions],
            },
        )
        return response.model_copy(
            update={
                "agent": self.name,
                "answer": answer,
                "follow_up_questions": follow_ups,
                "query_steps": [
                    *response.query_steps,
                    orchestrator_step,
                    step,
                ],
                "invoked_agents": list(
                    dict.fromkeys(
                        [
                            delegated_agent,
                            *response.invoked_agents,
                            self.name,
                        ]
                    )
                ),
            }
        )

    def _build_actions(
        self, context: AgentContext, response: AIResponse
    ) -> list[AgentAction]:
        """按注册表声明，为当前意图生成页面动作（深链 + 预填）。

        复合问题按子任务意图逐个匹配，取第一个带动作声明的意图，
        保证"介绍+配队"类回答也能带上配队页深链。
        """
        registry = getattr(self.router_agent, "registry", None)
        if registry is None:
            return []
        candidate_intents = [context.intent]
        subtasks = context.intent_metadata.get("subtasks") or []
        candidate_intents.extend(
            str(task.get("intent") or "") for task in subtasks
        )
        descriptor = None
        for intent in candidate_intents:
            candidate = registry.descriptor_for_intent(intent)
            if candidate.action is not None:
                descriptor = candidate
                break
        if descriptor is None or descriptor.action is None:
            return []
        action_spec = descriptor.action
        params: dict[str, str] = {}
        action_type = "navigate"
        if action_spec.prefill_character:
            character_name = self._first_character_name(context)
            if character_name:
                params["core"] = character_name
                action_type = "prefill"
        return [
            AgentAction(
                action_type=action_type,
                title=action_spec.title,
                target_url=action_spec.url,
                description=action_spec.description,
                params=params,
            )
        ]

    @staticmethod
    def _first_character_name(context: AgentContext) -> str:
        for item in context.entities.get("mentioned_characters", []):
            name = str(item.get("name") or "").strip()
            if name:
                return name
        return ""

    async def _persona_frame(
        self, context: AgentContext, response: AIResponse
    ) -> PersonaFrame:
        # 风格池只服务正常有据回答：拒答、澄清、复核未通过的降级回答
        # 绝不套傲慢开场/收尾，避免"这种问题也值得问？+ 自己动动脑子"式观感。
        is_self_review = response.validation.method == "player_self_review"
        if (
            not self.persona_llm
            or response.agent == "conversation_agent"
            or (not response.claims and not is_self_review)
            or response.validation.status != "verified"
        ):
            return PersonaFrame()
        style_directive = STYLE_DIRECTIVES[
            crc32(
                f"{context.conversation_id or ''}|{context.message}".encode(
                    "utf-8"
                )
            )
            % len(STYLE_DIRECTIVES)
        ]
        payload = {
            "user_message": context.message[:200],
            "intent": context.intent,
            "answer_depth": context.intent_metadata.get("answer_depth"),
            "confirmed_memories": context.memories[-8:],
            "sub_agent_status": response.validation.status,
            "has_verified_claims": bool(response.claims),
        }
        try:
            raw = await self.persona_llm.complete(
                [
                    LLMMessage(
                        role="system",
                        content=PERSONA_PROMPT.replace(
                            "{style_directive}", style_directive
                        ),
                    ),
                    LLMMessage(
                        role="user",
                        content=json.dumps(payload, ensure_ascii=False),
                    ),
                ]
            )
            start, end = raw.find("{"), raw.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("persona response did not contain JSON")
            frame = PersonaFrame.model_validate_json(raw[start : end + 1])
            return PersonaFrame(
                opening=self._safe_style_line(frame.opening),
                closing=self._safe_style_line(frame.closing),
            )
        except Exception:
            return PersonaFrame()

    @staticmethod
    def _safe_style_line(value: str) -> str:
        line = re.sub(r"\s+", " ", value).strip()
        if re.search(r"\[C\d+\]", line) or len(line) > 100:
            return ""
        return line

    @staticmethod
    def _grounded_answer(
        context: AgentContext,
        response: AIResponse,
        frame: PersonaFrame | None = None,
    ) -> str:
        answer = response.answer.strip()
        if not answer:
            return "这点资料目前还不足以得出可靠结论。把问题说具体些，我再让智库查一遍。"
        if response.agent == "conversation_agent":
            return answer
        # 自查等非检索型回答不适用"无证据"语境；报告本身就是任务产物。
        if response.validation.method == "player_self_review":
            parts = [answer]
            if frame and frame.opening:
                parts.insert(0, frame.opening)
            if frame and frame.closing:
                parts.append(frame.closing)
            return "\n\n".join(parts)
        if not response.claims:
            # 无已验证主张=拒答/降级：用中性说明，不套风格引导语。
            return answer
        lead_pool = (
            "行，智库里能查到的都给你摆出来了。",
            "这些就是能验证的部分，够用了。",
            "结论在下面，都是对过档案的。",
            "看好了，只说有据可查的部分。",
        )
        default_lead = lead_pool[
            crc32(answer.encode("utf-8")) % len(lead_pool)
        ]
        opening = frame.opening if frame and frame.opening else default_lead
        parts = [opening, answer]
        if frame and frame.closing:
            parts.append(frame.closing)
        return "\n\n".join(parts)

    @staticmethod
    def _expand_with_claims(
        response: AIResponse, answer: str, depth: str
    ) -> str:
        if depth == "concise" or not response.claims:
            return answer
        minimum_length = 220 if depth == "detailed" else 120
        if len(answer) >= minimum_length:
            return answer
        limit = 8 if depth == "detailed" else 5
        additions = []
        for claim in response.claims:
            if claim.statement in answer:
                continue
            references = " ".join(f"[{item}]" for item in claim.citation_ids)
            additions.append(
                f"- {claim.statement}{f' {references}' if references else ''}"
            )
            if len(additions) >= limit:
                break
        if not additions:
            return answer
        return f"{answer}\n\n已验证要点：\n" + "\n".join(additions)
