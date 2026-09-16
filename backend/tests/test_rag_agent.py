import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from app.agents.base import AgentContext
from app.agents.answer_review_agent import AnswerReviewAgent
from app.agents.herta_main_agent import HertaMainAgent
from app.agents.intent_analyzer import IntentSubtask
from app.agents.rag_agent import DraftClaim, RAGAgent
from app.agents.router_agent import RouterAgent
from app.llm.base import LLMMessage, LLMProvider
from app.schemas.ai_response import (
    AIResponse,
    Citation,
    Claim,
    FilteringReport,
    ValidationReport,
)


class FakeStore:
    def search(self, _query: str, _limit: int, _entry_type: str | None):
        return [
            {
                "id": "chunk-1",
                "distance": 0.88,
                "vector_score": 0.88,
                "model_rerank_score": 0.96,
                "entity": {
                    "chunk_id": "chunk-1",
                    "entry_id": "1308",
                    "entry_type": "hsr_character",
                    "title": "黄泉",
                    "section": "基本资料",
                    "content": "黄泉是五星雷属性虚无命途角色。",
                    "data_version": "1.0",
                    "source_page": "https://example.com/character/1308",
                    "generated_at": "2026-01-01T00:00:00+08:00",
                },
            }
        ]


class RecordingLimitStore(FakeStore):
    def __init__(self) -> None:
        self.limits: list[int] = []

    def search(self, query: str, limit: int, entry_type: str | None):
        self.limits.append(limit)
        return super().search(query, limit, entry_type)


class FailIfSearchedStore:
    def search(self, _query: str, _limit: int, _entry_type: str | None):
        raise AssertionError("结构化技能查询不应调用向量检索")


class FakeLLM(LLMProvider):
    name = "fake"

    async def complete(self, _messages: list[LLMMessage]) -> str:
        return """{
          "answer": "黄泉是五星雷属性虚无命途角色。[C1] 这是一条没有引用的扩展判断。",
          "claims": [
            {"statement":"黄泉是五星雷属性虚无命途角色。","confidence":0.95,"citation_ids":["C1"]},
            {"statement":"没有来源的主张。","confidence":0.9,"citation_ids":["C99"]},
            {"statement":"低置信主张。","confidence":0.2,"citation_ids":["C1"]}
          ],
          "warnings": []
        }"""

    async def stream(self, _messages: list[LLMMessage]) -> AsyncIterator[str]:
        if False:
            yield ""


class FakeIntentLLM(LLMProvider):
    name = "deepseek-pro-test"

    def __init__(self) -> None:
        self.messages: list[LLMMessage] = []

    async def complete(self, messages: list[LLMMessage]) -> str:
        self.messages = messages
        return """{
          "intent": "story_analysis",
          "standalone_query": "大黑塔的角色故事",
          "confidence": 0.97,
          "needs_retrieval": true,
          "reason": "结合上一轮中的角色名消解了代词“她”",
          "answer_depth": "detailed",
          "clarification_question": null
        }"""

    async def stream(self, _messages: list[LLMMessage]) -> AsyncIterator[str]:
        if False:
            yield ""


class EntityCorrectingIntentLLM(FakeIntentLLM):
    async def complete(self, messages: list[LLMMessage]) -> str:
        self.messages = messages
        return """{
          "intent": "character_build",
          "standalone_query": "我要养花火怎么养",
          "confidence": 0.96,
          "needs_retrieval": true,
          "reason": "识别为角色养成"
        }"""


class CompoundIntentLLM(FakeIntentLLM):
    async def complete(self, messages: list[LLMMessage]) -> str:
        self.messages = messages
        return """{
          "intent": "knowledge_qa",
          "standalone_query": "流萤是谁？她的技能是什么？",
          "confidence": 0.98,
          "needs_retrieval": true,
          "reason": "用户同时询问角色身份和技能",
          "answer_depth": "detailed",
          "task_mode": "single_character_fact",
          "subtasks": [
            {
              "intent": "knowledge_qa",
              "standalone_query": "流萤是谁？",
              "task_mode": "single_character_fact",
              "answer_depth": "standard",
              "needs_retrieval": true
            },
            {
              "intent": "knowledge_qa",
              "standalone_query": "流萤的技能是什么？",
              "task_mode": "single_character_fact",
              "answer_depth": "detailed",
              "needs_retrieval": true
            }
          ]
        }"""


