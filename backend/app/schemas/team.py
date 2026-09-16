from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.ai_response import AIResponse


class OfficialTeamRequest(BaseModel):
    core_character_id: str = Field(min_length=1, max_length=16)
    preferred_character_ids: list[str] = Field(default_factory=list, max_length=20)
    excluded_character_ids: list[str] = Field(default_factory=list, max_length=20)
    require_sustain: bool = True
    use_owned_only: bool = False
    game_mode: Literal["balanced", "moc", "pure_fiction", "apocalyptic"] = (
        "balanced"
    )

    @field_validator("preferred_character_ids", "excluded_character_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


class OfficialTeamMember(BaseModel):
    character_id: str
    name: str
    element: str
    roles: list[str]
    mechanic_tags: list[str] = Field(default_factory=list)
    image_url: str | None = None


class TeamScenarioScore(BaseModel):
    scenario_id: str
    name: str
    score: float


class TeamScoreBreakdown(BaseModel):
    scoring_version: str
    game_data_version: str
    structural_score: float
    knowledge_score: float = 50.0
    knowledge_notes: list[str] = Field(default_factory=list)
    mechanical_simulation_score: float
    observed_meta_score: float | None = None
    evidence_confidence: float
    final_score: float
    scenarios: list[TeamScenarioScore] = Field(default_factory=list)


class TeamRotationSummary(BaseModel):
    skill_point_balance: float
    estimated_ultimate_turns: dict[str, float | None] = Field(default_factory=dict)
    speed_order: list[str] = Field(default_factory=list)


class OfficialRecommendedTeam(BaseModel):
    members: list[OfficialTeamMember]
    score: float
    covered_roles: list[str]
    reasons: list[str]
    strengths: list[str]
    weaknesses: list[str]
    source_character_ids: list[str]
    preferred_character_ids: list[str] = Field(default_factory=list)
    missing_character_ids: list[str] = Field(default_factory=list)
    model_assessment: str | None = None
    model_verdict: str | None = None
    score_breakdown: TeamScoreBreakdown | None = None
    rotation: TeamRotationSummary | None = None
    data_warnings: list[str] = Field(default_factory=list)


class OfficialTeamResponse(BaseModel):
    response: AIResponse
    theoretical: list[OfficialRecommendedTeam]
    owned: list[OfficialRecommendedTeam]
    favorite_trials: list[OfficialRecommendedTeam] = Field(default_factory=list)


class SavedTeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=48)
    member_ids: list[str] = Field(min_length=4, max_length=4)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("member_ids")
    @classmethod
    def validate_members(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if len(set(cleaned)) != 4:
            raise ValueError("队伍必须包含 4 名不重复角色")
        return cleaned


class SavedTeamUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=48)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()


class SavedTeamResponse(BaseModel):
    id: str
    name: str
    members: list[OfficialTeamMember]
    created_at: datetime
    updated_at: datetime


class SavedTeamListResponse(BaseModel):
    items: list[SavedTeamResponse]
    total: int
