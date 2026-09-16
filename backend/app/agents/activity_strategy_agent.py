import json
import re
from pathlib import Path

from app.agents.base import AgentContext, BaseAgent
from app.llm.base import LLMMessage, LLMProvider
from app.schemas.ai_response import (
    AIResponse,
    Citation,
    Claim,
    FilteringReport,
    QueryStep,
    ValidationReport,
)
from app.services.activity_service import ActivityService


class ActivityStrategyAgent(BaseAgent):
    name = "activity_strategy_agent"
    description = "依据 4.4 官方活动资料生成有引用的活动说明与攻略总结"

    def __init__(
        self, docs_root: Path, llm: LLMProvider | None = None
    ) -> None:
        self.service = ActivityService(docs_root)
        self.llm = llm

    async def run(self, context: AgentContext) -> AIResponse:
        activity = self._match(context.message)
        if activity is None or not activity.get("detail_available"):
            return self._not_available(activity)

        claims: list[Claim] = []
        citations: list[Citation] = []
        for index, section in enumerate(
            (activity.get("detail") or {}).get("sections", []), start=1
        ):
            paragraphs = [
                str(item).strip()
                for item in section.get("paragraphs", [])
                if str(item).strip()
            ]
            if not paragraphs:
                continue
            citation_id = f"C{index}"
            citations.append(
                Citation(
                    id=citation_id,
                    title=f"{activity['title']} · {section.get('title') or '活动资料'}",
                    source=str(activity.get("source", {}).get("url") or "本地活动资料"),
                    excerpt="\n".join(paragraphs),
                    document_id=activity["id"],
                    game_version=activity["version"],
                    entity_url=f"/activities/{activity['id']}",
                    image_url=(activity.get("image") or {}).get("api_path"),
                )
            )
            for paragraph in paragraphs:
                claims.append(
                    Claim(
                        statement=paragraph,
                        confidence=0.97,
                        citation_ids=[citation_id],
                    )
                )

        answer = await self._compose(context.message, activity, citations)
        return AIResponse(
            agent=self.name,
            answer=answer,
            claims=claims,
            citations=citations,
            validation=ValidationReport(
                status="verified" if claims else "unverified",
                method="version_4_4_structured_activity_evidence",
                evidence_count=len(citations),
                notes=[
                    "仅使用 4.4 活动结构化资料生成；活动界面中的实时剩余次数仍以游戏内显示为准。"
                ],
            ),
            filtering=FilteringReport(
                passed=bool(claims),
                removed_claims=0,
                rules=[
                    "往期活动不生成详情攻略。",
                    "未提供的掉落数量、敌人配置和实时开放状态不补造。",
                ],
                warnings=[] if claims else ["活动资料没有可引用的正文段落。"],
            ),
            query_steps=[
                QueryStep(
                    id="activity_strategy",
                    name="活动攻略 Agent",
                    status="completed" if claims else "fallback",
                    detail=(
                        f"锁定 4.4 活动「{activity['title']}」，读取官方活动说明并按用户问题组织攻略。"
                    ),
                    duration_ms=0,
                )
            ],
        )

    async def _compose(
        self, question: str, activity: dict, citations: list[Citation]
    ) -> str:
        evidence = [
            {"id": item.id, "title": item.title, "excerpt": item.excerpt}
            for item in citations
        ]
        if self.llm and evidence:
            prompt = (
                "你是活动攻略专业 Agent。只依据 evidence 充分回答 question，不添加资料中没有的"
                "数值、敌人或奖励。先说明活动机制，再给执行顺序、注意事项，并区分新手/中期/"
                "后期玩家；资料不足的阶段明确说明。每段用 [C编号] 引用。"
            )
            try:
                generated = await self.llm.complete(
                    [
                        LLMMessage(role="system", content=prompt),
                        LLMMessage(
                            role="user",
                            content=json.dumps(
                                {
                                    "question": question,
                                    "activity": activity["title"],
                                    "version": activity["version"],
                                    "evidence": evidence,
                                },
                                ensure_ascii=False,
                            ),
                        ),
                    ]
                )
                if generated.strip():
                    return generated.strip()
            except Exception:
                pass
        lines = [
            f"这是 4.4 版本活动「{activity['title']}」的可验证说明：",
        ]
        lines.extend(
            f"- {item.excerpt.replace(chr(10), ' ')} [{item.id}]"
            for item in citations
        )
        lines.append(
            "执行建议：先核对活动界面的剩余次数与截止时间，再按上述机制完成；"
            "现有资料没有区分玩家阶段的额外规则，因此不虚构分阶段打法。"
        )
        return "\n".join(lines)

    def _match(self, message: str) -> dict | None:
        normalized = re.sub(r"[\s·：:「」『』]", "", message).lower()
        candidates = [
            item
            for item in self.service.activities
            if item.get("version") == self.service.DETAIL_VERSION
        ]
        for item in candidates:
            title = re.sub(
                r"[\s·：:「」『』]", "", str(item.get("title", ""))
            ).lower()
            if title and (title in normalized or normalized in title):
                return self.service.get(item["id"])
        return None

    def _not_available(self, activity: dict | None) -> AIResponse:
        title = f"「{activity['title']}」" if activity else "该活动"
        return AIResponse(
            agent=self.name,
            answer=(
                f"{title}目前没有可用于攻略总结的 4.4 详细资料。"
                "你可以查看往期活动列表，但本天才不会拿简介硬编打法。"
            ),
            claims=[],
            citations=[],
            validation=ValidationReport(
                status="unverified",
                method="activity_version_policy",
                evidence_count=0,
                notes=["当前仅 4.4 活动开放详情与攻略。"],
            ),
            filtering=FilteringReport(
                passed=False,
                removed_claims=0,
                rules=["往期活动只展示索引，不生成详情攻略。"],
                warnings=["请明确提供 4.4 活动名称。"],
            ),
            query_steps=[
                QueryStep(
                    id="activity_strategy",
                    name="活动攻略 Agent",
                    status="fallback",
                    detail="未匹配到具备详细资料的 4.4 活动。",
                    duration_ms=0,
                )
            ],
        )
