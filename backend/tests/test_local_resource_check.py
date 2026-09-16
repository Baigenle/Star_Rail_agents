import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "check_local_resources.py"
MANIFEST_SCRIPT = PROJECT_ROOT / "scripts" / "generate_asset_manifest.py"


def _run_checker(project_root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(project_root), "--json", *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_checker_fails_when_local_models_are_missing(tmp_path: Path) -> None:
    result = _run_checker(tmp_path)
    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert {item["resource"] for item in payload["checks"] if item["level"] == "error"} == {
        "bge-m3",
        "bge-reranker-v2-m3",
    }


def test_checker_accepts_minimal_models_and_strict_asset_layout(tmp_path: Path) -> None:
    for model_name in ("bge-m3", "bge-reranker-v2-m3"):
        model_dir = tmp_path / "models" / model_name
        model_dir.mkdir(parents=True)
        (model_dir / "config.json").write_text("{}", encoding="utf-8")
        (model_dir / "model.safetensors").write_bytes(b"weights")
        (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

    assets = tmp_path / "docs" / "data" / "assets"
    for category in ("characters", "items", "lightcones", "relics", "manifest"):
        (assets / category).mkdir(parents=True)
    (assets / "assets_manifest.sha256").write_text("", encoding="utf-8")

    result = _run_checker(tmp_path, "--strict-assets")

    assert result.returncode == 0, result.stdout
    assert not any(
        item["level"] == "error" for item in json.loads(result.stdout)["checks"]
    )


def test_asset_manifest_supports_external_resource_directory(tmp_path: Path) -> None:
    assets = tmp_path / "external-assets"
    (assets / "characters" / "1001").mkdir(parents=True)
    image = assets / "characters" / "1001" / "1001.svg"
    image.write_text("<svg/>", encoding="utf-8")

    generated = subprocess.run(
        [sys.executable, str(MANIFEST_SCRIPT), "--root", str(assets)],
        check=False,
        capture_output=True,
        text=True,
    )
    checked = subprocess.run(
        [sys.executable, str(MANIFEST_SCRIPT), "--root", str(assets), "--check"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert generated.returncode == 0, generated.stderr
    assert checked.returncode == 0, checked.stdout
    summary = json.loads((assets / "assets_manifest_summary.json").read_text(encoding="utf-8"))
    assert summary["file_count"] == 1
    assert summary["root"] == str(assets.resolve())


def test_checker_reports_missing_local_knowledge_files(tmp_path: Path) -> None:
    result = _run_checker(tmp_path, "--strict-knowledge")
    payload = json.loads(result.stdout)

    assert result.returncode == 1
    knowledge_errors = [
        item
        for item in payload["checks"]
        if item["resource"] == "knowledge-data" and item["level"] == "error"
    ]
    assert knowledge_errors
    assert "hsr_nanoka_characters/manifest.json" in knowledge_errors[0]["detail"]