class RejectIrrelevantAnswerLLM(FakeIntentLLM):
    async def complete(self, messages: list[LLMMessage]) -> str:
        self.messages = messages
        return """{
          "items": [
            {
              "index": 1,
              "relevant": false,
              "reason": "答案只引用相同词的剧情台词，没有解释物品定义"
            }
          ]
        }"""


class MixedIntentLLM(FakeIntentLLM):
    async def complete(self, messages: list[LLMMessage]) -> str:
        self.messages = messages
        return """{
          "intent": "knowledge_qa",
          "standalone_query": "介绍流萤，并告诉我怎么养她",
          "confidence": 0.98,
          "needs_retrieval": true,
          "reason": "同时包含角色事实与养成任务",
          "answer_depth": "detailed",
          "task_mode": "single_character_fact",
          "subtasks": [
            {
              "intent": "knowledge_qa",
              "standalone_query": "介绍流萤",
              "task_mode": "single_character_fact",
              "answer_depth": "standard",
              "needs_retrieval": true
            },
            {
              "intent": "character_build",
              "standalone_query": "流萤怎么养？",
              "task_mode": "build_planning",
              "answer_depth": "detailed",
              "needs_retrieval": true
            }
          ]
        }"""


class CompoundRAGRecorder:
    name = "rag_agent"
    docs_root = None

    def __init__(self) -> None:
        self.messages: list[str] = []

    async def run(self, context: AgentContext) -> AIResponse:
        self.messages.append(context.message)
        if "技能" in context.message:
            statement = "流萤的技能包含普攻、战技、终结技、天赋与秘技。"
            title = "流萤 · 技能"
        else:
            statement = "流萤是五星火属性毁灭命途角色。"
            title = "流萤 · 基本资料"
        return AIResponse(
            agent=self.name,
            answer=f"{statement} [C1]",
            claims=[
                Claim(
                    statement=statement,
                    confidence=0.9,
                    citation_ids=["C1"],
                )
            ],
            citations=[
                Citation(
                    id="C1",
                    title=title,
                    source="docs/character/firefly.md",
                    excerpt=statement,
                )
            ],
            validation=ValidationReport(
                status="verified", method="test", evidence_count=1
            ),
            filtering=FilteringReport(passed=True, removed_claims=0),
        )


class BuildAgentRecorder(CompoundRAGRecorder):
    name = "character_build_agent"

    async def run(self, context: AgentContext) -> AIResponse:
        self.messages.append(context.message)
        statement = "流萤养成需要分别规划等级、技能、光锥与遗器。"
        return AIResponse(
            agent=self.name,
            answer=f"{statement} [C1]",
            claims=[
                Claim(
                    statement=statement,
                    confidence=0.9,
                    citation_ids=["C1"],
                )
            ],
            citations=[
                Citation(
                    id="C1",
                    title="流萤 · 养成",
                    source="docs/character/firefly-build.md",
                    excerpt=statement,
                )
            ],
            validation=ValidationReport(
                status="verified", method="test", evidence_count=1
            ),
            filtering=FilteringReport(passed=True, removed_claims=0),
        )


def test_rag_agent_filters_unsupported_claims() -> None:
    agent = RAGAgent(store=FakeStore(), llm=FakeLLM(), top_k=5)  # type: ignore[arg-type]
    response = asyncio.run(agent.run(AgentContext(user_id=None, message="黄泉是什么属性？")))

    assert response.agent == "rag_agent"
    assert response.answer
    assert "没有引用" not in response.answer
    assert [step.id for step in response.query_steps] == ["retrieval", "generation", "validation"]
    assert len(response.claims) == 1
    assert response.claims[0].citation_ids == ["C1"]
    assert response.citations[0].title == "黄泉 · 基本资料"
    assert response.filtering.removed_claims == 2
    assert response.validation.status == "partially_verified"


def test_detailed_character_skill_question_retrieves_more_evidence() -> None:
    store = RecordingLimitStore()
    agent = RAGAgent(store=store, llm=None, top_k=5)  # type: ignore[arg-type]

    asyncio.run(
        agent.run(
            AgentContext(
                user_id=None,
                message="详细介绍流萤的全部技能",
                intent="knowledge_qa",
                intent_metadata={
                    "answer_depth": "detailed",
                    "task_mode": "single_character_fact",
                },
            )
        )
    )

    assert store.limits == [8]


