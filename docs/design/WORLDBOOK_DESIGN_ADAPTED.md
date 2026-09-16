# Worldbook 注入层 · 仓库适配版（基于 star-rail-worldbook-design.md v1.0）

> **性质**：对 `D:\Tools\Cyrene\Cyrene-Agent-master\star-rail-worldbook-design.md` 的落地适配。原设计的机制（DMAE 状态机、条目格式 v1.1、两层分工、降级模式）**全部保留**；本文只做三类事：①把"实施时再看"的挂点落实为仓库精确位置；②修正设计稿里的 3 处技术瑕疵；③列出需要用户补充的资料清单。
> **结论先行：方案可行，且质量高——它正面解决了痛点 #1 的结构性成因（背景式知识被迫依赖工具调用决策）。数学和格式不动，改动全部在挂点、时序和验收参数上。**

---

## 1. 与既有结论的关系（覆盖关系声明）

- 本设计**修订**工作簿 Q7 的结论：从"知识来源已解决、规格无需改"修正为"**Milvus 工具层不动 + 新增骨架知识注入层，两层并存**"。分工判据（"是否应该在用户没提问时也影响回复"）保留，判定清晰，无冲突。
- 与主 agent 规格（main-agent-spec.md）的关系：worldbook 注入属于上下文管线的新增段，对应规格 §7 的"⑤相关记忆"旁路——**与记忆层（Phase 2）互不依赖**，可独立交付。
- 与人格草稿（HERTA_PERSONA_DRAFT.md）的关系：条目【写法】层按黑塔人格撰写（已拍板），不存在设计稿 §11.4 担心的"人格方向未定"问题。

## 2. 时序决策（推荐：内容先行，接线排 Phase 1 之后）

| 事项 | 时点 | 理由 |
|---|---|---|
| loader / engine / injector 代码 + 测试 | 随时可做 | agent 无关，纯函数 + PG 状态表 |
| 种子条目 24 条内容起草 | 随时可做（ZCode 从 docs/ 蒸馏起草，用户只审） | 只依赖 docs 语料与人格草稿 |
| **接线**（AgentContext 字段 + chat.py 计算点 + _loop_prompt 渲染） | **Phase 1（FC 改造+收底）之后** | W01 验收依赖"日志确认未调工具"的稳定循环；避免 FC 改造与注入层两个变量同时上线，出问题分不清归因 |
| W01-W08 验收 | 接线后 | 依赖接线 |

## 3. 接入点精确化（原设计 §7 的"实施时再看"→ 落实）

### 3.1 数据流

```
chat.py :: _execute_message()                          ← 计算点（唯一新增 LLM-free 逻辑）
  conversation_history 就绪后（chat.py:331-344 之后）：
    last_reply = 历史里最后一条 assistant 消息（无则空串）
    injection = worldbook.on_turn_and_build(
                    conversation_id, user_msg=request.message, model_text=last_reply)
  AgentContext(active_knowledge=injection, ...)        ← base.py 新增字段（dataclass 加一行）
      │
      ▼
react_main_agent.py :: _loop_prompt()                  ← 渲染点（每步可见）
  parts 装配中，插入位置：`if history:` 块之后、`if citation_lines:` 之前
      │
      ▼
react_main_agent.py :: _deep_integrate()               ← 兜底整合也要带上（prompt_parts 加一行）
```

### 3.2 为什么插在"近期对话之后、可用引用之前"（对原设计 §2 槽位的修正）

原设计说注入块"紧贴最新用户消息之前"——那是单请求场景的最优解。本仓库的循环是**每步重发整个 payload**（`_loop_prompt` 每步重建），槽位要按"轮内前缀缓存"选：放在 `近期对话`之后、`可用引用/已完成步骤`（这两段随步数增长）之前，注入块就落在**本轮逐步增长的稳定前缀内**——同一轮的第 2-N 步请求里，注入块字节不变，吃轮内前缀缓存；放在用户消息之后则会被增长的步骤段挤出稳定区。
验收锚点不变：静态 system 的 token 序列逐字节一致（注入不碰 system）。

### 3.3 匿名会话边界

`optional_current_user` 下 user 为 None → conversation 为 None → 引擎直接跳过（`active_knowledge=""`）。激活状态以 conversation_id 为粒度，匿名无会话即无状态，与设计 §5.4 的隔离决策自洽。

### 3.4 计算点为什么放 chat.py 而不是 agent.run() 里

`ReactMainAgent` 是 `lru_cache` 的单例（dependencies.py:87），保持无状态是既有设计；chat.py 已经是 memories/entities/history 的组装点，且 job 路径（run_chat_job）复用 `_execute_message`，一条链路全覆盖。

## 4. 对原设计的三处技术修正

1. **§5.2 的 Rm clamp 未实现**：注释写"clamp Rm ≤ 本轮衰减量（模型话语不能抵消遗忘）"，但代码直接 `activation + rm` 没夹。按注释语义实现：先用更新前的 silence 值算出本轮衰减量 d，再 `rm = min(rm, d)`。
2. **W03 验收阈值与公式不匹配**：γ=0.5、Bu=20 时，沉默 5 轮的久别重逢单次增益 ≈ 20×(1+0.5×ln6) ≈ **37.9 分**，达不到 W03 写的"+40+"（要沉默约 8 轮才到 42）。修正：W03 改为"单次增益 ≥30 且显著高于基础值 20"，或测试用例把间隔拉到 8+ 轮。
3. **W06 的"≤8 条"口径含糊**：glossary 4 条常驻 + 激活条目 ≤8，注入块总数最多 12。修正：W06 表述改为"常驻 ≤4、激活 ≤8、总量受 2500 字预算硬约束"（injector 的贪心装包已保证）。

