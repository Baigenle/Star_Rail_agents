from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class CharacterPoolUpdate(BaseModel):
    character_ids: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("character_ids")
    @classmethod
    def normalize_character_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        return list(dict.fromkeys(normalized))


class FavoriteCharacterUpdate(BaseModel):
    is_favorite: bool


class UserCharacterResponse(BaseModel):
    character_id: str
    name: str
    rarity: int
    path: str
    element: str
    image_url: str | None = None
    level: int
    eidolon: int
    is_favorite: bool
    is_built: bool
    created_at: datetime
    updated_at: datetime


class CharacterPoolResponse(BaseModel):
    items: list[UserCharacterResponse]
    total: int
    favorites: int


class CharacterProgressUpdate(BaseModel):
    current_level: int = Field(ge=1, le=80)
    target_level: int = Field(ge=1, le=80)
    eidolon: int = Field(default=0, ge=0, le=6)
    current_skills: dict[str, int] = Field(default_factory=dict)
    target_skills: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_targets(self) -> "CharacterProgressUpdate":
        if self.current_level > self.target_level:
            raise ValueError("目标等级不能低于当前等级")
        if set(self.current_skills) != set(self.target_skills):
            raise ValueError("当前与目标技能必须使用相同的技能轨道")
        if any(
            current > self.target_skills[key]
            for key, current in self.current_skills.items()
        ):
            raise ValueError("目标技能等级不能低于当前技能等级")
        return self


class CharacterProgressResponse(CharacterProgressUpdate):
    character_id: str
    created_at: datetime
    updated_at: datetime
