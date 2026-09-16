"""Worldbook 注入块组装（设计 §5.3）。

常驻条目（glossary）永远在最前；激活条目按 (激活分, 优先级) 排序、上限
max_active、总字数受 char_budget 硬约束（超预算砍整条，不截半条）。
DmaeParams/EntryState 数据结构也定义在此（避免与 engine 循环导入）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DmaeParams:
    max_score: float = 100.0
    threshold: float = 30.0
    # 偏离设计稿（20→35）：设计默认值下首次提及激活分 20 < 阈值 30，
    # W01 验收（首次提到即注入）不可能达成——首提即注入是本层核心价值
    user_base: float = 35.0
    wake_gamma: float = 0.5
    model_base: float = 8.0
    wake_lambda: float = 0.3
    decay_alpha: float = 1.5
    decay_beta: float = 0.3
    max_active: int = 8
    char_budget: int = 2500


@dataclass
class EntryState:
    activation: float = 0.0
    user_silence: int = 0
    model_silence: int = 0


from app.knowledge.worldbook.loader import WorldbookEntry  # noqa: E402

PREAMBLE = (
    "以下是与当前话题相关的背景知识，请在回复中自然引用，不要罗列、不要说'根据资料'。"
    "涉及具体数值、材料、攻略等长尾细节时，仍然调用 knowledge_search 等工具核实，"
    "背景知识里没有的不要编造。"
)


def build_injection(
    entries: list[WorldbookEntry],
    states: dict[str, EntryState],
    cascade_ids: set[str],
    params: DmaeParams,
) -> str:
    permanent = [entry for entry in entries if entry.permanent]
    scored = [
        entry
        for entry in entries
        if not entry.permanent
        and (
            states.get(entry.entry_id, EntryState()).activation >= params.threshold
            or entry.entry_id in cascade_ids
        )
    ]
    scored.sort(
        key=lambda entry: (
            -states.get(entry.entry_id, EntryState()).activation,
            -entry.priority,
        )
    )
    parts: list[str] = []
    total = 0
    for entry in permanent + scored[: params.max_active]:
        if total + len(entry.content) > params.char_budget:
            continue  # 超预算砍整条，不截半条
        parts.append(f"【{entry.title}】\n{entry.content}")
        total += len(entry.content)
    if not parts:
        return ""
    return PREAMBLE + "\n\n" + "\n\n".join(parts)
