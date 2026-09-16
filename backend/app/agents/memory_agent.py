from app.agents.base import AgentContext, BaseAgent
from app.schemas.ai_response import (
    AIResponse,
    Citation,
    Claim,
    FilteringReport,
    QueryStep,
    ValidationReport,
)
from app.services.memory_service import MemoryService


class MemoryAgent(BaseAgent):
    name = "memory_agent"
    description = "提取可由用户确认的长期记忆候选，不直接写入数据库"

    async def run(self, context: AgentContext) -> AIResponse:
        suggestions = MemoryService.suggestions(context.message)
        citations = [
            Citation(
                id=f"C{index}",
                title="用户本轮明确输入",
                source="当前会话",
                excerpt=item.content,
            )
            for index, item in enumerate(suggestions, start=1)
        ]
        claims = [
            Claim(
                statement=f"可确认记忆：{item.content}",
                confidence=1.0,
                citation_ids=[f"C{index}"],
            )
            for index, item in enumerate(suggestions, start=1)
        ]
        return AIResponse(
            agent=self.name,
            answer=(
                "我提取出了记忆候选；只有你点击“确认记忆”后才会保存。"
                if suggestions
                else "这句话还没有形成明确的长期偏好，请说得更具体些。"
            ),
            claims=claims,
            citations=citations,
            validation=ValidationReport(
                status="verified" if claims else "unverified",
                method="explicit_user_statement_extraction",
                evidence_count=len(citations),
                notes=["记忆候选不会自动写入。"],
            ),
            filtering=FilteringReport(
                passed=bool(claims),
                removed_claims=0,
                rules=["只提取用户明确表达的偏好。", "必须由用户再次确认。"],
            ),
            query_steps=[
                QueryStep(
                    id="memory_candidate",
                    name="长期记忆 Agent",
                    status="completed" if claims else "fallback",
                    detail=f"提取 {len(claims)} 条待确认记忆候选。",
                    duration_ms=0,
                )
            ],
        )
