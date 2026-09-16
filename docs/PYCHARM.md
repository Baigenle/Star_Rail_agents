# PyCharm 开发配置

项目可以在 PyCharm 2024.3 或更高版本运行。建议使用 Professional；Community 版也可通过 Terminal 启动。

## 1. 打开项目

将 `E:\Workshop\Star_Rail_agents` 作为项目根目录打开，不要只打开 `backend/app`。

## 2. Python 解释器

使用 Python 3.11 或 3.12，在 `backend/.venv` 创建虚拟环境：

```powershell
cd E:\Workshop\Star_Rail_agents\backend
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

PyCharm 中选择：

- Settings → Project → Python Interpreter
- Add Interpreter → Add Local Interpreter
- Existing environment → `E:\Workshop\Star_Rail_agents\backend\.venv\Scripts\python.exe`

## 3. 数据库迁移

项目使用 Alembic，不再依赖应用启动时的 `create_all` 修改既有表。

在 PyCharm Terminal 运行：

```powershell
cd E:\Workshop\Star_Rail_agents\backend
.venv\Scripts\alembic upgrade head
```

如只想在 PyCharm 调试应用，可以先用 Docker 启动基础设施：

```powershell
cd E:\Workshop\Star_Rail_agents
docker compose up -d postgres etcd minio milvus-standalone bge-model-service
```

此时根目录 `.env` 中宿主机连接地址应为：

```env
DATABASE_URL=postgresql+psycopg://star_rail:change-me@localhost:5432/star_rail_agents
MILVUS_HOST=localhost
MILVUS_PORT=19531
BGE_SERVICE_URL=http://localhost:8001
MAIN_AGENT_IMPL=fc
```

需要完整自然语言编排时，还应设置 `DEFAULT_LLM_PROVIDER=zhipu` 或 `deepseek` 并填写对应 API Key；`mock`、Qwen 或缺少 Key 时会使用兼容 ReAct 回退。

## 4. 一键启动开发环境

仓库提供了共享运行配置：

```text
Star Rail Dev 一键启动
```

首次使用前，先完成后端与前端依赖安装：

```powershell
cd E:\Workshop\Star_Rail_agents\backend
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"

cd ..\frontend
npm install
```

然后在 PyCharm 顶部运行配置中选择 `Star Rail Dev 一键启动` 并点击运行。
启动器会依次：

1. 停止可能占用 8000/8030 端口的 Docker 前后端容器。
2. 启动 PostgreSQL、Milvus、MinIO、etcd 和 BGE。
3. 等待 PostgreSQL 与 BGE 健康检查。
4. 使用 `backend/.venv` 启动 FastAPI。
5. 使用 npm 启动 Vue，并打开 `http://localhost:5173`。

在 PyCharm 中停止该运行配置会关闭本地 FastAPI 与 Vue，Docker
基础服务继续保留，方便下次快速启动。

如果不希望自动打开浏览器，在运行配置参数中增加：

```text
--no-browser
```

## 5. FastAPI 单独运行配置

创建 Python Run Configuration：

- Module name：`uvicorn`
- Parameters：`app.main:app --reload --host 0.0.0.0 --port 8000`
- Working directory：`E:\Workshop\Star_Rail_agents\backend`
- Interpreter：`backend\.venv\Scripts\python.exe`
- Environment file：项目根目录 `.env`

启动后访问 http://localhost:8000/docs 。

## 6. Vue 单独运行配置

在 `frontend` 安装依赖：

```powershell
cd E:\Workshop\Star_Rail_agents\frontend
npm install
```

创建 npm Run Configuration：

- package.json：`frontend/package.json`
- Command：`run`
- Script：`dev`

开发地址为 http://localhost:5173 。生产 Docker 地址为 http://localhost:8030 。

## 7. 测试配置

创建 Python 测试配置：

- Target：`backend/tests`
- Working directory：`E:\Workshop\Star_Rail_agents\backend`
- Interpreter：`backend\.venv\Scripts\python.exe`

或直接运行：

```powershell
cd E:\Workshop\Star_Rail_agents\backend
.venv\Scripts\python -m pytest -q

cd ..\frontend
npm run type-check
npm run build
```

## 8. Docker 完整复现

完整环境不要求 PyCharm 安装额外插件：

```powershell
cd E:\Workshop\Star_Rail_agents
docker compose up -d --build
docker compose ps
```

模型文件通过卷挂载使用，不写入 Git，也不会在普通后端重建时重复打包。路径配置说明见 [BGE_MODELS.md](BGE_MODELS.md)。
