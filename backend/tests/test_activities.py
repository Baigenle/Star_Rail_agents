from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.routes.activities import require_activity_admin, router
from app.api.v1.routes.auth import current_user
from app.db.session import Base, get_db
from app.models.user import User


def activity_client() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as database:
        user = User(
            username="guide-author",
            email="guide@example.com",
            display_name="攻略作者",
            password_hash="test-only",
        )
        database.add(user)
        database.commit()
        user_id = user.id

    app = FastAPI()
    app.include_router(router)

    def override_database():
        with testing_session() as database:
            yield database

    def override_user() -> User:
        with testing_session() as database:
            user = database.get(User, user_id)
            assert user is not None
            database.expunge(user)
            return user

    app.dependency_overrides[get_db] = override_database
    app.dependency_overrides[current_user] = override_user
    app.dependency_overrides[require_activity_admin] = override_user
    return TestClient(app)


def test_activity_catalog_only_exposes_detail_for_version_44() -> None:
    with activity_client() as client:
        listed = client.get("/activities")
        assert listed.status_code == 200
        body = listed.json()
        assert body["total"] >= 190
        current = next(item for item in body["items"] if item["version"] == "4.4")
        historical = next(item for item in body["items"] if item["version"] != "4.4")

        current_detail = client.get(f"/activities/{current['id']}")
        assert current_detail.status_code == 200
        assert current_detail.json()["detail"]["sections"]

        historical_detail = client.get(f"/activities/{historical['id']}")
        assert historical_detail.status_code == 200
        assert historical_detail.json()["detail"] is None
        assert historical_detail.json()["detail_available"] is False


def test_activity_guide_submission_requires_44_and_admin_review() -> None:
    with activity_client() as client:
        items = client.get("/activities").json()["items"]
        current = next(item for item in items if item["version"] == "4.4")
        historical = next(item for item in items if item["version"] != "4.4")

        rejected = client.post(
            f"/activities/{historical['id']}/guides",
            json={"title": "旧活动攻略", "content": "不应允许投稿" * 10, "player_stage": "all"},
        )
        assert rejected.status_code == 422

        submitted = client.post(
            f"/activities/{current['id']}/guides",
            json={
                "title": "低配通关思路",
                "content": "先确认活动机制，再根据角色池选择生存位与输出位。" * 4,
                "player_stage": "beginner",
            },
        )
        assert submitted.status_code == 201
        guide = submitted.json()
        assert guide["status"] == "pending_review"
        assert client.get(f"/activities/{current['id']}/guides").json()["total"] == 0

        pending = client.get("/admin/activity-guide-reviews")
        assert pending.status_code == 200
        assert pending.json()["total"] == 1

        approved = client.post(
            f"/admin/activity-guide-reviews/{guide['id']}",
            json={"action": "approve", "reason": ""},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "published"
        assert client.get(f"/activities/{current['id']}/guides").json()["total"] == 1

        missing_reason = client.post(
            f"/admin/activity-guides/{guide['id']}/moderation",
            json={"action": "unpublish", "reason": ""},
        )
        assert missing_reason.status_code == 422

        unpublished = client.post(
            f"/admin/activity-guides/{guide['id']}/moderation",
            json={"action": "unpublish", "reason": "内容需要修正"},
        )
        assert unpublished.status_code == 200
        assert unpublished.json()["status"] == "unpublished"
        assert client.get(f"/activities/{current['id']}/guides").json()["total"] == 0

        restored = client.post(
            f"/admin/activity-guides/{guide['id']}/moderation",
            json={"action": "republish"},
        )
        assert restored.status_code == 200
        assert restored.json()["status"] == "published"
