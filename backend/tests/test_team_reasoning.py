import asyncio
import json

from app.api.v1.routes.teams import _team
from app.llm.base import LLMMessage
from app.services.team_reasoning_service import TeamReasoningService
from app.services.team_recommendation_service import TeamRecommendationService
from pathlib import Path


DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs"


class FakeTeamLLM:
    name = "fake-team-reasoner"

    async def complete(self, messages: list[LLMMessage]) -> str:
        payload = json.loads(messages[-1].content)
        team = payload["teams"][0]
        assert team["score_breakdown"]["scoring_version"] == "team_score_v3"
        assert team["rotation"]["speed_order"]
        return json.dumps(
            {
                "assessments": [
                    {
                        "member_ids": list(reversed(team["member_ids"])),
                        "verdict": "compatible",
                        "reasoning": "定位完整，辅助机制可以服务核心输出循环。",
                        "strengths": ["辅助与生存定位完整"],
                        "weaknesses": ["仍需按敌人弱点调整"],
                    },
                    {
                        "member_ids": ["unknown-1", "unknown-2", "unknown-3", "unknown-4"],
                        "verdict": "compatible",
                        "reasoning": "不得进入结果",
                        "strengths": [],
                        "weaknesses": [],
                    },
                ]
            },
            ensure_ascii=False,
        )

    async def stream(self, messages: list[LLMMessage]):
        if False:
            yield ""


def test_model_assessment_can_explain_but_not_replace_candidate_members_or_score() -> None:
    recommendation = TeamRecommendationService(DOCS_ROOT).recommend_official(
        core_character_id="1412",
        owned_character_ids={"1412", "1303", "1208", "1101", "1201"},
        preferred_character_ids=set(),
    )
    original = _team(recommendation.owned[0])

    assessed, model_name = asyncio.run(
        TeamReasoningService(FakeTeamLLM()).assess([original])
    )

    assert model_name == "fake-team-reasoner"
    assert [item.character_id for item in assessed[0].members] == [
        item.character_id for item in original.members
    ]
    assert assessed[0].score == original.score
    assert assessed[0].model_verdict == "compatible"
    assert "定位完整" in (assessed[0].model_assessment or "")
