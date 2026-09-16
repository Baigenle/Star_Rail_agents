from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.routes.auth import current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import (
    User,
    UserCharacter,
    UserCharacterProgress,
    UserMemory,
)
from app.schemas.profile import (
    CharacterPoolResponse,
    CharacterPoolUpdate,
    FavoriteCharacterUpdate,
    CharacterProgressResponse,
    CharacterProgressUpdate,
    UserCharacterResponse,
)
from app.services.catalog_service import CatalogService
from app.services.progression_service import ProgressionService, ProgressionValidationError

router = APIRouter()
progression_service = ProgressionService(settings.docs_root)


def _catalog() -> dict[str, object]:
    return {
        character.id: character
        for character in CatalogService(settings.docs_root).list_characters()
    }


def _pool_response(database: Session, user: User) -> CharacterPoolResponse:
    catalog = _catalog()
    rows = database.scalars(
        select(UserCharacter).where(UserCharacter.user_id == user.id)
    ).all()
    rows_by_id = {row.character_id: row for row in rows}
    items: list[UserCharacterResponse] = []
    for character_id, character in catalog.items():
        row = rows_by_id.get(character_id)
        if row is None:
            continue
        items.append(
            UserCharacterResponse(
                character_id=character_id,
                name=character.name,
                rarity=character.rarity,
                path=character.path,
                element=character.element,
                image_url=character.image_url,
                level=row.level,
                eidolon=row.eidolon,
                is_favorite=row.is_favorite,
                is_built=row.is_built,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    return CharacterPoolResponse(
        items=items,
        total=len(items),
        favorites=sum(item.is_favorite for item in items),
    )


@router.get("/characters", response_model=CharacterPoolResponse)
def get_character_pool(
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> CharacterPoolResponse:
    return _pool_response(database, user)


@router.put("/characters", response_model=CharacterPoolResponse)
def replace_character_pool(
    payload: CharacterPoolUpdate,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> CharacterPoolResponse:
    catalog = _catalog()
    unknown_ids = [
        character_id
        for character_id in payload.character_ids
        if character_id not in catalog
    ]
    if unknown_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"角色档案不存在：{', '.join(unknown_ids)}",
        )

    requested_ids = set(payload.character_ids)
    existing = database.scalars(
        select(UserCharacter).where(UserCharacter.user_id == user.id)
    ).all()
    existing_by_id = {row.character_id: row for row in existing}

    for character_id, row in existing_by_id.items():
        if character_id not in requested_ids:
            database.delete(row)
    for character_id in requested_ids - existing_by_id.keys():
        database.add(UserCharacter(user_id=user.id, character_id=character_id))

    database.commit()
    return _pool_response(database, user)


@router.patch(
    "/characters/{character_id}/favorite",
    response_model=UserCharacterResponse,
)
def update_favorite_character(
    character_id: str,
    payload: FavoriteCharacterUpdate,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> UserCharacterResponse:
    row = database.scalar(
        select(UserCharacter).where(
            UserCharacter.user_id == user.id,
            UserCharacter.character_id == character_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="请先把该角色加入“我的角色”",
        )
    catalog = _catalog()
    character = catalog.get(character_id)
    if character is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色档案不存在",
        )
    row.is_favorite = payload.is_favorite
    memory_source = f"character_pool:{character_id}"
    memory = database.scalar(
        select(UserMemory).where(
            UserMemory.user_id == user.id,
            UserMemory.memory_type == "favorite_character",
            UserMemory.source == memory_source,
        )
    )
    if payload.is_favorite:
        content = f"喜欢角色：{character.name}（角色 ID：{character_id}）"
        if memory is None:
            database.add(
                UserMemory(
                    user_id=user.id,
                    memory_type="favorite_character",
                    content=content,
                    source=memory_source,
                    is_active=True,
                )
            )
        else:
            memory.content = content
            memory.is_active = True
    elif memory is not None:
        memory.is_active = False
    database.commit()
    database.refresh(row)
    item = next(
        (
            item
            for item in _pool_response(database, user).items
            if item.character_id == character_id
        ),
        None,
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色档案不存在",
        )
    return item


def _progress_response(row: UserCharacterProgress) -> CharacterProgressResponse:
    return CharacterProgressResponse(
        character_id=row.character_id,
        current_level=row.current_level,
        target_level=row.target_level,
        eidolon=row.eidolon,
        current_skills=row.current_skills,
        target_skills=row.target_skills,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get(
    "/characters/{character_id}/progression",
    response_model=CharacterProgressResponse,
)
def get_character_progress(
    character_id: str,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> CharacterProgressResponse:
    row = database.scalar(
        select(UserCharacterProgress).where(
            UserCharacterProgress.user_id == user.id,
            UserCharacterProgress.character_id == character_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="尚未保存该角色的养成计划"
        )
    return _progress_response(row)


@router.put(
    "/characters/{character_id}/progression",
    response_model=CharacterProgressResponse,
)
def save_character_progress(
    character_id: str,
    payload: CharacterProgressUpdate,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> CharacterProgressResponse:
    owned = database.scalar(
        select(UserCharacter).where(
            UserCharacter.user_id == user.id,
            UserCharacter.character_id == character_id,
        )
    )
    if owned is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="请先把该角色加入“我的角色”再保存练度",
        )
    try:
        tracks = progression_service.track_definitions(character_id)
        for key, current in payload.current_skills.items():
            if key not in tracks or not 1 <= current <= int(tracks[key]["max_level"]):
                raise ProgressionValidationError(f"无效的当前技能等级：{key}")
            target = payload.target_skills[key]
            if not current <= target <= int(tracks[key]["max_level"]):
                raise ProgressionValidationError(f"无效的目标技能等级：{key}")
    except ProgressionValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    row = database.scalar(
        select(UserCharacterProgress).where(
            UserCharacterProgress.user_id == user.id,
            UserCharacterProgress.character_id == character_id,
        )
    )
    if row is None:
        row = UserCharacterProgress(
            user_id=user.id, character_id=character_id, **payload.model_dump()
        )
        database.add(row)
    else:
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
    owned.level = payload.current_level
    owned.eidolon = payload.eidolon
    owned.is_built = True
    database.commit()
    database.refresh(row)
    return _progress_response(row)
