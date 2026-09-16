"""人格场景层（Phase 3）：场景库加载与语气注入。

场景文件：backend/app/prompts/persona/scenes/*.md（元数据头 + 规则 + 台词样本）
匹配：BGE 向量（余弦 ≥0.72，规格 §9.5）优先；无 embedder 或服务不可用降级
关键词命中计数（平局时正经场景优先——"先站队"比"嘴硬"更安全）。
daily_chat 为兜底基调：其规则已由 system 静态段承载，永不主动匹配注入。
"""

from pathlib import Path

SCENES_DIR = Path(__file__).resolve().parents[1] / "prompts" / "persona" / "scenes"
MATCH_THRESHOLD = 0.72
