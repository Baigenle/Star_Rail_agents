import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse


SOURCE_ORIGIN = "https://bbs.mihoyo.com"
ROW_CLASS = "obc-tmpl__filter-row"
CONTENT_ID_PATTERN = re.compile(r"/content/(\d+)/")
SECTION_PATTERN = re.compile(r"^[▌■]\s*(.+?)\s*$")
DETAIL_TITLE_PATTERN = re.compile(r"^[^●■▌\s].*：$")


class ActivityTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, Any]] = []
        self._row: dict[str, Any] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if tag == "tr" and ROW_CLASS in attributes.get("class", "").split():
            self._row = {
                "source_index": int(attributes.get("data-index", "-1")),
                "filter_tag": attributes.get("data-filter-tag", ""),
                "texts": [],
                "href": "",
                "image_source_url": "",
            }
            return
        if self._row is None:
            return
        if tag == "a" and not self._row["href"]:
            self._row["href"] = attributes.get("href", "")
        if tag == "img" and not self._row["image_source_url"]:
            self._row["image_source_url"] = (
                attributes.get("large") or attributes.get("src") or ""
            )

    def handle_data(self, data: str) -> None:
        if self._row is None:
            return
        value = re.sub(r"\s+", " ", data).strip()
        if value:
            self._row["texts"].append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _row_score(row: dict[str, Any]) -> tuple[int, int]:
    return (int(bool(row["image_source_url"])), len(row["texts"]))


def _normalize_row(row: dict[str, Any]) -> dict[str, Any] | None:
    filter_parts = row["filter_tag"].split()
    versions = [
        part.removeprefix("所属版本-")
        for part in filter_parts
        if part.startswith("所属版本-")
    ]
    types = [
        part.removeprefix("类型-")
        for part in filter_parts
        if part.startswith("类型-")
    ]
    tags = [
        part.removeprefix("活动标签-")
        for part in filter_parts
        if part.startswith("活动标签-")
    ]
    version = versions[0] if versions else ""
    texts = _unique(row["texts"])
    href = str(row["href"])
    title = texts[0] if texts else ""
    if not title or not version or not href:
        return None

    excluded = {title, f"{version}版本", *types, *tags}
    schedule = next(
        (
            value
            for value in texts
            if value not in excluded
            and (
                re.search(r"\d{4}/\d{1,2}/\d{1,2}", value)
                or "版本更新后" in value
                or "版本结束前" in value
            )
        ),
        "",
    )
    content_id_match = CONTENT_ID_PATTERN.search(href)
    return {
        "source_index": int(row["source_index"]),
        "source_content_id": content_id_match.group(1) if content_id_match else "",
        "title": title,
        "version": version,
        "schedule": schedule,
        "types": _unique(types),
        "tags": _unique(tags),
        "source_url": urljoin(SOURCE_ORIGIN, href),
        "image_source_url": str(row["image_source_url"]),
    }


def parse_activity_rows(html: str) -> list[dict[str, Any]]:
    parser = ActivityTableParser()
    parser.feed(html)
    preferred: dict[int, dict[str, Any]] = {}
    for row in parser.rows:
        source_index = int(row["source_index"])
        existing = preferred.get(source_index)
        if existing is None or _row_score(row) > _row_score(existing):
            preferred[source_index] = row

    normalized = [
        item
        for source_index in sorted(preferred)
        if (item := _normalize_row(preferred[source_index])) is not None
    ]
    return normalized


def parse_activity_details(raw: str) -> dict[str, dict[str, Any]]:
    activities: dict[str, dict[str, Any]] = {}
    current_title = ""
    current_section: dict[str, Any] | None = None

    for raw_line in raw.replace("\r\n", "\n").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if DETAIL_TITLE_PATTERN.match(line):
            current_title = line[:-1].strip()
            activities[current_title] = {"sections": []}
            current_section = None
            continue
        if not current_title:
            continue
        section_match = SECTION_PATTERN.match(line)
        if section_match:
            current_section = {
                "title": section_match.group(1).strip(),
                "paragraphs": [],
            }
            activities[current_title]["sections"].append(current_section)
            continue
        paragraph = re.sub(r"^[●•]\s*", "", line).strip()
        if not paragraph:
            continue
        if current_section is None:
            current_section = {"title": "活动说明", "paragraphs": []}
            activities[current_title]["sections"].append(current_section)
        current_section["paragraphs"].append(paragraph)

    return activities


