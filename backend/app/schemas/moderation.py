from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ModerationRequest(BaseModel):
    action: Literal["unpublish", "republish"]
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None


class CompletenessAssessment(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    missing_fields: list[str] = Field(default_factory=list)


class CharacterAIAssessment(BaseModel):
    decision: Literal["advisory_only"] = "advisory_only"
    completeness: CompletenessAssessment
    consistency_warnings: list[str] = Field(default_factory=list)
    numerical_risks: list[str] = Field(default_factory=list)
    official_lore_risks: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    model_used: bool = False
    generated_at: datetime


class ModerationListItem(BaseModel):
    content_type: Literal["character", "activity_guide"]
    content_id: str
    title: str
    status: str
    author_name: str
    reason: str | None = None
    updated_at: datetime


class ModerationListResponse(BaseModel):
    items: list[ModerationListItem]
    total: int
