"""Phase 1.3 工具补齐的覆盖与安全执行测试。"""

from __future__ import annotations

import pytest

from app.agents.base import AgentContext
from app.agents.fc_tools import safe_execute
from app.core.config import settings


EXPECTED_TOOLS = {
    "catalog_search",
    "character_profile",
    "character_materials",
    "team_recommendation",
    "knowledge_search",
    "character_build",
    "activity_strategy",
    "weekly_planning",
    "custom_character_guide",
    "custom_character_review",
}


@pytest.fixture(scope="module")
def fc_definitions():
    settings.main_agent_impl = "fc"
    from app.api.dependencies import get_herta_main_agent

    get_herta_main_agent.cache_clear()
    agent = get_herta_main_agent()
    return agent.definitions


def test_tool_coverage_complete(fc_definitions):
    assert EXPECTED_TOOLS <= set(fc_definitions)
    assert len(fc_definitions) == len(EXPECTED_TOOLS)
    # 每个新工具都有四段式描述（含"何时用"与"返回约定"关键段）
    for name in ("character_build", "activity_strategy", "weekly_planning",
                 "custom_character_guide", "custom_character_review"):
        desc = fc_definitions[name].description
        assert "何时用" in desc and "返回约定" in desc


def test_all_specs_bindable(fc_definitions):
    specs = [d.spec() for d in fc_definitions.values()]
    assert len(specs) == len(EXPECTED_TOOLS)
    for spec in specs:
        assert spec["type"] == "function"
        assert spec["function"]["parameters"].get("properties") is not None


@pytest.mark.asyncio
async def test_weekly_planning_safe_execute_without_user(fc_definitions):
    """未登录（无养成方案数据）时不得抛异常，观察文本非空。"""
    definition = fc_definitions["weekly_planning"]
    context = AgentContext(user_id=None, message="这周体力怎么分配")
    text, result = await safe_execute(definition, {"request": "这周体力怎么分配"}, context)
    assert text
    assert not text.startswith("[错误·运行时]")


@pytest.mark.asyncio
async def test_custom_character_review_without_login(fc_definitions):
    """未登录时自查工具应给出可转述的引导/无结果，而不是崩溃。"""
    definition = fc_definitions["custom_character_review"]
    context = AgentContext(user_id=None, message="帮我看看我的角色")
    text, _ = await safe_execute(definition, {"request": "帮我看看我的角色"}, context)
    assert text
