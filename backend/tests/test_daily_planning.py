from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.routes.auth import current_user
from app.api.v1.routes.planning import _today, router
from app.db.session import Base, get_db
from app.models.planning import ProgressionPlan, WeeklyPlan
from app.models.user import User
from app.services.planning_service import DailyPlanningService

MONDAY = date(2026, 8, 3)
SUNDAY = date(2026, 8, 9)
DAY_KEYS = [f"2026-08-{day:02d}" for day in range(3, 10)]


def sample_tasks() -> list[dict]:
    return [
        {
            "id": "weekly-1",
            "title": "历战余响 · 3 次",
            "detail": "",
            "dungeon_type": "历战余响",
            "stamina_per_run": 30,
            "run_count": 3,
            "stamina_cost": 90,
            "priority": 100,
            "completed": False,
            "targets": [],
            "source_plan_ids": ["plan-1"],
        },
        {
            "id": "trace-1",
            "title": "拟造花萼（赤） · 10 次",
            "detail": "",
            "dungeon_type": "拟造花萼（赤）",
            "stamina_per_run": 10,
            "run_count": 10,
            "stamina_cost": 100,
            "priority": 300,
            "completed": False,
            "targets": [],
            "source_plan_ids": ["plan-1"],
        },
        {
            "id": "relic-1",
            "title": "侵蚀隧洞 · 12 次",
            "detail": "",
            "dungeon_type": "侵蚀隧洞",
            "stamina_per_run": 40,
            "run_count": 12,
            "stamina_cost": 480,
            "priority": 500,
            "completed": False,
            "targets": [],
            "source_plan_ids": ["plan-1"],
        },
    ]


def fake_plan(tasks: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(
        week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 9),
        stamina_budget=1680,
        allocated_stamina=1680,
        weekly_runs_remaining=3,
        tasks=tasks,
        daily_plan=None,
    )


def test_monday_frontloads_boss_and_consolidates_days() -> None:
    row = fake_plan(sample_tasks())
    DailyPlanningService.ensure_schedule(row)
    schedule = row.daily_plan

    assert schedule["unscheduled_runs"] == 0
    # 周一直接清完 3 次历战余响，再按优先级填花萼与隧洞
    monday = schedule["days"]["2026-08-03"]
    assert [(item["dungeon_type"], item["run_count"]) for item in monday] == [
        ("历战余响", 3),
        ("拟造花萼（赤）", 10),
        ("侵蚀隧洞", 1),
    ]
    total_planned = 0
    for iso in DAY_KEYS:
        items = schedule["days"][iso]
        planned = sum(item["run_count"] * item["stamina_per_run"] for item in items)
        assert planned <= DailyPlanningService.DAILY_STAMINA_CAP, iso
        total_planned += planned
    assert total_planned == 90 + 100 + 480


def test_dense_front_packing_splits_300_into_240_and_60() -> None:
    """体力从头开始按 240 排满：总量 300 → 周一 240、周二 60。"""
    tasks = [
        {
            "id": "asc-1",
            "title": "凝滞虚影 · 8 次",
            "detail": "",
            "dungeon_type": "凝滞虚影",
            "stamina_per_run": 30,
            "run_count": 8,
            "stamina_cost": 240,
            "priority": 200,
            "completed": False,
            "targets": [],
            "source_plan_ids": [],
        },
        {
            "id": "trace-1",
            "title": "拟造花萼（赤） · 6 次",
            "detail": "",
            "dungeon_type": "拟造花萼（赤）",
            "stamina_per_run": 10,
            "run_count": 6,
            "stamina_cost": 60,
            "priority": 300,
            "completed": False,
            "targets": [],
            "source_plan_ids": [],
        },
    ]
    row = fake_plan(tasks)
    DailyPlanningService.ensure_schedule(row)
    days = row.daily_plan["days"]

    assert [(i["dungeon_type"], i["run_count"]) for i in days["2026-08-03"]] == [
        ("凝滞虚影", 8)
    ]
    tuesday = days["2026-08-04"]
    assert [(i["dungeon_type"], i["run_count"]) for i in tuesday] == [
        ("拟造花萼（赤）", 6)
    ]
    assert 10 * 6 == 60
    for iso in DAY_KEYS[2:]:
        assert days[iso] == []


