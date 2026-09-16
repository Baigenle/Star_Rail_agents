from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.routes.auth import current_user, is_admin_username, optional_current_user
from app.api.dependencies import get_optional_llm_provider, get_reasoning_llm_provider
from app.core.config import settings
from app.db.session import get_db
from app.llm.base import LLMProvider
from app.agents.player_review_agent import PlayerReviewAgent
from app.models.custom_character import (
    CustomCharacter,
    CustomCharacterMessage,
    CustomCharacterSession,
    CustomCharacterVersion,
)
from app.models.activity import ActivityGuide
from app.models.moderation import ModerationAction
from app.models.user import User, UserCharacter
from app.schemas.ai_response import (
    AIResponse,
    Citation,
    Claim,
    FilteringReport,
    QueryStep,
    ValidationReport,
)
from app.schemas.custom_character import (
    CreatorMessageRequest,
    CreatorSessionResponse,
    CreatorTurnResponse,
    CustomCharacterCreate,
    CustomCharacterListResponse,
    CustomCharacterPatch,
    CustomCharacterPayload,
    CustomCharacterResponse,
    CustomTeamResponse,
    RecommendedTeamResponse,
    ReviewRequest,
    SelfReviewReport,
    TeamMemberResponse,
)
from app.schemas.moderation import (
    CharacterAIAssessment,
    ModerationListItem,
    ModerationListResponse,
    ModerationRequest,
)
from app.services.custom_character_review_service import (
    CustomCharacterReviewService,
)
from app.services.team_recommendation_service import TeamRecommendationService
from app.services.custom_character_extraction import CustomCharacterFieldExtractor
from app.services.fabrication_detector import FabricationDetector

router = APIRouter()
team_service = TeamRecommendationService(settings.docs_root)

STAGE_FIELDS = {
    1: {"name", "rarity", "element", "path", "summary"},
    2: {"roles", "core_mechanics", "mechanic_tags"},
    3: {"base_stats", "skills"},
    4: {"special_skills", "story", "eidolons"},
}
STAGE_REQUIRED = {
    1: {"name", "rarity", "element", "path", "summary"},
    2: {"roles", "core_mechanics"},
    3: {"base_stats", "skills"},
    4: set(),
}
STAGE_QUESTIONS = {
    1: "先把基础档案定下来：名字、稀有度、属性、命途和一句角色简介。",
    2: "接着说战斗定位。主C、副C、辅助或生存，核心机制又是什么？",
    3: "现在补基础数值与普攻、战技、终结技、天赋、秘技。数值别凭空省略。",
    4: "最后是命途专属技能；故事和星魂可以现在写，也可以留到以后。",
}
CORE_SKILLS = {"basic", "skill", "ultimate", "talent", "technique"}


def _version(database: Session, character: CustomCharacter, version_id: str | None):
    return database.get(CustomCharacterVersion, version_id) if version_id else None


def _character_response(
    database: Session,
    character: CustomCharacter,
    version: CustomCharacterVersion,
    viewer: User | None,
) -> CustomCharacterResponse:
    author = database.get(User, character.author_id)
    return CustomCharacterResponse(
        id=character.id,
        author_id=character.author_id,
        author_name=author.display_name if author else "未知作者",
        name=character.name,
        visibility=character.visibility,
        version_id=version.id,
        version_number=version.version_number,
        status=version.status,
        payload=CustomCharacterPayload.model_validate(version.payload),
        review_reason=version.review_reason,
        is_owner=bool(viewer and viewer.id == character.author_id),
        created_at=character.created_at,
        updated_at=character.updated_at,
    )


def _get_visible(
    database: Session,
    character_id: str,
    viewer: User | None,
) -> tuple[CustomCharacter, CustomCharacterVersion]:
    character = database.get(CustomCharacter, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="自定义角色不存在")
    if viewer and viewer.id == character.author_id:
        version = _version(database, character, character.current_draft_version_id)
    else:
        version = _version(database, character, character.published_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="自定义角色不存在")
    return character, version


def _owned(
    database: Session, character_id: str, user: User
) -> tuple[CustomCharacter, CustomCharacterVersion]:
    character, version = _get_visible(database, character_id, user)
    if character.author_id != user.id:
        raise HTTPException(status_code=404, detail="自定义角色不存在")
    return character, version


