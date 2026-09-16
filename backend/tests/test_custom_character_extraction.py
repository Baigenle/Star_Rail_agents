import pytest

from app.llm.base import LLMMessage, LLMProvider
from app.services.custom_character_extraction import CustomCharacterFieldExtractor


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, response: str) -> None:
        self.response = response

    async def complete(self, messages: list[LLMMessage]) -> str:
        assert "禁止推断" in messages[0].content
        return self.response

    async def stream(self, messages: list[LLMMessage]):
        if False:
            yield ""


@pytest.mark.asyncio
async def test_extractor_keeps_only_current_stage_explicit_fields() -> None:
    extractor = CustomCharacterFieldExtractor(
        FakeProvider(
            '{"fields":{"name":"量子棱镜","element":"量子",'
            '"roles":["辅助"],"invented":"不要保留"}}'
        )
    )

    fields = await extractor.extract(
        stage=1,
        message="角色叫量子棱镜，是量子属性。",
        allowed_fields={"name", "rarity", "element", "path", "summary"},
    )

    assert fields == {"name": "量子棱镜", "element": "量子"}


@pytest.mark.asyncio
async def test_extractor_has_deterministic_no_key_fallback() -> None:
    fields = await CustomCharacterFieldExtractor(None).extract(
        stage=1,
        message="角色叫量子棱镜。",
        allowed_fields={"name"},
    )
    assert fields == {}
