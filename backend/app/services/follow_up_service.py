"""按意图生成衍生问题建议，渲染为前端可点击追问按钮。

生成是确定性的模板逻辑（零成本、稳定、可测），内容基于意图与上下文实体；
生成的追问文本会被用户点击后直接作为新问题发送。
"""

from __future__ import annotations

from app.core.answer_budget import budget_for


def generate_follow_ups(
    intent: str | None,
    *,
    message: str,
    entities: dict | None = None,
    answer_text: str = "",
    depth: str | None = None,
    task_mode: str = "",
) -> list[str]:
    entities = entities or {}
    character_names = [
        str(item.get("name") or "")
        for item in (entities.get("mentioned_characters") or [])
        if item.get("name")
    ]
    first = character_names[0] if character_names else ""

    def budget_reached() -> bool:
        return len(answer_text) >= budget_for(intent, depth)

    if intent == "story_analysis":
        base = [f"把{first or '这段'}剧情的完整时间线展开讲讲", f"{first or '他'}和其他角色的关系是怎样的？"]
    elif intent == "team_recommendation":
        base = [
            "把这套配队的替代角色和适用场景讲详细一点",
            f"{first or '这个队伍'}的养成优先级是什么？",
            "去配队页自己调整" ,
        ]
    elif intent == "character_build":
        base = [f"{first or '这个角色'}的配队推荐", "需要的材料哪里刷？"]
    elif intent == "knowledge_qa" or intent == "structured_lookup":
        base = [f"{first or '这个角色'}的配队推荐", f"讲讲{first or '这个角色'}的剧情故事"]
    elif intent == "custom_character_review":
        base = ["按报告回到工坊修改后，再帮我审一次", "给我的角色配一套队"]
    elif intent == "custom_character_creation":
        base = ["继续下一阶段的创作", "看看我的角色能不能配队"]
    elif intent == "activity_strategy":
        base = ["这个活动的奖励值不值得刷", "活动用哪套配队好打"]
    elif intent == "weekly_plan":
        base = ["调整一下本周的体力安排"]
    elif intent == "conversation":
        base = ["你能帮我做什么？", "看看社区里的玩家创作角色"]
    elif intent == "memory":
        base = ["查看我现在的长期记忆"]
    else:
        base = []

    # 预算被软截断时，第一个追问固定为"展开"类，呼应"重点回答+追加提问"策略。
    if intent == "conversation" and task_mode == "capability_intro":
        # 自我认知回答的追问：点名功能时给该功能的示例问法，泛问给试玩清单。
        from app.agents.capability import find_feature

        feature = find_feature(message)
        if feature:
            base = [f"试试：「{feature['example']}」"]
        else:
            base = [
                "流萤怎么配队？",
                "卡芙卡怎么养成？",
                "看看社区里的玩家创作角色",
            ]
    elif intent == "conversation" and (
        "帮我做什么" in message
        or "能做什么" in message
        or "有什么功能" in message
    ):
        base = [
            "流萤怎么配队？",
            "卡芙卡怎么养成？",
            "看看社区里的玩家创作角色",
        ]
    if budget_reached() and intent in {
        "story_analysis",
        "knowledge_qa",
        "character_build",
        "activity_strategy",
    }:
        expand = "把刚才的内容展开讲详细一点"
        base = [expand, *base]

    cleaned: list[str] = []
    for item in base:
        text = str(item).strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned[:3]
