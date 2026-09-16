import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from statistics import mean
from typing import Any

from app.services.team_archetype_service import TeamArchetypeService


# 游戏模式 → 场景权重（数据来源 docs/team_benchmark/scenarios.json 的 weight 字段）。
GAME_MODE_WEIGHTS: dict[str, dict[str, float]] = {
    "balanced": {"single_boss": 0.34, "dual_elite": 0.33, "five_targets": 0.33},
    "moc": {"single_boss": 0.6, "dual_elite": 0.3, "five_targets": 0.1},
    "pure_fiction": {"single_boss": 0.05, "dual_elite": 0.25, "five_targets": 0.7},
    "apocalyptic": {"single_boss": 0.7, "dual_elite": 0.25, "five_targets": 0.05},
}

# 机制标签 → 增益分桶。跨桶增益相乘，同桶堆叠收益递减，
# 因此协同分按"覆盖多少个不同乘区"计，而不是共享标签总数。
TAG_BUCKETS: dict[str, str] = {
    "增伤": "damage_amp",
    "暴击": "crit_amp",
    "减抗": "res_shred",
    "减防": "def_shred",
    "易伤": "vulnerability",
    "拉条": "action_economy",
    "速度": "action_economy",
    "能量": "energy_economy",
    "战技点": "skill_point_economy",
    "治疗": "survivability",
    "护盾": "survivability",
    "净化": "survivability",
    "击破": "break_engine",
    "持续伤害": "dot_engine",
    "追加攻击": "fua_engine",
    "召唤": "summon_engine",
}


@dataclass(frozen=True, slots=True)
class CharacterCombatParameters:
    character_id: str
    name: str
    roles: list[str]
    mechanic_tags: list[str]
    game_data_version: str
    speed: float
    max_energy: float | None
    skill_point_delta: float
    estimated_ultimate_turns: float | None
    skill_point_fields_found: bool
    data_confidence: float


@dataclass(frozen=True, slots=True)
class ScenarioSimulation:
    scenario_id: str
    name: str
    score: float


