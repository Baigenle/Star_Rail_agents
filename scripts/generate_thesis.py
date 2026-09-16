"""张家界学院本科毕业设计报告生成器（第一版）。

以官方样例文档为底（保留全部样式与页面设置），清除示例内容后
按本项目真实实现填充正文。封面个人信息留占位由学生本人填写。
"""

from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

BASE = Path(__file__).resolve().parents[1]
SAMPLE = Path(
    r"C:/Users/擺给Savior/OneDrive/Desktop/毕设/"
    r"张家界学院本科毕业设计模板—项目开发方向(样例).docx"
)
OUTPUT = Path(
    r"C:/Users/擺给Savior/OneDrive/Desktop/毕设/"
    r"毕业设计报告_第一版.docx"
)

TITLE_CN = "基于多智能体与RAG的星穹铁道智能助手平台设计与实现"
TITLE_EN = (
    "Design and Implementation of a Honkai: Star Rail Intelligent "
    "Assistant Platform Based on Multi-Agent and RAG"
)
KEYWORDS_CN = "多智能体；检索增强生成；机制知识评分；游戏智能助手；知识溯源"
KEYWORDS_EN = (
    "Multi-Agent; Retrieval-Augmented Generation; Mechanism-Knowledge "
    "Scoring; Game Assistant; Knowledge Traceability"
)

ABSTRACT_CN = [
    "通用大语言模型在游戏垂直领域存在知识过时与事实幻觉问题：模型无法回答版本更新后的角色机制，"
    "生成的游戏攻略缺乏可验证依据，难以满足玩家对准确性与时效性的要求。本设计面向《崩坏：星穹铁道》"
    "玩家群体，实现了一个基于多智能体协作与检索增强生成（RAG）的游戏智能助手平台。",
    "系统采用前后端分离架构：前端基于 Vue 3 与 TypeScript 构建单页应用；后端基于 FastAPI 实现多智能体"
    "编排，通过 Agent 注册表统一管理十四个专业智能体，分别负责知识问答、配队推荐、养成规划、材料查询、"
    "剧情解析、活动攻略、每周规划、创作自查等职责。知识层采用 Milvus 向量数据库与 BGE-M3 嵌入模型实现"
    "检索增强生成，回答内容附带引用编号并可溯源至本地知识文档。针对游戏攻略场景，本设计提出机制知识"
    "驱动的配队评分方法：为九十五名角色构建机制画像，以需求满足判定、引擎参与度与体系增益价值适配三个"
    "维度计算知识分并主导推荐排序，同时引入官方配队整队注入与校准测试保证推荐质量底线。",
    "系统经一百三十九个自动化测试用例与三十七项接口穷举探针、端到端业务旅程、多页面视觉审查验证，"
    "各功能模块均可用且在模型服务异常时具备确定性降级能力。与直接询问通用大模型相比，本平台的回答"
    "具备可溯源、知识可人工修订、能力可自我说明三点优势。",
]
ABSTRACT_POINTS_CN = [
    "1.分析了通用大模型在游戏垂直领域知识过时与事实幻觉问题的成因，提出以本地机制知识库结合"
    "检索增强生成的解决思路，并完成多智能体平台的需求分析与总体方案设计；",
    "2.设计并实现了注册表式多智能体编排架构，涵盖意图理解、复合任务拆解、确定性兜底与全程可审计的"
    "执行轨迹；",
    "3.提出并实现了机制知识驱动的配队评分模型与校准测试方法，使配队推荐从统计拼凑升级为"
    "可解释、可校准、可人工修订的知识推理过程；",
    "4.实现了玩家角色创作、自助审核与社区流通的完整闭环，并完成系统测试与部署验证。",
]
ABSTRACT_EN = [
    "General large language models suffer from outdated knowledge and factual hallucination in the "
    "gaming vertical: they cannot answer questions about character mechanics changed by version updates, "
    "and the guides they generate lack verifiable evidence. This project designs and implements a game "
    "assistant platform for Honkai: Star Rail players based on multi-agent collaboration and "
    "Retrieval-Augmented Generation (RAG).",
    "The system adopts a front-end and back-end separated architecture. The front end is a single-page "
    "application built with Vue 3 and TypeScript. The back end orchestrates fourteen professional agents "
    "registered in an Agent Registry through FastAPI, covering knowledge question answering, team "
    "recommendation, character progression planning, material query, story analysis, event strategy, "
    "weekly planning, creation self-review and other duties. The knowledge layer combines the Milvus "
    "vector database with the BGE-M3 embedding model to implement RAG, and every answer carries citation "
    "identifiers traceable to local knowledge documents. For the game guide scenario, this project "
    "proposes a mechanism-knowledge-driven team scoring method: mechanism profiles are built for ninety-five "
    "characters, and a knowledge score computed from requirement satisfaction, engine participation and "
    "archetype buff-value adaptation dominates the recommendation ranking, with official stored teams "
    "injected as explicit candidates and a calibration test suite guarding the quality baseline.",
    "The system is verified by one hundred and thirty-nine automated test cases, a thirty-seven-case "
    "API probe, end-to-end business journeys and multi-page visual inspection. All modules remain usable "
    "with deterministic degradation when the model service is unavailable. Compared with directly asking "
    "a general LLM, the platform is traceable, manually revisable and self-describable.",
]
ABSTRACT_POINTS_EN = [
    "1. Analyzes the causes of outdated knowledge and factual hallucination of general LLMs in the gaming "
    "vertical, and proposes a local mechanism-knowledge base combined with RAG, completing the "
    "requirement analysis and overall design of the multi-agent platform;",
    "2. Designs and implements a registry-style multi-agent orchestration architecture covering intent "
    "understanding, compound task decomposition, deterministic fallback and fully auditable execution "
    "traces;",
    "3. Proposes and implements a mechanism-knowledge-driven team scoring model with a calibration test "
    "suite, upgrading team recommendation from statistical assembly to an explainable, calibratable and "
    "manually revisable knowledge reasoning process;",
    "4. Implements the complete loop of player character creation, self-review and community "
    "circulation, and completes system testing and deployment verification.",
]