def test_relic_marked_recommended_and_excluded_from_plan_progress() -> None:
    row = fake_plan(sample_tasks())
    DailyPlanningService.ensure_schedule(row)

    monday = DailyPlanningService.day_view(row, today=MONDAY)
    relic = next(item for item in monday["items"] if item["dungeon_type"] == "侵蚀隧洞")
    boss = next(item for item in monday["items"] if item["is_weekly_boss"])
    assert relic["is_required"] is False
    assert boss["is_required"] is True

    # 只完成推荐项：方案完成度不动
    for iso in DAY_KEYS:
        DailyPlanningService.set_daily_completion(row, iso, "relic-1", True)
    stats = DailyPlanningService.weekly_statistics(row)
    assert stats["recommended_completed"] == 12
    assert stats["required_completed"] == 0
    assert stats["plan_complete"] is False


def test_statistics_track_plan_progress_and_completion() -> None:
    row = fake_plan(sample_tasks())
    DailyPlanningService.ensure_schedule(row)
    # v3 密排下花萼 10 次全部落在窗口第一天
    DailyPlanningService.set_daily_completion(row, "2026-08-03", "trace-1", True)

    stats = DailyPlanningService.weekly_statistics(row, {"plan-1": "方案A"})
    assert stats["required_scheduled"] == 13  # boss 3 + 花萼 10
    assert stats["required_completed"] == 10
    assert stats["plan_complete"] is False
    assert stats["plans"][0]["plan_id"] == "plan-1"
    assert stats["plans"][0]["plan_name"] == "方案A"
    assert stats["plans"][0]["scheduled_runs"] == 13
    assert stats["plans"][0]["completed_runs"] == 10

    # 刚需全部完成 → 方案完成（隧洞推荐项不影响判定）
    for iso in DAY_KEYS:
        DailyPlanningService.set_daily_completion(row, iso, "weekly-1", True)
        DailyPlanningService.set_daily_completion(row, iso, "trace-1", True)
    stats = DailyPlanningService.weekly_statistics(row)
    assert stats["required_completed"] == 13
    assert stats["plan_complete"] is True
    # 隧洞推荐项未被勾选：单独计数，不影响方案完成判定
    assert stats["recommended_scheduled"] == 12
    assert stats["recommended_completed"] == 0


def test_small_demand_never_inflates_to_fill_the_cap() -> None:
    """本周养成需求只有 60 点：周一排 60/240，其余天为空。
    240 是每日上限而不是配额，调度器绝不虚构工作量。"""
    tasks = [
        {
            "id": "trace-1",
            "title": "拟造花萼（赤） · 6 次",
            "detail": "",
            "dungeon_type": "拟造花萼（赤）",
            "stamina_per_run": 10,
            "run_count": 6,
            "stamina_cost": 60,
            "priority": 300,
            "completed": False,
            "targets": [],
            "source_plan_ids": [],
        },
    ]
    row = fake_plan(tasks)
    DailyPlanningService.ensure_schedule(row)
    days = row.daily_plan["days"]

    monday = days["2026-08-03"]
    assert [(item["dungeon_type"], item["run_count"]) for item in monday] == [
        ("拟造花萼（赤）", 6)
    ]
    monday_view = DailyPlanningService.day_view(row, today=MONDAY)
    assert monday_view["planned_stamina"] == 60
    assert monday_view["stamina_cap"] == 240
    assert "正常剩余" in monday_view["notice"]
    # 需求已排完：后续 6 天保持为空，绝不硬凑 240
    for iso in DAY_KEYS[1:]:
        assert days[iso] == []
        view = DailyPlanningService.day_view(row, today=date.fromisoformat(iso))
        assert view["planned_stamina"] == 0
        assert "没有排程任务" in view["notice"]


def test_overflow_runs_are_reported_as_unscheduled() -> None:
    tasks = [
        {
            "id": "weekly-1",
            "title": "历战余响 · 3 次",
            "detail": "",
            "dungeon_type": "历战余响",
            "stamina_per_run": 30,
            "run_count": 3,
            "stamina_cost": 90,
            "priority": 100,
            "completed": False,
            "targets": [],
            "source_plan_ids": [],
        },
        {
            "id": "relic-1",
            "title": "侵蚀隧洞 · 45 次",
            "detail": "",
            "dungeon_type": "侵蚀隧洞",
            "stamina_per_run": 40,
            "run_count": 45,
            "stamina_cost": 1800,
            "priority": 500,
            "completed": False,
            "targets": [],
            "source_plan_ids": [],
        },
    ]
    row = fake_plan(tasks)
    DailyPlanningService.ensure_schedule(row)

    # 需求 1890 > 1680：挤出 6 次溢出，且每天不超过 240 点
    assert row.daily_plan["unscheduled_runs"] == 6
    for iso in DAY_KEYS:
        items = row.daily_plan["days"][iso]
        planned = sum(item["run_count"] * item["stamina_per_run"] for item in items)
        assert planned <= DailyPlanningService.DAILY_STAMINA_CAP, iso


