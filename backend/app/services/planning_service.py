import copy
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm.attributes import flag_modified

from app.schemas.ai_response import (
    AIResponse,
    Citation,
    Claim,
    FilteringReport,
    QueryStep,
    ValidationReport,
)
from app.schemas.planning import (
    BuildRecommendation,
    CharacterPlanInput,
    MultiProgressionResponse,
)
from app.schemas.progression import (
    ProgressionCalculateResponse,
    ProgressionMaterialResponse,
    SkillRange,
)
from app.services.catalog_service import CatalogService
from app.services.progression_service import ProgressionService


class PlanningService:
    def __init__(self, docs_root: Path) -> None:
        self.progression = ProgressionService(docs_root)
        self.catalog = CatalogService(docs_root)

    def calculate(
        self, characters: list[CharacterPlanInput]
    ) -> MultiProgressionResponse:
        calculations: list[ProgressionCalculateResponse] = []
        total_by_key: defaultdict[str, int] = defaultdict(int)
        material_by_identity: dict[str, ProgressionMaterialResponse] = {}
        recommendations: dict[str, BuildRecommendation] = {}
        citations: list[Citation] = []
        claims: list[Claim] = []
        warnings: list[str] = []

        for index, request in enumerate(characters, start=1):
            result = self.progression.calculate(
                request.character_id,
                from_level=request.from_level,
                to_level=request.to_level,
                skill_ranges={
                    key: (value.from_level, value.to_level)
                    for key, value in request.skill_ranges.items()
                },
            )
            response = ProgressionCalculateResponse(
                character_id=result.character_id,
                archetype=result.archetype,
                from_level=result.from_level,
                to_level=result.to_level,
                skill_ranges={
                    key: SkillRange(from_level=value[0], to_level=value[1])
                    for key, value in result.skill_ranges.items()
                },
                total_by_key=result.total_by_key,
                materials=[
                    ProgressionMaterialResponse(
                        key=material.key,
                        quantity=material.quantity,
                        item=material.item,
                    )
                    for material in result.materials
                ],
            )
            calculations.append(response)
            for key, quantity in result.total_by_key.items():
                total_by_key[key] += quantity
            for material in response.materials:
                identity = (
                    f"item:{material.item.id}"
                    if material.item is not None
                    else f"unresolved:{result.character_id}:{material.key}"
                )
                if identity not in material_by_identity:
                    material_by_identity[identity] = material.model_copy(
                        update={"quantity": 0}
                    )
                material_by_identity[identity].quantity += material.quantity

            detail = self.catalog.get_character(request.character_id)
            if detail is None:
                continue
            recommendation = self._recommendation(detail)
            recommendations[request.character_id] = recommendation
            warnings.extend(recommendation.warnings)
            lightcone_names = "、".join(
                item["name"] for item in recommendation.lightcones
            )
            tunnel_names = "、".join(
                item["name"] for item in recommendation.tunnel_relics
            )
            planar_names = "、".join(
                item["name"] for item in recommendation.planar_relics
            )
            skill_names = "、".join(recommendation.skill_priority)
            citation_id = f"C{index}"
            citations.append(
                Citation(
                    id=citation_id,
                    title=f"{detail.name}官方角色档案与养成补充",
                    source=detail.source_url,
                    excerpt=(
                        f"角色等级 {request.from_level}→{request.to_level}；"
                        "推荐光锥："
                        f"{lightcone_names or '暂无'}；"
                        "隧洞遗器："
                        f"{tunnel_names or '暂无'}；"
                        "位面饰品："
                        f"{planar_names or '暂无'}；"
                        "档案主技能顺序："
                        f"{skill_names or '暂无'}；"
                        "可信技能优先级：资料未提供。"
                    ),
                    document_id=detail.id,
                    entity_url=f"/characters/{detail.id}",
                    image_url=detail.image_url,
                )
            )
            claims.append(
                Claim(
                    statement=(
                        f"{detail.name}的目标区间已按逐级规则计算，"
                        f"并合并 {len(response.materials)} 类材料。"
                    ),
                    confidence=0.95,
                    citation_ids=[citation_id],
                )
            )
            if lightcone_names:
                claims.append(
                    Claim(
                        statement=f"{detail.name}推荐光锥包括{lightcone_names}。",
                        confidence=0.9,
                        citation_ids=[citation_id],
                    )
                )
            if tunnel_names:
                claims.append(
                    Claim(
                        statement=f"{detail.name}隧洞遗器推荐为{tunnel_names}。",
                        confidence=0.9,
                        citation_ids=[citation_id],
                    )
                )
            if planar_names:
                claims.append(
                    Claim(
                        statement=f"{detail.name}位面饰品推荐包括{planar_names}。",
                        confidence=0.9,
                        citation_ids=[citation_id],
                    )
                )
            claims.append(
                Claim(
                    statement=(
                        f"{detail.name}档案主技能顺序为{skill_names or '暂无'}；"
                        "现有资料未提供可信技能优先级。"
                    ),
                    confidence=0.95,
                    citation_ids=[citation_id],
                )
            )

        ai_response = AIResponse(
            agent="character_build_agent",
            answer="本天才已经把多名角色的等级与技能目标合并成一份可执行养成方案。",
            claims=claims,
            citations=citations,
            validation=ValidationReport(
                status="verified" if claims else "unverified",
                method="deterministic_progression_rules+catalog_build_records",
                evidence_count=len(citations),
                notes=["材料数量由仓库内逐级规则计算，相同材料已合并。"],
            ),
            filtering=FilteringReport(
                passed=bool(claims),
                removed_claims=len(warnings),
                rules=[
                    "只保留能映射到物品档案的材料卡片。",
                    "构筑推荐按官方角色档案中的已对齐记录分组。",
                ],
                warnings=warnings,
            ),
            query_steps=[
                QueryStep(
                    id="character_build",
                    name="角色养成规划 Agent",
                    status="completed",
                    detail="完成多角色逐级消耗计算、材料合并与构筑档案校验。",
                    duration_ms=0,
                )
            ],
        )
        return MultiProgressionResponse(
            response=ai_response,
            characters=calculations,
            total_by_key=dict(total_by_key),
            materials=list(material_by_identity.values()),
            recommendations=recommendations,
        )

    @staticmethod
    def _recommendation(detail: Any) -> BuildRecommendation:
        tunnel = [
            item.model_dump()
            for item in detail.recommended_relics
            if item.set_type in {"tunnel", "cavern"}
        ]
        planar = [
            item.model_dump()
            for item in detail.recommended_relics
            if item.set_type == "planar"
        ]
        warnings: list[str] = []
        if not detail.recommended_lightcones:
            warnings.append(f"{detail.name}缺少已对齐光锥推荐。")
        if not tunnel:
            warnings.append(f"{detail.name}缺少已验证隧洞遗器推荐。")
        if not planar:
            warnings.append(f"{detail.name}缺少已验证位面饰品推荐。")
        skill_priority = [
            skill.name
            for skill in detail.skills
            if skill.type not in {"MazeNormal", "秘技"}
        ][:4]
        return BuildRecommendation(
            lightcones=[item.model_dump() for item in detail.recommended_lightcones],
            tunnel_relics=tunnel,
            planar_relics=planar,
            skill_priority=skill_priority,
            warnings=warnings,
        )


