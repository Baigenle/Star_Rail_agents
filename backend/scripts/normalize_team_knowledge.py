import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.services.catalog_service import CatalogService


ROLE_BY_PATH = {
    "丰饶": ["sustain"],
    "存护": ["sustain"],
    "同谐": ["support"],
    "巡猎": ["dps"],
    "智识": ["dps"],
    "毁灭": ["dps"],
    "虚无": ["support", "sub_dps"],
    "记忆": ["dps", "sub_dps"],
    "欢愉": ["dps", "sub_dps"],
}
TAG_KEYWORDS = {
    "减抗": ("减抗", "抗性降低", "抗性穿透", "弱点"),
    "减防": ("减防", "防御力降低", "无视目标", "无视防御"),
    "击破": ("击破", "超击破", "削韧"),
    "持续伤害": ("持续伤害", "灼烧", "裂伤", "触电", "风化"),
    "追加攻击": ("追加攻击", "追击"),
    "召唤": ("忆灵", "召唤物", "神君", "账账"),
    "治疗": ("治疗", "回复生命"),
    "护盾": ("护盾", "提供护盾"),
    "拉条": ("行动提前", "立即行动", "拉条"),
    "能量": ("恢复能量", "能量恢复"),
    "暴击": ("暴击率", "暴击伤害"),
}
HEADER_PATTERN = re.compile(r"^(?:主[cC]|主C|副[cC]|副C|辅C|辅助|生存|治疗)(?:[/／].+)?$")


def normalize_name(value: str) -> str:
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", value).lower()


def frontmatter(raw: str) -> tuple[dict[str, object], str]:
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", raw, re.S)
    if not match:
        return {}, raw
    return yaml.safe_load(match.group(1)) or {}, match.group(2)


def section(text: str, name: str) -> str:
    match = re.search(
        rf"^##\s+{re.escape(name)}\s*$\n(.*?)(?=^##\s+|\Z)", text, re.M | re.S
    )
    return match.group(1).strip() if match else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs-root", type=Path, required=True)
    args = parser.parse_args()
    docs_root = args.docs_root.resolve()
    catalog = CatalogService(docs_root)
    characters = catalog.list_characters()
    name_index: defaultdict[str, list[str]] = defaultdict(list)
    for character in characters:
        name_index[normalize_name(character.name)].append(character.id)

    records: list[dict[str, object]] = []
    unresolved: list[dict[str, str]] = []
    cooccurrence: defaultdict[str, Counter[str]] = defaultdict(Counter)
    source_count = 0
    for path in sorted((docs_root / "normalized_supplements" / "characters").glob("*.md")):
        metadata, body = frontmatter(path.read_text(encoding="utf-8"))
        source_id = str(metadata.get("character_id") or "")
        team_text = section(body, "配队推荐")
        if not source_id or not team_text:
            continue
        source_count += 1
        teammate_ids: list[str] = []
        raw_names: list[str] = []
        for raw_line in team_text.splitlines():
            line = raw_line.strip().strip("-*")
            if (
                not line
                or line.startswith(("※", "推荐", "队伍"))
                or HEADER_PATTERN.match(line)
            ):
                continue
            raw_names.append(line)
            matches = name_index.get(normalize_name(line), [])
            if len(matches) == 1:
                teammate_ids.append(matches[0])
            else:
                unresolved.append(
                    {
                        "source_character_id": source_id,
                        "source_file": path.name,
                        "raw_name": line,
                        "reason": "ambiguous" if matches else "not_found",
                    }
                )
        teammate_ids = list(dict.fromkeys(x for x in teammate_ids if x != source_id))
        for teammate_id in teammate_ids:
            cooccurrence[source_id][teammate_id] += 1
            cooccurrence[teammate_id][source_id] += 1
        records.append(
            {
                "source_character_id": source_id,
                "source_file": str(path.relative_to(docs_root)).replace("\\", "/"),
                "source_url": metadata.get("source_page"),
                "raw_names": raw_names,
                "teammate_ids": teammate_ids,
                "team_groups": [
                    [source_id, *teammate_ids[index : index + 3]]
                    for index in range(0, len(teammate_ids), 3)
                    if len(teammate_ids[index : index + 3]) == 3
                ],
            }
        )

    overrides_path = docs_root / "team_profile_overrides.json"
    overrides = (
        json.loads(overrides_path.read_text(encoding="utf-8"))
        if overrides_path.is_file()
        else {}
    )
    profiles: dict[str, dict[str, object]] = {}
    low_confidence: list[dict[str, object]] = []
    for character in characters:
        detail = catalog.get_character(character.id)
        searchable = " ".join(
            [
                detail.description if detail else "",
                *(skill.description for skill in detail.skills if detail),
            ]
        )
        roles = ROLE_BY_PATH.get(character.path, ["sub_dps"])
        tags = [
            tag
            for tag, keywords in TAG_KEYWORDS.items()
            if any(keyword in searchable for keyword in keywords)
        ]
        override = overrides.get(character.id, {})
        roles = list(override.get("roles", roles))
        tags = sorted(set(tags) | set(override.get("mechanic_tags", [])))
        confidence = 0.9 if override else (0.8 if tags else 0.55)
        profile = {
            "character_id": character.id,
            "name": character.name,
            "element": character.element,
            "path": character.path,
            "roles": roles,
            "mechanic_tags": tags,
            "confidence": confidence,
            "source": "official_catalog_and_normalized_supplement",
        }
        profiles[character.id] = profile
        if confidence < 0.7:
            low_confidence.append(profile)

    output_root = docs_root / "team_knowledge"
    output_root.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    (output_root / "normalized_team_recommendations.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "source_count": source_count,
                "records": records,
                "cooccurrence": {
                    source: dict(counter) for source, counter in cooccurrence.items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_root / "official_combat_profiles.json").write_text(
        json.dumps(
            {"generated_at": generated_at, "characters": profiles},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report = {
        "generated_at": generated_at,
        "source_count": source_count,
        "record_count": len(records),
        "unresolved_count": len(unresolved),
        "unresolved": unresolved,
        "low_confidence_count": len(low_confidence),
        "low_confidence_profiles": low_confidence,
    }
    (output_root / "team_alignment_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in report.items() if key not in {"unresolved", "low_confidence_profiles"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
