# 本地 BGE 模型服务

项目使用本地 `bge-m3` 生成 1024 维语义向量，使用
`bge-reranker-v2-m3` 对 Milvus 初步召回结果进行重排。

## 模型目录

模型权重不提交到 Git，运行前目录应为：

```text
models/
  bge-m3/
    config.json
    pytorch_model.bin
    tokenizer.json
  bge-reranker-v2-m3/
    config.json
    model.safetensors
    tokenizer.json
```

## Docker 启动

Docker Desktop 使用 WSL 2 后端并启用 NVIDIA GPU 支持，然后执行：

```powershell
docker compose up -d --build bge-model-service
```

健康检查地址为 `http://localhost:8001/health`。

## 建立 BGE-M3 向量集合

模型服务启动成功后，在 PyCharm 的 `backend` 终端运行：

```powershell
.venv\Scripts\python scripts\ingest_knowledge.py `
  --docs ..\docs `
  --uri http://localhost:19531 `
  --collection star_rail_knowledge_bge_m3_v2 `
  --embedding bge-m3 `
  --model-service-url http://localhost:8001 `
  --batch-size 16 `
  --recreate
```

测试检索和重排：

```powershell
.venv\Scripts\python scripts\search_knowledge.py `
  "黄泉适合使用什么光锥" `
  --uri http://localhost:19531 `
  --collection star_rail_knowledge_bge_m3_v2 `
  --embedding bge-m3 `
  --model-service-url http://localhost:8001 `
  --rerank
```

`--recreate` 会删除并重建同名 collection，只应在首次初始化或明确全量更新时使用。
