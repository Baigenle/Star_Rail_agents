from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.schemas.catalog import (
    CharacterDetail,
    CharacterListResponse,
    ItemDetail,
    ItemListResponse,
    KnowledgeEntityDetail,
    KnowledgeEntityListResponse,
    LightconeDetail,
    RelicDetail,
)
from app.schemas.progression import (
    ProgressionCalculateRequest,
    ProgressionCalculateResponse,
    ProgressionMaterialResponse,
    ProgressionProfile,
    ProgressionTrack,
    SkillRange,
)
from app.services.catalog_service import CatalogService
from app.services.progression_service import ProgressionService, ProgressionValidationError

router = APIRouter()
service = CatalogService(settings.docs_root)
progression_service = ProgressionService(settings.docs_root)
ENTITY_KINDS = {"lightcones", "relics", "items", "monsters"}


@router.get("/characters", response_model=CharacterListResponse)
async def list_characters(
    search: str = "",
    element: str = "",
    path: str = "",
    rarity: int | None = Query(default=None, ge=4, le=5),
) -> CharacterListResponse:
    items = service.list_characters(search, element, path, rarity)
    return CharacterListResponse(items=items, total=len(items))


@router.get("/characters/{character_id}", response_model=CharacterDetail)
async def get_character(character_id: str) -> CharacterDetail:
    character = service.get_character(character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="角色不存在或数据尚未准备完成")
    return character


@router.get(
    "/characters/{character_id}/progression", response_model=ProgressionProfile
)
async def get_character_progression(character_id: str) -> ProgressionProfile:
    try:
        archetype = progression_service.archetype_for(character_id)
        tracks = progression_service.track_definitions(character_id)
    except ProgressionValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProgressionProfile(
        character_id=character_id,
        archetype=archetype,
        tracks={
            key: ProgressionTrack(
                label=str(definition["label"]),
                max_level=int(definition["max_level"]),
            )
            for key, definition in tracks.items()
        },
        ascension_gates=[
            int(level) for level in progression_service.rules()["ascension"]["steps"]
        ],
    )


@router.post(
    "/characters/{character_id}/progression/calculate",
    response_model=ProgressionCalculateResponse,
)
async def calculate_character_progression(
    character_id: str, payload: ProgressionCalculateRequest
) -> ProgressionCalculateResponse:
    try:
        result = progression_service.calculate(
            character_id,
            from_level=payload.from_level,
            to_level=payload.to_level,
            skill_ranges={
                key: (value.from_level, value.to_level)
                for key, value in payload.skill_ranges.items()
            },
        )
    except ProgressionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ProgressionCalculateResponse(
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


@router.get("/items", response_model=ItemListResponse)
async def list_items(
    search: str = "", limit: int = Query(default=2000, ge=1, le=2000)
) -> ItemListResponse:
    items = service.list_items(search, limit)
    return ItemListResponse(items=items, total=len(items))


@router.get("/items/{item_id}", response_model=ItemDetail)
async def get_item(item_id: str) -> ItemDetail:
    item = service.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="物品不存在")
    return item


@router.get("/lightcones/{entry_id}", response_model=LightconeDetail)
async def get_lightcone(entry_id: str) -> LightconeDetail:
    lightcone = service.get_lightcone(entry_id)
    if lightcone is None:
        raise HTTPException(status_code=404, detail="光锥不存在")
    return lightcone


@router.get("/relics/{entry_id}", response_model=RelicDetail)
async def get_relic(entry_id: str) -> RelicDetail:
    relic = service.get_relic(entry_id)
    if relic is None:
        raise HTTPException(status_code=404, detail="遗器不存在")
    return relic


@router.get("/{kind}", response_model=KnowledgeEntityListResponse)
async def list_knowledge_entities(kind: str) -> KnowledgeEntityListResponse:
    if kind not in ENTITY_KINDS:
        raise HTTPException(status_code=404, detail="知识分区不存在")
    items = service.list_entities(kind)
    return KnowledgeEntityListResponse(items=items, total=len(items))


@router.get("/{kind}/{entry_id}", response_model=KnowledgeEntityDetail)
async def get_knowledge_entity(kind: str, entry_id: str) -> KnowledgeEntityDetail:
    if kind not in ENTITY_KINDS:
        raise HTTPException(status_code=404, detail="知识分区不存在")
    entity = service.get_entity(kind, entry_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return entity
