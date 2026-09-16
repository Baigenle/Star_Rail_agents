"""ReAct 主 Agent 的工具层。

每个工具是大脑可调用的一个原子能力：接收 JSON 参数，返回 JSON 观察结果。
工具优先包装已验证的确定性服务与子 Agent（配队评分 v3、约束解析、
关系抽取、材料对齐），历史修复自动继承；输出统一携带来源引用，
供大脑在最终回答中标注 [Cn]。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.agents.activity_strategy_agent import ActivityStrategyAgent
from app.agents.base import AgentContext
from app.agents.character_build_agent import CharacterBuildAgent
from app.agents.custom_character_agent import CustomCharacterAgent
from app.agents.custom_character_review_agent import ChatCustomCharacterReviewAgent
from app.agents.weekly_planning_agent import WeeklyPlanningAgent
from app.memory.schemas import L15Fact
from app.schemas.ai_response import AIResponse, Citation
from app.services.catalog_service import CatalogService


@dataclass(slots=True)
class ToolResult:
    """一次工具执行的结构化观察。"""

    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    citations: list[Citation] = field(default_factory=list)

    def observation(self, citation_offset: int) -> dict[str, Any]:
        """转成给大脑的观察 JSON；引用编号在引擎层全局重排。"""
        payload: dict[str, Any] = {"result": self.data}
        if self.citations:
            payload["citations"] = [
                {
                    "citation_id": f"C{citation_offset + index}",
                    "title": citation.title,
                    "source": citation.source,
                }
                for index, citation in enumerate(self.citations, start=1)
            ]
        return payload


ToolHandler = Callable[[dict[str, Any], AgentContext], Awaitable[ToolResult]]


@dataclass(slots=True)
class ToolSpec:
    name: str
    label: str
    description: str
    args_schema: str
    handler: ToolHandler


def _sub_context(context: AgentContext, message: str, intent: str) -> AgentContext:
    """为子 Agent 构造执行上下文：继承用户实体与记忆，消息换成工具参数。"""
    return AgentContext(
        user_id=context.user_id,
        message=message,
        conversation_id=context.conversation_id,
        intent=intent,
        entities=context.entities,
        memories=context.memories,
        event_sink=None,
    )


def _citations_from(response: AIResponse) -> list[Citation]:
    return list(response.citations)


def _relabel_citations(response: AIResponse) -> tuple[str, list[Citation]]:
    """子 Agent 的 [C1] 编号原样保留（每次工具调用独立编号，引擎统一重排）。"""
    answer = response.answer
    citations = _citations_from(response)
    return answer, citations


def make_catalog_search(catalog: CatalogService) -> ToolSpec:
    async def handler(args: dict[str, Any], context: AgentContext) -> ToolResult:
        keyword = str(args.get("keyword") or "").strip()
        if not keyword:
            return ToolResult(summary="catalog_search 需要 keyword 参数", data={})
        normalized = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", keyword).lower()
        characters = [
            {"character_id": item.id, "name": item.name, "element": item.element,
             "path": item.path, "rarity": item.rarity}
            for item in catalog.list_characters()
            if normalized and normalized in re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", item.name).lower()
        ][:8]
        return ToolResult(
            summary=f"目录命中 {len(characters)} 个角色",
            data={"characters": characters},
        )

    return ToolSpec(
        name="catalog_search",
        label="角色目录检索",
        description="按名称关键词查找角色目录，返回角色ID、命途、属性、稀有度。用于解析用户提到的角色。",
        args_schema='{"keyword": "角色名称或片段"}',
        handler=handler,
    )


def make_character_profile(catalog: CatalogService) -> ToolSpec:
    async def handler(args: dict[str, Any], context: AgentContext) -> ToolResult:
        name = str(args.get("name") or "").strip()
        if not name:
            return ToolResult(summary="character_profile 需要 name 参数", data={})
        character_id = _resolve_character_id(catalog, name)
        if not character_id:
            return ToolResult(
                summary=f"目录中没有找到「{name}」",
                data={"found": False},
            )
        detail = catalog.get_character(character_id)
        if detail is None:
            return ToolResult(summary=f"「{name}」档案缺失", data={"found": False})
        citation = Citation(
            id="C1",
            title=f"{detail.name} · 结构化档案",
            source=str(detail.source_url or "docs/hsr_nanoka_characters"),
            excerpt=re.sub(r"\s+", " ", f"{detail.description} {detail.story}")[:900],
            document_id=detail.id,
            entity_url=f"/characters/{detail.id}",
            image_url=detail.image_url,
        )
        data = {
            "found": True,
            "character_id": detail.id,
            "name": detail.name,
            "rarity": detail.rarity,
            "path": detail.path,
            "element": detail.element,
            "description": detail.description,
            "stats": detail.stats,
            "skills": [
                {
                    "name": skill.name,
                    "type": str(getattr(skill, "type", "") or "技能"),
                    "description": re.sub(r"\s+", " ", skill.description)[:180],
                }
                for skill in detail.skills
            ],
            "story_excerpt": re.sub(r"\s+", " ", detail.story)[:400],
        }
        return ToolResult(
            summary=f"读取 {detail.name} 结构化档案（{len(data['skills'])} 项技能）",
            data=data,
            citations=[citation],
        )

    return ToolSpec(
        name="character_profile",
        label="角色结构化档案",
        description="读取角色的官方结构化档案：身份、面板数值、全部技能、背景故事摘录。适合「XX是谁/技能是什么」类精确查询。",
        args_schema='{"name": "角色名"}',
        handler=handler,
    )


def make_character_materials(catalog: CatalogService, material_agent: Any) -> ToolSpec:
    async def handler(args: dict[str, Any], context: AgentContext) -> ToolResult:
        name = str(args.get("name") or "").strip()
        if not name:
            return ToolResult(summary="character_materials 需要 name 参数", data={})
        character_id = _resolve_character_id(catalog, name)
        if not character_id:
            return ToolResult(summary=f"目录中没有找到「{name}」", data={"found": False})
        character = catalog.get_character(character_id)
        if character is None:
            return ToolResult(summary=f"「{name}」档案缺失", data={"found": False})
        response = material_agent._character_materials(character, f"{name}突破材料")
        materials = [
            citation.title
            for citation in response.citations
        ]
        return ToolResult(
            summary=f"{character.name} 养成材料 {len(materials)} 项",
            data={"character": character.name, "materials": materials},
            citations=_relabel_citations(response)[1],
        )

    return ToolSpec(
        name="character_materials",
        label="养成材料查询",
        description="查询角色突破/晋阶所需的全部材料清单（结构化对齐结果）。",
        args_schema='{"name": "角色名"}',
        handler=handler,
    )


def make_team_recommendation(team_agent: Any) -> ToolSpec:
    async def handler(args: dict[str, Any], context: AgentContext) -> ToolResult:
        request = str(args.get("request") or "").strip()
        if not request:
            return ToolResult(summary="team_recommendation 需要 request 参数", data={})
        sub = _sub_context(context, request, "team_recommendation")
        response = await team_agent.run(sub)
        answer, citations = _relabel_citations(response)
        return ToolResult(
            summary=f"配队推荐完成（{len(citations)} 条来源）",
            data={
                "answer": answer,
                "note": "answer 中队伍按推荐顺序排列，含综合分与模型复核；已应用用户显式约束。",
            },
            citations=citations,
        )

    return ToolSpec(
        name="team_recommendation",
        label="智能配队引擎",
        description="调用配队评分引擎（机制画像+模拟评分+约束过滤）为角色生成推荐队伍。request 写成完整需求，如「流萤的虚构叙事队伍，不要限定五星」。",
        args_schema='{"request": "完整配队需求描述"}',
        handler=handler,
    )


def make_knowledge_search(rag_agent: Any) -> ToolSpec:
    async def handler(args: dict[str, Any], context: AgentContext) -> ToolResult:
        query = str(args.get("query") or "").strip()
        domain = str(args.get("domain") or "auto").strip()
        if not query:
            return ToolResult(summary="knowledge_search 需要 query 参数", data={})
        intent = {
            "story": "story_analysis",
            "knowledge": "knowledge_qa",
        }.get(domain, "knowledge_qa")
        sub = _sub_context(context, query, intent)
        if domain == "story":
            sub.intent_metadata = {"task_mode": "story_detail"}
        response = await rag_agent.run(sub)
        answer, citations = _relabel_citations(response)
        if not citations:
            return ToolResult(
                summary="知识库没有检索到相关内容",
                data={"answer": "", "empty": True},
            )
        return ToolResult(
            summary=f"检索到 {len(citations)} 条证据",
            data={
                "answer": answer,
                "evidence_excerpts": [
                    f"[{citation.id}] {citation.title}：{citation.excerpt[:220]}"
                    for citation in citations
                ],
            },
            citations=citations,
        )

    return ToolSpec(
        name="knowledge_search",
        label="知识库检索",
        description="在官方知识库（剧情/世界观/角色故事/物品/活动）做语义检索，返回带引用的证据。适合剧情、世界观、活动、养成知识类问题。",
        args_schema='{"query": "检索问题", "domain": "story|knowledge|auto（剧情类用story）"}',
        handler=handler,
    )


def make_character_build(docs_root: Path, rag_agent, memory_repo=None) -> ToolSpec:
    """养成建议：结合用户练度（entities.character_progress）计算材料与构筑。
    成功时顺手写 L1.5 事实缓存（latest_build），供后续秒答。"""
    agent = CharacterBuildAgent(Path(docs_root), rag_agent)

    async def handler(args: dict[str, Any], context: AgentContext) -> ToolResult:
        request = str(args.get("request") or "").strip()
        if not request:
            return ToolResult(summary="character_build 需要 request 参数", data={})
        sub = _sub_context(context, request, "character_build")
        response = await agent.run(sub)
        answer, citations = _relabel_citations(response)
        if memory_repo is not None and context.user_id and answer:
            try:
                memory_repo.upsert_fact(
                    str(context.user_id),
                    L15Fact(
                        fact_key="latest_build",
                        fact_value=f"{request[:80]} → {answer[:180]}",
                    ),
                )
            except Exception:  # noqa: BLE001 —— 缓存失败不影响主流程
                pass
        return ToolResult(
            summary=f"养成建议（{len(citations)} 条来源）",
            data={"answer": answer},
            citations=citations,
        )

    return ToolSpec(
        name="character_build",
        label="养成建议引擎",
        description="结合用户练度计算材料缺口与已验证构筑建议。",
        args_schema='{"request": "完整养成需求，含角色名与目标"}',
        handler=handler,
    )


def make_activity_strategy(docs_root: Path, llm) -> ToolSpec:
    """活动攻略：依据官方活动资料生成带引用的攻略总结。"""
    agent = ActivityStrategyAgent(Path(docs_root), llm)

    async def handler(args: dict[str, Any], context: AgentContext) -> ToolResult:
        request = str(args.get("request") or "").strip()
        if not request:
            return ToolResult(summary="activity_strategy 需要 request 参数", data={})
        sub = _sub_context(context, request, "activity_strategy")
        response = await agent.run(sub)
        answer, citations = _relabel_citations(response)
        return ToolResult(
            summary=f"活动攻略（{len(citations)} 条来源）",
            data={"answer": answer},
            citations=citations,
        )

    return ToolSpec(
        name="activity_strategy",
        label="活动攻略助手",
        description="依据官方活动资料生成带引用的活动说明与攻略总结。",
        args_schema='{"request": "活动相关需求"}',
        handler=handler,
    )


def make_weekly_planning() -> ToolSpec:
    """每周规划：依据用户启用中的养成方案（entities.active_progression_plans）排体力。"""
    agent = WeeklyPlanningAgent()

    async def handler(args: dict[str, Any], context: AgentContext) -> ToolResult:
        request = str(args.get("request") or "").strip()
        if not request:
            return ToolResult(summary="weekly_planning 需要 request 参数", data={})
        sub = _sub_context(context, request, "weekly_plan")
        response = await agent.run(sub)
        answer, citations = _relabel_citations(response)
        return ToolResult(
            summary="每周体力规划",
            data={"answer": answer},
            citations=citations,
        )

    return ToolSpec(
        name="weekly_planning",
        label="每周规划助手",
        description="依据用户启用中的养成方案生成每周体力规划。",
        args_schema='{"request": "规划需求，可含体力预算"}',
        handler=handler,
    )


def make_custom_character_guide() -> ToolSpec:
    """创作工坊引导：自创角色/自定义配队的流程入口（读写隔离，不碰草稿数据）。"""
    agent = CustomCharacterAgent()

    async def handler(args: dict[str, Any], context: AgentContext) -> ToolResult:
        request = str(args.get("request") or "").strip()
        mode = str(args.get("mode") or "auto").strip()
        if not request:
            return ToolResult(summary="custom_character_guide 需要 request 参数", data={})
        if mode == "auto":
            mode = "team" if "配队" in request else "creation"
        intent = "custom_team_recommendation" if mode == "team" else "custom_character_creation"
        sub = _sub_context(context, request, intent)
        response = await agent.run(sub)
        answer, citations = _relabel_citations(response)
        return ToolResult(
            summary="创作工坊流程引导",
            data={"answer": answer},
            citations=citations,
        )

    return ToolSpec(
        name="custom_character_guide",
        label="创作工坊引导",
        description="引导用户进入玩家自创角色/自定义配队的隔离流程。",
        args_schema='{"request": "诉求", "mode": "creation|team|auto"}',
        handler=handler,
    )


def make_custom_character_review(draft_provider, llm) -> ToolSpec:
    """原创角色自查：对用户当前草稿运行五维评分报告（需登录且有草稿）。"""
    agent = ChatCustomCharacterReviewAgent(draft_provider, llm)

    async def handler(args: dict[str, Any], context: AgentContext) -> ToolResult:
        request = str(args.get("request") or "").strip() or "审核我的角色草稿"
        sub = _sub_context(context, request, "custom_character_review")
        response = await agent.run(sub)
        answer, citations = _relabel_citations(response)
        return ToolResult(
            summary="草稿自查报告",
            data={"answer": answer},
            citations=citations,
        )

    return ToolSpec(
        name="custom_character_review",
        label="原创角色自查",
        description="对用户的原创角色草稿运行提交前自查（五维评分报告）。",
        args_schema='{"request": "审核需求，默认审核最近草稿"}',
        handler=handler,
    )


def _resolve_character_id(catalog: CatalogService, name: str) -> str | None:
    """角色名解析：精确 → 前缀（开拓者·毁灭）→ 泛名家族（开拓者）。"""
    normalized = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", name).lower()
    if not normalized:
        return None
    characters = catalog.list_characters()
    for item in characters:
        if re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", item.name).lower() == normalized:
            return item.id
    for item in characters:
        full = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", item.name).lower()
        if full.startswith(normalized) or normalized in full:
            return item.id
    return None


def tool_catalog_line(specs: list[ToolSpec]) -> str:
    return "\n".join(
        f"- {spec.name}: {spec.description} 参数: {spec.args_schema}"
        for spec in specs
    )


def dump_tool_result(result: ToolResult) -> str:
    return json.dumps(result.data, ensure_ascii=False)
