"""FC（Function Calling）模型对比冒烟测试 —— 规格 Q5 的实测脚本。

对同一批星铁化 T 系列查询，分别用 glm-4.7（关思考）与 DeepSeek 跑"单发工具选择"，
比对三个指标：工具调用命中率、参数正确性、收底诚实性。只测单发选择层，不含完整循环。

另含一个智谱专属探针：验证「tools + response_format=json_object 同请求」是否冲突
（providers.py 当前给所有请求硬编码了 json_object，FC 路径必须确认这一点）。

用法（在 backend/ 目录下）：
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/fc_model_compare.py
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/fc_model_compare.py --providers zhipu
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel, Field  # noqa: E402

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402

from app.core.config import settings  # noqa: E402

PER_CALL_TIMEOUT = 90


class CatalogSearchArgs(BaseModel):
    keyword: str = Field(description="角色名称或名称片段，如「景元」")


class CharacterProfileArgs(BaseModel):
    name: str = Field(description="角色全名")


class CharacterMaterialsArgs(BaseModel):
    name: str = Field(description="角色全名")


class TeamRecommendationArgs(BaseModel):
    request: str = Field(
        description="完整配队需求文本，包含角色与约束，如「流萤的队伍，不要限定五星」"
    )


class KnowledgeSearchArgs(BaseModel):
    query: str = Field(description="检索问题")
    domain: str = Field(default="auto", description="剧情类用 story，其余 knowledge，不确定 auto")


def _tool(name: str, description: str, schema: type[BaseModel]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": schema.model_json_schema(),
        },
    }


# 工具描述按规格 6.3 四段模板的压缩版书写。
TOOLS = [
    _tool(
        "catalog_search",
        "按名称关键词查找角色目录，返回角色ID、命途、属性、稀有度。\n"
        "何时用：需要确认用户提到的是哪个角色、解析模糊称呼时。\n"
        "不要用于：查角色详情（用 character_profile）、配队（用 team_recommendation）。",
        CatalogSearchArgs,
    ),
    _tool(
        "character_profile",
        "读取角色官方结构化档案：身份、面板数值、全部技能、背景故事摘录。\n"
        "何时用：「XX是谁/技能是什么/什么命途属性」类精确查询。\n"
        "不要用于：配队请求（用 team_recommendation）、养成材料（用 character_materials）。",
        CharacterProfileArgs,
    ),
    _tool(
        "character_materials",
        "查询角色突破/晋阶所需的全部材料清单（结构化对齐结果）。\n"
        "何时用：「XX突破要什么材料/养成还缺什么」类问题。\n"
        "不要用于：配队、剧情类问题。",
        CharacterMaterialsArgs,
    ),
    _tool(
        "team_recommendation",
        "调用配队评分引擎（机制画像+模拟评分+约束过滤）生成推荐队伍。\n"
        "何时用：「XX怎么配队/给我一队/带约束的队伍（如不要限定五星）」。\n"
        "不要用于：单角色事实查询。",
        TeamRecommendationArgs,
    ),
    _tool(
        "knowledge_search",
        "在官方知识库（剧情/世界观/角色故事/物品/活动）做语义检索，返回带引用的证据。\n"
        "何时用：剧情、世界观、活动攻略、设定考据类问题。\n"
        "不要用于：角色结构化档案能直接回答的数值事实。",
        KnowledgeSearchArgs,
    ),
]

SYSTEM = """你是星穹列车智库的主控大脑「黑塔」，通过调用工具回答《崩坏：星穹铁道》相关问题。
规则：
1. 需要数据（角色/配队/材料/剧情）时主动调用工具，不等用户说"去查"。
2. 问候、寒暄、闲聊不调用任何工具，直接回答，1-3 句。
3. 用户问到你没有的能力（如天气、实时战绩），如实说明做不到，禁止调用不存在的工具。
4. 查不到就如实说明查了什么、缺什么，禁止编造。"""

# (编号, 查询, 判定函数名)
QUERIES: list[tuple[str, str, str]] = [
    ("T01", "流萤怎么配队，我不要限定五星", "t01"),
    ("T02", "帮我看看景元的养成还缺什么材料", "t02"),
    ("T03", "三年前今天我深渊什么成绩", "t03"),
    ("T05", "今天天气怎么样", "t05"),
    ("T06", "查下景元档案，顺便配个队", "t06"),
    ("T07", "你好呀", "t07"),
    # 工作簿 7.3 提案：未接入能力（weekly_planning 未包装成工具，模型也拿不到用户角色池）
    # → 期望"这个能力我还没接入"式诚实收口，而不是编造个人化结论。
    ("T09", "帮我按我角色池的情况，排一下这周体力刷什么", "t09"),
]


def _names(calls: list[dict[str, Any]]) -> list[str]:
    return [str(call.get("name") or "") for call in calls]


def _judge(qid: str, calls: list[dict[str, Any]]) -> str:
    names = _names(calls)
    if qid == "T01":
        hit = "team_recommendation" in names
        arg_ok = any(
            "流萤" in json.dumps(call.get("args") or {}, ensure_ascii=False)
            for call in calls
            if call.get("name") == "team_recommendation"
        )
        return "PASS" if hit and arg_ok else ("PARTIAL" if hit else "FAIL")
    if qid == "T02":
        return "PASS" if "character_materials" in names else (
            "PARTIAL" if "knowledge_search" in names else "FAIL"
        )
    if qid == "T03":
        if not names:
            return "PASS"
        return "PARTIAL" if names == ["knowledge_search"] else "FAIL"
    if qid == "T05":
        return "PASS" if not names else "FAIL"
    if qid == "T06":
        both = {"character_profile", "team_recommendation"} <= set(names)
        return "PASS" if both else ("PARTIAL" if names else "FAIL")
    if qid == "T07":
        return "PASS" if not names else "FAIL"
    if qid == "T09":
        if not names:
            return "PASS"
        return "PARTIAL" if names == ["knowledge_search"] else "FAIL"
    return "UNJUDGED"


def _client(provider: str) -> ChatOpenAI:
    if provider == "zhipu":
        return ChatOpenAI(
            api_key=settings.zhipu_api_key,
            base_url=settings.zhipu_base_url,
            model=settings.zhipu_intent_model or settings.zhipu_pro_model,
            temperature=0.1,
            timeout=PER_CALL_TIMEOUT,
            max_retries=2,
            extra_body={"thinking": {"type": "disabled"}},
        )
    if provider == "deepseek":
        return ChatOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_flash_model or settings.deepseek_model,
            temperature=0.1,
            timeout=PER_CALL_TIMEOUT,
            max_retries=2,
        )
    raise ValueError(f"未知 provider: {provider}")


async def run_provider(provider: str) -> None:
    llm = _client(provider).bind_tools(TOOLS)
    model_name = llm.model_name if hasattr(llm, "model_name") else provider
    print(f"\n===== provider={provider} model={model_name} =====")
    results: list[dict[str, Any]] = []
    for qid, text, _ in QUERIES:
        try:
            ai = await asyncio.wait_for(
                llm.ainvoke([SystemMessage(content=SYSTEM), HumanMessage(content=text)]),
                PER_CALL_TIMEOUT,
            )
            calls = [
                {"name": call.get("name"), "args": call.get("args")}
                for call in (getattr(ai, "tool_calls", None) or [])
            ]
            content = str(ai.content or "").strip()
            verdict = _judge(qid, calls)
            print(
                f"[{qid}] {verdict} | tools={_names(calls) or '无'}"
                f" | text={content[:60]!r}"
            )
            if calls:
                print(f"      args={json.dumps([c['args'] for c in calls], ensure_ascii=False)[:220]}")
            results.append({"qid": qid, "verdict": verdict, "tools": _names(calls)})
        except Exception as exc:  # noqa: BLE001
            print(f"[{qid}] ERROR | {type(exc).__name__}: {str(exc)[:160]}")
            results.append({"qid": qid, "verdict": "ERROR", "error": type(exc).__name__})
    passed = sum(1 for item in results if item["verdict"] == "PASS")
    partial = sum(1 for item in results if item["verdict"] == "PARTIAL")
    errored = sum(1 for item in results if item["verdict"] == "ERROR")
    print(f"--- {provider} 小计: PASS={passed}/{len(results)} PARTIAL={partial} ERROR={errored}")

    if provider == "zhipu":
        # 探针：现役 provider 给所有请求带 response_format=json_object，
        # 验证它与 tools 同请求是否冲突（FC 路径的必改点确认）。
        probe_llm = ChatOpenAI(
            api_key=settings.zhipu_api_key,
            base_url=settings.zhipu_base_url,
            model=settings.zhipu_intent_model or settings.zhipu_pro_model,
            temperature=0.1,
            timeout=PER_CALL_TIMEOUT,
            max_retries=1,
            model_kwargs={"response_format": {"type": "json_object"}},
            extra_body={"thinking": {"type": "disabled"}},
        ).bind_tools(TOOLS)
        try:
            ai = await asyncio.wait_for(
                probe_llm.ainvoke(
                    [SystemMessage(content=SYSTEM), HumanMessage(content=QUERIES[0][1])]
                ),
                PER_CALL_TIMEOUT,
            )
            calls = getattr(ai, "tool_calls", None) or []
            print(
                f"[探针] tools+json_object 同请求: 可用 | tool_calls={_names(calls)}"
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"[探针] tools+json_object 同请求: 冲突 | "
                f"{type(exc).__name__}: {str(exc)[:160]}"
            )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--providers",
        nargs="+",
        default=["zhipu", "deepseek"],
        choices=["zhipu", "deepseek"],
    )
    args = parser.parse_args()
    for provider in args.providers:
        try:
            await run_provider(provider)
        except Exception as exc:  # noqa: BLE001
            print(f"provider={provider} 整体失败: {type(exc).__name__}: {str(exc)[:200]}")


if __name__ == "__main__":
    asyncio.run(main())