def test_character_skill_question_uses_complete_structured_catalog() -> None:
    docs_root = Path(__file__).resolve().parents[2] / "docs"
    agent = RAGAgent(
        store=FailIfSearchedStore(),
        llm=None,
        top_k=5,
        docs_root=docs_root,
    )  # type: ignore[arg-type]

    response = asyncio.run(
        agent.run(
            AgentContext(
                user_id=None,
                message="流萤的技能是什么？",
                intent="knowledge_qa",
                intent_metadata={
                    "answer_depth": "detailed",
                    "task_mode": "single_character_fact",
                },
                entities={
                    "mentioned_characters": [
                        {"character_id": "1310", "name": "流萤"}
                    ],
                    "mentioned_catalog_entities": [
                        {
                            "entity_type": "hsr_character",
                            "entity_id": "1310",
                            "character_id": "1310",
                            "name": "流萤",
                        }
                    ],
                },
            )
        )
    )

    assert "普攻" in response.answer
    assert "战技" in response.answer
    assert "终结技" in response.answer
    assert "天赋" in response.answer
    assert "秘技" in response.answer
    assert "simple_desc" not in response.answer
    assert response.agent == "structured_character_agent"
    assert len(response.citations) >= 5
    assert response.query_steps[0].id == "structured_character_skills"


def test_character_identity_question_uses_complete_structured_profile() -> None:
    docs_root = Path(__file__).resolve().parents[2] / "docs"
    agent = RAGAgent(
        store=FailIfSearchedStore(),
        llm=None,
        top_k=5,
        docs_root=docs_root,
    )  # type: ignore[arg-type]

    response = asyncio.run(
        agent.run(
            AgentContext(
                user_id=None,
                message="流萤是谁？",
                intent="knowledge_qa",
                intent_metadata={"task_mode": "single_character_fact"},
                entities={
                    "mentioned_characters": [
                        {"character_id": "1310", "name": "流萤"}
                    ],
                    "mentioned_catalog_entities": [
                        {
                            "entity_type": "hsr_character",
                            "entity_id": "1310",
                            "character_id": "1310",
                            "name": "流萤",
                        }
                    ],
                },
            )
        )
    )

    assert "5星火属性毁灭命途角色" in response.answer
    assert "星核猎手成员" in response.answer
    assert response.agent == "structured_character_agent"
    assert response.query_steps[0].id == "structured_character_profile"


def test_story_citation_removes_crawler_metadata() -> None:
    agent = RAGAgent(store=FakeStore(), llm=None, top_k=5)  # type: ignore[arg-type]
    citations = agent._citations(
        [
            {
                "model_rerank_score": 0.96,
                "entity": {
                    "chunk_id": "story-scene-1",
                    "entry_id": "story-mission-1",
                    "entry_type": "hsr_story",
                    "title": "小城畸人",
                    "section": "与流萤对话（1/2）",
                    "content": (
                        "角色/条目：小城畸人\n章节：概览\n"
                        "【当前地点】匹诺康尼-流梦礁\n"
                        "【出场角色】流萤、MediaWiki、刃、瓦尔特\n"
                        "【剧情正文】\n流萤:很高兴能再次与你同行。\n"
                        "MediaWiki:PlotOptions"
                    ),
                    "data_version": "2.2",
                    "source_page": "https://example.com/story",
                },
            }
        ]
    )

    assert len(citations) == 1
    assert citations[0].title == "小城畸人 · 与流萤对话（1/2）"
    assert "MediaWiki" not in citations[0].excerpt
    assert "角色/条目" not in citations[0].excerpt
    assert "【当前地点】" not in citations[0].excerpt
    assert "【出场角色】" not in citations[0].excerpt
    assert "流萤:很高兴能再次与你同行。" in citations[0].excerpt


def test_router_registers_dedicated_story_analysis_agent() -> None:
    rag = RAGAgent(store=FakeStore(), llm=FakeLLM(), top_k=5)  # type: ignore[arg-type]
    router = RouterAgent(rag)

    assert router.agent_for_intent("story_analysis").name == "story_analysis_agent"


