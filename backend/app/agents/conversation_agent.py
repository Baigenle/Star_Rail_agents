from app.agents.base import AgentContext, BaseAgent
from app.agents.capability import feature_answer, find_feature, overview_answer
from app.schemas.ai_response import (
    AIResponse,
    FilteringReport,
    QueryStep,
    ValidationReport,
)


class ConversationAgent(BaseAgent):
    name = "conversation_agent"
    description = "处理问候、致谢和能力说明，不检索或编造游戏事实"

    async def run(self, context: AgentContext) -> AIResponse:
        message = context.message
        task_mode = context.intent_metadata.get("task_mode")
        if task_mode == "capability_intro":
            feature = find_feature(message)
            if feature:
                answer = feature_answer(feature)
                detail = f"介绍功能「{feature['title']}」的用途与用法。"
            else:
                answer = overview_answer()
                detail = "基于能力注册表介绍系统能力清单。"
        elif task_mode == "assistant_identity":
            answer = (
                "我是负责这套列车智库的黑塔主 Agent，不是角色档案里的"
                "“大黑塔”或“小黑塔”。你若想比较游戏角色的身份或关系，"
                "可以直接说清角色名，我再让剧情解析 Agent 按文献查证。"
            )
            detail = "识别为助手身份询问，没有调用角色知识库。"
        elif task_mode == "ambiguous_multi_character":
            answer = (
                "先别让我替你乱猜。你提到的是多个角色，但还没说明想查"
                "剧情关系、比较养成，还是判断能否一起配队。"
            )
            detail = "多角色任务目标不明确，等待用户选择任务类型。"
        elif task_mode == "ambiguous_catalog_term":
            answer = (
                "你说的“星穹”有歧义：是想问物品“星琼”、地点与载具"
                "“星穹列车”，还是游戏名称中的“星穹”？确认一个，本天才再调用"
                "对应知识域，免得拿剧情台词冒充定义。"
            )
            detail = "检测到相近术语歧义，未调用知识库。"
        elif context.intent == "conversation_recall":
            answer = self._history_answer(context.conversation_history)
            detail = "读取当前会话最近消息并直接复述，没有调用知识库。"
        elif any(token in message for token in ("谢谢", "谢了", "感谢")):
            answer = "不用谢。把下一件事说清楚，本天才继续处理。"
            detail = "识别为致谢，本轮无需调用知识库。"
        elif any(token in message for token in ("你是谁", "自我介绍", "能做什么")):
            answer = (
                "我是黑塔，现在负责这套列车智库。角色档案、配队、养成、材料、"
                "攻略和每周体力安排都可以交给我；涉及游戏事实时，我会先检索再回答。"
            )
            detail = "识别为助手能力说明，本轮无需调用知识库。"
        else:
            answer = "我在。直接说你想查哪个角色，或者要处理配队、养成和材料。"
            detail = "识别为问候或闲聊，本轮无需调用知识库。"
        return AIResponse(
            agent=self.name,
            answer=answer,
            claims=[],
            citations=[],
            validation=ValidationReport(
                status="verified",
                method="deterministic_conversation_response",
                evidence_count=0,
                notes=["本轮仅处理日常对话，没有生成游戏事实。"],
            ),
            filtering=FilteringReport(
                passed=True,
                removed_claims=0,
                rules=["日常对话不得夹带未经检索的游戏事实。"],
            ),
            query_steps=[
                QueryStep(
                    id="conversation",
                    name="普通对话",
                    status="completed",
                    detail=detail,
                    duration_ms=0,
                )
            ],
        )

    @staticmethod
    def _history_answer(history: list[dict[str, str]]) -> str:
        if not history:
            return "当前会话还没有更早的消息。你可以直接告诉我想接着处理什么。"
        recent = history[-6:]
        lines = [
            f"{'你' if item.get('role') == 'user' else '我'}："
            f"{str(item.get('content', '')).strip()[:240]}"
            for item in recent
            if str(item.get("content", "")).strip()
        ]
        return "当前会话最近谈过这些：\n\n" + "\n".join(lines)
