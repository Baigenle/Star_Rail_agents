"""把提交前自查能力接入聊天链路的适配 Agent。

PlayerReviewAgent 只接受角色 payload；本适配器通过注入的 draft_provider
读取当前用户的草稿数据，完成审核后按统一问答契约输出报告与页面动作。
"""

from app.agents.base import AgentContext, BaseAgent
from app.agents.player_review_agent import PlayerReviewAgent
from app.llm.base import LLMProvider
from app.schemas.ai_response import (
    AgentAction,
    AIResponse,
    Claim,
    FilteringReport,
    QueryStep,
    ValidationReport,
)
from app.core.config import settings
from app.schemas.custom_character import (
    CustomCharacterPayload,
    SelfReviewReport,
)
from app.services.fabrication_detector import FabricationDetector

# async or sync callable (user_id) -> list[{"character_id","name","payload"}]
DraftProvider = object


class ChatCustomCharacterReviewAgent(BaseAgent):
    name = "custom_character_review_agent"
    description = "对玩家的原创角色草稿运行提交前自查并输出审核报告"

    def __init__(
        self,
        draft_provider: DraftProvider | None,
        llm: LLMProvider | None = None,
    ) -> None:
        self.draft_provider = draft_provider
        self.review_agent = PlayerReviewAgent(
            FabricationDetector(settings.docs_root),
            llm,
        )

    async def run(self, context: AgentContext) -> AIResponse:
        if not self.draft_provider:
            return self._unavailable(context)
        user_id = context.user_id
        drafts = []
        if user_id:
            drafts = list(await self._load_drafts(str(user_id)))
        if not drafts:
            return self._no_drafts(context)
        target = self._select_draft(drafts, context.message)
        if target is None:
            return self._ambiguous(drafts, context)
        report = await self.review_agent.review(
            CustomCharacterPayload.model_validate(target["payload"])
        )
        return self._report_response(target, report, context)

    async def _load_drafts(self, user_id: str) -> list[dict]:
        result = self.draft_provider(user_id)
        if hasattr(result, "__await__"):
            result = await result
        return result or []

    @staticmethod
    def _select_draft(
        drafts: list[dict], message: str
    ) -> dict | None:
        """按名称匹配草稿；同名多个时默认最近编辑的一个（列表已按更新时间倒序）。"""
        named = [
            draft
            for draft in drafts
            if str(draft.get("name") or "") and str(draft["name"]) in message
        ]
        if named:
            return named[0]
        if len(drafts) == 1:
            return drafts[0]
        return None

    def _base_response(self, context: AgentContext) -> AIResponse:
        return AIResponse(
            agent=self.name,
            answer="",
            claims=[],
            citations=[],
            validation=ValidationReport(
                status="unverified",
                method="player_self_review",
                evidence_count=0,
                notes=["自查报告面向玩家创作，不引用官方知识库。"],
            ),
            filtering=FilteringReport(
                passed=True,
                removed_claims=0,
                rules=["自查报告为建议性质，不参与官方 RAG。"],
            ),
            conversation_id=context.conversation_id,
        )

    def _unavailable(self, context: AgentContext) -> AIResponse:
        response = self._base_response(context)
        response.answer = (
            "自查服务当前没有可用的草稿数据通道。去创作工坊里直接点"
            "『运行玩家自助审核』也可以拿到同样的报告。"
        )
        return self._with_action(response)

    def _no_drafts(self, context: AgentContext) -> AIResponse:
        response = self._base_response(context)
        response.answer = (
            "你还没有可自查的原创角色草稿。先在创作工坊完成至少一个阶段，"
            "我再帮你检查完整度、乱编造内容和一致性。"
        )
        return self._with_action(response)

    def _ambiguous(self, drafts: list[dict], context: AgentContext) -> AIResponse:
        response = self._base_response(context)
        names = "、".join(
            str(draft.get("name") or "未命名") for draft in drafts[:5]
        )
        response.answer = (
            f"你有 {len(drafts)} 个草稿（{names}）。想审哪一个？"
            "直接把角色名告诉我；如果有同名草稿，我会默认审核最近编辑的那份。"
        )
        return self._with_action(response)

    def _report_response(
        self,
        draft: dict,
        report: SelfReviewReport,
        context: AgentContext,
    ) -> AIResponse:
        response = self._base_response(context)
        verdict_label = {
            "ready": "可以提交",
            "needs_work": "需要修改",
            "rejected": "暂不建议提交",
        }.get(report.verdict, report.verdict)
        lines = [
            f"《{draft.get('name')}》的自查结果：总分 {report.overall_score}/100，"
            f"结论：{verdict_label}。",
            report.summary,
            "",
        ]
        for category in report.categories:
            if not category.issues:
                continue
            lines.append(f"【{category.name} {category.score}分】")
            for issue in category.issues:
                prefix = "必须修复" if issue.severity == "error" else "建议"
                lines.append(
                    f"- （{prefix}）{issue.field}：{issue.description}"
                    f" 建议：{issue.suggestion}"
                )
        if report.highlights:
            lines.append("")
            lines.append("亮点：" + "；".join(report.highlights))
        lines.append("")
        lines.append(
            f"必须修复 {report.must_fix_count} 项，建议优化 {report.warn_count} 项。"
            "自查只是预审，最终以社区管理员审核为准。"
        )
        response.answer = "\n".join(lines)
        response.claims = [
            Claim(
                statement=(
                    f"{category.name}得分 {category.score}，"
                    f"包含 {len(category.issues)} 个问题。"
                ),
                confidence=0.95,
                claim_type="fact",
            )
            for category in report.categories
        ]
        response.validation = ValidationReport(
            status="partially_verified",
            method="deterministic_rules+llm_review"
            if report.model_used
            else "deterministic_rules_only",
            evidence_count=len(report.categories),
            notes=[
                "完整度、乱编造与一致性检查基于确定性规则；"
                + (
                    "语义层面检查由推理模型辅助完成。"
                    if report.model_used
                    else "推理模型不可用，语义检查未执行。"
                )
            ],
        )
        response.query_steps = [
            QueryStep(
                id="self_review",
                name="运行玩家自查审核",
                status="completed",
                detail=(
                    f"五维审核完成：总分 {report.overall_score}，"
                    f"必须修复 {report.must_fix_count} 项。"
                ),
            )
        ]
        return self._with_action(response)

    def _with_action(self, response: AIResponse) -> AIResponse:
        return response.model_copy(
            update={
                "actions": [
                    AgentAction(
                        action_type="navigate",
                        title="去创作工坊",
                        target_url="/creator",
                        description="查看草稿状态并按报告修改对应阶段",
                    )
                ]
            }
        )