def test_story_interpretation_claim_requires_verbatim_evidence_quote() -> None:
    citations = [
        Citation(
            id="C1",
            title="测试剧情",
            source="https://example.com/story",
            excerpt="角色拒绝撤退，并表示自己必须保护仍在城中的居民。",
        )
    ]
    drafts = [
        DraftClaim(
            statement="这一选择体现了角色把居民安全置于自身风险之上。",
            claim_type="interpretation",
            confidence=0.86,
            citation_ids=["C1"],
            evidence_quotes=["必须保护仍在城中的居民"],
        ),
        DraftClaim(
            statement="没有文本依据的动机判断。",
            claim_type="interpretation",
            confidence=0.9,
            citation_ids=["C1"],
            evidence_quotes=["为了获得个人利益"],
        ),
    ]

    claims, removed, _ = RAGAgent._filter_claims(drafts, citations)

    assert len(claims) == 1
    assert claims[0].claim_type == "interpretation"
    assert claims[0].confidence == 0.8
    assert removed == 1
    assert RAGAgent._claims_answer(claims).startswith("据文献可以推断：")


class StoryDomainStore:
    def __init__(self) -> None:
        self.entry_types: list[str | None] = []

    def search(self, _query: str, _limit: int, entry_type: str | None):
        self.entry_types.append(entry_type)
        if entry_type == "hsr_story":
            return [
                {
                    "model_rerank_score": 0.91,
                    "entity": {
                        "chunk_id": "story-domain-1",
                        "entry_id": "mission-1",
                        "entry_type": "hsr_story",
                        "title": "测试主线",
                        "section": "冲突发生",
                        "content": "角色拒绝撤退，并表示自己必须保护仍在城中的居民。",
                        "data_version": "2.0",
                        "source_page": "https://example.com/story",
                        "generated_at": "",
                    },
                }
            ]
        if entry_type == "hsr_lore":
            return [
                {
                    "model_rerank_score": 0.94,
                    "entity": {
                        "chunk_id": "lore-domain-1",
                        "entry_id": "lore-1",
                        "entry_type": "hsr_lore",
                        "title": "某阵营",
                        "section": "理念",
                        "content": "该阵营认为保护文明延续比短期胜利更重要。",
                        "data_version": "revision-42",
                        "source_page": "https://example.com/lore",
                        "generated_at": "",
                    },
                }
            ]
        return []


def test_story_analysis_searches_story_and_lore_domains() -> None:
    store = StoryDomainStore()
    agent = RAGAgent(store=store, llm=None, top_k=5)  # type: ignore[arg-type]

    response = asyncio.run(
        agent.run(
            AgentContext(
                user_id=None,
                message="结合主线剧情解释这个阵营为什么保护居民",
                intent="story_analysis",
                intent_metadata={"answer_depth": "detailed"},
            )
        )
    )

    assert set(store.entry_types) == {"hsr_story", "hsr_lore"}
    assert {citation.document_id for citation in response.citations} == {
        "mission-1",
        "lore-1",
    }


class CharacterRelationshipStore:
    def __init__(self, *, include_character_profiles: bool = True) -> None:
        self.include_character_profiles = include_character_profiles
        self.entry_types: list[str | None] = []

    def search(self, _query: str, _limit: int, entry_type: str | None):
        self.entry_types.append(entry_type)
        if entry_type == "hsr_story":
            return [
                {
                    "model_rerank_score": 0.99,
                    "entity": {
                        "chunk_id": "unrelated-story",
                        "entry_id": "mission-unrelated",
                        "entry_type": "hsr_story",
                        "title": "初日啊，逐退群星与残月",
                        "section": "错误候选",
                        "characters": ["大黑塔", "来古士"],
                        "content": (
                            "【出场角色】大黑塔、来古士\n"
                            "【剧情正文】小皇冠拒绝了接管律法的诉求。"
                        ),
                        "source_page": "https://example.com/unrelated",
                    },
                }
            ]
        if entry_type == "hsr_character" and self.include_character_profiles:
            return [
                {
                    "model_rerank_score": 0.98,
                    "entity": {
                        "chunk_id": "character-1401-skill",
                        "entry_id": "1401",
                        "entry_type": "hsr_character",
                        "title": "大黑塔",
                        "section": "技能",
                        "content": "攻击敌人，进入战斗后削弱目标韧性。",
                        "source_page": "https://example.com/character/1401",
                    },
                },
                {
                    "model_rerank_score": 0.91,
                    "entity": {
                        "chunk_id": "character-1401",
                        "entry_id": "1401",
                        "entry_type": "hsr_character",
                        "title": "大黑塔",
                        "section": "角色故事",
                        "content": (
                            "因返老还童，外貌永葆全盛时期的少女青春。"
                            "厌恶闲人琐事，杂事通常交由人偶完成。"
                        ),
                        "source_page": "https://example.com/character/1401",
                    },
                },
                {
                    "model_rerank_score": 0.90,
                    "entity": {
                        "chunk_id": "character-1013",
                        "entry_id": "1013",
                        "entry_type": "hsr_character",
                        "title": "黑塔",
                        "section": "角色故事",
                        "content": (
                            "平时以远程操纵的人偶形态登场："
                            "“跟我小时候比，勉强七分相似吧。”——黑塔本人。"
                        ),
                        "source_page": "https://example.com/character/1013",
                    },
                },
            ]
        return []


