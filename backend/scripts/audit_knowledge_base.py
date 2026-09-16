import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
PLACEHOLDER_PATTERN = re.compile(r"#[0-9]+\[[A-Za-z]\]")
BAD_TITLE_MARKERS = ("'enhance':", "{'", "['", "\\n")
HTML_LIKE_PATTERN = re.compile(r"<[^>]+>")
NAME_PLACEHOLDER_PATTERN = re.compile(r"\{(?:NICKNAME|TEXTJOIN#[^}]+)\}")


@dataclass(frozen=True, slots=True)
class DatasetConfig:
    name: str
    root: Path
    content_dir: str
    id_field: str
    entry_type: str
    manifest_entries: str


@dataclass(slots=True)
class DatasetReport:
    name: str
    markdown_count: int = 0
    usable_count: int = 0
    rejected_count: int = 0
    json_count: int = 0
    placeholder_document_count: int = 0
    versions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_markdown(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_text(encoding="utf-8")
    match = FRONTMATTER_PATTERN.match(raw)
    if not match:
        raise ValueError("missing_frontmatter")
    metadata = yaml.safe_load(match.group(1))
    if not isinstance(metadata, dict):
        raise ValueError("invalid_frontmatter_object")
    return metadata, raw[match.end() :].strip()


def validate_manifest(config: DatasetConfig, report: DatasetReport) -> dict[str, Any] | None:
    manifest_path = config.root / "manifest.json"
    if not manifest_path.exists():
        report.errors.append("manifest.json: missing")
        return None
    try:
        manifest = read_json(manifest_path)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        report.errors.append(f"manifest.json: invalid_json:{exc}")
        return None

    entries = manifest.get(config.manifest_entries)
    if entries is None and config.manifest_entries != "entries":
        report.errors.append(f"manifest.json: missing_entries:{config.manifest_entries}")
    elif entries is None:
        entries = manifest.get("entries")
    if entries is not None and len(entries) != report.markdown_count:
        report.errors.append(
            f"manifest.json: entry_count_mismatch manifest={len(entries)} files={report.markdown_count}"
        )

    declared_count = manifest.get("split_markdown_count")
    if declared_count is not None and declared_count != report.markdown_count:
        report.errors.append(
            f"manifest.json: split_count_mismatch declared={declared_count} files={report.markdown_count}"
        )

    for item in entries or []:
        filename = item.get("filename")
        if filename and not (config.root / config.content_dir / filename).exists():
            report.errors.append(f"manifest.json: missing_file:{filename}")
        if item.get("error") and not filename:
            entry_id = str(item.get(config.id_field, ""))
            recovered = list((config.root / config.content_dir).glob(f"{entry_id}_*.md"))
            if recovered:
                report.warnings.append(
                    f"manifest_stale_recovered_file:{entry_id}:{recovered[0].name}"
                )
    return manifest


def validate_item_json(config: DatasetConfig, report: DatasetReport) -> None:
    if config.name != "items":
        return
    normalized_path = config.root / "hsr_items.json"
    raw_path = config.root / "item_all.raw.json"
    if not normalized_path.exists() or not raw_path.exists():
        report.errors.append("item_json_pair_missing")
        return
    try:
        normalized = read_json(normalized_path)
        raw = read_json(raw_path)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return  # The generic JSON pass records the detailed parse error.
    if not isinstance(normalized, dict) or not isinstance(raw, dict):
        report.errors.append("item_json_root_must_be_object")
        return
    if len(normalized) != report.markdown_count:
        report.errors.append(
            f"normalized_json_count_mismatch json={len(normalized)} markdown={report.markdown_count}"
        )
    if set(normalized) != set(raw):
        report.errors.append("raw_normalized_key_mismatch")
    bad_ids = sorted(
        key for key, item in normalized.items() if str(item.get("id", "")) != str(key)
    )
    if bad_ids:
        report.errors.append(f"normalized_json_internal_id_mismatch:{bad_ids[:20]}")

    markdown_by_id: dict[str, str] = {}
    for path in (config.root / config.content_dir).glob("*.md"):
        try:
            metadata, _ = parse_markdown(path)
        except (UnicodeDecodeError, yaml.YAMLError, ValueError):
            continue
        markdown_by_id[str(metadata.get("item_id", ""))] = str(metadata.get("title", ""))
    if set(markdown_by_id) != set(normalized):
        report.errors.append("normalized_json_markdown_id_set_mismatch")
    def clean_name(value: str) -> str:
        return NAME_PLACEHOLDER_PATTERN.sub("", HTML_LIKE_PATTERN.sub("", value))

    title_mismatches = []
    for key, item in normalized.items():
        raw_name = str(item.get("item_name", ""))
        if not raw_name or raw_name.startswith("{TEXTJOIN#"):
            continue
        if markdown_by_id.get(key) != clean_name(raw_name):
            title_mismatches.append(key)
    if title_mismatches:
        report.errors.append(f"normalized_json_markdown_title_mismatch:{title_mismatches[:20]}")


def audit_dataset(config: DatasetConfig) -> DatasetReport:
    report = DatasetReport(name=config.name)
    content_root = config.root / config.content_dir
    paths = sorted(content_root.glob("*.md")) if content_root.exists() else []
    report.markdown_count = len(paths)
    if not content_root.exists():
        report.errors.append(f"content_directory_missing:{content_root}")

    ids: list[str] = []
    titles: list[str] = []
    versions: set[str] = set()
    rejected_paths: set[Path] = set()

    required_fields = {
        "title",
        config.id_field,
        "game",
        "data_version",
        "language",
        "source_page",
        "source_data",
        "generated_at",
    }

    for path in paths:
        issues: list[str] = []
        try:
            metadata, content = parse_markdown(path)
        except (UnicodeDecodeError, yaml.YAMLError, ValueError) as exc:
            report.errors.append(f"{path.name}: {exc}")
            rejected_paths.add(path)
            continue

        missing = sorted(field for field in required_fields if not metadata.get(field))
        issues.extend(f"missing_metadata:{field}" for field in missing)

        entry_id = str(metadata.get(config.id_field, ""))
        title = str(metadata.get("title", ""))
        entry_type = str(metadata.get("entry_type", metadata.get("document_type", "")))
        version = str(metadata.get("data_version", ""))
        ids.append(entry_id)
        titles.append(title)
        if version:
            versions.add(version)

        if entry_type != config.entry_type:
            # The first character export used document_type before the common schema was introduced.
            legacy_character = (
                config.name == "characters"
                and metadata.get("document_type") == "hsr_character_knowledge"
            )
            if not legacy_character:
                issues.append(f"entry_type_mismatch:{entry_type}")
        if entry_id and not path.name.startswith(f"{entry_id}_"):
            issues.append("id_filename_mismatch")
        if not title or len(title) > 80 or "\n" in title or any(x in title for x in BAD_TITLE_MARKERS):
            issues.append("malformed_title")
        if config.name == "items" and title == entry_id:
            issues.append("missing_item_display_name")
        if not content or len(content) < 80:
            issues.append("empty_or_too_short_content")
        if "�" in content or "�" in title:
            issues.append("replacement_character_detected")
        if title and f"# {title}" not in content:
            issues.append("h1_title_mismatch")

        if PLACEHOLDER_PATTERN.search(content):
            report.placeholder_document_count += 1

        if issues:
            report.errors.append(f"{path.name}: {','.join(issues)}")
            rejected_paths.add(path)

    duplicate_ids = sorted(key for key, count in Counter(ids).items() if key and count > 1)
    if duplicate_ids:
        report.errors.append(f"duplicate_ids:{duplicate_ids}")
        for path in paths:
            try:
                metadata, _ = parse_markdown(path)
            except Exception:  # already recorded above
                continue
            if str(metadata.get(config.id_field, "")) in duplicate_ids:
                rejected_paths.add(path)

    duplicate_titles = sorted(key for key, count in Counter(titles).items() if key and count > 1)
    if duplicate_titles:
        report.warnings.append(f"duplicate_titles:{duplicate_titles}")

    report.rejected_count = len(rejected_paths)
    report.usable_count = report.markdown_count - report.rejected_count
    report.versions = sorted(versions)

    manifest = validate_manifest(config, report)
    json_paths = sorted(config.root.glob("*.json"))
    report.json_count = len(json_paths)
    for path in json_paths:
        try:
            read_json(path)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            report.errors.append(f"{path.name}: invalid_json:{exc}")

    validate_item_json(config, report)

    if manifest and isinstance(manifest.get("sha256"), dict):
        file_mapping = {
            "raw_json": manifest.get("raw_json_file"),
            "normalized_json": manifest.get("json_file"),
            "markdown": manifest.get("markdown_file"),
        }
        for key, expected in manifest["sha256"].items():
            filename = file_mapping.get(key)
            if filename and (config.root / filename).exists():
                actual = sha256(config.root / filename)
                if actual != expected:
                    report.errors.append(f"sha256_mismatch:{filename}")

    if report.placeholder_document_count:
        report.warnings.append(
            f"unresolved_display_placeholders:{report.placeholder_document_count}_documents"
        )
    if len(versions) > 1:
        report.warnings.append(f"mixed_versions:{sorted(versions)}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit all Star Rail knowledge exports.")
    parser.add_argument("--docs", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    configs = (
        DatasetConfig(
            "characters",
            args.docs / "hsr_nanoka_characters",
            "characters",
            "character_id",
            "hsr_character",
            "characters",
        ),
        DatasetConfig(
            "lightcones", args.docs / "lightcone", "lightcones", "entry_id", "hsr_lightcone", "entries"
        ),
        DatasetConfig("relics", args.docs / "relic", "relics", "entry_id", "hsr_relic_set", "entries"),
        DatasetConfig("monsters", args.docs / "monster", "monsters", "entry_id", "hsr_monster", "entries"),
        DatasetConfig(
            "items", args.docs / "hsr_nanoka_items", "items_markdown", "item_id", "hsr_item", "items"
        ),
    )
    reports = [audit_dataset(config) for config in configs]
    result = {
        "summary": {
            "markdown_count": sum(report.markdown_count for report in reports),
            "usable_count": sum(report.usable_count for report in reports),
            "rejected_count": sum(report.rejected_count for report in reports),
            "error_count": sum(len(report.errors) for report in reports),
            "warning_count": sum(len(report.warnings) for report in reports),
        },
        "datasets": [asdict(report) for report in reports],
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
