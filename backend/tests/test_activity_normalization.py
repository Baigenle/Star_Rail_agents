import json
from pathlib import Path

from scripts.normalize_activity_knowledge import (
    build_activity_dataset,
    parse_activity_details,
    parse_activity_rows,
)


SAMPLE_HTML = """
<table>
  <tr data-filter-tag="类型-版本活动 类型-挑战活动 所属版本-4.4 活动标签-战斗"
      data-index="0" class="obc-tmpl__filter-row">
    <td><a href="/sr/wiki/content/5563/detail"><div>位面分裂</div></a></td>
    <td><span>4.4版本</span>
      <img large="https://cdn.example/plane.png" src="https://cdn.example/plane.png?resize=1">
    </td>
    <td><p>2026/07/27 04:00 - 2026/08/10 03:59</p></td>
    <td><p>版本活动</p><p>挑战活动</p></td>
    <td><p>战斗</p></td>
  </tr>
  <tr data-filter-tag="类型-版本活动 所属版本-4.3 活动标签-其他"
      data-index="1" class="obc-tmpl__filter-row">
    <td><a href="/sr/wiki/content/4000/detail"><div>往期活动</div></a></td>
    <td><span>4.3版本</span>
      <img large="https://cdn.example/history.png">
    </td>
    <td><p>2026/06/01 - 2026/06/10</p></td>
    <td><p>版本活动</p></td>
    <td><p>其他</p></td>
  </tr>
</table>
"""


def test_parse_activity_rows_extracts_stable_fields_and_deduplicates() -> None:
    rows = parse_activity_rows(SAMPLE_HTML)

    assert rows == [
        {
            "source_index": 0,
            "source_content_id": "5563",
            "title": "位面分裂",
            "version": "4.4",
            "schedule": "2026/07/27 04:00 - 2026/08/10 03:59",
            "types": ["版本活动", "挑战活动"],
            "tags": ["战斗"],
            "source_url": (
                "https://bbs.mihoyo.com/sr/wiki/content/5563/detail"
            ),
            "image_source_url": "https://cdn.example/plane.png",
        },
        {
            "source_index": 1,
            "source_content_id": "4000",
            "title": "往期活动",
            "version": "4.3",
            "schedule": "2026/06/01 - 2026/06/10",
            "types": ["版本活动"],
            "tags": ["其他"],
            "source_url": (
                "https://bbs.mihoyo.com/sr/wiki/content/4000/detail"
            ),
            "image_source_url": "https://cdn.example/history.png",
        },
    ]


def test_parse_activity_details_keeps_only_named_sections() -> None:
    details = parse_activity_details(
        """
位面分裂：

▌活动说明
●挑战模拟宇宙可获得双倍奖励。

■注意事项
●次数不会重置。

幻造：圣杯战争：

■活动说明
●使用概念礼装进行作战。
"""
    )

    assert details["位面分裂"] == {
        "sections": [
            {
                "title": "活动说明",
                "paragraphs": ["挑战模拟宇宙可获得双倍奖励。"],
            },
            {
                "title": "注意事项",
                "paragraphs": ["次数不会重置。"],
            },
        ]
    }
    assert details["幻造：圣杯战争"]["sections"][0]["paragraphs"] == [
        "使用概念礼装进行作战。"
    ]


def test_build_activity_dataset_only_enables_44_details_and_guides(
    tmp_path: Path,
) -> None:
    assets = [
        {
            "url": "https://cdn.example/plane.png?format=webp",
            "path": "assets/plane.png",
            "sha256": "plane-sha",
            "status": 200,
        },
        {
            "url": "https://cdn.example/history.png",
            "path": "assets/history.png",
            "sha256": "history-sha",
            "status": 200,
        },
    ]
    source = tmp_path / "content_1257_版本活动"
    source.mkdir()
    (source / "assets").mkdir()
    (source / "assets" / "plane.png").write_bytes(b"plane")
    (source / "assets" / "history.png").write_bytes(b"history")

    dataset, report = build_activity_dataset(
        parse_activity_rows(SAMPLE_HTML),
        {"位面分裂": {"sections": []}},
        assets,
        source,
    )

    current, historical = dataset["activities"]
    assert current["id"] == "4-4-5563-0"
    assert current["detail_available"] is True
    assert current["official_guide_available"] is True
    assert current["community_submission_available"] is True
    assert current["detail"] == {"sections": []}
    assert current["image"]["api_path"] == (
        "/api/v1/activities/assets/plane.png"
    )
    assert historical["detail_available"] is False
    assert historical["official_guide_available"] is False
    assert historical["community_submission_available"] is False
    assert "detail" not in historical
    assert report["activity_count"] == 2
    assert report["version_4_4_count"] == 1
    assert report["missing_image_count"] == 0
    assert json.dumps(dataset, ensure_ascii=False)


def test_build_activity_dataset_preserves_remote_image_when_local_file_is_missing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "content_1257_版本活动"
    source.mkdir()

    dataset, report = build_activity_dataset(
        parse_activity_rows(SAMPLE_HTML),
        {},
        [],
        source,
    )

    assert dataset["activities"][0]["image"] == {
        "source_url": "https://cdn.example/plane.png",
        "api_path": None,
        "availability": "remote_only",
    }
    assert report["remote_only_image_count"] == 2
    assert report["missing_image_count"] == 0