def _character_relationship_context() -> AgentContext:
    return AgentContext(
        user_id=None,
        message="大黑塔和小黑塔是什么关系",
        intent="story_analysis",
        intent_metadata={"task_mode": "character_relationship"},
        entities={
            "mentioned_characters": [
                {"character_id": "1401", "name": "大黑塔"},
                {"character_id": "1013", "name": "黑塔"},
            ]
        },
    )


def test_character_relationship_requires_evidence_for_all_characters() -> None:
    store = CharacterRelationshipStore()
    agent = RAGAgent(store=store, llm=None, top_k=5)  # type: ignore[arg-type]

    response = asyncio.run(agent.run(_character_relationship_context()))

    assert "hsr_character" in store.entry_types
    assert "hsr_story" in store.entry_types
    assert {citation.document_id for citation in response.citations} == {
        "1401",
        "1013",
    }
    assert "小皇冠" not in response.answer
    assert "来古士" not in response.answer
    assert all("技能" not in citation.title for citation in response.citations)


def test_character_relationship_rejects_unrelated_single_character_story() -> None:
    store = CharacterRelationshipStore(include_character_profiles=False)
    agent = RAGAgent(store=store, llm=None, top_k=5)  # type: ignore[arg-type]

    response = asyncio.run(agent.run(_character_relationship_context()))

    assert response.citations == []
    assert response.validation.status == "unverified"
    assert "大黑塔" in response.answer
    assert "黑塔" in response.answer
    assert "小皇冠" not in response.answer


class CitationOnlyHallucinationLLM(LLMProvider):
    name = "citation-only-hallucination"

    async def complete(self, _messages: list[LLMMessage]) -> str:
        return """{
          "answer": "黄泉是冰属性角色。[C1]",
          "claims": [
            {"statement":"黄泉是冰属性角色。","confidence":0.99,"citation_ids":["C1"]}
          ],
          "warnings": []
        }"""

    async def stream(self, _messages: list[LLMMessage]) -> AsyncIterator[str]:
        if False:
            yield ""


def test_rag_agent_rejects_claim_not_present_in_cited_evidence() -> None:
    agent = RAGAgent(
        store=FakeStore(), llm=CitationOnlyHallucinationLLM(), top_k=5
    )  # type: ignore[arg-type]
    response = asyncio.run(
        agent.run(AgentContext(user_id=None, message="黄泉是什么属性？"))
    )

    assert "冰属性" not in response.answer
    assert "雷属性虚无命途" in response.answer
    assert any("证据原文" in warning for warning in response.filtering.warnings)


def test_router_classifies_business_intents() -> None:
    assert RouterAgent.classify_intent("帮我推荐黄泉配队") == "team_recommendation"
    assert RouterAgent.classify_intent("末日兽是什么敌人") == "knowledge_qa"
    assert RouterAgent.classify_intent("你好，黑塔") == "conversation"
    assert RouterAgent.classify_intent("帮我做本周体力规划") == "weekly_plan"
    assert RouterAgent.classify_intent("我们刚才聊了什么") == "conversation_recall"
    assert RouterAgent.classify_intent("大黑塔和黑塔是什么关系") == "story_analysis"
    assert RouterAgent.classify_intent("大黑塔和黑塔一起怎么养") == "character_build"
    assert RouterAgent.classify_intent("大黑塔和黑塔可以一起配队吗") == "team_recommendation"


def test_exact_item_entity_restricts_rag_to_item_domain() -> None:
    context = AgentContext(
        user_id=None,
        message="星琼是什么？",
        intent="knowledge_qa",
        entities={
            "mentioned_catalog_entities": [
                {
                    "entity_type": "hsr_item",
                    "entity_id": "1",
                    "name": "星琼",
                }
            ]
        },
    )

    assert RAGAgent._entry_types(context) == ["hsr_item"]


