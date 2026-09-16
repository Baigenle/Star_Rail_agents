"""care cue（规格 §9.6）：正则检测用户情绪，写一句"下轮回应提示"。

规则判定（问答卷 Q8：不用 LLM，毫秒级），存 conversations.next_care_cue，
下一轮注入 [回应提示] 后消费清除。"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.chat import Conversation

# (正则, 回应提示)。按优先级排列，首个命中即用。
_CUE_RULES: tuple[tuple[str, str], ...] = (
    (r"连(跪|败)|又输了|没满星|差一刀|卡关了?|打不过", "用户受挫，先站队承认局面，再给一个可执行止损动作"),
    (r"烦死了|气死了|恶心坏了?|心态崩了?|麻了", "用户情绪差，先接情绪，本轮禁止损人"),
    (r"好累|困死了?|不想玩(了)?|想弃游|想退坑", "用户疲惫，别上强度，建议休息或换轻松内容"),
    (r"歪了|小保底|大保底|沉船|没抽到|吃满保底", "抽卡受挫，站队一起吐槽策划，再谈星琼规划"),
    (r"哈哈+|太开心|爽到了?|满星了?|一次过|出了?!|抽到了?", "用户开心，可以一起得意，嘴硬式夸"),
)


def detect_care_cue(message: str) -> str:
    text = str(message or "")
    for pattern, cue in _CUE_RULES:
        if re.search(pattern, text):
            return cue
    return ""


def update_care_cue(session: Session, conversation: Conversation | None, message: str) -> None:
    """回复完成后调用：用本轮用户消息刷新下一轮的回应提示。"""
    if conversation is None:
        return
    conversation.next_care_cue = detect_care_cue(message)


def consume_care_cue(session: Session, conversation: Conversation | None) -> str:
    """下一轮组装时调用：读取并清除（提示只生效一轮）。"""
    if conversation is None:
        return ""
    cue = str(getattr(conversation, "next_care_cue", "") or "")
    if cue:
        conversation.next_care_cue = None
    return cue
