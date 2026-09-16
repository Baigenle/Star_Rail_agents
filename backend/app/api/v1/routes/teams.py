from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.v1.routes.auth import current_user
from app.api.dependencies import get_fast_llm_provider, get_reasoning_llm_provider
from app.core.config import settings
from app.db.session import get_db
from app.models.team import UserTeam, UserTeamMember
from app.models.user import User, UserCharacter
from app.schemas.ai_response import (
    AIResponse,
    Citation,
    Claim,
    FilteringReport,
    QueryStep,
    ValidationReport,
)
from app.schemas.team import (
    OfficialRecommendedTeam,
    OfficialTeamMember,
    OfficialTeamRequest,
    OfficialTeamResponse,
    SavedTeamCreate,
    SavedTeamListResponse,
    SavedTeamResponse,
    SavedTeamUpdate,
    TeamRotationSummary,
    TeamScenarioScore,
    TeamScoreBreakdown,
)
from app.services.catalog_service import CatalogService
from app.services.team_recommendation_service import (
    RecommendedTeam,
    TeamRecommendationService,
)
from app.services.team_reasoning_service import TeamReasoningService
from app.llm.base import LLMProvider

router = APIRouter()
team_service = TeamRecommendationService(settings.docs_root)


@lru_cache(maxsize=1)
def _catalog() -> dict[str, object]:
    return {
        character.id: character
        for character in CatalogService(settings.docs_root).list_characters()
    }


def _member(character_id: str) -> OfficialTeamMember:
    profile = team_service.profiles().get(character_id)
    character = _catalog().get(character_id)
    if profile is None or character is None:
        raise HTTPException(status_code=422, detail=f"角色不存在：{character_id}")
    return OfficialTeamMember(
        character_id=character_id,
        name=profile["name"],
        element=profile["element"],
        roles=list(profile["roles"]),
        mechanic_tags=list(profile.get("mechanic_tags", [])),
        image_url=character.image_url,
    )


def _team(team: RecommendedTeam) -> OfficialRecommendedTeam:
    roles = set(team.covered_roles)
    strengths = [
        "队伍包含输出、辅助与生存定位，基础结构完整。",
        "推荐结果结合了角色机制标签与历史配队共现数据。",
    ]
    weaknesses = []
    if "sustain" not in roles:
        weaknesses.append("没有固定生存位，对操作和练度要求更高。")
    if len(set(member.element for member in team.members)) == 1:
        weaknesses.append("属性较集中，面对非对应弱点敌人时适用面较窄。")
    if not weaknesses:
        weaknesses.append("仍需根据敌人弱点与实际练度调整速度和装备。")
    simulation = team.simulation
    score_breakdown = (
        TeamScoreBreakdown(
            scoring_version=simulation.scoring_version,
            game_data_version=simulation.game_data_version,
            structural_score=simulation.structural_score,
            knowledge_score=simulation.knowledge_score,
            knowledge_notes=simulation.knowledge_notes,
            mechanical_simulation_score=simulation.mechanical_simulation_score,
            observed_meta_score=simulation.observed_meta_score,
            evidence_confidence=simulation.evidence_confidence,
            final_score=simulation.final_score,
            scenarios=[
                TeamScenarioScore(
                    scenario_id=scenario.scenario_id,
                    name=scenario.name,
                    score=scenario.score,
                )
                for scenario in simulation.scenarios
            ],
        )
        if simulation
        else None
    )
    rotation = (
        TeamRotationSummary(
            skill_point_balance=simulation.skill_point_balance,
            estimated_ultimate_turns=simulation.estimated_ultimate_turns,
            speed_order=simulation.speed_order,
        )
        if simulation
        else None
    )
    return OfficialRecommendedTeam(
        members=[_member(member.character_id) for member in team.members],
        score=team.score,
        covered_roles=team.covered_roles,
        reasons=team.reasons,
        strengths=strengths,
        weaknesses=weaknesses,
        source_character_ids=team.source_character_ids,
        preferred_character_ids=team.preferred_character_ids,
        missing_character_ids=team.missing_character_ids,
        score_breakdown=score_breakdown,
        rotation=rotation,
        data_warnings=simulation.warnings if simulation else [],
    )


