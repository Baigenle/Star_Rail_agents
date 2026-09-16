# Docker、PyCharm 与资源包复现

## 最小复现清单

1. Windows 10/11、Docker Desktop 4.x。
2. 项目源码与 `.env.example`。
3. `models/bge-m3`、`models/bge-reranker-v2-m3` 本地模型目录。
4. 使用者本地准备的知识语料目录与可选图片目录。
5. Docker 至少预留约 12 GB 内存；GPU 模式需要可用的 NVIDIA Container Toolkit。

模型权重、完整知识语料、数据库卷、镜像缓存和图片二进制不提交普通 Git。它们不参与每次镜像构建：BGE 权重和知识目录通过只读卷挂载，Docker 构建层命中缓存时不会重复下载。

模型和图片不必复制进仓库，可在 `.env` 指向其他磁盘：

```env
BGE_MODELS_PATH=D:/StarRailResources/models
GAME_ASSETS_PATH=D:/StarRailResources/assets
KNOWLEDGE_DATA_PATH=D:/StarRailResources/knowledge
DOCS_ROOT=D:/StarRailResources/knowledge
```

首次启动前执行：

```powershell
python scripts/check_local_resources.py --strict-assets --strict-knowledge
```

完整模型下载、图片目录及知识切分教程见 [LOCAL_RESOURCES.md](LOCAL_RESOURCES.md)。

## 首次启动

```powershell
Copy-Item .env.example .env
# 编辑 .env，至少修改数据库密码、JWT_SECRET_KEY 和模型提供商/API Key
# MAIN_AGENT_IMPL=fc 为现役主链；当前 FC 客户端支持 zhipu/deepseek
docker compose up -d --build
docker compose ps
```

无 NVIDIA GPU 时可使用 CPU 覆盖配置：

```powershell
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d --build
```

CPU 模式仍使用同一份本地模型和推理镜像，但首次加载及检索会明显更慢。

默认入口：

- 前端：`http://localhost:8030`
- FastAPI：`http://localhost:8000/docs`
- BGE：`http://localhost:8001/health`
- Milvus 宿主机端口：`19531`

后端启动命令会先执行 `alembic upgrade head`，因此空数据库可自动迁移到当前结构。

`.env.example` 中的 PostgreSQL、Milvus 与 BGE 地址面向宿主机直接运行；Docker Compose 会显式覆盖为容器内部服务名。模型、检索深度和温度分别通过 `DEFAULT_LLM_PROVIDER`、`RAG_TOP_K` 与 `LLM_TEMPERATURE` 调整。使用 `mock`、Qwen 或未配置相应 Key 时，FC 会安全回退到兼容 ReAct 链路。

全新 Milvus 数据卷还需要建立一次知识索引：

```powershell
docker compose exec backend python scripts/ingest_knowledge.py `
  --docs /data/knowledge `
  --uri http://milvus-standalone:19530 `
  --collection star_rail_knowledge_bge_m3_v2 `
  --embedding bge-m3 `
  --model-service-url http://bge-model-service:8001 `
  --batch-size 16 `
  --recreate
```

管理员不使用默认密码。先注册普通账号，再将其“用户名”写入
`.env` 的 `ADMIN_USERNAMES`，最后执行
`docker compose up -d --force-recreate backend`。

## PyCharm

具体运行配置见 [PYCHARM.md](PYCHARM.md)。推荐模式是：

- Docker 启动 PostgreSQL、Milvus、MinIO、etcd 和 BGE；
- PyCharm 使用 `backend/.venv` 调试 FastAPI；
- npm Run Configuration 调试 Vue。

## 资源分发

公开 GitHub Release 只发布源码、目录模板、校验工具和使用者原创或明确获得再分发许可的资源。不要把完整剧情/Wiki 原文、游戏图片、第三方原始导出或模型权重作为公开附件。

- `knowledge-layout-example.zip`：不含游戏原文的目录结构与格式示例。
- `bge-models-local-guide.txt`：模型目录结构与官方下载说明。

使用者在本地准备图片后自行生成并校验清单：

```powershell
python scripts\generate_asset_manifest.py --root D:/StarRailResources/assets
python scripts\generate_asset_manifest.py --root D:/StarRailResources/assets --check
```

资源位于仓库外时直接指定根目录：

```powershell
python scripts/generate_asset_manifest.py --root D:/StarRailResources/assets --check
```

## 不需要重复的大文件

- `docker compose up -d` 不会重建镜像。
- 只有源码或依赖发生变化时才需要 `--build`。
- BGE 模型目录在宿主机，仅挂载进容器，不复制进镜像。
- PostgreSQL、Milvus、MinIO、etcd 使用命名卷，容器重建不会删除数据。
- 不要执行 `docker compose down -v`，除非明确要清空全部数据库和向量索引。
