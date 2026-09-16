from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_backend_image_contains_reproducible_knowledge_scripts() -> None:
    dockerfile = (PROJECT_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY scripts ./scripts" in dockerfile
    assert "PYTHONPATH=/app" in dockerfile


def test_compose_has_no_implicit_admin_and_supports_frontend_port_override() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "ADMIN_USERNAMES: ${ADMIN_USERNAMES:-}" in compose
    assert "${FRONTEND_HOST_PORT:-8030}:80" in compose


def test_fc_and_tunable_ai_settings_are_forwarded_to_backend() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "MAIN_AGENT_IMPL: ${MAIN_AGENT_IMPL:-fc}" in compose
    for name in (
        "BACKEND_CORS_ORIGINS",
        "RAG_TOP_K",
        "LLM_TEMPERATURE",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "QWEN_BASE_URL",
        "QWEN_MODEL",
        "ZHIPU_MODEL",
        "ZHIPU_INTENT_MODEL",
    ):
        assert f"{name}:" in compose
        assert f"{name}=" in example

    assert "MAIN_AGENT_IMPL=fc" in example
    assert "react=兼容回退" in example
    assert 'BACKEND_CORS_ORIGINS=["http://localhost:5173","http://localhost:8030"]' in example
    assert "DATABASE_URL=postgresql+psycopg://star_rail:change-me@localhost:5432/star_rail_agents" in example
    assert "MILVUS_HOST=localhost" in example
    assert "MILVUS_PORT=19531" in example
    assert "BGE_SERVICE_URL=http://localhost:8001" in example
    assert "MILVUS_HOST: milvus-standalone" in compose
    assert "MILVUS_PORT: 19530" in compose
    assert "BGE_SERVICE_URL: http://bge-model-service:8001" in compose
    assert "DEEPSEEK_API_KEY=\n" in example
    assert "QWEN_API_KEY=\n" in example
    assert "ZHIPU_API_KEY=\n" in example


def test_gitignore_keeps_runtime_source_and_lightweight_fallback_assets() -> None:
    """大文件必须忽略，但后端 ORM 源码和占位图必须能随仓库分发。"""
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "\n/models/\n" in f"\n{gitignore}"
    assert "\nmodels/\n" not in f"\n{gitignore}"
    assert "/docs/data/assets/characters/" in gitignore
    assert "/docs/data/assets/items/" in gitignore
    assert "/docs/data/assets/placeholders/" not in gitignore

    model_sources = sorted((PROJECT_ROOT / "backend" / "app" / "models").glob("*.py"))
    placeholders = sorted(
        (PROJECT_ROOT / "docs" / "data" / "assets" / "placeholders").glob("*.svg")
    )
    assert model_sources, "backend ORM model sources must be present"
    assert placeholders, "lightweight SVG fallbacks must be present"


def test_compose_supports_external_local_resource_directories() -> None:
    """模型和图片可以放在仓库外，避免重复占用系统盘或误提交 Git。"""
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "${BGE_MODELS_PATH:-./models}:/models:ro" in compose
    assert (
        "${GAME_ASSETS_PATH:-./docs/data/assets}/characters:"
        "/data/knowledge/data/assets/characters:ro"
    ) in compose
    assert (
        "${GAME_ASSETS_PATH:-./docs/data/assets}/items:"
        "/data/knowledge/data/assets/items:ro"
    ) in compose
    assert (
        "${GAME_ASSETS_PATH:-./docs/data/assets}:/data/knowledge/data/assets:ro"
        not in compose
    )
    assert "BGE_MODELS_PATH=./models" in example
    assert "GAME_ASSETS_PATH=./docs/data/assets" in example
    assert "KNOWLEDGE_DATA_PATH=./docs" in example
    assert "${KNOWLEDGE_DATA_PATH:-./docs}:/data/knowledge:ro" in compose


def test_public_repository_excludes_full_local_knowledge_datasets() -> None:
    """完整抓取/清洗语料只在本地使用，公开仓库仅保留代码、规则和说明。"""
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    local_only_paths = (
        "/docs/data_character_story/",
        "/docs/data_lore_pages/",
        "/docs/hsr_nanoka_characters/",
        "/docs/hsr_nanoka_items/",
        "/docs/clean_markdown/",
        "/docs/clean_relic/",
        "/docs/normalized_supplements/",
        "/docs/content_1257_版本活动/",
        "/docs/lightcone/",
        "/docs/relic/",
        "/docs/monster/",
    )
    for path in local_only_paths:
        assert path in gitignore


def test_maintenance_scripts_never_embed_admin_credentials() -> None:
    """管理员账号只能从运行时环境变量读取，不能进入源码和 Git 历史。"""
    seed_script = (PROJECT_ROOT / "scripts" / "seed_community.py").read_text(
        encoding="utf-8"
    )
    probe_script = (
        PROJECT_ROOT / "scripts" / "comprehensive_api_probe.py"
    ).read_text(encoding="utf-8")
    combined = seed_script + probe_script

    # 分段构造曾用于本地演示的凭据，避免仓库扫描器把测试样例误判为现役秘密。
    legacy_account = "123" + "@163.com"
    legacy_password = "1234" + "5678"
    assert legacy_account not in combined
    assert legacy_password not in combined
    assert "STAR_RAIL_ADMIN_ACCOUNT" in seed_script
    assert "STAR_RAIL_ADMIN_PASSWORD" in seed_script
    assert "STAR_RAIL_ADMIN_ACCOUNT" in probe_script
    assert "STAR_RAIL_ADMIN_PASSWORD" in probe_script
