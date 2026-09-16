from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.routes import activities, auth, custom_characters
from app.core.config import settings
from app.core.security import verify_password
from app.db.session import Base, get_db
from app.models.user import User


@pytest.fixture()
def auth_client() -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    """使用内存数据库验证真实 Bearer Token 链路，不覆盖 current_user。"""

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    application = FastAPI()
    application.include_router(auth.router, prefix="/auth")
    application.include_router(custom_characters.router)
    application.include_router(activities.router)

    def override_database() -> Iterator[Session]:
        with testing_session() as database:
            yield database

    application.dependency_overrides[get_db] = override_database
    with TestClient(application) as client:
        yield client, testing_session


def register(
    client: TestClient,
    *,
    username: str,
    email: str,
    password: str = "ThesisTest123!",
) -> dict:
    response = client.post(
        "/auth/register",
        json={
            "username": username,
            "email": email,
            "password": password,
            "display_name": username,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_register_login_me_and_password_hashing(
    auth_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, testing_session = auth_client
    created = register(
        client,
        username="Thesis_User",
        email="THESIS_USER@example.com",
    )

    assert created["user"]["username"] == "thesis_user"
    assert created["user"]["email"] == "thesis_user@example.com"
    assert created["user"]["is_admin"] is False
    assert "password" not in created["user"]

    with testing_session() as database:
        stored = database.scalar(select(User).where(User.username == "thesis_user"))
        assert stored is not None
        assert stored.password_hash != "ThesisTest123!"
        assert verify_password("ThesisTest123!", stored.password_hash)

    logged_in = client.post(
        "/auth/login",
        json={"account": "THESIS_USER@EXAMPLE.COM", "password": "ThesisTest123!"},
    )
    assert logged_in.status_code == 200
    token = logged_in.json()["access_token"]

    profile = client.get("/auth/me", headers=bearer(token))
    assert profile.status_code == 200
    assert profile.json()["username"] == "thesis_user"
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers=bearer("invalid.token.value")).status_code == 401


def test_registration_validation_duplicates_and_wrong_password(
    auth_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = auth_client
    register(client, username="first_user", email="first@example.com")

    duplicate_username = client.post(
        "/auth/register",
        json={
            "username": "FIRST_USER",
            "email": "another@example.com",
            "password": "ThesisTest123!",
            "display_name": "duplicate",
        },
    )
    duplicate_email = client.post(
        "/auth/register",
        json={
            "username": "another_user",
            "email": "FIRST@example.com",
            "password": "ThesisTest123!",
            "display_name": "duplicate",
        },
    )
    invalid_username = client.post(
        "/auth/register",
        json={
            "username": "包含中文",
            "email": "valid@example.com",
            "password": "ThesisTest123!",
            "display_name": "invalid",
        },
    )
    wrong_password = client.post(
        "/auth/login",
        json={"account": "first_user", "password": "WrongPassword123!"},
    )

    assert duplicate_username.status_code == 409
    assert duplicate_email.status_code == 409
    assert invalid_username.status_code == 422
    assert wrong_password.status_code == 401


def test_admin_routes_use_configured_username_not_email(
    auth_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = auth_client
    previous_admins = settings.admin_usernames
    settings.admin_usernames = " REVIEW_ADMIN , backup_admin "
    try:
        normal = register(client, username="normal_user", email="normal@example.com")
        admin = register(client, username="Review_Admin", email="admin@example.com")

        assert normal["user"]["is_admin"] is False
        assert admin["user"]["is_admin"] is True

        for path in ("/admin/reviews", "/admin/activity-guide-reviews"):
            assert client.get(path).status_code == 401
            assert (
                client.get(path, headers=bearer(normal["access_token"])).status_code
                == 403
            )
            assert (
                client.get(path, headers=bearer(admin["access_token"])).status_code
                == 200
            )
    finally:
        settings.admin_usernames = previous_admins

