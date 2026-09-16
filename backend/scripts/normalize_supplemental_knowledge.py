import argparse
import json
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
SELECTED_CHARACTER_SECTIONS = (
    "角色晋阶",
    "角色星魂",
    "光锥推荐",
    "遗器推荐",
    "配队推荐",
    "角色攻略推荐",
    "角色故事",
)
EXCLUDED_TITLES = {
    "## 内容一览",
    "关于开拓者笔记",
    "成就筛选",
    "敌对物种筛选",
    "光锥筛选",
    "角色筛选",
    "新人入坑",
}
MANUAL_ALIASES = {
    "仙舟三月七": ("character", "1224"),
    "丹恒饮月": ("character", "1213"),
    "阮梅": ("character", "1303"),
    "丹恒腾荒": ("character", "1414"),
    "千冶刃": ("character", "1507"),
    "姬子启行": ("character", "1510"),
    "知更鸟晴歌": ("character", "1512"),
    "砂金戏浪": ("character", "1513"),
    "三月七": ("character", "1001"),
}
CONTENT_ID_ALIASES = {
    "3124": ("character", "8001"),
    "3128": ("character", "8002"),
    "3123": ("character", "8003"),
    "3127": ("character", "8004"),
    "411": ("character", "8005"),
    "872": ("character", "8006"),
    "4441": ("character", "8007"),
    "4442": ("character", "8008"),
    "7046": ("character", "8009"),
    "7047": ("character", "8010"),
}


def normalize(value: str) -> str:
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", value).lower()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_markdown(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_text(encoding="utf-8")
    match = FRONTMATTER.match(raw)
    if not match:
        raise ValueError("missing_frontmatter")
    return yaml.safe_load(match.group(1)), raw[match.end() :].strip()


def section(body: str, heading: str) -> str:
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)", body, re.M | re.S
    )
    return match.group(1).strip() if match else ""


def master_maps(docs: Path) -> tuple[dict[str, list[dict[str, str]]], dict[str, dict[str, str]]]:
    by_name: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_kind_id: dict[str, dict[str, str]] = defaultdict(dict)

    characters = load_json(docs / "hsr_nanoka_characters" / "manifest.json")["characters"]
    lightcones = load_json(docs / "lightcone" / "manifest.json")["entries"]
    relics = load_json(docs / "relic" / "manifest.json")["entries"]
    items = load_json(docs / "hsr_nanoka_items" / "hsr_items.json")
    browser_assets = load_json(docs / "data" / "assets" / "browser_assets_manifest.json")
    character_overrides = load_json(docs / "character_catalog_overrides.json")

    def add(entry: dict[str, str]) -> None:
        existing = by_kind_id[entry["kind"]].get(entry["id"])
        if existing:
            return
        by_name[normalize(entry["name"])].append(entry)
        by_kind_id[entry["kind"]][entry["id"]] = entry["name"]

    for item in characters:
        name = str(item.get("name") or "").strip()
        if not name or len(name) > 40 or "'" in name:
            continue
        entry = {"kind": "character", "id": str(item["character_id"]), "name": name}
        add(entry)
    for entry_id, item in character_overrides.items():
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        by_kind_id["character"][str(entry_id)] = name
        key = normalize(name)
        if not any(
            entry["kind"] == "character" and entry["id"] == str(entry_id)
            for entry in by_name[key]
        ):
            by_name[key].append(
                {"kind": "character", "id": str(entry_id), "name": name}
            )
    for item in lightcones:
        entry = {"kind": "lightcone", "id": str(item["id"]), "name": str(item["name"])}
        add(entry)
    for item in relics:
        entry = {"kind": "relic", "id": str(item["id"]), "name": str(item["name"])}
        add(entry)
    for item_id, item in items.items():
        name = str(item.get("item_name") or "").strip()
        if not name or name == "...":
            continue
        entry = {"kind": "item", "id": str(item_id), "name": name}
        add(entry)
    # The browser asset inventory is newer than some Markdown manifests. It is
    # authoritative for entity IDs only when a local asset directory exists.
    for group, kind in (("characters", "character"), ("lightcones", "lightcone"), ("relics", "relic")):
        for entry_id, item in browser_assets.get(group, {}).items():
            name = str(item.get("name") or "").strip()
            asset_dir = docs / "data" / "assets" / group / str(entry_id)
            if name and asset_dir.is_dir():
                add({"kind": kind, "id": str(entry_id), "name": name})
    return by_name, by_kind_id


