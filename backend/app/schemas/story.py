from pydantic import BaseModel, Field


class StorySummary(BaseModel):
    mission_id: str
    mission_name: str
    mission_type: str
    version: str
    world: str
    series_name: str
    mission_order: int
    characters: list[str] = Field(default_factory=list)
    summary: str
    scene_count: int = 0
    matched_character: str | None = None
    matched_scene_count: int = 0
    first_matching_chunk_id: str | None = None


class StorySceneSummary(BaseModel):
    chunk_id: str
    chunk_order: int
    scene_title: str
    location: str | None = None
    characters: list[str] = Field(default_factory=list)


class StoryDetail(StorySummary):
    story_text: str
    source_url: str
    previous_mission: str | None = None
    next_mission: str | None = None
    scenes: list[StorySceneSummary] = Field(default_factory=list)


class StoryScene(StorySceneSummary):
    mission_id: str
    mission_name: str
    content: str
    source_url: str
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None


class StoryFilters(BaseModel):
    versions: list[str] = Field(default_factory=list)
    worlds: list[str] = Field(default_factory=list)
    mission_types: list[str] = Field(default_factory=list)
    series: list[str] = Field(default_factory=list)


class StoryListResponse(BaseModel):
    items: list[StorySummary]
    total: int
    filters: StoryFilters