def test_ambiguous_xingqiong_term_asks_for_clarification_without_rag() -> None:
    rag = FakeRAGRecorder()
    router = RouterAgent(rag)  # type: ignore[arg-type]

    response = asyncio.run(
        router.run(AgentContext(user_id=None, message="星穹是什么？"))
    )

    assert response.agent == "conversation_agent"
    assert "星琼" in response.answer
    assert "星穹列车" in response.answer
    assert rag.received_message == ""


def test_assistant_identity_comparison_does_not_call_rag() -> None:
    rag = FakeRAGRecorder()
    router = RouterAgent(rag)  # type: ignore[arg-type]
    context = AgentContext(
        user_id=None,
        message="你是大黑塔还是小黑塔",
        entities={
            "mentioned_characters": [
                {"character_id": "1401", "name": "大黑塔"},
                {"character_id": "1013", "name": "黑塔"},
            ]
        },
    )

    response = asyncio.run(router.run(context))

    assert context.intent == "conversation"
    assert context.intent_metadata["task_mode"] == "assistant_identity"
    assert response.agent == "conversation_agent"
    assert "黑塔主 Agent" in response.answer
    assert rag.received_message == ""


def test_router_uses_pro_model_and_history_to_resolve_follow_up() -> None:
    llm = FakeIntentLLM()
    rag = FakeRAGRecorder()
    router = RouterAgent(rag, intent_llm=llm)  # type: ignore[arg-type]
    context = AgentContext(
        user_id="user-1",
        message="那她的故事呢？",
        conversation_history=[
            {"role": "user", "content": "我想了解大黑塔"},
            {"role": "assistant", "content": "你想了解她的哪一部分？"},
        ],
    )

    response = asyncio.run(router.run(context))

    assert rag.received_message == "大黑塔的角色故事"
    assert context.intent == "story_analysis"
    assert context.intent_metadata["answer_depth"] == "detailed"
    assert response.query_steps[0].status == "completed"
    assert "0.97" in response.query_steps[0].detail
    assert "我想了解大黑塔" in llm.messages[-1].content


def test_conversation_recall_reads_history_without_calling_rag() -> None:
    rag = FakeRAGRecorder()
    router = RouterAgent(rag)  # type: ignore[arg-type]

    response = asyncio.run(
        router.run(
            AgentContext(
                user_id="user-1",
                message="我们刚才聊了什么？",
                conversation_history=[
                    {"role": "user", "content": "我想了解大黑塔"},
                    {"role": "assistant", "content": "你想了解哪一部分？"},
                ],
            )
        )
    )

    assert response.agent == "conversation_agent"
    assert "我想了解大黑塔" in response.answer
    assert rag.received_message == ""


def test_intent_model_cannot_rename_explicit_catalog_character() -> None:
    llm = EntityCorrectingIntentLLM()
    rag = FakeRAGRecorder()
    router = RouterAgent(rag, intent_llm=llm)  # type: ignore[arg-type]
    context = AgentContext(
        user_id=None,
        message="我要养火花怎么养",
        entities={
            "mentioned_characters": [
                {"character_id": "1501", "name": "火花"}
            ]
        },
    )

    asyncio.run(router.run(context))

    assert rag.received_message == "我要养火花怎么养"


def test_router_decomposes_compound_question_and_merges_all_answers() -> None:
    llm = CompoundIntentLLM()
    rag = CompoundRAGRecorder()
    router = RouterAgent(rag, intent_llm=llm)  # type: ignore[arg-type]
    context = AgentContext(
        user_id=None,
        message="流萤是谁？她的技能是什么？",
        entities={
            "mentioned_characters": [
                {"character_id": "1310", "name": "流萤"}
            ]
        },
    )

    response = asyncio.run(router.run(context))

    assert rag.messages == ["流萤是谁？", "流萤的技能是什么？"]
    assert "流萤是谁？" in response.answer
    assert "流萤的技能是什么？" in response.answer
    assert "五星火属性毁灭命途角色" in response.answer
    assert "普攻、战技、终结技、天赋与秘技" in response.answer
    assert [citation.id for citation in response.citations] == ["C1", "C2"]
    assert response.claims[1].citation_ids == ["C2"]
    assert "answer_review_agent" in response.invoked_agents


def test_router_deterministically_decomposes_identity_and_skill_question() -> None:
    rag = CompoundRAGRecorder()
    router = RouterAgent(rag)  # type: ignore[arg-type]
    context = AgentContext(
        user_id=None,
        message="流萤是谁？她的技能是什么？",
        entities={
            "mentioned_characters": [
                {"character_id": "1310", "name": "流萤"}
            ]
        },
    )

    response = asyncio.run(router.run(context))

    assert rag.messages == ["流萤是谁？", "流萤的技能是什么？"]
    assert "流萤是谁？" in response.answer
    assert "流萤的技能是什么？" in response.answer