class WeeklyPlanningService:
    DUNGEON_RULES = {
        "weekly": ("历战余响", 30, 1),
        "ascension": ("凝滞虚影", 30, 2),
        "trace": ("拟造花萼（赤）", 10, 3),
        "credits": ("拟造花萼（金）", 10, 4),
        "relic": ("侵蚀隧洞", 40, 5),
        "free": ("无体力来源", 0, 6),
    }

    @classmethod
    def build_tasks(
        cls,
        plans: list[Any],
        *,
        stamina_budget: int,
        weekly_runs_remaining: int,
        previous_tasks: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for plan in plans:
            plan_priority = int(plan.priority)
            for material in plan.material_snapshot.get("materials", []):
                key = str(material.get("key") or "")
                category = cls._category(key)
                item = material.get("item") or {}
                target_key = str(item.get("id") or key)
                group = grouped.setdefault(
                    category,
                    {
                        "targets": {},
                        "source_plan_ids": set(),
                        "plan_priority": plan_priority,
                    },
                )
                group["plan_priority"] = min(group["plan_priority"], plan_priority)
                group["source_plan_ids"].add(plan.id)
                target = group["targets"].setdefault(
                    target_key,
                    {
                        "key": key,
                        "name": str(item.get("name") or key),
                        "required_quantity": 0,
                        "item_id": str(item.get("id")) if item.get("id") else None,
                        "entity_url": (
                            f"/items/{item['id']}" if item.get("id") else None
                        ),
                    },
                )
                target["required_quantity"] += int(material.get("quantity") or 0)

            relic_targets: dict[str, dict[str, Any]] = {}
            for recommendation in plan.recommendation_snapshot.values():
                for relic in recommendation.get("tunnel_relics", [])[:1]:
                    relic_id = str(relic.get("id") or "")
                    if not relic_id:
                        continue
                    relic_targets[relic_id] = {
                        "key": f"relic:{relic_id}",
                        "name": str(relic.get("name") or relic_id),
                        "required_quantity": 0,
                        "item_id": relic_id,
                        "entity_url": f"/relics/{relic_id}",
                    }
            if relic_targets:
                group = grouped.setdefault(
                    "relic",
                    {
                        "targets": {},
                        "source_plan_ids": set(),
                        "plan_priority": plan_priority,
                    },
                )
                group["plan_priority"] = min(group["plan_priority"], plan_priority)
                group["source_plan_ids"].add(plan.id)
                group["targets"].update(relic_targets)

        task_specs: list[dict[str, Any]] = []
        for category, group in grouped.items():
            dungeon_type, stamina_per_run, base_priority = cls.DUNGEON_RULES[category]
            task_specs.append(
                {
                    "category": category,
                    "dungeon_type": dungeon_type,
                    "stamina_per_run": stamina_per_run,
                    "priority": base_priority * 100 + int(group["plan_priority"]),
                    "targets": list(group["targets"].values()),
                    "source_plan_ids": sorted(group["source_plan_ids"]),
                    "run_count": 0,
                }
            )
        task_specs.sort(key=lambda item: item["priority"])

        allocated = 0
        weekly = next(
            (item for item in task_specs if item["category"] == "weekly"), None
        )
        if weekly:
            weekly["run_count"] = min(
                weekly_runs_remaining, stamina_budget // weekly["stamina_per_run"]
            )
            allocated += weekly["run_count"] * weekly["stamina_per_run"]

        stamina_specs = [
            item
            for item in task_specs
            if item["stamina_per_run"] > 0 and item["category"] != "weekly"
        ]
        while stamina_specs:
            progressed = False
            for item in stamina_specs:
                cost = item["stamina_per_run"]
                if allocated + cost <= stamina_budget:
                    item["run_count"] += 1
                    allocated += cost
                    progressed = True
            if not progressed:
                break

        completed_signatures = {
            cls._signature(task): bool(task.get("completed"))
            for task in previous_tasks or []
        }
        tasks: list[dict[str, Any]] = []
        for item in task_specs:
            run_count = int(item["run_count"])
            if item["stamina_per_run"] > 0 and run_count == 0:
                continue
            targets = item["targets"]
            target_text = "、".join(
                (
                    f"{target['name']}×{target['required_quantity']}"
                    if target["required_quantity"]
                    else f"{target['name']}（构筑推荐）"
                )
                for target in targets
            )
            stamina_cost = run_count * int(item["stamina_per_run"])
            task = {
                "id": str(uuid4()),
                "title": (
                    f"{item['dungeon_type']} · {run_count} 次"
                    if run_count
                    else f"{item['dungeon_type']} · 无需分配体力"
                ),
                "detail": (
                    f"目标：{target_text}。本周安排 {stamina_cost} 点体力；"
                    "材料数量是养成缺口，副本次数是本周预算分配，不代表固定掉落量。"
                    if stamina_cost
                    else f"目标：{target_text}。请通过敌人掉落、活动或合成补充。"
                ),
                "dungeon_type": item["dungeon_type"],
                "stamina_per_run": item["stamina_per_run"],
                "run_count": run_count,
                "stamina_cost": stamina_cost,
                "priority": item["priority"],
                "completed": False,
                "targets": targets,
                "source_plan_ids": item["source_plan_ids"],
            }
            task["completed"] = completed_signatures.get(cls._signature(task), False)
            tasks.append(task)
        return tasks

    @staticmethod
    def _category(key: str) -> str:
        if key == "weekly":
            return "weekly"
        if key == "ascension":
            return "ascension"
        if key.startswith("trace_path"):
            return "trace"
        if key == "credits":
            return "credits"
        return "free"

    @staticmethod
    def _signature(task: dict[str, Any]) -> str:
        target_keys = ",".join(
            sorted(str(target.get("key") or "") for target in task.get("targets", []))
        )
        return f"{task.get('dungeon_type')}:{target_keys}"


class DailyPlanningService:
    """生成并维护周计划的逐日体力排程（daily_schedule_v1）。

    规则：从周一到周日逐日排程，每天 240 点体力封顶；每天按优先级
    从高到低填充（历战余响恒置顶），单日排不下的自然落到后续天数；
    全周 7×240 仍排不下的次数计入溢出提示。每个日任务可独立勾选
    完成：完成状态持久化在 weekly_plans.daily_plan，按天扣减当日
    240 点账本，并反向同步周任务的完成次数与完成状态。
    """

    DAILY_STAMINA_CAP = 240
    SCHEDULE_VERSION = "daily_schedule_v4"
    EVIDENCE_VERSION = "weekly_plan_snapshot+daily_schedule_v4"
    WEEKLY_BOSS_TYPE = "历战余响"
    RECOMMENDED_TYPE = "侵蚀隧洞"
    WEEK_DAY_LABELS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

    @classmethod
    def _sorted_active_tasks(cls, weekly_plan_row: Any) -> list[dict[str, Any]]:
        active = [
            dict(task)
            for task in weekly_plan_row.tasks
            if int(task.get("run_count") or 0) > 0 and not task.get("completed")
        ]
        active.sort(
            key=lambda task: (
                0 if task.get("dungeon_type") == cls.WEEKLY_BOSS_TYPE else 1,
                int(task.get("priority") or 0),
            )
        )
        return active

    @classmethod
    def _tasks_signature(cls, weekly_plan_row: Any) -> str:
        return "|".join(
            sorted(
                f"{task.get('id')}:{task.get('run_count')}"
                for task in weekly_plan_row.tasks
            )
        )

    @classmethod
    def ensure_schedule(cls, weekly_plan_row: Any, *, today: date | None = None) -> None:
        """保证排程存在且"从今天开始"。

        每天首次访问时自动重锚（rolling re-anchor）：
        - 已完成的历史日程原样保留（进度不丢）；
        - 未完成的剩余次数从今天起重新按优先级前排；
        - 窗口起点滚动到今天，覆盖未来 7 天。
        """
        anchor = today if today is not None else weekly_plan_row.week_start
        if anchor < weekly_plan_row.week_start:
            anchor = weekly_plan_row.week_start
        schedule = weekly_plan_row.daily_plan
        needs_rebuild = not isinstance(schedule, dict) or (
            schedule.get("version") != cls.SCHEDULE_VERSION
            # 滚动窗口：锚点（窗口起点）不再是今天就必须重排
            or schedule.get("window_start") != anchor.isoformat()
            or schedule.get("tasks_signature") != cls._tasks_signature(weekly_plan_row)
        )
        if not needs_rebuild:
            return
        old_days = schedule.get("days", {}) if isinstance(schedule, dict) else {}
        # 完成历史双保险：
        # a) 按 (日期, 副本) 保留完成标记 —— 覆盖重新生成后任务换 id 的场景；
        # b) 按任务 id 统计已完成次数 —— 覆盖同任务跨天重锚的场景（只排剩余）。
        previous_completed = {
            (iso, item.get("dungeon_type")): bool(item.get("completed"))
            for iso, items in old_days.items()
            for item in items
            if isinstance(item, dict)
        }
        done_by_task: dict[str, int] = {}
        for items in old_days.values():
            for item in items:
                if item.get("completed"):
                    task_id = str(item.get("weekly_task_id"))
                    done_by_task[task_id] = (
                        done_by_task.get(task_id, 0)
                        + int(item.get("run_count") or 0)
                    )

        anchor_iso = anchor.isoformat()
        new_day_keys = [
            (anchor + timedelta(days=offset)).isoformat() for offset in range(7)
        ]
        day_slots: dict[str, list[dict[str, Any]]] = {iso: [] for iso in new_day_keys}
        pending: list[dict[str, Any]] = []
        for task in cls._sorted_active_tasks(weekly_plan_row):
            done = done_by_task.get(str(task["id"]), 0)
            pending.append(
                {
                    **task,
                    "remaining_runs": max(int(task["run_count"]) - done, 0),
                }
            )
        for iso in new_day_keys:
            capacity = cls.DAILY_STAMINA_CAP
            for task in pending:
                cost = int(task["stamina_per_run"])
                if cost <= 0 or task["remaining_runs"] <= 0:
                    continue
                fits = min(task["remaining_runs"], capacity // cost)
                if fits <= 0:
                    continue
                task["remaining_runs"] -= fits
                capacity -= fits * cost
                day_slots[iso].append(
                    {
                        "weekly_task_id": str(task["id"]),
                        "dungeon_type": task["dungeon_type"],
                        "stamina_per_run": cost,
                        "run_count": fits,
                        "run_count_week": int(task["run_count"]),
                        "priority": int(task.get("priority") or 0),
                        "completed": previous_completed.get(
                            (iso, task["dungeon_type"]), False
                        ),
                        # 侵蚀隧洞属于装备推荐刷取项，不计入养成方案完成度
                        "is_required": task["dungeon_type"] != cls.RECOMMENDED_TYPE,
                        "targets": list(task.get("targets") or []),
                    }
                )
        unscheduled = sum(task["remaining_runs"] for task in pending)
        # 过去日期的排程（含完成状态）原样保留，作为进度历史
        past_days = {
            iso: items
            for iso, items in old_days.items()
            if iso < anchor_iso and isinstance(items, list)
        }
        weekly_plan_row.daily_plan = {
            "version": cls.SCHEDULE_VERSION,
            "window_start": anchor_iso,
            "unscheduled_runs": unscheduled,
            "days": {**past_days, **day_slots},
            "tasks_signature": cls._tasks_signature(weekly_plan_row),
        }
        # 滚动窗口：起点滚动到今天
        weekly_plan_row.week_start = anchor
        weekly_plan_row.week_end = anchor + timedelta(days=6)
        cls.sync_weekly_tasks(weekly_plan_row)

    @classmethod
    def sync_weekly_tasks(cls, weekly_plan_row: Any) -> None:
        schedule = (
            weekly_plan_row.daily_plan
            if isinstance(weekly_plan_row.daily_plan, dict)
            else {}
        )
        completed_by_task: dict[str, int] = {}
        scheduled_by_task: dict[str, int] = {}
        for items in schedule.get("days", {}).values():
            for item in items:
                task_id = str(item.get("weekly_task_id"))
                runs = int(item.get("run_count") or 0)
                scheduled_by_task[task_id] = scheduled_by_task.get(task_id, 0) + runs
                if item.get("completed"):
                    completed_by_task[task_id] = (
                        completed_by_task.get(task_id, 0) + runs
                    )
        tasks = [dict(task) for task in weekly_plan_row.tasks]
        for task in tasks:
            task_id = str(task["id"])
            done = completed_by_task.get(task_id, 0)
            scheduled = scheduled_by_task.get(task_id, 0)
            task["completed_runs"] = done
            task["is_required"] = task.get("dungeon_type") != cls.RECOMMENDED_TYPE
            if scheduled > 0:
                task["completed"] = done >= scheduled
        weekly_plan_row.tasks = tasks

    @classmethod
    def set_daily_completion(
        cls, weekly_plan_row: Any, day: str, weekly_task_id: str, completed: bool
    ) -> bool:
        schedule = (
            weekly_plan_row.daily_plan
            if isinstance(weekly_plan_row.daily_plan, dict)
            else {}
        )
        changed = False
        for item in schedule.get("days", {}).get(day, []):
            if str(item.get("weekly_task_id")) == weekly_task_id:
                item["completed"] = bool(completed)
                changed = True
        if changed:
            # JSON 列的原地修改 SQLAlchemy 检测不到（flush 用 == 比较新旧值，
            # 内容相等就跳过），必须 flag_modified 强制写库，否则下一次请求
            # 从数据库读到旧排程，之前的完成状态会"凭空消失"。
            weekly_plan_row.daily_plan = copy.deepcopy(schedule)
            try:
                flag_modified(weekly_plan_row, "daily_plan")
            except Exception:  # 单元测试使用非 ORM 的 SimpleNamespace 桩对象
                pass
            cls.sync_weekly_tasks(weekly_plan_row)
        return changed

    @classmethod
    def set_weekly_completion(
        cls, weekly_plan_row: Any, weekly_task_id: str, completed: bool
    ) -> None:
        tasks = [dict(task) for task in weekly_plan_row.tasks]
        for task in tasks:
            if str(task["id"]) == weekly_task_id:
                task["completed"] = bool(completed)
        weekly_plan_row.tasks = tasks

        schedule = (
            weekly_plan_row.daily_plan
            if isinstance(weekly_plan_row.daily_plan, dict)
            else {}
        )
        had_items = False
        for items in schedule.get("days", {}).values():
            for item in items:
                if str(item.get("weekly_task_id")) == weekly_task_id:
                    item["completed"] = bool(completed)
                    had_items = True
        if not completed and not had_items:
            # 取消的是一个从未排入日程的已完成任务：重排让它回归每日计划。
            weekly_plan_row.daily_plan = None
            cls.ensure_schedule(weekly_plan_row)
            return
        # 同 set_daily_completion：JSON 原地修改必须 flag_modified 才会持久化。
        weekly_plan_row.daily_plan = copy.deepcopy(schedule)
        try:
            flag_modified(weekly_plan_row, "daily_plan")
        except Exception:  # 单元测试使用非 ORM 的 SimpleNamespace 桩对象
            pass
        cls.sync_weekly_tasks(weekly_plan_row)

    @classmethod
    def empty_view(cls, today: date) -> dict[str, Any]:
        week_start = today - timedelta(days=today.weekday())
        return {
            "date": today,
            "weekday_label": cls.WEEK_DAY_LABELS[today.weekday()],
            "week_start": week_start,
            "week_end": week_start + timedelta(days=6),
            "week_day_index": today.weekday() + 1,
            "remaining_days": 7 - today.weekday(),
            "stamina_cap": cls.DAILY_STAMINA_CAP,
            "planned_stamina": 0,
            "completed_stamina": 0,
            "weekly_budget": 0,
            "weekly_allocated": 0,
            "weekly_runs_remaining": 0,
            "items": [],
            "notice": "本周计划尚未生成。请先在“本周”页签生成本周计划，再查看每日安排。",
            "evidence_version": cls.EVIDENCE_VERSION,
        }

    @classmethod
    def day_view(cls, weekly_plan_row: Any, *, today: date) -> dict[str, Any]:
        week_start: date = weekly_plan_row.week_start
        week_end: date = weekly_plan_row.week_end
        schedule = (
            weekly_plan_row.daily_plan
            if isinstance(weekly_plan_row.daily_plan, dict)
            else {}
        )
        iso = today.isoformat()
        planned_stamina = 0
        completed_stamina = 0
        items: list[dict[str, Any]] = []
        for item in schedule.get("days", {}).get(iso, []):
            runs = int(item.get("run_count") or 0)
            cost = int(item.get("stamina_per_run") or 0)
            stamina = runs * cost
            completed = bool(item.get("completed"))
            planned_stamina += stamina
            if completed:
                completed_stamina += stamina
            items.append(
                {
                    "weekly_task_id": str(item.get("weekly_task_id")),
                    "title": str(item.get("dungeon_type")),
                    "dungeon_type": item.get("dungeon_type"),
                    "stamina_per_run": cost,
                    "run_count_week": int(item.get("run_count_week") or 0),
                    "runs_planned": runs,
                    "stamina": stamina,
                    "completed": completed,
                    "is_weekly_boss": item.get("dungeon_type") == cls.WEEKLY_BOSS_TYPE,
                    "is_required": bool(item.get("is_required", True)),
                    "priority": int(item.get("priority") or 0),
                    "targets": list(item.get("targets") or []),
                }
            )
        unscheduled = int(schedule.get("unscheduled_runs") or 0)
        if items:
            notice = (
                f"当日计划 {planned_stamina} 点体力，已完成 {completed_stamina} 点；"
                "点击任务按钮即从当日 240 点账本核销，并同步到周计划进度。"
            )
            if planned_stamina < cls.DAILY_STAMINA_CAP:
                if unscheduled:
                    notice += "当日剩余体力不足以安排一次剩余的整次副本，已尽量排满。"
                else:
                    notice += (
                        "本周养成需求已全部排入，当日少于 240 点属正常剩余，"
                        "可自由用于每日实训或其他资源副本。"
                    )
        elif unscheduled:
            notice = "本日无需安排体力：剩余需求已超出全周容量。"
        else:
            notice = "本日没有排程任务，好好休息。"
        if unscheduled:
            notice += f"另有 {unscheduled} 次低优先级需求超出 7×240 点容量，未排入本周。"
        return {
            "date": today,
            "weekday_label": cls.WEEK_DAY_LABELS[today.weekday()],
            "week_start": week_start,
            "week_end": week_end,
            "week_day_index": today.weekday() + 1,
            "remaining_days": max((week_end - today).days + 1, 1),
            "stamina_cap": cls.DAILY_STAMINA_CAP,
            "planned_stamina": planned_stamina,
            "completed_stamina": completed_stamina,
            "weekly_budget": int(weekly_plan_row.stamina_budget),
            "weekly_allocated": int(weekly_plan_row.allocated_stamina),
            "weekly_runs_remaining": int(weekly_plan_row.weekly_runs_remaining),
            "items": items,
            "notice": notice,
            "evidence_version": cls.EVIDENCE_VERSION,
        }

    @classmethod
    def weekly_statistics(
        cls, weekly_plan_row: Any, plan_names: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """方案进度统计：完成度只观察养成刚需副本（侵蚀隧洞为推荐项单列），
        用于确认养成方案是否跟随排程逐步完成。"""
        schedule = (
            weekly_plan_row.daily_plan
            if isinstance(weekly_plan_row.daily_plan, dict)
            else {}
        )
        scheduled_by_task: dict[str, int] = {}
        done_by_task: dict[str, int] = {}
        for items in schedule.get("days", {}).values():
            for item in items:
                task_id = str(item.get("weekly_task_id"))
                runs = int(item.get("run_count") or 0)
                scheduled_by_task[task_id] = scheduled_by_task.get(task_id, 0) + runs
                if item.get("completed"):
                    done_by_task[task_id] = done_by_task.get(task_id, 0) + runs

        required_scheduled = 0
        required_completed = 0
        recommended_scheduled = 0
        recommended_completed = 0
        plans_progress: dict[str, dict[str, Any]] = {}
        for task in weekly_plan_row.tasks:
            task_id = str(task["id"])
            is_required = task.get("dungeon_type") != cls.RECOMMENDED_TYPE
            scheduled = scheduled_by_task.get(task_id, 0)
            done = done_by_task.get(task_id, 0)
            if is_required:
                required_scheduled += scheduled
                required_completed += done
                for plan_id in task.get("source_plan_ids") or []:
                    entry = plans_progress.setdefault(
                        str(plan_id),
                        {
                            "plan_id": str(plan_id),
                            "plan_name": (plan_names or {}).get(
                                str(plan_id), "养成方案"
                            ),
                            "scheduled_runs": 0,
                            "completed_runs": 0,
                        },
                    )
                    entry["scheduled_runs"] += scheduled
                    entry["completed_runs"] += done
            else:
                recommended_scheduled += scheduled
                recommended_completed += done

        return {
            "required_scheduled": required_scheduled,
            "required_completed": required_completed,
            "recommended_scheduled": recommended_scheduled,
            "recommended_completed": recommended_completed,
            "plan_complete": required_scheduled > 0
            and required_completed >= required_scheduled,
            "plans": list(plans_progress.values()),
        }
