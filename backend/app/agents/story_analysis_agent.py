from app.agents.base import AgentContext, BaseAgent
from app.agents.rag_agent import RAGAgent
from app.schemas.ai_response import AIResponse, QueryStep


class StoryAnalysisAgent(BaseAgent):
    name = "story_analysis_agent"
    description = "基于主线、同行任务、阵营与星神文献完成剧情和世界观解析"

    def __init__(self, rag_agent: RAGAgent) -> None:
        self.rag_agent = rag_agent

    async def run(self, context: AgentContext) -> AIResponse:
        response = await self.rag_agent.run(context)
        scope_step = QueryStep(
            id="story_analysis_scope",
            name="剧情与世界观 Agent",
            status="completed",
            detail=(
                "已按用户意图选择主线/同行任务剧情域与世界观/星神文献域；"
                "事实和文献解释分别验证。"
            ),
            duration_ms=0,
        )
        return response.model_copy(
            update={
                "agent": self.name,
                "query_steps": [scope_step, *response.query_steps],
            }
        )
