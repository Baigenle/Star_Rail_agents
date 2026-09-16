from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.ai_response import AIResponse
from app.schemas.progression import (
    ProgressionCalculateResponse,
    ProgressionMaterialResponse,
    SkillRange,
)


class CharacterPlanInput(BaseModel):
    character_id: str
    from_level: int = Field(ge=1, le=80)
    to_level: int = Field(ge=1, le=80)
    skill_ranges: dict[str, SkillRange] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_levels(self) -> "CharacterPlanInput":
        if self.from_level > self.to_level:
            raise ValueError("目标等级不能低于当前等级")
        return self


class MultiProgressionRequest(BaseModel):
    characters: list[CharacterPlanInput] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_unique_characters(self) -> "MultiProgressionRequest":
        ids = [item.character_id for item in self.characters]
        if len(ids) != len(set(ids)):
            raise ValueError("同一角色不能在一份方案中重复")
        return self


class BuildRecommendation(BaseModel):
    lightcones: list[dict] = Field(default_factory=list)
    tunnel_relics: list[dict] = Field(default_factory=list)
    planar_relics: list[dict] = Field(default_factory=list)
    skill_priority: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MultiProgressionResponse(BaseModel):
    response: AIResponse
    characters: list[ProgressionCalculateResponse]
    total_by_key: dict[str, int]
    materials: list[ProgressionMaterialResponse]
    recommendations: dict[str, BuildRecommendation]


class ProgressionPlanCreate(MultiProgressionRequest):
    name: str = Field(min_length=1, max_length=80)
    priority: int = Field(default=1, ge=1, le=99)


class ProgressionPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    priority: int | None = Field(default=None, ge=1, le=99)
    status: Literal["active", "paused", "completed"] | None = None


class ProgressionPlanProgress(BaseModel):
    scheduled_runs: int = Field(default=0, ge=0)
    completed_runs: int = Field(default=0, ge=0)
    required_scheduled: int = Field(default=0, ge=0)
    required_completed: int = Field(default=0, ge=0)
    in_current_window: bool = False
    complete: bool = False


class ProgressionPlanResponse(BaseModel):
    id: str
    name: str
    status: Literal["active", "paused", "completed"]
    priority: int
    request_payload: dict
    material_snapshot: dict
    recommendation_snapshot: dict
    progress: ProgressionPlanProgress
    created_at: datetime
    updated_at: datetime


class ProgressionPlanListResponse(BaseModel):
    items: list[ProgressionPlanResponse]
    total: int


class WeeklyPlanGenerateRequest(BaseModel):
    stamina_budget: int = Field(default=1680, ge=0, le=2400)
    weekly_runs_remaining: int = Field(default=3, ge=0, le=3)


class WeeklyMaterialTarget(BaseModel):
    key: str
    name: str
    required_quantity: int = Field(ge=0)
    item_id: str | None = None
    entity_url: str | None = None


class WeeklyTask(BaseModel):
    id: str
    title: str
    detail: str
    dungeon_type: Literal[
        "历战余响",
        "拟造花萼（金）",
        "拟造花萼（赤）",
        "凝滞虚影",
        "侵蚀隧洞",
        "无体力来源",
    ]
    stamina_per_run: int = Field(ge=0)
    run_count: int = Field(ge=0)
    stamina_cost: int = Field(ge=0)
    priority: int = Field(ge=1)
    completed: bool = False
    completed_runs: int = Field(default=0, ge=0)
    is_required: bool = True
    targets: list[WeeklyMaterialTarget] = Field(default_factory=list)
    source_plan_ids: list[str] = Field(default_factory=list)


class PlanProgressEntry(BaseModel):
    plan_id: str
    plan_name: str
    scheduled_runs: int = Field(default=0, ge=0)
    completed_runs: int = Field(default=0, ge=0)


class WeeklyStatistics(BaseModel):
    required_scheduled: int = Field(default=0, ge=0)
    required_completed: int = Field(default=0, ge=0)
    recommended_scheduled: int = Field(default=0, ge=0)
    recommended_completed: int = Field(default=0, ge=0)
    plan_complete: bool = False
    plans: list[PlanProgressEntry] = Field(default_factory=list)


class WeeklyPlanResponse(BaseModel):
    id: str
    week_start: date
    week_end: date
    stamina_budget: int
    allocated_stamina: int
    weekly_runs_remaining: int
    tasks: list[WeeklyTask]
    statistics: WeeklyStatistics
    notice: str
    evidence_version: str
    created_at: datetime
    updated_at: datetime


class WeeklyTaskUpdate(BaseModel):
    completed: bool


class DailyTaskSlice(BaseModel):
    weekly_task_id: str
    title: str
    dungeon_type: Literal[
        "历战余响",
        "拟造花萼（金）",
        "拟造花萼（赤）",
        "凝滞虚影",
        "侵蚀隧洞",
        "无体力来源",
    ]
    stamina_per_run: int = Field(ge=0)
    run_count_week: int = Field(ge=0)
    runs_planned: int = Field(ge=0)
    stamina: int = Field(ge=0)
    completed: bool = False
    is_weekly_boss: bool = False
    is_required: bool = True
    priority: int = Field(ge=1)
    targets: list[WeeklyMaterialTarget] = Field(default_factory=list)


class DailyPlanResponse(BaseModel):
    date: date
    weekday_label: str
    week_start: date
    week_end: date
    week_day_index: int = Field(ge=1, le=7)
    remaining_days: int = Field(ge=1)
    stamina_cap: int = Field(ge=0)
    planned_stamina: int = Field(ge=0)
    completed_stamina: int = Field(ge=0)
    weekly_budget: int = Field(ge=0)
    weekly_allocated: int = Field(ge=0)
    weekly_runs_remaining: int = Field(ge=0)
    items: list[DailyTaskSlice] = Field(default_factory=list)
    notice: str
    evidence_version: str
