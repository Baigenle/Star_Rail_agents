from app.agents.base import AgentContext, BaseAgent
from app.schemas.ai_response import (
    AIResponse,
    FilteringReport,
    QueryStep,
    ValidationReport,
)


class CustomCharacterAgent(BaseAgent):
    name = "custom_character_agent"
    description = "引导用户进入隔离的玩家角色创作与自定义配队流程"

    async def run(self, context: AgentContext) -> AIResponse:
        if context.intent == "custom_team_recommendation":
            answer = "自定义角色配队要读取你已确认的角色版本。进入创作工坊打开对应角色，我会在那里生成理论队和“我的替代”队。"
        else:
            answer = "角色创作工坊已经准备好了。登录后进入“创作工坊”，我会分四个阶段和你把角色做完整。"
        return AIResponse(
            agent=self.name,
            answer=answer,
            claims=[],
            citations=[],
            validation=ValidationReport(
                status="unverified",
                method="workflow_routing",
                evidence_count=0,
                notes=["未在主聊天中读取私有草稿，避免跨用户数据泄露。"],
            ),
            filtering=FilteringReport(
                passed=True,
                removed_claims=0,
                rules=["玩家创作与官方 RAG 隔离"],
                warnings=[],
            ),
            query_steps=[
                QueryStep(
                    id="custom_character_route",
                    name="自定义角色 Agent",
                    status="completed",
                    detail="已路由到独立创作工坊流程。",
                    duration_ms=0,
                )
            ],
        )
