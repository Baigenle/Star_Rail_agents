"""体系（archetype）感知数据服务与实战元数据仓库。

体系数据来自 docs/team_knowledge/character_archetypes.json
（由 scripts/build_archetype_profiles.py 生成，可人工修订）。
数据文件缺失时服务优雅降级：所有亲和度返回中性值，评分退回标签通用逻辑。
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ArchetypeProfile:
    character_id: str
    name: str
    primary_stat: str
    archetypes: list[str]
    engine_tags: list[str]
    sp_profile: str
    core_mechanic: str


# 核心体系 → 引擎标签权重。候选角色命中这些标签说明它参与核心的资源循环。
CORE_ENGINE_TAGS: dict[str, dict[str, float]] = {
    "超击破": {"击破": 1.0, "减抗": 0.7, "减防": 0.6, "战技点": 0.4},
    "持续伤害": {"持续伤害": 1.0, "减抗": 0.8, "减防": 0.6, "易伤": 0.6},
    "追加攻击": {"追加攻击": 1.0, "暴击": 0.7, "拉条": 0.6, "增伤": 0.5},
    "召唤": {"召唤": 0.9, "能量": 0.9, "拉条": 0.9, "增伤": 0.5},
    "记忆忆灵": {"治疗": 0.9, "拉条": 0.7, "增伤": 0.5, "护盾": 0.4},
    "黄泉充能": {"减抗": 0.9, "减防": 0.9, "易伤": 0.7, "持续伤害": 0.5},
    "暴击直伤": {"暴击": 0.8, "拉条": 0.8, "增伤": 0.8, "能量": 0.6, "战技点": 0.6},
}

# 核心体系 → 高价值候选体系。
ARCHETYPE_MATCH: dict[str, tuple[str, ...]] = {
    "超击破": ("超击破", "减抗辅助"),
    "持续伤害": ("持续伤害", "减抗辅助"),
    "追加攻击": ("追加攻击", "增益辅助"),
    "召唤": ("召唤", "增益辅助"),
    "记忆忆灵": ("记忆忆灵", "增益辅助", "生存辅助"),
    "黄泉充能": ("减抗辅助", "持续伤害"),
    "暴击直伤": ("暴击直伤", "增益辅助", "生存辅助"),
}

# 缩放属性 → 额外引擎标签权重（停云式攻击辅助对生命/防御缩放核心价值低）。
SCALING_ENGINE_TAGS: dict[str, dict[str, float]] = {
    "hp": {"治疗": 0.9, "护盾": 0.5, "追加攻击": 0.5},
    "defense": {"追加攻击": 0.6, "治疗": 0.4},
    "attack": {},
}

# 核心体系 → 场景亲和度加成（0-1，乘以场景分后作小幅度修正）。
SCENARIO_AFFINITY: dict[str, dict[str, float]] = {
    "持续伤害": {"five_targets": 0.06, "dual_elite": 0.02},
    "追加攻击": {"single_boss": 0.05},
    "超击破": {"single_boss": 0.05, "dual_elite": 0.03},
    "暴击直伤": {"single_boss": 0.03},
    "召唤": {"dual_elite": 0.03, "five_targets": 0.02},
    "记忆忆灵": {"single_boss": 0.03},
    "黄泉充能": {"single_boss": 0.04, "five_targets": 0.03},
}


class TeamArchetypeService:
    """角色体系档案的只读访问与引擎亲和度计算。"""

    def __init__(self, docs_root: Path) -> None:
        self.docs_root = docs_root.resolve()

    @lru_cache(maxsize=1)
    def profiles(self) -> dict[str, ArchetypeProfile]:
        path = self.docs_root / "team_knowledge" / "character_archetypes.json"
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8")).get(
            "characters", {}
        )
        profiles: dict[str, ArchetypeProfile] = {}
        for character_id, item in raw.items():
            profiles[str(character_id)] = ArchetypeProfile(
                character_id=str(character_id),
                name=str(item.get("name") or ""),
                primary_stat=str(item.get("primary_stat") or "attack"),
                archetypes=[str(tag) for tag in item.get("archetypes") or []],
                engine_tags=[str(tag) for tag in item.get("engine_tags") or []],
                sp_profile=str(item.get("sp_profile") or "neutral"),
                core_mechanic=str(item.get("core_mechanic") or ""),
            )
        return profiles

    def get(self, character_id: str) -> ArchetypeProfile | None:
        return self.profiles().get(str(character_id))

    @lru_cache(maxsize=1)
    def mechanism_profiles(self) -> dict[str, dict[str, Any]]:
        path = (
            self.docs_root
            / "team_knowledge"
            / "mechanism_profiles.json"
        )
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {
            str(character_id): item
            for character_id, item in raw.get("characters", {}).items()
        }

    @lru_cache(maxsize=1)
    def mechanism_vocabulary(self) -> dict[str, Any]:
        path = (
            self.docs_root
            / "team_knowledge"
            / "mechanism_vocabulary.json"
        )
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def engine_affinity(
        self,
        core: ArchetypeProfile | None,
        candidate: ArchetypeProfile | None,
    ) -> float:
        """核心与候选的引擎契合度，0-1；任一缺失时返回 0（中性）。"""
        if core is None or candidate is None:
            return 0.0
        best = 0.0
        for archetype in core.archetypes:
            tag_weights = CORE_ENGINE_TAGS.get(archetype, {})
            scaling_weights = SCALING_ENGINE_TAGS.get(
                core.primary_stat, {}
            )
            merged = {**tag_weights, **scaling_weights}
            score = sum(
                weight
                for tag, weight in merged.items()
                if tag in candidate.engine_tags
                or tag in candidate.archetypes
            )
            if candidate.archetypes and set(
                candidate.archetypes
            ) & set(ARCHETYPE_MATCH.get(archetype, ())):
                score += 0.3
            best = max(best, min(1.0, score))
        return round(best, 3)

    def scenario_affinity(
        self, core: ArchetypeProfile | None
    ) -> dict[str, float]:
        if core is None:
            return {}
        affinity: dict[str, float] = {}
        for archetype in core.archetypes:
            for scenario_id, value in SCENARIO_AFFINITY.get(
                archetype, {}
            ).items():
                affinity[scenario_id] = max(
                    affinity.get(scenario_id, 0.0), value
                )
        return affinity


def archetype_profile_from_tags(
    character_id: str, name: str, tags: list[str]
) -> ArchetypeProfile:
    """为自定义角色（无体系档案）按机制标签推断体系画像。"""
    archetype_rules = {
        "超击破": ("击破",),
        "持续伤害": ("持续伤害",),
        "追加攻击": ("追加攻击", "反击"),
        "召唤": ("召唤", "忆灵"),
        "暴击直伤": ("暴击",),
    }
    archetypes = [
        archetype
        for archetype, keywords in archetype_rules.items()
        if any(keyword in tags for keyword in keywords)
    ] or ["暴击直伤"]
    return ArchetypeProfile(
        character_id=str(character_id),
        name=name,
        primary_stat="attack",
        archetypes=archetypes,
        engine_tags=list(tags)[:6],
        sp_profile="neutral",
        core_mechanic="由机制标签推断。",
    )


class ObservedTeamMetaStore:
    """实战使用率元数据仓库。

    数据文件 docs/team_benchmark/observed_team_meta.json 的 entries 结构：
      {"member_ids": ["1310", ...], "game_version": "4.4.51", "mode": "moc",
       "score": 92.5, "sample_size": 16423, "source_url": "https://..."}
    仅当 game_version 与角色档案版本一致、样本量 > 0 且来源为 http(s)
    时才会进入最终评分（校验逻辑复用 TeamSimulationService）。
    """

    def __init__(self, docs_root: Path) -> None:
        self.docs_root = docs_root.resolve()

    @lru_cache(maxsize=1)
    def entries(self) -> dict[frozenset[str], dict[str, Any]]:
        path = (
            self.docs_root
            / "team_benchmark"
            / "observed_team_meta.json"
        )
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
        indexed: dict[frozenset[str], dict[str, Any]] = {}
        for entry in raw.get("entries", []):
            member_ids = entry.get("member_ids")
            if not isinstance(member_ids, list) or not member_ids:
                continue
            key = frozenset(str(item) for item in member_ids)
            if len(key) != len(member_ids):
                continue
            indexed[key] = entry
        return indexed

    def lookup(self, member_ids: list[str]) -> dict[str, Any] | None:
        return self.entries().get(frozenset(member_ids))
