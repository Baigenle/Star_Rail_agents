from datetime import datetime, timezone

from app.llm.base import LLMProvider
from app.schemas.custom_character import (
    CustomCharacterPayload,
    SelfReviewCategory,
    SelfReviewIssue,
    SelfReviewReport,
)
from app.services.custom_character_review_service import CustomCharacterReviewService
from app.services.fabrication_detector import FabricationDetector


CATEGORY_DEFINITIONS = (
    ("completeness", "完整度", 30),
    ("authenticity", "内容真实性", 25),
    ("consistency", "内部一致性", 20),
    ("balance", "数值合理性", 15),
    ("compliance", "设定合规", 10),
)
CORE_SKILLS = ("basic", "skill", "ultimate", "talent", "technique")
REQUIRED_FIELDS = (
    "name",
    "rarity",
    "element",
    "path",
    "summary",
    "roles",
    "core_mechanics",
    "base_stats",
)


class PlayerReviewAgent:
    """协调确定性规则与推理模型，为作者生成提交前自查报告。"""

    name = "player_review_agent"

    def __init__(
        self,
        detector: FabricationDetector,
        llm: LLMProvider | None,
    ) -> None:
        self.detector = detector
        self.llm = llm

    async def review(self, payload: CustomCharacterPayload) -> SelfReviewReport:
        category_issues: dict[str, list[SelfReviewIssue]] = {
            key: [] for key, _, _ in CATEGORY_DEFINITIONS
        }
        category_issues["completeness"].extend(self._completeness_issues(payload))
        category_issues["authenticity"].extend(self.detector.detect(payload))
        category_issues["consistency"].extend(self._deterministic_consistency(payload))

        base_assessment = await CustomCharacterReviewService(self.llm).assess(payload)
        category_issues["consistency"].extend(
            self._messages_to_issues(
                "consistency_check",
                "warning",
                "core_mechanics",
                base_assessment.consistency_warnings,
                "请让角色定位、触发条件和技能效果保持一致。",
            )
        )
        category_issues["balance"].extend(
            self._messages_to_issues(
                "numerical_risk",
                "warning",
                "base_stats",
                base_assessment.numerical_risks,
                "请参考同定位官方角色区间，或补充异常数值对应的代价与限制。",
            )
        )
        category_issues["compliance"].extend(
            self._messages_to_issues(
                "official_lore_risk",
                "warning",
                "story",
                base_assessment.official_lore_risks,
                "请明确标注为玩家创作，避免把原创设定描述成官方事实。",
            )
        )

        llm_fabrication, fabrication_model_used = await self.detector.detect_with_llm(
            payload, self.llm
        )
        category_issues["authenticity"].extend(llm_fabrication)
        for key, values in category_issues.items():
            category_issues[key] = self._deduplicate(values)

        categories = [
            SelfReviewCategory(
                key=key,
                name=name,
                score=self._score(category_issues[key]),
                weight=weight,
                issues=category_issues[key],
            )
            for key, name, weight in CATEGORY_DEFINITIONS
        ]
        overall_score = round(
            sum(category.score * category.weight for category in categories) / 100
        )
        all_issues = [issue for category in categories for issue in category.issues]
        must_fix_count = sum(issue.severity == "error" for issue in all_issues)
        warn_count = sum(issue.severity == "warning" for issue in all_issues)
        compliance_errors = any(
            issue.severity == "error"
            for issue in category_issues["compliance"]
        )
        if compliance_errors or overall_score < 60:
            verdict = "rejected"
            summary = "草稿存在影响公开提交的明显问题，请先处理必须修复项。"
        elif must_fix_count or overall_score < 80:
            verdict = "needs_work"
            summary = "角色框架已经形成，但仍有必须修复或明显影响质量的问题。"
        else:
            verdict = "ready"
            summary = "角色档案已达到提交条件；黄色建议可继续优化，也可以确认后提交。"
        highlights = self._highlights(payload, categories)
        return SelfReviewReport(
            overall_score=overall_score,
            verdict=verdict,
            summary=summary,
            categories=categories,
            highlights=highlights,
            must_fix_count=must_fix_count,
            warn_count=warn_count,
            model_used=base_assessment.model_used or fabrication_model_used,
            generated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _completeness_issues(
        payload: CustomCharacterPayload,
    ) -> list[SelfReviewIssue]:
        issues: list[SelfReviewIssue] = []
        for field in REQUIRED_FIELDS:
            if not getattr(payload, field):
                issues.append(
                    PlayerReviewAgent._issue(
                        "missing_required_field",
                        "error",
                        field,
                        f"必填字段 {field} 尚未填写。",
                        "返回对应创作阶段补齐后再重新审核。",
                    )
                )
        for key in CORE_SKILLS:
            description = payload.skills.get(key, "").strip()
            if not description:
                issues.append(
                    PlayerReviewAgent._issue(
                        "missing_core_skill",
                        "error",
                        f"skills.{key}",
                        "核心技能描述为空。",
                        "补充技能对象、触发方式和具体效果。",
                    )
                )
            elif len(description) < 16:
                issues.append(
                    PlayerReviewAgent._issue(
                        "short_skill_description",
                        "warning",
                        f"skills.{key}",
                        f"技能描述只有 {len(description)} 个字符，信息可能不足。",
                        "建议补充效果对象、触发条件、持续时间或消耗。",
                    )
                )
        if payload.summary and len(payload.summary.strip()) < 20:
            issues.append(
                PlayerReviewAgent._issue(
                    "short_summary",
                    "warning",
                    "summary",
                    f"简介只有 {len(payload.summary.strip())} 个字符。",
                    "建议用一句话同时说明身份、战斗定位和核心特色。",
                )
            )
        if payload.core_mechanics and len(payload.core_mechanics.strip()) < 30:
            issues.append(
                PlayerReviewAgent._issue(
                    "short_core_mechanics",
                    "warning",
                    "core_mechanics",
                    "核心机制描述较短，难以判断完整循环。",
                    "建议补充触发条件、资源变化、持续时间和服务对象。",
                )
            )
        if payload.path == "记忆":
            for key in ("memosprite_skill", "memosprite_talent"):
                if not payload.special_skills.get(key, "").strip():
                    issues.append(
                        PlayerReviewAgent._issue(
                            "missing_path_skill",
                            "error",
                            f"special_skills.{key}",
                            "记忆命途角色缺少对应的忆灵技能。",
                            "返回阶段 4 补齐忆灵技与忆灵天赋。",
                        )
                    )
        if payload.path == "欢愉" and not payload.special_skills.get(
            "elation_skill", ""
        ).strip():
            issues.append(
                PlayerReviewAgent._issue(
                    "missing_path_skill",
                    "error",
                    "special_skills.elation_skill",
                    "欢愉命途角色缺少欢愉技。",
                    "返回阶段 4 补充欢愉技。",
                )
            )
        return issues

    @staticmethod
    def _deterministic_consistency(
        payload: CustomCharacterPayload,
    ) -> list[SelfReviewIssue]:
        text = " ".join(
            [payload.core_mechanics or "", *payload.skills.values()]
        )
        issues: list[SelfReviewIssue] = []
        if "辅助" in payload.roles and not any(
            keyword in text
            for keyword in ("提高", "降低", "恢复", "增益", "减抗", "减防", "加速", "拉条")
        ):
            issues.append(
                PlayerReviewAgent._issue(
                    "role_mechanic_mismatch",
                    "warning",
                    "core_mechanics",
                    "定位包含“辅助”，但现有机制没有清晰的队伍增益或敌方削弱。",
                    "说明辅助对象、增益/减益数值或触发窗口。",
                )
            )
        if "生存" in payload.roles and not any(
            keyword in text for keyword in ("治疗", "护盾", "减伤", "复活", "分摊", "抵抗")
        ):
            issues.append(
                PlayerReviewAgent._issue(
                    "role_mechanic_mismatch",
                    "warning",
                    "core_mechanics",
                    "定位包含“生存”，但技能中没有明确的治疗、防护或减伤能力。",
                    "说明角色如何维持队伍生存，以及效果持续时间。",
                )
            )
        other_elements = [
            element
            for element in ("物理", "火", "冰", "雷", "风", "量子", "虚数")
            if element != payload.element and f"{element}属性" in text
        ]
        if other_elements:
            issues.append(
                PlayerReviewAgent._issue(
                    "element_description_mismatch",
                    "warning",
                    "skills",
                    f"技能描述出现其他属性：{'、'.join(other_elements)}。",
                    "若这是刻意设计，请说明转属性机制；否则改为角色当前属性。",
                )
            )
        return issues

    @staticmethod
    def _messages_to_issues(
        code: str,
        severity: str,
        field: str,
        messages: list[str],
        suggestion: str,
    ) -> list[SelfReviewIssue]:
        return [
            PlayerReviewAgent._issue(code, severity, field, message, suggestion)
            for message in messages
        ]

    @staticmethod
    def _score(issues: list[SelfReviewIssue]) -> int:
        penalties = {"error": 35, "warning": 12, "suggestion": 5}
        return max(0, 100 - sum(penalties[issue.severity] for issue in issues))

    @staticmethod
    def _highlights(
        payload: CustomCharacterPayload,
        categories: list[SelfReviewCategory],
    ) -> list[str]:
        highlights: list[str] = []
        if payload.roles and payload.core_mechanics:
            highlights.append("角色定位与核心机制已经明确。")
        if len(payload.mechanic_tags) >= 2:
            highlights.append("机制标签足以支持后续配队分析。")
        if payload.story and len(payload.story) >= 60:
            highlights.append("背景故事具备可阅读的内容基础。")
        if all(category.score >= 90 for category in categories):
            highlights.append("五项审核维度均达到优秀区间。")
        return highlights[:4]

    @staticmethod
    def _issue(
        code: str,
        severity: str,
        field: str,
        description: str,
        suggestion: str,
    ) -> SelfReviewIssue:
        return SelfReviewIssue(
            code=code,
            severity=severity,
            field=field,
            description=description,
            suggestion=suggestion,
        )

    @staticmethod
    def _deduplicate(issues: list[SelfReviewIssue]) -> list[SelfReviewIssue]:
        unique: dict[tuple[str, str, str], SelfReviewIssue] = {}
        for issue in issues:
            unique.setdefault((issue.field, issue.code, issue.description), issue)
        return list(unique.values())
