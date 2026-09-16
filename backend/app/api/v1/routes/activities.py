from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.routes.auth import current_user, is_admin_username
from app.core.config import settings
from app.db.session import get_db
from app.models.activity import ActivityGuide
from app.models.moderation import ModerationAction
from app.models.user import User
from app.schemas.activity import (
    ActivityDetail,
    ActivityGuideCreate,
    ActivityGuideListResponse,
    ActivityGuideResponse,
    ActivityGuideReview,
    ActivityListResponse,
)
from app.schemas.moderation import ModerationRequest
from app.services.activity_service import ActivityService

router = APIRouter()
service = ActivityService(settings.docs_root)
assets_root = (
    settings.docs_root / "content_1257_版本活动" / "assets"
).resolve()


def require_activity_admin(
    user: User = Depends(current_user),
) -> User:
    if not is_admin_username(user.username):
        raise HTTPException(status_code=403, detail="仅管理员可以审核活动攻略")
    return user


def _guide_response(database: Session, guide: ActivityGuide) -> ActivityGuideResponse:
    author = database.get(User, guide.author_id)
    return ActivityGuideResponse(
        id=guide.id,
        activity_id=guide.activity_id,
        activity_title=service.title(guide.activity_id),
        author_id=guide.author_id,
        author_name=author.display_name if author else "未知作者",
        title=guide.title,
        content=guide.content,
        player_stage=guide.player_stage,
        status=guide.status,
        review_reason=guide.review_reason,
        submitted_at=guide.submitted_at,
        reviewed_at=guide.reviewed_at,
    )


@router.get("/activities", response_model=ActivityListResponse)
def list_activities(
    version: str | None = Query(default=None),
) -> ActivityListResponse:
    items = service.list(version=version)
    return ActivityListResponse(items=items, total=len(items))


@router.get("/activities/assets/{filename}")
def activity_asset(filename: str) -> FileResponse:
    target = (assets_root / Path(filename).name).resolve()
    if target.parent != assets_root or not target.is_file():
        raise HTTPException(status_code=404, detail="活动图片不存在")
    return FileResponse(target)


@router.get("/activities/{activity_id}", response_model=ActivityDetail)
def get_activity(activity_id: str) -> ActivityDetail:
    item = service.get(activity_id)
    if item is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    return ActivityDetail.model_validate(item)


@router.get(
    "/activities/{activity_id}/guides",
    response_model=ActivityGuideListResponse,
)
def list_published_guides(
    activity_id: str,
    database: Session = Depends(get_db),
) -> ActivityGuideListResponse:
    if service.get(activity_id) is None:
        raise HTTPException(status_code=404, detail="活动不存在")
    guides = database.scalars(
        select(ActivityGuide)
        .where(
            ActivityGuide.activity_id == activity_id,
            ActivityGuide.status == "published",
        )
        .order_by(ActivityGuide.reviewed_at.desc())
    ).all()
    items = [_guide_response(database, guide) for guide in guides]
    return ActivityGuideListResponse(items=items, total=len(items))


@router.post(
    "/activities/{activity_id}/guides",
    response_model=ActivityGuideResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_guide(
    activity_id: str,
    payload: ActivityGuideCreate,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> ActivityGuideResponse:
    if not service.accepts_guides(activity_id):
        raise HTTPException(status_code=422, detail="仅 4.4 活动开放攻略投稿")
    guide = ActivityGuide(
        activity_id=activity_id,
        author_id=user.id,
        title=payload.title,
        content=payload.content,
        player_stage=payload.player_stage,
    )
    database.add(guide)
    database.commit()
    database.refresh(guide)
    return _guide_response(database, guide)


@router.get(
    "/admin/activity-guide-reviews",
    response_model=ActivityGuideListResponse,
)
def list_pending_guides(
    _: User = Depends(require_activity_admin),
    database: Session = Depends(get_db),
) -> ActivityGuideListResponse:
    guides = database.scalars(
        select(ActivityGuide)
        .where(ActivityGuide.status == "pending_review")
        .order_by(ActivityGuide.submitted_at)
    ).all()
    items = [_guide_response(database, guide) for guide in guides]
    return ActivityGuideListResponse(items=items, total=len(items))


@router.post(
    "/admin/activity-guide-reviews/{guide_id}",
    response_model=ActivityGuideResponse,
)
def review_guide(
    guide_id: str,
    payload: ActivityGuideReview,
    admin: User = Depends(require_activity_admin),
    database: Session = Depends(get_db),
) -> ActivityGuideResponse:
    guide = database.get(ActivityGuide, guide_id)
    if guide is None or guide.status != "pending_review":
        raise HTTPException(status_code=404, detail="待审核攻略不存在")
    if payload.action == "reject" and not payload.reason.strip():
        raise HTTPException(status_code=422, detail="驳回时必须填写理由")
    guide.status = "published" if payload.action == "approve" else "rejected"
    guide.review_reason = payload.reason.strip() or None
    guide.reviewer_id = admin.id
    guide.reviewed_at = datetime.now(timezone.utc)
    database.add(
        ModerationAction(
            content_type="activity_guide",
            content_id=guide.id,
            action=payload.action,
            reason=payload.reason.strip() or None,
            actor_id=admin.id,
        )
    )
    database.commit()
    database.refresh(guide)
    return _guide_response(database, guide)


@router.post(
    "/admin/activity-guides/{guide_id}/moderation",
    response_model=ActivityGuideResponse,
)
def moderate_guide(
    guide_id: str,
    payload: ModerationRequest,
    admin: User = Depends(require_activity_admin),
    database: Session = Depends(get_db),
) -> ActivityGuideResponse:
    guide = database.get(ActivityGuide, guide_id)
    if guide is None:
        raise HTTPException(status_code=404, detail="社区攻略不存在")
    if payload.action == "unpublish":
        if not payload.reason:
            raise HTTPException(status_code=422, detail="下架时必须填写原因")
        if guide.status != "published":
            raise HTTPException(status_code=409, detail="社区攻略当前不可下架")
        guide.status = "unpublished"
        guide.review_reason = payload.reason
    else:
        if guide.status != "unpublished":
            raise HTTPException(status_code=409, detail="社区攻略当前不是下架状态")
        guide.status = "published"
        guide.review_reason = None
    guide.reviewer_id = admin.id
    guide.reviewed_at = datetime.now(timezone.utc)
    database.add(
        ModerationAction(
            content_type="activity_guide",
            content_id=guide.id,
            action=payload.action,
            reason=payload.reason,
            actor_id=admin.id,
        )
    )
    database.commit()
    database.refresh(guide)
    return _guide_response(database, guide)
