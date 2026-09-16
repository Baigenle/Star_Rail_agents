# 《主 Agent 重构方案（Cyrene 迁移）》可行性评审与部署分析

> 评审对象：`D:\Tools\Cyrene\Cyrene-Agent-master\main-agent-spec.md`（下称"方案"）
> 评审基准：本仓库工作区现状（含**未提交**的 `ReactMainAgent` 重构），2026-09-05
>
> **结论先行：方案总体可行。** 架构方向（工具循环 + 分层记忆 + 人格文件 + 事件流）与本仓库正在进行的主 Agent 重构是同一条路线，不是推倒重来。但方案有 **7 处必须按本仓库现实修订**后再执行，其中 3 处属于"照原文执行会直接出问题"：存储选型（SQLite→应沿用 PostgreSQL）、SSE 协议（直连 SSE→应沿用现有 job 事件通道）、单轮超时（60s→须分档，实测思考模型单步 1-2 分钟）。

---

## 1. 现状盘点（对应方案第 1 节清单）

| # | 盘点项 | 现状答案 |
|---|---|---|
| 1 | 聊天入口 | `backend/app/api/v1/routes/chat.py`：`POST /api/v1/chat/messages`（同步全量返回）+ `POST /api/v1/chat/jobs`（后台任务）+ `GET /api/v1/chat/jobs/{id}/events`（SSE，读库轮询 250ms） |
| 2 | 主 agent 调子 agent 方式 | **进程内函数直调**。新主 Agent（未提交）`ReactMainAgent` 以 `ToolSpec.handler(args, ctx)` 直调 5 个工具；旧管线 `HertaMainAgent + RouterAgent` 按注册表（`registry.py`，14 个 intent）分发。全部子 agent：rag、story_analysis、character_build、material_query、team_recommendation、activity_strategy、memory、weekly_planning、player_review、conversation、capability、custom_character×3、answer_review。除配队（思考模型，可到分钟级）外其余为秒级 |
| 3 | 模型调用 | LangChain 0.3.13 + langchain-openai 0.2.14，`app/llm/providers.py` 统一封装 OpenAI 兼容端点（zhipu/deepseek/qwen/mock），按 workload 分档：fast/reasoning/intent/deep（deep=智谱开思考，timeout 240s）。当前 `.env`：`DEFAULT_LLM_PROVIDER=zhipu`，flash=glm-4.5-air、pro=glm-4.6v、intent=glm-4.7 |
| 4 | 会话历史与流式 | PostgreSQL（SQLAlchemy 2.0 同步 + Alembic），`conversations/chat_messages`。流式为 **job 事件 SSE**：事件落库 `chat_job_events`，SSE 端点轮询推流，支持 Last-Event-ID 断线续传；正文流是"答完再 48 字切片"的 `answer.delta`，**非真 token 流**。前端 fetch+getReader 消费（`frontend/src/services/api.ts`） |
| 5 | 已有 prompt/人格 | `backend/app/prompts/herta_style_persona.md`（黑塔人格，文件化已有雏形）+ `response_protocol.md`；`herta_main_agent.py` 内有人格开场/收尾硬编码；`react_main_agent.py` 内 SYSTEM_PROMPT 硬编码 |
| 6 | 现有数据库 | PostgreSQL 16.6（docker-compose），psycopg 3；无向量库之外的第二数据库。记忆为 `user_memories` 平表（**仅用户确认后写入**，`MemoryService` 只产候选建议） |

另有两项方案未问但关键的事实：

- **仓库里已存在"半成品 Phase 1"**（未提交）：`react_main_agent.py`（662 行）+ `react_tools.py`（286 行）+ `dependencies.py` 装配改造，实现了手写循环 + 工具注册 + 引用编号 + 澄清追问 + 收底兜底——但是 **JSON-ReAct 协议**，不是方案要求的原生 Function Calling。
- **新增主 Agent 尚无任何测试**（`backend/tests` 无 react 相关用例；旧管线的覆盖在 test_specialized_agents 等）。

---

## 2. 逐项可行性分析

### 2.1 工具层 + FC 循环（方案第 6 节）——可行，核心决策点一个

**可行性本身没有问题**：GLM-4.7 / glm-4.5-air / DeepSeek 均支持原生 function calling，langchain-openai 0.2.14 的 `bind_tools` 可用；手写循环（方案反对 AgentExecutor/LangGraph）与仓库现有做法一致。

