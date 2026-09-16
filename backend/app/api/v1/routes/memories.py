from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.routes.auth import current_user
from app.db.session import get_db
from app.models.user import User, UserMemory
from app.schemas.chat import (
    MemoryCreate,
    MemoryListResponse,
    MemoryResponse,
    MemoryUpdate,
)

router = APIRouter()
MemoryType = Literal[
    "playstyle_preference",
    "resource_priority",
    "favorite_character",
    "usual_team",
    "answer_preference",
]
ALLOWED_MEMORY_TYPES = {
    "playstyle_preference",
    "resource_priority",
    "favorite_character",
    "usual_team",
    "answer_preference",
}


def _validate_type(memory_type: str) -> None:
    if memory_type not in ALLOWED_MEMORY_TYPES:
        raise HTTPException(status_code=422, detail="不支持的记忆类型")


def _owned_memory(database: Session, user_id: str, memory_id: str) -> UserMemory:
    memory = database.scalar(
        select(UserMemory).where(
            UserMemory.id == memory_id, UserMemory.user_id == user_id
        )
    )
    if memory is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return memory


@router.get("/memories", response_model=MemoryListResponse)
def list_memories(
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> MemoryListResponse:
    items = database.scalars(
        select(UserMemory)
        .where(UserMemory.user_id == user.id)
        .order_by(UserMemory.updated_at.desc())
    ).all()
    return MemoryListResponse(
        items=[MemoryResponse.model_validate(item) for item in items],
        total=len(items),
    )


@router.post(
    "/memories",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_memory(
    payload: MemoryCreate,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> MemoryResponse:
    _validate_type(payload.memory_type)
    normalized_content = payload.content.strip()
    existing = database.scalar(
        select(UserMemory).where(
            UserMemory.user_id == user.id,
            UserMemory.memory_type == payload.memory_type,
            UserMemory.content == normalized_content,
        )
    )
    if existing is not None:
        existing.is_active = True
        database.commit()
        database.refresh(existing)
        return MemoryResponse.model_validate(existing)
    memory = UserMemory(
        user_id=user.id,
        memory_type=payload.memory_type,
        content=normalized_content,
        source="user_confirmed",
        is_active=True,
    )
    database.add(memory)
    database.commit()
    database.refresh(memory)
    return MemoryResponse.model_validate(memory)


@router.patch("/memories/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: str,
    payload: MemoryUpdate,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> MemoryResponse:
    memory = _owned_memory(database, user.id, memory_id)
    if payload.memory_type is not None:
        _validate_type(payload.memory_type)
        memory.memory_type = payload.memory_type
    if payload.content is not None:
        memory.content = payload.content.strip()
    if payload.is_active is not None:
        memory.is_active = payload.is_active
    database.commit()
    database.refresh(memory)
    return MemoryResponse.model_validate(memory)


@router.delete(
    "/memories/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_memory(
    memory_id: str,
    user: User = Depends(current_user),
    database: Session = Depends(get_db),
) -> Response:
    memory = _owned_memory(database, user.id, memory_id)
    database.delete(memory)
    database.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
