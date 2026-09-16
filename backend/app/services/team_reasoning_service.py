import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.llm.base import LLMMessage, LLMProvider
from app.schemas.team import OfficialRecommendedTeam


class TeamModelAssessment(BaseModel):
    member_ids: list[str] = Field(min_length=4, max_length=4)
    verdict: Literal["compatible", "conditional", "not_recommended"]
    reasoning: str = Field(min_length=1, max_length=600)
    strengths: list[str] = Field(default_factory=list, max_length=4)
    weaknesses: list[str] = Field(default_factory=list, max_length=4)


class TeamModelAssessmentEnvelope(BaseModel):
    assessments: list[TeamModelAssessment] = Field(default_factory=list)
    ranking: list[list[str]] = Field(default_factory=list, max_length=12)


class TeamReasoningService:
    """终审裁判：解释候选并按体系视角微调排序，但不授予评分与换人权。"""

    def __init__(self, llm: LLMProvider | None) -> None:
        self.llm = llm

    async def assess(
        self,
        teams: list[OfficialRecommendedTeam],
        *,
        archetype_context: dict[str, dict] | None = None,
        allow_ranking: bool = True,
    ) -> tuple[list[OfficialRecommendedTeam], str | None]:
        if not self.llm or not teams:
            return teams, None
        context = archetype_context or {}
        payload = {
            "scoring_policy": {
                "candidate_generation": "定位、机制标签和历史共现只负责生成合法候选",
                "mechanical_simulation": "有同版本实战样本时60%，否则重新归一为80%",
                "observed_meta": "同版本且有来源和样本量时25%，否则不参与",
                "evidence_confidence": "有同版本实战样本时15%，否则重新归一为20%",
                "favorite_character": "0%，仅用于生成额外尝试队",
            },
            "teams": [
                {
                    "member_ids": [member.character_id for member in team.members],
                    "score": team.score,
                    "score_breakdown": (
                        team.score_breakdown.model_dump()
                        if team.score_breakdown
                        else None
                    ),
                    "rotation": (
                        team.rotation.model_dump() if team.rotation else None
                    ),
                    "data_warnings": team.data_warnings,
                    "members": [
                        {
                            "name": member.name,
                            "element": member.element,
                            "roles": member.roles,
                            "mechanic_tags": member.mechanic_tags,
                            "archetypes": context.get(
                                member.character_id, {}
                            ).get("archetypes", []),
                            "primary_stat": context.get(
                                member.character_id, {}
                            ).get("primary_stat", "attack"),
                            "core_mechanic": context.get(
                                member.character_id, {}
                            ).get("core_mechanic", ""),
                            "mechanic_engine": context.get(
                                member.character_id, {}
                            ).get("mechanic_engine", ""),
                            "mech_needs": context.get(
                                member.character_id, {}
                            ).get("mech_needs", []),
                            "team_notes": context.get(
                                member.character_id, {}
                            ).get("team_notes", ""),
                        }
                        for member in team.members
                    ],
                }
                for team in teams
            ],
        }
        try:
            raw = await self.llm.complete(
                [
                    LLMMessage(
                        role="system",
                        content=(
                            "你是星穹铁道配队终审裁判。候选成员和分数已经由确定性规则"
                            "校验，你只能依据给出的定位、体系归属与机制标签解释协同、"
                            "条件和短板；评分明细中的战技点、速度顺序、场景分和数据"
                            "警告也是可用证据。"
                            "不能更换成员、修改分数、忽略跨版本警告或引入未提供的角色机制。"
                            "评审必须基于成员的 mechanic_engine（机制引擎）与 mech_needs（机制需求）："
                            "逐条检查核心角色的硬需求（hard=true）是否有队友满足——"
                            "例如'生命值变动来源'由大额治疗/高频治疗/生命值扣除满足，小额低频治疗不满足；"
                            "击破主C需要超击破转化来源（同谐主/忘归人）；追击主C需要全队攻击频率；"
                            "DoT体系不吃双爆（暴击增益无价值，价值在攻击/能量/速度/全队拉条）；"
                            "同时利用 team_notes 里已验证的协同与等价类结论。"
                            "逐队返回 JSON；"
                            + (
                                "同时在 ranking 数组中把所有队伍按总体推荐"
                                "顺序排列（每项为一队的 member_ids，成员与顺序可变，但必须是"
                                "候选队成员集合的排列）。"
                                if allow_ranking
                                else "不要输出 ranking，排序以确定性分数为准。"
                            )
                            + "只返回："
                            '{"assessments":[{"member_ids":["id1","id2","id3","id4"],'
                            '"verdict":"compatible|conditional|not_recommended",'
                            '"reasoning":"依据标签的复核说明","strengths":["优点"],'
                            '"weaknesses":["限制"]}],'
                            '"ranking":[["id1","id2","id3","id4"]]}'
                        ),
                    ),
                    LLMMessage(
                        role="user",
                        content=json.dumps(payload, ensure_ascii=False),
                    ),
                ]
            )
            parsed = TeamModelAssessmentEnvelope.model_validate_json(
                self._json_object(raw)
            )
        except Exception:
            return teams, None

        allowed = {
            tuple(sorted(member.character_id for member in team.members)): team
            for team in teams
        }
        assessments = {
            tuple(sorted(item.member_ids)): item
            for item in parsed.assessments
            if tuple(sorted(item.member_ids)) in allowed
        }
        enriched = []
        for signature, team in allowed.items():
            assessment = assessments.get(signature)
            if assessment is None:
                enriched.append(team)
                continue
            enriched.append(
                team.model_copy(
                    update={
                        "model_assessment": assessment.reasoning,
                        "model_verdict": assessment.verdict,
                        "strengths": [
                            *team.strengths,
                            *assessment.strengths,
                        ][:6],
                        "weaknesses": [
                            *team.weaknesses,
                            *assessment.weaknesses,
                        ][:6],
                    }
                )
            )
        applied = any(
            item.model_assessment is not None for item in enriched
        )
        enriched = self._apply_ranking(
            enriched, parsed.ranking if allow_ranking else []
        )
        return enriched, self.llm.name if applied else None

    @staticmethod
    def _apply_ranking(
        teams: list[OfficialRecommendedTeam],
        ranking: list[list[str]],
    ) -> list[OfficialRecommendedTeam]:
        """终审排序权：ranking 必须是候选队成员集合的排列，非法排列忽略。"""
        if not ranking:
            return teams
        signature_order: dict[tuple[str, ...], int] = {}
        for index, member_ids in enumerate(ranking):
            key = tuple(sorted(str(item) for item in member_ids))
            signature_order.setdefault(key, index)
        if not signature_order:
            return teams
        return sorted(
            teams,
            key=lambda team: (
                signature_order.get(
                    tuple(sorted(member.character_id for member in team.members)),
                    len(signature_order),
                ),
            ),
        )

    @staticmethod
    def _json_object(raw: str) -> str:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(
                r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I
            )
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("team assessment did not contain JSON")
        return text[start : end + 1]
