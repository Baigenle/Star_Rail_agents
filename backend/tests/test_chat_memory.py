from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_herta_main_agent
from app.api.v1.routes.auth import current_user, optional_current_user
from app.api.v1.routes.chat import router as chat_router
from app.api.v1.routes.memories import router as memory_router
from app.db.session import Base, get_db
from app.models.user import User
from app.services.memory_service import MemoryService
from app.schemas.ai_response import (
    AIResponse,
    Citation,
    FilteringReport,
    ValidationReport,
)


class FakeHertaAgent:
    async def run(self, context):
        return AIResponse(
            agent="herta_main_agent",
            answer=f"已处理：{context.message}",
            claims=[],
            citations=[],
            validation=ValidationReport(
                status="unverified",
                method="test",
                evidence_count=0,
            ),
            filtering=FilteringReport(
                passed=False,
                removed_claims=0,
            ),
        )


class RecordingHertaAgent(FakeHertaAgent):
    def __init__(self) -> None:
        self.contexts = []

    async def run(self, context):
        self.contexts.append(context)
        return await super().run(context)


class ItemCitationAgent(FakeHertaAgent):
    async def run(self, context):
        response = await super().run(context)
        return response.model_copy(
            update={
                "citations": [
                    Citation(
                        id="C1",
                        title="星琼 · 基本资料",
                        source="https://example.com/items/900001",
                        document_id="900001",
                        entity_url="/items/900001",
                    ),
                    Citation(
                        id="C2",
                        title="信用点 · 基本资料",
                        source="https://example.com/items/2",
                        document_id="2",
                        entity_url="/items/2",
                    ),
                    Citation(
                        id="C3",
                        title="燃料 · 基本资料",
                        source="https://example.com/items/3",
                        document_id="3",
                        entity_url="/items/3",
                    ),
                ]
            }
        )