def test_final_answer_review_filters_semantically_irrelevant_evidence() -> None:
    response = AIResponse(
        agent="rag_agent",
        answer="角色在剧情中说自己看到了星琼。[C1]",
        claims=[
            Claim(
                statement="角色在剧情中说自己看到了星琼。",
                confidence=0.9,
                citation_ids=["C1"],
            )
        ],
        citations=[
            Citation(
                id="C1",
                title="某段剧情",
                source="docs/story.md",
                excerpt="角色在剧情中说自己看到了星琼。",
            )
        ],
        validation=ValidationReport(
            status="verified", method="test", evidence_count=1
        ),
        filtering=FilteringReport(passed=True, removed_claims=0),
    )
    reviewer = AnswerReviewAgent(RejectIrrelevantAnswerLLM())

    reviewed = asyncio.run(
        reviewer.review_single(
            "星琼是什么？",
            IntentSubtask(
                intent="knowledge_qa",
                standalone_query="星琼是什么？",
                task_mode="item_fact",
            ),
            response,
        )
    )

    assert reviewed.claims == []
    assert reviewed.citations == []
    assert reviewed.validation.status == "unverified"
    assert "不直接相关" in reviewed.answer
    assert reviewer.name in reviewed.invoked_agents


def test_compound_question_can_invoke_different_specialized_agents() -> None:
    rag = CompoundRAGRecorder()
    build = BuildAgentRecorder()
    router = RouterAgent(
        rag,
        intent_llm=MixedIntentLLM(),
    )  # type: ignore[arg-type]
    router.registry.register("character_build", build)

    response = asyncio.run(
        router.run(
            AgentContext(
                user_id=None,
                message="介绍流萤，并告诉我怎么养她",
                entities={
                    "mentioned_characters": [
                        {"character_id": "1310", "name": "流萤"}
                    ]
                },
            )
        )
    )

    assert rag.messages == ["介绍流萤"]
    assert build.messages == ["流萤怎么养？"]
    assert "rag_agent" in response.invoked_agents
    assert "character_build_agent" in response.invoked_agents
    assert "介绍流萤" in response.answer
    assert "流萤怎么养" in response.answer


class FakeRAGRecorder:
    name = "rag_agent"
    docs_root = None

    def __init__(self) -> None:
        self.received_message = ""

    async def run(self, context: AgentContext) -> AIResponse:
        self.received_message = context.message
        return AIResponse(
            agent=self.name,
            answer="已根据上下文处理。",
            claims=[],
            citations=[],
            validation=ValidationReport(
                status="unverified", method="test", evidence_count=0
            ),
            filtering=FilteringReport(passed=False, removed_claims=0),
        )


class FakeRouter:
    async def run(self, _context: AgentContext):
        return await RAGAgent(store=FakeStore(), llm=FakeLLM(), top_k=5).run(_context)  # type: ignore[arg-type]


class FakePersonaLLM(LLMProvider):
    name = "deepseek-pro-persona-test"

    async def complete(self, _messages: list[LLMMessage]) -> str:
        return '{"opening":"这才像个值得查的问题。本天才已经把证据排好了。","closing":""}'

    async def stream(self, _messages: list[LLMMessage]) -> AsyncIterator[str]:
        if False:
            yield ""


def test_herta_main_agent_keeps_grounded_sub_agent_facts_unchanged() -> None:
    agent = HertaMainAgent(FakeRouter(), persona_llm=FakePersonaLLM())  # type: ignore[arg-type]
    response = asyncio.run(agent.run(AgentContext(user_id=None, message="黄泉是什么属性？")))

    assert response.agent == "herta_main_agent"
    # 子 Agent 仅部分验证时不采用模型生成的自信开场，避免掩盖证据缺口。
    assert "本天才已经把证据排好了" not in response.answer
    assert "黄泉是五星雷属性虚无命途角色" in response.answer
    assert "冰属性" not in response.answer
    assert "[C1]" in response.answer
    assert [step.id for step in response.query_steps][-1] == "herta_response"


