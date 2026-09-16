"""FC 工具层：把既有 ToolSpec（react_tools）包装成原生 Function Calling 工具。

规格依据 main-agent-spec.md §6：
- 四类错误前缀协议：正常 / [无结果] / [错误·配置] / [错误·运行时]，模型据此如实转述
- description 四段模板（何时用/不要用于/参数/返回约定）——意图判断的质量在此
- safe_execute 永不抛异常；观察文本上限 4000 字符
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.agents.base import AgentContext
from app.agents.react_tools import ToolResult, ToolSpec

TOOL_RESULT_LIMIT = 4000
# slow=True 的工具走"提交-收尾"模式（规格 §11）：FC 循环立即转后台，完成后收尾汇报
SLOW_TOOLS = {"team_recommendation"}


# ---------------------------------------------------------------------------
# 参数模型（bind_tools 直接可用；字段描述写清含义与默认值）
# ---------------------------------------------------------------------------


class CatalogSearchArgs(BaseModel):
    keyword: str = Field(default="", description="角色名称或名称片段，如「景元」；不确定全名时给片段")


class CharacterProfileArgs(BaseModel):
    name: str = Field(default="", description="角色全名，如「景元」「流萤」")


class CharacterMaterialsArgs(BaseModel):
    name: str = Field(default="", description="角色全名")


class TeamRecommendationArgs(BaseModel):
    request: str = Field(default="", description="完整配队需求文本，包含角色与约束，如「流萤的队伍，不要限定五星」")


class KnowledgeSearchArgs(BaseModel):
    query: str = Field(default="", description="检索问题")
    domain: str = Field(default="auto", description="剧情类用 story，其余 knowledge，不确定用 auto")


class CharacterBuildArgs(BaseModel):
    request: str = Field(default="", description="完整养成需求，包含角色名与目标，如「把景元练到 80 级还缺什么」")


class ActivityStrategyArgs(BaseModel):
    request: str = Field(default="", description="活动相关需求，如「当前版本活动怎么玩」「XXX 活动攻略」")


class WeeklyPlanningArgs(BaseModel):
    request: str = Field(default="", description="规划需求，如「这周体力怎么分配」；可含体力预算如「400 点」")


class CustomCharacterGuideArgs(BaseModel):
    request: str = Field(default="", description="用户关于自创角色/自定义配队的诉求")
    mode: str = Field(default="auto", description="creation=创作引导 | team=自定义配队 | auto=按内容判断")


class CustomCharacterReviewArgs(BaseModel):
    request: str = Field(default="", description="审核需求；默认审核用户最近编辑的草稿")


FC_ARGS_MODELS: dict[str, type[BaseModel]] = {
    "catalog_search": CatalogSearchArgs,
    "character_profile": CharacterProfileArgs,
    "character_materials": CharacterMaterialsArgs,
    "team_recommendation": TeamRecommendationArgs,
    "knowledge_search": KnowledgeSearchArgs,
    "character_build": CharacterBuildArgs,
    "activity_strategy": ActivityStrategyArgs,
    "weekly_planning": WeeklyPlanningArgs,
    "custom_character_guide": CustomCharacterGuideArgs,
    "custom_character_review": CustomCharacterReviewArgs,
}

# 四段模板 description（规格 6.3）——覆盖 react_tools 的单句式描述
FC_DESCRIPTIONS: dict[str, str] = {
    "catalog_search": (
        "按名称关键词查找角色目录，返回角色ID、命途、属性、稀有度。\n"
        "何时用：\n- 需要确认用户提到的是哪个角色、解析模糊称呼时（例句：「帮我看看景元」）\n"
        "不要用于：\n- 查角色详情（用 character_profile）\n- 配队请求（用 team_recommendation）\n"
        "参数说明：keyword=角色名称或片段，不确定全名时给片段。\n"
        "返回约定：命中返回角色列表；[无结果] 表示目录中没有该名称，可建议用户换叫法。"
    ),
    "character_profile": (
        "读取角色官方结构化档案：身份、面板数值、全部技能、背景故事摘录。\n"
        "何时用：\n- 「XX是谁/技能是什么/什么命途属性」类精确查询（例句：「黑塔的技能是什么」）\n"
        "不要用于：\n- 配队请求（用 team_recommendation）\n- 养成材料（用 character_materials）\n"
        "参数说明：name=角色全名。\n"
        "返回约定：返回结构化档案；[无结果] 表示目录中没有该角色。"
    ),
    "character_materials": (
        "查询角色突破/晋阶所需的全部材料清单（结构化对齐结果）。\n"
        "何时用：\n- 「XX突破要什么材料/养成还缺什么」类问题（例句：「景元晋升要什么」）\n"
        "不要用于：\n- 配队、剧情类问题\n"
        "参数说明：name=角色全名。\n"
        "返回约定：返回材料清单；[无结果] 表示目录中没有该角色。"
    ),
    "team_recommendation": (
        "调用配队评分引擎（机制画像+模拟评分+约束过滤）生成推荐队伍。耗时较长。\n"
        "何时用：\n- 「XX怎么配队/给我一队/带约束的队伍」（例句：「流萤怎么配队，不要限定五星」）\n"
        "不要用于：\n- 单角色事实查询\n"
        "参数说明：request=完整需求文本，包含角色与约束；约束必须原样保留。\n"
        "返回约定：返回推荐队伍与评分；[无结果] 表示约束过严，可建议放宽条件。"
    ),
    "knowledge_search": (
        "在官方知识库（剧情/世界观/角色故事/物品/活动）做语义检索，返回带引用的证据。\n"
        "何时用：\n- 剧情、世界观、活动攻略、设定考据类问题（例句：「翁法罗斯是什么」）\n"
        "不要用于：\n- 角色结构化档案能直接回答的数值事实\n"
        "参数说明：query=检索问题；domain=剧情类用 story，其余 knowledge，不确定用 auto。\n"
        "返回约定：返回证据摘录与引用；[无结果] 表示知识库没有相关内容，可建议换关键词。"
    ),
    "character_build": (
        "结合用户练度（角色池与养成进度）计算材料缺口与已验证构筑建议。\n"
        "何时用：\n- 「XX该怎么练/养成还缺什么/优先练谁」类需要结合用户数据的问题（例句：「把景元练到 80 级还缺什么」）\n"
        "不要用于：\n- 纯材料清单（用 character_materials）\n- 配队（用 team_recommendation）\n"
        "参数说明：request=完整需求，包含角色名与目标；用户未登录或无练度数据时引擎会给通用建议。\n"
        "返回约定：返回建议文本与引用；[无结果] 表示角色未收录或数据不足，可建议补充信息。"
    ),
    "activity_strategy": (
        "依据官方活动资料生成带引用的活动说明与攻略总结。\n"
        "何时用：\n- 「现在有什么活动/XXX 活动怎么玩」类问题（例句：「当前版本活动有什么」）\n"
        "不要用于：\n- 非活动类的养成或配队问题\n"
        "参数说明：request=活动相关需求。\n"
        "返回约定：返回攻略总结与引用；[无结果] 表示资料未收录该活动，可建议给出活动全名。"
    ),
    "weekly_planning": (
        "依据用户启用中的养成方案生成每周体力规划。\n"
        "何时用：\n- 「这周体力怎么分配/帮我排下体力」类规划请求（例句：「400 点体力怎么用」）\n"
        "不要用于：\n- 单个角色的材料查询（用 character_materials）\n"
        "参数说明：request=规划需求，可含体力预算；用户没有启用中的养成方案时会说明并给通用优先级。\n"
        "返回约定：返回规划文本；[无结果] 表示没有可用的养成方案数据。"
    ),
    "custom_character_guide": (
        "引导用户进入玩家自创角色/自定义配队的隔离流程（创作工坊）。\n"
        "何时用：\n- 用户想做自己的角色、或想给自己创建的角色配队（例句：「我想自己设计一个角色」）\n"
        "不要用于：\n- 官方角色的配队（用 team_recommendation）\n"
        "参数说明：request=诉求；mode=creation（创作引导）| team（自定义配队）| auto（按内容判断，含「配队」选 team）。\n"
        "返回约定：返回流程引导话术；本工具不读取草稿数据（读写隔离）。"
    ),
    "custom_character_review": (
        "对用户的原创角色草稿运行提交前自查，输出五维评分报告（完整度/真实性/一致性/数值/合规）。\n"
        "何时用：\n- 用户想检查/优化自己的自创角色草稿（例句：「帮我看看我的角色 balanced 吗」）\n"
        "不要用于：\n- 官方角色的任何查询\n"
        "参数说明：request=审核需求；默认审核用户最近编辑的草稿。\n"
        "返回约定：返回审核报告；[无结果] 表示未登录或没有草稿，可引导先去创作工坊创建。"
    ),
}


# ---------------------------------------------------------------------------
# 工具定义与包装
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FCToolDefinition:
    tool_id: str
    label: str
    description: str
    args_model: type[BaseModel]
    handler: Any  # async (args: dict, context: AgentContext) -> ToolResult（继承 react_tools）
    risk: str = "safe"
    enabled: bool = True
    slow: bool = False

    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.tool_id,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }


def build_fc_tools(specs: list[ToolSpec]) -> dict[str, FCToolDefinition]:
    definitions: dict[str, FCToolDefinition] = {}
    for spec in specs:
        args_model = FC_ARGS_MODELS.get(spec.name)
        if args_model is None:
            # 没有 pydantic 参数模型的工具不接入 FC（显式跳过，避免运行时才发现）
            continue
        definitions[spec.name] = FCToolDefinition(
            tool_id=spec.name,
            label=spec.label,
            description=FC_DESCRIPTIONS.get(spec.name, spec.description),
            args_model=args_model,
            handler=spec.handler,
            slow=spec.name in SLOW_TOOLS,
        )
    return definitions


# ---------------------------------------------------------------------------
# safe_execute 与观察文本（永不抛异常，四类前缀协议）
# ---------------------------------------------------------------------------


def _is_empty(result: ToolResult) -> bool:
    data = result.data or {}
    if data.get("empty") or data.get("found") is False:
        return True
    return not any(value for value in data.values())


def _render(result: ToolResult) -> str:
    lines = [result.summary]
    if result.data:
        lines.append(json.dumps(result.data, ensure_ascii=False)[:3500])
    if result.citations:
        lines.extend(f"[{item.id}] {item.title}（{item.source}）" for item in result.citations)
    return "\n".join(lines)


def truncate(text: str, limit: int = TOOL_RESULT_LIMIT) -> str:
    if len(text) <= limit:
        return text
    head, tail = limit - 200, 150
    return f"{text[:head]}\n…省略…\n{text[-tail:]}"


async def safe_execute(
    definition: FCToolDefinition | None,
    raw_args: dict[str, Any] | None,
    context: AgentContext,
) -> tuple[str, ToolResult | None]:
    """执行工具并返回（观察文本, ToolResult）。任何失败都转成可转述文本，不抛异常。"""
    if definition is None or not definition.enabled:
        return "[错误·配置] 该工具不可用，请如实告知用户，不要假装调用成功。", None
    try:
        args = definition.args_model(**(raw_args or {}))
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        return (
            f"[错误·配置] {definition.tool_id} 参数无效：{first.get('loc')} {first.get('msg')}。"
            "参数不确定时省略字段，使用默认值。",
            None,
        )
    try:
        result = await definition.handler(args.model_dump(), context)
    except Exception as exc:  # noqa: BLE001 —— 兜底：任何异常都转成模型可转述的文本
        return f"[错误·运行时] {type(exc).__name__}：工具执行失败。可换个工具重试，或如实告知用户失败原因。", None
    text = _render(result)
    if _is_empty(result):
        text = f"[无结果] {result.summary}。请建议用户换个条件或说法重查，不要编造内容。" if not result.summary.startswith("[") else result.summary
    return truncate(text), result


def rewrite_refs(text: str, offset: int) -> str:
    """本轮观察文本里的 [Cn] 全局重排（与 react_main_agent 同一规则）。"""
    if offset == 0 or not text:
        return text
    return re.sub(r"\[C(\d+)\]", lambda match: f"[C{int(match.group(1)) + offset}]", text)