def _ensure_editable_version(
    database: Session,
    character: CustomCharacter,
    version: CustomCharacterVersion,
) -> CustomCharacterVersion:
    if version.status in {"draft", "rejected"}:
        version.status = "draft"
        version.review_reason = None
        return version
    next_number = (
        database.scalar(
            select(func.max(CustomCharacterVersion.version_number)).where(
                CustomCharacterVersion.character_id == character.id
            )
        )
        or 0
    ) + 1
    draft = CustomCharacterVersion(
        character_id=character.id,
        version_number=next_number,
        status="draft",
        payload=dict(version.payload),
    )
    database.add(draft)
    database.flush()
    character.current_draft_version_id = draft.id
    return draft


@router.post(
    "/custom-characters",
    response_model=CustomCharacterResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_custom_character(
    payload: CustomCharacterCreate,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> CustomCharacterResponse:
    character = CustomCharacter(author_id=user.id, name=payload.name or "未命名角色")
    database.add(character)
    database.flush()
    initial_payload = {"name": payload.name} if payload.name else {}
    version = CustomCharacterVersion(
        character_id=character.id, version_number=1, payload=initial_payload
    )
    database.add(version)
    database.flush()
    character.current_draft_version_id = version.id
    database.commit()
    database.refresh(character)
    database.refresh(version)
    return _character_response(database, character, version, user)


@router.get("/custom-characters", response_model=CustomCharacterListResponse)
def list_my_custom_characters(
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> CustomCharacterListResponse:
    characters = database.scalars(
        select(CustomCharacter)
        .where(CustomCharacter.author_id == user.id)
        .order_by(CustomCharacter.updated_at.desc())
    ).all()
    items = [
        _character_response(
            database,
            character,
            _version(database, character, character.current_draft_version_id),
            user,
        )
        for character in characters
        if character.current_draft_version_id
    ]
    return CustomCharacterListResponse(items=items, total=len(items))


@router.get("/custom-characters/{character_id}", response_model=CustomCharacterResponse)
def get_custom_character(
    character_id: str,
    user: User | None = Depends(optional_current_user),
    database: Session = Depends(get_db),
) -> CustomCharacterResponse:
    character, version = _get_visible(database, character_id, user)
    return _character_response(database, character, version, user)


@router.patch(
    "/custom-characters/{character_id}", response_model=CustomCharacterResponse
)
def update_custom_character(
    character_id: str,
    payload: CustomCharacterPatch,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> CustomCharacterResponse:
    character, version = _owned(database, character_id, user)
    version = _ensure_editable_version(database, character, version)
    version.payload = payload.payload.model_dump(exclude_none=True)
    version.self_review = None
    character.name = payload.payload.name or character.name
    database.commit()
    database.refresh(character)
    database.refresh(version)
    return _character_response(database, character, version, user)


@router.post(
    "/custom-characters/{character_id}/sessions",
    response_model=CreatorSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_creator_session(
    character_id: str,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> CreatorSessionResponse:
    character, _ = _owned(database, character_id, user)
    session = CustomCharacterSession(
        character_id=character.id, author_id=user.id, stage=1
    )
    database.add(session)
    database.commit()
    database.refresh(session)
    return CreatorSessionResponse.model_validate(session, from_attributes=True)


@router.get(
    "/custom-characters/{character_id}/sessions/latest",
    response_model=CreatorSessionResponse,
)
def get_latest_creator_session(
    character_id: str,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> CreatorSessionResponse:
    character, _ = _owned(database, character_id, user)
    session = database.scalar(
        select(CustomCharacterSession)
        .where(
            CustomCharacterSession.character_id == character.id,
            CustomCharacterSession.author_id == user.id,
        )
        .order_by(CustomCharacterSession.updated_at.desc())
        .limit(1)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="创作会话不存在")
    return CreatorSessionResponse.model_validate(session, from_attributes=True)


def _owned_session(
    database: Session, session_id: str, user: User
) -> CustomCharacterSession:
    session = database.get(CustomCharacterSession, session_id)
    if session is None or session.author_id != user.id:
        raise HTTPException(status_code=404, detail="创作会话不存在")
    return session


def _creator_response(answer: str, *, status_name: str = "completed") -> AIResponse:
    return AIResponse(
        agent="custom_character_agent",
        answer=f"我是黑塔。{answer}",
        claims=[],
        citations=[],
        validation=ValidationReport(
            status="unverified",
            method="user_confirmed_structured_draft",
            evidence_count=0,
            notes=["创作内容是用户草稿，不属于官方游戏事实。"],
        ),
        filtering=FilteringReport(
            passed=True,
            removed_claims=0,
            rules=["不自动补造缺失数值", "仅接受官方属性与命途枚举"],
            warnings=[],
        ),
        query_steps=[
            QueryStep(
                id="creator_stage",
                name="黑塔创作工坊",
                status=status_name,
                detail="已记录用户明确提供的字段，等待阶段确认。",
                duration_ms=0,
            )
        ],
    )


def _turn(
    database: Session,
    session: CustomCharacterSession,
    character: CustomCharacter,
    version: CustomCharacterVersion,
    answer: str,
) -> CreatorTurnResponse:
    missing = sorted(
        key
        for key in STAGE_REQUIRED[session.stage]
        if not session.pending_fields.get(key) and not version.payload.get(key)
    )
    return CreatorTurnResponse(
        response=_creator_response(answer),
        character_id=character.id,
        session_id=session.id,
        stage=session.stage,
        draft=CustomCharacterPayload.model_validate(version.payload),
        pending_fields=session.pending_fields,
        required_fields=missing,
    )


@router.post(
    "/custom-character-sessions/{session_id}/messages",
    response_model=CreatorTurnResponse,
)
async def create_creator_message(
    session_id: str,
    payload: CreatorMessageRequest,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
    llm: LLMProvider | None = Depends(get_optional_llm_provider),
) -> CreatorTurnResponse:
    session = _owned_session(database, session_id, user)
    character, version = _owned(database, session.character_id, user)
    if session.status != "active":
        raise HTTPException(status_code=409, detail="创作会话已经完成")
    extracted_fields: dict[str, object] = {}
    extraction_warning = ""
    if not payload.fields and llm is not None:
        try:
            extracted_fields = await CustomCharacterFieldExtractor(llm).extract(
                stage=session.stage,
                message=payload.message,
                allowed_fields=STAGE_FIELDS[session.stage],
            )
        except (ValueError, TypeError):
            extraction_warning = " 模型提取失败，已切换为结构化表单，不会丢失现有草稿。"
    submitted_fields = {**extracted_fields, **payload.fields}
    unexpected = set(submitted_fields) - STAGE_FIELDS[session.stage]
    if unexpected:
        raise HTTPException(
            status_code=422, detail=f"当前阶段不接受字段：{', '.join(sorted(unexpected))}"
        )
    merged_payload = {**version.payload, **session.pending_fields, **submitted_fields}
    try:
        CustomCharacterPayload.model_validate(merged_payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="字段格式或枚举值无效") from exc
    session.pending_fields = {**session.pending_fields, **submitted_fields}
    database.add(
        CustomCharacterMessage(
            session_id=session.id,
            role="user",
            content=payload.message,
            stage=session.stage,
            structured_data=submitted_fields,
        )
    )
    answer = (
        f"第 {session.stage} 阶段的明确字段已经暂存。"
        f"{STAGE_QUESTIONS[session.stage]}确认前我不会把它写进正式草稿。"
        f"{extraction_warning}"
    )
    database.add(
        CustomCharacterMessage(
            session_id=session.id,
            role="assistant",
            content=answer,
            stage=session.stage,
            structured_data={},
        )
    )
    database.commit()
    database.refresh(session)
    return _turn(database, session, character, version, answer)


@router.post(
    "/custom-character-sessions/{session_id}/confirm-stage",
    response_model=CreatorTurnResponse,
)
def confirm_creator_stage(
    session_id: str,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> CreatorTurnResponse:
    session = _owned_session(database, session_id, user)
    character, version = _owned(database, session.character_id, user)
    missing = [
        key
        for key in STAGE_REQUIRED[session.stage]
        if not session.pending_fields.get(key) and not version.payload.get(key)
    ]
    if missing:
        raise HTTPException(
            status_code=422, detail=f"当前阶段还缺少：{', '.join(sorted(missing))}"
        )
    merged = {**version.payload, **session.pending_fields}
    if session.stage == 3 and not CORE_SKILLS <= set(merged.get("skills", {})):
        raise HTTPException(status_code=422, detail="核心技能必须包含普攻、战技、终结技、天赋和秘技")
    if session.stage == 4:
        path = merged.get("path")
        special = merged.get("special_skills", {})
        if path == "记忆" and not {"memosprite_skill", "memosprite_talent"} <= set(special):
            raise HTTPException(status_code=422, detail="记忆角色需要忆灵技与忆灵天赋")
        if path == "欢愉" and "elation_skill" not in special:
            raise HTTPException(status_code=422, detail="欢愉角色需要欢愉技")
    version.payload = CustomCharacterPayload.model_validate(merged).model_dump(
        exclude_none=True
    )
    version.self_review = None
    character.name = str(merged.get("name") or character.name)
    session.pending_fields = {}
    if session.stage < 4:
        session.stage += 1
        answer = f"第 {session.stage - 1} 阶段确认完成。{STAGE_QUESTIONS[session.stage]}"
    else:
        session.status = "completed"
        answer = "四个阶段都确认了。角色档案已经成为可保存、可配队的私有草稿。"
    database.commit()
    database.refresh(session)
    database.refresh(version)
    return _turn(database, session, character, version, answer)


def _team_response(character: CustomCharacter, version: CustomCharacterVersion, result):
    def convert(team) -> RecommendedTeamResponse:
        return RecommendedTeamResponse(
            members=[
                TeamMemberResponse(
                    character_id=member.character_id,
                    name=member.name,
                    element=member.element,
                    roles=member.roles,
                    is_custom=member.is_custom,
                )
                for member in team.members
            ],
            score=team.score,
            covered_roles=team.covered_roles,
            reasons=team.reasons,
            source_character_ids=team.source_character_ids,
        )

    theoretical = [convert(team) for team in result.theoretical]
    owned = [convert(team) for team in result.owned]
    citations = [
        Citation(
            id="C1",
            title=f"{character.name} 用户确认版本 v{version.version_number}",
            source="custom_character_version",
            excerpt="用户确认的属性、定位与机制标签。",
            document_id=version.id,
            entity_url=f"/creator/{character.id}",
        ),
        Citation(
            id="C2",
            title="官方角色战斗档案",
            source="docs/team_knowledge/official_combat_profiles.json",
            excerpt="官方角色属性、命途、定位及机制标签。",
        ),
        Citation(
            id="C3",
            title="规范化配队共现统计",
            source="docs/team_knowledge/normalized_team_recommendations.json",
            excerpt="由现有角色攻略配队推荐规范化得到的共现关系。",
        ),
    ]
    claims = [
        Claim(
            statement=f"推荐队伍 {index + 1}："
            + "、".join(member.name for member in team.members),
            confidence=min(0.95, max(0.5, team.score / 100)),
            citation_ids=["C1", "C2", "C3"],
        )
        for index, team in enumerate(theoretical)
    ]
    response = AIResponse(
        agent="custom_character_team_agent",
        answer="本天才已经按定位完整性、机制兼容、历史共现和属性协同筛完候选。",
        claims=claims,
        citations=citations,
        validation=ValidationReport(
            status="verified" if theoretical else "partially_verified",
            method="deterministic_team_scoring_and_role_validation",
            evidence_count=len(citations),
            notes=["每队包含自定义角色与三名不重复官方角色。"],
        ),
        filtering=FilteringReport(
            passed=bool(theoretical),
            removed_claims=0,
            rules=["队伍成员 ID 唯一", "定位覆盖校验", "我的替代仅使用已拥有角色"],
            warnings=[] if owned else ["当前角色池不足以生成三人官方替代队。"],
        ),
        query_steps=[
            QueryStep(
                id="custom_team",
                name="自定义角色配队 Agent",
                status="completed",
                detail="已完成确定性评分、角色池过滤与引用绑定。",
                duration_ms=0,
            )
        ],
    )
    return CustomTeamResponse(response=response, theoretical=theoretical, owned=owned)


@router.post(
    "/custom-characters/{character_id}/team-recommendations",
    response_model=CustomTeamResponse,
)
def recommend_custom_character_teams(
    character_id: str,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> CustomTeamResponse:
    character, version = _owned(database, character_id, user)
    payload = CustomCharacterPayload.model_validate(version.payload)
    if not payload.element or not payload.path or not payload.roles:
        raise HTTPException(status_code=422, detail="请先确认角色属性、命途和战斗定位")
    owned_ids = set(
        database.scalars(
            select(UserCharacter.character_id).where(
                UserCharacter.user_id == user.id
            )
        ).all()
    )
    result = team_service.recommend(
        {
            "name": payload.name,
            "element": payload.element,
            "path": payload.path,
            "roles": payload.roles,
            "mechanic_tags": payload.mechanic_tags,
        },
        owned_character_ids=owned_ids,
    )
    return _team_response(character, version, result)


def _validate_publishable(payload: CustomCharacterPayload) -> None:
    missing = [
        key
        for key in (
            "name",
            "rarity",
            "element",
            "path",
            "summary",
            "roles",
            "core_mechanics",
            "base_stats",
            "skills",
        )
        if not getattr(payload, key)
    ]
    if missing:
        raise HTTPException(status_code=422, detail=f"发布前还缺少：{', '.join(missing)}")
    if not CORE_SKILLS <= set(payload.skills):
        raise HTTPException(status_code=422, detail="发布前必须补全五项核心技能")


@router.post(
    "/custom-characters/{character_id}/self-review",
    response_model=SelfReviewReport,
)
async def review_own_custom_character(
    character_id: str,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
    llm: LLMProvider | None = Depends(get_reasoning_llm_provider),
) -> SelfReviewReport:
    _, version = _owned(database, character_id, user)
    if version.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="只有私有草稿可以重新自助审核")
    try:
        payload = CustomCharacterPayload.model_validate(version.payload)
    except Exception as exc:  # noqa: BLE001 - 未完成草稿按可修复错误引导
        missing = [
            field
            for field in (
                "name",
                "rarity",
                "element",
                "path",
                "summary",
                "roles",
                "core_mechanics",
                "base_stats",
            )
            if not (version.payload or {}).get(field)
        ]
        raise HTTPException(
            status_code=422,
            detail=(
                "草稿尚未达到可审核的最低完整度，请先回工坊补齐基础字段。"
                f"当前缺失：{'、'.join(missing) or '字段格式不符合规范'}"
            ),
        ) from exc
    report = await PlayerReviewAgent(
        FabricationDetector(settings.docs_root),
        llm,
    ).review(payload)
    version.self_review = report.model_dump(mode="json")
    database.commit()
    return report


@router.delete(
    "/custom-characters/{character_id}",
    summary="删除自己的原创角色草稿（含版本与会话）",
)
async def delete_own_custom_character(
    character_id: str,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> dict:
    from app.models.chat import ChatMessage
    from app.models.custom_character import (
        CustomCharacterMessage,
        CustomCharacterSession,
        CustomCharacterVersion,
    )

    character, _ = _owned(database, character_id, user)
    if character.published_version_id:
        raise HTTPException(
            status_code=409,
            detail="已发布到社区的作品不能直接删除，请先联系管理员下架。",
        )
    database.query(CustomCharacterVersion).filter(
        CustomCharacterVersion.character_id == character_id
    ).delete(synchronize_session=False)
    sessions = (
        database.query(CustomCharacterSession)
        .filter(CustomCharacterSession.character_id == character_id)
        .all()
    )
    for session in sessions:
        database.query(ChatMessage).filter(
            ChatMessage.conversation_id == session.id
        ).delete(synchronize_session=False)
        database.query(CustomCharacterMessage).filter(
            CustomCharacterMessage.session_id == session.id
        ).delete(synchronize_session=False)
        database.delete(session)
    database.delete(character)
    database.commit()
    return {"deleted": str(character_id)}


@router.get(
    "/custom-characters/{character_id}/self-review",
    response_model=SelfReviewReport,
)
def get_own_custom_character_review(
    character_id: str,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> SelfReviewReport:
    _, version = _owned(database, character_id, user)
    if not version.self_review:
        raise HTTPException(status_code=404, detail="当前草稿还没有有效的自助审核报告")
    return SelfReviewReport.model_validate(version.self_review)


@router.post(
    "/custom-characters/{character_id}/submit",
    response_model=CustomCharacterResponse,
)
def submit_custom_character(
    character_id: str,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> CustomCharacterResponse:
    character, version = _owned(database, character_id, user)
    _validate_publishable(CustomCharacterPayload.model_validate(version.payload))
    if version.status != "draft":
        raise HTTPException(status_code=409, detail="当前版本不能重复提交")
    if not version.self_review:
        raise HTTPException(status_code=422, detail="提交前请先完成玩家自助审核")
    report = SelfReviewReport.model_validate(version.self_review)
    if report.overall_score < 60 or report.must_fix_count > 0:
        raise HTTPException(status_code=422, detail="自助审核仍有必须修复项，暂不能提交")
    version.status = "pending_review"
    version.submitted_at = datetime.now(timezone.utc)
    database.commit()
    database.refresh(version)
    return _character_response(database, character, version, user)


def require_admin(user: User = Depends(current_user)) -> User:
    if not is_admin_username(user.username):
        raise HTTPException(status_code=403, detail="仅管理员可以审核社区角色")
    return user


@router.get("/admin/reviews", response_model=CustomCharacterListResponse)
def list_pending_reviews(
    admin: User = Depends(require_admin),
    database: Session = Depends(get_db),
) -> CustomCharacterListResponse:
    versions = database.scalars(
        select(CustomCharacterVersion)
        .where(CustomCharacterVersion.status == "pending_review")
        .order_by(CustomCharacterVersion.submitted_at)
    ).all()
    items = []
    for version in versions:
        character = database.get(CustomCharacter, version.character_id)
        if character:
            items.append(_character_response(database, character, version, admin))
    return CustomCharacterListResponse(items=items, total=len(items))


@router.post(
    "/admin/reviews/{version_id}", response_model=CustomCharacterResponse
)
def review_custom_character(
    version_id: str,
    payload: ReviewRequest,
    admin: User = Depends(require_admin),
    database: Session = Depends(get_db),
) -> CustomCharacterResponse:
    version = database.get(CustomCharacterVersion, version_id)
    if version is None or version.status != "pending_review":
        raise HTTPException(status_code=404, detail="待审核版本不存在")
    if payload.action == "reject" and not payload.reason:
        raise HTTPException(status_code=422, detail="驳回时必须填写理由")
    character = database.get(CustomCharacter, version.character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="自定义角色不存在")
    version.status = "published" if payload.action == "approve" else "rejected"
    version.review_reason = payload.reason
    version.reviewer_id = admin.id
    version.reviewed_at = datetime.now(timezone.utc)
    if payload.action == "approve":
        previous = _version(database, character, character.published_version_id)
        if previous and previous.id != version.id:
            previous.status = "superseded"
        character.published_version_id = version.id
        character.visibility = "public"
    database.add(
        ModerationAction(
            content_type="character",
            content_id=character.id,
            version_id=version.id,
            action=payload.action,
            reason=payload.reason,
            actor_id=admin.id,
        )
    )
    database.commit()
    database.refresh(version)
    database.refresh(character)
    return _character_response(database, character, version, admin)


@router.post(
    "/admin/reviews/{version_id}/ai-assessment",
    response_model=CharacterAIAssessment,
)
async def assess_custom_character(
    version_id: str,
    admin: User = Depends(require_admin),
    database: Session = Depends(get_db),
    llm: LLMProvider | None = Depends(get_reasoning_llm_provider),
) -> CharacterAIAssessment:
    version = database.get(CustomCharacterVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="自定义角色版本不存在")
    assessment = await CustomCharacterReviewService(llm).assess(
        CustomCharacterPayload.model_validate(version.payload)
    )
    database.add(
        ModerationAction(
            content_type="character",
            content_id=version.character_id,
            version_id=version.id,
            action="ai_assessment",
            actor_id=admin.id,
            details=assessment.model_dump(mode="json"),
        )
    )
    database.commit()
    return assessment


@router.post(
    "/admin/community/characters/{character_id}/moderation",
    response_model=CustomCharacterResponse,
)
def moderate_community_character(
    character_id: str,
    payload: ModerationRequest,
    admin: User = Depends(require_admin),
    database: Session = Depends(get_db),
) -> CustomCharacterResponse:
    character = database.get(CustomCharacter, character_id)
    if character is None or not character.published_version_id:
        raise HTTPException(status_code=404, detail="已发布社区角色不存在")
    version = _version(database, character, character.published_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="已发布社区角色不存在")
    if payload.action == "unpublish":
        if not payload.reason:
            raise HTTPException(status_code=422, detail="下架时必须填写原因")
        if character.visibility != "public":
            raise HTTPException(status_code=409, detail="社区角色已经下架")
        character.visibility = "unpublished"
        version.status = "unpublished"
        version.review_reason = payload.reason
    else:
        if character.visibility != "unpublished":
            raise HTTPException(status_code=409, detail="社区角色当前不是下架状态")
        character.visibility = "public"
        version.status = "published"
        version.review_reason = None
    database.add(
        ModerationAction(
            content_type="character",
            content_id=character.id,
            version_id=version.id,
            action=payload.action,
            reason=payload.reason,
            actor_id=admin.id,
        )
    )
    database.commit()
    database.refresh(character)
    database.refresh(version)
    return _character_response(database, character, version, admin)


@router.get(
    "/admin/community-moderation",
    response_model=ModerationListResponse,
)
def list_community_moderation(
    content_type: str = Query(default="all", alias="type"),
    content_status: str = Query(default="published", alias="status"),
    admin: User = Depends(require_admin),
    database: Session = Depends(get_db),
) -> ModerationListResponse:
    if content_type not in {"all", "character", "activity_guide"}:
        raise HTTPException(status_code=422, detail="不支持的社区内容类型")
    if content_status not in {"published", "unpublished"}:
        raise HTTPException(status_code=422, detail="不支持的社区内容状态")
    items: list[ModerationListItem] = []
    if content_type in {"all", "character"}:
        visibility = "public" if content_status == "published" else "unpublished"
        characters = database.scalars(
            select(CustomCharacter).where(
                CustomCharacter.visibility == visibility,
                CustomCharacter.published_version_id.is_not(None),
            )
        ).all()
        for character in characters:
            version = _version(database, character, character.published_version_id)
            author = database.get(User, character.author_id)
            if version:
                items.append(
                    ModerationListItem(
                        content_type="character",
                        content_id=character.id,
                        title=character.name,
                        status=version.status,
                        author_name=author.display_name if author else "未知作者",
                        reason=version.review_reason,
                        updated_at=character.updated_at,
                    )
                )
    if content_type in {"all", "activity_guide"}:
        guides = database.scalars(
            select(ActivityGuide).where(ActivityGuide.status == content_status)
        ).all()
        for guide in guides:
            author = database.get(User, guide.author_id)
            items.append(
                ModerationListItem(
                    content_type="activity_guide",
                    content_id=guide.id,
                    title=guide.title,
                    status=guide.status,
                    author_name=author.display_name if author else "未知作者",
                    reason=guide.review_reason,
                    updated_at=guide.updated_at,
                )
            )
    items.sort(key=lambda item: item.updated_at, reverse=True)
    return ModerationListResponse(items=items, total=len(items))


@router.get(
    "/community/characters", response_model=CustomCharacterListResponse
)
def list_community_characters(
    user: User | None = Depends(optional_current_user),
    database: Session = Depends(get_db),
) -> CustomCharacterListResponse:
    characters = database.scalars(
        select(CustomCharacter)
        .where(
            CustomCharacter.visibility == "public",
            CustomCharacter.published_version_id.is_not(None),
        )
        .order_by(CustomCharacter.updated_at.desc())
    ).all()
    items = [
        _character_response(
            database,
            character,
            _version(database, character, character.published_version_id),
            user,
        )
        for character in characters
        if character.published_version_id
    ]
    return CustomCharacterListResponse(items=items, total=len(items))


@router.get(
    "/community/characters/{character_id}", response_model=CustomCharacterResponse
)
def get_community_character(
    character_id: str,
    user: User | None = Depends(optional_current_user),
    database: Session = Depends(get_db),
) -> CustomCharacterResponse:
    character = database.get(CustomCharacter, character_id)
    if (
        character is None
        or character.visibility != "public"
        or not character.published_version_id
    ):
        raise HTTPException(status_code=404, detail="社区角色不存在")
    version = _version(database, character, character.published_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="社区角色不存在")
    return _character_response(database, character, version, user)
