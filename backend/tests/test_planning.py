from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.routes.auth import current_user
from app.api.v1.routes.planning import router
from app.db.session import Base, get_db
from app.models.user import User, UserCharacter


def planning_client() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as database:
        user = User(
            username="planner",
            email="planner@example.com",
            display_name="规划测试",
            password_hash="test-only",
        )
        database.add(user)
        database.flush()
        database.add_all(
            [
                UserCharacter(user_id=user.id, character_id="1015"),
                UserCharacter(user_id=user.id, character_id="1303"),
            ]
        )
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
    return TestClient(app)


def request_payload():
    return {
        "characters": [
            {
                "character_id": "1015",
                "from_level": 35,
                "to_level": 65,
                "skill_ranges": {
                    "basic": {"from_level": 1, "to_level": 6},
                    "skill": {"from_level": 1, "to_level": 10},
                },
            },
            {
                "character_id": "1303",
                "from_level": 60,
                "to_level": 70,
                "skill_ranges": {},
            },
        ]
    }


def test_multi_character_calculation_merges_materials_and_recommendations() -> None:
    with planning_client() as client:
        response = client.post(
            "/planning/progression/calculate", json=request_payload()
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["characters"]) == 2
        assert body["total_by_key"]["credits"] > 0
        assert body["response"]["protocol"] == "claim-citation-validation-filtering"
        assert body["recommendations"]["1015"]["lightcones"]
        assert body["recommendations"]["1015"]["tunnel_relics"]


def test_multi_character_calculation_keeps_character_specific_materials_separate() -> None:
    with planning_client() as client:
        response = client.post(
            "/planning/progression/calculate", json=request_payload()
        )
        assert response.status_code == 200
        body = response.json()

        character_material_ids = {
            character["character_id"]: {
                material["item"]["id"]
                for material in character["materials"]
                if material["item"] is not None
            }
            for character in body["characters"]
        }
        merged_materials = {
            material["item"]["id"]: material["quantity"]
            for material in body["materials"]
            if material["item"] is not None
        }

        assert "111003" in character_material_ids["1015"]
        assert "113003" in character_material_ids["1303"]
        assert merged_materials["111003"] == next(
            material["quantity"]
            for material in body["characters"][0]["materials"]
            if material["item"] and material["item"]["id"] == "111003"
        )
        assert merged_materials["113003"] == next(
            material["quantity"]
            for material in body["characters"][1]["materials"]
            if material["item"] and material["item"]["id"] == "113003"
        )


def test_saved_progression_plan_delete_and_weekly_budget_task_state() -> None:
    with planning_client() as client:
        saved = client.post(
            "/profile/progression-plans",
            json={
                "name": "两名角色冲刺",
                "priority": 1,
                **request_payload(),
            },
        )
        assert saved.status_code == 201
        plan_id = saved.json()["id"]

        listed = client.get("/profile/progression-plans")
        assert listed.status_code == 200
        assert listed.json()["total"] == 1

        paused = client.patch(
            f"/profile/progression-plans/{plan_id}", json={"status": "paused"}
        )
        assert paused.status_code == 200
        assert paused.json()["status"] == "paused"
        client.patch(
            f"/profile/progression-plans/{plan_id}", json={"status": "active"}
        )

        weekly = client.post(
            "/planning/weekly/generate",
            json={"stamina_budget": 420, "weekly_runs_remaining": 2},
        )
        assert weekly.status_code == 200
        weekly_body = weekly.json()
        assert weekly_body["allocated_stamina"] <= 420
        stamina_tasks = [
            task for task in weekly_body["tasks"] if task["stamina_cost"] > 0
        ]
        assert stamina_tasks
        assert stamina_tasks[0]["dungeon_type"] == "历战余响"
        assert stamina_tasks[0]["stamina_per_run"] == 30
        assert any(task["dungeon_type"] == "拟造花萼（赤）" for task in stamina_tasks)
        assert all(
            task["stamina_cost"]
            == task["stamina_per_run"] * task["run_count"]
            for task in stamina_tasks
        )

        task_id = weekly_body["tasks"][0]["id"]
        updated = client.patch(
            f"/profile/weekly-plans/{weekly_body['id']}/tasks/{task_id}",
            json={"completed": True},
        )
        assert updated.status_code == 200
        assert next(
            task for task in updated.json()["tasks"] if task["id"] == task_id
        )["completed"] is True
        assert client.get("/profile/weekly-plans/current").status_code == 200

        deleted = client.delete(f"/profile/progression-plans/{plan_id}")
        assert deleted.status_code == 204
        assert client.get("/profile/progression-plans").json()["total"] == 0