def _asset_index(assets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for asset in assets:
        url_name = Path(urlparse(str(asset.get("url", ""))).path).name
        path_name = Path(str(asset.get("path", ""))).name
        for name in (url_name, path_name):
            if name:
                indexed[name] = asset
    return indexed


def _activity_id(row: dict[str, Any]) -> str:
    version = str(row["version"]).replace(".", "-")
    content_id = str(row["source_content_id"] or "external")
    return f"{version}-{content_id}-{row['source_index']}"


def build_activity_dataset(
    rows: list[dict[str, Any]],
    details: dict[str, dict[str, Any]],
    assets: list[dict[str, Any]],
    source_root: Path,
    *,
    generated_at: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    indexed_assets = _asset_index(assets)
    activities: list[dict[str, Any]] = []
    used_asset_paths: set[str] = set()
    missing_images: list[dict[str, Any]] = []
    remote_only_images: list[dict[str, Any]] = []
    missing_44_details: list[dict[str, Any]] = []

    for row in rows:
        image_name = Path(urlparse(str(row["image_source_url"])).path).name
        asset = indexed_assets.get(image_name)
        local_relative_path = str(asset.get("path", "")) if asset else ""
        local_exists = bool(
            local_relative_path
            and (source_root / local_relative_path).is_file()
        )
        image: dict[str, Any] | None = None
        if asset and local_exists:
            used_asset_paths.add(local_relative_path)
            image = {
                "source_url": row["image_source_url"],
                "api_path": f"/api/v1/activities/assets/{Path(local_relative_path).name}",
                "availability": "local",
                "sha256": asset.get("sha256", ""),
                "content_type": asset.get("content_type", ""),
            }
        else:
            image_issue = {
                "source_index": row["source_index"],
                "title": row["title"],
                "version": row["version"],
                "image_source_url": row["image_source_url"],
            }
            if row["image_source_url"]:
                image = {
                    "source_url": row["image_source_url"],
                    "api_path": None,
                    "availability": "remote_only",
                }
                remote_only_images.append(image_issue)
            else:
                missing_images.append(image_issue)

        is_current_version = row["version"] == "4.4"
        detail = details.get(str(row["title"])) if is_current_version else None
        if is_current_version and detail is None:
            missing_44_details.append(
                {
                    "source_index": row["source_index"],
                    "title": row["title"],
                }
            )
        activity = {
            "id": _activity_id(row),
            "title": row["title"],
            "version": row["version"],
            "schedule": row["schedule"],
            "types": row["types"],
            "tags": row["tags"],
            "image": image,
            "detail_available": detail is not None,
            "official_guide_available": is_current_version,
            "community_submission_available": is_current_version,
            "source": {
                "content_id": row["source_content_id"],
                "url": row["source_url"],
                "source_index": row["source_index"],
            },
        }
        if detail is not None:
            activity["detail"] = detail
        activities.append(activity)

    referenced_assets = [
        {
            "filename": Path(path).name,
            "source_path": path,
            "api_path": f"/api/v1/activities/assets/{Path(path).name}",
            "sha256": indexed_assets[Path(path).name].get("sha256", ""),
            "content_type": indexed_assets[Path(path).name].get(
                "content_type", ""
            ),
        }
        for path in sorted(used_asset_paths)
    ]
    dataset = {
        "schema_version": 1,
        "generated_at": generated_at,
        "policy": {
            "detailed_version": "4.4",
            "historical_detail_enabled": False,
            "official_guides_version": "4.4",
            "community_submissions_version": "4.4",
        },
        "activities": activities,
        "assets": referenced_assets,
    }
    report = {
        "generated_at": generated_at,
        "activity_count": len(activities),
        "version_4_4_count": sum(
            activity["version"] == "4.4" for activity in activities
        ),
        "historical_count": sum(
            activity["version"] != "4.4" for activity in activities
        ),
        "detail_count": sum(
            activity["detail_available"] for activity in activities
        ),
        "referenced_asset_count": len(referenced_assets),
        "remote_only_image_count": len(remote_only_images),
        "remote_only_images": remote_only_images,
        "missing_image_count": len(missing_images),
        "missing_images": missing_images,
        "missing_4_4_detail_count": len(missing_44_details),
        "missing_4_4_details": missing_44_details,
        "unused_downloaded_asset_count": max(
            0, len(assets) - len(used_asset_paths)
        ),
    }
    return dataset, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs-root", type=Path, required=True)
    parser.add_argument(
        "--source-directory", default="content_1257_版本活动"
    )
    parser.add_argument("--output-directory", default="activity_knowledge")
    args = parser.parse_args()

    docs_root = args.docs_root.resolve()
    source_root = docs_root / args.source_directory
    source_metadata = json.loads(
        (source_root / "content_1257.json").read_text(encoding="utf-8")
    )
    rows = parse_activity_rows(
        (source_root / "page.html").read_text(encoding="utf-8")
    )
    details = parse_activity_details(
        (source_root / "活动简介.txt").read_text(encoding="utf-8")
    )
    dataset, report = build_activity_dataset(
        rows,
        details,
        list(source_metadata.get("assets", [])),
        source_root,
        generated_at=str(source_metadata.get("crawled_at", "")),
    )

    output_root = docs_root / args.output_directory
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "activities.json").write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_root / "activity_asset_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": dataset["schema_version"],
                "generated_at": dataset["generated_at"],
                "assets": dataset["assets"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_root / "activity_alignment_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key
                not in {
                    "remote_only_images",
                    "missing_images",
                    "missing_4_4_details",
                }
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