def test_daily_completion_deducts_day_and_syncs_weekly() -> None:
    row = fake_plan(sample_tasks())
    DailyPlanningService.ensure_schedule(row)

    changed = DailyPlanningService.set_daily_completion(
        row, "2026-08-03", "weekly-1", True
    )
    assert changed is True

    monday = DailyPlanningService.day_view(row, today=MONDAY)
    boss = next(item for item in monday["items"] if item["is_weekly_boss"])
    assert boss["completed"] is True
    assert boss["runs_planned"] == 3
    assert monday["planned_stamina"] == 230
    assert monday["completed_stamina"] == 90

    by_id = {task["id"]: task for task in row.tasks}
    assert by_id["weekly-1"]["completed_runs"] == 3
    assert by_id["weekly-1"]["completed"] is True
    assert by_id["trace-1"]["completed_runs"] == 0
    # 隧洞是推荐项：is_required 必须为 False
    assert by_id["relic-1"]["is_required"] is False
    assert by_id["weekly-1"]["is_required"] is True


def test_rebuild_preserves_completion_by_dungeon_and_day() -> None:
    row = fake_plan(sample_tasks())
    DailyPlanningService.ensure_schedule(row)
    DailyPlanningService.set_daily_completion(row, "2026-08-03", "weekly-1", True)

    # 模拟重新生成：任务全部换新 id，但副本与次数不变
    regenerated = [{**task, "id": str(uuid4())} for task in sample_tasks()]
    row.tasks = regenerated
    DailyPlanningService.ensure_schedule(row)

    monday = DailyPlanningService.day_view(row, today=MONDAY)
    boss = next(item for item in monday["items"] if item["is_weekly_boss"])
    assert boss["completed"] is True
    assert boss["weekly_task_id"] != "weekly-1"

    boss_task = next(task for task in row.tasks if task["dungeon_type"] == "历战余响")
    assert boss_task["completed_runs"] == 3
    assert boss_task["completed"] is True


def test_weekly_toggle_off_clears_all_day_completions() -> None:
    row = fake_plan(sample_tasks())
    DailyPlanningService.ensure_schedule(row)
    DailyPlanningService.set_daily_completion(row, "2026-08-03", "weekly-1", True)
    DailyPlanningService.set_weekly_completion(row, "weekly-1", False)

    monday = DailyPlanningService.day_view(row, today=MONDAY)
    boss = next(item for item in monday["items"] if item["is_weekly_boss"])
    assert boss["completed"] is False
    assert monday["completed_stamina"] == 0
    by_id = {task["id"]: task for task in row.tasks}
    assert by_id["weekly-1"]["completed"] is False
    assert by_id["weekly-1"]["completed_runs"] == 0


def test_unchecking_never_scheduled_task_reinserts_it_into_schedule() -> None:
    tasks = sample_tasks()
    tasks[0]["completed"] = True  # 历战余响已被标记完成，不应出现在排程里
    row = fake_plan(tasks)
    DailyPlanningService.ensure_schedule(row)
    assert all(
        item["dungeon_type"] != "历战余响"
        for items in row.daily_plan["days"].values()
        for item in items
    )

    # 用户取消完成 → 任务回归排程
    DailyPlanningService.set_weekly_completion(row, "weekly-1", False)
    monday = DailyPlanningService.day_view(row, today=MONDAY)
    boss = next(item for item in monday["items"] if item["is_weekly_boss"])
    assert boss["runs_planned"] == 3
    assert boss["completed"] is False
    by_id = {task["id"]: task for task in row.tasks}
    assert by_id["weekly-1"]["completed"] is False


