"""集中式 Agent 注册表。

每个专业 Agent 在此声明：服务的意图、展示名、供主 Agent 规划使用的简介、
可产生的页面动作与确定性兜底路由关键词。
新增 Agent 只需在 build_agent_registry 中注册一条，不再需要改动多处分发代码。
"""

from dataclasses import dataclass, field

from app.agents.base import BaseAgent


@dataclass(frozen=True, slots=True)
class AgentActionSpec:
    """Agent 回答完成后主 Agent 可以生成的页面动作。"""

    url: str
    title: str
    description: str = ""
    prefill_character: bool = False


@dataclass(frozen=True, slots=True)
class AgentDescriptor:
    intent: str
    title: str
    description: str
    keywords: tuple[str, ...] = field(default_factory=tuple)
    action: AgentActionSpec | None = None


CONVERSATION = AgentDescriptor(
    intent="conversation",
    title="日常对话",
    description="问候、致谢、助手身份说明与无需游戏事实的闲聊",
    keywords=("你好", "您好", "嗨", "谢谢", "谢了", "感谢", "你是谁", "自我介绍", "能做什么"),
)
CONVERSATION_RECALL = AgentDescriptor(
    intent="conversation_recall",
    title="会话回忆",
    description="回忆本会话之前聊过或回答过的内容",
    keywords=(
        "刚才聊",
        "刚才说",
        "之前聊",
        "之前说",
        "前面说",
        "我问过",
        "你回答过",
        "还记得",
    ),
)
KNOWLEDGE_QA = AgentDescriptor(
    intent="knowledge_qa",
    title="知识问答",
    description="角色、光锥、遗器、物品等官方事实的检索问答",
    keywords=(("攻略", "怎么打", "打法")),
)
STRUCTURED_LOOKUP = AgentDescriptor(
    intent="structured_lookup",
    title="档案速查",
    description="明确点名单个角色时的面板、简介与技能档案精确查询，跳过向量检索",
    keywords=("技能面板", "面板", "属性面板", "满级属性", "80级属性"),
)
STORY_ANALYSIS = AgentDescriptor(
    intent="story_analysis",
    title="剧情分析",
    description="角色故事、角色关系、剧情任务、世界观与势力时间线",
    keywords=("剧情", "世界观", "势力", "时间线", "关系", "认识吗", "互动"),
    action=AgentActionSpec(
        url="/stories",
        title="去剧情档案",
        description="浏览任务原文与场景脉络",
    ),
)
TEAM_RECOMMENDATION = AgentDescriptor(
    intent="team_recommendation",
    title="智能配队",
    description="基于角色池、体系引擎与真实使用数据的官方角色配队推荐",
    keywords=("配队", "队伍", "组队", "一起搭配", "一起上场"),
    action=AgentActionSpec(
        url="/teams",
        title="去配队页调整",
        description="在配队页调整核心角色、生存位与偏好后重新生成",
        prefill_character=True,
    ),
)
CHARACTER_BUILD = AgentDescriptor(
    intent="character_build",
    title="养成规划",
    description="角色培养顺序、光锥遗器搭配与技能升级优先级",
    keywords=(
        "养成",
        "培养",
        "怎么养",
        "要养",
        "想养",
        "练度",
        "技能优先",
        "遗器搭配",
    ),
    action=AgentActionSpec(
        url="/planning",
        title="去养成规划",
        description="把养成分解为可勾选的周计划",
    ),
)
MATERIAL_QUERY = AgentDescriptor(
    intent="material_query",
    title="材料查询",
    description="养成材料的获取途径、掉落关卡与开放时间",
    keywords=("材料", "掉落", "开放时间", "哪里刷"),
    action=AgentActionSpec(
        url="/items",
        title="去物品智库",
        description="查看材料档案与堆叠上限",
    ),
)
ACTIVITY_STRATEGY = AgentDescriptor(
    intent="activity_strategy",
    title="活动攻略",
    description="当前版本的限时活动机制、玩法与注意事项",
    keywords=(
        "版本活动",
        "活动攻略",
        "活动怎么玩",
        "位面分裂",
        "圣杯战争",
        "巡星之礼",
        "反贪",
    ),
    action=AgentActionSpec(
        url="/activities",
        title="去活动攻略库",
        description="浏览活动机制与玩家攻略",
    ),
)
MEMORY = AgentDescriptor(
    intent="memory",
    title="长期记忆",
    description="记录或管理用户的长期偏好",
    keywords=("记住", "长期记忆", "回答偏好", "资源优先"),
    action=AgentActionSpec(
        url="/profile/memories",
        title="管理长期记忆",
        description="查看与删除已确认的记忆条目",
    ),
)
WEEKLY_PLAN = AgentDescriptor(
    intent="weekly_plan",
    title="每周规划",
    description="基于养成方案安排本周体力分配",
    keywords=("本周", "每周", "周计划", "体力规划"),
    action=AgentActionSpec(
        url="/weekly-plan",
        title="去每周规划",
        description="查看与调整本周体力安排",
    ),
)
CUSTOM_CHARACTER_CREATION = AgentDescriptor(
    intent="custom_character_creation",
    title="角色创作",
    description="原创角色的四阶段创作流程引导",
    keywords=("自定义角色", "原创角色", "创作角色", "设计角色"),
    action=AgentActionSpec(
        url="/creator",
        title="去创作工坊",
        description="在工坊中逐阶段完成创作",
    ),
)
CUSTOM_TEAM_RECOMMENDATION = AgentDescriptor(
    intent="custom_team_recommendation",
    title="原创角色配队",
    description="基于已确认草稿的原创角色配队分析",
    keywords=("自定义角色配队", "原创角色配队", "给我的角色配队"),
    action=AgentActionSpec(
        url="/creator",
        title="去创作工坊",
        description="配队分析在工坊内基于最新草稿生成",
    ),
)
CUSTOM_CHARACTER_REVIEW = AgentDescriptor(
    intent="custom_character_review",
    title="创作自查",
    description="对玩家的原创角色草稿运行提交前自查，输出完整度、乱编造与一致性报告",
    keywords=(
        "审核我的角色",
        "审查我的角色",
        "自查我的角色",
        "帮我审",
        "审一下我的角色",
        "检查我的角色",
        "审我的角色",
    ),
    action=AgentActionSpec(
        url="/creator",
        title="去创作工坊修改",
        description="按审核报告回到对应创作阶段修改",
    ),
)


