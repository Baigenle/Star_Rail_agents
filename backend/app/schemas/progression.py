from pydantic import BaseModel, Field, model_validator

from app.schemas.catalog import RelatedItem


class SkillRange(BaseModel):
    from_level: int = Field(ge=1, le=10)
    to_level: int = Field(ge=1, le=10)

    @model_validator(mode="after")
    def validate_order(self) -> "SkillRange":
        if self.from_level > self.to_level:
            raise ValueError("目标技能等级不能低于当前等级")
        return self


class ProgressionCalculateRequest(BaseModel):
    from_level: int = Field(ge=1, le=80)
    to_level: int = Field(ge=1, le=80)
    skill_ranges: dict[str, SkillRange] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_order(self) -> "ProgressionCalculateRequest":
        if self.from_level > self.to_level:
            raise ValueError("目标角色等级不能低于当前等级")
        return self


class ProgressionTrack(BaseModel):
    label: str
    max_level: int


class ProgressionProfile(BaseModel):
    character_id: str
    archetype: str
    tracks: dict[str, ProgressionTrack]
    ascension_gates: list[int]


class ProgressionMaterialResponse(BaseModel):
    key: str
    quantity: int
    item: RelatedItem | None


class ProgressionCalculateResponse(BaseModel):
    character_id: str
    archetype: str
    from_level: int
    to_level: int
    skill_ranges: dict[str, SkillRange]
    total_by_key: dict[str, int]
    materials: list[ProgressionMaterialResponse]