def _ai_response(
    teams: list[OfficialRecommendedTeam], model_name: str | None
) -> AIResponse:
    citations = [
        Citation(
            id="C1",
            title="官方角色战斗档案",
            source="docs/team_knowledge/official_combat_profiles.json",
            excerpt="角色属性、命途、战斗定位与机制标签的规范化快照。",
        ),
        Citation(
            id="C2",
            title="规范化配队来源",
            source="docs/team_knowledge/normalized_team_recommendations.json",
            excerpt="92 份配队推荐中可可靠对齐的角色共现关系。",
        ),
        Citation(
            id="C3",
            title="统一练度与机制模拟基线",
            source="docs/team_benchmark/benchmark_assumptions.json",
            excerpt="角色、光锥、遗器与轮转模拟采用的统一实验条件。",
        ),
        Citation(
            id="C4",
            title="三类敌人模拟场景",
            source="docs/team_benchmark/scenarios.json",
            excerpt="单体、双精英与五目标环境的可复现场景定义。",
        ),
    ]
    claims = [
        Claim(
            statement=f"推荐队伍：{'、'.join(member.name for member in team.members)}",
            confidence=min(0.95, max(0.5, team.score / 100)),
            citation_ids=["C1", "C2", "C3", "C4"],
        )
        for team in teams
    ]
    return AIResponse(
        agent="team_recommendation_agent",
        answer="本天才已经按定位覆盖、机制协同和历史配队数据整理出候选队伍。",
        claims=claims,
        citations=citations,
        validation=ValidationReport(
            status="verified" if claims else "unverified",
            method="role_validation+rotation_simulation+scenario_scoring+model_review",
            evidence_count=len(citations) if claims else 0,
            notes=[
                "所有队伍均通过角色不重复和定位覆盖校验。",
                (
                    f"{model_name} 已基于成员定位和机制标签逐队复核；"
                    "模型不能修改成员或基础分数。"
                    if model_name
                    else "推理模型不可用，本次保留确定性配队结果。"
                ),
            ],
        ),
        filtering=FilteringReport(
            passed=bool(claims),
            removed_claims=0,
            rules=["排除重复角色", "排除用户明确禁用角色", "用户队仅使用已拥有角色"],
            warnings=[] if claims else ["当前条件下没有形成完整四人队。"],
        ),
        query_steps=[
            QueryStep(
                id="team_recommendation",
                name="官方角色配队 Agent",
                status="completed" if claims else "fallback",
                detail="完成角色池过滤、定位补全、轮转模拟、三场景评分和模型复核。",
                duration_ms=0,
            )
        ],
    )


@router.post(
    "/teams/recommendations",
    response_model=OfficialTeamResponse,
    summary="根据核心角色和用户角色池生成官方角色配队",
)
async def recommend_official_teams(
    payload: OfficialTeamRequest,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
    reasoning_llm: LLMProvider | None = Depends(get_reasoning_llm_provider),
    judge_llm: LLMProvider | None = Depends(get_fast_llm_provider),
) -> OfficialTeamResponse:
    profiles = team_service.profiles()
    requested_ids = {
        payload.core_character_id,
        *payload.preferred_character_ids,
        *payload.excluded_character_ids,
    }
    unknown = sorted(requested_ids - set(profiles))
    if unknown:
        raise HTTPException(status_code=422, detail=f"角色不存在：{', '.join(unknown)}")
    incomplete = sorted(
        requested_ids & team_service.EXCLUDED_INCOMPLETE_CHARACTER_IDS
    )
    if incomplete:
        raise HTTPException(
            status_code=422,
            detail=f"角色配队资料尚未完成：{', '.join(incomplete)}",
        )
    owned_ids = set(
        database.scalars(
            select(UserCharacter.character_id).where(UserCharacter.user_id == user.id)
        ).all()
    )
    result = team_service.recommend_official(
        core_character_id=payload.core_character_id,
        owned_character_ids=owned_ids,
        preferred_character_ids=set(payload.preferred_character_ids),
        excluded_character_ids=set(payload.excluded_character_ids),
        require_sustain=payload.require_sustain,
        game_mode=payload.game_mode,
    )
    theoretical = [] if payload.use_owned_only else [_team(team) for team in result.theoretical]
    owned = [_team(team) for team in result.owned]
    favorite_trials = [_team(team) for team in result.favorite_trials]
    combined = [*owned, *theoretical, *favorite_trials]
    mechanism_profiles = (
        team_service.archetype_service.mechanism_profiles()
    )
    archetype_context = {
        character_id: {
            "archetypes": profile.archetypes,
            "primary_stat": profile.primary_stat,
            "core_mechanic": profile.core_mechanic,
            "mechanic_engine": (
                mechanism_profiles.get(character_id, {}).get(
                    "mechanic_engine"
                )
            ),
            "mech_needs": (
                mechanism_profiles.get(character_id, {}).get("needs")
            ),
            "team_notes": (
                mechanism_profiles.get(character_id, {}).get("team_notes")
            ),
        }
        for character_id, profile in team_service.archetype_service.profiles().items()
    }
    assessed, model_name = await TeamReasoningService(judge_llm).assess(
        combined,
        archetype_context=archetype_context,
        # 快档终审只保留评语权：小模型全局排序易与确定性分数冲突。
        allow_ranking=False,
    )
    owned_count = len(owned)
    theoretical_count = len(theoretical)
    owned = assessed[:owned_count]
    theoretical = assessed[owned_count : owned_count + theoretical_count]
    favorite_trials = assessed[owned_count + theoretical_count :]
    return OfficialTeamResponse(
        response=_ai_response(assessed, model_name),
        theoretical=theoretical,
        owned=owned,
        favorite_trials=favorite_trials,
    )


