import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.api.dependencies import get_herta_main_agent
from app.api.v1.routes.chat import active_chat_job_tasks, recover_chat_jobs
from app.core.config import settings
from app.db.session import SessionLocal
from app import models  # noqa: F401

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    tasks: list[asyncio.Task[None]] = []
    try:
        tasks = recover_chat_jobs(get_herta_main_agent(), SessionLocal)
    except Exception:
        # 外部向量库短暂不可用时仍允许应用启动，便于健康检查和 Docker 自动恢复；
        # 新的 AI 请求会重新创建依赖，未完成任务则可在下一次进程启动时继续接管。
        logger.exception("聊天任务恢复已跳过：Agent 依赖暂时不可用")
    try:
        yield
    finally:
        tasks = list({*tasks, *active_chat_job_tasks()})
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="基于 Multi-Agent 与 RAG 的游戏智能助手平台",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount(
    f"{settings.api_v1_prefix}/assets",
    StaticFiles(directory=settings.docs_root / "data" / "assets", check_dir=True),
    name="game-assets",
)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}
