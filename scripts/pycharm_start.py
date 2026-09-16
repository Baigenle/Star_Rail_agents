"""星穹智库的 PyCharm 一键开发启动器。"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from argparse import ArgumentParser
from pathlib import Path
from typing import Mapping
from urllib.parse import quote_plus


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"


def read_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    """读取项目使用的简单 KEY=VALUE 环境变量。"""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def build_local_backend_environment(
    values: Mapping[str, str],
    *,
    base_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """把 Docker 内部服务名转换为本地 Uvicorn 可访问的宿主机地址。"""
    environment = dict(base_environment or os.environ)
    environment.update(values)

    database = values.get("POSTGRES_DB", "star_rail_agents")
    user = values.get("POSTGRES_USER", "star_rail")
    password = quote_plus(values.get("POSTGRES_PASSWORD", "change-me"))
    postgres_port = values.get("POSTGRES_HOST_PORT", "5432")
    milvus_port = values.get("MILVUS_HOST_PORT", "19531")
    bge_port = values.get("BGE_SERVICE_HOST_PORT", "8001")
    knowledge_root = Path(
        values.get("DOCS_ROOT") or values.get("KNOWLEDGE_DATA_PATH") or "docs"
    ).expanduser()
    if not knowledge_root.is_absolute():
        knowledge_root = PROJECT_ROOT / knowledge_root

    environment.update(
        {
            "DATABASE_URL": (
                f"postgresql+psycopg://{user}:{password}"
                f"@localhost:{postgres_port}/{database}"
            ),
            "MILVUS_HOST": "localhost",
            "MILVUS_PORT": milvus_port,
            "BGE_SERVICE_URL": f"http://localhost:{bge_port}",
            "DOCS_ROOT": str(knowledge_root.resolve()),
        }
    )
    return environment


def build_local_frontend_environment(
    base_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """构造前端进程环境，并剔除后端密钥。"""
    environment = dict(base_environment or os.environ)
    # Vite 会把 VITE_ 前缀变量写入浏览器包；这里也主动隔离其他密钥，防止误传给 npm 子进程。
    sensitive_keys = {
        key
        for key in environment
        if (
            key.endswith("_API_KEY")
            or key.endswith("_PASSWORD")
            or key.endswith("_SECRET")
            or key in {"JWT_SECRET_KEY", "DATABASE_URL"}
        )
    }
    for key in sensitive_keys:
        environment.pop(key, None)
    environment["VITE_API_BASE_URL"] = "http://localhost:8000/api/v1"
    return environment


def find_executable(name: str) -> str | None:
    discovered = shutil.which(name)
    if discovered:
        return discovered
    if name != "docker":
        return None
    candidates = [
        Path(os.getenv("LOCALAPPDATA", ""))
        / "Programs"
        / "DockerDesktop"
        / "resources"
        / "bin"
        / "docker.exe",
        Path(os.getenv("PROGRAMFILES", "C:/Program Files"))
        / "Docker"
        / "Docker"
        / "resources"
        / "bin"
        / "docker.exe",
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return None


def wait_for_http(url: str, label: str, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    next_report = time.monotonic()
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status < 500:
                    print(f"[ready] {label}: {url}", flush=True)
                    return
        except (OSError, urllib.error.URLError):
            pass
        if time.monotonic() >= next_report:
            remaining = max(0, int(deadline - time.monotonic()))
            print(
                f"[wait] {label} 正在启动，最多再等待 {remaining} 秒",
                flush=True,
            )
            next_report = time.monotonic() + 15
        time.sleep(2)
    raise RuntimeError(f"{label} 在 {timeout} 秒内未就绪：{url}")


def wait_for_tcp(host: str, port: int, label: str, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                print(f"[ready] {label}: {host}:{port}", flush=True)
                return
        except OSError:
            time.sleep(2)
    raise RuntimeError(f"{label} 在 {timeout} 秒内未就绪：{host}:{port}")


def terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()


def require_path(path: Path, description: str) -> None:
    if not path.exists():
        raise RuntimeError(f"缺少{description}：{path}")


def start_development_environment(*, open_browser: bool = True) -> int:
    values = read_env_file()
    require_path(ENV_FILE, "环境变量文件，请先复制 .env.example")
    require_path(
        PROJECT_ROOT / "models" / "bge-m3" / "config.json",
        "BGE-M3 模型",
    )
    require_path(
        PROJECT_ROOT
        / "models"
        / "bge-reranker-v2-m3"
        / "config.json",
        "BGE Reranker 模型",
    )

    docker = find_executable("docker")
    npm = find_executable("npm")
    backend_python = (
        PROJECT_ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
        if os.name == "nt"
        else PROJECT_ROOT / "backend" / ".venv" / "bin" / "python"
    )
    if not docker:
        raise RuntimeError("找不到 Docker CLI，请先启动或安装 Docker Desktop。")
    if not npm:
        raise RuntimeError("找不到 npm，请安装 Node.js 20 或更高版本。")
    require_path(backend_python, "后端虚拟环境 Python")
    require_path(
        PROJECT_ROOT / "frontend" / "node_modules",
        "前端依赖，请先在 frontend 目录执行 npm install",
    )

    compose = [docker, "compose"]
    # PyCharm 模式复用 Docker 数据库、Milvus 和模型服务，只把前后端换成本地热更新进程。
    print("[1/4] 停止 Docker 中的前后端容器，避免端口冲突。", flush=True)
    subprocess.run(
        [*compose, "stop", "backend", "frontend"],
        cwd=PROJECT_ROOT,
        check=False,
    )

    print("[2/4] 启动 PostgreSQL、Milvus 和 BGE 基础服务。", flush=True)
    subprocess.run(
        [
            *compose,
            "up",
            "-d",
            "postgres",
            "etcd",
            "minio",
            "milvus-standalone",
            "bge-model-service",
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )

    postgres_port = int(values.get("POSTGRES_HOST_PORT", "5432"))
    bge_port = int(values.get("BGE_SERVICE_HOST_PORT", "8001"))
    wait_for_tcp("localhost", postgres_port, "PostgreSQL")
    wait_for_http(
        f"http://localhost:{bge_port}/health",
        "BGE 模型服务",
        timeout=360,
    )

    print("[3/4] 启动 FastAPI 和 Vue 开发服务器。", flush=True)
    backend_environment = build_local_backend_environment(values)
    frontend_environment = build_local_frontend_environment()
    creation_flags = (
        subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    )
    backend = subprocess.Popen(
        [
            str(backend_python),
            "-m",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ],
        cwd=PROJECT_ROOT / "backend",
        env=backend_environment,
        creationflags=creation_flags,
    )
    frontend = subprocess.Popen(
        [npm, "run", "dev"],
        cwd=PROJECT_ROOT / "frontend",
        env=frontend_environment,
        creationflags=creation_flags,
    )

    try:
        wait_for_http(
            "http://localhost:8000/api/v1/health",
            "FastAPI",
            timeout=120,
        )
        wait_for_http("http://localhost:5173", "Vue", timeout=120)
        print("[4/4] 星穹智库开发环境启动完成。", flush=True)
        print("前端：http://localhost:5173", flush=True)
        print("接口：http://localhost:8000/docs", flush=True)
        print("在 PyCharm 中停止本运行配置即可关闭前后端。", flush=True)
        if open_browser:
            webbrowser.open("http://localhost:5173")

        while True:
            for label, process in (
                ("FastAPI", backend),
                ("Vue", frontend),
            ):
                return_code = process.poll()
                if return_code is not None:
                    raise RuntimeError(
                        f"{label} 已意外退出，退出码：{return_code}"
                    )
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[stop] 正在关闭 FastAPI 和 Vue。", flush=True)
        return 0
    finally:
        terminate_process_tree(frontend)
        terminate_process_tree(backend)


def main() -> int:
    parser = ArgumentParser(description="一键启动星穹智库 PyCharm 开发环境")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="启动完成后不自动打开浏览器",
    )
    args = parser.parse_args()
    try:
        return start_development_environment(
            open_browser=not args.no_browser
        )
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"[error] {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.default_int_handler)
    raise SystemExit(main())
