import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.services.catalog_service import CatalogService
from app.services.progression_service import build_material_binding


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs-root", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()

    docs_root = args.docs_root.resolve()
    output_root = docs_root / "progression"
    output_root.mkdir(parents=True, exist_ok=True)
    if args.source:
        shutil.copyfile(args.source.resolve(), output_root / "source_material_rules.txt")

    catalog = CatalogService(docs_root)
    characters: dict[str, dict[str, str]] = {}
    issues: list[dict[str, object]] = []
    for character in catalog.list_characters():
        binding, missing = build_material_binding(catalog, character.id)
        characters[character.id] = binding
        if missing:
            issues.append(
                {
                    "character_id": character.id,
                    "name": character.name,
                    "missing": missing,
                }
            )

    payload = {
        "version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "binding_scope": "all_characters_visible_in_catalog",
        "character_count": len(characters),
        "characters": characters,
    }
    (output_root / "character_material_bindings.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = {
        "generated_at": payload["generated_at"],
        "coverage_basis": "character_catalog",
        "coverage_note": "材料绑定覆盖生成时角色图鉴展示的全部角色。",
        "character_count": len(characters),
        "complete_count": len(characters) - len(issues),
        "issue_count": len(issues),
        "issues": issues,
        "not_planned_in_current_version": [
            "经验书",
            "升级过程信用点",
            "行迹小节点",
            "额外能力",
            "属性节点",
        ],
    }
    (output_root / "progression_audit_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
