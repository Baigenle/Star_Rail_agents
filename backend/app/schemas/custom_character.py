from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.ai_response import AIResponse


Element = Literal["物理", "火", "冰", "雷", "风", "量子", "虚数"]
PathName = Literal[
    "毁灭", "巡猎", "智识", "同谐", "虚无", "存护", "丰饶", "记忆", "欢愉"
]
RoleName = Literal["主C", "副C", "辅助", "生存"]
CORE_SKILL_KEYS = {"basic", "skill", "ultimate", "talent", "technique"}
SPECIAL_SKILL_KEYS = {"elation_skill", "memosprite_skill", "memosprite_talent"}


class CustomBaseStats(BaseModel):
    hp: int = Field(ge=1, le=9999)
    attack: int = Field(ge=1, le=9999)
    defence: int = Field(ge=1, le=9999)
    speed: int = Field(ge=1, le=999)
    taunt: int = Field(ge=1, le=999)
    energy: int = Field(ge=0, le=999)


class CustomCharacterPayload(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=48)
    rarity: Literal[4, 5] | None = None
    element: Element | None = None
    path: PathName | None = None
    summary: str | None = Field(default=None, max_length=500)
    roles: list[RoleName] = Field(default_factory=list, max_length=4)
    core_mechanics: str | None = Field(default=None, max_length=2000)
    mechanic_tags: list[str] = Field(default_factory=list, max_length=20)
    base_stats: CustomBaseStats | None = None
    skills: dict[str, str] = Field(default_factory=dict)
    special_skills: dict[str, str] = Field(default_factory=dict)
    story: str | None = Field(default=None, max_length=12000)
    eidolons: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("mechanic_tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(tag.strip() for tag in value if tag.strip()))
        if any(len(tag) > 32 for tag in normalized):
            raise ValueError("机制标签不能超过 32 个字符")
        return normalized

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, value: dict[str, str]) -> dict[str, str]:
        return cls._validate_skill_map(value, CORE_SKILL_KEYS)

    @field_validator("special_skills")
    @classmethod
    def validate_special_skills(cls, value: dict[str, str]) -> dict[str, str]:
        return cls._validate_skill_map(value, SPECIAL_SKILL_KEYS)

    @staticmethod
    def _validate_skill_map(
        value: dict[str, str], allowed_keys: set[str]
    ) -> dict[str, str]:
        unexpected = set(value) - allowed_keys
        if unexpected:
            raise ValueError(f"不支持的技能槽位：{', '.join(sorted(unexpected))}")
        normalized = {key: description.strip() for key, description in value.items()}
        if any(len(description) > 4000 for description in normalized.values()):
            raise ValueError("单项技能描述不能超过 4000 个字符")
        return normalized

    @field_validator("eidolons")
    @classmethod
    def validate_eidolons(cls, value: list[str]) -> list[str]:
        normalized = [description.strip() for description in value]
        if any(len(description) > 2000 for description in normalized):
            raise ValueError("单项星魂描述不能超过 2000 个字符")
        return normalized


class CustomCharacterCreate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=48)


class CustomCharacterPatch(BaseModel):
    payload: CustomCharacterPayload


class CustomCharacterResponse(BaseModel):
    id: str
    author_id: str
    author_name: str
    name: str
    visibility: str
    version_id: str
    version_number: int
    status: str
    payload: CustomCharacterPayload
    review_reason: str | None = None
    is_owner: bool
    created_at: datetime
    updated_at: datetime


class CustomCharacterListResponse(BaseModel):
    items: list[CustomCharacterResponse]
    total: int


class SelfReviewIssue(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    severity: Literal["error", "warning", "suggestion"]
    field: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    suggestion: str = Field(min_length=1, max_length=500)


class SelfReviewCategory(BaseModel):
    key: Literal[
        "completeness",
        "authenticity",
        "consistency",
        "balance",
        "compliance",
    ]
    name: str
    score: int = Field(ge=0, le=100)
    max_score: Literal[100] = 100
    weight: int = Field(ge=1, le=100)
    issues: list[SelfReviewIssue] = Field(default_factory=list)


class SelfReviewReport(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    verdict: Literal["ready", "needs_work", "rejected"]
    summary: str = Field(min_length=1, max_length=1000)
    categories: list[SelfReviewCategory]
    highlights: list[str] = Field(default_factory=list)
    must_fix_count: int = Field(ge=0)
    warn_count: int = Field(ge=0)
    model_used: bool = False
    generated_at: datetime


class CreatorSessionResponse(BaseModel):
    id: str
    character_id: str
    stage: int
    status: str
    pending_fields: dict
    created_at: datetime
    updated_at: datetime


class CreatorMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    fields: dict = Field(default_factory=dict)


class CreatorTurnResponse(BaseModel):
    response: AIResponse
    character_id: str
    session_id: str
    stage: int
    draft: CustomCharacterPayload
    pending_fields: dict
    required_fields: list[str]


class TeamMemberResponse(BaseModel):
    character_id: str
    name: str
    element: str
    roles: list[str]
    is_custom: bool


class RecommendedTeamResponse(BaseModel):
    members: list[TeamMemberResponse]
    score: float
    covered_roles: list[str]
    reasons: list[str]
    source_character_ids: list[str]


class CustomTeamResponse(BaseModel):
    response: AIResponse
    theoretical: list[RecommendedTeamResponse]
    owned: list[RecommendedTeamResponse]


class ReviewRequest(BaseModel):
    action: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def validate_rejection_reason(cls, value: str | None, info) -> str | None:
        return value.strip() if value else None