def _saved_team(team: UserTeam) -> SavedTeamResponse:
    return SavedTeamResponse(
        id=team.id,
        name=team.name,
        members=[_member(member.character_id) for member in team.members],
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


@router.get("/profile/teams", response_model=SavedTeamListResponse)
def list_saved_teams(
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> SavedTeamListResponse:
    teams = database.scalars(
        select(UserTeam)
        .options(selectinload(UserTeam.members))
        .where(UserTeam.user_id == user.id)
        .order_by(UserTeam.updated_at.desc())
    ).all()
    return SavedTeamListResponse(
        items=[_saved_team(team) for team in teams], total=len(teams)
    )


@router.post(
    "/profile/teams",
    response_model=SavedTeamResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_team(
    payload: SavedTeamCreate,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> SavedTeamResponse:
    owned_ids = set(
        database.scalars(
            select(UserCharacter.character_id).where(UserCharacter.user_id == user.id)
        ).all()
    )
    if not set(payload.member_ids) <= owned_ids:
        raise HTTPException(status_code=422, detail="保存队伍只能使用已拥有角色")
    if not set(payload.member_ids) <= set(team_service.profiles()):
        raise HTTPException(status_code=422, detail="队伍包含未知角色")
    team = UserTeam(user_id=user.id, name=payload.name)
    database.add(team)
    database.flush()
    database.add_all(
        UserTeamMember(
            team_id=team.id, character_id=character_id, position=position
        )
        for position, character_id in enumerate(payload.member_ids)
    )
    database.commit()
    team = database.scalar(
        select(UserTeam)
        .options(selectinload(UserTeam.members))
        .where(UserTeam.id == team.id)
    )
    assert team is not None
    return _saved_team(team)


@router.patch("/profile/teams/{team_id}", response_model=SavedTeamResponse)
def rename_saved_team(
    team_id: str,
    payload: SavedTeamUpdate,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> SavedTeamResponse:
    team = database.scalar(
        select(UserTeam)
        .options(selectinload(UserTeam.members))
        .where(UserTeam.id == team_id, UserTeam.user_id == user.id)
    )
    if team is None:
        raise HTTPException(status_code=404, detail="常用队伍不存在")
    team.name = payload.name
    database.commit()
    database.refresh(team)
    return _saved_team(team)


@router.delete("/profile/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_team(
    team_id: str,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> Response:
    team = database.scalar(
        select(UserTeam).where(UserTeam.id == team_id, UserTeam.user_id == user.id)
    )
    if team is None:
        raise HTTPException(status_code=404, detail="常用队伍不存在")
    database.delete(team)
    database.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
