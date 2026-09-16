"""按意图类型配置的回答长度预算与软截断。

预算是"建议上限"而非硬砍：超出时优先在句号/问号/感叹号边界截断，
避免把句子拦腰斩断。数值可在 ANSWER_BUDGETS 中直接调整。
"""

from __future__ import annotations

import re

# 每意图类型的字符预算（按答案深度自动缩放：detailed ×1.8，concise ×0.6）。
ANSWER_BUDGETS: dict[str, int] = {
    "story_analysis": 600,  # 剧情：先给核心段，用户追问再展开（detailed 时 1080）
    "team_recommendation": 500,  # 配队：top1 重点，详情引导去配队页
    "custom_team_recommendation": 500,
    "knowledge_qa": 650,
    "structured_lookup": 450,
    "character_build": 550,
    "material_query": 400,
    "activity_strategy": 550,
    "weekly_plan": 400,
    "memory": 300,
    "conversation": 220,
    "conversation_recall": 320,
    "custom_character_creation": 300,
    "custom_character_review": 700,  # 自查报告信息密度高，预算最宽
    "custom_character_review_report": 700,
}

DEFAULT_BUDGET = 600

_SENTENCE_END = re.compile(r"([。！？!?…]+[”』」）)]*)")


def budget_for(intent: str | None, depth: str | None = None) -> int:
    base = ANSWER_BUDGETS.get(intent or "", DEFAULT_BUDGET)
    if depth == "detailed":
        return int(base * 1.8)
    if depth == "concise":
        return int(base * 0.6)
    return base


def soft_trim(text: str, budget: int) -> str:
    """超出预算时在句子边界软截断，并保证至少保留首句。"""
    if len(text) <= budget:
        return text
    head = text[:budget]
    ends = list(_SENTENCE_END.finditer(head))
    # 从预算位置向前找最近的句子边界；找不到就退回硬截断+省略号。
    cut = ends[-1].end() if ends else budget
    trimmed = head[:cut].rstrip()
    return f"{trimmed}……"
