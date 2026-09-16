from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: UUID | None = None
    history: list[ChatHistoryMessage] = Field(
        default_factory=list, max_length=12
    )


class Citation(BaseModel):
    id: str
    title: str
    source: str
    excerpt: str = ""
    document_id: str | None = None
    chunk_id: str | None = None
    game_version: str | None = None
    updated_at: str | None = None
    relevance_score: float | None = Field(default=None, ge=0, le=1)
    image_url: str | None = None
    entity_url: str | None = None


class Claim(BaseModel):
    statement: str
    confidence: float = Field(ge=0, le=1)
    citation_ids: list[str] = Field(default_factory=list)
    claim_type: Literal["fact", "interpretation"] = "fact"
    evidence_quotes: list[str] = Field(default_factory=list)


class ValidationReport(BaseModel):
    status: Literal["verified", "partially_verified", "unverified", "conflicted"]
    method: str
    evidence_count: int = Field(ge=0)
    notes: list[str] = Field(default_factory=list)


class FilteringReport(BaseModel):
    passed: bool
    removed_claims: int = Field(ge=0)
    rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QueryStep(BaseModel):
    id: str
    name: str
    status: Literal["completed", "fallback", "failed"]
    detail: str
    duration_ms: int | None = Field(default=None, ge=0)


class MemorySuggestion(BaseModel):
    memory_type: Literal[
        "playstyle_preference",
        "resource_priority",
        "favorite_character",
        "usual_team",
        "answer_preference",
    ]
    content: str = Field(min_length=1, max_length=500)
    reason: str = Field(default="用户在本轮对话中明确表达了可长期使用的偏好")


class FavoriteCharacterSuggestion(BaseModel):
    character_id: str
    name: str
    is_owned: bool
    prompt: str


class AgentAction(BaseModel):
    """主 Agent 生成的页面动作：用户点击后前端执行跳转或预填。"""

    action_type: Literal["navigate", "prefill"] = "navigate"
    title: str = Field(min_length=1, max_length=40)
    target_url: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=200)
    params: dict[str, str] = Field(default_factory=dict)


class RelatedEntity(BaseModel):
    entity_type: Literal[
        "character", "item", "lightcone", "relic", "story", "activity"
    ]
    entity_id: str
    name: str
    entity_url: str
    image_url: str | None = None


class AIResponse(BaseModel):
    response_id: UUID = Field(default_factory=uuid4)
    agent: str
    protocol: Literal["claim-citation-validation-filtering"] = "claim-citation-validation-filtering"
    answer: str = ""
    claims: list[Claim]
    citations: list[Citation]
    validation: ValidationReport
    filtering: FilteringReport
    query_steps: list[QueryStep] = Field(default_factory=list)
    invoked_agents: list[str] = Field(default_factory=list)
    conversation_id: UUID | None = None
    memory_suggestions: list[MemorySuggestion] = Field(default_factory=list)
    favorite_character_suggestions: list[FavoriteCharacterSuggestion] = Field(
        default_factory=list
    )
    related_entities: list[RelatedEntity] = Field(default_factory=list)
    actions: list[AgentAction] = Field(default_factory=list)
    # 衍生问题建议：前端渲染为可点击按钮，点击后直接作为新问题发送。
    follow_up_questions: list[str] = Field(default_factory=list, max_length=3)
