"""记忆层 pydantic 结构（main-agent-spec.md §8.2 的星铁适配版）。

字段名与规格保持一致；游戏语境替换为星铁（命途/角色/深渊）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class L0Profile(BaseModel):
    """永久画像：每轮全量注入 system 动态段。"""

    call_name: str = Field(default="", description="用户希望被怎么称呼（注册昵称优先）")
    main_role: str = Field(default="", description="主玩命途/定位，如「主玩毁灭」")
    main_characters: str = Field(default="", description="主练角色，如「流萤、景元」")
    skill_note: str = Field(default="", description="水平备注（用户自述为准，不妄评）")
    preferences: str = Field(default="", description="交互偏好，如「别替我排体力」「别玩梗」")
    permanent_note: str = Field(default="", description="其他稳定事实")
    field_confidence: dict[str, float] = Field(
        default_factory=dict, description="各字段当前值的置信度（MemoryJudge 合并策略用）"
    )
    updated_at: int = 0


class L1Profile(BaseModel):
    """近期状态：随对话演进，MemoryJudge 定期刷新。"""

    season_goal: str = Field(default="", description="当前版本/赛季目标，如「深渊满星」")
    current_focus: str = Field(default="", description="正在练的角色/卡关内容")
    recent_mood: str = Field(default="", description="近期情绪基调")
    round_count: int = Field(default=0, description="对话轮次计数（MemoryJudge 触发节奏用）")
    last_judged_round: int = Field(
        default=0, description="上次成功提取时的轮次游标（触发判据：差值 ≥6）"
    )
    field_confidence: dict[str, float] = Field(default_factory=dict)
    updated_at: int = 0


class L15Fact(BaseModel):
    """L1.5 事实缓存：精确数字靠工具现查，这里只存提示。"""

    fact_key: str = Field(description="如 rank_endgame / last_team / missing_materials")
    fact_value: str = Field(description="文本或 JSON 字符串")
    updated_at: int = 0


class L2Memory(BaseModel):
    """情景记忆：一次有记忆点的对话/事件。"""

    id: str = ""
    user_id: str = ""
    content: str = Field(description="一句完整的话，如「连歪三次卡池后他说想弃游，我陪他复盘到半夜」")
    trigger_text: str = Field(default="", description="什么话题应召回它，如「抽卡 歪了 弃游」")
    embedding: list[float] | None = None
    created_at: int = 0
    last_accessed_at: int = 0
    access_count: int = 0
    status: str = "active"
