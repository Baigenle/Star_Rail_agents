import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.team_archetype_service import (
    ArchetypeProfile,
    ObservedTeamMetaStore,
    TeamArchetypeService,
    archetype_profile_from_tags,
)
from app.services.team_simulation_service import (
    GAME_MODE_WEIGHTS,
    TAG_BUCKETS,
    TeamSimulationResult,
    TeamSimulationService,
)


@dataclass(frozen=True, slots=True)
class TeamMember:
    character_id: str
    name: str
    element: str
    roles: list[str]
    is_custom: bool = False


@dataclass(frozen=True, slots=True)
class RecommendedTeam:
    members: list[TeamMember]
    score: float
    covered_roles: list[str]
    reasons: list[str]
    source_character_ids: list[str]
    preferred_character_ids: list[str]
    missing_character_ids: list[str]
    simulation: TeamSimulationResult | None = None


@dataclass(frozen=True, slots=True)
class TeamRecommendationResult:
    theoretical: list[RecommendedTeam]
    owned: list[RecommendedTeam]
    favorite_trials: list[RecommendedTeam] = field(default_factory=list)


# 同一切换单位的不同命途/性别形态：同队只能出现一个。
# 注意不包含丹恒家族（丹恒/丹恒·饮月/丹恒·腾荒是可同队的独立单位）。
CHARACTER_VARIANT_GROUPS: tuple[tuple[str, ...], ...] = (
    tuple(str(i) for i in range(8001, 8011)),
    ("1001", "1224"),
)


def variant_group_of(character_id: str) -> str | None:
    for group in CHARACTER_VARIANT_GROUPS:
        if character_id in group:
            return group[0]
    return None


def is_team_legally_composed(member_ids: list[str]) -> bool:
    keys = [variant_group_of(str(member_id)) for member_id in member_ids]
    keys = [key for key in keys if key]
    return len(keys) == len(set(keys))


