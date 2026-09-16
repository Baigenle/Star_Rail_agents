from pathlib import Path

from app.schemas.custom_character import CustomCharacterPayload
from app.services.fabrication_detector import FabricationDetector


def test_detector_finds_placeholders_official_name_and_duplicated_skills(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "hsr_nanoka_characters" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        '{"characters": [{"character_id": "1013", "name": "黑塔"}]}',
        encoding="utf-8",
    )
    payload = CustomCharacterPayload(
        name="黑塔",
        rarity=5,
        element="冰",
        path="智识",
        summary="待填123",
        roles=["主C"],
        core_mechanics="通过攻击造成伤害。",
        base_stats={
            "hp": 1000,
            "attack": 500,
            "defence": 450,
            "speed": 100,
            "taunt": 75,
            "energy": 120,
        },
        skills={
            "basic": "对敌方单体造成大量伤害。",
            "skill": "对敌方单体造成大量伤害。",
            "ultimate": "TODO",
            "talent": "aaaa",
            "technique": "test",
        },
    )

    issues = FabricationDetector(tmp_path).detect(payload)
    issue_keys = {(issue.field, issue.code) for issue in issues}

    assert ("name", "official_name_collision") in issue_keys
    assert ("summary", "placeholder_text") in issue_keys
    assert ("skills.basic", "duplicated_skill_text") in issue_keys
    assert any(issue.severity == "error" for issue in issues)


def test_detector_accepts_distinct_meaningful_descriptions(tmp_path: Path) -> None:
    payload = CustomCharacterPayload(
        name="星澜",
        rarity=5,
        element="量子",
        path="虚无",
        summary="记录敌人的观测结果，为量子队创造稳定的输出窗口。",
        roles=["辅助"],
        core_mechanics="战技施加观测标记降低抗性，终结技延长标记并提高队伍伤害。",
        base_stats={
            "hp": 1080,
            "attack": 520,
            "defence": 470,
            "speed": 105,
            "taunt": 100,
            "energy": 120,
        },
        skills={
            "basic": "对指定敌方单体造成量子属性伤害。",
            "skill": "施加持续两回合的观测标记，使目标量子抗性降低。",
            "ultimate": "延长全部观测标记，并提高我方全体造成的量子伤害。",
            "talent": "队友攻击标记目标后，为星澜积累一层演算。",
            "technique": "进入战斗时为随机敌人施加一层观测标记。",
        },
    )

    issues = FabricationDetector(tmp_path).detect(payload)

    assert not [issue for issue in issues if issue.severity == "error"]
