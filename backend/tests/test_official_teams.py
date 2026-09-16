from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.routes.auth import current_user
from app.api.v1.routes.teams import router
from app.api.dependencies import get_reasoning_llm_provider
from app.db.session import Base, get_db
from app.models.user import User, UserCharacter


def test_official_team_recommendation_save_list_and_delete() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as database:
        user = User(
            username="team_user",
            email="team@example.com",
            display_name="配队用户",
            password_hash="test-only",
        )
        database.add(user)
        database.flush()
        database.add_all(
            UserCharacter(user_id=user.id, character_id=character_id)
            for character_id in ("1412", "1303", "1208", "1101", "1201")
        )
        database.commit()
        user_id = user.id

    application = FastAPI()
    application.include_router(router)

    def override_database():
        with testing_session() as database:
            yield database

    def override_user() -> User:
        with testing_session() as database:
            user = database.get(User, user_id)
            assert user is not None
            database.expunge(user)
            return user

    application.dependency_overrides[get_db] = override_database
    application.dependency_overrides[current_user] = override_user
    application.dependency_overrides[get_reasoning_llm_provider] = lambda: None

    with TestClient(application) as client:
        recommended = client.post(
            "/teams/recommendations",
            json={
                "core_character_id": "1412",
                "preferred_character_ids": ["1303"],
                "excluded_character_ids": [],
                "require_sustain": True,
            },
        )
        assert recommended.status_code == 200
        body = recommended.json()
        assert body["response"]["protocol"] == "claim-citation-validation-filtering"
        assert len(body["theoretical"]) == 3
        assert body["owned"]
        assert body["favorite_trials"]
        score = body["owned"][0]["score_breakdown"]
        assert score["scoring_version"] == "team_score_v3"
        assert score["game_data_version"] == "4.4.51"
        assert score["observed_meta_score"] is None
        assert len(score["scenarios"]) == 3
        assert score["final_score"] == body["owned"][0]["score"]
        assert body["owned"][0]["rotation"]["speed_order"]
        assert "暂无同版本结构化实战样本" in " ".join(
            body["owned"][0]["data_warnings"]
        )

        member_ids = [
            member["character_id"] for member in body["owned"][0]["members"]
        ]
        saved = client.post(
            "/profile/teams",
            json={"name": "我的第一队", "member_ids": member_ids},
        )
        assert saved.status_code == 201
        assert saved.json()["name"] == "我的第一队"
        assert [member["character_id"] for member in saved.json()["members"]] == member_ids

        listed = client.get("/profile/teams")
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        team_id = listed.json()["items"][0]["id"]

        renamed = client.patch(
            f"/profile/teams/{team_id}", json={"name": "改名后的队伍"}
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "改名后的队伍"

        deleted = client.delete(f"/profile/teams/{team_id}")
        assert deleted.status_code == 204
        assert client.get("/profile/teams").json()["total"] == 0


def test_saved_team_rejects_unowned_or_duplicate_characters() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as database:
        user = User(
            username="team_validation",
            email="team-validation@example.com",
            display_name="校验用户",
            password_hash="test-only",
        )
        database.add(user)
        database.flush()
        database.add_all(
            UserCharacter(user_id=user.id, character_id=character_id)
            for character_id in ("1412", "1303", "1208")
        )
        database.commit()
        user_id = user.id

    application = FastAPI()
    application.include_router(router)

    def override_database():
        with testing_session() as database:
            yield database

    def override_user() -> User:
        with testing_session() as database:
            user = database.get(User, user_id)
            assert user is not None
            database.expunge(user)
            return user

    application.dependency_overrides[get_db] = override_database
    application.dependency_overrides[current_user] = override_user

    with TestClient(application) as client:
        duplicate = client.post(
            "/profile/teams",
            json={"name": "重复队", "member_ids": ["1412", "1412", "1303", "1208"]},
        )
        assert duplicate.status_code == 422
        unowned = client.post(
            "/profile/teams",
            json={"name": "越权队", "member_ids": ["1412", "1303", "1208", "1101"]},
        )
        assert unowned.status_code == 422
