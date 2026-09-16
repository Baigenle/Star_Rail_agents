"""ReAct 主 Agent：思考-行动循环引擎。

架构（2026-09 重构，替代旧 intent→router→agent 流水线）：
1. 分流：大脑先判断 fast（闲聊/单角色事实，关思考，≤3 步）或
   deep（配队/剧情/复合/带约束，开思考，≤6 步）。
2. 循环：每轮输出严格 JSON——思考 + 工具调用 或 最终回答。
3. 澄清：关键歧义阻塞工具选择时，向用户追问并给出可选项，
   用户点选后作为观察回到循环。
4. 引用：工具返回的证据全局编号 [Cn]，最终回答中的事实句标注来源；
   不存在拒答模板——证据不足时如实说明已查范围并给出方向。

历史资产全部以工具形式复用：配队评分 v3、约束解析、家族泛名识别、
关系抽取、材料对齐、结构化档案。
"""

from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.agents.react_tools import ToolSpec, tool_catalog_line
from app.core.answer_budget import soft_trim
from app.llm.base import LLMMessage, LLMProvider
from app.schemas.ai_response import (
    AgentAction,
    AIResponse,
    Citation,
    FilteringReport,
    QueryStep,
    ValidationReport,
)

MAX_STEPS = {"fast": 3, "deep": 6}

ROUTE_PROMPT = """你是星穹列车智库的主控大脑。先对用户消息做一次快速分析，输出严格 JSON：
{"mode": "fast|deep", "intent": "conversation|knowledge_qa|story_analysis|team_recommendation|character_build|material_query|memory|capability|custom_character_review", "thought": "一句话理由"}

- fast：问候寒暄、助手身份、功能询问、单角色精确事实（是谁/技能/材料）、记忆管理。回答不超过两步工具调用。
- deep：配队推荐、剧情/世界观/角色关系分析、角色比较、复合问题（多个目标）、带约束条件的请求、养成规划。需要多轮检索与整合。
拿不准时选 deep。"""

SYSTEM_PROMPT = """你是星穹列车智库的主控大脑「黑塔」——天才俱乐部第 83 席（不是 81，81 是阮·梅），站长是艾丝妲。通过调用工具回答《崩坏：星穹铁道》相关问题。

## 可用工具
{tools}

## 已知上下文
- 用户确认提到的角色/实体：{entities}
- 用户长期记忆与角色池：{memories}
- 近期对话：{history}

## 行动协议
每一轮只输出一个严格 JSON 对象（不要 Markdown），二选一：

调用工具：
{{"thought": "当前判断与下一步计划（给用户可见，写清楚为什么）", "tool": {{"name": "工具名", "args": {{...}}}}}}

给出最终回答：
{{"thought": "收尾思考", "answer": "面向用户的完整回答", "follow_ups": ["可选的2-3个衍生问题"]}}

向用户追问（仅当关键歧义已经阻塞工具选择，比如「开拓者配队」没说哪种命途、「剧情」没说哪段；最多追问一次）：
{{"thought": "说明为什么必须问", "answer": "追问正文", "clarification": {{"options": ["选项1", "选项2", "选项3"]}}}}

## 规则
1. 事实必须有据：来自工具结果的句子在句尾标注引用编号，如 [C1][C3]。编号只能用「可用引用」列表里存在的。
2. 内容只能来自工具观察结果：技能名、数值、机制描述必须照抄观察原文，禁止改名、改数、脑补机制。整理转述可以，无中生有不行。
3. 工具没查到时如实说明查了什么、缺什么，再给最接近的可答方向；禁止编造、禁止输出"检索结果与问题不相关"这类系统腔。工具执行失败后，禁止改用记忆补出队伍、数值、材料等数据性结论。
4. 闲聊/身份/功能询问不需要工具，直接给最终回答，语气可以带黑塔的自信与俏皮；事实回答则克制、准确。
5. 复合问题（多个目标）必须在回答里逐项覆盖，不能只答第一个。
6. 回答长度参考：闲聊≤3句；单角色事实≤350字；配队/剧情分析 400-700字；用户明确要详细时可放宽。写完整自然的段落，不要罗列系统日志。
7. 最终回答开头不要重复用户问题，不要加"根据检索结果"这类开场白。"""

