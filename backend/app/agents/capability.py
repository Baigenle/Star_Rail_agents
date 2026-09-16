"""主 Agent 的自我认知：系统能力与功能页面的结构化文档。

闲聊中"你能帮我做什么""XX 功能是干嘛的"类问题的答案来源。
能力清单与功能页面在此维护，回答由它生成——新增功能后在这里补一条，
自我介绍就不会过时（单一事实源，不靠模型记忆）。
"""

from __future__ import annotations

# 功能页面文档：names 用于问题识别，summary/usage/example 用于回答。
FEATURE_DOCS: list[dict[str, str | tuple[str, ...]]] = [
    {
        "names": ("智能配队", "配队推荐", "配队"),
        "url": "/teams",
        "title": "智能配队",
        "summary": "基于机制知识体系（角色需求满足、体系引擎契合、增益价值适配）为你的角色池生成配队，支持混沌回忆/虚构叙事/末日幻影模式加权",
        "usage": "选核心角色和游戏模式，点『生成配队』；可设置偏好/排除角色和必带生存位；结果可保存为常用队伍",
        "example": "流萤怎么配队？混沌回忆用哪套？",
    },
    {
        "names": ("游戏智库", "角色库", "光锥", "遗器", "物品档案"),
        "url": "/characters",
        "title": "游戏智库",
        "summary": "覆盖当前角色图鉴的档案库，含光锥、遗器与物品档案，支持批量标记拥有和喜欢",
        "usage": "搜索或筛选角色，点♡标记喜欢；拥有的角色会自动用于配队和养成规划",
        "example": "帮我看看流萤的档案",
    },
    {
        "names": ("养成规划", "养成", "培养"),
        "url": "/planning",
        "title": "养成规划",
        "summary": "多角色养成目标拆解为可执行的培养计划，材料与优先级自动对齐",
        "usage": "告诉我要养谁，系统拆解材料与步骤并并入每周规划",
        "example": "卡芙卡怎么养成？",
    },
    {
        "names": ("每周规划", "周计划", "体力规划"),
        "url": "/weekly-plan",
        "title": "每周规划",
        "summary": "按体力上限和养成计划自动安排本周每天的刷取安排",
        "usage": "在页面查看/勾选每日安排；也可以在对话里让我直接排",
        "example": "本周体力怎么安排？",
    },
    {
        "names": ("剧情档案", "剧情", "故事档案"),
        "url": "/stories",
        "title": "剧情档案",
        "summary": "任务与场景级剧情原文，按版本浏览；分析由剧情 Agent 结合档案回答",
        "usage": "浏览任务剧情；对话里问角色故事/关系会引用这些档案并给出引用编号",
        "example": "流萤的剧情是什么？她和银狼什么关系？",
    },
    {
        "names": ("活动攻略", "活动", "版本活动"),
        "url": "/activities",
        "title": "活动与攻略",
        "summary": "当前版本活动的机制解析与攻略库",
        "usage": "浏览活动详情；对话里问活动玩法会由活动 Agent 结合攻略回答",
        "example": "这个版本活动怎么玩？",
    },
    {
        "names": ("角色创作工坊", "创作工坊", "创作角色", "原创角色"),
        "url": "/creator",
        "title": "角色创作工坊",
        "summary": "四阶段引导创作原创角色：身份→定位→数值技能→故事，带提交前自查审核",
        "usage": "完成四阶段后运行『玩家自助审核』，通过后可提交社区审核；在对话里说『帮我审一下我的角色』也能触发自查",
        "example": "帮我审一下我的角色",
    },
    {
        "names": ("社区角色库", "社区", "玩家创作"),
        "url": "/community/characters",
        "title": "社区角色库",
        "summary": "经审核的玩家原创角色档案，与官方知识完全隔离",
        "usage": "浏览社区作品；你也可以在工坊创作并提交自己的角色",
        "example": "看看别人创作了什么角色",
    },
    {
        "names": ("长期记忆", "记忆"),
        "url": "/profile/memories",
        "title": "长期记忆",
        "summary": "你确认过的偏好（喜欢的角色、回答偏好等），影响后续回答",
        "usage": "对话里说『记住我喜欢XX』即可写入；在页面可查看和删除",
        "example": "记住我喜欢玩辅助",
    },
]

# 自我认知问法：功能名 + 元问题模式 → 识别为能力询问而非功能使用。
META_QUESTION_PATTERNS = (
    "是干嘛",
    "干什么用",
    "有什么用",
    "怎么用",
    "功能是什么",
    "是什么功能",
    "能做什么",
    "有用吗",
    "好用吗",
    "怎么玩",
    "介绍一下这",
)

# 泛化自我认知问法：不点名功能，问整个系统能做什么。
GENERAL_CAPABILITY_PATTERNS = (
    "你能做什么",
    "你可以做什么",
    "能帮我做什么",
    "有什么功能",
    "有哪些功能",
    "你都会什么",
    "能干什么",
    "介绍一下你自己",
    "你会什么",
)


def find_feature(message: str) -> dict | None:
    """识别消息中点名的功能页面；未命中返回 None。"""
    for doc in FEATURE_DOCS:
        if any(name in message for name in doc["names"]):
            return doc
    return None


def is_general_capability_question(message: str) -> bool:
    return any(pattern in message for pattern in GENERAL_CAPABILITY_PATTERNS)


def is_capability_question(message: str) -> bool:
    """功能询问识别：点名功能 + 元问法，或泛化能力询问。"""
    if is_general_capability_question(message):
        return True
    if find_feature(message) is not None and any(
        pattern in message for pattern in META_QUESTION_PATTERNS
    ):
        return True
    return False


def overview_answer() -> str:
    """泛化能力询问的回答：逐条列出系统能力。"""
    lines = [
        "这套列车智库里，本天才手下有十几个专业 Agent，能帮你做这些事：",
        "",
    ]
    for doc in FEATURE_DOCS:
        lines.append(f"- **{doc['title']}**：{doc['summary']}")
    lines.append("")
    lines.append(
        "涉及游戏事实的回答我都会先检索并给出引用编号，不瞎编。"
        "直接说需求就行，比如：「流萤怎么配队」「卡芙卡怎么养成」。"
    )
    return "\n".join(lines)


def feature_answer(doc: dict) -> str:
    """点名功能询问的回答：摘要+用法+示例。"""
    return (
        f"【{doc['title']}】{doc['summary']}\n\n"
        f"用法：{doc['usage']}\n"
        f"直接问我也可以，比如：「{doc['example']}」"
    )
