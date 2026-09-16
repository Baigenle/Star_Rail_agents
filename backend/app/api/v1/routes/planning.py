from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.routes.auth import current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.planning import ProgressionPlan, WeeklyPlan
from app.models.user import User, UserCharacter
from app.schemas.planning import (
    DailyPlanResponse,
    MultiProgressionRequest,
    ProgressionPlanProgress,
    MultiProgressionResponse,
    ProgressionPlanCreate,
    ProgressionPlanListResponse,
    ProgressionPlanResponse,
    ProgressionPlanUpdate,
    WeeklyPlanGenerateRequest,
    WeeklyPlanResponse,
    WeeklyTask,
    WeeklyTaskUpdate,
)
from app.services.planning_service import (
    DailyPlanningService,
    PlanningService,
    WeeklyPlanningService,
)
from app.services.progression_service import ProgressionValidationError

router = APIRouter()
service = PlanningService(settings.docs_root)
APP_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _today() -> date:
    return datetime.now(APP_TIMEZONE).date()


def _current_plan(database: Session, user: User) -> WeeklyPlan | None:
    """滚动窗口：计划以生成当天为起点，覆盖未来 7 天；
    窗口跨越到的下个自然周，就是"下周"的时间。"""
    today = _today()
    return database.scalar(
        select(WeeklyPlan)
        .where(
            WeeklyPlan.user_id == user.id,
            WeeklyPlan.week_start <= today,
            WeeklyPlan.week_end >= today,
        )
        .order_by(WeeklyPlan.week_start.desc())
    )


def _ensure_owned(
    database: Session, user_id: str, character_ids: set[str]
) -> None:
    owned = set(
        database.scalars(
            select(UserCharacter.character_id).where(
                UserCharacter.user_id == user_id
            )
        ).all()
    )
    missing = sorted(character_ids - owned)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"养成方案只能使用已拥有角色：{', '.join(missing)}",
        )