但要注意三个具体冲突：

1. **JSON-ReAct（现状） vs 原生 FC（方案）二选一。** 现有 `ReactMainAgent` 每步让模型输出严格 JSON 再自行解析（`_parse_decision` + 格式无效重试消耗步数）。方案要求 `bind_tools` + ToolMessage 回填。迁 FC 的收益：删掉 JSON 容错解析、"格式无效浪费一步"、重复提醒等补丁；代价：改 `loop`（约 150-200 行）+ `providers.py` 一处**必改点**——当前 `OpenAICompatibleProvider` 给所有请求硬编码了 `model_kwargs={"response_format": {"type": "json_object"}}`（providers.py:33），**json_object 与 tools 同请求在 DeepSeek 上不兼容、在智谱上行为未验证**，FC 路径必须换成不带 response_format 的客户端实例。
   现有注释里的实测数据（glm-4.7 关思考每步 4-8s 且 JSON 服从完美；开思考每步磨蹭 1-2 分钟，最差 563s）说明 JSON 路线是被验证过的。两条路线都能活，**建议按方案迁 FC，但把"fast 脑关思考跑循环"的实测结论原样继承**。
2. **方案禁令"不做意图前置分类器"与现状 `_route()` 冲突。** 现有循环前有一 LLM 分流（fast/deep + intent）。迁 FC 后 fast/deep 的主要用途（步数上限、脑选择）可以取消：步数统一 8 轮上限、循环统一用快脑、深度思考只做终稿整合（现有 `_deep_integrate` 正好就是这个角色，保留）。intent 仅保留为 UI 元数据（chat.py 已依赖 `intent_metadata.task_mode` 抑制角色卡片）。
3. **收底机制现状只完成一半。** 现有：循环耗尽→`_fallback_answer` 拼引用、deep 模式→思考模型终稿。缺：方案 6.6 的"强制总结轮"（禁用工具再要一次回答，成功率更高）与"连续 2 次超时退出"。补齐成本低。四类错误前缀（`[无结果]/[错误·配置]/[错误·运行时]`）与工具 description 四段模板：现有 `react_tools.py` 描述是单句式，**建议按模板重写**（这是方案里性价比最高的一条，意图判断成败在此）。

### 2.2 上下文组装管线（方案第 7 节）——基本已满足，差形式化

现有 system prompt 本身就是静态的（工具目录写死，动态数据走每步 user payload），前缀缓存友好；会话历史追加不重写。要补：环境事实层（时间/用户/能力边界——注意**容器时区**需设置 `TZ`）、动态段落固定顺序、>24 条压缩（现有 `conversation_summary_service` 已做 keep 6 / refresh 6，方案是 keep 12，参数级差异，保留现实现即可）。

### 2.3 记忆层（方案第 8 节）——最大增量，两处必须修订

- **存储（修订 ①）：方案默认 SQLite(aiosqlite) 不可取。** 后端跑在无状态容器里，`agent_data.db` 放容器内 = 每次重建丢数据；放卷里 = 出现"PostgreSQL + SQLite 双数据库"的备份/迁移噩梦，且项目已有 Alembic 体系统一管 schema。**正确做法：Repository 接口照抄，默认实现用现有 PostgreSQL/SQLAlchemy/Alembic**（新增 3-4 张表一个 migration）。方案"个人助手 <1 万条内存算余弦"的量级判断仍然成立。
- **Embedding（修订 ②）：不需要智谱 embedding-3。** 项目已有部署好的 BGE-M3 服务（`RemoteBGEEmbeddingProvider`，GPU 容器），中文效果与延迟都优于再引一条云端 embedding 链路，且零边际成本。方案"无 embedding 降级关键词匹配"的降级路径值得保留。
- **写入哲学冲突（需要产品决策）**：现有记忆体系是"**只提取候选、用户点确认才入库**"（`memory_agent` + 前端 `memory_suggestions` 确认流），方案的 MemoryJudge 是"每 6 轮自动提取自动写入"。技术上完全可行（`asyncio.create_task` 后台跑，失败只记日志，与方案一致），但把"用户确认"变成"AI 自主记忆"是产品语义变化。**折中建议：MemoryJudge 产出落库为 `source="ai_extracted"`，L0/L1 直接生效（低风险字段），L2 情景记忆沿用现有确认流**；或先加 feature flag。
- MemoryJudge 模型：方案写 GLM-4.6-flash，本仓库 fast 档是 glm-4.5-air——用现有 fast 档即可，不必新增模型配置。JSON 截断容错解析照方案做（智谱 JSON 稳定性风险方案第 13.1 条判断正确）。
- L1.5"战绩类工具顺手写缓存"：**本仓库没有战绩类工具**（星铁无胜率/段位数据源），对应物是"档案/材料查询结果缓存"，Phase 4 的可选项，不是必做项。