@dataclass(frozen=True, slots=True)
class TeamSimulationResult:
    scoring_version: str
    game_data_version: str
    structural_score: float
    mechanical_simulation_score: float
    observed_meta_score: float | None
    evidence_confidence: float
    final_score: float
    skill_point_balance: float
    estimated_ultimate_turns: dict[str, float | None]
    speed_order: list[str]
    scenarios: list[ScenarioSimulation]
    knowledge_score: float = 50.0
    knowledge_notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class TeamSimulationService:
    SCORING_VERSION = "team_score_v3"

    def __init__(
        self,
        docs_root: Path,
        archetype_service: TeamArchetypeService | None = None,
    ) -> None:
        self.docs_root = docs_root.resolve()
        self.archetype_service = archetype_service

    @lru_cache(maxsize=1)
    def profiles(self) -> dict[str, dict[str, Any]]:
        path = self.docs_root / "team_knowledge" / "official_combat_profiles.json"
        return json.loads(path.read_text(encoding="utf-8"))["characters"]

    @lru_cache(maxsize=1)
    def scenarios(self) -> list[dict[str, Any]]:
        path = self.docs_root / "team_benchmark" / "scenarios.json"
        return json.loads(path.read_text(encoding="utf-8"))["scenarios"]

    @lru_cache(maxsize=256)
    def character_parameters(self, character_id: str) -> CharacterCombatParameters:
        profile = self.profiles().get(character_id)
        if profile is None:
            raise ValueError(f"角色不存在：{character_id}")
        matches = sorted(
            (self.docs_root / "hsr_nanoka_characters" / "characters").glob(
                f"{character_id}_*.md"
            )
        )
        if not matches:
            raise ValueError(f"角色缺少战斗档案：{character_id}")
        text = matches[0].read_text(encoding="utf-8")
        version = self._capture(text, r'data_version:\s*"([^"]+)"') or "unknown"
        energy = self._number(text, r"\|\s*终结技能量\s*\|\s*([\d.]+)\s*\|")
        speed = self._estimated_level_80_speed(text)
        has_sp_fields = bool(re.search(r"\|\s*(?:sp_base|bp_need|bp_add)\s*\|", text))
        roles = list(profile.get("roles", []))
        tags = list(profile.get("mechanic_tags", []))
        skill_point_cost = self._skill_point_cost(text)
        if skill_point_cost is not None:
            skill_point_delta = self._data_driven_skill_point_delta(
                roles, skill_point_cost
            )
        else:
            skill_point_delta = self._rotation_skill_point_delta(roles, tags)
        action_energy = self._action_energy_estimate(text, roles)
        ultimate_turns = (
            round(energy / action_energy, 2)
            if energy is not None and action_energy > 0
            else None
        )
        confidence = float(profile.get("confidence", 0.5)) * 0.6
        confidence += 0.15 if speed is not None else 0
        confidence += 0.15 if energy is not None else 0
        confidence += 0.1 if has_sp_fields else 0
        return CharacterCombatParameters(
            character_id=character_id,
            name=str(profile["name"]),
            roles=roles,
            mechanic_tags=tags,
            game_data_version=version,
            speed=float(speed or 100),
            max_energy=energy,
            skill_point_delta=skill_point_delta,
            estimated_ultimate_turns=ultimate_turns,
            skill_point_fields_found=has_sp_fields,
            data_confidence=round(min(1.0, confidence), 3),
        )

    def evaluate(
        self,
        member_ids: list[str],
        *,
        structural_score: float,
        profiles: dict[str, dict[str, Any]] | None = None,
        observed_meta: dict[str, Any] | None = None,
        scenario_weights: dict[str, float] | None = None,
    ) -> TeamSimulationResult:
        if len(member_ids) != 4 or len(set(member_ids)) != 4:
            raise ValueError("机制模拟要求4名不重复角色")
        known_profiles = profiles or self.profiles()
        unknown = sorted(set(member_ids) - set(known_profiles))
        if unknown:
            raise ValueError(f"角色不存在：{', '.join(unknown)}")
        parameters = [self.character_parameters(member_id) for member_id in member_ids]
        return self.evaluate_parameters(
            parameters,
            structural_score=structural_score,
            observed_meta=observed_meta,
            scenario_weights=scenario_weights,
        )

    def evaluate_parameters(
        self,
        parameters: list[CharacterCombatParameters],
        *,
        structural_score: float,
        observed_meta: dict[str, Any] | None = None,
        scenario_weights: dict[str, float] | None = None,
    ) -> TeamSimulationResult:
        if len(parameters) != 4:
            raise ValueError("机制模拟要求4名角色参数")
        versions = {item.game_data_version for item in parameters}
        game_version = next(iter(versions)) if len(versions) == 1 else "mixed"
        warnings: list[str] = []
        if len(versions) != 1:
            warnings.append("角色档案版本不一致，置信度已降低。")

        sp_balance = round(sum(item.skill_point_delta for item in parameters), 2)
        # 钟形曲线：小幅盈余(+0.4/回合)最理想；严重过剩说明产点浪费，不足则战技点枯竭。
        sp_score = max(30.0, min(100.0, 100.0 - abs(sp_balance - 0.4) * 30.0))
        ultimate_values = [
            item.estimated_ultimate_turns
            for item in parameters
            if item.estimated_ultimate_turns is not None
        ]
        energy_score = (
            max(0.0, min(100.0, 115.0 - mean(ultimate_values) * 12.5))
            if ultimate_values
            else 40.0
        )
        speed_values = [item.speed for item in parameters]
        speed_spread = max(speed_values) - min(speed_values)
        speed_score = max(35.0, 100.0 - max(0.0, speed_spread - 20.0) * 1.5)
        sustain_count = sum(
            1 for item in parameters if "sustain" in item.roles
        )
        sustain_score = (
            100.0 if sustain_count == 1 else (45.0 if sustain_count == 0 else 78.0)
        )
        synergy_score = self._mechanic_synergy_score(parameters)
        core_archetype = (
            self.archetype_service.get(parameters[0].character_id)
            if self.archetype_service
            else None
        )
        if self.archetype_service and core_archetype is not None:
            # 引擎参与度：非生存队友若与核心体系零亲和，说明没参与资源循环。
            non_sustain_idle = sum(
                1
                for item in parameters
                if "sustain" not in item.roles
                and self.archetype_service.engine_affinity(
                    core_archetype,
                    self.archetype_service.get(item.character_id),
                )
                <= 0.0
            )
            synergy_score = max(
                0.0, synergy_score - non_sustain_idle * 10.0
            )
        scenario_affinity = (
            self.archetype_service.scenario_affinity(core_archetype)
            if self.archetype_service
            else {}
        )
        scenario_results = self._scenario_scores(
            parameters, scenario_affinity=scenario_affinity
        )
        scenario_score = self._weighted_scenario_score(
            scenario_results, scenario_weights
        )
        knowledge_score, knowledge_notes = self._knowledge_score(parameters)
        # 机械核心（不含场景）：体系知识主导后稀释为平局裁决
        mechanical_core = (
            sp_score * 0.27
            + energy_score * 0.20
            + speed_score * 0.13
            + synergy_score * 0.27
            + sustain_score * 0.13
        )
        confidence = mean(item.data_confidence for item in parameters) * 100
        if len(versions) != 1:
            confidence *= 0.75
        if any(not item.skill_point_fields_found for item in parameters):
            warnings.append("部分角色缺少战技点字段，轮转使用定位模板估算。")
            confidence *= 0.9

        meta_score = self._validated_meta_score(
            observed_meta, game_version=game_version, warnings=warnings
        )
        if meta_score is None:
            final_score = (
                knowledge_score * 0.55
                + scenario_score * 0.20
                + mechanical_core * 0.15
                + confidence * 0.10
            )
            warnings.append("暂无同版本结构化实战样本，最终分未混入实战先验。")
        else:
            final_score = (
                knowledge_score * 0.40
                + meta_score * 0.25
                + scenario_score * 0.15
                + mechanical_core * 0.12
                + confidence * 0.08
            )

        return TeamSimulationResult(
            scoring_version=self.SCORING_VERSION,
            game_data_version=game_version,
            structural_score=round(max(0.0, min(100.0, structural_score)), 2),
            knowledge_score=round(max(0.0, min(100.0, knowledge_score)), 2),
            knowledge_notes=knowledge_notes,
            mechanical_simulation_score=round(mechanical_core, 2),
            observed_meta_score=meta_score,
            evidence_confidence=round(confidence, 2),
            final_score=round(max(0.0, min(100.0, final_score)), 2),
            skill_point_balance=sp_balance,
            estimated_ultimate_turns={
                item.character_id: item.estimated_ultimate_turns
                for item in parameters
            },
            speed_order=[
                item.character_id
                for item in sorted(
                    parameters, key=lambda item: (-item.speed, item.character_id)
                )
            ],
            scenarios=scenario_results,
            warnings=list(dict.fromkeys(warnings)),
        )

    def _knowledge_score(
        self, parameters: list[CharacterCombatParameters]
    ) -> tuple[float, list[str]]:
        """机制知识分：硬/软需求满足 + 引擎参与 + 增益价值适配。

        数据源 docs/team_knowledge/mechanism_profiles.json（画像）
        与 mechanism_vocabulary.json（需求->满足路径映射）。
        任一文件缺失时返回中性 50 分并说明，评分优雅降级。
        """
        notes: list[str] = []
        if not self.archetype_service:
            return 50.0, notes
        profiles = self.archetype_service.mechanism_profiles()
        if not profiles:
            return 50.0, notes
        vocabulary = self.archetype_service.mechanism_vocabulary()
        satisfaction = vocabulary.get("need_vocabulary", {})
        buff_value = vocabulary.get("archetype_buff_value", {})

        core = profiles.get(str(parameters[0].character_id))
        if not core:
            return 50.0, ["核心角色缺少机制画像，知识分取中性值。"]
        core_archetypes = self._core_archetype_names(core)
        score = 50.0

        # 1) 需求满足：硬需求缺失重罚，软需求满足加分
        teammate_provides: list[set[str]] = []
        for item in parameters[1:]:
            mate = profiles.get(str(item.character_id)) or {}
            teammate_provides.append(set(mate.get("provides") or []))
        for need in core.get("needs") or []:
            need_name = str(need.get("need") or "")
            mapping = satisfaction.get(need_name, {}).get(
                "satisfied_by", [need_name]
            )
            satisfied = any(
                provides & set(mapping) for provides in teammate_provides
            )
            if need.get("hard"):
                if satisfied:
                    score += 12.0
                    notes.append(f"硬需求已满足：{need_name}")
                else:
                    score -= 25.0
                    notes.append(f"硬需求未满足：{need_name}（队伍基本不成立）")
            elif satisfied:
                score += 6.0
                notes.append(f"软需求已满足：{need_name}")

        # 2) 引擎参与 + 增益价值适配（非生存队友）
        core_archetype = self.archetype_service.get(
            str(parameters[0].character_id)
        )
        value_rows = [
            buff_value.get(name, {}) for name in core_archetypes
        ]
        merged_value: dict[str, float] = {}
        for row in value_rows:
            for key, value in row.items():
                if key.startswith("_"):
                    continue
                merged_value[key] = max(
                    merged_value.get(key, 0.0), float(value)
                )
        for item in parameters[1:]:
            if "sustain" in item.roles:
                continue
            mate = profiles.get(str(item.character_id)) or {}
            mate_provides = set(mate.get("provides") or [])
            if core_archetype is not None:
                affinity = self.archetype_service.engine_affinity(
                    core_archetype,
                    self.archetype_service.get(str(item.character_id)),
                )
                if affinity >= 0.4:
                    score += 5.0
                elif affinity <= 0.0:
                    score -= 8.0
                    notes.append(
                        f"{item.name} 未参与核心资源循环（引擎亲和 0）"
                    )
            if merged_value:
                best = max(
                    (
                        merged_value.get(tag, 0.0)
                        for tag in mate_provides
                    ),
                    default=0.0,
                )
                if best <= 0.05:
                    score -= 6.0
                    notes.append(
                        f"{item.name} 的增益供给对本体系价值≈0"
                    )
                elif best >= 0.8:
                    score += 4.0
        return max(0.0, min(100.0, score)), notes

    @staticmethod
    def _core_archetype_names(core: dict) -> list[str]:
        return [str(name) for name in (core.get("archetypes") or [])]

    def _scenario_scores(
        self,
        parameters: list[CharacterCombatParameters],
        *,
        scenario_affinity: dict[str, float] | None = None,
    ) -> list[ScenarioSimulation]:
        dps_count = sum("dps" in item.roles for item in parameters)
        sub_dps_count = sum("sub_dps" in item.roles for item in parameters)
        all_tags = {tag for item in parameters for tag in item.mechanic_tags}
        affinity = scenario_affinity or {}
        results: list[ScenarioSimulation] = []
        for scenario in self.scenarios():
            scenario_id = str(scenario["id"])
            if scenario_id == "single_boss":
                score = 58 + dps_count * 12 + len(
                    all_tags & {"击破", "追加攻击", "减抗", "减防"}
                ) * 4
            elif scenario_id == "dual_elite":
                score = 55 + dps_count * 9 + sub_dps_count * 6 + len(
                    all_tags & {"扩散", "追加攻击", "减抗", "拉条"}
                ) * 4
            else:
                score = 48 + dps_count * 7 + sub_dps_count * 7 + len(
                    all_tags & {"扩散", "持续伤害", "追加攻击", "多段攻击", "召唤"}
                ) * 5
            score += affinity.get(scenario_id, 0.0) * 100
            results.append(
                ScenarioSimulation(
                    scenario_id=scenario_id,
                    name=str(scenario["name"]),
                    score=round(max(0.0, min(100.0, score)), 2),
                )
            )
        return results

    @staticmethod
    def _weighted_scenario_score(
        scenario_results: list[ScenarioSimulation],
        scenario_weights: dict[str, float] | None,
    ) -> float:
        if not scenario_results:
            return 0.0
        if not scenario_weights:
            return mean(item.score for item in scenario_results)
        total_weight = sum(
            scenario_weights.get(item.scenario_id, 0.0)
            for item in scenario_results
        )
        if total_weight <= 0:
            return mean(item.score for item in scenario_results)
        return sum(
            item.score * scenario_weights.get(item.scenario_id, 0.0)
            for item in scenario_results
        ) / total_weight

    @staticmethod
    def _mechanic_synergy_score(
        parameters: list[CharacterCombatParameters],
    ) -> float:
        tag_counts: dict[str, int] = {}
        for item in parameters:
            for tag in set(item.mechanic_tags):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        shared = sum(count - 1 for count in tag_counts.values() if count > 1)
        support_tags = {
            "增伤",
            "减抗",
            "减防",
            "拉条",
            "能量",
            "速度",
            "战技点",
            "治疗",
            "护盾",
            "净化",
        }
        support_coverage = len(set(tag_counts) & support_tags)
        # 增益分桶：全队覆盖的不同乘区数量决定增益组合的实际收益。
        buckets = {
            TAG_BUCKETS[tag]
            for tag in tag_counts
            if tag in TAG_BUCKETS
        }
        bucket_diversity = len(buckets)
        return max(
            35.0,
            min(
                100.0,
                40.0
                + bucket_diversity * 6
                + support_coverage * 3
                + shared * 2,
            ),
        )

    @staticmethod
    def _validated_meta_score(
        observed_meta: dict[str, Any] | None,
        *,
        game_version: str,
        warnings: list[str],
    ) -> float | None:
        if not observed_meta:
            return None
        if observed_meta.get("game_version") != game_version:
            warnings.append("实战统计与角色档案跨版本，已从最终评分中排除。")
            return None
        try:
            score = float(observed_meta["score"])
            sample_size = int(observed_meta["sample_size"])
            source_url = str(observed_meta["source_url"])
        except (KeyError, TypeError, ValueError):
            warnings.append("实战统计缺少分数、样本量或来源，已排除。")
            return None
        if not 0 <= score <= 100 or sample_size <= 0 or not source_url.startswith(
            ("https://", "http://")
        ):
            warnings.append("实战统计未通过边界校验，已排除。")
            return None
        return round(score, 2)

    @staticmethod
    def _rotation_skill_point_delta(roles: list[str], tags: list[str]) -> float:
        if "dps" in roles:
            value = -0.5
        elif "sub_dps" in roles:
            value = 0.0
        elif "sustain" in roles:
            value = 0.35
        else:
            value = 0.25
        if "战技点" in tags:
            value += 0.35
        if "强化普攻" in tags or "战技点联动" in tags:
            value -= 0.25
        return round(value, 2)

    @staticmethod
    def _skill_point_cost(text: str) -> float | None:
        """从战技段落解析标准战技点消耗（bp_need，正数=消耗）。"""
        skill_section = re.search(
            r"###\s*[^\n]*（战技）\s*\n(.*?)(?=\n###|\Z)",
            text,
            flags=re.DOTALL,
        )
        if not skill_section:
            return None
        match = re.search(
            r"\|\s*bp_need\s*\|\s*(-?[\d.]+)\s*\|",
            skill_section.group(1),
        )
        return float(match.group(1)) if match else None

    @classmethod
    def _data_driven_skill_point_delta(
        cls, roles: list[str], skill_point_cost: float
    ) -> float:
        """按角色档案的真实战技点消耗与定位轮转假设估算每回合净变化。

        每 4 回合窗口：DPS 3 战技 1 普攻，副C/辅助 2+2，生存 1+3；
        战技消耗 skill_point_cost 点，普攻产出 1 点。
        """
        if "dps" in roles:
            skills = 3
        elif "sustain" in roles:
            skills = 1
        elif "sub_dps" in roles:
            skills = 2
        else:
            skills = 2
        basics = 4 - skills
        cost = max(0.0, min(2.0, skill_point_cost))
        delta = (basics * 1.0 - skills * cost) / 4.0
        return round(delta, 2)

    @classmethod
    def _action_energy_estimate(cls, text: str, roles: list[str]) -> float:
        values = [
            float(value)
            for value in re.findall(r"\|\s*sp_base\s*\|\s*([\d.]+)\s*\|", text)
            if float(value) > 5
        ]
        if values:
            return max(20.0, min(35.0, mean(values)))
        return 28.0 if "dps" in roles else 25.0

    @classmethod
    def _estimated_level_80_speed(cls, text: str) -> float | None:
        match = re.search(
            r"\|\s*生命值\s*\|\s*攻击力\s*\|\s*防御力\s*\|\s*速度\s*\|"
            r"\s*嘲讽值\s*\|.*?\n\|[-:|\s]+\|\s*\n"
            r"\|[^|\n]+\|[^|\n]+\|[^|\n]+\|\s*([\d.]+)\s*\|",
            text,
            flags=re.DOTALL,
        )
        return float(match.group(1)) if match else None

    @staticmethod
    def _capture(text: str, pattern: str) -> str | None:
        match = re.search(pattern, text)
        return match.group(1) if match else None

    @classmethod
    def _number(cls, text: str, pattern: str) -> float | None:
        value = cls._capture(text, pattern)
        return float(value) if value is not None else None
