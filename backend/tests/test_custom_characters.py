from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.routes.auth import current_user
from app.api.v1.routes.custom_characters import router
from app.api.dependencies import get_reasoning_llm_provider
from app.core.config import settings
from app.db.session import Base, get_db
from app.models.user import User
from app.schemas.custom_character import CustomCharacterPayload


def test_custom_character_payload_rejects_unbounded_skill_content() -> None:
    with pytest.raises(ValidationError):
        CustomCharacterPayload(
            skills={"basic": "x" * 4001},
        )

    with pytest.raises(ValidationError):
        CustomCharacterPayload(
            skills={"server_command": "not an official skill slot"},
        )


def test_creator_stage_confirmation_team_recommendation_and_private_isolation() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as database:
        author = User(
            username="creator",
            email="creator@example.com",
            display_name="创作者",
            password_hash="test-only",
        )
        stranger = User(
            username="stranger",
            email="stranger@example.com",
            display_name="其他用户",
            password_hash="test-only",
        )
        database.add_all([author, stranger])
        database.commit()
        author_id, stranger_id = author.id, stranger.id

    active_user_id = {"value": author_id}
    application = FastAPI()
    application.include_router(router)

    def override_database():
        with testing_session() as database:
            yield database

    def override_user() -> User:
        with testing_session() as database:
            user = database.get(User, active_user_id["value"])
            assert user is not None
            database.expunge(user)
            return user

    application.dependency_overrides[get_db] = override_database
    application.dependency_overrides[current_user] = override_user
    application.dependency_overrides[get_reasoning_llm_provider] = lambda: None

    with TestClient(application) as client:
        created = client.post("/custom-characters", json={})
        assert created.status_code == 201
        character_id = created.json()["id"]

        session = client.post(f"/custom-characters/{character_id}/sessions")
        assert session.status_code == 201
        session_id = session.json()["id"]

        turn = client.post(
            f"/custom-character-sessions/{session_id}/messages",
            json={
                "message": "她叫量子观测员，是五星量子虚无角色。",
                "fields": {
                    "name": "量子观测员",
                    "rarity": 5,
                    "element": "量子",
                    "path": "虚无",
                    "summary": "通过观测削弱敌人抗性的学者。",
                },
            },
        )
        assert turn.status_code == 200
        assert turn.json()["response"]["agent"] == "custom_character_agent"
        assert turn.json()["pending_fields"]["element"] == "量子"

        resumed = client.get(
            f"/custom-characters/{character_id}/sessions/latest"
        )
        assert resumed.status_code == 200
        assert resumed.json()["id"] == session_id
        assert resumed.json()["stage"] == 1
        assert resumed.json()["pending_fields"]["element"] == "量子"

        confirmed = client.post(
            f"/custom-character-sessions/{session_id}/confirm-stage"
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["stage"] == 2

        updated = client.patch(
            f"/custom-characters/{character_id}",
            json={
                "payload": {
                    "name": "量子观测员",
                    "rarity": 5,
                    "element": "量子",
                    "path": "虚无",
                    "summary": "记录敌人的观测结果，为量子队创造稳定输出窗口的学者。",
                    "roles": ["辅助"],
                    "core_mechanics": "战技施加持续两回合的观测标记并降低抗性，终结技延长标记并强化全队量子伤害。",
                    "mechanic_tags": ["减抗"],
                    "base_stats": {
                        "hp": 1080,
                        "attack": 540,
                        "defence": 470,
                        "speed": 103,
                        "taunt": 100,
                        "energy": 120,
                    },
                    "skills": {
                        "basic": "对指定敌方单体造成量子属性伤害，并获得一层演算。",
                        "skill": "为目标施加持续两回合的观测标记，使其量子抗性降低。",
                        "ultimate": "延长所有观测标记一回合，并提高我方全体造成的量子伤害。",
                        "talent": "队友攻击带有观测标记的敌人后，为量子观测员恢复能量。",
                        "technique": "使用秘技后，下一场战斗开始时为随机敌人施加观测标记。",
                    },
                }
            },
        )
        assert updated.status_code == 200

        teams = client.post(
            f"/custom-characters/{character_id}/team-recommendations"
        )
        assert teams.status_code == 200
        body = teams.json()
        assert len(body["theoretical"]) == 3
        assert body["response"]["protocol"] == "claim-citation-validation-filtering"

        blocked_before_review = client.post(
            f"/custom-characters/{character_id}/submit"
        )
        assert blocked_before_review.status_code == 422

        self_review = client.post(
            f"/custom-characters/{character_id}/self-review"
        )
        assert self_review.status_code == 200
        assert self_review.json()["overall_score"] >= 60
        assert self_review.json()["must_fix_count"] == 0
        assert len(self_review.json()["categories"]) == 5

        cached_review = client.get(
            f"/custom-characters/{character_id}/self-review"
        )
        assert cached_review.status_code == 200
        assert cached_review.json()["generated_at"] == self_review.json()["generated_at"]

        submitted = client.post(f"/custom-characters/{character_id}/submit")
        assert submitted.status_code == 200
        assert submitted.json()["status"] == "pending_review"
        assert client.get("/community/characters").json()["total"] == 0
        assert client.get("/admin/reviews").status_code == 403

        previous_admins = settings.admin_usernames
        settings.admin_usernames = "creator"
        try:
            pending = client.get("/admin/reviews")
            assert pending.status_code == 200
            assert pending.json()["total"] == 1
            version_id = pending.json()["items"][0]["version_id"]
            approved = client.post(
                f"/admin/reviews/{version_id}",
                json={"action": "approve", "reason": "结构完整"},
            )
            assert approved.status_code == 200
            assert approved.json()["status"] == "published"

            assessment = client.post(
                f"/admin/reviews/{version_id}/ai-assessment"
            )
            assert assessment.status_code == 200
            assert assessment.json()["decision"] == "advisory_only"
            assert assessment.json()["completeness"]["passed"] is True

            unpublished = client.post(
                f"/admin/community/characters/{character_id}/moderation",
                json={"action": "unpublish", "reason": "等待作者修正"},
            )
            assert unpublished.status_code == 200
            assert unpublished.json()["status"] == "unpublished"
            assert client.get(f"/community/characters/{character_id}").status_code == 404

            listed = client.get(
                "/admin/community-moderation",
                params={"type": "character", "status": "unpublished"},
            )
            assert listed.status_code == 200
            assert listed.json()["total"] == 1

            republished = client.post(
                f"/admin/community/characters/{character_id}/moderation",
                json={"action": "republish"},
            )
            assert republished.status_code == 200
            assert republished.json()["status"] == "published"
        finally:
            settings.admin_usernames = previous_admins

        public_before_edit = client.get(
            f"/community/characters/{character_id}"
        ).json()
        assert public_before_edit["version_number"] == 1
        revised_payload = updated.json()["payload"]
        revised_payload["summary"] = "第二版简介"
        revised_payload["roles"] = ["主C"]
        revised = client.patch(
            f"/custom-characters/{character_id}",
            json={"payload": revised_payload},
        )
        assert revised.status_code == 200
        assert revised.json()["version_number"] == 2
        assert revised.json()["status"] == "draft"
        assert revised.json()["payload"]["roles"] == ["主C"]
        assert client.get(
            f"/custom-characters/{character_id}/self-review"
        ).status_code == 404
        public_after_edit = client.get(
            f"/community/characters/{character_id}"
        ).json()
        assert public_after_edit["version_number"] == 1

        active_user_id["value"] = stranger_id
        visible = client.get(f"/custom-characters/{character_id}")
        assert visible.status_code == 200
        assert visible.json()["version_number"] == 1
        assert visible.json()["payload"]["summary"] != "第二版简介"
        assert client.post(
            f"/custom-characters/{character_id}/self-review"
        ).status_code == 404
