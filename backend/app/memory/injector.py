"""记忆注入器（规格 §7 管线段④⑤）。

每轮输出两段文本（拼进 AgentContext.memory_injection，引擎放进动态段）：
[玩家画像]/[近期状态]：L0/L1 非空字段全量注入
[相关记忆]：L2 语义召回 top-5（余弦 ≥0.35），命中即更新访问统计

降级：无 embedder 或 embedding 服务不可用 → 关键词重合度召回（不中断主流程）。
"""

from __future__ import annotations

import math
import re
import time
from typing import Any

from app.memory.repository import MemoryRepository
from app.memory.schemas import L2Memory

RECALL_TOP_K = 5
RECALL_THRESHOLD = 0.35  # 余弦（向量召回）
KEYWORD_THRESHOLD = 0.15  # 重合度（关键词降级），与余弦阈值分家


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _tokens(text: str) -> set[str]:
    """轻量分词：连续汉字按 2-gram + 英文/数字词。"""
    normalized = re.sub(r"\s+", "", str(text or "")).lower()
    tokens: set[str] = set()
    for match in re.finditer(r"[a-z0-9]+", normalized):
        tokens.add(match.group(0))
    cjk = re.findall(r"[\u4e00-\u9fff]+", normalized)
    for chunk in cjk:
        if len(chunk) == 1:
            tokens.add(chunk)
            continue
        for index in range(len(chunk) - 1):
            tokens.add(chunk[index : index + 2])
    return tokens


def _keyword_score(query: str, memory: L2Memory) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    memory_tokens = _tokens(f"{memory.trigger_text} {memory.content}")
    if not memory_tokens:
        return 0.0
    overlap = len(query_tokens & memory_tokens)
    return overlap / min(len(query_tokens), len(memory_tokens))


def _profile_lines(l0, l1) -> list[str]:
    lines: list[str] = []
    l0_fields = (
        ("称呼", "call_name"),
        ("主玩", "main_role"),
        ("主练", "main_characters"),
        ("水平备注", "skill_note"),
        ("偏好", "preferences"),
        ("备注", "permanent_note"),
    )
    profile_values = [f"{label}：{getattr(l0, field)}" for label, field in l0_fields if getattr(l0, field)]
    if profile_values:
        lines.append("[玩家画像] " + "；".join(profile_values))
    l1_fields = (
        ("目标", "season_goal"),
        ("当前在练", "current_focus"),
        ("近期情绪", "recent_mood"),
    )
    state_values = [f"{label}：{getattr(l1, field)}" for label, field in l1_fields if getattr(l1, field)]
    if state_values:
        lines.append("[近期状态] " + "；".join(state_values))
    return lines


def _recall(repository: MemoryRepository, user_id: str, query: str, embedder: Any) -> list[L2Memory]:
    memories = repository.all_active_l2(user_id)
    if not memories:
        return []

    selected: list[L2Memory] = []
    use_vector = embedder is not None and any(memory.embedding for memory in memories)
    if use_vector:
        try:
            # 同步 HTTP 调用（<100ms GPU），与 RAG 既有模式一致；服务挂了走降级
            query_vector = embedder.embed_documents([query])[0]
            scored = [
                (memory, _cosine(query_vector, memory.embedding or []))
                for memory in memories
                if memory.embedding
            ]
            scored = [(memory, score) for memory, score in scored if score >= RECALL_THRESHOLD]
            scored.sort(key=lambda pair: pair[1], reverse=True)
            selected = [memory for memory, _ in scored[:RECALL_TOP_K]]
        except Exception:  # noqa: BLE001 —— embedding 服务不可用 → 关键词降级
            selected = []
            use_vector = False
    if not selected and not use_vector:
        scored = sorted(
            ((_keyword_score(query, memory), memory) for memory in memories),
            key=lambda pair: pair[0],
            reverse=True,
        )
        selected = [
            memory
            for score, memory in scored[:RECALL_TOP_K]
            if score >= KEYWORD_THRESHOLD
        ]
    for memory in selected:
        repository.update_l2_stats(memory.id)
    return selected


def build_memory_injection(
    repository: MemoryRepository,
    user_id: str | None,
    query: str,
    embedder: Any = None,
) -> str:
    """组装本轮记忆注入段；无用户或无内容返回空串。"""
    if not user_id:
        return ""
    lines = _profile_lines(repository.get_l0(user_id), repository.get_l1(user_id))
    fact_lines = _fact_lines(repository, user_id)
    if fact_lines:
        lines.append("[游戏档案] " + "；".join(fact_lines))
    recalled = _recall(repository, user_id, query, embedder)
    if recalled:
        lines.append("[相关记忆] " + "；".join(f"· {memory.content}" for memory in recalled))
    return "\n".join(lines)


def _fact_lines(repository: MemoryRepository, user_id: str) -> list[str]:
    """L1.5 事实缓存（规格 §8.1：事实要精确，情景要模糊；只做提示，精确数字靠工具现查）。"""
    try:
        facts = repository.get_facts(user_id)
    except Exception:  # noqa: BLE001 —— 缓存读取失败不中断主流程
        return []
    lines: list[str] = []
    now = int(time.time())
    for fact in facts[:3]:
        days = max(0, (now - fact.updated_at) // 86400) if fact.updated_at else None
        suffix = f"（更新于 {days} 天前）" if days is not None else ""
        lines.append(f"· {fact.fact_value[:160]}{suffix}")
    return lines
