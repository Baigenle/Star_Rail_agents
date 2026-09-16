"""care cue 规则测试（规格 §9.6，正则判定不用 LLM）。"""

from __future__ import annotations

from app.memory.care_cue import consume_care_cue, detect_care_cue, update_care_cue


def test_setback_triggers_support_cue():
    assert "先站队" in detect_care_cue("深渊又没满星，烦死了 连跪五把")
    assert detect_care_cue("又输了") == detect_care_cue("卡关了")


def test_emotion_and_gacha_cues():
    assert "禁止损人" in detect_care_cue("烦死了 恶心")
    assert "星琼规划" in detect_care_cue("又歪了 小保底")
    assert "建议休息" in detect_care_cue("好累，不想玩了")


def test_happy_cue():
    assert "得意" in detect_care_cue("这期虚构叙事满星了 哈哈")


def test_plain_message_no_cue():
    assert detect_care_cue("帮我看看景元的技能") == ""
    assert detect_care_cue("") == ""


class FakeConversation:
    def __init__(self):
        self.next_care_cue = None


def test_update_and_consume_cycle():
    conversation = FakeConversation()
    update_care_cue(None, conversation, "又没满星 烦死了")
    assert conversation.next_care_cue

    cue = consume_care_cue(None, conversation)
    assert "先站队" in cue
    assert conversation.next_care_cue is None  # 消费后清除，只生效一轮
    assert consume_care_cue(None, conversation) == ""


def test_none_conversation_safe():
    assert consume_care_cue(None, None) == ""
    update_care_cue(None, None, "又输了")  # 不抛
