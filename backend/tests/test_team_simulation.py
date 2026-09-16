from pathlib import Path

import pytest

from app.services.team_simulation_service import (
    CharacterCombatParameters,
    TeamSimulationService,
)


DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs"


def test_character_parameters_are_extracted_from_versioned_local_archive() -> None:
    service = TeamSimulationService(DOCS_ROOT)

    parameters = service.character_parameters("1501")

    assert parameters.character_id == "1501"
    assert parameters.name == "火花"
    assert parameters.game_data_version == "4.4.51"
    assert parameters.speed == pytest.approx(107)
    assert parameters.max_energy == pytest.approx(160)
    assert parameters.skill_point_fields_found is True


def test_team_simulation_reports_resource_cycles_and_three_scenarios() -> None:
    service = TeamSimulationService(DOCS_ROOT)
    profiles = service.profiles()

    result = service.evaluate(
        ["1412", "1303", "1208", "1101"],
        structural_score=78,
        profiles=profiles,
    )

    assert result.game_data_version == "4.4.51"
    assert result.scoring_version == "team_score_v3"
    assert {scenario.scenario_id for scenario in result.scenarios} == {
        "single_boss",
        "dual_elite",
        "five_targets",
    }
    assert len(result.speed_order) == 4
    assert set(result.estimated_ultimate_turns) == {
        "1412",
        "1303",
        "1208",
        "1101",
    }
    assert result.observed_meta_score is None
    assert 0 <= result.mechanical_simulation_score <= 100
    assert 0 <= result.evidence_confidence <= 100
    assert 0 <= result.final_score <= 100


def test_negative_skill_point_rotation_scores_below_balanced_rotation() -> None:
    service = TeamSimulationService(DOCS_ROOT)
    common = {
        "game_data_version": "4.4.51",
        "speed": 100.0,
        "max_energy": 120.0,
        "estimated_ultimate_turns": 4.0,
        "skill_point_fields_found": True,
        "data_confidence": 1.0,
    }
    hungry = [
        CharacterCombatParameters(
            character_id=str(index),
            name=f"hungry-{index}",
            roles=["dps"],
            mechanic_tags=[],
            skill_point_delta=-1.0,
            **common,
        )
        for index in range(4)
    ]
    balanced = [
        CharacterCombatParameters(
            character_id=str(index),
            name=f"balanced-{index}",
            roles=["support"],
            mechanic_tags=[],
            skill_point_delta=0.25,
            **common,
        )
        for index in range(4)
    ]

    hungry_result = service.evaluate_parameters(hungry, structural_score=80)
    balanced_result = service.evaluate_parameters(balanced, structural_score=80)

    assert hungry_result.skill_point_balance < 0
    assert balanced_result.skill_point_balance > 0
    assert (
        hungry_result.mechanical_simulation_score
        < balanced_result.mechanical_simulation_score
    )


def test_version_mismatched_observed_meta_is_not_blended_into_final_score() -> None:
    service = TeamSimulationService(DOCS_ROOT)
    parameters = [
        CharacterCombatParameters(
            character_id=str(index),
            name=f"unit-{index}",
            roles=["dps" if index == 0 else "support"],
            mechanic_tags=[],
            game_data_version="4.4.51",
            speed=100.0 + index,
            max_energy=120.0,
            skill_point_delta=0.0,
            estimated_ultimate_turns=4.0,
            skill_point_fields_found=True,
            data_confidence=1.0,
        )
        for index in range(4)
    ]

    result = service.evaluate_parameters(
        parameters,
        structural_score=80,
        observed_meta={
            "game_version": "4.3.1",
            "score": 99,
            "sample_size": 12000,
            "source_url": "https://example.invalid/stats",
        },
    )

    assert result.observed_meta_score is None
    assert any("跨版本" in warning for warning in result.warnings)
