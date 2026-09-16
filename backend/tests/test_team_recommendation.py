import asyncio
from pathlib import Path

import pytest

from app.agents.base import AgentContext
from app.agents.team_recommendation_agent import TeamRecommendationAgent
from app.services.team_recommendation_service import TeamRecommendationService


DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs"


def test_quantum_resistance_shred_prioritizes_quantum_dps_and_role_coverage() -> None:
    service = TeamRecommendationService(DOCS_ROOT)

    result = service.recommend(
        {
            "name": "量子观测员",
            "element": "量子",
            "path": "虚无",
            "roles": ["辅助"],
            "mechanic_tags": ["减抗", "量子增益"],
        }
    )

    assert len(result.theoretical) == 3
    for team in result.theoretical:
        assert team.members[0].is_custom is True
        official_ids = [member.character_id for member in team.members[1:]]
        assert len(official_ids) == len(set(official_ids)) == 3
        assert {"dps", "sustain"} <= set(team.covered_roles)
    assert any(
        member.element == "量子" and "dps" in member.roles
        for team in result.theoretical
        for member in team.members
    )


def test_owned_variants_only_use_owned_official_characters() -> None:
    service = TeamRecommendationService(DOCS_ROOT)
    owned = {"1102", "1306", "1208", "1201", "1110", "1101"}

    result = service.recommend(
        {
            "name": "量子观测员",
            "element": "量子",
            "path": "虚无",
            "roles": ["辅助"],
            "mechanic_tags": ["减抗"],
        },
        owned_character_ids=owned,
    )

    assert result.owned
    assert all(
        member.character_id in owned
        for team in result.owned
        for member in team.members
        if not member.is_custom
    )


def test_official_core_character_is_unique_and_favorites_are_separate_trials() -> None:
    service = TeamRecommendationService(DOCS_ROOT)
    result = service.recommend_official(
        core_character_id="1412",
        owned_character_ids={"1412", "1303", "1208", "1101", "1102", "1201"},
        preferred_character_ids={"1303"},
        excluded_character_ids={"1102"},
        require_sustain=True,
    )

    assert len(result.theoretical) == 3
    for team in [*result.theoretical, *result.owned]:
        ids = [member.character_id for member in team.members]
        assert ids[0] == "1412"
        assert len(ids) == len(set(ids)) == 4
        assert "1102" not in ids
        assert "sustain" in team.covered_roles
    assert all(
        member.character_id in {"1412", "1303", "1208", "1101", "1201"}
        for team in result.owned
        for member in team.members
    )
    assert any(
        "1303" in {member.character_id for member in team.members}
        for team in result.favorite_trials
    )
    assert all(team.preferred_character_ids for team in result.favorite_trials)


def test_favorite_character_does_not_change_base_team_scores() -> None:
    service = TeamRecommendationService(DOCS_ROOT)
    common = {
        "core_character_id": "1412",
        "owned_character_ids": {"1412", "1303", "1208", "1101", "1201"},
        "excluded_character_ids": set(),
        "require_sustain": True,
    }

    without_favorite = service.recommend_official(
        preferred_character_ids=set(), **common
    )
    with_favorite = service.recommend_official(
        preferred_character_ids={"1303"}, **common
    )

    assert [
        (tuple(member.character_id for member in team.members), team.score)
        for team in without_favorite.owned
    ] == [
        (tuple(member.character_id for member in team.members), team.score)
        for team in with_favorite.owned
    ]


def test_theoretical_teams_score_owned_members_before_missing_members() -> None:
    service = TeamRecommendationService(DOCS_ROOT)
    owned = {"1412", "1303", "1208", "1101"}
    result = service.recommend_official(
        core_character_id="1412",
        owned_character_ids=owned,
        preferred_character_ids={"1303"},
        excluded_character_ids=set(),
        require_sustain=True,
    )

    assert result.theoretical
    missing_counts = [
        sum(member.character_id not in owned for member in team.members)
        for team in result.theoretical
    ]
    assert missing_counts == sorted(missing_counts)
    assert all(count > 0 for count in missing_counts)
    owned_signatures = {
        tuple(member.character_id for member in team.members)
        for team in result.owned
    }
    assert all(
        tuple(member.character_id for member in team.members) not in owned_signatures
        for team in result.theoretical
    )


def test_pair_recommendations_keep_both_requested_characters() -> None:
    service = TeamRecommendationService(DOCS_ROOT)

    result = service.recommend_official(
        core_character_id="1306",
        required_character_ids={"1501"},
        owned_character_ids={"1306", "1501", "1208", "1101", "1201"},
        require_sustain=True,
    )

    assert result.theoretical
    for team in [*result.theoretical, *result.owned]:
        member_ids = {member.character_id for member in team.members}
        assert {"1306", "1501"} <= member_ids


def test_pair_question_returns_explicit_compatibility_verdict() -> None:
    agent = TeamRecommendationAgent(DOCS_ROOT)

    response = asyncio.run(
        agent.run(
            AgentContext(
                user_id=None,
                message="花火和火花可以一起配队吗？",
                entities={
                    "mentioned_characters": [
                        {"character_id": "1306", "name": "花火"},
                        {"character_id": "1501", "name": "火花"},
                    ]
                },
            )
        )
    )

    assert response.answer.startswith("结论：")
    assert "花火" in response.answer
    assert "火花" in response.answer
    assert "理论推荐" in response.answer  # v3 知识分下该对落进非优先推荐文案分支


def test_official_teams_are_ranked_with_versioned_mechanic_simulation() -> None:
    service = TeamRecommendationService(DOCS_ROOT)

    result = service.recommend_official(
        core_character_id="1412",
        owned_character_ids={"1412", "1303", "1208", "1101", "1201"},
        preferred_character_ids=set(),
        excluded_character_ids=set(),
        require_sustain=True,
    )

    assert result.owned
    for team in [*result.owned, *result.theoretical]:
        assert team.simulation is not None
        assert team.simulation.scoring_version == "team_score_v3"
        assert team.simulation.game_data_version == "4.4.51"
        assert len(team.simulation.scenarios) == 3
        assert team.score == team.simulation.final_score
    assert [team.score for team in result.owned] == sorted(
        (team.score for team in result.owned), reverse=True
    )


@pytest.mark.parametrize("character_id", ["1508", "1509"])
def test_incomplete_new_characters_cannot_be_used_as_team_core(
    character_id: str,
) -> None:
    service = TeamRecommendationService(DOCS_ROOT)

    with pytest.raises(ValueError, match="配队资料尚未完成"):
        service.recommend_official(core_character_id=character_id)
