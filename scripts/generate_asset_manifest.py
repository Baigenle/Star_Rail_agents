from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSET_ROOT = ROOT / "docs" / "data" / "assets"
ASSET_EXTENSIONS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".svg"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def assets(asset_root: Path) -> list[Path]:
    checksum_path = asset_root / "assets_manifest.sha256"
    summary_path = asset_root / "assets_manifest_summary.json"
    return sorted(
        path
        for path in asset_root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in ASSET_EXTENSIONS
        and path not in {checksum_path, summary_path}
    )


def generate(asset_root: Path) -> int:
    asset_root.mkdir(parents=True, exist_ok=True)
    checksum_path = asset_root / "assets_manifest.sha256"
    summary_path = asset_root / "assets_manifest_summary.json"
    files = assets(asset_root)
    lines: list[str] = []
    extensions: Counter[str] = Counter()
    directories: Counter[str] = Counter()
    total_bytes = 0
    for path in files:
        relative = path.relative_to(asset_root).as_posix()
        size = path.stat().st_size
        total_bytes += size
        extensions[path.suffix.lower()] += 1
        directories[relative.split("/", 1)[0]] += 1
        lines.append(f"{digest(path)}  {relative}")
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary_path.write_text(
        json.dumps(
            {
                "root": (
                    "docs/data/assets"
                    if asset_root == DEFAULT_ASSET_ROOT.resolve()
                    else str(asset_root)
                ),
                "algorithm": "sha256",
                "file_count": len(files),
                "total_bytes": total_bytes,
                "by_extension": dict(sorted(extensions.items())),
                "by_top_level_directory": dict(sorted(directories.items())),
                "checksum_file": checksum_path.name,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


def check(asset_root: Path) -> int:
    checksum_path = asset_root / "assets_manifest.sha256"
    if not checksum_path.is_file():
        raise SystemExit("checksum manifest is missing")
    expected = {}
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        checksum, relative = line.split("  ", 1)
        expected[relative] = checksum
    current = {
        path.relative_to(asset_root).as_posix(): digest(path) for path in assets(asset_root)
    }
    missing = sorted(set(expected) - set(current))
    added = sorted(set(current) - set(expected))
    changed = sorted(
        relative
        for relative in set(expected) & set(current)
        if expected[relative] != current[relative]
    )
    if missing or added or changed:
        print(
            json.dumps(
                {"missing": missing, "added": added, "changed": changed},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    print(f"verified {len(current)} assets")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(os.getenv("GAME_ASSETS_PATH", DEFAULT_ASSET_ROOT)),
        help="图片资源根目录；默认读取 GAME_ASSETS_PATH 或 docs/data/assets。",
    )
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    selected_root = arguments.root.expanduser()
    if not selected_root.is_absolute():
        selected_root = ROOT / selected_root
    selected_root = selected_root.resolve()
    raise SystemExit(check(selected_root) if arguments.check else generate(selected_root))
