from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import settings
from app.schemas.story import StoryDetail, StoryListResponse, StoryScene
from app.services.story_catalog_service import StoryCatalogService


router = APIRouter()


@lru_cache(maxsize=1)
def get_story_catalog() -> StoryCatalogService:
    return StoryCatalogService(settings.docs_root / "data_character_story")


@router.get("/stories", response_model=StoryListResponse)
def list_stories(
    q: str = Query(default="", max_length=100),
    version: str = Query(default="", max_length=16),
    world: str = Query(default="", max_length=80),
    mission_type: str = Query(default="", max_length=40),
    series: str = Query(default="", max_length=120),
    character: str = Query(default="", max_length=48),
    catalog: StoryCatalogService = Depends(get_story_catalog),
) -> StoryListResponse:
    return StoryListResponse.model_validate(
        catalog.list(
            q=q,
            version=version,
            world=world,
            mission_type=mission_type,
            series=series,
            character=character,
        )
    )


@router.get("/stories/{mission_id}", response_model=StoryDetail)
def get_story(
    mission_id: str,
    catalog: StoryCatalogService = Depends(get_story_catalog),
) -> StoryDetail:
    result = catalog.detail(mission_id)
    if result is None:
        raise HTTPException(status_code=404, detail="剧情任务不存在")
    result["scene_count"] = len(result["scenes"])
    return StoryDetail.model_validate(result)


@router.get(
    "/stories/{mission_id}/scenes/{chunk_id}",
    response_model=StoryScene,
)
def get_story_scene(
    mission_id: str,
    chunk_id: str,
    catalog: StoryCatalogService = Depends(get_story_catalog),
) -> StoryScene:
    result = catalog.scene(mission_id, chunk_id)
    if result is None:
        raise HTTPException(status_code=404, detail="剧情场景不存在")
    return StoryScene.model_validate(result)
