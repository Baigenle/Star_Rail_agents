# 系统架构与流程图

本文档对应毕业设计“系统设计与实现”章节，可直接作为论文图表底稿。

## 1. 总体架构

```mermaid
flowchart LR
    U["玩家 / 管理员"] --> V["Vue 3 + TypeScript"]
    V --> API["FastAPI REST API"]
    API --> AUTH["认证与用户域"]
    API --> H["黑塔主 Agent"]
    API --> CAT["官方知识库服务"]
    H --> R["Router Agent"]
    R --> LF["DeepSeek Flash<br/>意图与指代消解"]
    R --> A1["RAG Agent"]
    R --> A2["配队 Agent"]
    R --> A3["养成 Agent"]
    R --> A4["材料 Agent"]
    R --> A5["攻略 Agent"]
    R --> A6["Memory Agent"]
    R --> A7["每周规划 Agent"]
    A1 --> M["Milvus"]
    A1 --> B["BGE-M3 + Reranker"]
    A1 --> LP["DeepSeek Pro / Qwen<br/>有据回答生成"]
    AUTH --> P["PostgreSQL"]
    CAT --> D["JSON / Markdown / 图片资源"]
    A2 --> P
    A3 --> P
    A6 --> P
    A7 --> P
```

## 2. Multi-Agent 调用

```mermaid
sequenceDiagram
    actor User as 用户
    participant UI as Vue 前端
    participant H as 黑塔主 Agent
    participant R as Router Agent
    participant A as 专业 Agent
    participant DB as PostgreSQL / Milvus
    User->>UI: 输入问题
    UI->>H: message + conversation_id
    H->>R: 当前消息、最近12条消息、角色池、已确认记忆
    R->>R: Flash 语义意图、指代消解、独立问题改写
    R->>A: 按意图选择专业 Agent；失败时规则回退
    A->>DB: 结构化查询或向量检索
    DB-->>A: 证据与用户快照
    A-->>H: Claim + Citation + Validation + Filtering
    H-->>UI: 保留证据的黑塔风格回答
    UI-->>User: 回答、引用、可展开调用过程
```

Router 当前注册 `conversation`、`conversation_recall`、`knowledge_qa`、`team_recommendation`、`character_build`、`strategy_summary`、`material_query`、`memory`、`weekly_plan`、自定义角色创作与配队。剧情意图暂由 RAG Agent 安全降级。

系统采用混合式 Multi-Agent：Router、RAG 与自定义角色抽取使用大模型完成语义决策或有据生成；配队、养成、材料和每周规划 Agent 使用确定性业务工具计算并验证结果。确定性 Agent 不依赖生成式模型猜测数值，因此响应更快，但仍具备独立目标、上下文、工具调用、校验和统一输出协议。

## 3. RAG 流程

```mermaid
flowchart TD
    Q["语义补全后的独立问题"] --> E["BGE-M3 Query Embedding"]
    E --> V["Milvus Top-100 候选"]
    V --> K["实体标题与关键词加权"]
    K --> RR["BGE Reranker Top-30"]
    RR --> C["生成后端 Citation ID"]
    C --> L["DeepSeek Pro 仅基于证据生成候选主张"]
    L --> VA["引用 ID、置信度、重复主张校验"]
    VA --> F["Filtering 移除无引用或低置信内容"]
    F --> H["黑塔主 Agent 只改表达，不改证据"]
```

## 4. 核心 ER 图

```mermaid
erDiagram
    USER ||--o{ USER_CHARACTER : owns
    USER ||--o{ USER_CHARACTER_PROGRESS : records
    USER ||--o{ USER_MEMORY : confirms
    USER ||--o{ USER_TEAM : saves
    USER_TEAM ||--|{ USER_TEAM_MEMBER : contains
    USER ||--o{ CONVERSATION : starts
    CONVERSATION ||--|{ CHAT_MESSAGE : contains
    USER ||--o{ PROGRESSION_PLAN : saves
    USER ||--o{ WEEKLY_PLAN : generates
    USER ||--o{ CUSTOM_CHARACTER : authors
    CUSTOM_CHARACTER ||--|{ CUSTOM_CHARACTER_VERSION : versions
    CUSTOM_CHARACTER ||--o{ CUSTOM_CHARACTER_SESSION : creates
    CUSTOM_CHARACTER_SESSION ||--|{ CUSTOM_CHARACTER_MESSAGE : contains
```

## 5. 数据边界

- 官方角色、光锥、遗器、物品与怪物进入官方目录和 Milvus collection。
- 用户角色池、练度、队伍、养成方案、会话和记忆进入 PostgreSQL，并按 `user_id` 隔离。
- 玩家自定义角色使用独立版本表与社区接口，不写入官方 RAG。
- LLM 输出不能直接修改记忆、队伍、养成方案或公开版本；写操作必须由用户或管理员显式触发。