def resolve_entity(
    title: str,
    kind_hint: str,
    by_name: dict[str, list[dict[str, str]]],
    content_id: str = "",
) -> tuple[dict[str, str] | None, str, list[dict[str, str]]]:
    key = normalize(title)
    if content_id in CONTENT_ID_ALIASES:
        kind, entry_id = CONTENT_ID_ALIASES[content_id]
        return (
            {"kind": kind, "id": entry_id, "name": title},
            "content_id_alias",
            [],
        )
    if key in MANUAL_ALIASES:
        kind, entry_id = MANUAL_ALIASES[key]
        candidate = next(
            (item for item in by_name.get(key, []) if item["kind"] == kind and item["id"] == entry_id),
            {"kind": kind, "id": entry_id, "name": title},
        )
        return candidate, "manual_alias", by_name.get(key, [])
    candidates = [item for item in by_name.get(key, []) if item["kind"] == kind_hint]
    if len(candidates) == 1:
        return candidates[0], "exact_name", candidates
    all_candidates = by_name.get(key, [])
    if not candidates and len(all_candidates) == 1:
        return all_candidates[0], "exact_name_cross_type", all_candidates
    return None, "ambiguous" if candidates else "unmatched", candidates


def aligned_recommendations(
    body: str, heading: str, kind: str, by_name: dict[str, list[dict[str, str]]]
) -> tuple[list[dict[str, str]], list[str]]:
    content = section(body, heading)
    aligned: list[dict[str, str]] = []
    unresolved: list[str] = []
    seen: set[str] = set()
    for raw_line in content.splitlines():
        line = raw_line.strip().strip("-* ")
        if not line or len(line) > 40:
            continue
        candidates = [item for item in by_name.get(normalize(line), []) if item["kind"] == kind]
        if len(candidates) == 1 and candidates[0]["id"] not in seen:
            seen.add(candidates[0]["id"])
            aligned.append(candidates[0])
    # Descriptive lines and effect names in the scraped recommendation section
    # are not entity candidates. Only exact canonical-name matches are aligned;
    # non-matches are intentionally left as prose instead of becoming false
    # conflict records.
    return aligned, unresolved