def test_herta_main_agent_appends_non_blocking_clarification() -> None:
    context = AgentContext(
        user_id=None,
        message="讲讲大黑塔",
        intent_metadata={
            "clarification_question": "你是想看完整角色故事，还是只要背景概括？"
        },
    )
    response = asyncio.run(
        HertaMainAgent(FakeRouter(), persona_llm=FakePersonaLLM()).run(context)  # type: ignore[arg-type]
    )

    assert response.answer.endswith(
        "你是想看完整角色故事，还是只要背景概括？"
    )


class BrokenLLM(LLMProvider):
    name = "broken"

    async def complete(self, _messages: list[LLMMessage]) -> str:
        raise ValueError("invalid response")

    async def stream(self, _messages: list[LLMMessage]) -> AsyncIterator[str]:
        if False:
            yield ""


class StoryStore:
    def __init__(self) -> None:
        self.limit = 0
        self.query = ""

    def search(self, _query: str, _limit: int, _entry_type: str | None):
        self.query = _query
        self.limit = _limit
        return [
            {
                "vector_score": 0.9,
                "model_rerank_score": 0.95,
                "entity": {
                    "chunk_id": "story-1",
                    "entry_id": "1401",
                    "entry_type": "hsr_character",
                    "title": "大黑塔",
                    "section": "角色故事",
                    "content": (
                        "角色/条目：大黑塔 章节：角色故事。"
                        "大黑塔是天才俱乐部第83席，长期探索宇宙终极奥秘。"
                        "她把许多琐事交给人偶处理，自己专注于尚未解开的疑问。"
                        "这段后续内容故意写得非常长，不应该被截断成半句话"
                    ),
                    "data_version": "1.0",
                    "source_page": "https://example.com/character/1401",
                    "generated_at": "2026-01-01T00:00:00+08:00",
                },
            },
            {
                "vector_score": 0.88,
                "model_rerank_score": 0.93,
                "entity": {
                    "chunk_id": "story-2",
                    "entry_id": "1401",
                    "entry_type": "hsr_character",
                    "title": "大黑塔",
                    "section": "角色故事",
                    "content": (
                        "角色故事·其二。她主持了围绕自身研究成果的研讨会。"
                        "与会者整理了她跨越多个领域的研究记录。"
                    ),
                    "data_version": "1.0",
                    "source_page": "https://example.com/character/1401",
                    "generated_at": "2026-01-01T00:00:00+08:00",
                },
            },
            {
                "vector_score": 0.87,
                "model_rerank_score": 0.92,
                "entity": {
                    "chunk_id": "story-3",
                    "entry_id": "1401",
                    "entry_type": "hsr_character",
                    "title": "大黑塔",
                    "section": "角色故事",
                    "content": (
                        "角色故事·其三。她让人偶处理日常事务。"
                        "自己继续研究尚未解答的宇宙问题。"
                    ),
                    "data_version": "1.0",
                    "source_page": "https://example.com/character/1401",
                    "generated_at": "2026-01-01T00:00:00+08:00",
                },
            },
            {
                "vector_score": 0.86,
                "model_rerank_score": 0.91,
                "entity": {
                    "chunk_id": "wrong-character",
                    "entry_id": "1013",
                    "entry_type": "hsr_character",
                    "title": "黑塔",
                    "section": "角色故事",
                    "content": "这是另一个角色的故事，不应混入大黑塔回答。",
                    "data_version": "1.0",
                    "source_page": "https://example.com/character/1013",
                    "generated_at": "2026-01-01T00:00:00+08:00",
                },
            },
        ]


def test_story_fallback_uses_complete_grounded_sentences() -> None:
    store = StoryStore()
    agent = RAGAgent(store=store, llm=BrokenLLM(), top_k=5)  # type: ignore[arg-type]
    response = asyncio.run(
        agent.run(
            AgentContext(
                user_id=None,
                message="告诉我大黑塔完整详细的角色故事，不是角色简介",
                intent="story_analysis",
                intent_metadata={"answer_depth": "detailed"},
                entities={
                    "mentioned_characters": [
                        {"character_id": "1401", "name": "大黑塔"}
                    ]
                },
            )
        )
    )

    assert "大黑塔是天才俱乐部第83席" in response.answer
    assert "角色故事·其二" in response.answer
    assert "角色故事·其三" in response.answer
    assert "另一个角色" not in response.answer
    assert "截断成半句话" not in response.answer
    assert "[C1]" in response.answer
    assert len(response.claims) >= 3
    assert {item.document_id for item in response.citations} == {"1401"}
    assert store.limit >= 8
