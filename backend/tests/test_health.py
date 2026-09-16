from fastapi.testclient import TestClient

from app.api.dependencies import get_herta_main_agent
from app.main import app
from app.schemas.ai_response import AIResponse, FilteringReport, ValidationReport


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ai_response_protocol() -> None:
    class FakeHertaMainAgent:
        async def run(self, _context) -> AIResponse:
            return AIResponse(
                agent="test_rag_agent",
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

    app.dependency_overrides[get_herta_main_agent] = lambda: FakeHertaMainAgent()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/chat/messages", json={"message": "测试问题"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["protocol"] == "claim-citation-validation-filtering"
    assert all(key in payload for key in ("claims", "citations", "validation", "filtering"))