ACTION_MAP: dict[str, tuple[str, str, str]] = {
    # tool name -> (title, url, description)
    "team_recommendation": (
        "去配队页查看完整评分",
        "/teams",
        "查看评分明细、自由调整成员",
    ),
    "knowledge_search": (
        "去剧情档案阅读原文",
        "/stories",
        "浏览任务原文与场景脉络",
    ),
    "character_materials": (
        "去角色页看养成详情",
        "/characters",
        "查看角色养成与材料详情",
    ),
    "character_profile": (
        "进入角色档案",
        "/characters",
        "查看角色完整档案",
    ),
}


class ReactMainAgent(BaseAgent):
    name = "react_main_agent"
    description = "思考-行动循环主 Agent：大脑通过工具调用完成任务并整合回答"

    def __init__(
        self,
        tools: list[ToolSpec],
        brain_fast: LLMProvider | None,
        brain_deep: LLMProvider | None,
    ) -> None:
        self.tools = {spec.name: spec for spec in tools}
        self.brain_fast = brain_fast
        self.brain_deep = brain_deep
        self.registry = None  # 兼容旧 introspection 接口

    async def run(self, context: AgentContext) -> AIResponse:
        started = perf_counter()
        await context.emit_event(
            "orchestration.started",
            "主 Agent 开始思考",
            agent=self.name,
            detail="黑塔主控大脑已接管，进入思考-行动循环。",
            event_status="running",
            progress={"stage": "orchestration", "percent": 8},
        )

        route = await self._route(context)
        mode = route.get("mode") if isinstance(route, dict) else None
        mode = mode if mode in {"fast", "deep"} else "deep"
        intent = str(route.get("intent") or "") if isinstance(route, dict) else ""
        route_thought = str(route.get("thought") or "") if isinstance(route, dict) else ""
        context.intent = intent or None
        await context.emit_event(
            "react.route",
            "任务分析完成",
            agent=self.name,
            detail=f"{route_thought}（{'快速路径' if mode == 'fast' else '深度思考循环'}）",
            event_status="completed",
            progress={"stage": "routing", "percent": 15},
        )

        citations: list[Citation] = []
        steps: list[dict[str, str]] = []
        query_steps: list[QueryStep] = []
        used_tools: list[str] = []
        answer = ""
        follow_ups: list[str] = []
        max_steps = MAX_STEPS[mode]
        # 循环统一用快脑：工具选择与观察评估是协议任务，实测关思考的
        # glm-4.7 每步 4-8s 且 JSON 服从完美；思考模型在循环里每步会磨蹭
        # 1-2 分钟（实测 563s 灾难案例）。深度思考只用在最终整合一次。
        brain = self.brain_fast

        for step_index in range(1, max_steps + 1):
            payload = self._loop_prompt(context, citations, steps, step_index)
            if step_index == max_steps:
                payload += (
                    "\n\n【最后一步】已经没有更多调用工具的机会了。"
                    "必须基于已有证据输出最终回答（answer）；"
                    "证据不足的部分如实说明即可。"
                )
            repeated = self._detect_repeated_call(steps, payload)
            if repeated:
                payload += (
                    "\n\n【重复提醒】你刚才已经以相同参数调用过工具，"
                    "结果不会改变。请基于已有证据直接给出最终回答。"
                )
            raw = ""
            if brain:
                try:
                    raw = await brain.complete(
                        [
                            LLMMessage(
                                role="system",
                                content=self._system_prompt(),
                            ),
                            LLMMessage(role="user", content=payload),
                        ]
                    )
                except Exception as exc:  # noqa: BLE001
                    # 循环大脑失败不放弃：deep 整合会看到全部观察并兜底。
                    await context.emit_event(
                        "react.error",
                        "循环大脑调用失败",
                        agent=self.name,
                        detail=f"{type(exc).__name__}，转入最终整合。",
                        event_status="failed",
                    )
                    break
            decision = self._parse_decision(raw)
            if decision is None:
                steps.append({"role": "system", "content": "（大脑输出格式无效，已要求重试）"})
                continue
            thought = str(decision.get("thought") or "")
            if thought:
                await context.emit_event(
                    "react.thought",
                    f"思考 · 第{step_index}步",
                    agent=self.name,
                    detail=thought[:400],
                    event_status="completed",
                    progress={"stage": "thinking", "percent": min(90, 20 + step_index * 12)},
                )
            steps.append({"role": "brain", "content": thought})

            if decision.get("tool"):
                tool_call = decision["tool"]
                tool_name = str(tool_call.get("name") or "")
                args = tool_call.get("args") or {}
                spec = self.tools.get(tool_name)
                if spec is None:
                    steps.append({
                        "role": "observation",
                        "content": f"工具 {tool_name} 不存在。可用：{', '.join(self.tools)}",
                    })
                    continue
                await context.emit_event(
                    "react.tool_started",
                    f"调用 {spec.label}",
                    agent=self.name,
                    detail=json.dumps(args, ensure_ascii=False)[:200],
                    event_status="running",
                )
                tool_started = perf_counter()
                try:
                    result = await spec.handler(args, context)
                except Exception as exc:  # noqa: BLE001
                    steps.append({
                        "role": "observation",
                        "content": f"工具 {tool_name} 执行失败：{type(exc).__name__}。请换思路或如实告知用户。",
                    })
                    await context.emit_event(
                        "react.tool_completed",
                        f"{spec.label} 失败",
                        agent=self.name,
                        detail=f"{type(exc).__name__}",
                        event_status="failed",
                    )
                    continue
                offset = len(citations)
                for citation in result.citations:
                    citations.append(
                        citation.model_copy(
                            update={"id": f"C{len(citations) + 1}"}
                        )
                    )
                rewritten = self._rewrite_citation_refs(
                    str(result.data.get("answer") or ""), offset
                )
                if rewritten:
                    result.data["answer"] = rewritten
                observation = result.observation(offset)
                steps.append({
                    "role": "observation",
                    "content": json.dumps(observation, ensure_ascii=False)[:6000],
                })
                used_tools.append(tool_name)
                await context.emit_event(
                    "react.tool_completed",
                    f"{spec.label} 完成",
                    agent=self.name,
                    detail=result.summary,
                    event_status="completed",
                    duration_ms=int((perf_counter() - tool_started) * 1000),
                    progress={"stage": "tools", "percent": min(92, 30 + step_index * 12)},
                )
                continue

            # 最终回答
            answer = str(decision.get("answer") or "").strip()
            follow_ups = [
                str(item)[:60]
                for item in (decision.get("follow_ups") or [])
                if str(item).strip()
            ][:3]
            clarification = decision.get("clarification")
            if isinstance(clarification, dict) and answer:
                options = [
                    str(item)[:40]
                    for item in (clarification.get("options") or [])
                    if str(item).strip()
                ][:3]
                if options:
                    follow_ups = options
                    await context.emit_event(
                        "react.clarification",
                        "主 Agent 向用户追问",
                        agent=self.name,
                        detail=f"{answer[:120]} 选项：{' / '.join(options)}",
                        event_status="completed",
                    )
            follow_ups = follow_ups[:3]
            break

        # 深度整合仅作兜底：快脑循环已收敛时其草稿即终稿（实测质量达标
        # 且延迟可控）；循环耗尽/失败时才让思考模型基于全部观察写终稿。
        if not answer and mode == "deep" and self.brain_deep:
            integrate_started = perf_counter()
            await context.emit_event(
                "react.integrating",
                "深度思考整合最终回答",
                agent=self.name,
                detail=f"基于 {len(citations)} 条证据与 {len(used_tools)} 次工具观察综合作答。",
                event_status="running",
                progress={"stage": "integration", "percent": 94},
            )
            integrated = await self._deep_integrate(
                context, citations, steps, answer
            )
            if integrated:
                answer = integrated.get("answer") or answer
                deep_follows = [
                    str(item)[:60]
                    for item in (integrated.get("follow_ups") or [])
                    if str(item).strip()
                ][:3]
                if deep_follows:
                    follow_ups = deep_follows
            await context.emit_event(
                "react.integrating",
                "深度整合完成",
                agent=self.name,
                detail=(
                    "思考模型终稿已生成"
                    if integrated
                    else "思考模型不可用，使用快速草稿。"
                ),
                event_status="completed" if integrated else "failed",
                duration_ms=int((perf_counter() - integrate_started) * 1000),
            )

        if not answer:
            answer = self._fallback_answer(context, citations)

        # 保险性软截断（引擎协议已含长度指引，这里只防极端失控）。
        answer = soft_trim(answer, 1400)

        # 页面动作：按实际使用的工具映射深链。
        actions = self._build_actions(used_tools, context, citations)

        elapsed_ms = int((perf_counter() - started) * 1000)
        query_steps.append(
            QueryStep(
                id="react_route",
                name="任务分析",
                status="completed",
                detail=route_thought or f"分流为 {mode} 模式",
                duration_ms=0,
            )
        )
        for index, step in enumerate(steps, start=1):
            if step["role"] == "brain":
                query_steps.append(
                    QueryStep(
                        id=f"react_thought_{index}",
                        name="大脑思考",
                        status="completed",
                        detail=step["content"][:300],
                        duration_ms=0,
                    )
                )
            elif step["role"] == "observation":
                query_steps.append(
                    QueryStep(
                        id=f"react_tool_{index}",
                        name="工具观察",
                        status="completed",
                        detail=step["content"][:200],
                        duration_ms=0,
                    )
                )
        query_steps.append(
            QueryStep(
                id="react_final",
                name="回答整合",
                status="completed",
                detail=(
                    f"{'思考-行动循环' if mode == 'deep' else '快速路径'}完成："
                    f"{len(used_tools)} 次工具调用、{len(citations)} 条引用，"
                    f"总耗时 {elapsed_ms}ms。"
                ),
                duration_ms=elapsed_ms,
            )
        )
        await context.emit_event(
            "orchestration.completed",
            "主 Agent 完成",
            agent=self.name,
            detail=(
                f"模式 {mode}；工具调用 {len(used_tools)} 次；"
                f"引用 {len(citations)} 条。"
            ),
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
                method="react_tool_loop",
                evidence_count=len(citations),
                notes=[
                    "回答由主控大脑整合工具结果生成，事实句带来源引用。",
                ],
            ),
            filtering=FilteringReport(
                passed=True,
                removed_claims=0,
                rules=["引用随工具证据走，过滤器不再对整段回答有一票否决权。"],
            ),
            query_steps=query_steps,
            invoked_agents=[self.name, *dict.fromkeys(used_tools)],
            follow_up_questions=follow_ups,
            actions=actions,
        )

    # ------------------------------------------------------------------
    def _system_prompt(self) -> str:
        return SYSTEM_PROMPT.format(
            tools=tool_catalog_line(list(self.tools.values())),
            entities="（运行时注入）",
            memories="（运行时注入）",
            history="（运行时注入）",
        )

    def _loop_prompt(
        self,
        context: AgentContext,
        citations: list[Citation],
        steps: list[dict[str, str]],
        step_index: int,
    ) -> str:
        mentioned = [
            f"{item.get('name')}({item.get('character_id')})"
            for item in context.entities.get("mentioned_characters", [])
            if isinstance(item, dict)
        ]
        owned = context.entities.get("owned_character_ids") or []
        memories = [
            str(item.get("content") or "")
            for item in context.memories[:8]
            if isinstance(item, dict)
        ]
        history = [
            f"{item.get('role')}: {str(item.get('content') or '')[:160]}"
            for item in (context.conversation_history or [])[-6:]
        ]
        citation_lines = [
            f"[{citation.id}] {citation.title}（{citation.source}）"
            for citation in citations
        ]
        step_lines = [
            # 思考行短截断即可；观察行必须完整进入 prompt（技能/材料
            # 数据都在 observation JSON 里，砍掉会诱发"档案无技能"误判）。
            f"{step['role']}: {step['content'][:300 if step['role'] == 'brain' else 6000]}"
            for step in steps[-6:]
        ]
        parts = [
            f"用户消息：{context.message}",
            f"已确认实体：{'、'.join(mentioned) or '无'}",
            f"用户角色池：{len(owned)} 名角色；长期记忆：{'；'.join(memories[:4]) or '无'}",
        ]
        if history:
            parts.append("近期对话：\n" + "\n".join(history))
        if getattr(context, "memory_injection", ""):
            parts.append(context.memory_injection)
        if citation_lines:
            parts.append(
                "可用引用（回答中的事实句必须标注这些编号）：\n"
                + "\n".join(citation_lines)
            )
        if step_lines:
            parts.append("已完成步骤：\n" + "\n".join(step_lines))
        parts.append(f"当前第 {step_index} 步。输出下一步行动 JSON。")
        return "\n\n".join(parts)

    async def _route(self, context: AgentContext) -> dict[str, Any] | None:
        if not self.brain_fast:
            return None
        history = [
            f"{item.get('role')}: {str(item.get('content') or '')[:100]}"
            for item in (context.conversation_history or [])[-4:]
        ]
        payload = (
            "近期对话：\n" + "\n".join(history) + "\n\n"
            if history
            else ""
        ) + f"用户消息：{context.message}"
        try:
            raw = await self.brain_fast.complete(
                [
                    LLMMessage(role="system", content=ROUTE_PROMPT),
                    LLMMessage(role="user", content=payload),
                ]
            )
            start, end = raw.find("{"), raw.rfind("}")
            if start < 0 or end <= start:
                return None
            return json.loads(raw[start : end + 1])
        except Exception:  # noqa: BLE001
            return None

    async def _deep_integrate(
        self,
        context: AgentContext,
        citations: list[Citation],
        steps: list[dict[str, str]],
        draft_answer: str,
    ) -> dict[str, Any] | None:
        """终笔整合：思考模型一次性基于全部证据与循环草稿写最终回答。"""
        evidence_lines = [
            f"[{citation.id}] {citation.title}（{citation.source}）：{citation.excerpt[:300]}"
            for citation in citations[:18]
        ]
        observations = [
            step["content"][:600]
            for step in steps
            if step["role"] in {"observation", "brain"}
        ]
        prompt_parts = [
            f"用户消息：{context.message}",
            "全部可用证据：\n" + ("\n".join(evidence_lines) or "（无）"),
            "思考循环的观察记录：\n" + ("\n".join(observations) or "（无）"),
        ]
        if draft_answer:
            prompt_parts.append(
                "循环草稿（可以重写、补充或纠正，必须覆盖其全部有效内容）：\n"
                + draft_answer
            )
        prompt_parts.append(
            "输出严格 JSON：{\"answer\": \"最终回答（事实句标注 [Cn] 引用）\", "
            "\"follow_ups\": [\"最多3条衍生问题\"]}。"
            "规则：只依据证据与观察；技能名/数值照抄原文；复合问题逐项覆盖；"
            "证据不足的部分如实说明；语气自然直接，不要系统腔开场白。"
        )
        try:
            raw = await self.brain_deep.complete(
                [
                    LLMMessage(
                        role="system",
                        content=(
                            "你是星穹列车智库的终笔整合者。基于给出的证据和"
                            "思考循环记录写出最终回答，只输出 JSON。"
                        ),
                    ),
                    LLMMessage(role="user", content="\n\n".join(prompt_parts)),
                ]
            )
            start, end = raw.find("{"), raw.rfind("}")
            if start < 0 or end <= start:
                return None
            data = json.loads(raw[start : end + 1])
            return data if isinstance(data, dict) else None
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _detect_repeated_call(steps: list[dict[str, str]], payload: str) -> bool:
        """已连续两轮以上都在调工具时提醒收敛，防止原地打转。"""
        tool_rounds = sum(
            1 for step in steps if step["role"] == "observation"
        )
        return tool_rounds >= 2 and '"tool"' in payload

    @staticmethod
    def _parse_decision(raw: str) -> dict[str, Any] | None:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _rewrite_citation_refs(answer: str, offset: int) -> str:
        if offset == 0 or not answer:
            return answer
        return re.sub(
            r"\[C(\d+)\]",
            lambda match: f"[C{int(match.group(1)) + offset}]",
            answer,
        )

    @staticmethod
    def _fallback_answer(context: AgentContext, citations: list[Citation]) -> str:
        if citations:
            excerpts = "\n\n".join(
                f"{citation.excerpt[:160]} [C{index + 1}]"
                for index, citation in enumerate(citations[:3])
            )
            return (
                "这轮思考没能整合出完整结论，先把查到的可靠材料给你：\n\n"
                + excerpts
            )
        return (
            "这轮我没能从智库工具里拿到足够材料来回答这个问题。"
            "你可以换个说法补充细节（角色名、场景或想要的结果），我再重新想一遍。"
        )

    def _build_actions(
        self,
        used_tools: list[str],
        context: AgentContext,
        citations: list[Citation],
    ) -> list[AgentAction]:
        actions: list[AgentAction] = []
        seen_urls: set[str] = set()
        character_name = self._first_character_name(context)
        for tool_name in dict.fromkeys(used_tools):
            mapping = ACTION_MAP.get(tool_name)
            if mapping is None:
                continue
            title, url, description = mapping
            if url in seen_urls:
                continue
            seen_urls.add(url)
            params: dict[str, str] = {}
            action_type = "navigate"
            if tool_name in {"team_recommendation", "character_profile"} and character_name:
                params["core"] = character_name
                action_type = "prefill"
            if tool_name == "character_profile" and citations:
                target = next(
                    (
                        citation.entity_url
                        for citation in citations
                        if citation.entity_url
                        and citation.entity_url.startswith("/characters/")
                    ),
                    None,
                )
                if target:
                    url = target
                    action_type = "navigate"
                    params = {}
            actions.append(
                AgentAction(
                    action_type=action_type,
                    title=title,
                    target_url=url,
                    description=description,
                    params=params,
                )
            )
        return actions[:2]

    @staticmethod
    def _first_character_name(context: AgentContext) -> str:
        for item in context.entities.get("mentioned_characters", []):
            name = str(item.get("name") or "").strip()
            if name:
                return name
        return ""