class TeamRecommendationService:
    EXCLUDED_INCOMPLETE_CHARACTER_IDS = {"1508", "1509"}

    def __init__(self, docs_root: Path) -> None:
        self.docs_root = docs_root.resolve()
        self.simulation_service = TeamSimulationService(
            self.docs_root,
            archetype_service=TeamArchetypeService(self.docs_root),
        )
        self.archetype_service = TeamArchetypeService(self.docs_root)
        self.meta_store = ObservedTeamMetaStore(self.docs_root)

    @lru_cache(maxsize=1)
    def profiles(self) -> dict[str, dict[str, Any]]:
        path = self.docs_root / "team_knowledge" / "official_combat_profiles.json"
        return json.loads(path.read_text(encoding="utf-8"))["characters"]

    @lru_cache(maxsize=1)
    def rarity_by_id(self) -> dict[str, int]:
        """角色稀有度表（角色 markdown 清单），供"不用限定五星"约束过滤。"""
        path = self.docs_root / "hsr_nanoka_characters" / "manifest.json"
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {
            str(item.get("character_id")): int(item.get("rarity") or 0)
            for item in manifest.get("characters", [])
            if item.get("character_id")
        }

    @lru_cache(maxsize=1)
    def cooccurrence(self) -> dict[str, dict[str, int]]:
        path = (
            self.docs_root
            / "team_knowledge"
            / "normalized_team_recommendations.json"
        )
        return json.loads(path.read_text(encoding="utf-8")).get("cooccurrence", {})

    @lru_cache(maxsize=1)
    def stored_team_groups(self) -> dict[str, tuple[tuple[str, ...], ...]]:
        """核心角色 -> 官方存储队伍（去掉核心本人的 3 名成员）。"""
        path = (
            self.docs_root
            / "team_knowledge"
            / "normalized_team_recommendations.json"
        )
        records = json.loads(path.read_text(encoding="utf-8")).get(
            "records", []
        )
        grouped: dict[str, list[tuple[str, ...]]] = {}
        for record in records:
            core_id = str(record.get("source_character_id") or "")
            for group in record.get("team_groups") or []:
                members = tuple(
                    str(member_id) for member_id in group if str(member_id) != core_id
                )
                if len(members) == 3:
                    grouped.setdefault(core_id, []).append(members)
        return {core_id: tuple(groups) for core_id, groups in grouped.items()}

    def _seeded_member_ids(
        self,
        core: dict[str, Any],
        pool: set[str],
    ) -> list[list[str]]:
        """存储队整队注入 + 体系内等价类换人变体。

        变体规则：把存储队中的体系引擎件替换为同定位、引擎亲和度
        不低于原成员的候选（阮·梅 <-> 同谐主/忘归人/大丽花 一类），
        每个槽位只取最优一个替换，最多产出 3 支变体。
        """
        core_id = str(core["character_id"])
        groups = self.stored_team_groups().get(core_id) or ()
        if not groups:
            return []
        core_archetype = self.archetype_service.get(core_id)
        if core_archetype is None:
            return []
        core_profile = self.archetype_service.mechanism_profiles().get(core_id) or {}
        vocabulary = self.archetype_service.mechanism_vocabulary()
        need_mapping = vocabulary.get("need_vocabulary", {})
        # 未满足硬需求的满足路径：变体替换时优先选能补上刚需的候选。
        unmet_supply: set[str] = set()
        for need in core_profile.get("needs") or []:
            if not need.get("hard"):
                continue
            mapping = need_mapping.get(str(need.get("need") or ""), {}).get(
                "satisfied_by", []
            )
            unmet_supply.update(str(tag) for tag in mapping)

        def affinity(character_id: str) -> float:
            return self.archetype_service.engine_affinity(
                core_archetype, self.archetype_service.get(character_id)
            )

        def hard_need_fit(character_id: str) -> int:
            provides = set(
                (self.archetype_service.mechanism_profiles().get(character_id) or {}).get(
                    "provides"
                )
                or []
            )
            return len(provides & unmet_supply)

        seeded: list[list[str]] = []
        seen_signatures = {
            frozenset(group) for group in groups
        }
        for group in groups[:3]:
            seeded.append(list(group))
            for slot_index in range(3):
                anchor_id = group[slot_index]
                anchor_value = affinity(anchor_id)
                if anchor_value < 0.4:
                    continue  # 非引擎件的位置不产生变体
                anchor_roles = set(
                    self.profiles().get(anchor_id, {}).get("roles") or []
                )
                best_id, best_value, best_fit = None, 0.0, -1
                for candidate_id in sorted(pool):
                    if candidate_id in group or candidate_id == core_id:
                        continue
                    profile = self.profiles().get(candidate_id)
                    if not profile or not anchor_roles & set(
                        profile.get("roles") or []
                    ):
                        continue
                    group_keys = {
                        key
                        for key in (
                            variant_group_of(str(member_id))
                            for member_id in group
                        )
                        if key is not None
                    }
                    candidate_key = variant_group_of(candidate_id)
                    if candidate_key and candidate_key in group_keys:
                        continue
                    value = affinity(candidate_id)
                    fit = hard_need_fit(candidate_id)
                    if value >= max(0.4, anchor_value - 0.05) and (
                        value > best_value
                        or (value == best_value and fit > best_fit)
                    ):
                        best_id, best_value, best_fit = candidate_id, value, fit
                if best_id is None:
                    continue
                variant = list(group)
                variant[slot_index] = best_id
                signature = frozenset(variant)
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)
                seeded.append(variant)
                if len(seeded) >= 8:
                    return seeded
        return seeded

    def recommend(
        self,
        custom: dict[str, Any],
        owned_character_ids: set[str] | None = None,
    ) -> TeamRecommendationResult:
        theoretical = self._recommend_for_pool(custom, set(self.profiles()))
        owned = (
            self._recommend_for_pool(custom, owned_character_ids)
            if owned_character_ids
            else []
        )
        return TeamRecommendationResult(
            theoretical=theoretical, owned=owned, favorite_trials=[]
        )

    def recommend_official(
        self,
        *,
        core_character_id: str,
        required_character_ids: set[str] | None = None,
        owned_character_ids: set[str] | None = None,
        preferred_character_ids: set[str] | None = None,
        excluded_character_ids: set[str] | None = None,
        require_sustain: bool = True,
        game_mode: str = "balanced",
        element_filter: str | None = None,
        allow_limited_five: bool = True,
        max_rarity: int | None = None,
    ) -> TeamRecommendationResult:
        profiles = self.profiles()
        if core_character_id not in profiles:
            raise ValueError("核心角色不存在")
        if core_character_id in self.EXCLUDED_INCOMPLETE_CHARACTER_IDS:
            raise ValueError("该角色配队资料尚未完成")
        excluded = set(excluded_character_ids or ())
        # "不用限定五星"：排除全部付费五星，仅保留开拓者（免费五星）。
        if not allow_limited_five or max_rarity == 4:
            rarity_map = self.rarity_by_id()
            for character_id, rarity in rarity_map.items():
                if (
                    character_id in profiles
                    and rarity >= 5
                    and not character_id.startswith("8")
                ):
                    excluded.add(character_id)
        excluded.discard(core_character_id)
        required = (
            set(required_character_ids or ())
            - {core_character_id}
            - excluded
        )
        invalid_required = required - set(profiles)
        if invalid_required:
            raise ValueError("指定同队角色不存在")
        if required & self.EXCLUDED_INCOMPLETE_CHARACTER_IDS:
            raise ValueError("指定同队角色配队资料尚未完成")
        if len(required) > 3:
            raise ValueError("一支队伍最多指定 4 名角色")
        preferred = set(preferred_character_ids or ()) - excluded
        core = profiles[core_character_id]
        available_ids = (
            set(profiles)
            - excluded
            - {core_character_id}
            - self.EXCLUDED_INCOMPLETE_CHARACTER_IDS
        )
        if element_filter:
            # 属性约束作用于队友候选；属性池太小（组不成三人队）时
            # 保留全池降级，由模拟评分自然处理，避免直接无解。
            element_pool = {
                character_id
                for character_id in available_ids
                if profiles[character_id].get("element") == element_filter
            }
            if len(element_pool) >= 3:
                available_ids = element_pool
        seeded = self._seeded_member_ids(core, available_ids)
        theoretical = self._recommend_for_pool(
            core,
            available_ids,
            preferred_ids=set(),
            required_ids=required,
            require_sustain=require_sustain,
            owned_ids=set(owned_character_ids or ()),
            seeded_member_ids=seeded,
        )
        owned_pool = (
            set(owned_character_ids or ())
            - excluded
            - {core_character_id}
            - self.EXCLUDED_INCOMPLETE_CHARACTER_IDS
        )
        if element_filter:
            owned_element_pool = {
                character_id
                for character_id in owned_pool
                if profiles[character_id].get("element") == element_filter
            }
            if len(owned_element_pool) >= 3:
                owned_pool = owned_element_pool
        owned = (
            self._recommend_for_pool(
                core,
                owned_pool,
                preferred_ids=set(),
                required_ids=required,
                require_sustain=require_sustain,
                seeded_member_ids=seeded,
            )
            if (
                owned_character_ids
                and core_character_id in owned_character_ids
                and required <= set(owned_character_ids)
            )
            else []
        )
        favorite_trials = (
            self._recommend_for_pool(
                core,
                available_ids,
                preferred_ids=preferred,
                required_ids=required,
                require_sustain=require_sustain,
                owned_ids=set(owned_character_ids or ()),
            )
            if preferred
            else []
        )
        base_signatures = {
            self._signature(team) for team in [*theoretical, *owned]
        }
        favorite_trials = [
            team
            for team in favorite_trials
            if team.preferred_character_ids
            and self._signature(team) not in base_signatures
        ][:3]
        theoretical = self._apply_simulation(
            self._replace_custom_lead(
                theoretical, core, set(owned_character_ids or ())
            ),
            game_mode=game_mode,
        )
        owned = self._apply_simulation(
            self._replace_custom_lead(
                owned, core, set(owned_character_ids or ())
            ),
            game_mode=game_mode,
        )
        favorite_trials = self._apply_simulation(
            self._replace_custom_lead(
                favorite_trials, core, set(owned_character_ids or ())
            ),
            game_mode=game_mode,
        )
        # 知识库锚定：核心角色的首选存储队必须出现在理论推荐中，
        # 即使包含未拥有角色（缺失照常计分标注），保证文档配队可见。
        # 用户显式约束（排除名单/稀有度上限/属性过滤）优先于锚定——
        # 存储队含被约束排除的成员时放弃锚定。
        primary_group = (
            self.stored_team_groups().get(core_character_id) or ((),)
        )[0]
        anchor_blocked = bool(
            excluded & {str(m) for m in primary_group if m}
        ) or bool(element_filter)
        if theoretical and not required and not anchor_blocked:
            expected = {str(m) for m in primary_group if m}
            if expected and not any(
                {member.character_id for member in team.members} - {"custom"}
                == expected
                for team in theoretical
            ):
                member_list = [
                    str(member_id)
                    for member_id in primary_group
                    if str(member_id) != core_character_id
                ]
                seed_profiles = [
                    self.profiles()[member_id]
                    for member_id in member_list
                    if member_id in self.profiles()
                ]
                if len(seed_profiles) == 3 and is_team_legally_composed(
                    [core_character_id, *member_list]
                ):
                    core_roles = self._normalize_roles(core.get("roles", []))
                    anchored = self._apply_simulation(
                        self._replace_custom_lead(
                            [
                                self._build_team(
                                    core,
                                    seed_profiles,
                                    self._similar_profiles(
                                        core_roles,
                                        set(core.get("mechanic_tags") or []),
                                    ),
                                    preferred_ids=set(),
                                    owned_ids=set(owned_character_ids or ()),
                                )
                            ],
                            core,
                            set(owned_character_ids or ()),
                        ),
                        game_mode=game_mode,
                    )
                    theoretical.extend(anchored)
                    # 维持 3 支契约：挤掉分数最低的非锚定队。
                    if len(theoretical) > 3:
                        pinned_ids = {id(team) for team in anchored}
                        worst = max(
                            (
                                team
                                for team in theoretical
                                if id(team) not in pinned_ids
                            ),
                            key=lambda team: (
                                len(team.missing_character_ids),
                                -team.score,
                            ),
                        )
                        theoretical.remove(worst)
                    # 按最终分排序：缺失角色已在 missing_character_ids 标注，
                    # 完全体的高分不应被缺失数压到低分队之后。
                    theoretical.sort(key=lambda team: -team.score)

        # 变体组合法性兜底：同一单位的多个命途形态不可同队。
        theoretical = [
            team
            for team in theoretical
            if is_team_legally_composed(
                [member.character_id for member in team.members]
            )
        ]
        owned = [
            team
            for team in owned
            if is_team_legally_composed(
                [member.character_id for member in team.members]
            )
        ]
        return TeamRecommendationResult(
            theoretical=theoretical,
            owned=owned,
            favorite_trials=favorite_trials,
        )

    def _apply_simulation(
        self,
        teams: list[RecommendedTeam],
        *,
        game_mode: str = "balanced",
    ) -> list[RecommendedTeam]:
        scenario_weights = GAME_MODE_WEIGHTS.get(
            game_mode, GAME_MODE_WEIGHTS["balanced"]
        )
        evaluated: list[RecommendedTeam] = []
        for team in teams:
            member_ids = [member.character_id for member in team.members]
            simulation = self.simulation_service.evaluate(
                member_ids,
                structural_score=team.score,
                profiles=self.profiles(),
                observed_meta=self.meta_store.lookup(member_ids),
                scenario_weights=scenario_weights,
            )
            evaluated.append(
                RecommendedTeam(
                    members=team.members,
                    score=simulation.final_score,
                    covered_roles=team.covered_roles,
                    reasons=[
                        *team.reasons,
                        (
                            f"机制模拟：战技点净变化 {simulation.skill_point_balance:+.2f}，"
                            f"加权场景分 "
                            f"{sum(item.score for item in simulation.scenarios) / len(simulation.scenarios):.1f}。"
                        ),
                    ],
                    source_character_ids=team.source_character_ids,
                    preferred_character_ids=team.preferred_character_ids,
                    missing_character_ids=team.missing_character_ids,
                    simulation=simulation,
                )
            )
        return sorted(
            evaluated,
            key=lambda team: (
                len(team.missing_character_ids),
                -team.score,
                self._signature(team),
            ),
        )

    def _recommend_for_pool(
        self,
        custom: dict[str, Any],
        allowed_ids: set[str],
        *,
        preferred_ids: set[str] | None = None,
        required_ids: set[str] | None = None,
        require_sustain: bool = True,
        owned_ids: set[str] | None = None,
        seeded_member_ids: list[list[str]] | None = None,
    ) -> list[RecommendedTeam]:
        profiles = {
            character_id: profile
            for character_id, profile in self.profiles().items()
            if character_id in allowed_ids
        }
        if len(profiles) < 3:
            return []

        custom_roles = self._normalize_roles(custom.get("roles", []))
        custom_tags = set(custom.get("mechanic_tags", []))
        needed = self._needed_roles(custom_roles, require_sustain=require_sustain)
        similar_ids = self._similar_profiles(custom_roles, custom_tags)
        core_archetype = self._archetype_for_custom(custom)
        preferred_ids = preferred_ids or set()
        required_ids = required_ids or set()
        required_profiles = [
            profiles[character_id]
            for character_id in sorted(required_ids)
            if character_id in profiles
        ]
        if len(required_profiles) != len(required_ids):
            return []
        if len(required_profiles) > 3:
            return []

        ranked_by_role: dict[str, list[dict[str, Any]]] = {}
        # sorted：set 遍历顺序受 PYTHONHASHSEED 影响，会让不同进程选出不同队伍。
        for role in sorted(set(needed)):
            candidates = [
                profile for profile in profiles.values() if role in profile["roles"]
            ]
            ranked_by_role[role] = sorted(
                candidates,
                key=lambda profile: (
                    -self._candidate_score(
                        profile,
                        role,
                        custom,
                        custom_tags,
                        similar_ids,
                        set(),
                        core_archetype=core_archetype,
                    ),
                    profile["character_id"],
                ),
            )

        teams: list[RecommendedTeam] = []
        signatures: set[tuple[str, ...]] = set()
        for offset in range(12):
            selected: list[dict[str, Any]] = list(required_profiles)
            remaining_needed = list(needed)
            for profile in required_profiles:
                matching_index = next(
                    (
                        index
                        for index, role in enumerate(remaining_needed)
                        if role in profile.get("roles", [])
                    ),
                    None,
                )
                if matching_index is not None:
                    remaining_needed.pop(matching_index)
            for role_index, role in enumerate(remaining_needed):
                if len(selected) >= 3:
                    break
                candidates = ranked_by_role.get(role, [])
                if not candidates:
                    continue
                start = (offset + role_index) % len(candidates)
                selected_groups = {
                    key
                    for key in (
                        variant_group_of(str(item["character_id"]))
                        for item in selected
                    )
                    if key is not None
                }
                candidate = next(
                    (
                        candidates[(start + step) % len(candidates)]
                        for step in range(len(candidates))
                        if candidates[(start + step) % len(candidates)][
                            "character_id"
                        ]
                        not in {item["character_id"] for item in selected}
                        and variant_group_of(
                            str(
                                candidates[(start + step) % len(candidates)][
                                    "character_id"
                                ]
                            )
                        )
                        not in selected_groups
                    ),
                    None,
                )
                if candidate:
                    selected.append(candidate)
            if len(selected) < 3:
                remaining = sorted(
                    (
                        profile
                        for profile in profiles.values()
                        if profile["character_id"]
                        not in {item["character_id"] for item in selected}
                    ),
                    key=lambda profile: (
                        -self._candidate_score(
                            profile,
                            "sub_dps",
                            custom,
                            custom_tags,
                            similar_ids,
                            set(),
                            core_archetype=core_archetype,
                        ),
                        profile["character_id"],
                    ),
                )
                selected.extend(remaining[: 3 - len(selected)])
            if len(selected) != 3:
                continue
            preferred_candidates = [
                profile
                for profile in profiles.values()
                if profile["character_id"] in preferred_ids
            ]
            if preferred_candidates and not any(
                item["character_id"] in preferred_ids for item in selected
            ):
                preferred_profile = max(
                    preferred_candidates,
                    key=lambda profile: self._candidate_score(
                        profile,
                        next(iter(profile["roles"]), "support"),
                        custom,
                        custom_tags,
                        similar_ids,
                        preferred_ids,
                        core_archetype=core_archetype,
                    ),
                )
                replace_index = next(
                    (
                        index
                        for index in range(len(selected) - 1, -1, -1)
                        if selected[index]["character_id"]
                        not in required_ids
                        if set(selected[index]["roles"])
                        & set(preferred_profile["roles"])
                    ),
                    None,
                )
                if replace_index is not None:
                    selected[replace_index] = preferred_profile
            selected_roles = {
                role for profile in selected for role in profile.get("roles", [])
            }
            if require_sustain and "sustain" not in selected_roles:
                continue
            if "dps" not in selected_roles and "dps" not in custom_roles:
                continue
            if not required_ids <= {
                item["character_id"] for item in selected
            }:
                continue
            signature = tuple(sorted(item["character_id"] for item in selected))
            if signature in signatures:
                continue
            signatures.add(signature)
            teams.append(
                self._build_team(
                    custom,
                    selected,
                    similar_ids,
                    preferred_ids=preferred_ids,
                    owned_ids=owned_ids,
                )
            )

        for member_ids in seeded_member_ids or []:
            member_list = [str(member_id) for member_id in member_ids]
            if len(member_list) != 3 or not set(member_list) <= set(allowed_ids):
                continue
            if not is_team_legally_composed(
                [str(custom["character_id"]), *member_list]
            ):
                continue
            seed_profiles = [
                profile
                for profile in (
                    self.profiles().get(member_id) for member_id in member_list
                )
                if profile
            ]
            if len(seed_profiles) != 3:
                continue
            seed_roles = {
                role for profile in seed_profiles for role in profile.get("roles", [])
            }
            if require_sustain and "sustain" not in seed_roles:
                continue
            if "dps" not in seed_roles and "dps" not in custom_roles:
                continue
            if not required_ids <= {
                profile["character_id"] for profile in seed_profiles
            }:
                continue
            signature = tuple(
                sorted(profile["character_id"] for profile in seed_profiles)
            )
            if signature in signatures:
                continue
            signatures.add(signature)
            teams.append(
                self._build_team(
                    custom,
                    seed_profiles,
                    similar_ids,
                    preferred_ids=preferred_ids,
                    owned_ids=owned_ids,
                )
            )
        return sorted(
            teams,
            key=lambda team: (
                len(team.missing_character_ids),
                -len(team.preferred_character_ids),
                -team.score,
                self._signature(team),
            ),
        )[:3]

    def _candidate_score(
        self,
        profile: dict[str, Any],
        needed_role: str,
        custom: dict[str, Any],
        custom_tags: set[str],
        similar_ids: list[str],
        preferred_ids: set[str],
        *,
        core_archetype: ArchetypeProfile | None = None,
    ) -> float:
        role_score = 40.0 if needed_role in profile["roles"] else 0.0
        tags = set(profile.get("mechanic_tags", []))
        mechanic_score = min(30.0, len(tags & custom_tags) * 10.0)
        history = sum(
            self.cooccurrence().get(similar_id, {}).get(
                profile["character_id"], 0
            )
            for similar_id in similar_ids
        )
        history_score = min(20.0, history * 4.0)
        element_score = 0.0
        if profile["element"] == custom.get("element"):
            element_score = 5.0
        if (
            custom.get("element") == "量子"
            and {"减抗", "量子增益"} & custom_tags
            and profile["element"] == "量子"
            and "dps" in profile["roles"]
        ):
            element_score = 20.0
        candidate_archetype = self.archetype_service.get(
            profile["character_id"]
        )
        engine_score = (
            self.archetype_service.engine_affinity(
                core_archetype, candidate_archetype
            )
            * 25.0
        )
        if (
            core_archetype is not None
            and needed_role != "sustain"
            and engine_score <= 0.0
        ):
            # 不参与核心资源循环的输出/辅助位候选降权。
            engine_score -= 12.0
        # 增益价值适配：队友的机制供给在该体系价值表中的连续权重，
        # 用于区分"体系最优件"（托帕之于飞霄）与"泛用件"（飞霄之于卡芙卡）。
        buff_fit_score = self._archetype_buff_fit(
            core_archetype, profile["character_id"]
        ) * 15.0
        return (
            role_score
            + mechanic_score
            + history_score
            + element_score
            + engine_score
            + buff_fit_score
        )

    def _archetype_buff_fit(
        self,
        core_archetype,  # ArchetypeProfile | None
        candidate_id: str,
    ) -> float:
        """候选的机制供给在核心体系增益价值表中的最高权重（0-1）。"""
        if core_archetype is None:
            return 0.0
        service = self.archetype_service
        provides = set(
            (service.mechanism_profiles().get(candidate_id) or {}).get(
                "provides"
            )
            or []
        )
        if not provides:
            return 0.0
        buff_value = service.mechanism_vocabulary().get(
            "archetype_buff_value", {}
        )
        best = 0.0
        for archetype in core_archetype.archetypes:
            row = buff_value.get(archetype) or {}
            for tag in provides:
                if str(tag).startswith("_"):
                    continue
                best = max(best, float(row.get(tag, 0.0)))
        return best

    def _archetype_for_custom(
        self, custom: dict[str, Any]
    ) -> ArchetypeProfile | None:
        """官方核心直接读体系档案；自定义角色按机制标签推断。"""
        core_id = str(custom.get("character_id") or "")
        official = self.archetype_service.get(core_id) if core_id else None
        if official:
            return official
        tags = [str(tag) for tag in custom.get("mechanic_tags", [])]
        if not tags:
            return None
        return archetype_profile_from_tags(
            core_id or "custom",
            str(custom.get("name") or "自定义角色"),
            tags,
        )

    def _build_team(
        self,
        custom: dict[str, Any],
        selected: list[dict[str, Any]],
        similar_ids: list[str],
        *,
        preferred_ids: set[str],
        owned_ids: set[str] | None,
    ) -> RecommendedTeam:
        custom_roles = self._normalize_roles(custom.get("roles", []))
        members = [
            TeamMember(
                character_id="custom",
                name=str(custom.get("name") or "自定义角色"),
                element=str(custom.get("element") or "未知"),
                roles=custom_roles,
                is_custom=True,
            ),
            *[
                TeamMember(
                    character_id=profile["character_id"],
                    name=profile["name"],
                    element=profile["element"],
                    roles=list(profile["roles"]),
                )
                for profile in selected
            ],
        ]
        covered = sorted(
            {
                role
                for member in members
                for role in member.roles
                if role in {"dps", "sub_dps", "support", "sustain"}
            }
        )
        role_score = min(40.0, len(set(covered) & {"dps", "support", "sustain"}) / 3 * 40)
        selected_tags = {
            tag for profile in selected for tag in profile.get("mechanic_tags", [])
        }
        custom_tags = set(custom.get("mechanic_tags", []))
        mechanic_score = min(30.0, len(selected_tags & custom_tags) * 10.0)
        union_tags = selected_tags | custom_tags
        buckets = {
            bucket
            for bucket in (TAG_BUCKETS.get(tag) for tag in union_tags)
            if bucket
        }
        bucket_bonus = min(6.0, len(buckets) * 1.0)
        history_score = min(
            20.0,
            sum(
                self.cooccurrence()
                .get(similar_id, {})
                .get(profile["character_id"], 0)
                for similar_id in similar_ids
                for profile in selected
            )
            * 2.0,
        )
        element_score = (
            10.0
            if any(
                profile["element"] == custom.get("element")
                for profile in selected
            )
            else 0.0
        )
        reasons = [
            f"定位覆盖：{', '.join(covered)}",
            f"机制交集：{', '.join(sorted(selected_tags & custom_tags)) or '基础定位互补'}",
            f"增益分桶覆盖 {len(buckets)} 个乘区（{', '.join(sorted(buckets)) or '无'}）。",
            "候选来自已规范化的官方角色档案与现有配队共现统计。",
        ]
        selected_ids = {profile["character_id"] for profile in selected}
        preferred_hits = sorted(selected_ids & preferred_ids)
        missing_ids = sorted(selected_ids - set(owned_ids or ())) if owned_ids else []
        if preferred_hits:
            reasons.append(f"已纳入 {len(preferred_hits)} 名偏好角色。")
        if missing_ids:
            reasons.append(f"仍缺少 {len(missing_ids)} 名角色，已在理论评分中扣分。")
        ownership_score = (
            len(selected_ids & set(owned_ids or ())) / 3 * 12 if owned_ids else 0
        )
        final_score = (
            role_score
            + mechanic_score
            + history_score
            + element_score
            + bucket_bonus
            + ownership_score
            - len(missing_ids) * 8
        )
        return RecommendedTeam(
            members=members,
            score=round(max(0.0, min(100.0, final_score)), 2),
            covered_roles=covered,
            reasons=reasons,
            source_character_ids=similar_ids[:3],
            preferred_character_ids=preferred_hits,
            missing_character_ids=missing_ids,
        )

    def _similar_profiles(
        self, custom_roles: list[str], custom_tags: set[str]
    ) -> list[str]:
        def score(profile: dict[str, Any]) -> tuple[int, int]:
            return (
                len(set(profile["roles"]) & set(custom_roles)) * 3
                + len(set(profile.get("mechanic_tags", [])) & custom_tags),
                int(float(profile.get("confidence", 0)) * 10),
            )

        return [
            profile["character_id"]
            for profile in sorted(
                self.profiles().values(),
                key=lambda profile: (
                    -score(profile)[0],
                    -score(profile)[1],
                    profile["character_id"],
                ),
            )[:5]
        ]

    @staticmethod
    def _normalize_roles(roles: list[str]) -> list[str]:
        mapping = {
            "主C": "dps",
            "副C": "sub_dps",
            "辅助": "support",
            "生存": "sustain",
        }
        return list(dict.fromkeys(mapping.get(role, role) for role in roles))

    @staticmethod
    def _needed_roles(
        custom_roles: list[str], *, require_sustain: bool = True
    ) -> list[str]:
        if "dps" in custom_roles:
            return ["support", "support", "sustain" if require_sustain else "sub_dps"]
        if "sustain" in custom_roles:
            return ["dps", "support", "sub_dps"]
        return ["dps", "support", "sustain" if require_sustain else "sub_dps"]

    @staticmethod
    def _replace_custom_lead(
        teams: list[RecommendedTeam], core: dict[str, Any], owned_ids: set[str]
    ) -> list[RecommendedTeam]:
        lead = TeamMember(
            character_id=core["character_id"],
            name=core["name"],
            element=core["element"],
            roles=list(core["roles"]),
        )
        return [
            RecommendedTeam(
                members=[lead, *team.members[1:]],
                score=team.score,
                covered_roles=team.covered_roles,
                reasons=team.reasons,
                source_character_ids=team.source_character_ids,
                preferred_character_ids=team.preferred_character_ids,
                missing_character_ids=sorted(
                    {
                        *team.missing_character_ids,
                        *(
                            []
                            if core["character_id"] in owned_ids
                            else [core["character_id"]]
                        ),
                    }
                ),
                simulation=team.simulation,
            )
            for team in teams
        ]

    @staticmethod
    def _signature(team: RecommendedTeam) -> str:
        return ",".join(member.character_id for member in team.members)
