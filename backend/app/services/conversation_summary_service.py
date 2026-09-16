"""长对话摘要服务：旧消息压缩为上下文摘要，随会话删除而清除。

策略（用户确认的渐进方案）：
- 保留最近 KEEP_RECENT 条完整消息；
- 更早的消息压缩为一段摘要存入 conversations.summary_text；
- 每当未摘要的新消息达到 REFRESH_EVERY 条时刷新一次摘要；
- 摘要以伪历史条目注入意图分析与回答上下文。
LLM 不可用或摘要失败时保留旧摘要，不影响主流程。
"""

from __future__ import annotations


from sqlalchemy.orm import Session

from app.llm.base import LLMMessage, LLMProvider
from app.models.chat import ChatMessage, Conversation

KEEP_RECENT = 6
REFRESH_EVERY = 6
MAX_SUMMARY_SOURCE = 24

SUMMARY_PROMPT = """把以下星穹铁道助手的旧对话压缩成一段上下文摘要（250字以内）。
必须保留：用户提到过的角色/队伍、用户的偏好与要求、已得到的结论要点、
未回答完的问题。用第三人称陈述句，不要对话体，不要添加原文没有的信息。"""


def _message_count(database: Session, conversation_id: str) -> int:
    return (
        database.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .count()
    )


def should_refresh(conversation: Conversation | None, message_count: int) -> bool:
    if conversation is None:
        return False
    summarized_until = conversation.summary_until or 0
    return message_count - summarized_until >= REFRESH_EVERY


async def build_context_summary(
    database: Session,
    conversation: Conversation,
    llm: LLMProvider | None,
) -> str:
    """刷新并返回会话摘要；返回空字符串表示暂无可用摘要。"""
    message_count = _message_count(database, conversation.id)
    keep_from = max(0, message_count - KEEP_RECENT)
    summarize_until = min(keep_from, MAX_SUMMARY_SOURCE)
    if summarize_until <= 0:
        return conversation.summary_text or ""

    older = (
        database.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation.id)
        .order_by(ChatMessage.created_at.asc())
        .limit(summarize_until)
        .all()
    )
    if not older:
        return conversation.summary_text or ""

    transcript = "\n".join(
        f"{'用户' if message.role == 'user' else '助手'}：{message.content[:200]}"
        for message in older
    )
    previous = conversation.summary_text or ""
    if previous:
        transcript = f"[已有摘要]{previous}\n[新增片段]{transcript}"

    if llm is None:
        return previous
    try:
        raw = await llm.complete(
            [
                LLMMessage(role="system", content=SUMMARY_PROMPT),
                LLMMessage(role="user", content=transcript[:3000]),
            ]
        )
    except Exception:  # noqa: BLE001 - 摘要失败不影响主流程
        return previous

    summary = raw.strip()[:600]
    if summary:
        conversation.summary_text = summary
        conversation.summary_until = summarize_until
        database.add(conversation)
        database.commit()
    return conversation.summary_text or ""


def inject_summary(
    history: list[dict[str, str]], summary: str
) -> list[dict[str, str]]:
    """把摘要作为伪历史首条注入，供意图分析与回答使用。"""
    if not summary:
        return history
    entry = {"role": "assistant", "content": f"[早前对话摘要] {summary}"}
    return [entry, *history]
