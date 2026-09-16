import importlib.util
from pathlib import Path
from types import ModuleType


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_PATH = PROJECT_ROOT / "scripts" / "pycharm_start.py"


def _load_launcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "pycharm_start",
        LAUNCHER_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_backend_environment_uses_docker_host_ports() -> None:
    launcher = _load_launcher()

    environment = launcher.build_local_backend_environment(
        {
            "POSTGRES_DB": "star_rail_agents",
            "POSTGRES_USER": "star_rail",
            "POSTGRES_PASSWORD": "secret",
            "POSTGRES_HOST_PORT": "55432",
            "MILVUS_HOST_PORT": "29531",
            "BGE_SERVICE_HOST_PORT": "18001",
        },
        base_environment={"PATH": "test-path"},
    )

    assert environment["DATABASE_URL"] == (
        "postgresql+psycopg://star_rail:secret"
        "@localhost:55432/star_rail_agents"
    )
    assert environment["MILVUS_HOST"] == "localhost"
    assert environment["MILVUS_PORT"] == "29531"
    assert environment["BGE_SERVICE_URL"] == "http://localhost:18001"
    assert environment["PATH"] == "test-path"


def test_local_backend_environment_supports_external_knowledge_root() -> None:
    launcher = _load_launcher()
    expected = PROJECT_ROOT / "local-resources" / "knowledge"

    environment = launcher.build_local_backend_environment(
        {"KNOWLEDGE_DATA_PATH": "local-resources/knowledge"},
        base_environment={},
    )

    assert Path(environment["DOCS_ROOT"]) == expected.resolve()


def test_compose_exposes_postgres_for_pycharm_backend() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(
        encoding="utf-8"
    )

    assert '"${POSTGRES_HOST_PORT:-5432}:5432"' in compose


def test_docker_discovery_ignores_inaccessible_install_paths(
    monkeypatch,
) -> None:
    launcher = _load_launcher()
    monkeypatch.setattr(launcher.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        launcher.Path,
        "is_file",
        lambda _path: (_ for _ in ()).throw(PermissionError()),
    )

    assert launcher.find_executable("docker") is None


def test_frontend_environment_does_not_receive_backend_secrets() -> None:
    launcher = _load_launcher()

    environment = launcher.build_local_frontend_environment(
        {
            "PATH": "test-path",
            "DEEPSEEK_API_KEY": "secret-key",
            "QWEN_API_KEY": "secret-key",
            "JWT_SECRET_KEY": "secret-key",
            "POSTGRES_PASSWORD": "secret-password",
        }
    )

    assert environment["PATH"] == "test-path"
    assert environment["VITE_API_BASE_URL"] == (
        "http://localhost:8000/api/v1"
    )
    assert "DEEPSEEK_API_KEY" not in environment
    assert "QWEN_API_KEY" not in environment
    assert "JWT_SECRET_KEY" not in environment
    assert "POSTGRES_PASSWORD" not in environment
