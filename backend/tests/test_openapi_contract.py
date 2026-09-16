from app.main import app


def test_core_feature_routes_are_exposed_in_openapi() -> None:
    """防止重构 Router 时误删毕业设计演示所需的核心接口。"""

    paths = app.openapi()["paths"]
    expected_methods = {
        "/api/v1/chat/jobs": {"get", "post"},
        "/api/v1/chat/jobs/{job_id}/events": {"get"},
        "/api/v1/catalog/characters": {"get"},
        "/api/v1/catalog/characters/{character_id}/progression": {"get"},
        "/api/v1/teams/recommendations": {"post"},
        "/api/v1/planning/progression/calculate": {"post"},
        "/api/v1/planning/weekly/generate": {"post"},
        "/api/v1/profile/memories": {"get", "post"},
        "/api/v1/custom-characters": {"get", "post"},
        "/api/v1/community/characters": {"get"},
        "/api/v1/activities": {"get"},
        "/api/v1/stories": {"get"},
    }

    for path, methods in expected_methods.items():
        assert path in paths, f"OpenAPI missing core path: {path}"
        assert methods.issubset(paths[path]), f"{path} missing methods: {methods}"


def test_openapi_operation_ids_are_unique() -> None:
    schema = app.openapi()
    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for method, operation in path_item.items()
        if method.lower() in {"get", "post", "put", "patch", "delete"}
        and "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))