def relic_set_info(docs: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for entry in load_json(docs / "relic" / "manifest.json")["entries"]:
        entry_id = str(entry["id"])
        text = (docs / "relic" / "relics" / str(entry["filename"])).read_text(encoding="utf-8")
        pieces = len(re.findall(r"^####\s+\d+\s*$", section(text, "其他结构化资料"), re.M))
        result[entry_id] = {
            "set_type": "cavern" if pieces == 4 else "planar",
            "piece_count": pieces,
        }
    return result


def aligned_relic_recommendations(
    body: str,
    by_name: dict[str, list[dict[str, str]]],
    set_info: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    content = section(body, "遗器推荐")
    canonical = [
        item
        for candidates in by_name.values()
        for item in candidates
        if item["kind"] == "relic"
    ]
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    current_type = ""
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "隧洞遗器" in line:
            current_type = "cavern"
            continue
        if "位面饰品" in line:
            current_type = "planar"
            continue
        key = normalize(line)
        matches = [item for item in canonical if normalize(item["name"]) in key]
        if not matches:
            continue
        matches.sort(key=lambda item: len(normalize(item["name"])), reverse=True)
        item = matches[0]
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        info = set_info.get(item["id"], {})
        result.append(
            {
                **item,
                # Canonical component count is authoritative. Community headings
                # occasionally place a cavern set below the planar heading.
                "set_type": info.get("set_type", "") or current_type,
                "piece_count": int(info.get("piece_count") or 0),
            }
        )
    return result


def selected_character_content(body: str) -> str:
    parts: list[str] = []
    for heading in SELECTED_CHARACTER_SECTIONS:
        value = section(body, heading)
        if value:
            parts.append(f"## {heading}\n\n{value}")
    return "\n\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Align community Markdown to canonical game IDs.")
    parser.add_argument("--docs", type=Path, required=True)
    args = parser.parse_args()
    docs = args.docs.resolve()
    source_dir = docs / "clean_markdown"
    output_root = docs / "normalized_supplements"
    staging = docs / ".normalized_supplements_staging"
    if staging.exists():
        shutil.rmtree(staging)
    (staging / "characters").mkdir(parents=True)
    (staging / "lightcones").mkdir(parents=True)
    (staging / "relics").mkdir(parents=True)

    by_name, by_kind_id = master_maps(docs)
    set_info = relic_set_info(docs)
    report: dict[str, Any] = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_count": 0,
        "aligned": [],
        "conflicts": [],
        "excluded": [],
        "recommendation_conflicts": [],
        "relic_recommendation_gaps": [],
        "relic_supplements": [],
    }

    for path in sorted(source_dir.glob("*.md")):
        report["source_count"] += 1
        metadata, body = parse_markdown(path)
        title = str(metadata.get("title") or "").strip()
        content_id = str(metadata.get("content_id") or "")
        if title in EXCLUDED_TITLES:
            report["excluded"].append({"title": title, "content_id": content_id, "reason": "non_entity_page"})
            continue
        kind_hint = "lightcone" if re.search(r"## 基础信息\s+光锥", body) else "character"
        entity, method, candidates = resolve_entity(
            title, kind_hint, by_name, content_id
        )
        if not entity:
            report["conflicts"].append(
                {
                    "title": title,
                    "content_id": content_id,
                    "kind_hint": kind_hint,
                    "reason": method,
                    "candidates": candidates,
                }
            )
            continue

        canonical_name = by_kind_id[entity["kind"]].get(entity["id"], entity["name"])
        lightcones, unresolved_lc = aligned_recommendations(body, "光锥推荐", "lightcone", by_name)
        relics = aligned_relic_recommendations(body, by_name, set_info)
        unresolved_relic: list[str] = []
        if entity["kind"] == "character" and section(body, "遗器推荐"):
            present_types = {item["set_type"] for item in relics}
            missing_types = sorted({"cavern", "planar"} - present_types)
            if missing_types:
                report["relic_recommendation_gaps"].append(
                    {
                        "title": canonical_name,
                        "content_id": content_id,
                        "missing_types": missing_types,
                        "aligned": relics,
                    }
                )
        if unresolved_lc or unresolved_relic:
            report["recommendation_conflicts"].append(
                {
                    "title": title,
                    "content_id": content_id,
                    "unresolved_lightcone_lines": unresolved_lc,
                    "unresolved_relic_lines": unresolved_relic,
                }
            )

        output_metadata = {
            "title": canonical_name,
            "game": "崩坏：星穹铁道",
            "data_version": "community-current-2026-07-22",
            "language": "zh",
            "source_page": metadata.get("source_url"),
            "source_data": metadata.get("source_url"),
            "generated_at": report["generated_at"],
            "source_provider": "mihoyo_wiki",
            "source_priority": "secondary",
            "source_content_id": content_id,
            "alignment_method": method,
            "recommended_lightcones": lightcones,
            "recommended_relics": relics,
        }
        if entity["kind"] == "character":
            output_metadata["character_id"] = entity["id"]
            output_metadata["document_type"] = "hsr_character_supplement"
            content = selected_character_content(body)
            target_dir = staging / "characters"
        else:
            output_metadata["entry_id"] = entity["id"]
            output_metadata["document_type"] = "hsr_lightcone_supplement"
            content = body
            target_dir = staging / "lightcones"

        aligned_lines: list[str] = []
        if lightcones:
            aligned_lines.append("## 光锥推荐实体对齐\n\n" + "\n".join(
                f"- {item['name']}（光锥 ID：{item['id']}）" for item in lightcones
            ))
        if relics:
            aligned_lines.append("## 遗器推荐实体对齐\n\n" + "\n".join(
                f"- {item['name']}（遗器套装 ID：{item['id']}）" for item in relics
            ))
        if aligned_lines:
            content = content + "\n\n" + "\n\n".join(aligned_lines)

        filename = f"{entity['id']}_{content_id}_{canonical_name}.md".replace("/", "_")
        target = target_dir / filename
        target.write_text(
            "---\n"
            + yaml.safe_dump(output_metadata, allow_unicode=True, sort_keys=False).strip()
            + "\n---\n\n# "
            + canonical_name
            + "\n\n"
            + content.strip()
            + "\n",
            encoding="utf-8",
        )
        report["aligned"].append(
            {
                "title": title,
                "canonical_name": canonical_name,
                "canonical_id": entity["id"],
                "kind": entity["kind"],
                "content_id": content_id,
                "method": method,
                "path": str(target.relative_to(staging)).replace("\\", "/"),
                "recommended_lightcones": lightcones,
                "recommended_relics": relics,
            }
        )

    for path in sorted((docs / "clean_relic").glob("*.md")):
        metadata, body = parse_markdown(path)
        title = str(metadata.get("title") or "").strip()
        content_id = str(metadata.get("content_id") or "")
        entity, method, candidates = resolve_entity(
            title, "relic", by_name, content_id
        )
        if not entity or entity["kind"] != "relic":
            report["conflicts"].append(
                {
                    "title": title,
                    "content_id": content_id,
                    "kind_hint": "relic",
                    "reason": method,
                    "candidates": candidates,
                }
            )
            continue
        canonical_name = by_kind_id["relic"].get(entity["id"], entity["name"])
        info = set_info.get(entity["id"], {})
        output_metadata = {
            "title": canonical_name,
            "game": "崩坏：星穹铁道",
            "data_version": "community-current-2026-07-22",
            "language": "zh",
            "source_page": metadata.get("source_url"),
            "source_data": metadata.get("source_url"),
            "generated_at": report["generated_at"],
            "source_provider": "mihoyo_wiki",
            "source_priority": "secondary",
            "source_content_id": content_id,
            "alignment_method": method,
            "entry_id": entity["id"],
            "document_type": "hsr_relic_supplement",
            "set_type": info.get("set_type"),
            "piece_count": info.get("piece_count"),
        }
        filename = f"{entity['id']}_{content_id}_{canonical_name}.md".replace("/", "_")
        target = staging / "relics" / filename
        target.write_text(
            "---\n"
            + yaml.safe_dump(output_metadata, allow_unicode=True, sort_keys=False).strip()
            + "\n---\n\n# "
            + canonical_name
            + "\n\n"
            + body.strip()
            + "\n",
            encoding="utf-8",
        )
        report["relic_supplements"].append(
            {
                "title": title,
                "canonical_name": canonical_name,
                "canonical_id": entity["id"],
                "content_id": content_id,
                "method": method,
                **info,
                "path": str(target.relative_to(staging)).replace("\\", "/"),
            }
        )

    (staging / "alignment_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = [
        "# 补充知识实体对齐报告",
        "",
        f"- 原始文档：{report['source_count']}",
        f"- 已对齐：{len(report['aligned'])}",
        f"- 实体冲突/未确认：{len(report['conflicts'])}",
        f"- 排除非实体页面：{len(report['excluded'])}",
        f"- 推荐条目需复核：{len(report['recommendation_conflicts'])}",
        f"- 遗器补充文档已对齐：{len(report['relic_supplements'])}",
        f"- 角色遗器推荐缺少类型：{len(report['relic_recommendation_gaps'])}",
        "",
        "## 实体冲突与未确认",
        "",
    ]
    summary.extend(
        f"- {item['title']}（content_id={item['content_id']}）：{item['reason']}"
        for item in report["conflicts"]
    )
    summary.extend(["", "## 排除页面", ""])
    summary.extend(
        f"- {item['title']}（content_id={item['content_id']}）：{item['reason']}"
        for item in report["excluded"]
    )
    (staging / "alignment_report.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    if output_root.exists():
        shutil.rmtree(output_root)
    staging.replace(output_root)
    print(f"source={report['source_count']}")
    print(f"aligned={len(report['aligned'])}")
    print(f"conflicts={len(report['conflicts'])}")
    print(f"excluded={len(report['excluded'])}")
    print(f"recommendation_conflicts={len(report['recommendation_conflicts'])}")
    print(f"relic_supplements={len(report['relic_supplements'])}")
    print(f"relic_recommendation_gaps={len(report['relic_recommendation_gaps'])}")


if __name__ == "__main__":
    main()
