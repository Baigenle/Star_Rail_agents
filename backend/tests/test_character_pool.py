from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.routes.auth import current_user
from app.api.v1.routes.profile import router
from app.db.session import Base, get_db
from app.models.user import User, UserMemory


def test_character_pool_batch_import_and_favorite_persistence() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as database:
        user = User(
            username="pool_test",
            email="pool@example.com",
            display_name="角色池测试",
            password_hash="test-only",
        )
        database.add(user)
        database.commit()
        database.refresh(user)
        user_id = user.id

    application = FastAPI()
    application.include_router(router, prefix="/profile")

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
        imported = client.put(
            "/profile/characters",
            json={"character_ids": ["1412", "1303", "1412"]},
        )
        assert imported.status_code == 200
        assert imported.json()["total"] == 2
        assert {item["character_id"] for item in imported.json()["items"]} == {
            "1412",
            "1303",
        }

        favorite = client.patch(
            "/profile/characters/1412/favorite",
            json={"is_favorite": True},
        )
        assert favorite.status_code == 200
        assert favorite.json()["is_favorite"] is True
        with testing_session() as database:
            memory = database.scalar(
                select(UserMemory).where(
                    UserMemory.user_id == user_id,
                    UserMemory.memory_type == "favorite_character",
                    UserMemory.source == "character_pool:1412",
                )
            )
            assert memory is not None
            assert memory.is_active is True
            assert "1412" in memory.content

        resynced = client.put(
            "/profile/characters",
            json={"character_ids": ["1412", "1507"]},
        )
        assert resynced.status_code == 200
        assert resynced.json()["total"] == 2
        assert resynced.json()["favorites"] == 1
        assert next(
            item
            for item in resynced.json()["items"]
            if item["character_id"] == "1412"
        )["is_favorite"] is True

        current = client.get("/profile/characters")
        assert current.status_code == 200
        assert {item["character_id"] for item in current.json()["items"]} == {
            "1412",
            "1507",
        }

        missing = client.patch(
            "/profile/characters/1303/favorite",
            json={"is_favorite": True},
        )
        assert missing.status_code == 404

        unfavorite = client.patch(
            "/profile/characters/1412/favorite",
            json={"is_favorite": False},
        )
        assert unfavorite.status_code == 200
        with testing_session() as database:
            memory = database.scalar(
                select(UserMemory).where(
                    UserMemory.user_id == user_id,
                    UserMemory.source == "character_pool:1412",
                )
            )
            assert memory is not None
            assert memory.is_active is False

        invalid = client.put(
            "/profile/characters",
            json={"character_ids": ["not-a-character"]},
        )
        assert invalid.status_code == 422


def test_character_progress_requires_owned_character_and_persists() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as database:
        user = User(
            username="progress_test",
            email="progress@example.com",
            display_name="练度测试",
            password_hash="test-only",
        )
        database.add(user)
        database.commit()
        database.refresh(user)
        user_id = user.id

    application = FastAPI()
    application.include_router(router, prefix="/profile")

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

    payload = {
        "current_level": 20,
        "target_level": 70,
        "eidolon": 1,
        "current_skills": {"basic": 2, "skill": 3, "ultimate": 3, "talent": 3},
        "target_skills": {"basic": 6, "skill": 10, "ultimate": 10, "talent": 10},
    }
    with TestClient(application) as client:
        missing = client.put("/profile/characters/1015/progression", json=payload)
        assert missing.status_code == 404

        imported = client.put(
            "/profile/characters", json={"character_ids": ["1015"]}
        )
        assert imported.status_code == 200

        saved = client.put("/profile/characters/1015/progression", json=payload)
        assert saved.status_code == 200
        assert saved.json()["target_level"] == 70
        assert saved.json()["target_skills"]["skill"] == 10

        current = client.get("/profile/characters/1015/progression")
        assert current.status_code == 200
        assert current.json()["eidolon"] == 1