def test_progression_plan_progress_visible_on_plans_page() -> None:
    """玩家在自己设定的养成方案上直接看到实施进度：
    进度跟随每日勾选实时更新，刚需全部完成时方案标记完成。"""
    client = daily_client(
        with_plan=True, with_progression=True, progression_plan_id="plan-1"
    )
    window_start = _today()

    plans = client.get("/profile/progression-plans").json()
    progress = plans["items"][0]["progress"]
    assert plans["items"][0]["id"] == "plan-1"
    assert progress["in_current_window"] is True
    assert progress["scheduled_runs"] == 25  # boss 3 + 花萼 10 + 隧洞 12
    assert progress["required_scheduled"] == 13
    assert progress["completed_runs"] == 0
    assert progress["complete"] is False

    # 完成周一的 3 次周本 → 方案进度实时前进
    monday = client.get(
        "/planning/daily", params={"date": window_start.isoformat()}
    ).json()
    boss_id = next(
        item["weekly_task_id"] for item in monday["items"] if item["is_weekly_boss"]
    )
    client.patch(
        f"/planning/daily/{window_start.isoformat()}/{boss_id}",
        json={"completed": True},
    )

    plans = client.get("/profile/progression-plans").json()
    progress = plans["items"][0]["progress"]
    assert progress["completed_runs"] == 3
    assert progress["required_completed"] == 3
    assert progress["complete"] is False  # 3 < 13，还在进行中


def test_stale_window_reanchors_remaining_work_to_today() -> None:
    """跨天之后：已完成的历史保留，未完成的剩余次数从今天重新前排。"""
    row = fake_plan(sample_tasks())
    DailyPlanningService.ensure_schedule(row)  # 周一锚点：全部前排到周一
    DailyPlanningService.set_daily_completion(row, "2026-08-03", "weekly-1", True)

    # 两天过去了（今天 = 周三 08-05）
    DailyPlanningService.ensure_schedule(row, today=date(2026, 8, 5))
    assert row.week_start == date(2026, 8, 5)
    assert row.week_end == date(2026, 8, 11)

    # 周一历史原样保留（进度不丢）
    monday_history = DailyPlanningService.day_view(row, today=MONDAY)
    boss_past = next(
        item for item in monday_history["items"] if item["is_weekly_boss"]
    )
    assert boss_past["completed"] is True
    assert boss_past["runs_planned"] == 3
    assert boss_past["run_count_week"] == 3

    # 剩余工作（花萼 10 + 隧洞 12）从今天重新按优先级前排
    wednesday = row.daily_plan["days"]["2026-08-05"]
    assert [(i["dungeon_type"], i["run_count"]) for i in wednesday] == [
        ("拟造花萼（赤）", 10),
        ("侵蚀隧洞", 3),
    ]
    thursday = row.daily_plan["days"]["2026-08-06"]
    assert [(i["dungeon_type"], i["run_count"]) for i in thursday] == [
        ("侵蚀隧洞", 6)
    ]
    friday = row.daily_plan["days"]["2026-08-07"]
    assert [(i["dungeon_type"], i["run_count"]) for i in friday] == [
        ("侵蚀隧洞", 3)
    ]

    # 统计不丢：boss 的 3 次完成仍计入
    stats = DailyPlanningService.weekly_statistics(row)
    by_task = {task["id"]: task for task in row.tasks}
    assert by_task["weekly-1"]["completed"] is True
    assert by_task["weekly-1"]["completed_runs"] == 3
    assert stats["required_completed"] == 3


def test_stale_plan_rolls_forward_on_first_request() -> None:
    client = daily_client(with_plan=True, plan_start_offset=-2)
    response = client.get("/planning/daily")

    assert response.status_code == 200
    payload = response.json()
    assert payload["date"] == _today().isoformat()
    assert payload["week_start"] == _today().isoformat()
    assert payload["planned_stamina"] > 0  # 剩余工作自动重排到今天


def test_missing_plan_returns_guidance() -> None:
    view = DailyPlanningService.empty_view(MONDAY)
    assert view["items"] == []
    assert "尚未生成" in view["notice"]
    assert view["stamina_cap"] == 240
    assert view["week_start"] == MONDAY
    assert view["week_end"] == SUNDAY


def daily_client(
    with_plan: bool,
    plan_start_offset: int = 0,
    with_progression: bool = False,
    progression_plan_id: str | None = None,
) -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as database:
        user = User(
            username="daily",
            email="daily@example.com",
            display_name="每日测试",
            password_hash="test-only",
        )
        database.add(user)
        database.flush()
        if with_progression:
            database.add(
                ProgressionPlan(
                    id=progression_plan_id or str(uuid4()),
                    user_id=user.id,
                    name="方案A",
                    status="active",
                    priority=1,
                    request_payload={"characters": []},
                    material_snapshot={
                        "materials": [
                            {
                                "key": "weekly",
                                "quantity": 3,
                                "item": {"id": "weekly", "name": "历战余响材料"},
                            },
                            {
                                "key": "ascension",
                                "quantity": 4,
                                "item": {"id": "asc", "name": "凝滞虚影材料"},
                            },
                        ]
                    },
                    recommendation_snapshot={},
                )
            )
        if with_plan:
            week_start = _today() + timedelta(days=plan_start_offset)
            database.add(
                WeeklyPlan(
                    user_id=user.id,
                    week_start=week_start,
                    week_end=week_start + timedelta(days=6),
                    stamina_budget=1680,
                    allocated_stamina=1680,
                    weekly_runs_remaining=3,
                    tasks=sample_tasks(),
                    notice="test-only",
                    evidence_version="test",
                )
            )
        database.commit()
        user_id = user.id

    app = FastAPI()
    app.include_router(router)

    def override_database():
        with testing_session() as database:
            yield database

    def override_user() -> User:
        with testing_session() as database:
            user = database.get(User, user_id)
            assert user is not None
            database.expunge(user)
            return user

    app.dependency_overrides[get_db] = override_database
    app.dependency_overrides[current_user] = override_user
    return TestClient(app)


