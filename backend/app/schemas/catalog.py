from pydantic import BaseModel, Field


class CharacterSummary(BaseModel):
    id: str
    name: str
    rarity: int
    path: str
    element: str
    image_url: str | None = None


class NamedDescription(BaseModel):
    name: str
    description: str
    type: str | None = None
    image_url: str | None = None


class RelatedItem(BaseModel):
    id: str
    name: str
    rarity: str
    type: str
    description: str = ""
    image_url: str | None = None


class EntityRecommendation(BaseModel):
    id: str
    name: str
    kind: str
    image_url: str | None = None
    image_status: str = "official"
    set_type: str | None = None
    piece_count: int | None = None


class KnowledgeEntitySummary(BaseModel):
    id: str
    name: str
    kind: str
    subtitle: str = ""
    image_url: str | None = None
    image_status: str = "official"
    rarity: int | None = None
    path: str | None = None
    set_type: str | None = None
    piece_count: int | None = None


class RelatedEntity(KnowledgeEntitySummary):
    pass


class KnowledgeEntityDetail(KnowledgeEntitySummary):
    description: str = ""
    sections: list[NamedDescription] = Field(default_factory=list)
    related_entities: list[RelatedEntity] = Field(default_factory=list)
    source_url: str | None = None
    data_version: str | None = None


class LightconeLevelStats(BaseModel):
    level: int
    hp: int
    attack: int
    defence: int


class LightconeMaterial(RelatedItem):
    quantity: int


class LightconeDetail(KnowledgeEntityDetail):
    lore_description: str = ""
    effect_name: str = ""
    superimposition_effects: list[str] = Field(default_factory=list)
    level_stats: list[LightconeLevelStats] = Field(default_factory=list)
    promotion_materials: dict[int, list[LightconeMaterial]] = Field(default_factory=dict)


class RelicDetail(KnowledgeEntityDetail):
    set_type: str
    piece_count: int
    acquisition: str = ""
    set_effects: list[NamedDescription] = Field(default_factory=list)
    pieces: list[NamedDescription] = Field(default_factory=list)
    community_source_url: str | None = None


class CharacterDetail(CharacterSummary):
    description: str = ""
    energy: str | None = None
    stats: dict[str, str] = Field(default_factory=dict)
    skills: list[NamedDescription] = Field(default_factory=list)
    eidolons: list[NamedDescription] = Field(default_factory=list)
    related_items: list[RelatedItem] = Field(default_factory=list)
    recommended_lightcones: list[EntityRecommendation] = Field(default_factory=list)
    recommended_relics: list[EntityRecommendation] = Field(default_factory=list)
    story: str = ""
    community_source_url: str | None = None
    portrait_url: str | None = None
    element_icon_url: str | None = None
    path_icon_url: str | None = None
    source_url: str
    data_version: str | None = None


class ItemDetail(RelatedItem):
    background: str = ""
    sources: list[str] = Field(default_factory=list)
    pile_limit: int | None = None
    source_url: str | None = None
    related_entities: list[RelatedEntity] = Field(default_factory=list)


class CharacterListResponse(BaseModel):
    items: list[CharacterSummary]
    total: int


class ItemListResponse(BaseModel):
    items: list[RelatedItem]
    total: int


class KnowledgeEntityListResponse(BaseModel):
    items: list[KnowledgeEntitySummary]
    total: int
