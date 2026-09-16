"""文本预算 / 衍生问题 / 长对话摘要的单元测试。"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import AsyncMock, MagicMock

from app.core.answer_budget import budget_for, soft_trim
from app.models.chat import Conversation
from app.services.conversation_summary_service import (
    build_context_summary,
    inject_summary,
    should_refresh,
)
from app.services.follow_up_service import generate_follow_ups


def test_budget_varies_by_intent_and_depth() -> None:
    assert budget_for("story_analysis") == 600
    assert budget_for("story_analysis", "detailed") > budget_for("story_analysis")
    assert budget_for("conversation", "concise") < budget_for("conversation")
    assert budget_for(None) > 0


def test_soft_trim_keeps_sentence_boundary() -> None:
    text = "第一句话讲完了。第二句话也讲完了。第三句话很长很长很长很长很长很长很长很长。"
    trimmed = soft_trim(text, 20)
    assert trimmed.startswith("第一句话讲完了。")
    assert trimmed.endswith("……") or trimmed in text
    assert soft_trim("短文本", 100) == "短文本"


def test_follow_ups_story_suggests_expansion() -> None:
    ups = generate_follow_ups(
        "story_analysis",
        message="流萤的剧情是什么",
        entities={"mentioned_characters": [{"character_id": "1310", "name": "流萤"}]},
        answer_text="x" * 700,  # 超预算 → 第一个追问固定为展开
        depth="standard",
    )
    assert ups
    assert ups[0].startswith("把")
    assert "展开" in ups[0]


def test_follow_ups_team_guides_to_page() -> None:
    ups = generate_follow_ups(
        "team_recommendation",
        message="流萤怎么配队",
        entities={"mentioned_characters": [{"character_id": "1310", "name": "流萤"}]},
    )
    assert any("配队" in item for item in ups)


def test_follow_ups_deduplicated_and_capped() -> None:
    ups = generate_follow_ups("knowledge_qa", message="星穹是什么", entities={})
    assert len(ups) <= 3
    assert len(ups) == len(set(ups))


def test_summary_refresh_threshold() -> None:
    conv = Conversation(id="c1", user_id="u1", title="t", summary_until=0)
    assert should_refresh(conv, 6) is True
    assert should_refresh(conv, 3) is False
    conv.summary_until = 10
    assert should_refresh(conv, 16) is True
    assert should_refresh(conv, 14) is False


def test_inject_summary_prepends_entry() -> None:
    history = [{"role": "user", "content": "问题"}]
    merged = inject_summary(history, "早前聊过流萤配队")
    assert merged[0]["content"].startswith("[早前对话摘要]")
    assert merged[1] == history[0]
    assert inject_summary(history, "") == history


def test_build_context_summary_persists_and_injects() -> None:
    database = MagicMock()
    database.query.return_value.filter.return_value.count.return_value = 8
    older_messages = [
        MagicMock(role="user", content="介绍流萤"),
        MagicMock(role="assistant", content="流萤是星核猎手"),
    ]
    query_chain = database.query.return_value.filter.return_value
    query_chain.order_by.return_value.limit.return_value.all.return_value = (
        older_messages
    )
    conversation = Conversation(
        id="c1", user_id="u1", title="t", summary_text="", summary_until=0
    )
    llm = MagicMock()
    llm.complete = AsyncMock(return_value="用户询问了流萤的介绍。")

    import asyncio

    summary = asyncio.run(
        build_context_summary(database, conversation, llm)
    )
    assert summary == "用户询问了流萤的介绍。"
    assert conversation.summary_text == summary
    assert conversation.summary_until == 2