def _calculate(payload: MultiProgressionRequest) -> MultiProgressionResponse:
    try:
        return service.calculate(payload.characters)
    except ProgressionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _plan_response(
    plan: ProgressionPlan,
    progress: ProgressionPlanProgress | None = None,
) -> ProgressionPlanResponse:
    return ProgressionPlanResponse(
        id=plan.id,
        name=plan.name,
        status=plan.status,
        priority=plan.priority,
        request_payload=plan.request_payload,
        material_snapshot=plan.material_snapshot,
        recommendation_snapshot=plan.recommendation_snapshot,
        progress=progress or ProgressionPlanProgress(),
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def _progress_by_plan(
    database: Session, user: User
) -> dict[str, ProgressionPlanProgress]:
    """按养成方案聚合当前滚动窗口排程的完成次数，
    让玩家在自己设定的方案上直接看到实施进度。"""
    weekly = _current_plan(database, user)
    result: dict[str, ProgressionPlanProgress] = {}
    if weekly is None:
        return result
    DailyPlanningService.ensure_schedule(weekly, today=_today())
    for task in weekly.tasks:
        runs = int(task.get("run_count") or 0)
        done_runs = int(task.get("completed_runs") or 0)
        is_required = task.get("dungeon_type") != DailyPlanningService.RECOMMENDED_TYPE
        for plan_id in task.get("source_plan_ids") or []:
            entry = result.setdefault(
                str(plan_id),
                ProgressionPlanProgress(in_current_window=True),
            )
            entry.in_current_window = True
            entry.scheduled_runs += runs
            entry.completed_runs += done_runs
            if is_required:
                entry.required_scheduled += runs
                entry.required_completed += done_runs
                entry.complete = (
                    entry.required_scheduled > 0
                    and entry.required_completed >= entry.required_scheduled
                )
    return result


def _weekly_response(database: Session, plan: WeeklyPlan) -> WeeklyPlanResponse:
    plan_ids = {
        pid for task in plan.tasks for pid in (task.get("source_plan_ids") or [])
    }
    names: dict[str, str] = {}
    if plan_ids:
        rows = database.scalars(
            select(ProgressionPlan).where(ProgressionPlan.id.in_(plan_ids))
        ).all()
        names = {row.id: row.name for row in rows}
    statistics = DailyPlanningService.weekly_statistics(plan, names)
    # is_required 兜底：旧数据可能缺这个字段，按副本类型现算
    tasks = []
    for task in plan.tasks:
        data = dict(task)
        data["is_required"] = (
            data.get("is_required", True)
            if "is_required" in data
            else data.get("dungeon_type") != DailyPlanningService.RECOMMENDED_TYPE
        )
        tasks.append(WeeklyTask.model_validate(data))
    return WeeklyPlanResponse(
        id=plan.id,
        week_start=plan.week_start,
        week_end=plan.week_end,
        stamina_budget=plan.stamina_budget,
        allocated_stamina=plan.allocated_stamina,
        weekly_runs_remaining=plan.weekly_runs_remaining,
        tasks=tasks,
        statistics=statistics,
        notice=plan.notice,
        evidence_version=plan.evidence_version,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.post(
    "/planning/progression/calculate",
    response_model=MultiProgressionResponse,
    summary="合并计算多名已拥有角色的等级、技能和材料需求",
)
def calculate_progression_plan(
    payload: MultiProgressionRequest,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> MultiProgressionResponse:
    _ensure_owned(
        database, user.id, {item.character_id for item in payload.characters}
    )
    return _calculate(payload)


@router.get(
    "/profile/progression-plans",
    response_model=ProgressionPlanListResponse,
)
def list_progression_plans(
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> ProgressionPlanListResponse:
    items = database.scalars(
        select(ProgressionPlan)
        .where(ProgressionPlan.user_id == user.id)
        .order_by(ProgressionPlan.priority, ProgressionPlan.updated_at.desc())
    ).all()
    progress_map = _progress_by_plan(database, user)
    return ProgressionPlanListResponse(
        items=[
            _plan_response(item, progress_map.get(item.id))
            for item in items
        ],
        total=len(items),
    )


@router.post(
    "/profile/progression-plans",
    response_model=ProgressionPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_progression_plan(
    payload: ProgressionPlanCreate,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> ProgressionPlanResponse:
    _ensure_owned(
        database, user.id, {item.character_id for item in payload.characters}
    )
    calculation = _calculate(
        MultiProgressionRequest(characters=payload.characters)
    )
    plan = ProgressionPlan(
        user_id=user.id,
        name=payload.name,
        priority=payload.priority,
        status="active",
        request_payload={
            "characters": [
                item.model_dump(mode="json") for item in payload.characters
            ]
        },
        material_snapshot=calculation.model_dump(mode="json"),
        recommendation_snapshot={
            key: value.model_dump(mode="json")
            for key, value in calculation.recommendations.items()
        },
    )
    database.add(plan)
    database.commit()
    database.refresh(plan)
    progress_map = _progress_by_plan(database, user)
    return _plan_response(plan, progress_map.get(plan.id))


@router.patch(
    "/profile/progression-plans/{plan_id}",
    response_model=ProgressionPlanResponse,
)
def update_progression_plan(
    plan_id: str,
    payload: ProgressionPlanUpdate,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> ProgressionPlanResponse:
    plan = database.scalar(
        select(ProgressionPlan).where(
            ProgressionPlan.id == plan_id,
            ProgressionPlan.user_id == user.id,
        )
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="养成方案不存在")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(plan, key, value)
    database.commit()
    database.refresh(plan)
    progress_map = _progress_by_plan(database, user)
    return _plan_response(plan, progress_map.get(plan.id))


@router.delete(
    "/profile/progression-plans/{plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_progression_plan(
    plan_id: str,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> Response:
    plan = database.scalar(
        select(ProgressionPlan).where(
            ProgressionPlan.id == plan_id,
            ProgressionPlan.user_id == user.id,
        )
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="养成方案不存在")
    database.delete(plan)
    database.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/planning/weekly/generate",
    response_model=WeeklyPlanResponse,
    summary="依据启用中的养成方案生成本周副本次数与体力分配",
)
def generate_weekly_plan(
    payload: WeeklyPlanGenerateRequest,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> WeeklyPlanResponse:
    plans = database.scalars(
        select(ProgressionPlan)
        .where(
            ProgressionPlan.user_id == user.id,
            ProgressionPlan.status == "active",
        )
        .order_by(ProgressionPlan.priority)
    ).all()
    if not plans:
        raise HTTPException(status_code=422, detail="请先保存并启用至少一份养成方案")

    today = _today()
    weekly_plan = _current_plan(database, user)
    previous_tasks = weekly_plan.tasks if weekly_plan else []
    tasks = WeeklyPlanningService.build_tasks(
        plans,
        stamina_budget=payload.stamina_budget,
        weekly_runs_remaining=payload.weekly_runs_remaining,
        previous_tasks=previous_tasks,
    )
    allocated = sum(task["stamina_cost"] for task in tasks)
    if weekly_plan is None:
        weekly_plan = WeeklyPlan(
            user_id=user.id,
            week_start=today,
            week_end=today + timedelta(days=6),
        )
        database.add(weekly_plan)
    # 滚动窗口：重新生成时以当天为起点重排未来 7 天
    weekly_plan.week_start = today
    weekly_plan.week_end = today + timedelta(days=6)
    weekly_plan.stamina_budget = payload.stamina_budget
    weekly_plan.allocated_stamina = allocated
    weekly_plan.weekly_runs_remaining = payload.weekly_runs_remaining
    weekly_plan.tasks = tasks
    weekly_plan.notice = (
        "历战余响按养成缺口优先安排；其余体力按启用方案优先级轮转分配。"
        "当前缺少各均衡等级的确定掉落数量，因此副本次数表示本周预算，不承诺一次完成全部缺口。"
    )
    weekly_plan.evidence_version = (
        "progression_rules_v1+saved_plan_snapshot+dungeon_stamina_costs_v1"
    )
    DailyPlanningService.ensure_schedule(weekly_plan, today=_today())
    database.commit()
    database.refresh(weekly_plan)
    return _weekly_response(database, weekly_plan)


@router.get(
    "/profile/weekly-plans/current",
    response_model=WeeklyPlanResponse,
)
def get_current_weekly_plan(
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> WeeklyPlanResponse:
    plan = _current_plan(database, user)
    if plan is None:
        raise HTTPException(status_code=404, detail="本周计划尚未生成")
    return _weekly_response(database, plan)


@router.patch(
    "/profile/weekly-plans/{plan_id}/tasks/{task_id}",
    response_model=WeeklyPlanResponse,
)
def update_weekly_task(
    plan_id: str,
    task_id: str,
    payload: WeeklyTaskUpdate,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> WeeklyPlanResponse:
    plan = database.scalar(
        select(WeeklyPlan).where(
            WeeklyPlan.id == plan_id,
            WeeklyPlan.user_id == user.id,
        )
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="每周计划不存在")
    tasks = [dict(task) for task in plan.tasks]
    target = next((task for task in tasks if task.get("id") == task_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="每周任务不存在")
    target["completed"] = payload.completed
    plan.tasks = tasks
    DailyPlanningService.ensure_schedule(plan, today=_today())
    DailyPlanningService.set_weekly_completion(plan, task_id, payload.completed)
    database.commit()
    database.refresh(plan)
    return _weekly_response(database, plan)


@router.get(
    "/planning/daily",
    response_model=DailyPlanResponse,
    summary="查看滚动窗口内指定日期的每日体力安排（240 点上限，按优先级排程，周本置顶）",
)
def get_daily_plan(
    day: date | None = Query(default=None, alias="date"),
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> DailyPlanResponse:
    requested = day if day is not None else _today()
    plan = _current_plan(database, user)
    if plan is None:
        return DailyPlanningService.empty_view(requested)
    # 先按"今天"重锚（窗口自动滚动到今天），再校验请求日期
    DailyPlanningService.ensure_schedule(plan, today=_today())
    database.commit()
    if not plan.week_start <= requested <= plan.week_end:
        raise HTTPException(
            status_code=422,
            detail=(
                f"该日期不在当前计划窗口内（{plan.week_start} ~ {plan.week_end}），"
                "重新生成计划即可从今天起排未来 7 天。"
            ),
        )
    return DailyPlanningService.day_view(plan, today=requested)


@router.patch(
    "/planning/daily/{day}/{weekly_task_id}",
    response_model=DailyPlanResponse,
    summary="勾选或取消某个日任务的完成状态，从当日 240 点账本核销并同步周计划进度",
)
def update_daily_task(
    day: date,
    weekly_task_id: str,
    payload: WeeklyTaskUpdate,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> DailyPlanResponse:
    plan = _current_plan(database, user)
    if plan is None:
        raise HTTPException(status_code=404, detail="本周计划尚未生成")
    DailyPlanningService.ensure_schedule(plan, today=_today())
    if not plan.week_start <= day <= plan.week_end:
        raise HTTPException(
            status_code=422,
            detail=f"该日期不在当前计划窗口内（{plan.week_start} ~ {plan.week_end}）",
        )
    if not DailyPlanningService.set_daily_completion(
        plan, day.isoformat(), weekly_task_id, payload.completed
    ):
        raise HTTPException(status_code=404, detail="当日没有这个任务的排程")
    database.commit()
    return DailyPlanningService.day_view(plan, today=day)
