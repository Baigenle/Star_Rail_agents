# GitHub 上传前检查

## 不得提交

- `.env`、API Key、JWT 密钥、访问 Token 和用户密码。
- `models/`、`backend/.venv/`、`frontend/node_modules/`、`frontend/dist/`。
- Docker 数据卷、测试缓存、临时截图、数据库备份和个人简历。
- 大型游戏图片、完整剧情/Wiki 文本、第三方数据导出与清洗后的完整语料；使用者按 `LOCAL_RESOURCES.md` 在本地准备。

## 必须提交

- `backend/app/models/*.py`：SQLAlchemy 数据模型，不能被根目录模型权重规则误伤。
- Alembic 迁移、后端和前端源码、测试、`package-lock.json`。
- `.env.example`、Docker Compose、README 和部署文档。
- 轻量 SVG 占位图、数据格式示例和资源检查脚本。

## 本地质量门禁

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
backend/.venv/Scripts/python.exe -m ruff check --no-cache backend/app backend/tests backend/scripts scripts
backend/.venv/Scripts/python.exe -m pip check

Set-Location frontend
npm run type-check
npm run build
npm audit --registry=https://registry.npmjs.org --audit-level=high
Set-Location ..

docker compose config --quiet
python scripts/check_local_resources.py --strict-assets --strict-knowledge
```

## 提交前人工检查

```powershell
git status --short
git diff --check
git diff --staged
git grep -n -I -E "sk-[A-Za-z0-9_-]{16,}"
```

最后一条命令应无输出。若密钥曾经进入提交历史，仅从当前文件删除是不够的：必须吊销旧密钥、生成新密钥，并在发布前清理 Git 历史。

## 建立远程仓库

先在 GitHub 创建空仓库，不要勾选自动生成 README、`.gitignore` 或 License，然后执行：

```powershell
git remote add origin https://github.com/<用户名>/<仓库名>.git
git push -u origin main
```

只有原创或明确获得再分发许可的资源才能放到 GitHub Release；Release 不是规避版权限制的渠道。发布后用全新目录重新克隆一次，并按 README 准备本地语料、完成切分与启动，才算复现验收通过。
