import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
BAD_TITLE_MARKERS = ("'enhance':", "{'", "['", "\\n")


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    name: str
    relative_directory: str
    id_field: str
    entry_type: str


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    path: Path
    entry_id: str
    entry_type: str
    title: str
    content: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RejectedDocument:
    path: Path
    reasons: tuple[str, ...]


DATASET_SPECS = (
    DatasetSpec("characters", "hsr_nanoka_characters/characters", "character_id", "hsr_character"),
    DatasetSpec("lightcones", "lightcone/lightcones", "entry_id", "hsr_lightcone"),
    DatasetSpec("relics", "relic/relics", "entry_id", "hsr_relic_set"),
    DatasetSpec("monsters", "monster/monsters", "entry_id", "hsr_monster"),
    DatasetSpec("items", "hsr_nanoka_items/items_markdown", "item_id", "hsr_item"),
    DatasetSpec(
        "character_supplements",
        "normalized_supplements/characters",
        "character_id",
        "hsr_character",
    ),
    DatasetSpec(
        "lightcone_supplements",
        "normalized_supplements/lightcones",
        "entry_id",
        "hsr_lightcone",
    ),
    DatasetSpec(
        "relic_supplements",
        "normalized_supplements/relics",
        "entry_id",
        "hsr_relic_set",
    ),
)

JSONL_DATASET_SPECS = (
    (
        "data_character_story/trailblaze_story_chunks.jsonl",
        "hsr_story",
        "mission_id",
        "mission_name",
    ),
    (
        "data_lore_pages/lore_sections.jsonl",
        "hsr_lore",
        "document_id",
        "heading",
    ),
)


def _parse(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_text(encoding="utf-8")
    match = FRONTMATTER_PATTERN.match(raw)
    if not match:
        raise ValueError("missing_frontmatter")
    metadata = yaml.safe_load(match.group(1))
    if not isinstance(metadata, dict):
        raise ValueError("invalid_frontmatter")
    return metadata, raw[match.end() :].strip()


def _quality_issues(
    path: Path, spec: DatasetSpec, metadata: dict[str, Any], content: str
) -> list[str]:
    issues: list[str] = []
    entry_id = str(metadata.get(spec.id_field, ""))
    title = str(metadata.get("title", ""))
    required = (
        spec.id_field,
        "title",
        "game",
        "data_version",
        "language",
        "source_page",
        "source_data",
        "generated_at",
    )
    issues.extend(f"missing:{field}" for field in required if not metadata.get(field))
    if not entry_id or not path.name.startswith(f"{entry_id}_"):
        issues.append("id_filename_mismatch")
    if not title or len(title) > 80 or "\n" in title or any(x in title for x in BAD_TITLE_MARKERS):
        issues.append("malformed_title")
    if spec.entry_type == "hsr_item" and title == entry_id:
        issues.append("missing_item_display_name")
    if len(content) < 80:
        issues.append("content_too_short")
    if "�" in title or "�" in content:
        issues.append("replacement_character")
    return issues


def load_knowledge_documents(
    docs_root: Path,
) -> tuple[list[KnowledgeDocument], list[RejectedDocument]]:
    accepted: list[KnowledgeDocument] = []
    rejected: list[RejectedDocument] = []

    for spec in DATASET_SPECS:
        directory = docs_root / spec.relative_directory
        for path in sorted(directory.glob("*.md")):
            try:
                metadata, content = _parse(path)
            except (UnicodeDecodeError, yaml.YAMLError, ValueError) as exc:
                rejected.append(RejectedDocument(path, (str(exc),)))
                continue
            issues = _quality_issues(path, spec, metadata, content)
            if issues:
                rejected.append(RejectedDocument(path, tuple(issues)))
                continue
            normalized_metadata = dict(metadata)
            normalized_metadata["entry_id"] = str(metadata[spec.id_field])
            normalized_metadata["entry_type"] = spec.entry_type
            accepted.append(
                KnowledgeDocument(
                    path=path,
                    entry_id=normalized_metadata["entry_id"],
                    entry_type=spec.entry_type,
                    title=str(metadata["title"]),
                    content=content,
                    metadata=normalized_metadata,
                )
            )
    for relative_path, entry_type, id_field, title_field in JSONL_DATASET_SPECS:
        path = docs_root / relative_path
        if not path.is_file():
            continue
        for line_number, raw_line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not raw_line.strip():
                continue
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError:
                rejected.append(
                    RejectedDocument(
                        path,
                        (f"invalid_json:line_{line_number}",),
                    )
                )
                continue
            required = ("chunk_id", id_field, title_field, "content", "source_url")
            missing = [
                field for field in required if not payload.get(field)
            ]
            if missing:
                rejected.append(
                    RejectedDocument(
                        path,
                        (
                            f"line_{line_number}:"
                            + ",".join(f"missing:{field}" for field in missing),
                        ),
                    )
                )
                continue
            metadata = dict(payload)
            metadata.update(
                {
                    "entry_id": str(payload[id_field]),
                    "entry_type": entry_type,
                    "data_version": str(
                        payload.get("version")
                        or (
                            f"revision-{payload['source_revision_id']}"
                            if payload.get("source_revision_id")
                            else ""
                        )
                    ),
                    "source_page": str(payload["source_url"]),
                    "generated_at": str(
                        payload.get("source_updated_at") or ""
                    ),
                }
            )
            accepted.append(
                KnowledgeDocument(
                    path=path,
                    entry_id=metadata["entry_id"],
                    entry_type=entry_type,
                    title=str(payload[title_field]),
                    content=str(payload["content"]).strip(),
                    metadata=metadata,
                )
            )
    return accepted, rejected
