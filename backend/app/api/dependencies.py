from functools import lru_cache

from app.agents.base import BaseAgent
from app.agents.fc_main_agent import FCMainAgent
from app.agents.material_query_agent import MaterialQueryAgent
from app.agents.rag_agent import RAGAgent
from app.agents.react_main_agent import ReactMainAgent
from app.agents.react_tools import (
    make_activity_strategy,
    make_catalog_search,
    make_character_build,
    make_character_materials,
    make_character_profile,
    make_custom_character_guide,
    make_custom_character_review,
    make_knowledge_search,
    make_team_recommendation,
    make_weekly_planning,
)
from app.agents.team_recommendation_agent import TeamRecommendationAgent
from app.core.config import settings
from app.db.session import SessionLocal
from app.llm.base import LLMProvider
from app.llm.providers import create_fc_llm_provider, create_llm_provider
from app.memory.repository import PgMemoryRepository
from app.rag.embeddings import RemoteBGEEmbeddingProvider
from app.rag.milvus_store import MilvusKnowledgeStore
from app.rag.rerankers import RemoteBGEReranker
from app.services.catalog_service import CatalogService


@lru_cache
def get_fast_llm_provider() -> LLMProvider | None:
    return create_llm_provider(settings, workload="fast")


@lru_cache
def get_reasoning_llm_provider() -> LLMProvider | None:
    return create_llm_provider(settings, workload="reasoning")


@lru_cache
def get_intent_llm_provider() -> LLMProvider | None:
    # 意图理解专用：更高阶思考模型（glm-4.7），不可用时工厂自动回退 pro。
    return create_llm_provider(settings, workload="intent")


def get_optional_llm_provider() -> LLMProvider | None:
    """Backward-compatible dependency for structured extraction workloads."""
    return get_fast_llm_provider()


def _list_custom_character_drafts(user_id: str) -> list[dict]:
    """聊天自查 Agent 的草稿数据通道：读取作者当前草稿版本 payload。"""
    from app.models.custom_character import (
        CustomCharacter,
        CustomCharacterVersion,
    )

    database = SessionLocal()
    try:
        characters = (
            database.query(CustomCharacter)
            .filter(CustomCharacter.author_id == user_id)
            .order_by(CustomCharacter.updated_at.desc())
            .all()
        )
        drafts: list[dict] = []
        for character in characters:
            version = (
                database.get(
                    CustomCharacterVersion,
                    character.current_draft_version_id,
                )
                if character.current_draft_version_id
                else None
            )
            if version and version.payload:
                drafts.append(
                    {
                        "character_id": str(character.id),
                        "name": str(
                            version.payload.get("name") or character.name
                        ),
                        "payload": dict(version.payload),
                    }
                )
        return drafts
    finally:
        database.close()


@lru_cache
def get_herta_main_agent() -> BaseAgent:
    """装配主 Agent；默认使用原生 FC，不可用时回退兼容 ReAct。"""
    embedding = RemoteBGEEmbeddingProvider(settings.bge_service_url)
    reranker = RemoteBGEReranker(settings.bge_service_url)
    store = MilvusKnowledgeStore(
        uri=f"http://{settings.milvus_host}:{settings.milvus_port}",
        collection_name=settings.milvus_collection,
        embedding=embedding,
        reranker=reranker,
    )
    llm = get_reasoning_llm_provider()
    rag_agent = RAGAgent(
        store=store,
        llm=llm,
        top_k=settings.rag_top_k,
        docs_root=settings.docs_root,
    )
    catalog = CatalogService(settings.docs_root)
    material_agent = MaterialQueryAgent(settings.docs_root, rag_agent)
    team_agent = TeamRecommendationAgent(settings.docs_root, reasoning_llm=llm)
    tools = [
        make_catalog_search(catalog),
        make_character_profile(catalog),
        make_character_materials(catalog, material_agent),
        make_team_recommendation(team_agent),
        make_knowledge_search(rag_agent),
        # Phase 1.3 工具补齐：5/14 → 覆盖全部可包装能力（memory/ conversation /
        # conversation_recall 由响应层与大脑直答承载，不做工具——见工作簿 1.2）
        make_character_build(settings.docs_root, rag_agent, memory_repo=PgMemoryRepository()),
        make_activity_strategy(settings.docs_root, llm),
        make_weekly_planning(),
        make_custom_character_guide(),
        make_custom_character_review(_list_custom_character_drafts, llm),
    ]
    # 主 Agent 开关：fc=现役原生 Function Calling；react=兼容 JSON-ReAct。
    # FC 客户端不可用（如 mock 或当前不支持 FC 的提供商）时自动回退 ReAct。
    if settings.main_agent_impl.strip().lower() == "fc":
        fc_llm = create_fc_llm_provider(settings)
        if fc_llm is not None:
            return FCMainAgent(tools=tools, llm=fc_llm)
    return ReactMainAgent(
        tools=tools,
        brain_fast=get_intent_llm_provider(),
        brain_deep=create_llm_provider(settings, workload="deep"),
    )
