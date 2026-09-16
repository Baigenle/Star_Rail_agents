import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from app.llm.base import LLMMessage, LLMProvider
from app.schemas.custom_character import CustomCharacterPayload, SelfReviewIssue


PLACEHOLDER_PATTERN = re.compile(
    r"(?:待填|待补|占位|暂无|todo|tbd|test|asdf|qwer|(?:a{4,})|(?:1{3,})|123+)",
    re.IGNORECASE,
)
MOJIBAKE_PATTERN = re.compile(r"(?:�|Ã.|Â.|â€|æ\S|ç\S){2,}")
ABUSIVE_PATTERN = re.compile(r"(?:傻逼|操你|去死|废物东西)", re.IGNORECASE)
SKILL_HEADING_PATTERN = re.compile(
    r"^###\s+(.+?)（(?:普攻|战技|终结技|天赋|秘技|忆灵技|忆灵天赋|欢愉技)）\s*$",
    re.MULTILINE,
)


class FabricationDetector:
    """检测草稿中的占位、乱码、复制内容与官方名称冒用。"""

    def __init__(self, docs_root: Path) -> None:
        self.docs_root = docs_root.resolve()
        self.official_names, self.official_skill_names = self._load_reference_terms()

    def detect(self, payload: CustomCharacterPayload) -> list[SelfReviewIssue]:
        issues: list[SelfReviewIssue] = []
        text_fields = self._text_fields(payload)

        if payload.name and self._normalize(payload.name) in self.official_names:
            issues.append(
                self._issue(
                    "official_name_collision",
                    "error",
                    "name",
                    f"角色名“{payload.name}”与官方角色重名，容易被误认为官方内容。",
                    "请改用原创名称；如果只是致敬，可在故事中说明而不要直接重名。",
                )
            )

        for field, value in text_fields.items():
            compact = value.strip()
            if not compact:
                continue
            if PLACEHOLDER_PATTERN.search(compact) and (
                len(compact) <= 24 or PLACEHOLDER_PATTERN.fullmatch(compact)
            ):
                issues.append(
                    self._issue(
                        "placeholder_text",
                        "error",
                        field,
                        f"“{self._excerpt(compact)}”疑似占位或测试文本。",
                        "请替换成能说明触发条件、效果对象和持续时间的正式内容。",
                    )
                )
            if MOJIBAKE_PATTERN.search(compact) or "\ufffd" in compact:
                issues.append(
                    self._issue(
                        "garbled_text",
                        "error",
                        field,
                        "内容中出现疑似编码乱码或不可识别字符。",
                        "请删除乱码并重新输入该字段。",
                    )
                )
            if ABUSIVE_PATTERN.search(compact):
                issues.append(
                    self._issue(
                        "abusive_content",
                        "error",
                        field,
                        "内容包含明显辱骂表达，不适合公开社区展示。",
                        "请改为不针对个人或群体的中性叙述。",
                    )
                )
            matched_skill = next(
                (
                    name
                    for name in self.official_skill_names
                    if len(name) >= 4 and name in compact
                ),
                None,
            )
            if matched_skill:
                issues.append(
                    self._issue(
                        "official_skill_phrase",
                        "warning",
                        field,
                        f"内容直接出现官方技能名“{matched_skill}”，需要确认是否为复制。",
                        "保留机制灵感可以，但建议改写名称与表达，形成清晰的原创差异。",
                    )
                )

        issues.extend(self._duplicated_skill_issues(payload.skills))
        return self._deduplicate(issues)

    async def detect_with_llm(
        self,
        payload: CustomCharacterPayload,
        llm: LLMProvider | None,
    ) -> tuple[list[SelfReviewIssue], bool]:
        if llm is None:
            return [], False
        allowed_fields = set(self._text_fields(payload))
        try:
            raw = await llm.complete(
                [
                    LLMMessage(
                        role="system",
                        content=(
                            "你是玩家原创角色的内容质量检查器。自定义创意不是虚假内容，"
                            "不要因为设定不存在于官方游戏就处罚。只标记明显凑字数、随手乱打、"
                            "语义完全不通、内部自相矛盾或冒充官方事实的文字。输出JSON数组，"
                            "每项只能包含field、severity、description、suggestion；severity只能是"
                            "error、warning、suggestion，最多6项。不要输出政治立场判断。"
                        ),
                    ),
                    LLMMessage(
                        role="user",
                        content=json.dumps(payload.model_dump(), ensure_ascii=False),
                    ),
                ]
            )
            document = self._parse_json_array(raw)
        except Exception:  # noqa: BLE001 - 限流/额度/网络异常时降级为纯规则审核
            return [], False
            return [], False

        issues: list[SelfReviewIssue] = []
        for item in document[:6]:
            if not isinstance(item, dict):
                continue
            field = str(item.get("field", "")).strip()
            severity = str(item.get("severity", "suggestion")).strip()
            description = str(item.get("description", "")).strip()
            suggestion = str(item.get("suggestion", "")).strip()
            if (
                field not in allowed_fields
                or severity not in {"error", "warning", "suggestion"}
                or not description
                or not suggestion
            ):
                continue
            issues.append(
                self._issue(
                    "llm_content_quality",
                    severity,
                    field,
                    description[:500],
                    suggestion[:500],
                )
            )
        return self._deduplicate(issues), True

    def _load_reference_terms(self) -> tuple[set[str], set[str]]:
        names: set[str] = set()
        skills: set[str] = set()
        manifest_path = self.docs_root / "hsr_nanoka_characters" / "manifest.json"
        if manifest_path.exists():
            try:
                document = json.loads(manifest_path.read_text(encoding="utf-8"))
                names = {
                    self._normalize(str(item.get("name", "")))
                    for item in document.get("characters", [])
                    if str(item.get("name", "")).strip()
                }
            except (OSError, ValueError, TypeError):
                names = set()
        character_dir = self.docs_root / "hsr_nanoka_characters" / "characters"
        if character_dir.exists():
            for path in character_dir.glob("*.md"):
                try:
                    skills.update(
                        name.strip()
                        for name in SKILL_HEADING_PATTERN.findall(
                            path.read_text(encoding="utf-8")
                        )
                        if name.strip()
                    )
                except OSError:
                    continue
        return names, skills

    @staticmethod
    def _text_fields(payload: CustomCharacterPayload) -> dict[str, str]:
        fields = {
            "name": payload.name or "",
            "summary": payload.summary or "",
            "core_mechanics": payload.core_mechanics or "",
            "story": payload.story or "",
        }
        fields.update({f"skills.{key}": value for key, value in payload.skills.items()})
        fields.update(
            {
                f"special_skills.{key}": value
                for key, value in payload.special_skills.items()
            }
        )
        fields.update(
            {f"eidolons.{index}": value for index, value in enumerate(payload.eidolons)}
        )
        return fields

    def _duplicated_skill_issues(self, skills: dict[str, str]) -> list[SelfReviewIssue]:
        issues: list[SelfReviewIssue] = []
        values = [(key, value.strip()) for key, value in skills.items() if value.strip()]
        duplicated: set[str] = set()
        for index, (left_key, left) in enumerate(values):
            for right_key, right in values[index + 1 :]:
                if min(len(left), len(right)) < 8:
                    continue
                if SequenceMatcher(None, left, right).ratio() > 0.8:
                    duplicated.update({left_key, right_key})
        for key in sorted(duplicated):
            issues.append(
                self._issue(
                    "duplicated_skill_text",
                    "error",
                    f"skills.{key}",
                    "该技能与其他技能描述高度重复，疑似复制粘贴或占位。",
                    "请分别写清这个技能独有的触发方式、目标和效果。",
                )
            )
        return issues

    @staticmethod
    def _parse_json_array(raw: str) -> list[dict]:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
        start, end = text.find("["), text.rfind("]")
        if start < 0 or end <= start:
            raise ValueError("模型未返回JSON数组")
        document = json.loads(text[start : end + 1])
        if not isinstance(document, list):
            raise ValueError("模型审核结果不是数组")
        return document

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
        unique: dict[tuple[str, str], SelfReviewIssue] = {}
        for issue in issues:
            unique.setdefault((issue.field, issue.code), issue)
        return list(unique.values())

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[\s·•・&]", "", value).casefold()

    @staticmethod
    def _excerpt(value: str, limit: int = 36) -> str:
        return value if len(value) <= limit else value[:limit] + "…"