def build_client() -> tuple[TestClient, sessionmaker, dict[str, str]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as database:
        users = [
            User(
                username="memory_one",
                email="memory-one@example.com",
                display_name="记忆一号",
                password_hash="test-only",
            ),
            User(
                username="memory_two",
                email="memory-two@example.com",
                display_name="记忆二号",
                password_hash="test-only",
            ),
        ]
        database.add_all(users)
        database.commit()
        user_ids = {user.username: user.id for user in users}

    application = FastAPI()
    application.include_router(chat_router, prefix="/chat")
    application.include_router(memory_router, prefix="/profile")

    def override_database():
        with testing_session() as database:
            yield database

    def user_one() -> User:
        with testing_session() as database:
            user = database.get(User, user_ids["memory_one"])
            assert user is not None
            database.expunge(user)
            return user

    application.dependency_overrides[get_db] = override_database
    application.dependency_overrides[current_user] = user_one
    application.dependency_overrides[optional_current_user] = user_one
    application.dependency_overrides[get_herta_main_agent] = FakeHertaAgent
    return TestClient(application), testing_session, user_ids


def test_logged_in_chat_persists_conversation_and_only_suggests_memory() -> None:
    client, testing_session, _ = build_client()
    with client:
        created = client.post("/chat/messages", json={"message": "我喜欢阮·梅"})
        assert created.status_code == 200
        body = created.json()
        assert body["conversation_id"]
        assert body["memory_suggestions"] == []
        assert body["favorite_character_suggestions"]
        assert body["favorite_character_suggestions"][0]["name"] == "阮·梅"

        conversations = client.get("/chat/conversations")
        assert conversations.status_code == 200
        assert conversations.json()["total"] == 1

        messages = client.get(
            f"/chat/conversations/{body['conversation_id']}/messages"
        )
        assert messages.status_code == 200
        assert [item["role"] for item in messages.json()["items"]] == [
            "user",
            "assistant",
        ]

    from app.models.user import UserMemory

    with testing_session() as database:
        assert database.query(UserMemory).count() == 0


def test_logged_in_background_job_persists_and_returns_completed_response() -> None:
    client, _, user_ids = build_client()
    with client:
        created = client.post("/chat/jobs", json={"message": "后台回答这个问题"})
        assert created.status_code == 202
        job_id = created.json()["id"]

        fetched = client.get(f"/chat/jobs/{job_id}")
        assert fetched.status_code == 200
        assert fetched.json()["status"] == "completed"
        assert fetched.json()["response"]["answer"] == "已处理：后台回答这个问题"
        assert fetched.json()["partial_answer"] == "已处理：后台回答这个问题"
        assert fetched.json()["progress"]["stage"] == "completed"
        assert fetched.json()["progress"]["percent"] == 100

        events = client.get(f"/chat/jobs/{job_id}/events")
        assert events.status_code == 200
        assert events.headers["content-type"].startswith("text/event-stream")
        assert "event: job.queued" in events.text
        assert "event: intent.started" in events.text
        assert "event: agent.selected" in events.text
        assert "event: answer.delta" in events.text
        assert "event: job.completed" in events.text
        assert "system prompt" not in events.text.lower()

        jobs = client.get("/chat/jobs")
        assert jobs.status_code == 200
        assert jobs.json()["total"] == 1

        conversation_id = fetched.json()["conversation_id"]
        messages = client.get(
            f"/chat/conversations/{conversation_id}/messages"
        ).json()["items"]
        assert [item["role"] for item in messages] == ["user", "assistant"]

        def user_two() -> User:
            return User(
                id=user_ids["memory_two"],
                username="memory_two",
                email="memory-two@example.com",
                display_name="记忆二号",
                password_hash="test-only",
            )

        client.app.dependency_overrides[current_user] = user_two
        assert client.get(f"/chat/jobs/{job_id}").status_code == 404
        assert client.get(f"/chat/jobs/{job_id}/events").status_code == 404


def test_follow_up_chat_passes_previous_messages_into_agent_context() -> None:
    client, _, _ = build_client()
    recorder = RecordingHertaAgent()
    client.app.dependency_overrides[get_herta_main_agent] = lambda: recorder

    with client:
        first = client.post("/chat/messages", json={"message": "我想了解大黑塔"})
        conversation_id = first.json()["conversation_id"]
        second = client.post(
            "/chat/messages",
            json={
                "message": "那她的故事呢？",
                "conversation_id": conversation_id,
            },
        )

    assert second.status_code == 200
    assert recorder.contexts[0].conversation_history == []
    assert recorder.contexts[1].conversation_history == [
        {"role": "user", "content": "我想了解大黑塔"},
        {"role": "assistant", "content": "已处理：我想了解大黑塔"},
    ]


def test_anonymous_chat_accepts_validated_temporary_history() -> None:
    client, _, _ = build_client()
    recorder = RecordingHertaAgent()
    client.app.dependency_overrides[get_herta_main_agent] = lambda: recorder
    client.app.dependency_overrides[optional_current_user] = lambda: None

    with client:
        response = client.post(
            "/chat/messages",
            json={
                "message": "那她的故事呢？",
                "history": [
                    {"role": "user", "content": "我想了解大黑塔"},
                    {
                        "role": "assistant",
                        "content": "你想了解她的哪一部分？",
                    },
                ],
            },
        )

    assert response.status_code == 200
    assert recorder.contexts[0].conversation_history == [
        {"role": "user", "content": "我想了解大黑塔"},
        {"role": "assistant", "content": "你想了解她的哪一部分？"},
    ]


def test_character_mention_adds_direct_catalog_reference() -> None:
    client, _, _ = build_client()

    with client:
        response = client.post("/chat/messages", json={"message": "我要养火花怎么养"})

    assert response.status_code == 200
    references = response.json()["related_entities"]
    assert references == [
        {
            "entity_type": "character",
            "entity_id": "1501",
            "name": "火花",
            "entity_url": "/characters/1501",
            "image_url": "/api/v1/assets/characters/1501/raw/1501_3de381e3.webp",
        }
    ]


def test_explicit_item_question_returns_one_exact_catalog_reference() -> None:
    client, _, _ = build_client()
    client.app.dependency_overrides[get_herta_main_agent] = ItemCitationAgent

    with client:
        response = client.post("/chat/messages", json={"message": "星琼是什么？"})

    assert response.status_code == 200
    references = response.json()["related_entities"]
    assert len(references) == 1
    assert references[0]["entity_type"] == "item"
    assert references[0]["name"] == "星琼"


def test_exact_item_is_available_to_router_before_agent_execution() -> None:
    client, _, _ = build_client()
    recorder = RecordingHertaAgent()
    client.app.dependency_overrides[get_herta_main_agent] = lambda: recorder

    with client:
        response = client.post("/chat/messages", json={"message": "星琼是什么？"})

    assert response.status_code == 200
    assert recorder.contexts[0].entities["mentioned_catalog_entities"] == [
        {
            "entity_type": "hsr_item",
            "entity_id": "1",
            "name": "星琼",
        }
    ]


def test_memory_requires_confirmation_and_supports_update_disable_delete() -> None:
    client, _, _ = build_client()
    with client:
        created = client.post(
            "/profile/memories",
            json={
                "memory_type": "answer_preference",
                "content": "回答尽量简洁",
                "source": "chat_suggestion",
            },
        )
        assert created.status_code == 201
        memory_id = created.json()["id"]
        assert created.json()["source"] == "user_confirmed"
        duplicate = client.post(
            "/profile/memories",
            json={
                "memory_type": "answer_preference",
                "content": "回答尽量简洁",
            },
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["id"] == memory_id

        updated = client.patch(
            f"/profile/memories/{memory_id}",
            json={"content": "回答先给结论", "is_active": False},
        )
        assert updated.status_code == 200
        assert updated.json()["content"] == "回答先给结论"
        assert updated.json()["is_active"] is False

        assert client.get("/profile/memories").json()["total"] == 1
        assert client.delete(f"/profile/memories/{memory_id}").status_code == 204
        assert client.get("/profile/memories").json()["total"] == 0


def test_cross_user_conversation_is_not_visible() -> None:
    client, _, user_ids = build_client()
    with client:
        created = client.post("/chat/messages", json={"message": "继续这个会话"})
        conversation_id = created.json()["conversation_id"]

        app = client.app

        def user_two() -> User:
            user = User(
                id=user_ids["memory_two"],
                username="memory_two",
                email="memory-two@example.com",
                display_name="记忆二号",
                password_hash="test-only",
            )
            return user

        app.dependency_overrides[current_user] = user_two
        assert (
            client.get(f"/chat/conversations/{conversation_id}/messages").status_code
            == 404
        )


def test_character_mentions_return_all_non_overlapping_catalog_characters() -> None:
    characters = [
        {"id": "1401", "name": "大黑塔"},
        {"id": "1013", "name": "黑塔"},
    ]

    mentions = MemoryService.character_mentions(
        "比较大黑塔和黑塔的关系",
        characters,
        limit=None,
    )

    assert [(item["id"], item["name"]) for item in mentions] == [
        ("1401", "大黑塔"),
        ("1013", "黑塔"),
    ]


def test_neutral_character_mentions_do_not_create_favorite_prompts() -> None:
    suggestions = MemoryService.favorite_character_suggestions(
        "给我讲讲大黑塔的故事，再说说黑塔。",
        [
            {"id": "1401", "name": "大黑塔"},
            {"id": "1013", "name": "黑塔"},
        ],
        owned_character_ids={"1401"},
        favorite_character_ids=set(),
    )

    assert suggestions == []


def test_explicit_character_preference_creates_favorite_prompt() -> None:
    suggestions = MemoryService.favorite_character_suggestions(
        "我很喜欢大黑塔，想多看她的故事。",
        [
            {"id": "1401", "name": "大黑塔"},
            {"id": "1013", "name": "黑塔"},
        ],
        owned_character_ids={"1401"},
        favorite_character_ids=set(),
    )

    assert [(item.character_id, item.name) for item in suggestions] == [
        ("1401", "大黑塔")
    ]
    assert suggestions[0].is_owned is True
    assert "设为喜欢" in suggestions[0].prompt
