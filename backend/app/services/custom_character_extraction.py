import json
import re

from app.llm.base import LLMMessage, LLMProvider


class CustomCharacterFieldExtractor:
    def __init__(self, llm: LLMProvider | None) -> None:
        self.llm = llm

    async def extract(
        self,
        *,
        stage: int,
        message: str,
        allowed_fields: set[str],
    ) -> dict[str, object]:
        if self.llm is None:
            return {}
        raw = await self.llm.complete(
            [
                LLMMessage(
                    role="system",
                    content=(
                        "你是黑塔角色创作工坊的结构化字段提取器。"
                        "只能提取用户本句明确提供的信息，禁止推断、补造或采用你自己的建议。"
                        "输出单个 JSON 对象，格式为 {\"fields\": {...}}。"
                        f"当前阶段为 {stage}，允许字段只有："
                        f"{', '.join(sorted(allowed_fields))}。"
                        "无法确定的字段不要输出。"
                    ),
                ),
                LLMMessage(role="user", content=message),
            ]
        )
        document = self._json_object(raw)
        fields = document.get("fields", {})
        if not isinstance(fields, dict):
            raise ValueError("LLM fields must be an object")
        return {key: value for key, value in fields.items() if key in allowed_fields}

    @staticmethod
    def _json_object(raw: str) -> dict[str, object]:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("LLM response did not contain a JSON object")
        document = json.loads(text[start : end + 1])
        if not isinstance(document, dict):
            raise ValueError("LLM response must be a JSON object")
        return document