### 2.4 人格层（方案第 9 节）——机制全盘可行，内容全部要重写

三文件结构（identity/soul/tone_rules）+ 场景库 + 正经模式 + care cue：机制层与现有代码无冲突，`app/prompts/` 已有文件化先例，落地是加载器 + 注入器的纯增量。

但**内容层方案全文是"王者荣耀式毒舌损友"**（胜率/段位/连跪/出装/开黑），本仓库产品是**崩坏：星穹铁道智库 + 黑塔人格**（已有 `herta_style_persona.md`：自信、直接、轻微傲慢、禁止人身攻击）。soul.md 的"毒舌损友"人设与黑塔人设是两个产品方向，不能直接迁移。需要做的是：**把方案的"三文件结构 + 场景注入机制 + 双模式切换机制"套在黑塔人格上重写**；场景库 7 个也要星铁化（如 `lose_streak→深渊/忘却之庭卡关`、`hero_question→配队/养成提问`、`salt_mine→歪卡/抽卡吐槽`）。方案 9.6 care cue 用正则不调 LLM，简单可靠，照做。

### 2.5 SSE 事件协议（方案第 10 节）——可行，但要改成"映射"而不是"替换"（修订 ③）

方案设计：`POST /api/chat` 直连返回 SSE + 8 类事件 + 1-4 字 text_delta。
现状：`POST /jobs`(202) + `GET /jobs/{id}/events`（DB 轮询推流），已有 tool_started/tool_completed/thought/delta 等事件、**断线续传（Last-Event-ID）、进程重启任务恢复（recover_chat_jobs）、事件持久化**——这些是方案直连方案不具备的优点，且前端已按此契约实现。

**建议：不推翻，做映射**——保留 job 通道，把方案的事件语义对齐进去（`tool_call_started/result`、`text_delta` 等价于现有 `react.tool_started/tool_completed`、`answer.delta`）。Phase 4 真流式升级时，`astream` 切片走内存队列直推 SSE（DB 只落关键节点），250ms 轮询粒度对逐字流足够。**直连 POST SSE 会丢掉恢复能力且要重写前端，收益为零。**

### 2.6 异步任务（方案第 11 节）——与现有 job 体系天然契合

"提交-收尾"模式可完整落在现有 ChatJob 基建上：慢工具返回 `task_submitted` 事件，后台 `asyncio.create_task` 跑完后再开一个收尾 run。唯一要小心的：收尾 run 的会话/事件生命周期要新开 DB session（现有 `run_chat_job` 一个 session 用到底的写法不能照搬）。首个 slow 工具候选：`team_recommendation`（思考模型可达分钟级）。

### 2.7 模型分池（方案第 3.2 节）——修订 ④：复用现有 workload 池

| 方案 | 本仓库对应 | 结论 |
|---|---|---|
| 主对话 deepseek-chat / GLM-4.7 | intent 档 glm-4.7（关思考）跑循环 + deep 档（开思考）终稿整合 | 一致，实测调优已做过 |
| MemoryJudge GLM-4.6-flash | fast 档 glm-4.5-air | 用 fast 档，零新配置 |
| 场景/L2 检索 embedding-3 | BGE-M3 本地服务 | 用 BGE，省一条外部依赖 |
| 前缀缓存约定 | system prompt 已静态 | 只需补"静态段永不拼时间戳"的 review 规则 |

### 2.8 验收标准——必须星铁化重写（修订 ⑤）

方案 Phase 1-4 验收里"胜率查询""连败站队""段位秒答"在本产品中无对应物。等价改写示例：战绩分析→配队/材料/档案查询；"重启进程后答对主玩位置"→"重启后记得主玩角色与养成目标"（L0/L1 验收保留）；lose_streak 场景→"深渊又没满星，烦死了"。

