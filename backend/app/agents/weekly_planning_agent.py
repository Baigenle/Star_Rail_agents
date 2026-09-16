import re

from app.agents.base import AgentContext, BaseAgent
from app.schemas.ai_response import (
    AIResponse,
    Citation,
    Claim,
    FilteringReport,
    QueryStep,
    ValidationReport,
)


class WeeklyPlanningAgent(BaseAgent):
    name = "weekly_planning_agent"
    description = "根据用户启用中的养成方案生成每周体力规划入口"

    async def run(self, context: AgentContext) -> AIResponse:
        plans = context.entities.get("active_progression_plans", [])
        budget_match = re.search(r"(\d{3,4})\s*(?:点)?体力", context.message)
        budget = int(budget_match.group(1)) if budget_match else 1680
        budget = max(0, min(2400, budget))
        citations = [
            Citation(
                id=f"C{index}",
                title=str(plan["name"]),
                source="用户已保存的养成方案",
                excerpt=f"优先级 {plan['priority']}；状态 active。",
                document_id=str(plan["id"]),
                entity_url="/planning",
            )
            for index, plan in enumerate(plans, start=1)
        ]
        claims = [
            Claim(
                statement=f"本周优先处理养成方案“{plan['name']}”。",
                confidence=1.0,
                citation_ids=[f"C{index}"],
            )
            for index, plan in enumerate(plans, start=1)
        ]
        return AIResponse(
            agent=self.name,
            answer=(
                f"我会按 {budget} 点本周体力读取 {len(plans)} 份启用方案，"
                "历战余响优先，再安排凝滞虚影、拟造花萼和侵蚀隧洞。"
                "到“每周养成规划”生成可勾选任务。"
            ),
            claims=claims,
            citations=citations,
            validation=ValidationReport(
                status="verified" if citations else "partially_verified",
                method="confirmed_progression_plan_snapshot",
                evidence_count=len(citations),
                notes=["副本体力成本使用仓库内固定规则，掉落数量不足时不推算完成次数。"],
            ),
            filtering=FilteringReport(
                passed=bool(citations),
                removed_claims=0,
                rules=["只读取用户主动保存且启用的养成方案。", "不虚构副本掉落数量。"],
                warnings=[] if citations else ["当前没有启用中的养成方案。"],
            ),
            query_steps=[
                QueryStep(
                    id="weekly_planning",
                    name="每周规划 Agent",
                    status="completed" if citations else "fallback",
                    detail=f"读取 {len(plans)} 份启用方案，本周体力预算为 {budget}。",
                    duration_ms=0,
                )
            ],
        )
