from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ActivityImage(BaseModel):
    source_url: str = ""
    api_path: str | None = None
    availability: str = "missing"


class ActivitySummary(BaseModel):
    id: str
    title: str
    version: str
    schedule: str = ""
    types: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    image: ActivityImage | None = None
    detail_available: bool = False
    official_guide_available: bool = False
    community_submission_available: bool = False


class ActivityDetail(ActivitySummary):
    detail: dict | None = None
    source: dict = Field(default_factory=dict)


class ActivityListResponse(BaseModel):
    items: list[ActivitySummary]
    total: int


class ActivityGuideCreate(BaseModel):
    title: str = Field(min_length=2, max_length=100)
    content: str = Field(min_length=40, max_length=12000)
    player_stage: Literal["beginner", "midgame", "endgame", "all"] = "all"


class ActivityGuideReview(BaseModel):
    action: Literal["approve", "reject"]
    reason: str = Field(default="", max_length=1000)


class ActivityGuideResponse(BaseModel):
    id: str
    activity_id: str
    activity_title: str
    author_id: str
    author_name: str
    title: str
    content: str
    player_stage: str
    status: str
    review_reason: str | None = None
    submitted_at: datetime
    reviewed_at: datetime | None = None


class ActivityGuideListResponse(BaseModel):
    items: list[ActivityGuideResponse]
    total: int
