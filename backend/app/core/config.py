from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "Star Rail Agents"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    backend_cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    database_url: str = "postgresql+psycopg://star_rail:change-me@localhost:5432/star_rail_agents"
    milvus_host: str = "localhost"
    milvus_port: int = 19531
    milvus_collection: str = "star_rail_knowledge_bge_m3_v2"
    bge_service_url: str = "http://localhost:8001"
    rag_top_k: int = Field(default=5, ge=1, le=10)
    docs_root: Path = Path(__file__).resolve().parents[3] / "docs"
    # FC 是现役主链；ReAct 仅用于显式切换或 FC 客户端不可用时的兼容回退。
    main_agent_impl: Literal["fc", "react"] = "fc"

    default_llm_provider: Literal["mock", "deepseek", "qwen", "zhipu"] = "mock"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_flash_model: str = "deepseek-v4-flash"
    deepseek_pro_model: str = "deepseek-v4-pro"
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    zhipu_api_key: str = ""
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    zhipu_model: str = "glm-4.6"
    zhipu_flash_model: str = "glm-4-flash"
    zhipu_pro_model: str = "glm-4.6"
    zhipu_intent_model: str = "glm-4.7"
    llm_temperature: float = Field(default=0.1, ge=0, le=1)

    jwt_secret_key: str = "development-only-change-this-secret"
    jwt_expire_minutes: int = Field(default=1440, ge=15, le=43200)
    admin_usernames: str = ""

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def parse_list(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
