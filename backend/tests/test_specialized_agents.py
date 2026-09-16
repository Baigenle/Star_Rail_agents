import asyncio
from pathlib import Path

from app.agents.base import AgentContext
from app.agents.material_query_agent import MaterialQueryAgent
from app.agents.activity_strategy_agent import ActivityStrategyAgent
from app.agents.router_agent import RouterAgent
from app.schemas.ai_response import (
    AIResponse,
    Citation,
    Claim,
    FilteringReport,
    ValidationReport,
)


DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs"


class FakeRAGAgent:
    name = "rag_agent"
    docs_root = DOCS_ROOT

    async def run(self, context):
        return AIResponse(
            agent=self.name,
            answer="阶段化证据摘要 [C1]",
            claims=[
                Claim(statement="先保证生存。", confidence=0.8, citation_ids=["C1"]),
                Claim(statement="再处理核心机制。", confidence=0.8, citation_ids=["C1"]),
                Claim(statement="最后优化轮次。", confidence=0.7, citation_ids=["C1"]),
            ],
            citations=[
                Citation(
                    id="C1",
                    title="攻略记录",
                    source="docs/guide.md",
                    excerpt="经过验证的攻略记录",
                )
            ],
            validation=ValidationReport(
                status="verified", method="fake", evidence_count=1
            ),
            filtering=FilteringReport(passed=True, removed_claims=0),
        )


def test_material_agent_prefers_structured_character_materials() -> None:
    agent = MaterialQueryAgent(DOCS_ROOT, FakeRAGAgent())
    result = asyncio.run(
        agent.run(
            AgentContext(
                user_id=None,
                message="阮·梅突破和行迹需要什么材料？",
            )
        )
    )

    assert result.agent == "material_query_agent"
    assert result.citations
    assert all(citation.entity_url for citation in result.citations)
    assert "信用点" in result.answer
    assert result.query_steps[0].id == "structured_material_lookup"


def test_router_registers_specialized_agents() -> None:
    router = RouterAgent(FakeRAGAgent(), docs_root=DOCS_ROOT)

    assert router.agent_for_intent("material_query").name == "material_query_agent"
    assert router.agent_for_intent("team_recommendation").name == "team_recommendation_agent"
    assert router.agent_for_intent("character_build").name == "character_build_agent"
    assert router.agent_for_intent("weekly_plan").name == "weekly_planning_agent"
    assert router.agent_for_intent("activity_strategy").name == "activity_strategy_agent"
    assert (
        router.agent_for_intent("story_analysis").name
        == "story_analysis_agent"
    )
    assert (
        router.classify_intent("阮·梅突破和行迹需要什么材料")
        == "material_query"
    )
    assert router.classify_intent("幻造圣杯战争活动攻略") == "activity_strategy"


def test_activity_strategy_agent_uses_version_44_structured_evidence() -> None:
    result = asyncio.run(
        ActivityStrategyAgent(DOCS_ROOT).run(
            AgentContext(user_id=None, message="位面分裂活动怎么玩")
        )
    )

    assert result.agent == "activity_strategy_agent"
    assert result.claims
    assert result.citations
    assert "4.4" in result.answer
    assert result.query_steps[-1].id == "activity_strategy"


def test_natural_character_training_question_returns_actionable_build_guide() -> None:
    router = RouterAgent(FakeRAGAgent(), docs_root=DOCS_ROOT)

    result = asyncio.run(
        router.run(AgentContext(user_id=None, message="我要养火花怎么养"))
    )

    assert result.agent == "character_build_agent"
    assert "光锥" in result.answer
    assert "隧洞遗器" in result.answer
    assert "位面饰品" in result.answer
    assert "现有资料未给出可信优先级" in result.answer
    assert any("光锥" in claim.statement for claim in result.claims)
    assert any("隧洞遗器" in claim.statement for claim in result.claims)
    assert any("位面饰品" in claim.statement for claim in result.claims)
    assert any("可信技能优先级" in claim.statement for claim in result.claims)
    assert any(item.entity_url == "/characters/1501" for item in result.citations)