def test_daily_endpoint_builds_and_persists_schedule() -> None:
    client = daily_client(with_plan=True)
    response = client.get("/planning/daily")

    assert response.status_code == 200
    payload = response.json()
    assert payload["stamina_cap"] == 240
    assert payload["planned_stamina"] <= payload["stamina_cap"]
    assert all(item["runs_planned"] >= 0 for item in payload["items"])
    assert all(item["is_required"] is not None for item in payload["items"])


def test_completion_persists_across_requests() -> None:
    """回归测试：JSON 列原地修改不落库会导致
    「点击别的完成时取消之前完成过的日程」。每个请求都使用全新
    Session，任何一次点击都必须真实写入数据库。"""
    client = daily_client(with_plan=True)
    window_start = _today()
    monday_iso = window_start.isoformat()
    wednesday_iso = (window_start + timedelta(days=2)).isoformat()

    monday = client.get("/planning/daily", params={"date": monday_iso}).json()
    boss_id = next(
        item["weekly_task_id"] for item in monday["items"] if item["is_weekly_boss"]
    )
    assert (
        client.patch(
            f"/planning/daily/{monday_iso}/{boss_id}",
            json={"completed": True},
        ).status_code
        == 200
    )

    wednesday = client.get(
        "/planning/daily", params={"date": wednesday_iso}
    ).json()
    relic_id = next(
        item["weekly_task_id"]
        for item in wednesday["items"]
        if item["dungeon_type"] == "侵蚀隧洞"
    )
    assert (
        client.patch(
            f"/planning/daily/{wednesday_iso}/{relic_id}",
            json={"completed": True},
        ).status_code
        == 200
    )

    # 关键断言：第二次点击之后，第一次的完成状态必须还在
    monday_after = client.get(
        "/planning/daily", params={"date": monday_iso}
    ).json()
    boss_after = next(
        item for item in monday_after["items"] if item["is_weekly_boss"]
    )
    assert boss_after["completed"] is True

    weekly_payload = client.get("/profile/weekly-plans/current").json()
    by_id = {task["id"]: task for task in weekly_payload["tasks"]}
    assert by_id[boss_id]["completed"] is True
    assert by_id[boss_id]["completed_runs"] == 3
    assert by_id[relic_id]["completed_runs"] == 5


def test_generate_rolls_window_to_start_from_today() -> None:
    client = daily_client(with_plan=True, plan_start_offset=-3, with_progression=True)
    today = _today()

    generate = client.post(
        "/planning/weekly/generate",
        json={"stamina_budget": 1680, "weekly_runs_remaining": 3},
    )
    assert generate.status_code == 200
    payload = generate.json()
    # 滚动窗口：重新生成后计划以今天为起点，覆盖未来 7 天
    assert payload["week_start"] == today.isoformat()
    assert payload["week_end"] == (today + timedelta(days=6)).isoformat()
    assert payload["statistics"]["required_scheduled"] > 0
    assert payload["statistics"]["plans"][0]["plan_name"] == "方案A"

    # 窗口内的日期可以查看，窗口外拒绝
    assert (
        client.get("/planning/daily", params={"date": today.isoformat()}).status_code
        == 200
    )
    far = today + timedelta(days=14)
    assert (
        client.get("/planning/daily", params={"date": far.isoformat()}).status_code
        == 422
    )


def test_daily_endpoint_rejects_unknown_task() -> None:
    client = daily_client(with_plan=True)
    window_start = _today()

    missing = client.patch(
        f"/planning/daily/{window_start.isoformat()}/no-such-task",
        json={"completed": True},
    )
    assert missing.status_code == 404
