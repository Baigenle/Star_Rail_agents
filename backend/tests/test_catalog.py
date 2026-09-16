from pathlib import Path

from app.services.catalog_service import CatalogService


DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs"


def test_character_catalog_and_detail() -> None:
    service = CatalogService(DOCS_ROOT)

    characters = service.list_characters(search="刻律德菈")
    detail = service.get_character("1412")

    assert len(characters) == 1
    assert characters[0].image_url
    assert detail is not None
    assert detail.name == "刻律德菈"
    assert detail.stats["生命值"] == "1358"
    assert len(detail.skills) >= 5
    assert len(detail.eidolons) == 6
    assert any(item.id == "110435" for item in detail.related_items)


def test_related_item_has_local_image_and_source() -> None:
    service = CatalogService(DOCS_ROOT)

    item = service.get_item("110435")

    assert item is not None
    assert item.name == "暮晖烬蕾"
    assert item.image_url == "/api/v1/assets/items/110435/raw/110435.webp"
    assert "凝滞虚影" in item.sources[0]


def test_character_detail_data_quality_rules() -> None:
    service = CatalogService(DOCS_ROOT)

    for summary in service.list_characters():
        detail = service.get_character(summary.id)
        assert detail is not None
        assert len(detail.related_items) == 9
        assert sum(item.type == "WeeklyMonsterDrop" for item in detail.related_items) == 2
        assert all(skill.type != "MazeNormal" for skill in detail.skills)
        assert all("#" not in eidolon.description for eidolon in detail.eidolons)
        assert all(
            (relic.set_type == "cavern" and relic.piece_count == 4)
            or (relic.set_type == "planar" and relic.piece_count == 2)
            for relic in detail.recommended_relics
        )


def test_special_path_skill_entries_are_complete() -> None:
    service = CatalogService(DOCS_ROOT)

    remembrance = service.get_character("1413")
    elation = service.get_character("1501")

    assert remembrance is not None
    assert {"忆灵技", "忆灵天赋"} <= {skill.type for skill in remembrance.skills}
    assert elation is not None
    assert any(skill.type == "欢愉技" and skill.image_url for skill in elation.skills)


def test_recovered_character_labels_and_trailblazer_variants() -> None:
    service = CatalogService(DOCS_ROOT)
    expected_names = {
        "1213": "丹恒·饮月",
        "1303": "阮·梅",
        "1414": "丹恒·腾荒",
        "1507": "千冶·刃",
        "1510": "姬子·启行",
        "8001": "开拓者·毁灭（穹）",
        "8002": "开拓者·毁灭（星）",
        "8003": "开拓者·存护（穹）",
        "8004": "开拓者·存护（星）",
        "8005": "开拓者·同谐（穹）",
        "8006": "开拓者·同谐（星）",
        "8007": "开拓者·记忆（穹）",
        "8008": "开拓者·记忆（星）",
        "8009": "开拓者·欢愉（穹）",
        "8010": "开拓者·欢愉（星）",
    }

    characters = {item.id: item for item in service.list_characters()}
    assert len(characters) == 95
    assert {item.id for item in service.list_characters(search="丹恒饮月")} == {"1213"}
    assert {item.id for item in service.list_characters(search="开拓者欢愉")} == {
        "8009",
        "8010",
    }
    for character_id, expected_name in expected_names.items():
        assert characters[character_id].name == expected_name
        detail = service.get_character(character_id)
        assert detail is not None
        assert detail.name == expected_name
        assert detail.image_url
        assert detail.portrait_url
        assert len(detail.skills) >= 5
        assert len(detail.eidolons) == 6

    remembrance = service.get_character("8007")
    elation = service.get_character("8009")
    assert remembrance is not None
    assert {"忆灵技", "忆灵天赋"} <= {skill.type for skill in remembrance.skills}
    assert elation is not None
    assert any(skill.type == "欢愉技" and skill.image_url for skill in elation.skills)
