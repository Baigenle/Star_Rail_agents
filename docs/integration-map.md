# 接入点映射表（main-agent-spec.md §1 产出，2026-09-05）

> 规格 Phase 1 开工前要求的盘点产物。详细版见 `docs/design/MAIN_AGENT_SPEC_FEASIBILITY.md` 与 `D:\Tools\Cyrene\Cyrene-Agent-master\discussion-workbook.md` 第 1 部分。

| # | 盘点项 | 产出 |
|---|---|---|
| 1 | 聊天入口 | `backend/app/api/v1/routes/chat.py`：`POST /chat/messages`（同步）+ `POST /chat/jobs`（后台）+ `GET /chat/jobs/{id}/events`（job 事件 SSE，落库+断线续传）；装配点 `_execute_message()` |
| 2 | 主 Agent → 领域工具 | 进程内异步调用。现役：`FCMainAgent`（原生 Function Calling，最多 8 轮），统一注册 10 项领域工具；`ReactMainAgent` 保留为显式切换及 FC 客户端不可用时的兼容回退，slow=True 仅 team_recommendation |
| 3 | 模型调用 | `backend/app/llm/providers.py`：OpenAICompatibleProvider（zhipu/deepseek/qwen，workload 分档）；FC 专用 `create_fc_llm_provider`（无 response_format，实测冲突已规避） |
| 4 | 会话历史/流式 | PostgreSQL（conversations/chat_messages）+ 渐进摘要（conversation_summary_service，keep6/refresh6）；SSE 走 chat_job_events 落库轮询 |
| 5 | 人格文本 | 已落库 `backend/app/prompts/persona/{system,identity,soul,tone_rules}.md`（问答卷 12 题定调，用户已审）；台词库 `docs/design/persona/herta_quotes.md` |
| 6 | 数据库 | PostgreSQL 16.6 + SQLAlchemy 2.0 同步 + Alembic（规格存储接口的默认实现，不用 SQLite） |

## FC 链路落点（Phase 1 已实施）

| 组件 | 文件 | 说明 |
|---|---|---|
| FC 工具层 | `app/agents/fc_tools.py` | pydantic 参数模型、四段 description、safe_execute 四类前缀、观察文本 4000 截断、[Cn] 重排 |
| FC 主循环 | `app/agents/fc_main_agent.py` | bind_tools 循环（8 轮上限、单轮 60s、连续 2 次超时退出）、强制总结轮（90s）、降级文案、引用编号、页面动作 |
| LLM 客户端 | `app/llm/providers.py` | `create_fc_llm_provider`（glm-4.7 关思考 / deepseek-v4-flash 裸客户端） |
| 装配开关 | `app/api/dependencies.py` + `MAIN_AGENT_IMPL` | fc（默认，现役）/ react（兼容回退）；FC 客户端不可用时自动回退 react |
| 人格静态段 | `app/prompts/persona/` | system+identity+soul+tone_rules，逐字节稳定吃前缀缓存 |
| 单测 | `tests/test_fc_main_agent.py` | 6 条路径全绿（工具→答/异常前缀/耗尽总结/超时总结/直答/未知工具配置错误） |

## 待办（Phase 1 剩余 → Phase 2-4）

1. ~~补齐工具覆盖~~ ✅ **Phase 1.3 完成（2026-09-05）**：新增 character_build / activity_strategy / weekly_planning / custom_character_guide / custom_character_review，工具 5→10；memory / conversation / conversation_recall / answer_review 明确不做工具（理由见工作簿 1.2）。覆盖与安全执行测试 `tests/test_fc_tools_coverage.py` 4 条全绿；真实冒烟：weekly_planning（无方案时诚实给通用优先级）、activity_strategy（资料未收录时明说）、character_build（T02 解锁）
2. **真流式**：astream 切片走内存通道直推 SSE（Phase 4）；T04 断服务集成验收 ✅ 已过（见工作簿证据③）
3. ~~记忆层~~ ✅ **Phase 2 完成（2026-09-05，commit 37deddc）**：三表迁移 0013 + Repository + MemoryJudge（≥6轮/闲置30分钟兜底、JSON 容错、置信度合并）+ 注入器（画像全量 + L2 余弦召回，关键词降级）+ care cue（迁移 0014）+ chat.py 接线（后台任务不阻塞回复）
4. ~~人格场景注入~~ ✅ **Phase 3 完成（2026-09-05）**：场景库 7 个（lose_streak/tilted 带正经模式标记）落 `app/prompts/persona/scenes/`；匹配器 BGE 向量 ≥0.72 优先、关键词降级（平局正经优先）、daily_chat 兜底不主动注入；注入随 memory_injection 进动态段。端到端冒烟：「深渊又没满星 烦死了」→ 先站队零嘲讽零工具
5. **Worldbook 注入层**（独立设计，见 `docs/design/WORLDBOOK_DESIGN_ADAPTED.md`）：内容已产出待审，接线排在 Phase 1 验收后；触发词审查待用户语料
6. **已知陈旧测试**：`tests/test_rag_agent.py::test_herta_main_agent_keeps_grounded_sub_agent_facts_unchanged` 在 `602e27c`（React 提交）即失败——断言旧管线开场白，需随 React 迁移更新（与 Phase 1.3 无关，已用 stash 验证归属）
7. **Phase 4**：~~4.1 真流式~~ ✅ **完成（2026-09-05）**——`AgentContext.delta_sink` + FC 循环 `astream` 逐字转发（tool_call 片段出现即停转发，流式异常回退 ainvoke）；chat.py `_DeltaFlusher` 合并冲刷（64字/0.5s）落 `answer.delta` + `partial_answer` 权威字段（前端零改动，漂移自愈）；实测 133 次增量、7s 流式窗口、流式文本与最终回答一致。**待做**：4.2 慢任务提交-收尾（team_recommendation）、4.3 L1.5 事实缓存、4.4 前缀缓存用量验证
