# 本地模型、图片、知识语料与索引准备

公开仓库只保存可审查的源代码、规则配置、项目文档和轻量占位图。BGE 权重、游戏图片、完整剧情/Wiki 文本、第三方数据导出、数据库卷与 API Key 均由使用者在本地准备，避免 Git 仓库过大，也避免未经授权再分发第三方内容。

## 1. 资源目录

推荐把大文件放到独立磁盘：

```text
D:/StarRailResources/
  models/
    bge-m3/
    bge-reranker-v2-m3/
  assets/
    characters/
    lightcones/
    relics/
    items/
    manifest/
    assets_manifest.sha256
  knowledge/
    hsr_nanoka_characters/
    hsr_nanoka_items/
    lightcone/
    relic/
    normalized_supplements/
    data_character_story/
    data_lore_pages/
    activity_knowledge/
    progression/
    team_knowledge/
```

在项目根目录 `.env` 中配置：

```env
BGE_MODELS_PATH=D:/StarRailResources/models
GAME_ASSETS_PATH=D:/StarRailResources/assets
KNOWLEDGE_DATA_PATH=D:/StarRailResources/knowledge
DOCS_ROOT=D:/StarRailResources/knowledge
```

Windows 路径建议使用 `/`，不要在 `.env` 中使用未经转义的反斜杠。若沿用本项目当前本地布局，可使用 `./models`、`./docs/data/assets` 和 `./docs`。

## 2. 下载 BGE 模型

本项目中的 BGE 服务只执行 embedding 与 rerank；负责回答的 DeepSeek、Qwen 或智谱模型仍通过 API 调用。

### 方式 A：Hugging Face

```powershell
python -m pip install --upgrade huggingface_hub
hf download BAAI/bge-m3 --local-dir D:/StarRailResources/models/bge-m3
hf download BAAI/bge-reranker-v2-m3 --local-dir D:/StarRailResources/models/bge-reranker-v2-m3
```

官方说明：<https://huggingface.co/docs/huggingface_hub/en/guides/download>

### 方式 B：中国大陆网络下使用 ModelScope

```powershell
python -m pip install --upgrade modelscope
modelscope download --model BAAI/bge-m3 --local_dir D:/StarRailResources/models/bge-m3
modelscope download --model AI-ModelScope/bge-reranker-v2-m3 --local_dir D:/StarRailResources/models/bge-reranker-v2-m3
```

模型页面：

- <https://www.modelscope.cn/models/BAAI/bge-m3>
- <https://www.modelscope.cn/models/AI-ModelScope/bge-reranker-v2-m3>

每个目录至少需要 `config.json`、tokenizer 文件，以及 `model.safetensors` 或 `pytorch_model.bin`。只需要保留一种主权重格式；不要把下载缓存和重复权重提交到 Git。

## 3. 准备图片

图片不是 RAG 检索的必要条件；缺失时前端使用仓库内的 SVG 占位图。需要完整展示时，将自己有权使用的图片按以下分类放置：

```text
assets/characters
assets/lightcones
assets/relics
assets/items
assets/manifest
```

目录命名和图片 ID 映射以使用者本地生成的 `assets_manifest.sha256` 与知识文档中的实体 ID 为准。请勿把来源不明或无权再分发的游戏资源提交到公开仓库或 Release。

生成资源校验清单：

```powershell
python scripts/generate_asset_manifest.py --root D:/StarRailResources/assets
```

收到资源包后校验：

```powershell
python scripts/generate_asset_manifest.py --root D:/StarRailResources/assets --check
```

## 4. 一键检查本地资源

默认目录：

```powershell
python scripts/check_local_resources.py --strict-assets
```

外部目录：

```powershell
python scripts/check_local_resources.py `
  --models D:/StarRailResources/models `
  --assets D:/StarRailResources/assets `
  --knowledge D:/StarRailResources/knowledge `
  --strict-assets `
  --strict-knowledge
```

去掉 `--strict-assets` 后，图片缺失只会显示提醒；模型不完整仍会返回失败。自动化脚本可加 `--json` 获取结构化结果。

## 5. 准备本地知识语料

仓库不提供完整游戏知识语料。使用者应从自己有权使用的本地文件开始，运行仓库中的规范化脚本，最终让知识根目录至少具备以下核心文件：

```text
hsr_nanoka_characters/manifest.json
hsr_nanoka_items/hsr_items.json
lightcone/manifest.json
relic/manifest.json
normalized_supplements/alignment_report.json
data_character_story/trailblaze_story_chunks.jsonl
data_lore_pages/lore_sections.jsonl
activity_knowledge/activities.json
progression/progression_rules.json
progression/character_material_bindings.json
team_knowledge/mechanism_profiles.json
```

相关构建程序位于 `backend/scripts/` 与 `scripts/`。先阅读每个脚本的 `--help`，明确输入目录和输出目录，再处理自己的本地源文件。例如：

```powershell
backend/.venv/Scripts/python.exe backend/scripts/build_progression_data.py --help
backend/.venv/Scripts/python.exe backend/scripts/normalize_team_knowledge.py --help
backend/.venv/Scripts/python.exe backend/scripts/normalize_activity_knowledge.py --help
```

处理完成后进行严格检查：

```powershell
python scripts/check_local_resources.py --strict-knowledge
```

## 6. 模型切分与 Milvus 入库

`ingest_knowledge.py` 会执行固定流程：

1. 读取带 YAML frontmatter 的 Markdown 和已规范化 JSONL。
2. 拒绝缺 ID、标题、版本、来源或正文过短的文档。
3. 按一级/二级标题分段。
4. 长段落按最多 900 字符、120 字符重叠切片。
5. 使用 BGE-M3 生成向量并写入 Milvus。
6. 查询时使用 BGE reranker 二次排序。

先进行不写数据库的切分检查：

```powershell
docker compose exec backend python scripts/ingest_knowledge.py `
  --docs /data/knowledge `
  --dry-run
```

输出中的 `documents.accepted`、`documents.rejected` 和 `chunks.total` 用来确认清洗结果。被拒绝的文件会显示具体原因。

首次写入 Milvus：

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

`--recreate` 会删除并重建指定 collection，只应在首次建库或确认需要全量重建时使用。普通增量更新去掉该参数。

### Markdown 数据格式

如果要替换或补充现有知识文件，应保持对应数据目录和 frontmatter 字段。例如角色文件：

```markdown
---
character_id: "1001"
title: "示例角色"
game: "Honkai: Star Rail"
data_version: "4.4"
language: "zh-CN"
source_page: "https://example.invalid/character/1001"
source_data: "local-curated"
generated_at: "2026-09-14T00:00:00+08:00"
---

# 示例角色

## 角色简介

正文内容……
```

不要把未经清洗的网页 HTML 直接交给入库脚本。先去除导航、广告、脚本、重复段落和模板占位符，并保留可靠来源与版本信息。

## 7. 启动顺序

```powershell
Copy-Item .env.example .env
# 编辑 .env，填入本机资源路径、随机数据库密码、JWT_SECRET_KEY 和模型 API Key。
python scripts/check_local_resources.py --strict-assets --strict-knowledge
docker compose up -d --build
docker compose ps
```

确认 BGE 健康后再执行知识切分和 Milvus 入库：

```powershell
Invoke-RestMethod http://localhost:8001/health
```

后续启动已有容器使用 `docker compose up -d`，不需要每次重新构建镜像或重建向量库。