### 2.9 方案禁令 vs 现状对照

| 禁令 | 现状 | 处置 |
|---|---|---|
| 不引入 AgentExecutor/LangGraph | 手写循环 ✅ | 无冲突 |
| 不做意图前置分类器 | `_route()` 存在 ⚠️ | 迁 FC 时移除/降级为 UI 元数据 |
| 记忆写入不阻塞主回复 | 无自动写入；job 均异步 ✅ | 照方案用 create_task |
| 子 agent 不抛裸异常 | 循环层 catch ✅，但无统一前缀 | 补四类前缀 |
| 游戏数据不凭记忆回答 | 引用编号+诚实性规则+fabrication_detector ✅ | 无冲突 |
| 人格在文件不在代码 | 大部分硬编码 ⚠️ | 落 `app/prompts/persona/` |
| 存储不写死、可换 | 方案默认 SQLite 与现状冲突 | Repository 接口 + PG 实现 |

---

## 3. 工具覆盖缺口（方案"全部子 agent 接入"的真实工作量）

当前 `react_tools.py` 只包了 **5/14** 个能力：catalog_search、character_profile、character_materials、team_recommendation、knowledge_search。
旧注册表里已存在而新主 Agent **接不上的**：`conversation_recall`（会话回忆）、`activity_strategy`（版本活动）、`memory`（记忆确认增删）、`weekly_plan`（每周规划）、`custom_character_creation/review`（自创角色）、`custom_team_recommendation`（自创角色配队）。
这不是回归理论——是用户从旧管线切到新主 Agent 后实际丢失的功能面。方案的 Phase 1 验收"现有子 agent 全部接入"恰好逼着补齐，估算每个工具 0.5 天内（多为薄包装）。

---

## 4. 部署分析

### 4.1 现有部署拓扑（不因本方案改变）

docker-compose（Windows 10/11 + Docker Desktop，≥12GB 内存，GPU 可选有 cpu overlay）：
`postgres 16.6` / `etcd` / `minio` / `milvus 2.5.2` / `bge-model-service（BGE-M3+reranker，CUDA，模型只读挂载宿主机 ./models）` / `backend（uvicorn，启动先 alembic upgrade head）` / `frontend`。
端口：前端 8030、后端 8000、BGE 8001、Milvus 19531。开发模式 = docker 起基础设施 + PyCharm/.venv 跑 FastAPI + npm 跑 Vite（docs/DEPLOYMENT.md）。

### 4.2 本方案带来的部署增量（结论：零新增服务，一个 migration，少量 env）

| 项 | 增量 | 说明 |
|---|---|---|
| 服务/容器 | **0** | 不引入向量库/Redis/新数据库；记忆检索用 JSONB 列 + 内存余弦（个人量级） |
| Python 依赖 | ≈0 | 不选 SQLite 则无需 aiosqlite；jieba 仅在要关键词降级时加；sse-starlette 不需要（StreamingResponse 现成） |
| DB 迁移 | 1 个 Alembic revision | `player_profiles`（L0/L1 JSONB）、`l15_facts`、`l2_memories`（embedding 存 JSONB）、可选 `care_cues`（或并入会话状态） |
| 环境变量 | 0-2 个 | 复用 ZHIPU_API_KEY；建议加 `MAIN_AGENT_IMPL`（react/cyrene 切换，回滚开关）与容器 `TZ=Asia/Shanghai`（环境事实层时间要对） |
| 人格/场景文件 | 纯新增 | `backend/app/prompts/persona/*.md` + `scenes/*.md`，随镜像走，无外部资源 |
| Milvus/知识库 | 不动 | 不需要重新 ingest |

### 4.3 延迟与成本预算（单人/小规模场景）

- 每轮对话：循环 1-4 步 × glm-4.7 关思考（实测 4-8s/步）+ 偶发深度整合（1-3 分钟，靠强制总结兜底封顶）；去掉 `_route` 分流每轮净省 1 次调用。
- 每 6 轮：MemoryJudge 一次 glm-4.5-air（1-3s，后台）+ 一次 embedding（本地 GPU，<100ms）。
- 记忆检索：内存余弦 <1 万条 <10ms；BGE 服务不可用时降级关键词，主流程不中断（方案 13.2 的降级设计保留）。
- SSE：DB 轮询 250ms/客户端，真流式后每 delta 最多 +250ms 显示延迟，可接受；不建议为了逐字流放弃持久化事件通道。
- 缓存：静态 system prompt 命中智谱前缀缓存后，人格+工具目录段近乎免费——方案 3.3 的约定照做，code review 盯"静态段不得拼动态值"。

