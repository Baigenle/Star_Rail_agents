import re
from pathlib import Path

from app.agents.base import AgentContext, BaseAgent
from app.schemas.ai_response import (
    AIResponse,
    Citation,
    Claim,
    FilteringReport,
    QueryStep,
    ValidationReport,
)
from app.services.team_recommendation_service import (
    TeamRecommendationService,
    variant_group_of,
)
from app.services.team_constraints import parse_team_constraints
from app.services.team_reasoning_service import TeamReasoningService
from app.llm.base import LLMProvider
from app.schemas.team import (
    OfficialRecommendedTeam,
    OfficialTeamMember,
    TeamRotationSummary,
    TeamScenarioScore,
    TeamScoreBreakdown,
)


class TeamRecommendationAgent(BaseAgent):
    name = "team_recommendation_agent"
    description = "根据官方战斗档案、共现统计和用户角色池生成队伍"

    def __init__(
        self, docs_root: Path, reasoning_llm: LLMProvider | None = None
    ) -> None:
        self.service = TeamRecommendationService(docs_root)
        self.reasoning = TeamReasoningService(reasoning_llm)
                # 终审只做解释与排序微调，用快档模型保证交互延迟。

    async def run(self, context: AgentContext) -> AIResponse:
        profiles = self.service.profiles()
        mentioned_ids = [
            str(item.get("character_id", ""))
            for item in context.entities.get("mentioned_characters", [])
            if str(item.get("character_id", "")) in profiles
        ]
        # 家族泛名（如「开拓者」命中全系变体）按变体组去重，各变体互斥同队，
        # 保留第一个作为核心候选。
        deduped_ids: list[str] = []
        seen_variant_groups: set[str] = set()
        for character_id in mentioned_ids:
            group = variant_group_of(character_id)
            if group:
                if group in seen_variant_groups:
                    continue
                seen_variant_groups.add(group)
            deduped_ids.append(character_id)
        mentioned_ids = list(dict.fromkeys(deduped_ids))
        core_id = (
            mentioned_ids[0]
            if mentioned_ids
            else self._core_id(context.message, profiles)
        )
        owned_ids = set(context.entities.get("owned_character_ids", []))
        favorite_ids = set(context.entities.get("favorite_character_ids", []))

        # 显式配队约束（属性/场景/稀有度/点名排除）：确定性解析，直接作用于候选。
        constraints = parse_team_constraints(
            context.message,
            known_names={
                self._normalize(str(profile["name"])): character_id
                for character_id, profile in profiles.items()
            },
        )
        constraint_notes: list[str] = []
        if not core_id and constraints["element"]:
            # 冷启动"帮我配一队X队"：核心直接选该属性角色。
            core_id = self._core_by_element(
                constraints["element"],
                profiles,
                self.service.rarity_by_id(),
                allow_limited_five=constraints["allow_limited_five"],
                max_rarity=constraints["max_rarity"],
            )
        if (
            constraints["element"]
            and core_id
            and profiles[core_id].get("element") != constraints["element"]
            and profiles[core_id]["name"] not in context.message
        ):
            # 核心来自历史实体carryover且与显式属性约束冲突：以约束为准重选核心。
            replacement = self._core_by_element(
                constraints["element"],
                profiles,
                self.service.rarity_by_id(),
                allow_limited_five=constraints["allow_limited_five"],
                max_rarity=constraints["max_rarity"],
            )
            if replacement:
                core_id = replacement
        if core_id and constraints["element"] and not mentioned_ids:
            # 没点名核心却要"X队"：核心选该属性角色（优先输出定位）。
            if profiles[core_id].get("element") != constraints["element"]:
                core_id = (
                    self._core_by_element(
                        constraints["element"],
                        profiles,
                        self.service.rarity_by_id(),
                        allow_limited_five=constraints["allow_limited_five"],
                        max_rarity=constraints["max_rarity"],
                    )
                    or core_id
                )
        if not core_id:
            core_id = next(iter(favorite_ids & set(profiles)), None)
        if not core_id:
            return self._missing_core()

        excluded_ids = set(constraints["excluded_ids"])
        if not constraints["allow_limited_five"]:
            constraint_notes.append("不含限定五星")
        if constraints["max_rarity"] == 4:
            constraint_notes.append("仅四星及以下")
        if constraints["element"] and constraints["element"] != profiles[core_id].get("element"):
            constraint_notes.append(f"队友仅{constraints['element']}属性")
        elif constraints["element"]:
            constraint_notes.append(f"{constraints['element']}属性队")
        if constraints["game_mode"]:
            mode_names = {
                "pure_fiction": "虚构叙事",
                "moc": "混沌回忆",
                "apocalyptic": "末日幻影",
            }
            constraint_notes.append(
                f"按{mode_names.get(constraints['game_mode'], constraints['game_mode'])}场景加权"
            )
        if excluded_ids:
            excluded_names = [
                profiles[item]["name"]
                for item in excluded_ids
                if item in profiles
            ]
            if excluded_names:
                constraint_notes.append(
                    f"已排除：{'、'.join(excluded_names[:4])}"
                )

        result = self.service.recommend_official(
            core_character_id=core_id,
            required_character_ids=set(mentioned_ids[1:]),
            owned_character_ids=owned_ids,
            preferred_character_ids=favorite_ids,
            excluded_character_ids=excluded_ids,
            require_sustain=True,
            game_mode=constraints["game_mode"] or "balanced",
            element_filter=constraints["element"],
            allow_limited_five=constraints["allow_limited_five"],
            max_rarity=constraints["max_rarity"],
        )
        # 渐进放宽：约束组合可能组不成完整队（如某属性没有五星生存位）。
        # 优先放宽属性过滤，其次放宽稀有度，每次放宽都在回答里注明。
        while not (
            result.owned or result.theoretical or result.favorite_trials
        ):
            if constraints["element"]:
                constraint_notes = [
                    note
                    for note in constraint_notes
                    if not note.endswith("属性队")
                    and not note.startswith("队友仅")
                ]
                constraint_notes.append(
                    f"「{constraints['element']}属性」下组不成定位完整的队伍，"
                    "已放宽属性限制"
                )
                constraints["element"] = None
            elif not constraints["allow_limited_five"]:
                constraint_notes = [
                    note for note in constraint_notes if note != "不含限定五星"
                ]
                constraint_notes.append(
                    "排除限定五星后组不成完整队伍，已放宽稀有度限制"
                )
                constraints["allow_limited_five"] = True
                constraints["max_rarity"] = None
            else:
                break
            excluded_ids = set(constraints["excluded_ids"])
            result = self.service.recommend_official(
                core_character_id=core_id,
                required_character_ids=set(mentioned_ids[1:]),
                owned_character_ids=owned_ids,
                preferred_character_ids=favorite_ids,
                excluded_character_ids=excluded_ids,
                require_sustain=True,
                game_mode=constraints["game_mode"] or "balanced",
                element_filter=constraints["element"],
                allow_limited_five=constraints["allow_limited_five"],
                max_rarity=constraints["max_rarity"],
            )
        if not (
            result.owned or result.theoretical or result.favorite_trials
        ):
            return AIResponse(
                agent=self.name,
                answer=(
                    "现有条件和角色池下组不出定位完整的四人队。"
                    "先放宽限制（指定核心角色、放开属性或稀有度），我再重新配。"
                ),
                claims=[],
                citations=[],
                validation=ValidationReport(
                    status="unverified",
                    method="constraint_no_solution",
                    evidence_count=0,
                    notes=["约束组合下无合法候选队伍。"],
                ),
                filtering=FilteringReport(
                    passed=False,
                    removed_claims=0,
                    rules=["组不出合法四人队时不猜测队伍。"],
                ),
                query_steps=[
                    QueryStep(
                        id="official_team_recommendation",
                        name="官方配队推荐 Agent",
                        status="fallback",
                        detail="约束组合下未生成候选队伍。",
                        duration_ms=0,
                    )
                ],
            )
        teams = [
            *result.owned,
            *result.theoretical,
            *result.favorite_trials,
        ]
        unique = []
        seen: set[tuple[str, ...]] = set()
        for team in teams:
            signature = tuple(member.character_id for member in team.members)
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(team)
            if len(unique) == 6:
                break
        assessed, model_name = await self.reasoning.assess(
            [
                OfficialRecommendedTeam(
                    members=[
                        OfficialTeamMember(
                            character_id=member.character_id,
                            name=member.name,
                            element=member.element,
                            roles=member.roles,
                            mechanic_tags=list(
                                profiles[member.character_id].get(
                                    "mechanic_tags", []
                                )
                            ),
                        )
                        for member in team.members
                    ],
                    score=team.score,
                    covered_roles=team.covered_roles,
                    reasons=team.reasons,
                    strengths=[],
                    weaknesses=[],
                    source_character_ids=team.source_character_ids,
                    preferred_character_ids=team.preferred_character_ids,
                    missing_character_ids=team.missing_character_ids,
                    score_breakdown=(
                        TeamScoreBreakdown(
                            scoring_version=team.simulation.scoring_version,
                            game_data_version=team.simulation.game_data_version,
                            structural_score=team.simulation.structural_score,
                            mechanical_simulation_score=(
                                team.simulation.mechanical_simulation_score
                            ),
                            observed_meta_score=team.simulation.observed_meta_score,
                            evidence_confidence=team.simulation.evidence_confidence,
                            final_score=team.simulation.final_score,
                            scenarios=[
                                TeamScenarioScore(
                                    scenario_id=scenario.scenario_id,
                                    name=scenario.name,
                                    score=scenario.score,
                                )
                                for scenario in team.simulation.scenarios
                            ],
                        )
                        if team.simulation
                        else None
                    ),
                    rotation=(
                        TeamRotationSummary(
                            skill_point_balance=team.simulation.skill_point_balance,
                            estimated_ultimate_turns=(
                                team.simulation.estimated_ultimate_turns
                            ),
                            speed_order=team.simulation.speed_order,
                        )
                        if team.simulation
                        else None
                    ),
                    data_warnings=(
                        team.simulation.warnings if team.simulation else []
                    ),
                )
                for team in unique
            ]
        )
        citations = [
            Citation(
                id="C1",
                title="官方角色战斗档案",
                source="docs/team_knowledge/official_combat_profiles.json",
                excerpt="角色属性、命途、战斗定位与机制标签。",
            ),
            Citation(
                id="C2",
                title="规范化配队共现记录",
                source="docs/team_knowledge/normalized_team_recommendations.json",
                excerpt="现有配队推荐中的角色共现与来源记录。",
            ),
            Citation(
                id="C3",
                title="统一练度与机制模拟基线",
                source="docs/team_benchmark/benchmark_assumptions.json",
                excerpt="角色、光锥、遗器、初始战技点与模拟次数的统一实验条件。",
            ),
            Citation(
                id="C4",
                title="单体、双精英与五目标场景",
                source="docs/team_benchmark/scenarios.json",
                excerpt="三类合成敌人环境及弱点、抗性和结果报告规则。",
            ),
        ]
        # 终审可能按 judge 排名重排（assessed 内是带复核字段的 enriched 副本），
        # 渲染直接以 assessed 为准，杜绝"成员列表是 A 队、复核文本是 B 队"的错位。
        render_teams: list = (
            list(assessed) if len(assessed) == len(unique) else list(unique)
        )
        claims = [
            Claim(
                statement="、".join(member.name for member in team.members),
                confidence=max(0.5, min(0.95, team.score / 100)),
                citation_ids=["C1", "C2", "C3", "C4"],
            )
            for team in (render_teams or unique)
        ]
        owned_signatures = {
            tuple(member.character_id for member in team.members)
            for team in result.owned
        }
        favorite_signatures = {
            tuple(member.character_id for member in team.members)
            for team in result.favorite_trials
        }
        answers = []
        is_pair_question = len(mentioned_ids) > 1
        for index, team in enumerate(render_teams, start=1):
            signature = tuple(
                member.character_id for member in team.members
            )
            kind = (
                "角色池可用"
                if signature in owned_signatures
                else "猜你喜欢尝试"
                if signature in favorite_signatures
                else "理论推荐"
            )
            names = '、'.join(member.name for member in team.members)
            if index == 1:
                # 预算策略：top1 给完整解说，其余队伍压成一行备用方案，
                # 详情引导用户去配队页（回答层瘦身，避免刷屏）。
                team_lines = [
                    f"{kind} 1：{names}（{team.score:.0f} 综合分）[C1][C2][C3][C4]"
                ]
                if team.model_assessment:
                    team_lines.append(f"模型复核：{team.model_assessment}")
                strengths = team.strengths or team.reasons[:2]
                weaknesses = (
                    team.weaknesses or self._deterministic_weaknesses(team)
                )
                if strengths:
                    team_lines.append(f"优点：{'；'.join(strengths[:3])}")
                if weaknesses:
                    team_lines.append(f"缺点：{'；'.join(weaknesses[:3])}")
                team_lines.append(
                    "想自己调整成员或看完整评分明细，去配队页操作即可。"
                )
            else:
                team_lines = [
                    f"{kind} {index}：{names}（{team.score:.0f} 综合分）——备用方案"
                ]
            answers.append("\n".join(team_lines))

        if constraint_notes:
            answers.insert(
                0, "已按条件执行：" + "、".join(constraint_notes) + "。"
            )

        if is_pair_question:
            # enriched 队伍同时携带确定性分数与 judge 复核字段，成对传入避免错位。
            verdict = self._pair_verdict(render_teams, render_teams)
            requested_names = "和".join(
                profiles[character_id]["name"]
                for character_id in mentioned_ids
            )
            answers.insert(
                0,
                f"结论：{requested_names}{verdict}",
            )
        return AIResponse(
            agent=self.name,
            answer="\n".join(answers),
            claims=claims,
            citations=citations,
            validation=ValidationReport(
                status="verified" if claims else "unverified",
                method="role_validation+rotation_simulation+scenario_scoring+model_review",
                evidence_count=4 if claims else 0,
                notes=[
                    "候选队伍已校验四名角色不重复、基础定位覆盖和角色池范围。",
                    (
                        f"{model_name} 已复核机制协同，但不能修改成员或分数。"
                        if model_name
                        else "模型不可用，本次使用确定性结果。"
                    ),
                ],
            ),
            filtering=FilteringReport(
                passed=bool(claims),
                removed_claims=0,
                rules=[
                    "角色池可用队只保留用户已拥有角色。",
                    "排除重复角色与基础定位不完整队伍。",
                ],
                warnings=(
                    []
                    if result.owned
                    else ["当前角色池不足以生成完整用户可用队，仅返回理论推荐。"]
                ),
            ),
            query_steps=[
                QueryStep(
                    id="official_team_recommendation",
                    name="官方配队推荐 Agent",
                    status="completed" if claims else "fallback",
                    detail=(
                        f"以 {profiles[core_id]['name']} 为核心"
                        + (
                            f"，固定搭配 "
                            f"{'、'.join(profiles[item]['name'] for item in mentioned_ids[1:])}"
                            if len(mentioned_ids) > 1
                            else ""
                        )
                        + "，"
                        f"生成 {len(result.theoretical)} 支理论队和 {len(result.owned)} 支角色池队。"
                    ),
                    duration_ms=0,
                ),
                QueryStep(
                    id="team_mechanic_simulation",
                    name="配队机制模拟 Agent",
                    status="completed" if claims else "fallback",
                    detail="完成战技点、能量循环、速度顺序和三类敌人场景模拟。",
                    duration_ms=0,
                ),
                QueryStep(
                    id="team_model_reasoning",
                    name="配队推理评审 Agent",
                    status="completed" if model_name else "fallback",
                    detail=(
                        f"{model_name} 已按角色定位与机制标签逐队复核。"
                        if model_name
                        else "推理模型不可用，未改变确定性候选。"
                    ),
                    duration_ms=0,
                ),
            ],
        )

    @staticmethod
    def _pair_verdict(
        teams: list,
        assessments: list[OfficialRecommendedTeam],
    ) -> str:
        if not teams:
            return (
                "不建议强行一起配队。当前档案无法补出定位完整且通过校验的"
                "四人队，先不要为了同时上场牺牲基础队伍结构。"
            )
        best_team = teams[0]
        best_assessment = assessments[0] if assessments else None
        model_verdict = (
            best_assessment.model_verdict if best_assessment else None
        )
        if best_team.score >= 70 and model_verdict != "not_recommended":
            return (
                f"可以一起配队。当前最佳候选为 {best_team.score:.0f} 分，"
                "下面给出满足两者同时上场的完整队伍。"
            )
        if (
            best_team.score >= 58
            and model_verdict in {None, "compatible", "conditional"}
        ):
            return (
                f"可以尝试，但不是优先推荐。当前最佳候选只有 "
                f"{best_team.score:.0f} 分，需要接受下面列出的循环或定位短板。"
            )
        return (
            f"不建议强行一起配队。当前最佳候选仅 {best_team.score:.0f} 分，"
            "协同收益不足以覆盖下面列出的队伍缺点。"
        )

    @staticmethod
    def _deterministic_weaknesses(team) -> list[str]:
        """兼容两种队伍对象：内部 RecommendedTeam(.simulation) 与
        渲染层 OfficialRecommendedTeam(.rotation/.score_breakdown)。"""
        weaknesses: list[str] = []
        simulation = getattr(team, "simulation", None)
        rotation = getattr(team, "rotation", None)
        balance = None
        if simulation is not None:
            balance = simulation.skill_point_balance
        elif rotation is not None:
            balance = getattr(rotation, "skill_point_balance", None)
        if balance is not None and balance < 0:
            weaknesses.append(
                f"战技点净变化 {balance:+.2f}，循环存在压力"
            )
        if getattr(team, "missing_character_ids", None):
            weaknesses.append(
                f"当前角色池仍缺少 {len(team.missing_character_ids)} 名队员"
            )
        if getattr(team, "score", 0) < 70:
            weaknesses.append("综合分未达到优先推荐阈值 70")
        if not weaknesses:
            weaknesses.append("评分来自统一模拟基线，仍需按实际敌人弱点调整")
        return weaknesses

    @classmethod
    def _core_id(cls, message: str, profiles: dict[str, dict]) -> str | None:
        normalized = cls._normalize(message)
        matches = [
            profile
            for profile in profiles.values()
            if cls._normalize(str(profile["name"])) in normalized
        ]
        if not matches:
            return None
        return max(
            matches, key=lambda item: len(cls._normalize(str(item["name"])))
        )["character_id"]

    @staticmethod
    def _core_by_element(
        element: str,
        profiles: dict[str, dict],
        rarity_by_id: dict[str, int] | None = None,
        *,
        allow_limited_five: bool = True,
        max_rarity: int | None = None,
    ) -> str | None:
        """按属性约束选核心：尊重稀有度约束，优先输出定位，稳定按 ID 序决胜。"""
        rarity_by_id = rarity_by_id or {}
        candidates = [
            profile
            for profile in profiles.values()
            if profile.get("element") == element
        ]
        if not allow_limited_five or max_rarity == 4:
            candidates = [
                profile
                for profile in candidates
                if rarity_by_id.get(str(profile["character_id"]), 5) < 5
                or str(profile["character_id"]).startswith("8")
            ]
        if not candidates:
            return None
        strikers = [
            profile
            for profile in candidates
            if any(
                keyword in " ".join(profile.get("roles") or [])
                for keyword in ("输出", "主C", "主c")
            )
        ]
        pool = strikers or candidates
        return sorted(pool, key=lambda item: str(item["character_id"]))[0][
            "character_id"
        ]

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", value).lower()

    def _missing_core(self) -> AIResponse:
        return AIResponse(
            agent=self.name,
            answer="先告诉我想围绕哪名角色配队；登录后也可以直接使用你标记喜欢的角色。",
            claims=[],
            citations=[],
            validation=ValidationReport(
                status="unverified",
                method="core_character_required",
                evidence_count=0,
                notes=["未识别到核心角色。"],
            ),
            filtering=FilteringReport(
                passed=False,
                removed_claims=0,
                rules=["没有核心角色时不猜测队伍。"],
            ),
            query_steps=[
                QueryStep(
                    id="official_team_recommendation",
                    name="官方配队推荐 Agent",
                    status="fallback",
                    detail="等待用户指定核心角色。",
                    duration_ms=0,
                )
            ],
        )
