"""配队约束的确定性解析。

从用户原始消息中解析显式约束（属性、游戏模式、稀有度上限、点名排除），
结构化后传给配队服务，保证"不想用限定五星""雷队""虚构叙事"这类条件
真正作用于候选生成，而不是停留在意图文本里。

只解析有把握的字面模式；解析结果允许为空（无约束）。
"""

from __future__ import annotations

import re

ELEMENTS = ("物理", "火", "冰", "雷", "风", "量子", "虚数")

# 场景关键词 → GAME_MODE_WEIGHTS 键（team_simulation_service）。
SCENE_GAME_MODES = {
    "虚构叙事": "pure_fiction",
    "混沌回忆": "moc",
    "忘却之庭": "moc",
    "末日幻影": "apocalyptic",
    "末日兽": "apocalyptic",
}

# "不用限定五星"类表述 → 排除所有限定五星（免费五星开拓者保留）。
LIMITED_FIVE_PATTERNS = (
    "不用限定",
    "不想用限定",
    "想用限定",
    "不要限定",
    "没有限定",
    "别用限定",
    "不使用限定",
    "零氪",
    "平民",
    "不氪金",
)
FOUR_STAR_ONLY_PATTERNS = ("全四星", "只用四星", "只要四星", "纯四星")

# 开拓者全系为免费五星，"不用限定五星"时保留。
FREE_FIVE_STAR_PREFIX = "8"

_EXCLUDE_VERBS = ("不要", "不用", "别用", "排除", "去掉", "除去")


def parse_team_constraints(
    message: str,
    *,
    known_names: dict[str, str] | None = None,
) -> dict:
    """解析配队约束。

    known_names: 归一化角色名 → 角色 ID（用于点名排除）。
    返回 {element, game_mode, allow_limited_five, max_rarity, excluded_ids}。
    """
    text = message or ""
    constraints: dict = {
        "element": None,
        "game_mode": None,
        "allow_limited_five": True,
        "max_rarity": None,
        "excluded_ids": [],
    }

    for element in ELEMENTS:
        if (
            f"{element}队" in text
            or f"{element}系" in text
            or f"{element}属性" in text
            or f"{element}队" in re.sub(r"\s", "", text)
        ):
            constraints["element"] = element
            break

    for scene, game_mode in SCENE_GAME_MODES.items():
        if scene in text:
            constraints["game_mode"] = game_mode
            break

    if any(pattern in text for pattern in FOUR_STAR_ONLY_PATTERNS):
        constraints["max_rarity"] = 4
        constraints["allow_limited_five"] = False
    elif any(pattern in text for pattern in LIMITED_FIVE_PATTERNS):
        constraints["allow_limited_five"] = False

    if known_names:
        # 排除支持连词列表："不要花火和银狼""不用A、B"。
        # 以排除动词分段，再在分段内（截至句末标点）匹配已知角色名。
        for verb in _EXCLUDE_VERBS:
            for segment in text.split(verb)[1:]:
                scope = re.split(r"[。！？!?；;\n]", segment)[0]
                for name, character_id in known_names.items():
                    if name and name in scope:
                        constraints["excluded_ids"].append(character_id)
        constraints["excluded_ids"] = list(
            dict.fromkeys(constraints["excluded_ids"])
        )

    return constraints