### 4.4 滚动实施与回滚

- 装配点唯一（`dependencies.get_herta_main_agent`），Phase 1 可与现役 ReactMainAgent 并行装配，env 开关切换，**回滚 = 改一行 env**。
- 现有 28 个测试文件是安全网；**必须给新循环补测试**（当前 react 主 Agent 零覆盖）：工具注册/收底/引用编号/降级文案至少各一条，用 mock LLMProvider 即可，无需真实 key。
- 数据风险：记忆表是新增表，不动 conversations/user_memories，Phase 2 出问题可直接 drop。

### 4.5 部署风险清单

1. **智谱 FC + response_format 冲突**（最高优先验证点）：FC 客户端实例必须去掉 `response_format=json_object`，先写一个 5 行 smoke 脚本对 glm-4.7 / glm-4.5-air 各验一次 bind_tools。
2. **SQLite 进容器**（若照方案原文）：数据随容器销毁丢失；修订为 PostgreSQL 后此风险消除。
3. **容器时区**：环境事实层输出"当前时间"，容器默认 UTC 会与用户错 8 小时；compose 加 TZ。
4. **Windows 开发机编码**：persona md 文件统一 UTF-8，加载器显式 `encoding="utf-8"`。
5. **长回复占用**：deep 整合最差 3 分钟，前端已有分阶段进度条可承载；强制总结兜底后封顶可预期。
6. **并发**：aiosqlite 单写者问题随 PG 选型消失；PG 侧记忆写并入现有同步 SQLAlchemy 模式，个人规模无锁竞争。

---

## 5. 修订后的实施路线（映射方案 Phase 1-4）

| Phase | 内容（本仓库语境） | 预估 |
|---|---|---|
| 0 | 先提交/固定现有 ReactMainAgent 未提交改动（当前主链路是"裸奔"状态），补基础测试 | 0.5 天 |
| 1 | FC 循环改造（bind_tools + ToolMessage + 无 response_format 客户端 + 分档超时 + 强制总结收底 + 四类错误前缀 + 工具 description 四段模板）+ 补齐 5 个缺失工具 + `docs/integration-map.md` | 2-3 天 |
| 2 | 记忆层：Alembic 三表 + Repository(PG) + MemoryJudge(fast 档) + 注入器 + care cue；确认流与自动写入的边界按 2.3 折中方案 | 3-4 天 |
| 3 | 人格层：三文件黑塔化重写 + 7 场景星铁化 + 注入器 + 正经模式 | 1.5-2 天（内容写作占大头） |
| 4 | astream 真流式（内存通道直推 SSE）+ 慢任务提交-收尾（先给 team_recommendation）+ L1.5 档案缓存 + 前缀缓存验证 | 2-3 天 |

总计约 9-12 个工作日（兼职节奏 2-3 周）。Phase 1 完成即可切换上线（env 开关），Phase 2-4 逐个灰度。

---

## 6. 最终判定

1. **方案可行**，且与仓库既有方向高度互补：方案提供"记忆层 + 人格层 + 收底规范"，仓库已有"job 事件流 + 工具循环骨架 + RAG/配队等领域能力"。没有根本性架构冲突。
2. **不能照原文执行**的 7 处修订：①存储 SQLite→PostgreSQL（保 Repository 接口）；②SSE 直连→沿用 job 事件通道做事件映射；③单轮 60s 超时→fast 60s / deep 240s 分档；④模型分池→复用现有 workload（judge=fast 档、embedding=BGE）；⑤验收标准与人设内容全面星铁化（黑塔替毒舌损友）；⑥意图前置 `_route` 按禁令移除/降级；⑦工具覆盖 5/14→补齐全部子 agent。
3. **执行顺序关键**：先把未提交的 ReactMainAgent 现状提交并补测试，再动方案 Phase 1，避免在无版本管理的工作区上叠加大改。
