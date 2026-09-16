from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ai_response import AIResponse


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    response: AIResponse | None = None
    created_at: datetime


class ChatMessageListResponse(BaseModel):
    conversation: ConversationResponse
    items: list[ChatMessageResponse]


class ChatJobResponse(BaseModel):
    id: str
    conversation_id: str
    status: Literal["queued", "running", "completed", "failed"]
    message: str
    response: AIResponse | None = None
    partial_answer: str = ""
    progress: dict[str, object] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class ChatJobListResponse(BaseModel):
    items: list[ChatJobResponse]
    total: int


class ChatJobEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sequence: int
    event_type: str
    agent: str | None = None
    title: str
    detail: str
    status: str
    duration_ms: int | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class MemoryCreate(BaseModel):
    memory_type: str
    content: str = Field(min_length=1, max_length=500)
    source: str | None = None


class MemoryUpdate(BaseModel):
    memory_type: str | None = None
    content: str | None = Field(default=None, min_length=1, max_length=500)
    is_active: bool | None = None


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    memory_type: str
    content: str
    source: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MemoryListResponse(BaseModel):
    items: list[MemoryResponse]
    total: int