def default_keyword_routes() -> tuple[tuple[tuple[str, ...], str], ...]:
    """确定性兜底路由的全局匹配顺序：具体意图在前，宽泛意图在后。"""
    ordered = (
        CONVERSATION_RECALL,
        CONVERSATION,
        CUSTOM_TEAM_RECOMMENDATION,
        CUSTOM_CHARACTER_CREATION,
        CUSTOM_CHARACTER_REVIEW,
        TEAM_RECOMMENDATION,
        ACTIVITY_STRATEGY,
        MATERIAL_QUERY,
        CHARACTER_BUILD,
        STRUCTURED_LOOKUP,
        STORY_ANALYSIS,
        WEEKLY_PLAN,
        MEMORY,
        KNOWLEDGE_QA,
    )
    return tuple(
        (descriptor.keywords, descriptor.intent)
        for descriptor in ordered
        if descriptor.keywords
    )


def build_agent_registry(
    agents_by_intent: dict[str, BaseAgent],
) -> "AgentRegistry":
    """把已实例化的 Agent 与描述符装配成注册表。"""
    descriptors: dict[str, AgentDescriptor] = {
        descriptor.intent: descriptor
        for descriptor in (
            CONVERSATION,
            CONVERSATION_RECALL,
            KNOWLEDGE_QA,
            STRUCTURED_LOOKUP,
            STORY_ANALYSIS,
            TEAM_RECOMMENDATION,
            CHARACTER_BUILD,
            MATERIAL_QUERY,
            ACTIVITY_STRATEGY,
            MEMORY,
            WEEKLY_PLAN,
            CUSTOM_CHARACTER_CREATION,
            CUSTOM_TEAM_RECOMMENDATION,
            CUSTOM_CHARACTER_REVIEW,
        )
    }
    return AgentRegistry(
        {
            intent: (descriptor, agent)
            for intent, agent in agents_by_intent.items()
            if (descriptor := descriptors.get(intent)) is not None
        },
        fallback_descriptor=KNOWLEDGE_QA,
    )


class AgentRegistry:
    """意图到 Agent 的唯一映射，附带规划清单与兜底路由。"""

    def __init__(
        self,
        entries: dict[str, tuple[AgentDescriptor, BaseAgent]],
        fallback_descriptor: AgentDescriptor,
    ) -> None:
        self._entries = entries
        self._fallback = fallback_descriptor

    def agent_for_intent(self, intent: str | None) -> BaseAgent:
        if intent and intent in self._entries:
            return self._entries[intent][1]
        return self._entries[self._fallback.intent][1]

    def register(self, intent: str, agent: BaseAgent) -> None:
        """替换或补充一个意图的 Agent（测试与运行时扩展共用入口）。

        描述符缺失时继承兜底意图的描述符，保证规划清单始终完整。
        """
        descriptor = self._entries.get(intent, (self._fallback, agent))[0]
        self._entries[intent] = (descriptor, agent)

    def descriptor_for_intent(self, intent: str | None) -> AgentDescriptor:
        if intent and intent in self._entries:
            return self._entries[intent][0]
        return self._fallback

    @property
    def fallback_intent(self) -> str:
        return self._fallback.intent

    def intents(self) -> list[str]:
        return list(self._entries)

    def planner_manifest(self) -> list[dict[str, str]]:
        """供主 Agent 编排规划使用的精简能力清单。"""
        return [
            {
                "intent": intent,
                "title": descriptor.title,
                "description": descriptor.description,
            }
            for intent, (descriptor, _) in self._entries.items()
        ]

    def keyword_routes(self) -> tuple[tuple[tuple[str, ...], str], ...]:
        """确定性兜底路由：按声明顺序匹配关键词。"""
        return tuple(
            (descriptor.keywords, intent)
            for intent, (descriptor, _) in self._entries.items()
            if descriptor.keywords
        )
