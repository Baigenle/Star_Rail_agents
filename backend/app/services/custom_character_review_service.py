import json
import re
from datetime import datetime, timezone

from app.llm.base import LLMMessage, LLMProvider
from app.schemas.custom_character import CustomCharacterPayload
from app.schemas.moderation import (
    CharacterAIAssessment,
    CompletenessAssessment,
)


REQUIRED_FIELDS = (
    "name",
    "rarity",
    "element",
    "path",
    "summary",
    "roles",
    "core_mechanics",
    "base_stats",
    "skills",
)
CORE_SKILLS = {"basic", "skill", "ultimate", "talent", "technique"}


class CustomCharacterReviewService:
    def __init__(self, llm: LLMProvider | None) -> None:
        self.llm = llm

    async def assess(
        self, payload: CustomCharacterPayload
    ) -> CharacterAIAssessment:
        missing = [key for key in REQUIRED_FIELDS if not getattr(payload, key)]
        missing_skills = sorted(CORE_SKILLS - set(payload.skills))
        missing.extend(f"skills.{key}" for key in missing_skills)
        required_count = len(REQUIRED_FIELDS) + len(CORE_SKILLS)
        score = round(100 * (required_count - len(missing)) / required_count)
        consistency: list[str] = []
        numerical: list[str] = []
        lore: list[str] = []
        suggestions: list[str] = []

        if payload.path == "记忆" and not {
            "memosprite_skill",
            "memosprite_talent",
        } <= set(payload.special_skills):
            consistency.append("记忆命途角色缺少忆灵技或忆灵天赋。")
        if payload.path == "欢愉" and "elation_skill" not in payload.special_skills:
            consistency.append("欢愉命途角色缺少欢愉技。")
        if payload.base_stats:
            if payload.base_stats.speed > 180:
                numerical.append("基础速度高于180，明显超出常见官方角色区间。")
            if payload.base_stats.energy > 300:
                numerical.append("能量上限高于300，需要补充机制理由。")
            if payload.base_stats.attack > 2000:
                numerical.append("基础攻击高于2000，需要核对是否误填满级面板。")
        if missing:
            suggestions.append("先补齐发布必填字段和五项核心技能。")

        model_used = False
        if self.llm is not None:
            try:
                model_result = await self._model_assessment(payload)
                consistency.extend(model_result.get("consistency_warnings", []))
                numerical.extend(model_result.get("numerical_risks", []))
                lore.extend(model_result.get("official_lore_risks", []))
                suggestions.extend(model_result.get("suggestions", []))
                model_used = True
            except Exception:
                suggestions.append("模型辅助审核暂不可用，以上为确定性规则结果。")

        return CharacterAIAssessment(
            completeness=CompletenessAssessment(
                passed=not missing,
                score=max(0, min(100, score)),
                missing_fields=missing,
            ),
            consistency_warnings=list(dict.fromkeys(consistency)),
            numerical_risks=list(dict.fromkeys(numerical)),
            official_lore_risks=list(dict.fromkeys(lore)),
            suggestions=list(dict.fromkeys(suggestions)),
            model_used=model_used,
            generated_at=datetime.now(timezone.utc),
        )

    async def _model_assessment(
        self, payload: CustomCharacterPayload
    ) -> dict[str, list[str]]:
        assert self.llm is not None
        raw = await self.llm.complete(
            [
                LLMMessage(
                    role="system",
                    content=(
                        "你是社区自定义角色审核助手。自定义创意本身不是虚假内容。"
                        "仅检查内部矛盾、数值风险、冒充官方事实或与官方基础枚举冲突。"
                        "不得决定通过或驳回。输出JSON对象，键只能是"
                        "consistency_warnings、numerical_risks、official_lore_risks、suggestions，"
                        "每个值都是最多5条的字符串数组。"
                    ),
                ),
                LLMMessage(
                    role="user",
                    content=json.dumps(payload.model_dump(), ensure_ascii=False),
                ),
            ]
        )
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型未返回JSON")
        document = json.loads(text[start : end + 1])
        result: dict[str, list[str]] = {}
        for key in (
            "consistency_warnings",
            "numerical_risks",
            "official_lore_risks",
            "suggestions",
        ):
            values = document.get(key, [])
            if not isinstance(values, list):
                raise ValueError("模型审核字段格式错误")
            result[key] = [
                str(value).strip()[:300]
                for value in values[:5]
                if str(value).strip()
            ]
        return result
