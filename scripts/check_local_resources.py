from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_NAMES = ("bge-m3", "bge-reranker-v2-m3")
ASSET_CATEGORIES = ("characters", "items", "lightcones", "relics", "manifest")
KNOWLEDGE_FILES = (
    "hsr_nanoka_characters/manifest.json",
    "hsr_nanoka_items/hsr_items.json",
    "lightcone/manifest.json",
    "relic/manifest.json",
    "normalized_supplements/alignment_report.json",
    "data_character_story/trailblaze_story_chunks.jsonl",
    "data_lore_pages/lore_sections.jsonl",
    "activity_knowledge/activities.json",
    "progression/progression_rules.json",
    "progression/character_material_bindings.json",
    "team_knowledge/mechanism_profiles.json",
)


@dataclass(frozen=True, slots=True)
class ResourceCheck:
    level: str
    resource: str
    detail: str


def _resolve_path(value: str | None, default: Path, project_root: Path) -> Path:
    path = Path(value).expanduser() if value else default
    # Compose 将相对路径按项目根目录解析；检查脚本保持同一语义。
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()


def _weight_files(directory: Path) -> list[Path]:
    candidates = [directory / "pytorch_model.bin"]
    candidates.extend(directory.glob("*.safetensors"))
    return [path for path in candidates if path.is_file()]


def inspect_resources(
    project_root: Path,
    models_value: str | None = None,
    assets_value: str | None = None,
    knowledge_value: str | None = None,
    strict_assets: bool = False,
    strict_knowledge: bool = False,
) -> tuple[list[ResourceCheck], Path, Path, Path]:
    models_root = _resolve_path(
        models_value or os.getenv("BGE_MODELS_PATH"),
        Path("models"),
        project_root,
    )
    assets_root = _resolve_path(
        assets_value or os.getenv("GAME_ASSETS_PATH"),
        Path("docs/data/assets"),
        project_root,
    )
    knowledge_root = _resolve_path(
        knowledge_value
        or os.getenv("DOCS_ROOT")
        or os.getenv("KNOWLEDGE_DATA_PATH"),
        Path("docs"),
        project_root,
    )
    checks: list[ResourceCheck] = []

    for model_name in MODEL_NAMES:
        model_dir = models_root / model_name
        if not model_dir.is_dir():
            checks.append(ResourceCheck("error", model_name, f"缺少目录：{model_dir}"))
            continue
        if not (model_dir / "config.json").is_file():
            checks.append(ResourceCheck("error", model_name, "缺少 config.json"))
        if not _weight_files(model_dir):
            checks.append(
                ResourceCheck("error", model_name, "缺少 model.safetensors 或 pytorch_model.bin")
            )
        if not any((model_dir / name).is_file() for name in ("tokenizer.json", "tokenizer.model")):
            checks.append(ResourceCheck("warning", model_name, "未发现 tokenizer 文件"))
        if not any(item.resource == model_name and item.level == "error" for item in checks):
            checks.append(ResourceCheck("ok", model_name, f"模型目录可用：{model_dir}"))

    asset_level = "error" if strict_assets else "warning"
    if not assets_root.is_dir():
        checks.append(ResourceCheck(asset_level, "game-assets", f"图片目录不存在：{assets_root}"))
    else:
        missing = [name for name in ASSET_CATEGORIES if not (assets_root / name).is_dir()]
        if missing:
            checks.append(
                ResourceCheck(asset_level, "game-assets", f"缺少分类目录：{', '.join(missing)}")
            )
        else:
            checks.append(ResourceCheck("ok", "game-assets", f"图片分类目录完整：{assets_root}"))
        if not (assets_root / "assets_manifest.sha256").is_file():
            checks.append(
                ResourceCheck("warning", "game-assets", "未发现 assets_manifest.sha256，无法校验资源包")
            )

    missing_knowledge = [
        relative for relative in KNOWLEDGE_FILES if not (knowledge_root / relative).is_file()
    ]
    if missing_knowledge:
        level = "error" if strict_knowledge else "warning"
        checks.append(
            ResourceCheck(
                level,
                "knowledge-data",
                "缺少本地知识文件：" + ", ".join(missing_knowledge),
            )
        )
    else:
        checks.append(
            ResourceCheck("ok", "knowledge-data", f"知识目录可用：{knowledge_root}")
        )

    return checks, models_root, assets_root, knowledge_root


def main() -> int:
    # Windows 的控制台代码页可能不是 UTF-8；固定编码以保证 JSON 可被脚本稳定解析。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="检查 Star Rail Agents 的本地模型、图片和知识资源。"
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--models", help="覆盖 BGE_MODELS_PATH")
    parser.add_argument("--assets", help="覆盖 GAME_ASSETS_PATH")
    parser.add_argument("--knowledge", help="覆盖 DOCS_ROOT/KNOWLEDGE_DATA_PATH")
    parser.add_argument("--strict-assets", action="store_true", help="图片缺失时返回失败")
    parser.add_argument(
        "--strict-knowledge", action="store_true", help="核心知识文件缺失时返回失败"
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    checks, models_root, assets_root, knowledge_root = inspect_resources(
        args.project_root.resolve(),
        models_value=args.models,
        assets_value=args.assets,
        knowledge_value=args.knowledge,
        strict_assets=args.strict_assets,
        strict_knowledge=args.strict_knowledge,
    )
    if args.as_json:
        print(
            json.dumps(
                {
                    "models_root": str(models_root),
                    "assets_root": str(assets_root),
                    "knowledge_root": str(knowledge_root),
                    "checks": [asdict(item) for item in checks],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        labels = {"ok": "通过", "warning": "提醒", "error": "失败"}
        for item in checks:
            print(f"[{labels[item.level]}] {item.resource}: {item.detail}")

    return 1 if any(item.level == "error" for item in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