def clear_body(doc: Document) -> None:
    body = doc.element.body
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)


def add_toc_field(doc: Document) -> None:
    paragraph = doc.add_paragraph(style="toc 1")
    run = paragraph.add_run()
    fld_char_begin = OxmlElement("w:fldChar")
    fld_char_begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = 'TOC \\o "1-3" \\h \\z \\u'
    fld_char_separate = OxmlElement("w:fldChar")
    fld_char_separate.set(qn("w:fldCharType"), "separate")
    placeholder = OxmlElement("w:t")
    placeholder.text = "（目录将在 Word 中按 Ctrl+A 后 F9 更新）"
    fld_char_end = OxmlElement("w:fldChar")
    fld_char_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char_begin)
    run._r.append(instruction)
    run._r.append(fld_char_separate)
    run._r.append(placeholder)
    run._r.append(fld_char_end)


def build() -> Path:
    doc = Document(str(SAMPLE))
    clear_body(doc)

    # ── 封面 ──
    doc.add_paragraph("毕业论文（设计）", style="封面")
    doc.add_paragraph("", style="封面")
    doc.add_paragraph(TITLE_CN, style="封面")
    doc.add_paragraph("", style="封面")
    doc.add_paragraph("学    院：______________________", style="封面")
    doc.add_paragraph("专    业：______________________", style="封面")
    doc.add_paragraph("学    号：______________________", style="封面")
    doc.add_paragraph("学生姓名：______________________", style="封面")
    doc.add_paragraph("指导教师：______________________", style="封面")
    doc.add_paragraph("完成日期：______________________", style="封面")
    doc.add_page_break()

    # ── 中文摘要 ──
    doc.add_paragraph(TITLE_CN, style="摘要标题")
    doc.add_paragraph("摘  要", style="摘 要 Abstract")
    for paragraph in ABSTRACT_CN:
        doc.add_paragraph(paragraph, style="Normal")
    for point in ABSTRACT_POINTS_CN:
        doc.add_paragraph(point, style="Normal")
    doc.add_paragraph(f"关键词：{KEYWORDS_CN}", style="Normal")

    # ── 英文摘要 ──
    doc.add_paragraph(TITLE_EN, style="摘要标题")
    doc.add_paragraph("Abstract", style="摘 要 Abstract")
    for paragraph in ABSTRACT_EN:
        doc.add_paragraph(paragraph, style="Normal")
    for point in ABSTRACT_POINTS_EN:
        doc.add_paragraph(point, style="Normal")
    doc.add_paragraph(f"Keywords: {KEYWORDS_EN}", style="Normal")
    doc.add_page_break()

    # ── 目录 ──
    doc.add_paragraph("目  录", style="目录 题目")
    add_toc_field(doc)
    doc.add_page_break()

    # ── 第1章 前言 ──
    doc.add_paragraph("第1章 前 言", style="Heading 1")
    doc.add_paragraph("1.1 选题背景和意义", style="Heading 2")
    doc.add_paragraph(
        "《崩坏：星穹铁道》是一款持续更新的回合制角色扮演游戏，角色、装备、剧情与活动内容"
        "随版本快速迭代。玩家在游戏过程中高频产生三类需求：查询类需求（角色机制、材料掉落、"
        "剧情梳理）、决策类需求（配队推荐、养成优先级、体力安排）与创作类需求（原创角色设计"
        "与分享）。传统攻略社区依赖人工撰写与检索，信息分散且更新滞后；直接向通用大语言模型"
        "提问则面临两个根本问题：其一，模型训练数据截止后上线的版本内容完全不可知；其二，"
        "模型会以流畅的语言编造看似合理的游戏事实，玩家难以分辨真伪。",
        style="Normal",
    )
    doc.add_paragraph(
        "检索增强生成（RAG）技术通过先检索后生成的方式为模型提供外部知识，是缓解幻觉的有效"
        "手段；多智能体架构则通过职责分离让不同智能体各自专注一个领域，并以统一的输出契约"
        "保证结果可校验。本设计将二者结合，面向星穹铁道构建了一个知识可溯源、评分可解释、"
        "能力可自述的游戏智能助手平台。平台对玩家而言可以降低信息获取成本、提供个性化的"
        "配队与养成决策支持；对开发者而言，其“机制知识库+校准测试”的知识治理模式可迁移到"
        "其他需要专家经验判断的快速变化领域，具有方法层面的参考价值。",
        style="Normal",
    )
    doc.add_paragraph("1.2 国内外研究现状", style="Heading 2")
    doc.add_paragraph(
        "在检索增强生成方向，Lewis 等人于 2020 年提出 RAG 框架，将参数化模型记忆与非参数化"
        "向量检索结合，显著提升了知识密集型任务的事实准确性，此后 RAG 成为知识问答类应用的"
        "主流范式。向量数据库方面，Milvus 提供了面向海量向量的高性能检索能力，中文嵌入方面"
        "以 BGE 系列模型为代表的中文语义向量在多类评测中表现优异，二者构成了本地知识检索的"
        "成熟技术栈。",
        style="Normal",
    )
    doc.add_paragraph(
        "在多智能体方向，AutoGen、Generative Agents 等工作证明了多个基于大模型的智能体通过"
        "对话与分工可以完成单一智能体难以处理的复杂任务；游戏领域则有以自然语言驱动角色行为"
        "的生成式智能体实验。在游戏助手产品方向，国内外已有攻略站点与大模型问答产品，但普遍"
        "存在三点不足：一是答案无引用来源，玩家无法验证；二是知识更新依赖平台运营者，个人"
        "开发者难以维护；三是缺乏针对具体游戏机制的专业决策能力（如回合制游戏的配队与体力"
        "规划）。本设计针对上述不足，以本地化知识库、引用溯源与机制知识评分作为核心切入点。",
        style="Normal",
    )
    doc.add_paragraph("1.3 项目目标和范围", style="Heading 2")
    doc.add_paragraph(
        "项目目标：构建一个面向星穹铁道玩家的多智能体智能助手平台，实现八大功能模块——"
        "AI 智能问答、智能配队推荐、角色养成规划、游戏攻略智能总结、游戏材料查询、剧情解析"
        "与世界观问答、用户记忆管理、每日任务规划，并在此基础上扩展玩家角色创作、自助审核"
        "与社区流通的完整闭环。",
        style="Normal",
    )
    doc.add_paragraph(
        "项目范围：平台覆盖游戏内知识的检索、问答、决策与创作辅助，不涉及游戏客户端的修改"
        "或自动化操作；知识数据仅用于个人学习研究。平台已实现全部八大功能模块，并在配队推荐"
        "上超额实现了机制知识驱动的评分体系。",
        style="Normal",
    )

    # ── 第2章 技术与原理 ──
    doc.add_paragraph("第2章 技术与原理", style="Heading 1")
    doc.add_paragraph("2.1 Vue 3 与 TypeScript", style="Heading 2")
    doc.add_paragraph(
        "前端采用 Vue 3 组合式 API 与 TypeScript 构建，配合 Pinia 状态管理与 Vue Router "
        "实现单页应用。组合式 API 使异步任务（如后台问答轮询）的状态管理更简洁；TypeScript "
        "的类型定义与后端 Pydantic 模型保持字段级一致，降低了前后端协作的联调成本。",
        style="Normal",
    )
    doc.add_paragraph("2.2 FastAPI 与 SQLAlchemy", style="Heading 2")
    doc.add_paragraph(
        "后端采用 FastAPI 框架，利用 Pydantic 模型完成请求校验与响应序列化，自动生成 OpenAPI "
        "接口文档；数据访问层使用 SQLAlchemy 2.0，通过 Alembic 管理数据库版本演进。FastAPI 的"
        "异步特性支撑了后台聊天任务、事件流推送等并发场景。",
        style="Normal",
    )
    doc.add_paragraph("2.3 大语言模型与 LangChain", style="Heading 2")
    doc.add_paragraph(
        "平台通过 LangChain 的 ChatOpenAI 兼容接口接入大语言模型，支持智谱 GLM、DeepSeek、"
        "通义千问等多供应商切换。针对不同工作负载采用模型分档策略：意图理解使用高阶思考模型，"
        "推理与终审使用旗舰模型，字段抽取等轻量任务使用轻量快速模型，以在质量与成本之间取得"
        "平衡；任一档位不可用时自动降级至下一档，保证链路永不为空。",
        style="Normal",
    )
    doc.add_paragraph("2.4 Milvus、BGE-M3 与检索增强生成", style="Heading 2")
    doc.add_paragraph(
        "检索增强生成（RAG）的核心思想是将外部知识向量化入库，回答前先检索相关知识片段，"
        "再交由模型基于证据生成回答。本平台使用 BGE-M3 模型生成中文语义向量，Milvus 存储"
        "并检索知识片段，BGE Reranker 对候选证据重排，最终以“主张—引用—校验—过滤”的输出"
        "契约保证回答可溯源：无引用或低置信度的主张在输出前被过滤。",
        style="Normal",
    )
    doc.add_paragraph("2.5 多智能体架构与注册表", style="Heading 2")
    doc.add_paragraph(
        "多智能体架构将复杂任务按领域拆分给多个具备独立职责的智能体。本平台的注册表"
        "（AgentRegistry）要求每个专业智能体在唯一入口声明其服务的意图、能力描述、页面动作"
        "与兜底关键词，新增智能体只需注册一处；主智能体据此进行调度、生成页面动作并向用户"
        "自述系统能力，保证自述与实现一致。",
        style="Normal",
    )
    doc.add_paragraph("2.6 机制知识驱动评分原理", style="Heading 2")
    doc.add_paragraph(
        "回合制游戏的配队决策本质上是机制匹配问题：核心角色的机制需求（如生命值变动充能、"
        "击破转化、能量循环）需要由队友的机制供给满足，不同体系对增益类型的价值评价也不同"
        "（如持续伤害队伍不吃暴击增益）。本平台将上述领域知识形式化为“机制画像+受控词表+"
        "满足路径映射+体系增益价值表”，以规则引擎计算知识分并主导推荐排序，使配队推荐"
        "可解释、可校准、可人工修订。",
        style="Normal",
    )

    # ── 第3章 系统分析 ──
    doc.add_paragraph("第3章 系统分析", style="Heading 1")
    doc.add_paragraph("3.1 可行性分析", style="Heading 2")
    doc.add_paragraph("3.1.1 经济可行性", style="Heading 3")
    doc.add_paragraph(
        "平台全部采用开源技术栈（Vue、FastAPI、Milvus 社区版、PostgreSQL），无商业授权成本；"
        "大语言模型采用按量计费的国产 API，配合模型分档策略将单次问答成本控制在分级别；本地"
        "嵌入与重排模型运行于消费级显卡，无需额外算力采购。",
        style="Normal",
    )
    doc.add_paragraph("3.1.2 操作可行性", style="Heading 2")
    doc.add_paragraph(
        "用户通过浏览器访问，交互以自然语言对话为主、表单操作为辅，无需学习成本；一键部署"
        "脚本与 Docker Compose 使非开发用户亦可完成环境搭建。",
        style="Normal",
    )
    doc.add_paragraph("3.1.3 技术可行性", style="Heading 2")
    doc.add_paragraph(
        "关键链路均已有工程验证：Milvus+Embedding 的本地知识检索、LangChain 的模型编排、"
        "FastAPI 的异步任务与事件流均为成熟方案；机制知识评分以确定性规则引擎实现，可通过"
        "校准测试持续验证。系统已通过一百三十九个自动化测试用例与多轮端到端验收。",
        style="Normal",
    )
    doc.add_paragraph("3.1.4 运行可行性", style="Heading 2")
    doc.add_paragraph(
        "系统支持 Docker Compose 一键部署与 PyCharm 本地开发两种运行方式；模型服务异常时"
        "具备确定性降级能力，结构化功能（配队、规划、检索、创作审核规则）在无外部模型时"
        "保持可用。",
        style="Normal",
    )
    doc.add_paragraph("3.2 需求分析", style="Heading 2")
    doc.add_paragraph("3.2.1 功能需求", style="Heading 3")
    doc.add_paragraph(
        "平台按八大功能模块组织：AI 智能问答（基于 RAG 的知识检索与引用溯源）、智能配队推荐"
        "（机制知识驱动的队伍生成与解释）、角色养成规划（目标拆解与材料计算）、游戏攻略智能"
        "总结（分玩家阶段的攻略建议）、游戏材料查询（数量、副本与开放时间）、剧情解析与世界"
        "观问答（结合剧情知识库）、用户记忆管理（偏好与上下文个性化）、每日任务规划（体力"
        "安排与活动提醒）。在八大模块之外，平台扩展了玩家角色创作工坊（四阶段引导）、提交前"
        "自助审核（五维度规则检查）与社区流通（审核上架）三个创作侧模块，形成完整闭环。",
        style="Normal",
    )
    doc.add_paragraph("3.2.2 非功能需求", style="Heading 3")
    doc.add_paragraph(
        "可溯源：事实性回答必须携带引用编号并可定位至知识原文；可降级：外部模型异常时确定性"
        "功能保持可用并明确告知用户；可审计：智能体执行过程产生结构化轨迹事件，可回放；"
        "安全性：密码加盐哈希存储、接口鉴权、用户数据按所有者隔离、社区内容经审核后流通；"
        "可维护：知识数据与代码分离，支持人工修订与版本管理。",
        style="Normal",
    )

    # ── 第4章 系统设计 ──
    doc.add_paragraph("第4章 系统设计", style="Heading 1")
    doc.add_paragraph("4.1 系统架构设计", style="Heading 2")
    doc.add_paragraph(
        "系统采用表现层、接入层、编排层、执行层与数据层的分层架构。表现层为 Vue 3 单页应用；"
        "接入层为 FastAPI 路由与静态资源服务；编排层为黑塔主智能体，负责规划轨迹生成、页面动作"
        "生成、回答预算与衍生问题建议；执行层包含通过 AgentRegistry 注册的十四个专业智能体与"
        "确定性服务；数据层包含 PostgreSQL（用户事务数据）、Milvus（向量知识）、本地知识文档"
        "（机制画像、官方配队、剧情文本）与静态资源。",
        style="Normal",
    )
    doc.add_paragraph(
        "编排层与执行层通过统一的 AIResponse 契约通信，契约包含回答正文、主张、引用、校验报告、"
        "过滤报告、查询步骤、页面动作与衍生问题等字段，使任意智能体的结果都可以被一致地呈现、"
        "审计与测试。",
        style="Normal",
    )
    doc.add_paragraph("4.2 主要功能设计", style="Heading 2")
    doc.add_paragraph("4.2.1 智能问答与异步任务设计", style="Heading 3")
    doc.add_paragraph(
        "问答链路设计为“独立问题改写→向量检索→重排→有据生成→校验过滤”流水线，回答中的每个"
        "主张携带引用编号与置信度。为避免长问题阻塞交互，问答同时提供同步与异步任务两种模式："
        "异步任务落库并产生结构化轨迹事件，前端通过轮询与事件流实时呈现智能体执行过程，应用"
        "重启时自动恢复未完成任务。",
        style="Normal",
    )
    doc.add_paragraph("4.2.2 机制知识配队设计", style="Heading 3")
    doc.add_paragraph(
        "配队推荐由三层推断构成：候选生成层按槽位计划对角色池进行六因子排序（定位、机制标签、"
        "官方共现、体系引擎亲和、增益价值适配、属性），十二次轮转保证多样性；知识评分层基于"
        "机制画像逐条判定核心角色硬/软需求的满足度、引擎参与度与增益价值适配，占最终得分"
        "55%；机械模拟层以真实战技点轮转、能量循环与速度协调作为平局裁决，占 15%。官方存储队"
        "以整队形式注入候选并生成体系内等价类变体，首选存储队保证出现在推荐结果中。系统内置"
        "校准测试，要求官方完全体队伍得分必须高于体系外扰动队伍。",
        style="Normal",
    )
    doc.add_paragraph("4.2.3 创作工坊与社区审核设计", style="Heading 3")
    doc.add_paragraph(
        "创作采用四阶段确认流程（基础身份、战斗定位、属性技能、故事星魂），已确认阶段可回退"
        "修改，修改后旧自查结果失效。提交前运行五维自助审核（完整度、内容真实性、内部一致性、"
        "数值合理性、设定合规），其中乱编检测由确定性规则与模型辅助检查共同完成，模型不可用"
        "时自动降级为纯规则审核。作品提交后进入管理员审核，通过后进入社区角色库，审核动作"
        "全程留痕。",
        style="Normal",
    )
    doc.add_paragraph("4.2.4 记忆与个性化设计", style="Heading 3")
    doc.add_paragraph(
        "用户记忆分为两类：功能数据（角色池、队伍、计划）由功能操作直接维护，无需确认；偏好"
        "记忆（玩法倾向、资源优先级、回答偏好）须经用户确认后写入，停用后立即从所有智能体"
        "上下文移除。长对话场景下，超过保留窗口的旧消息自动压缩为渐进式摘要并随会话保存，"
        "摘要作为伪历史注入意图理解，删除会话时一并清除。",
        style="Normal",
    )
    doc.add_paragraph("4.3 数据库设计", style="Heading 2")
    doc.add_paragraph("4.3.1 概念结构设计", style="Heading 3")
    doc.add_paragraph(
        "系统核心实体包括：用户（User）、会话（Conversation）与聊天消息（ChatMessage）、"
        "角色池（UserCharacter）、用户队伍（UserTeam）、养成计划（ProgressionPlan）、每周计划"
        "（WeeklyPlan）、用户记忆（UserMemory）、创作角色（CustomCharacter）及其版本"
        "（CustomCharacterVersion）与创作会话（CustomCharacterSession）、审核动作"
        "（ModerationAction）、后台任务（ChatJob）及任务事件（ChatJobEvent）。用户与其会话、"
        "角色池、队伍、计划、记忆之间为一对多关系；创作角色与版本为一对多关系并由草稿指针"
        "区分当前编辑版本；审核动作记录内容类型与对象标识以支持多类型内容治理。",
        style="Normal",
    )
    doc.add_paragraph("4.3.2 逻辑结构设计", style="Heading 3")
    doc.add_paragraph(
        "数据库通过 Alembic 管理十二个迁移版本。关键约束包括：用户名与邮箱唯一、队伍成员的"
        "（队伍, 位置）唯一、创作角色版本的（角色, 版本号）唯一；外键均设置级联删除以保持"
        "数据一致性。会话表包含摘要文本与摘要边界字段以支持渐进式摘要；创作版本表包含自助"
        "审核结果字段以支撑“修改后审核失效”的业务规则。",
        style="Normal",
    )

    # ── 第5章 系统实现 ──
    doc.add_paragraph("第5章 系统实现", style="Heading 1")
    doc.add_paragraph("5.1 多智能体编排实现", style="Heading 2")
    doc.add_paragraph(
        "编排层以注册表驱动：每个专业智能体在注册表中声明服务意图、能力描述、页面动作与兜底"
        "关键词，主智能体据此完成调度、生成页面动作（如配队页深链与核心角色预填）并向用户"
        "自述系统能力。主智能体在执行前后产生编排轨迹事件，与调度、检索、校验等事件一同在"
        "前端的执行面板中实时呈现，全程可审计。意图理解采用专用高阶模型并设置回退链：主模型"
        "失败后回退至旗舰模型再次解析，仍失败时按确定性关键词规则路由，保证链路永不为空。"
        "复合问题（如“介绍流萤并推荐配队”）由模型拆解为独立子任务并行执行后由复核智能体"
        "合并，拆解失败时按关键词规则确定性兜底。",
        style="Normal",
    )
    doc.add_paragraph("5.2 智能问答实现", style="Heading 2")
    doc.add_paragraph(
        "问答实现遵循“主张—引用—校验—过滤”契约：检索层按意图选择知识类型并执行向量检索与"
        "重排，生成层基于证据组织回答并为每个主张标注引用编号，校验层核对主张能否在证据原文"
        "中定位，过滤层丢弃无引用、低置信与重复的主张。回答按意图类型执行文本预算（剧情、"
        "配队、闲聊各有预算），超限时在句子边界软截断并生成衍生问题建议，前端将衍生问题渲染"
        "为可点击按钮实现“重点回答、按需展开”。",
        style="Normal",
    )
    doc.add_paragraph("5.3 机制知识配队实现", style="Heading 2")
    doc.add_paragraph(
        "实现要点包括四部分：其一，机制画像与受控词表以数据文件形式存储，由脚本从角色技能"
        "文本标注初稿、结合人工修订生成，评分引擎加载失败时优雅降级为通用标签逻辑；其二，"
        "知识分计算硬需求（未满足重罚）、软需求（满足加分）、引擎参与度与增益价值适配四个"
        "维度，与场景分、机械核心分、数据置信度加权得到最终分；其三，官方存储队整队注入为"
        "显式候选并按体系引擎件生成等价类变体，替换时优先选择能补足核心未满足硬需求的候选；"
        "其四，校准测试以“官方完全体必须高于体系外扰动版”为断言守护评分规则。此外，同一"
        "切换单位的多个命途形态（开拓者十形态、三月七双命途）在候选过滤与最终校验双层拦截，"
        "杜绝非法队伍。",
        style="Normal",
    )
    doc.add_paragraph("5.4 创作工坊与自查实现", style="Heading 2")
    doc.add_paragraph(
        "创作会话按阶段保存待确认字段，显式字段直接进入草稿、自然语言输入由抽取模型解析，"
        "抽取失败时引导用户重试而不丢弃内容。五维自查中完整度、一致性与数值规则由确定性规则"
        "引擎执行，语义层面的乱编检测由模型辅助完成，模型不可用时自动降级为纯规则审核并在"
        "报告中注明。草稿修改后旧审核结果自动失效，须重新审核后方可提交，提交与审核状态"
        "由版本状态机驱动。",
        style="Normal",
    )
    doc.add_paragraph("5.5 长上下文与个性化实现", style="Heading 2")
    doc.add_paragraph(
        "长对话采用渐进式摘要：超过保留窗口的旧消息由轻量模型压缩为上下文摘要并随会话持久化，"
        "摘要作为伪历史注入意图理解，任务完成后异步补刷，删除会话时一并清除。个性化方面，"
        "已确认记忆注入主智能体上下文影响回答取向；回答语言层面通过人设风格池轮换与禁用模板"
        "句式降低重复感，同时保留角色人设特色。",
        style="Normal",
    )

    # ── 第6章 测试与部署 ──
    doc.add_paragraph("第6章 测试与部署", style="Heading 1")
    doc.add_paragraph("6.1 系统运行环境", style="Heading 2")
    doc.add_paragraph(
        "开发环境：Windows 10/11、Python 3.12、Node.js 20、Docker Desktop（WSL 2 后端）。"
        "生产部署通过 Docker Compose 编排 PostgreSQL、Milvus、MinIO、etcd、BGE 模型服务、"
        "后端与前端七个容器；本地开发模式下基础设施运行于容器、前后端以热更新进程运行。",
        style="Normal",
    )
    doc.add_paragraph("6.2 系统部署过程", style="Heading 2")
    doc.add_paragraph(
        "部署步骤为：准备环境变量与模型权重 → docker compose up -d --build 启动全部容器"
        "（后端容器自动执行数据库迁移）→ 执行知识入库脚本建立 Milvus 索引 → 通过健康检查"
        "接口验证各服务。数据库结构通过 Alembic 迁移脚本演进，保证开发与部署环境一致。",
        style="Normal",
    )
    doc.add_paragraph("6.3 系统测试", style="Heading 2")
    doc.add_paragraph(
        "测试体系由四部分组成：其一，一百三十九个自动化测试用例，覆盖注册登录、鉴权隔离、"
        "检索问答、配队、养成、每周规划、后台任务、社区审核与全部专业智能体；其二，机制知识"
        "分校准测试，断言官方完全体队伍得分必须高于体系外扰动队伍，作为评分规则的回归考卷；"
        "其三，三十七项接口穷举探针，覆盖认证边界、越权访问、注入文本、并发任务与降级行为，"
        "过程中发现并修复了未完成草稿自查服务端错误与创作角色缺少删除功能两个缺陷；其四，"
        "端到端业务旅程与多页面视觉审查，验证创作上架全链路与多分辨率页面渲染。测试中发现"
        "的缺陷均已修复并回归通过。",
        style="Normal",
    )

    # ── 第7章 总结 ──
    doc.add_paragraph("第7章 总 结", style="Heading 1")
    doc.add_paragraph(
        "本设计完成了一个面向星穹铁道玩家的多智能体智能助手平台，实现了智能问答、机制知识"
        "配队、养成规划、材料查询、剧情解析、活动攻略、记忆管理与每周规划八大功能模块，并"
        "扩展了角色创作、自助审核与社区流通闭环。平台的主要工作与创新点包括：（1）注册表式"
        "多智能体编排，使能力扩展单点化、系统自述与实现一致；（2）机制知识驱动的配队评分"
        "体系，将领域专家经验形式化为可解释的知识分，并以校准测试守护质量底线；（3）可溯源"
        "的问答契约与分层降级设计，兼顾回答可信度与工程健壮性。",
        style="Normal",
    )
    doc.add_paragraph(
        "不足与展望：其一，实战使用率数据的采集管线已注册但尚未回填数据，后续可在版本更新后"
        "接入真实使用率以进一步校准评分；其二，部分新角色与联动角色的机制画像仍待完善，计划"
        "建立版本更新时的画像维护流程；其三，当前知识库仅覆盖星穹铁道一款游戏，机制知识驱动"
        "的方法论可向其他回合制游戏迁移；其四，回答的多模态呈现（配图、表格化对比）与更深层"
        "的多轮任务规划是值得继续探索的方向。",
        style="Normal",
    )

    # ── 参考文献 ──
    doc.add_paragraph("参考文献", style="Heading 1")
    references = [
        "[1] Lewis P, Perez E, Piktus A, et al. Retrieval-Augmented Generation for "
        "Knowledge-Intensive NLP Tasks[C]// Advances in Neural Information Processing "
        "Systems 33. 2020: 9459-9474.",
        "[2] Wang J, Yi X, Guo R, et al. Milvus: A Purpose-Built Vector Data Management "
        "System[C]// Proceedings of the 2021 International Conference on Management of "
        "Data (SIGMOD). 2021: 2614-2627.",
        "[3] Xiao S, Liu Z, Zhang P, et al. C-Pack: Packaged Resources To Advance General "
        "Chinese Embedding[C]// Proceedings of the 46th International ACM SIGIR Conference "
        "on Research and Development in Information Retrieval. 2023: 641-649.",
        "[4] Wu Q, Bansal G, Zhang J, et al. AutoGen: Enabling Next-Gen LLM Applications "
        "via Multi-Agent Conversation[EB/OL]. arXiv:2308.08155, 2023.",
        "[5] Park J S, O'Brien J, Cai C J, et al. Generative Agents: Interactive "
        "Simulacra of Human Behavior[C]// Proceedings of the 36th Annual ACM Symposium on "
        "User Interface Software and Technology (UIST). 2023.",
        "[6] Vaswani A, Shazeer N, Parmar N, et al. Attention Is All You Need[C]// "
        "Advances in Neural Information Processing Systems 30. 2017: 5998-6008.",
        "[7] Gao Y, Xiong Y, Gao X, et al. Retrieval-Augmented Generation for Large "
        "Language Models: A Survey[EB/OL]. arXiv:2312.10997, 2023.",
        "[8] 米哈游. 崩坏：星穹铁道游戏内文本与角色资料[EB/OL]. 上海: 米哈游网络科技股份有限公司, 2025.",
        "[9] LangChain Documentation[EB/OL]. https://python.langchain.com, 2025.",
        "[10] FastAPI Documentation[EB/OL]. https://fastapi.tiangolo.com, 2025.",
    ]
    for reference in references:
        doc.add_paragraph(reference, style="Normal")

    # ── 致谢 ──
    doc.add_paragraph("致 谢", style="Heading 1")
    doc.add_paragraph(
        "（此处由学生本人填写：感谢指导教师在选题、设计与论文写作过程中的指导，"
        "感谢学院提供的开发环境，以及家人与同学的支持。请结合实际情况撰写。）",
        style="Normal",
    )

    output = Path(str(OUTPUT))
    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output))
    return output


if __name__ == "__main__":
    result = build()
    print(f"已生成: {result}")