## 5. 落点与数据模型（确认采纳，微调一处）

```
backend/app/knowledge/worldbook/
    __init__.py  loader.py  engine.py  injector.py
    entries/ 00_glossary.md 10_herta.md 20_world.md 30_characters.md 40_canon.md
backend/alembic/versions/xxxx_add_worldbook_states.py
backend/tests/test_worldbook_loader.py  test_worldbook_engine.py  test_worldbook_injection.py
```

- `worldbook_states` 表结构与设计稿 §5.4 一致（PG，主键 (conversation_id, entry_id)）。仓库用同步 SQLAlchemy：读 = 按 conversation_id 全取；写 = postgresql `insert().on_conflict_do_update` upsert 变更行。61 条目 × 每轮全量重算的成本可忽略。
- 并发注记：同一 conversation 的两个 chat job 理论上可并发（create_chat_job 无会话级锁），激活分 last-write-wins，误差一轮以内、无锁可接受——与设计稿判断一致，加一句说明即可。
- 条目格式 v1.1（标题即触发词 + 元数据空行终结）**照单采纳**，并配一致性校验脚本（每条必有【事实】；【写法】【口径】可选但不得空串；触发词跨条目不重复、≥2 字、禁高频子串）。Cyrene 原型（5 文件 61 条）已核对，格式兼容。

## 6. 验收映射（W01-W08 → 仓库测试）

| 验收 | 仓库落法 |
|---|---|
| W01 未调工具自然带设定 | 人工验收（看 react.tool_started 事件流）+ 单测：注入块含"人偶"事实时 prompt 含该文本 |
| W02 数据走工具 | T 系列复测（materials 问题仍调 character_materials） |
| W03 久别重逢 | test_worldbook_engine：模拟 silence 序列断言激活分（用 §4.2 修正后的阈值） |
| W04 双用户隔离 | test_worldbook_engine：两个 conversation_id 状态独立 |
| W05 重启恢复 | test_worldbook_injection：写库→新 engine 实例懒加载→状态一致 |
| W06 预算硬约束 | test_worldbook_injection：构造超预算条目断言截断行为（§4.3 修正后口径） |
| W07 别名触发 | test_worldbook_loader/engine：Mydei/迈德漠斯 类条目 |
| W08 无关轮空注入 | test_worldbook_injection：无命中 → 空串 |
| 前缀锚点 | 既有静态 system 断言 + 注入前后 system 字节一致单测 |
| 误命中审查 | **缺用户语料**（见 §8 资料①） |

## 7. 内容生产流程（对原设计 §8 的改良）

原设计估"种子内容 2-3 天，主要工作量在内容"——那是按用户手写估的。改为：**ZCode 从 `docs/`（data_lore_pages、data_character_story、hsr_nanoka_characters、content_1257_版本活动 等）蒸馏起草 24 条**，触发词按 §4.4 规则撰写、【写法】按黑塔人格草稿口吻，产出后**用户只做审读**（重点审触发词和口径，不写正文）。用户工作量从 2-3 天降到约半天审读。
40_canon.md 的"高频考据易错点"条目设计为持续追加型：上线后把用户实际问错的问题记进去（这一条天然需要真实使用语料）。

## 8. 需要用户补充的资料（唯一阻塞项清单）

| # | 资料 | 用途 | 格式要求 |
|---|---|---|---|
| ① | **真实日常语料 ≥50 条**（你和助手的实际对话，或你预期会这么说的话） | 触发词误命中审查（W07/风险1）+ "自然问句"触发词的撰写素材——没有它，触发词只能靠我按书面语猜测 | txt/jsonl/截图均可，无需清洗 |
| ② | **口味输入**：24 条种子之外，最希望"没问也知道"的话题/角色 Top5；glossary 的"命途-星神速查表"是否值得常驻（每轮占约 300 字预算） | 决定条目优先级与常驻取舍 | 几行字 |
| ③ | **版本口径基线**：当前游戏版本号；`docs/content_1257_版本活动` 覆盖到哪个版本、之后是否继续更新；"官方盖章 vs 社区考据"的边界例子 1-2 个 | 40_canon.md（版本剧情节点口径表）的时效性与红线 | 几行字 |
| ④ | **时序确认**（可默认按 §2 推荐）：内容起草立即并行开始，接线排 Phase 1 之后 | 排期 | 一句话 |
| ⑤ | （可选）**第二个测试账号** | W04 双用户并发隔离验收 | 注册一个即可 |

**不需要提供的**：Milvus 导出（docs/ 就是源头）、Cyrene 原型条目（已核对）、DMAE 公式（设计稿已带全）、API key（已在 .env）。

## 9. 工作量复估（对原设计 §10）

| 步骤 | 原估 | 复估 | 说明 |
|---|---|---|---|
| loader + 校验脚本 | 0.5 天 | 0.5 天 | 不变 |
| engine + 迁移 + 懒加载 | 1 天 | 1 天 | 不变（含 Rm clamp 修正） |
| injector + 接线 | 0.5 天 | 0.5 天 | 挂点已精确化，反而更省 |
| 种子 24 条 | 2-3 天（用户写） | **ZCode 起草 1 天内，用户审 0.5 天** | 流程改良（§7） |
| W01-W08 + 误命中审查 | 0.5 天 | 0.5-1 天 | 误命中审查依赖资料①到位 |
| 合计 | 4.5-5.5 天 | **3-3.5 天**（用户参与 ≈ 半天 + 审读） | |

**明确不做（v2）**：embedding 语义触发（BGE-M3 模糊命中）、DMAE 参数仿真器、token-budget 背包调度、条目热度统计后台——与原设计一致。
