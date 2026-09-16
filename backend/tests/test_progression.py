from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes.catalog import router
from app.services.progression_service import ProgressionService, ProgressionValidationError


DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs"


def test_standard_core_track_full_range_matches_archer_example() -> None:
    service = ProgressionService(DOCS_ROOT)

    result = service.calculate(
        "1015",
        from_level=1,
        to_level=1,
        skill_ranges={"skill": (1, 10)},
    )

    assert result.total_by_key == {
        "credits": 652_500,
        "tracks": 2,
        "trace_path_2": 3,
        "trace_path_3": 15,
        "trace_path_4": 30,
        "weekly": 3,
        "common_2": 9,
        "common_3": 13,
        "common_4": 7,
    }


def test_elation_and_remembrance_special_tracks_use_distinct_rules() -> None:
    service = ProgressionService(DOCS_ROOT)

    elation = service.calculate(
        "1501",
        from_level=1,
        to_level=1,
        skill_ranges={"elation_skill": (1, 10)},
    )
    remembrance = service.calculate(
        "1402",
        from_level=1,
        to_level=1,
        skill_ranges={"memosprite_skill": (1, 6)},
    )

    assert elation.total_by_key == {
        "credits": 520_000,
        "trace_path_2": 3,
        "trace_path_3": 12,
        "trace_path_4": 24,
        "common_2": 7,
        "common_3": 11,
        "common_4": 14,
    }
    assert remembrance.total_by_key == {
        "credits": 201_500,
        "trace_path_2": 2,
        "trace_path_3": 6,
        "trace_path_4": 8,
        "common_2": 4,
        "common_3": 5,
        "common_4": 4,
    }


def test_level_range_only_counts_crossed_ascension_gates() -> None:
    service = ProgressionService(DOCS_ROOT)

    result = service.calculate("1015", from_level=35, to_level=65, skill_ranges={})

    assert result.total_by_key == {
        "credits": 136_000,
        "common_3": 15,
        "common_4": 6,
        "ascension": 30,
    }


def test_invalid_ranges_and_track_caps_are_rejected() -> None:
    service = ProgressionService(DOCS_ROOT)

    with pytest.raises(ProgressionValidationError):
        service.calculate("1015", from_level=70, to_level=20, skill_ranges={})
    with pytest.raises(ProgressionValidationError):
        service.calculate(
            "1015",
            from_level=1,
            to_level=1,
            skill_ranges={"basic": (1, 10)},
        )
    with pytest.raises(ProgressionValidationError):
        service.calculate(
            "1015",
            from_level=1,
            to_level=1,
            skill_ranges={"elation_skill": (1, 2)},
        )


def test_progression_catalog_endpoints_expose_rules_and_material_cards() -> None:
    application = FastAPI()
    application.include_router(router, prefix="/catalog")

    with TestClient(application) as client:
        profile = client.get("/catalog/characters/1015/progression")
        assert profile.status_code == 200
        assert profile.json()["archetype"] == "standard"
        assert profile.json()["tracks"]["basic"]["max_level"] == 6

        result = client.post(
            "/catalog/characters/1015/progression/calculate",
            json={
                "from_level": 1,
                "to_level": 70,
                "skill_ranges": {
                    "basic": {"from_level": 1, "to_level": 6},
                    "skill": {"from_level": 1, "to_level": 10},
                },
            },
        )
        assert result.status_code == 200
        body = result.json()
        assert body["total_by_key"]["ascension"] == 65
        assert all(material["item"] for material in body["materials"])
        assert any(
            material["item"]["name"] == "信用点" for material in body["materials"]
        )
